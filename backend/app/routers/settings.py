from typing import Any, Dict
from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.services.logger_service import log_event
from backend.app.services.settings_service import (
    get_effective_settings,
    update_settings,
)

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


@router.get("")
def get_settings_endpoint(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return get_effective_settings(db, mask_secrets=True)


@router.put("")
def update_settings_endpoint(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    updated = update_settings(db, payload)
    log_event("INFO", "SYSTEM", "Updated application settings.", {"keys": list(payload.keys())}, db=db)
    return updated
