from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models import SearchJob, SearchResult
from backend.app.schemas import SearchJobOut, SearchQueryInput, SearchResultOut
from backend.app.services.search_engine import search_engine

router = APIRouter(prefix="/api/v1/search", tags=["Search"])


@router.post("/start", response_model=SearchJobOut)
async def start_search(
    payload: SearchQueryInput,
    wait: bool = Query(default=False, description="Wait for search completion before returning"),
    db: Session = Depends(get_db),
) -> SearchJob:
    if payload.project_id is None and not any([payload.artist.strip(), payload.album.strip(), payload.track.strip()]):
        raise HTTPException(status_code=400, detail="Provide at least an artist, album, track, or project_id.")

    job = await search_engine.start_async_search_job(
        db=db,
        artist=payload.artist,
        album=payload.album,
        track=payload.track,
        project_id=payload.project_id,
        sources=payload.sources,
        lossless_only=payload.lossless_only,
        wait_for_completion=wait,
    )
    return job


@router.get("/jobs", response_model=List[SearchJobOut])
def list_search_jobs(
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> List[SearchJob]:
    return db.query(SearchJob).order_by(SearchJob.created_at.desc()).limit(limit).all()


@router.get("/jobs/{job_id}", response_model=SearchJobOut)
def get_search_job(job_id: int, db: Session = Depends(get_db)) -> SearchJob:
    job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Search job not found.")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=SearchJobOut)
def cancel_search_job(job_id: int, db: Session = Depends(get_db)) -> SearchJob:
    job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Search job not found.")
    job.status = "CANCELLED"
    db.commit()
    db.refresh(job)
    return job


@router.get("/results")
def list_search_results(
    job_id: Optional[int] = Query(default=None),
    source: Optional[str] = Query(default=None),
    artist: Optional[str] = Query(default=None),
    album: Optional[str] = Query(default=None),
    lossless_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    q = db.query(SearchResult)
    if job_id is not None:
        q = q.filter(SearchResult.search_job_id == job_id)
    if source:
        q = q.filter(SearchResult.source == source)
    if artist:
        q = q.filter(SearchResult.artist.ilike(f"%{artist}%"))
    if album:
        q = q.filter(SearchResult.album.ilike(f"%{album}%"))
    if lossless_only:
        q = q.filter(SearchResult.is_lossless.is_(True))

    total = q.count()
    offset = (page - 1) * limit
    items = (
        q.order_by(
            SearchResult.is_lossless.desc(),
            SearchResult.match_score.desc(),
            SearchResult.created_at.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    serialized = [SearchResultOut.model_validate(it).model_dump() for it in items]

    # Identify duplicate groups across different sources
    dup_counts: Dict[str, int] = {}
    for s in serialized:
        dk = s.get("duplicate_group_key") or ""
        if dk:
            dup_counts[dk] = dup_counts.get(dk, 0) + 1

    for s in serialized:
        dk = s.get("duplicate_group_key") or ""
        s["duplicate_count"] = dup_counts.get(dk, 1)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit),
        "items": serialized,
    }


@router.get("/results/{result_id}", response_model=SearchResultOut)
def get_search_result(result_id: int, db: Session = Depends(get_db)) -> SearchResult:
    res = db.query(SearchResult).filter(SearchResult.id == result_id).first()
    if not res:
        raise HTTPException(status_code=404, detail="Search result not found.")
    return res
