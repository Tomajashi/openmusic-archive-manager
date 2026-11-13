from pathlib import Path
import re
import shutil
from typing import Optional, Tuple

INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_component(value: str, fallback: str = "Unknown") -> str:
    if not value:
        return fallback
    cleaned = INVALID_PATH_CHARS.sub("_", str(value)).strip()
    cleaned = cleaned.strip(". ")
    if cleaned in {"", ".", ".."}:
        return fallback
    return cleaned[:180]


def build_organized_track_path(
    music_root: Path,
    artist: str,
    album: str,
    title: str,
    track_number: int = 1,
    disc_number: int = 1,
    year: Optional[int] = None,
    extension: str = "flac",
    naming_pattern: str = "{artist}/{album_year}/{track_num} - {title}.{ext}",
) -> Tuple[Path, Path]:
    """Return (final_track_path, cover_art_path) strictly confined inside music_root."""
    root_resolved = music_root.resolve()
    safe_artist = sanitize_component(artist, "Unknown Artist")
    safe_album = sanitize_component(album, "Unknown Album")
    safe_title = sanitize_component(title, f"Track {track_number:02d}")
    safe_ext = sanitize_component(extension.lstrip(".").lower(), "flac")

    album_year = f"{safe_album} ({year})" if year else safe_album
    track_num_str = f"{disc_number}-{track_number:02d}" if disc_number and disc_number > 1 else f"{track_number:02d}"

    try:
        rel_str = naming_pattern.format(
            artist=safe_artist,
            album=safe_album,
            album_year=album_year,
            year=year or "",
            track_num=track_num_str,
            title=safe_title,
            ext=safe_ext,
        )
    except Exception:
        rel_str = f"{safe_artist}/{album_year}/{track_num_str} - {safe_title}.{safe_ext}"

    # Sanitize every path segment individually to prevent path traversal
    parts = [sanitize_component(p, "_") for p in Path(rel_str).parts if p not in {"/", "\\", ".", ".."}]
    target_path = (root_resolved / Path(*parts)).resolve()

    if not str(target_path).startswith(str(root_resolved)):
        raise ValueError("Path traversal detected while organizing music file.")

    cover_path = target_path.parent / "cover.jpg"
    return target_path, cover_path


def move_to_library(
    temp_file: Path,
    target_path: Path,
    overwrite: bool = False,
) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"Destination file already exists and overwrite is disabled: {target_path}")

    shutil.copy2(str(temp_file), str(target_path))
    try:
        temp_file.unlink(missing_ok=True)
    except Exception:
        pass
    return target_path
