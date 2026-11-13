from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Dict, List, Optional

TRUE_LOSSLESS_CODECS = {
    "flac",
    "alac",
    "wavpack",
    "ape",
    "tta",
    "pcm_s16le",
    "pcm_s16be",
    "pcm_s24le",
    "pcm_s24be",
    "pcm_s32le",
    "pcm_s32be",
    "pcm_f32le",
    "pcm_f64le",
    "pcm_u8",
}

LOSSY_CODECS = {"mp3", "aac", "vorbis", "opus", "wmav2", "ac3", "eac3", "mp2"}


@dataclass
class AudioVerificationReport:
    is_valid_audio: bool
    codec_name: str
    bit_depth: Optional[int]
    sample_rate: Optional[int]
    channels: Optional[int]
    duration_seconds: Optional[int]
    bit_rate: Optional[int]
    is_verified_lossless: bool
    checksum_verified: Optional[bool]
    audit_flags: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    error_message: str = ""


def verify_checksums(
    file_path: Path,
    expected_md5: str = "",
    expected_sha1: str = "",
) -> Optional[bool]:
    if not expected_md5 and not expected_sha1:
        return None
    if not file_path.exists():
        return False

    md5_hasher = hashlib.md5() if expected_md5 else None
    sha1_hasher = hashlib.sha1() if expected_sha1 else None

    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            if md5_hasher:
                md5_hasher.update(chunk)
            if sha1_hasher:
                sha1_hasher.update(chunk)

    if md5_hasher and md5_hasher.hexdigest().lower() != expected_md5.strip().lower():
        return False
    if sha1_hasher and sha1_hasher.hexdigest().lower() != expected_sha1.strip().lower():
        return False
    return True


