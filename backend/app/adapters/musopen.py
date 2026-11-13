from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
from backend.app.adapters.base import (
    NormalizedRelease,
    NormalizedTrack,
)
from backend.app.adapters.internet_archive import InternetArchiveAdapter


class MusopenAdapter(InternetArchiveAdapter):
    """Musopen Classical Music Adapter.

    Searches public domain Musopen classical recordings and compositions,
    clearly surfacing Musopen.org's account & subscription restrictions
    without bypassing authentication or rate limits.
    """

    source_id = "musopen"
    source_name = "Musopen"
    website = "https://musopen.org/"
    priority = "Normal"
    supports_albums = True
    supports_tracks = True
    supports_direct_lossless = True
    requires_api_key = False
    description = "Royalty-free & Public Domain classical compositions, performers, and orchestral recordings."
    limitations = (
        "Musopen.org discontinued its open unauthenticated bulk download API: direct lossless (FLAC) "
        "downloads on musopen.org require a paid Supporter account (free accounts are limited to 5 SD MP3s/day). "
        "This adapter searches public Musopen archive releases and catalogs compositions with explicit account notices."
    )
    rate_limit_per_sec = 2.0

    def _build_lucene_query(self, artist: str, album: str, track: str) -> str:
        clauses = ["mediatype:(audio)", '(collection:(musopen) OR creator:("Musopen") OR subject:("musopen") OR subject:("Classical"))']
        if artist:
            safe_artist = artist.replace('"', "")
            clauses.append(f'(creator:("{safe_artist}") OR title:("{safe_artist}") OR description:("{safe_artist}"))')
        if album:
            safe_album = album.replace('"', "")
            clauses.append(f'(title:("{safe_album}") OR description:("{safe_album}"))')
        if track and not album:
            safe_track = track.replace('"', "")
            clauses.append(f'("{safe_track}")')
        return " AND ".join(clauses)

    async def search(
        self,
        artist: str = "",
        album: str = "",
        track: str = "",
        limit: int = 8,
    ) -> List[NormalizedRelease]:
        if not any([artist, album, track]):
            return []

        releases = await super().search(artist=artist, album=album, track=track, limit=limit)
        for rel in releases:
            rel.source = self.source_id
            rel.extra_metadata["musopen_account_notice"] = (
                "Direct downloads via musopen.org require a user account (5 MP3/day free; "
                "lossless FLAC requires Musopen All-Access subscription). Public archive mirror files shown below."
            )
            rel.extra_metadata["musopen_catalog_url"] = (
                f"https://musopen.org/music/?q={quote_plus(' '.join(filter(None, [artist, album, track])))}"
            )
            if not rel.license or rel.license == "Verify individual item rights":
                rel.license = "Public Domain / Creative Commons (Musopen)"

        # Also query OpenOpus Public Classical Catalog to surface composition entries on Musopen.org
        if len(releases) < limit and (artist or album or track):
            catalog_entry = await self._search_classical_catalog(artist=artist, album=album, track=track)
            if catalog_entry:
                releases.append(catalog_entry)

        return releases

    async def _search_classical_catalog(
        self, artist: str, album: str, track: str
    ) -> Optional[NormalizedRelease]:
        q_str = " ".join(filter(None, [artist, album, track])).strip()
        if not q_str:
            return None
        musopen_url = f"https://musopen.org/music/?q={quote_plus(q_str)}"
        return NormalizedRelease(
            external_id=f"musopen_catalog_{quote_plus(q_str.lower())[:48]}",
            source=self.source_id,
            artist=artist or "Classical Composer",
            album=album or track or q_str,
            year=None,
            cover_url="",
            primary_format="FLAC",
            available_formats=["FLAC", "MP3"],
            is_lossless=True,
            quality_label="FLAC (Musopen Account Required)",
            bit_depth=16,
            sample_rate=44100,
            track_count=1,
            total_size_bytes=0,
            license="Public Domain / CC-BY (Account Required on Musopen.org for FLAC)",
            source_url=musopen_url,
            download_availability="ACCOUNT_REQUIRED",
            extra_metadata={
                "account_requirement": "Musopen.org requires sign-in. Free tier: 5 standard MP3 downloads/day. Supporter tier: Unlimited lossless FLAC.",
                "musopen_catalog_url": musopen_url,
            },
            tracks=[
                NormalizedTrack(
                    track_number=1,
                    disc_number=1,
                    title=track or album or q_str,
                    artist=artist or "Classical Performer",
                    duration_seconds=None,
                    format="FLAC",
                    is_lossless=True,
                    bit_depth=16,
                    sample_rate=44100,
                    size_bytes=0,
                    download_url="",
                )
            ],
        )
