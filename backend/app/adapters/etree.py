from typing import Any, Dict, Optional
from backend.app.adapters.base import NormalizedRelease
from backend.app.adapters.internet_archive import InternetArchiveAdapter


class EtreeAdapter(InternetArchiveAdapter):
    """Specialized Live Music Archive (etree) adapter built on InternetArchiveAdapter."""

    source_id = "etree"
    source_name = "etree / Live Music Archive"
    website = "https://archive.org/details/etree"
    priority = "High"
    supports_albums = True
    supports_tracks = True
    supports_direct_lossless = True
    requires_api_key = False
    description = "Live Music Archive (etree) lossless concert recordings (16-bit & 24-bit FLAC)."
    limitations = "Trade-friendly live recordings only; non-commercial trading terms apply per artist."

    def _build_lucene_query(self, artist: str, album: str, track: str) -> str:
        clauses = ["collection:(etree)", "mediatype:(audio)"]
        if artist:
            safe_artist = artist.replace('"', "")
            clauses.append(f'(creator:("{safe_artist}") OR title:("{safe_artist}"))')
        if album:
            safe_album = album.replace('"', "")
            clauses.append(f'(title:("{safe_album}") OR venue:("{safe_album}") OR date:("{safe_album}"))')
        if track and not album:
            safe_track = track.replace('"', "")
            clauses.append(f'("{safe_track}")')
        return " AND ".join(clauses)

    def _parse_item_metadata(
        self,
        identifier: str,
        doc: Dict[str, Any],
        meta: Dict[str, Any],
        requested_track: str = "",
    ) -> Optional[NormalizedRelease]:
        release = super()._parse_item_metadata(identifier, doc, meta, requested_track=requested_track)
        if not release:
            return None
        metadata = meta.get("metadata", {}) or {}
        venue = metadata.get("venue") or ""
        coverage = metadata.get("coverage") or ""
        concert_date = metadata.get("date") or ""
        rights_notice = (
            metadata.get("rights")
            or metadata.get("Possible Copyright Status")
            or "Live Music Archive — Non-Commercial Trading Permitted by Artist"
        )
        if isinstance(rights_notice, list):
            rights_notice = "; ".join(str(r) for r in rights_notice)
        release.license = str(rights_notice)
        release.extra_metadata.update(
            {
                "is_live_concert": True,
                "concert_date": concert_date,
                "venue": venue,
                "location": coverage,
                "lineage": metadata.get("source") or metadata.get("lineage") or "",
                "transferer": metadata.get("transferer") or "",
                "trading_notes": metadata.get("notes") or "Check artist policy on Archive.org etree.",
            }
        )
        return release
