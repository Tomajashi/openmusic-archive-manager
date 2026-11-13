from typing import Any, Dict, List
from backend.app.adapters.base import (
    BaseSourceAdapter,
    NormalizedRelease,
    NormalizedTrack,
    extract_year,
    parse_duration,
)
from backend.app.config import settings


class JamendoAdapter(BaseSourceAdapter):
    source_id = "jamendo"
    source_name = "Jamendo Music"
    website = "https://www.jamendo.com/"
    priority = "High"
    supports_albums = True
    supports_tracks = True
    supports_direct_lossless = True
    requires_api_key = True
    description = "Official Jamendo REST API v3.0 for independent Creative Commons artists and albums."
    limitations = (
        "Requires JAMENDO_CLIENT_ID. Jamendo v3.0 only provides FLAC when the artist has uploaded lossless "
        "masters and enabled downloads (audiodlallowed=true); otherwise defaults to MP3 (192kbps) or stream-only."
    )
    rate_limit_per_sec = 2.0

    base_url = "https://api.jamendo.com/v3.0"

    def get_client_id(self, runtime_client_id: str = "") -> str:
        return (runtime_client_id or settings.jamendo_client_id or "").strip()

    async def search(
        self,
        artist: str = "",
        album: str = "",
        track: str = "",
        limit: int = 8,
        client_id: str = "",
    ) -> List[NormalizedRelease]:
        cid = self.get_client_id(client_id)
        if not cid:
            return []

        releases: List[NormalizedRelease] = []

        # 1. Search complete albums with embedded tracklists via /albums/tracks
        if artist or album:
            album_params: Dict[str, Any] = {
                "client_id": cid,
                "format": "json",
                "limit": min(limit, 10),
                "audioformat": "flac",
            }
            if artist:
                album_params["artist_name"] = artist
            if album:
                album_params["namesearch"] = album

            try:
                album_data = await self._get_json(f"{self.base_url}/albums/tracks/", params=album_params)
                for alb in album_data.get("results", []) or []:
                    parsed = self._parse_album_result(alb)
                    if parsed:
                        releases.append(parsed)
            except Exception:
                pass

        # 2. If track-specific search or no albums returned, search /tracks
        if track or not releases:
            track_params: Dict[str, Any] = {
                "client_id": cid,
                "format": "json",
                "limit": min(limit, 15),
                "audioformat": "flac",
                "include": "licenses+musicinfo",
            }
            if artist:
                track_params["artist_name"] = artist
            if album:
                track_params["album_name"] = album
            if track:
                track_params["namesearch"] = track
            elif not artist and not album:
                return releases

            try:
                track_data = await self._get_json(f"{self.base_url}/tracks/", params=track_params)
                for trk in track_data.get("results", []) or []:
                    parsed_trk = self._parse_single_track_as_release(trk)
                    if parsed_trk:
                        releases.append(parsed_trk)
            except Exception:
                pass

        return releases

    def _parse_album_result(self, alb: Dict[str, Any]) -> NormalizedRelease | None:
        alb_id = str(alb.get("id", ""))
        tracks_raw = alb.get("tracks") or []
        if not alb_id or not tracks_raw:
            return None

        artist_name = str(alb.get("artist_name") or "Unknown Artist")
        album_name = str(alb.get("name") or "Unknown Album")
        year = extract_year(alb.get("releasedate"))
        cover_url = str(alb.get("image") or "")

        tracks: List[NormalizedTrack] = []
        any_dl_allowed = False
        any_flac = False
        formats_set = set()

        for idx, t in enumerate(tracks_raw, start=1):
            dl_allowed = bool(t.get("audiodlallowed", False))
            dl_url = str(t.get("audiodownload") or "") if dl_allowed else ""
            # Verify whether Jamendo actually returned a FLAC download URL
            is_flac = "flac" in dl_url.lower() and dl_allowed
            fmt = "FLAC" if is_flac else "MP3"
            formats_set.add(fmt)
            if dl_allowed:
                any_dl_allowed = True
            if is_flac:
                any_flac = True

            duration = parse_duration(t.get("duration"))
            pos = int(t.get("position") or idx)
            est_size = (duration or 180) * (110000 if is_flac else 24000)

            tracks.append(
                NormalizedTrack(
                    track_number=pos,
                    disc_number=1,
                    title=str(t.get("name") or f"Track {pos}"),
                    artist=artist_name,
                    duration_seconds=duration,
                    format=fmt,
                    is_lossless=is_flac,
                    bit_depth=16 if is_flac else None,
                    sample_rate=44100,
                    size_bytes=est_size,
                    download_url=dl_url,
                )
            )

        primary_fmt = "FLAC" if any_flac else "MP3"
        total_size = sum(t.size_bytes for t in tracks)
        license_cc = str(tracks_raw[0].get("license_ccurl") or "Creative Commons (Jamendo)")

        return NormalizedRelease(
            external_id=f"jamendo_album_{alb_id}",
            source=self.source_id,
            artist=artist_name,
            album=album_name,
            year=year,
            cover_url=cover_url,
            primary_format=primary_fmt,
            available_formats=sorted(formats_set),
            is_lossless=any_flac,
            quality_label="16-bit / 44.1 kHz (FLAC)" if any_flac else "MP3 ~192 kbps (Jamendo API)",
            bit_depth=16 if any_flac else None,
            sample_rate=44100,
            track_count=len(tracks),
            total_size_bytes=total_size,
            license=license_cc,
            source_url=str(alb.get("shareurl") or f"https://www.jamendo.com/album/{alb_id}"),
            download_availability="DIRECT" if any_dl_allowed else "STREAM_ONLY",
            extra_metadata={"jamendo_album_id": alb_id, "audiodlallowed": any_dl_allowed},
            tracks=tracks,
        )

    def _parse_single_track_as_release(self, trk: Dict[str, Any]) -> NormalizedRelease | None:
        trk_id = str(trk.get("id", ""))
        if not trk_id:
            return None
        dl_allowed = bool(trk.get("audiodlallowed", False))
        dl_url = str(trk.get("audiodownload") or "") if dl_allowed else ""
        is_flac = "flac" in dl_url.lower() and dl_allowed
        fmt = "FLAC" if is_flac else "MP3"
        duration = parse_duration(trk.get("duration"))
        est_size = (duration or 180) * (110000 if is_flac else 24000)
        artist_name = str(trk.get("artist_name") or "Unknown Artist")
        album_name = str(trk.get("album_name") or trk.get("name") or "Single")

        t_obj = NormalizedTrack(
            track_number=int(trk.get("position") or 1),
            disc_number=1,
            title=str(trk.get("name") or "Track"),
            artist=artist_name,
            duration_seconds=duration,
            format=fmt,
            is_lossless=is_flac,
            bit_depth=16 if is_flac else None,
            sample_rate=44100,
            size_bytes=est_size,
            download_url=dl_url,
        )

        return NormalizedRelease(
            external_id=f"jamendo_track_{trk_id}",
            source=self.source_id,
            artist=artist_name,
            album=album_name,
            year=extract_year(trk.get("releasedate")),
            cover_url=str(trk.get("album_image") or trk.get("image") or ""),
            primary_format=fmt,
            available_formats=[fmt],
            is_lossless=is_flac,
            quality_label="16-bit / 44.1 kHz (FLAC)" if is_flac else "MP3 ~192 kbps (Jamendo API)",
            bit_depth=16 if is_flac else None,
            sample_rate=44100,
            track_count=1,
            total_size_bytes=est_size,
            license=str(trk.get("license_ccurl") or "Creative Commons (Jamendo)"),
            source_url=str(trk.get("shareurl") or f"https://www.jamendo.com/track/{trk_id}"),
            download_availability="DIRECT" if dl_allowed else "STREAM_ONLY",
            extra_metadata={"jamendo_track_id": trk_id, "audiodlallowed": dl_allowed},
            tracks=[t_obj],
        )
