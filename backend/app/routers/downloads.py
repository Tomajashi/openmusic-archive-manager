from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models import DownloadJob
from backend.app.schemas import DownloadJobOut, DownloadSelectionRequest
from backend.app.services.download_manager import download_manager

router = APIRouter(prefix="/api/v1/downloads", tags=["Downloads"])


@router.post("/queue", response_model=List[DownloadJobOut])
def queue_selected_downloads(
    payload: DownloadSelectionRequest,
    db: Session = Depends(get_db),
) -> List[DownloadJob]:
    if not payload.approved_by_user:
        raise HTTPException(
            status_code=400,
            detail="Downloads cannot start without explicit user approval (approved_by_user=true).",
        )
    if not payload.result_ids and not payload.track_ids:
        raise HTTPException(status_code=400, detail="Select at least one album release or track to download.")

    try:
        jobs = download_manager.queue_downloads(
            db=db,
            result_ids=payload.result_ids,
            track_ids=payload.track_ids,
            approved_by_user=payload.approved_by_user,
            overwrite_existing=payload.overwrite_existing,
        )
        return jobs
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=List[DownloadJobOut])
def list_downloads(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[DownloadJob]:
    q = db.query(DownloadJob)
    if status:
        q = q.filter(DownloadJob.status == status.upper())
    return q.order_by(DownloadJob.created_at.desc()).limit(limit).all()


@router.post("/{job_id}/pause", response_model=DownloadJobOut)
def pause_download(job_id: int, db: Session = Depends(get_db)) -> DownloadJob:
    job = download_manager.pause_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found.")
    return job


@router.post("/{job_id}/resume", response_model=DownloadJobOut)
def resume_download(job_id: int, db: Session = Depends(get_db)) -> DownloadJob:
    job = download_manager.resume_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found.")
    return job


@router.post("/{job_id}/retry", response_model=DownloadJobOut)
def retry_download(job_id: int, db: Session = Depends(get_db)) -> DownloadJob:
    job = download_manager.resume_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found.")
    return job


@router.post("/{job_id}/cancel", response_model=DownloadJobOut)
def cancel_download(job_id: int, db: Session = Depends(get_db)) -> DownloadJob:
    job = download_manager.cancel_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found.")
    return job


@router.delete("/{job_id}")
def delete_download_record(job_id: int, db: Session = Depends(get_db)) -> Dict[str, str]:
    job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found.")
    download_manager.cancel_job(db, job_id)
    db.delete(job)
    db.commit()
    return {"status": "deleted"}
