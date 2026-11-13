import asyncio
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Optional
import httpx
import mutagen
from mutagen.flac import FLAC
from backend.app.config import settings
from backend.app.services.logger_service import log_event


@dataclass
class MusicBrainzReleaseInfo:
    mbid: str
    artist: str
    album: str
    year: Optional[int]
    cover_url: str


class MetadataService:
    mb_base_url = "https://musicbrainz.org/ws/2"
    caa_base_url = "https://coverartarchive.org/release"

    def __init__(self) -> None:
        self._last_mb_call: float = 0.0
        self._lock = asyncio.Lock()

    async def _throttle_mb(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_mb_call
            if elapsed < 1.1:
                await asyncio.sleep(1.1 - elapsed)
            self._last_mb_call = time.monotonic()

    async def lookup_release(self, artist: str, album: str) -> Optional[MusicBrainzReleaseInfo]:
        if not artist or not album:
            return None
        await self._throttle_mb()
        safe_artist = artist.replace('"', "")
        safe_album = album.replace('"', "")
        query = f'artist:"{safe_artist}" AND release:"{safe_album}"'
        headers = {
            "User-Agent": settings.musicbrainz_user_agent,
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                resp = await client.get(
                    f"{self.mb_base_url}/release/",
                    params={"query": query, "fmt": "json", "limit": 3},
                    headers=headers,
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                releases = data.get("releases") or []
                if not releases:
                    return None
                best = releases[0]
                mbid = str(best.get("id") or "")
                title = str(best.get("title") or album)
                date_str = str(best.get("date") or "")
                year = int(date_str[:4]) if len(date_str) >= 4 and date_str[:4].isdigit() else None
                ac = best.get("artist-credit") or []
                mb_artist = str(ac[0].get("name")) if ac and isinstance(ac[0], dict) else artist
                cover_url = f"{self.caa_base_url}/{mbid}/front-500" if mbid else ""
                return MusicBrainzReleaseInfo(
                    mbid=mbid,
                    artist=mb_artist,
                    album=title,
                    year=year,
                    cover_url=cover_url,
                )
        except Exception as exc:
            log_event("WARNING", "SYSTEM", f"MusicBrainz lookup warning: {exc}")
            return None

    async def download_cover_art(self, cover_url: str, target_path: Path) -> bool:
        if not cover_url:
            return False
        if target_path.exists() and target_path.stat().st_size > 0:
            return True
        headers = {"User-Agent": settings.musicbrainz_user_agent}
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(cover_url, headers=headers)
                if resp.status_code == 200 and resp.content:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_bytes(resp.content)
                    return True
        except Exception:
            pass
        return False

    def embed_tags(
        self,
        file_path: Path,
        artist: str,
        album: str,
        title: str,
        track_number: int = 1,
        disc_number: int = 1,
        year: Optional[int] = None,
        mbid: str = "",
    ) -> bool:
        if not file_path.exists():
            return False
        try:
            ext = file_path.suffix.lower()
            if ext == ".flac":
                audio = FLAC(str(file_path))
                audio["artist"] = artist
                audio["album"] = album
                audio["title"] = title
                audio["tracknumber"] = str(track_number)
                audio["discnumber"] = str(disc_number)
                if year:
                    audio["date"] = str(year)
                if mbid:
                    audio["musicbrainz_albumid"] = mbid
                audio.save()
                return True

            easy = mutagen.File(str(file_path), easy=True)
            if easy is not None:
                easy["artist"] = [artist]
                easy["album"] = [album]
                easy["title"] = [title]
                easy["tracknumber"] = [str(track_number)]
                easy["discnumber"] = [str(disc_number)]
                if year:
                    easy["date"] = [str(year)]
                easy.save()
                return True
        except Exception as exc:
            log_event("WARNING", "AUDIT", f"Could not embed metadata tags into {file_path.name}: {exc}")
        return False


metadata_service = MetadataService()
