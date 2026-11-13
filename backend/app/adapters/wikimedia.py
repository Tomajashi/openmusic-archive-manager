import re
from typing import Any, Dict, List
from backend.app.adapters.base import (
    BaseSourceAdapter,
    NormalizedRelease,
    NormalizedTrack,
    extract_year,
    is_lossless_format,
    normalize_format_name,
)


def _strip_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", "", str(raw_html))
    return re.sub(r"\s+", " ", text).strip()


class WikimediaCommonsAdapter(BaseSourceAdapter):
    source_id = "wikimedia"
    source_name = "Wikimedia Commons"
    website = "https://commons.wikimedia.org/"
    priority = "Normal"
    supports_albums = True
    supports_tracks = True
    supports_direct_lossless = True
    requires_api_key = False
    description = "Wikimedia Commons MediaWiki API for public domain and CC-licensed FLAC/WAV/OGG recordings."
    limitations = "Primarily single recordings, classical performances, and open-culture audio files."
    rate_limit_per_sec = 2.0

    api_url = "https://commons.wikimedia.org/w/api.php"

    async def search(
        self,
        artist: str = "",
        album: str = "",
        track: str = "",
        limit: int = 10,
    ) -> List[NormalizedRelease]:
        terms = [t.strip() for t in (artist, album, track) if t and t.strip()]
        if not terms:
            return []

        search_query = f"filetype:audio {' '.join(terms)}"
        params = {
            "action": "query",
            "generator": "search",
            "gsrnamespace": 6,  # File: namespace
            "gsrsearch": search_query,
            "gsrlimit": min(limit, 20),
            "prop": "imageinfo|categories",
            "iiprop": "url|size|mime|mediatype|extmetadata|sha1|user|timestamp",
            "format": "json",
        }

        data = await self._get_json(self.api_url, params=params)
        pages: Dict[str, Any] = data.get("query", {}).get("pages", {})
        if not pages:
            return []

        releases: List[NormalizedRelease] = []
        for page_id, page in pages.items():
            imageinfo_list = page.get("imageinfo") or []
            if not imageinfo_list:
                continue
            info = imageinfo_list[0]
            mime = str(info.get("mime", "")).lower()
            url = str(info.get("url", ""))
            if not url:
                continue

            raw_title = str(page.get("title", "")).replace("File:", "")
            ext = raw_title.rsplit(".", 1)[-1] if "." in raw_title else mime.split("/")[-1]
            norm_fmt = normalize_format_name(mime if "flac" in mime or "wav" in mime else ext)
            if norm_fmt not in {"FLAC", "WAV", "ALAC", "OGG", "OPUS", "MP3"}:
                continue

            extmeta = info.get("extmetadata", {}) or {}
            artist_val = _strip_html(extmeta.get("Artist", {}).get("value", "")) or artist or "Wikimedia Contributor"
            license_short = _strip_html(extmeta.get("LicenseShortName", {}).get("value", ""))
            usage_terms = _strip_html(extmeta.get("UsageTerms", {}).get("value", ""))
            attribution = _strip_html(extmeta.get("Attribution", {}).get("value", "") or extmeta.get("Credit", {}).get("value", ""))
            date_val = _strip_html(extmeta.get("DateTimeOriginal", {}).get("value", "")) or info.get("timestamp", "")
            uploader = str(info.get("user", "Unknown"))

            clean_title = raw_title.rsplit(".", 1)[0].replace("_", " ")
            lossless = is_lossless_format(norm_fmt)
            size_bytes = int(info.get("size") or 0)
            sha1 = str(info.get("sha1") or "")
            year = extract_year(date_val)
            license_str = " / ".join(filter(None, [license_short, usage_terms])) or "Creative Commons / Public Domain"

            bit_depth = 16 if lossless else None
            sample_rate = 44100

            track_obj = NormalizedTrack(
                track_number=1,
                disc_number=1,
                title=clean_title,
                artist=artist_val,
                duration_seconds=None,
                format=norm_fmt,
                is_lossless=lossless,
                bit_depth=bit_depth,
                sample_rate=sample_rate,
                size_bytes=size_bytes,
                download_url=url,
                checksum_sha1=sha1,
            )

            releases.append(
                NormalizedRelease(
                    external_id=f"wm_{page_id}",
                    source=self.source_id,
                    artist=artist_val[:250],
                    album=album or clean_title[:250],
                    year=year,
                    cover_url="",
                    primary_format=norm_fmt,
                    available_formats=[norm_fmt],
                    is_lossless=lossless,
                    quality_label=f"16-bit / 44.1 kHz ({norm_fmt})" if lossless else f"{norm_fmt} Audio",
                    bit_depth=bit_depth,
                    sample_rate=sample_rate,
                    track_count=1,
                    total_size_bytes=size_bytes,
                    license=license_str[:250],
                    source_url=str(info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/File:{raw_title}"),
                    download_availability="DIRECT",
                    extra_metadata={
                        "uploader": uploader,
                        "attribution": attribution,
                        "mime": mime,
                        "categories": [c.get("title", "").replace("Category:", "") for c in (page.get("categories") or [])],
                    },
                    tracks=[track_obj],
                )
            )

        return releases
