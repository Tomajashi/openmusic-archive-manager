from typing import Any, Dict, List
from sqlalchemy.orm import Session
from backend.app.config import settings
from backend.app.models import AppSetting

SECRET_KEYS = {
    "jamendo_client_id",
    "musopen_api_key",
    "torznab_api_key",
    "qbittorrent_password",
    "navidrome_password",
    "flacmusicfinder_cookie",
}

DEFAULT_ENABLED_SOURCES = [
    "internet_archive",
    "etree",
    "wikimedia",
    "jamendo",
    "musopen",
    "piratebay",
]


def get_default_settings_dict() -> Dict[str, Any]:
    return {
        "enabled_sources": list(DEFAULT_ENABLED_SOURCES),
        "search_concurrency": settings.search_concurrency,
        "download_concurrency": settings.download_concurrency,
        "download_dir": settings.download_dir,
        "music_dir": settings.music_dir,
        "preferred_formats": list(settings.preferred_formats),
        "min_audio_quality": settings.min_audio_quality,
        "max_storage_gb": settings.max_storage_gb,
        "auto_duplicate_detection": settings.auto_duplicate_detection,
        "naming_pattern": settings.naming_pattern,
        "musicbrainz_enabled": settings.musicbrainz_enabled,
        "embed_metadata": True,
        "download_cover_art": True,
        "jamendo_client_id": settings.jamendo_client_id,
        "musopen_api_key": settings.musopen_api_key,
        "piratebay_enabled": settings.piratebay_enabled,
        "piratebay_api_url": settings.piratebay_api_url,
        "torznab_url": settings.torznab_url,
        "torznab_api_key": settings.torznab_api_key,
        "qbittorrent_url": settings.qbittorrent_url,
        "qbittorrent_username": settings.qbittorrent_username,
        "qbittorrent_password": settings.qbittorrent_password,
        "transmission_url": settings.transmission_url,
        "flacmusicfinder_enabled": settings.flacmusicfinder_enabled,
        "flacmusicfinder_base_url": settings.flacmusicfinder_base_url,
        "flacmusicfinder_cookie": settings.flacmusicfinder_cookie,
        "flacmusicfinder_search_path": settings.flacmusicfinder_search_path,
        "flacmusicfinder_user_agent": settings.flacmusicfinder_user_agent,
        "flacmusicfinder_max_details": settings.flacmusicfinder_max_details,
        "flacmusicfinder_extra_download_hosts": settings.flacmusicfinder_extra_download_hosts,
        "navidrome_enabled": settings.navidrome_enabled,
        "navidrome_url": settings.navidrome_url,
        "navidrome_user": settings.navidrome_user,
        "navidrome_password": settings.navidrome_password,
        "navidrome_music_path": settings.navidrome_music_path,
        "navidrome_auto_rescan": settings.navidrome_auto_rescan,
        "log_level": settings.log_level,
    }


def get_effective_settings(db: Session, mask_secrets: bool = False) -> Dict[str, Any]:
    effective = get_default_settings_dict()
    rows = db.query(AppSetting).all()
    for row in rows:
        effective[row.key] = row.value

    if mask_secrets:
        masked = dict(effective)
        for sec_key in SECRET_KEYS:
            val = str(masked.get(sec_key) or "")
            masked[f"{sec_key}_configured"] = bool(val)
            masked[sec_key] = "********" if val else ""
        return masked

    return effective


def update_settings(db: Session, updates: Dict[str, Any]) -> Dict[str, Any]:
    defaults = get_default_settings_dict()
    for key, value in updates.items():
        if key not in defaults:
            continue
        if key in SECRET_KEYS and value == "********":
            # Do not overwrite stored secret with mask placeholder
            continue
        existing = db.query(AppSetting).filter(AppSetting.key == key).first()
        if existing:
            existing.value = value
        else:
            db.add(AppSetting(key=key, value=value))
        # Also sync runtime settings object if attribute exists
        if hasattr(settings, key):
            setattr(settings, key, value)

    db.commit()
    settings.ensure_directories()
    return get_effective_settings(db, mask_secrets=True)


def get_enabled_sources(db: Session) -> List[str]:
    eff = get_effective_settings(db, mask_secrets=False)
    sources = eff.get("enabled_sources", DEFAULT_ENABLED_SOURCES)
    if not eff.get("piratebay_enabled", True) and "piratebay" in sources:
        sources = [s for s in sources if s != "piratebay"]
    # FLAC Music Finder is opt-in: it is only searched when explicitly switched on.
    if eff.get("flacmusicfinder_enabled", False) and "flacmusicfinder" not in sources:
        sources = list(sources) + ["flacmusicfinder"]
    elif not eff.get("flacmusicfinder_enabled", False):
        sources = [s for s in sources if s != "flacmusicfinder"]
    return list(sources)
