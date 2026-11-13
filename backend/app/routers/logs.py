from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models import SystemLog

router = APIRouter(prefix="/api/v1/logs", tags=["Logs"])


@router.get("")
def list_logs(
    level: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=150, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    q = db.query(SystemLog)
    if level:
        q = q.filter(SystemLog.level == level.upper())
    if category:
        q = q.filter(SystemLog.category == category.upper())

    rows = q.order_by(SystemLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "level": r.level,
            "category": r.category,
            "message": r.message,
            "details": r.details,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.delete("")
def clear_logs(db: Session = Depends(get_db)) -> Dict[str, str]:
    db.query(SystemLog).delete()
    db.commit()
    return {"status": "cleared"}
