import asyncio
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import httpx

LOSSLESS_FORMATS = {"FLAC", "24BIT FLAC", "WAV", "WAVE", "ALAC", "AIFF", "APE", "WV"}


def normalize_format_name(raw_fmt: str) -> str:
    fmt = (raw_fmt or "").strip().upper()
    if "24BIT FLAC" in fmt or "24-BIT FLAC" in fmt:
        return "FLAC"
    if "FLAC" in fmt or "AUDIO/FLAC" in fmt or "AUDIO/X-FLAC" in fmt:
        return "FLAC"
    if "WAV" in fmt or "WAVE" in fmt or "PCM" in fmt:
        return "WAV"
    if "ALAC" in fmt or "APPLE LOSSLESS" in fmt:
        return "ALAC"
    if "AIFF" in fmt:
        return "AIFF"
    if "OGG" in fmt or "VORBIS" in fmt:
        return "OGG"
    if "OPUS" in fmt:
        return "OPUS"
    if "MP3" in fmt or "MPEG" in fmt:
        return "MP3"
    if "AAC" in fmt or "M4A" in fmt:
        return "AAC"
    return fmt or "UNKNOWN"


def is_lossless_format(raw_fmt: str) -> bool:
    norm = normalize_format_name(raw_fmt)
    return norm in {"FLAC", "WAV", "ALAC", "AIFF"} or (raw_fmt or "").strip().upper() in LOSSLESS_FORMATS


def extract_year(value: Any) -> Optional[int]:
    if not value:
        return None
    if isinstance(value, int) and 1600 <= value <= 2100:
        return value
    match = re.search(r"\b(1[6-9]\d{2}|20\d{2})\b", str(value))
    if match:
        return int(match.group(1))
    return None


def parse_duration(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if ":" in text:
        parts = text.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(float(parts[1]))
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
        except ValueError:
            return None
    try:
        return int(float(text))
    except ValueError:
        return None


@dataclass
class NormalizedTrack:
    track_number: int
    title: str
    format: str
    is_lossless: bool
    size_bytes: int = 0
    disc_number: int = 1
    artist: str = ""
    duration_seconds: Optional[int] = None
    bit_depth: Optional[int] = None
    sample_rate: Optional[int] = None
    download_url: str = ""
    checksum_md5: str = ""
    checksum_sha1: str = ""
    checksum_crc32: str = ""


@dataclass
class NormalizedRelease:
    external_id: str
    source: str
    artist: str
    album: str
    primary_format: str
    is_lossless: bool
    year: Optional[int] = None
    cover_url: str = ""
    available_formats: List[str] = field(default_factory=list)
    quality_label: str = ""
    bit_depth: Optional[int] = None
    sample_rate: Optional[int] = None
    track_count: int = 0
    total_size_bytes: int = 0
    license: str = "Verify individual item rights"
    source_url: str = ""
    download_availability: str = "DIRECT"  # DIRECT, MAGNET, ACCOUNT_REQUIRED, STREAM_ONLY
    magnet_uri: str = ""
    seeders: Optional[int] = None
    leechers: Optional[int] = None
    extra_metadata: Dict[str, Any] = field(default_factory=dict)
    tracks: List[NormalizedTrack] = field(default_factory=list)


class BaseSourceAdapter(ABC):
    source_id: str = "base"
    source_name: str = "Base Source"
    website: str = ""
    priority: str = "Normal"
    supports_albums: bool = True
    supports_tracks: bool = True
    supports_direct_lossless: bool = True
    requires_api_key: bool = False
    description: str = ""
    limitations: str = ""
    rate_limit_per_sec: float = 2.0

    def __init__(self) -> None:
        self._last_request_ts: float = 0.0
        self._lock = asyncio.Lock()
        self.user_agent = (
            "OpenMusicArchiveManager/1.0 "
            "(https://github.com/Tomajashi/openmusic-archive-manager; self-hosted music manager)"
        )

    async def _throttle(self) -> None:
        if self.rate_limit_per_sec <= 0:
            return
        min_interval = 1.0 / self.rate_limit_per_sec
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_ts
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            self._last_request_ts = time.monotonic()

    async def _get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 20.0,
        max_retries: int = 3,
    ) -> Any:
        req_headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if headers:
            req_headers.update(headers)

        backoff = 1.0
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            await self._throttle()
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    response = await client.get(url, params=params, headers=req_headers)
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < max_retries - 1:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    response.raise_for_status()
                    return response.json()
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
        if last_exc:
            raise last_exc
        return {}

    @abstractmethod
    async def search(
        self,
        artist: str = "",
        album: str = "",
        track: str = "",
        limit: int = 10,
    ) -> List[NormalizedRelease]:
        """Search the archive and return normalized releases."""
        raise NotImplementedError
