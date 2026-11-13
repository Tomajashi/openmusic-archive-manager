import hashlib
import secrets
from typing import Any, Dict
import httpx
from sqlalchemy.orm import Session
from backend.app.services.logger_service import log_event
from backend.app.services.settings_service import get_effective_settings


class NavidromeService:
    def _build_subsonic_params(self, username: str, password: str) -> Dict[str, str]:
        salt = secrets.token_hex(6)
        token = hashlib.md5(f"{password}{salt}".encode("utf-8")).hexdigest()
        return {
            "u": username,
            "t": token,
            "s": salt,
            "v": "1.16.1",
            "c": "OpenMusicArchiveManager",
            "f": "json",
        }

    async def trigger_rescan(self, db: Session) -> Dict[str, Any]:
        eff = get_effective_settings(db, mask_secrets=False)
        if not eff.get("navidrome_enabled"):
            return {
                "status": "disabled",
                "message": "Navidrome integration is disabled in Settings (standalone library mode active).",
            }

        base_url = str(eff.get("navidrome_url") or "").rstrip("/")
        username = str(eff.get("navidrome_user") or "")
        password = str(eff.get("navidrome_password") or "")

        if not base_url or not username or not password:
            return {
                "status": "unconfigured",
                "message": "Navidrome URL, username, or password is not configured.",
            }

        params = self._build_subsonic_params(username, password)
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(f"{base_url}/rest/startScan.view", params=params)
                resp.raise_for_status()
                payload = resp.json().get("subsonic-response", {})
                status = payload.get("status", "failed")
                scan_status = payload.get("scanStatus", {})
                if status == "ok":
                    log_event(
                        "INFO",
                        "NAVIDROME",
                        "Triggered Navidrome library rescan successfully.",
                        {"scanStatus": scan_status},
                        db=db,
                    )
                    return {"status": "ok", "scanStatus": scan_status}
                err_msg = payload.get("error", {}).get("message", "Unknown Subsonic API error")
                log_event("WARNING", "NAVIDROME", f"Navidrome scan error: {err_msg}", db=db)
                return {"status": "error", "message": err_msg}
        except Exception as exc:
            log_event("ERROR", "NAVIDROME", f"Failed to reach Navidrome server: {exc}", db=db)
            return {"status": "error", "message": str(exc)}

    async def check_status(self, db: Session) -> Dict[str, Any]:
        eff = get_effective_settings(db, mask_secrets=False)
        base_url = str(eff.get("navidrome_url") or "").rstrip("/")
        username = str(eff.get("navidrome_user") or "")
        password = str(eff.get("navidrome_password") or "")

        if not eff.get("navidrome_enabled") or not base_url:
            return {
                "enabled": bool(eff.get("navidrome_enabled")),
                "connected": False,
                "music_path": eff.get("navidrome_music_path", "/music"),
                "message": "Standalone mode (Navidrome remote API not active).",
            }

        params = self._build_subsonic_params(username, password)
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(f"{base_url}/rest/getScanStatus.view", params=params)
                resp.raise_for_status()
                payload = resp.json().get("subsonic-response", {})
                return {
                    "enabled": True,
                    "connected": payload.get("status") == "ok",
                    "scanStatus": payload.get("scanStatus", {}),
                    "music_path": eff.get("navidrome_music_path", "/music"),
                }
        except Exception as exc:
            return {
                "enabled": True,
                "connected": False,
                "music_path": eff.get("navidrome_music_path", "/music"),
                "message": str(exc),
            }


navidrome_service = NavidromeService()
