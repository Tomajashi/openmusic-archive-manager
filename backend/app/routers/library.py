from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models import LibraryItem
from backend.app.schemas import LibraryItemOut
from backend.app.services.audio_verifier import inspect_audio_with_ffprobe
from backend.app.services.navidrome_service import navidrome_service
from backend.app.services.settings_service import get_effective_settings

router = APIRouter(prefix="/api/v1/library", tags=["Library"])

AUDIO_EXTS = {".flac", ".wav", ".alac", ".aiff", ".mp3", ".ogg", ".opus", ".m4a"}


@router.get("", response_model=List[LibraryItemOut])
def list_library_items(
    artist: Optional[str] = Query(default=None),
    album: Optional[str] = Query(default=None),
    lossless_only: bool = Query(default=False),
    flagged_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> List[LibraryItem]:
    q = db.query(LibraryItem)
    if artist:
        q = q.filter(LibraryItem.artist.ilike(f"%{artist}%"))
    if album:
        q = q.filter(LibraryItem.album.ilike(f"%{album}%"))
    if lossless_only:
        q = q.filter(LibraryItem.is_verified_lossless.is_(True))

    items = q.order_by(LibraryItem.artist.asc(), LibraryItem.album.asc(), LibraryItem.track_number.asc()).all()
    if flagged_only:
        items = [it for it in items if it.audit_flags and len(it.audit_flags) > 0]
    return items


@router.post("/scan-disk")
def scan_music_directory(db: Session = Depends(get_db)) -> Dict[str, Any]:
    eff = get_effective_settings(db, mask_secrets=False)
    music_root = Path(str(eff.get("music_dir") or "./music"))
    if not music_root.exists():
        return {"scanned": 0, "added": 0}

    scanned = 0
    added = 0
    for fpath in music_root.rglob("*"):
        if not fpath.is_file() or fpath.suffix.lower() not in AUDIO_EXTS:
            continue
        scanned += 1
        existing = db.query(LibraryItem).filter(LibraryItem.file_path == str(fpath)).first()
        if existing:
            continue

        report = inspect_audio_with_ffprobe(fpath)
        rel_parts = fpath.relative_to(music_root).parts
        artist = report.tags.get("artist") or (rel_parts[0] if len(rel_parts) >= 2 else "Unknown Artist")
        album = report.tags.get("album") or (rel_parts[1] if len(rel_parts) >= 3 else "Unknown Album")
        title = report.tags.get("title") or fpath.stem

        cover_candidate = fpath.parent / "cover.jpg"
        db.add(
            LibraryItem(
                artist=artist,
                album=album,
                title=title,
                track_number=1,
                disc_number=1,
                format=fpath.suffix.lstrip(".").upper(),
                codec=report.codec_name,
                bit_depth=report.bit_depth,
                sample_rate=report.sample_rate,
                duration_seconds=report.duration_seconds,
                size_bytes=fpath.stat().st_size,
                file_path=str(fpath),
                cover_path=str(cover_candidate) if cover_candidate.exists() else "",
                source="local_disk",
                license="Local Library",
                is_verified_lossless=report.is_verified_lossless,
                audit_flags=report.audit_flags,
            )
        )
        added += 1

    db.commit()
    return {"scanned": scanned, "added": added}


@router.get("/navidrome/status")
async def get_navidrome_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return await navidrome_service.check_status(db)


@router.post("/navidrome/rescan")
async def trigger_navidrome_rescan(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return await navidrome_service.trigger_rescan(db)