def inspect_audio_with_ffprobe(
    file_path: Path,
    expected_size_bytes: int = 0,
    expected_md5: str = "",
    expected_sha1: str = "",
) -> AudioVerificationReport:
    flags: List[str] = []

    if not file_path.exists():
        return AudioVerificationReport(
            is_valid_audio=False,
            codec_name="",
            bit_depth=None,
            sample_rate=None,
            channels=None,
            duration_seconds=None,
            bit_rate=None,
            is_verified_lossless=False,
            checksum_verified=False,
            audit_flags=["INCOMPLETE_DOWNLOAD", "FILE_NOT_FOUND"],
            error_message="Downloaded file does not exist on disk.",
        )

    actual_size = file_path.stat().st_size
    if actual_size == 0:
        return AudioVerificationReport(
            is_valid_audio=False,
            codec_name="",
            bit_depth=None,
            sample_rate=None,
            channels=None,
            duration_seconds=None,
            bit_rate=None,
            is_verified_lossless=False,
            checksum_verified=False,
            audit_flags=["INCOMPLETE_DOWNLOAD", "CORRUPT_AUDIO_FILE"],
            error_message="Downloaded file is 0 bytes.",
        )

    if expected_size_bytes > 0 and actual_size < int(expected_size_bytes * 0.90):
        flags.append("INCOMPLETE_DOWNLOAD")

    checksum_ok = verify_checksums(file_path, expected_md5=expected_md5, expected_sha1=expected_sha1)
    if checksum_ok is False:
        flags.append("CHECKSUM_MISMATCH")

    ext = file_path.suffix.lower().lstrip(".")
    claims_lossless_ext = ext in {"flac", "wav", "wave", "alac", "aiff"}

    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
        if proc.returncode != 0 or not proc.stdout.strip():
            flags.append("CORRUPT_AUDIO_FILE")
            return AudioVerificationReport(
                is_valid_audio=False,
                codec_name="",
                bit_depth=None,
                sample_rate=None,
                channels=None,
                duration_seconds=None,
                bit_rate=None,
                is_verified_lossless=False,
                checksum_verified=checksum_ok,
                audit_flags=flags,
                error_message="ffprobe failed to decode audio container.",
            )
        probe_data = json.loads(proc.stdout)
    except Exception as exc:
        flags.append("CORRUPT_AUDIO_FILE")
        return AudioVerificationReport(
            is_valid_audio=False,
            codec_name="",
            bit_depth=None,
            sample_rate=None,
            channels=None,
            duration_seconds=None,
            bit_rate=None,
            is_verified_lossless=False,
            checksum_verified=checksum_ok,
            audit_flags=flags,
            error_message=f"ffprobe inspection error: {exc}",
        )

    streams = probe_data.get("streams") or []
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not audio_stream:
        flags.append("CORRUPT_AUDIO_FILE")
        return AudioVerificationReport(
            is_valid_audio=False,
            codec_name="",
            bit_depth=None,
            sample_rate=None,
            channels=None,
            duration_seconds=None,
            bit_rate=None,
            is_verified_lossless=False,
            checksum_verified=checksum_ok,
            audit_flags=flags,
            error_message="No valid audio stream found in file.",
        )

    codec_name = str(audio_stream.get("codec_name") or "").lower()
    sample_rate_str = audio_stream.get("sample_rate")
    sample_rate = int(sample_rate_str) if sample_rate_str and str(sample_rate_str).isdigit() else None
    channels = int(audio_stream.get("channels") or 0) or None

    if not sample_rate or sample_rate <= 0 or not channels or channels <= 0:
        flags.append("CORRUPT_AUDIO_FILE")
        return AudioVerificationReport(
            is_valid_audio=False,
            codec_name=codec_name,
            bit_depth=None,
            sample_rate=sample_rate,
            channels=channels,
            duration_seconds=None,
            bit_rate=None,
            is_verified_lossless=False,
            checksum_verified=checksum_ok,
            audit_flags=flags,
            error_message="Audio stream has invalid/zero sample rate or channel count (corrupt header).",
        )

    bits_raw = audio_stream.get("bits_per_raw_sample") or audio_stream.get("bits_per_sample")
    bit_depth = int(bits_raw) if bits_raw and str(bits_raw).isdigit() and int(bits_raw) > 0 else None
    if bit_depth is None and codec_name == "pcm_s16le":
        bit_depth = 16
    elif bit_depth is None and codec_name == "pcm_s24le":
        bit_depth = 24

    fmt_info = probe_data.get("format") or {}
    dur_raw = fmt_info.get("duration") or audio_stream.get("duration")
    try:
        duration_seconds = int(float(dur_raw)) if dur_raw is not None else None
    except ValueError:
        duration_seconds = None

    br_raw = fmt_info.get("bit_rate") or audio_stream.get("bit_rate")
    try:
        bit_rate = int(br_raw) if br_raw is not None else None
    except ValueError:
        bit_rate = None

    # Check embedded metadata tags (format.tags or audio_stream.tags)
    raw_tags: Dict[str, str] = {}
    for tag_src in (fmt_info.get("tags") or {}, audio_stream.get("tags") or {}):
        for k, v in tag_src.items():
            raw_tags[str(k).lower()] = str(v)

    has_title = bool(raw_tags.get("title") or raw_tags.get("track"))
    has_artist = bool(raw_tags.get("artist") or raw_tags.get("album_artist") or raw_tags.get("performer"))
    if not (has_title and has_artist):
        flags.append("MISSING_METADATA")

    # Verify true lossless status
    is_true_lossless = codec_name in TRUE_LOSSLESS_CODECS

    if claims_lossless_ext and not is_true_lossless:
        flags.append("FLAC_CONTAINING_LOSSY_AUDIO")

    if is_true_lossless and sample_rate and sample_rate < 44100:
        flags.append("SUSPICIOUS_LOW_SAMPLE_RATE")

    if is_true_lossless and bit_rate and bit_rate < 250_000 and (duration_seconds or 0) > 10:
        flags.append("SUSPICIOUS_LOW_BITRATE_FLAC")

    if duration_seconds is not None and duration_seconds <= 0:
        flags.append("INCOMPLETE_DOWNLOAD")

    return AudioVerificationReport(
        is_valid_audio=True,
        codec_name=codec_name,
        bit_depth=bit_depth,
        sample_rate=sample_rate,
        channels=channels,
        duration_seconds=duration_seconds,
        bit_rate=bit_rate,
        is_verified_lossless=is_true_lossless and "FLAC_CONTAINING_LOSSY_AUDIO" not in flags,
        checksum_verified=checksum_ok,
        audit_flags=flags,
        tags=raw_tags,
    )
