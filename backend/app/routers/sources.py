from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.adapters.registry import adapter_registry
from backend.app.database import get_db
from backend.app.schemas import SourceInfoOut
from backend.app.services.settings_service import (
    get_effective_settings,
    get_enabled_sources,
    update_settings,
)

router = APIRouter(prefix="/api/v1/sources", tags=["Sources"])


@router.get("", response_model=List[SourceInfoOut])
def list_sources(db: Session = Depends(get_db)) -> List[SourceInfoOut]:
    enabled = set(get_enabled_sources(db))
    eff = get_effective_settings(db, mask_secrets=False)
    out: List[SourceInfoOut] = []

    for adapter in adapter_registry.all():
        key_configured = True
        if adapter.source_id == "jamendo":
            key_configured = bool(eff.get("jamendo_client_id"))
        elif adapter.source_id == "musopen":
            key_configured = True

        out.append(
            SourceInfoOut(
                id=adapter.source_id,
                name=adapter.source_name,
                website=adapter.website,
                priority=adapter.priority,
                enabled=adapter.source_id in enabled,
                supports_albums=adapter.supports_albums,
                supports_tracks=adapter.supports_tracks,
                supports_direct_lossless=adapter.supports_direct_lossless,
                requires_api_key=adapter.requires_api_key,
                api_key_configured=key_configured,
                description=adapter.description,
                limitations=adapter.limitations,
                rate_limit_per_sec=adapter.rate_limit_per_sec,
            )
        )
    return out


@router.post("/{source_id}/toggle")
def toggle_source(source_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    adapter = adapter_registry.get(source_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Unknown source '{source_id}'.")

    enabled = get_enabled_sources(db)
    if source_id in enabled:
        new_enabled = [s for s in enabled if s != source_id]
        state = False
    else:
        new_enabled = enabled + [source_id]
        state = True

    updates: Dict[str, Any] = {"enabled_sources": new_enabled}
    if source_id == "piratebay":
        updates["piratebay_enabled"] = state
    update_settings(db, updates)
    return {"id": source_id, "enabled": state, "enabled_sources": new_enabled}
