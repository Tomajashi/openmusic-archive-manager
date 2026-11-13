from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models import (
    DownloadJob,
    ImportItem,
    LibraryItem,
    SearchResult,
)
from backend.app.schemas import DashboardStats
from backend.app.services.settings_service import get_enabled_sources

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)) -> DashboardStats:
    total_artists = db.query(func.count(func.distinct(ImportItem.artist))).scalar() or 0
    albums_found = db.query(func.count(SearchResult.id)).scalar() or 0
    albums_available = (
        db.query(func.count(SearchResult.id))
        .filter(SearchResult.download_availability.in_(["DIRECT", "MAGNET"]))
        .scalar()
        or 0
    )
    completed_dl = (
        db.query(func.count(DownloadJob.id)).filter(DownloadJob.status == "COMPLETED").scalar() or 0
    )
    failed_dl = (
        db.query(func.count(DownloadJob.id)).filter(DownloadJob.status == "FAILED").scalar() or 0
    )
    active_dl = (
        db.query(func.count(DownloadJob.id))
        .filter(DownloadJob.status.in_(["QUEUED", "DOWNLOADING", "VERIFYING", "ORGANIZING"]))
        .scalar()
        or 0
    )
    total_storage = db.query(func.coalesce(func.sum(LibraryItem.size_bytes), 0)).scalar() or 0
    enabled_sources = len(get_enabled_sources(db))

    total_lib = db.query(func.count(LibraryItem.id)).scalar() or 0
    lossless_lib = (
        db.query(func.count(LibraryItem.id)).filter(LibraryItem.is_verified_lossless.is_(True)).scalar() or 0
    )

    all_lib_flags = db.query(LibraryItem.audit_flags).all()
    flagged_count = sum(1 for (fl,) in all_lib_flags if fl and len(fl) > 0)

    return DashboardStats(
        total_artists_requested=total_artists,
        albums_found=albums_found,
        albums_available_for_download=albums_available,
        completed_downloads=completed_dl,
        failed_downloads=failed_dl,
        active_downloads=active_dl,
        total_downloaded_storage_bytes=int(total_storage),
        enabled_sources_count=enabled_sources,
        total_library_tracks=total_lib,
        verified_lossless_tracks=lossless_lib,
        flagged_tracks=flagged_count,
    )
