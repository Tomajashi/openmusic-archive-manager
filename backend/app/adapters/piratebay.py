import asyncio
from typing import Any, Dict, List
from urllib.parse import quote
from backend.app.adapters.base import (
    BaseSourceAdapter,
    NormalizedRelease,
    NormalizedTrack,
    extract_year,
    is_lossless_format,
    normalize_format_name,
)
from backend.app.config import settings

DEFAULT_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.bittor.pw:1337/announce",
    "udp://public.popcorn-tracker.org:6969/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://exodus.desync.com:6969",
]


def build_magnet_uri(info_hash: str, name: str) -> str:
    clean_hash = (info_hash or "").strip()
    if not clean_hash or clean_hash == "0" * 40:
        return ""
    tr_params = "&".join(f"tr={quote(t)}" for t in DEFAULT_TRACKERS)
    return f"magnet:?xt=urn:btih:{clean_hash}&dn={quote(name)}&{tr_params}"


class PirateBayAdapter(BaseSourceAdapter):
    """Torrent / P2P Indexer Adapter (The Pirate Bay APIbay + Custom Torznab support)."""

    source_id = "piratebay"
    source_name = "PirateBay / Torrent Indexer"
    website = "https://thepiratebay.org/"
    priority = "Optional (P2P)"
    supports_albums = True
    supports_tracks = True
    supports_direct_lossless = True
    requires_api_key = False
    description = (
        "BitTorrent P2P audio search via APIbay (Categories 104=FLAC & 101=Music) and optional Torznab indexer. "
        "Provides magnet links, seeders/leechers stats, file listings, and qBittorrent/Transmission handoff."
    )
    limitations = (
        "P2P swarm availability depends on active seeders. Always verify item licensing in your jurisdiction "
        "and inspect downloaded audio with the built-in FFprobe lossless verifier."
    )
    rate_limit_per_sec = 1.5

    def get_base_url(self) -> str:
        return (settings.piratebay_api_url or "https://apibay.org").rstrip("/")

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

        query = " ".join(terms)
        base_url = self.get_base_url()
        search_url = f"{base_url}/q.php"
        params = {"q": query, "cat": "101,104"}

        data = await self._get_json(search_url, params=params)
        if not isinstance(data, list):
            return []

        valid_items = [
            item
            for item in data
            if isinstance(item, dict)
            and str(item.get("id", "0")) != "0"
            and str(item.get("name", "")) != "No results returned"
        ]
        if not valid_items:
            return []

        # Sort by FLAC category (104) first and then seeders descending
        valid_items.sort(
            key=lambda x: (
                1 if str(x.get("category")) == "104" or "flac" in str(x.get("name", "")).lower() else 0,
                int(x.get("seeders") or 0),
            ),
            reverse=True,
        )

        sem = asyncio.Semaphore(3)

        async def build_release(item: Dict[str, Any]) -> NormalizedRelease:
            tid = str(item.get("id", ""))
            title = str(item.get("name", "Unknown Torrent"))
            info_hash = str(item.get("info_hash", ""))
            size_bytes = int(item.get("size") or 0)
            seeders = int(item.get("seeders") or 0)
            leechers = int(item.get("leechers") or 0)
            num_files = max(1, int(item.get("num_files") or 1))
            cat = str(item.get("category") or "101")

            lower_title = title.lower()
            is_flac = cat == "104" or "flac" in lower_title or "lossless" in lower_title or "24bit" in lower_title or "24-bit" in lower_title
            is_wav = "wav" in lower_title or "pcm" in lower_title
            primary_fmt = "FLAC" if is_flac else ("WAV" if is_wav else "MP3")
            lossless = is_lossless_format(primary_fmt)

            bit_depth = 24 if ("24bit" in lower_title or "24-bit" in lower_title) else (16 if lossless else None)
            sample_rate = 96000 if "96khz" in lower_title else (44100 if lossless else 44100)
            quality_label = (
                f"{bit_depth}-bit / {sample_rate / 1000:.1f} kHz ({primary_fmt} Torrent)"
                if lossless
                else f"{primary_fmt} Torrent"
            )

            magnet = build_magnet_uri(info_hash, title)

            # Attempt to fetch torrent file list from /f.php?id={tid}
            tracks: List[NormalizedTrack] = []
            async with sem:
                try:
                    files_data = await self._get_json(f"{base_url}/f.php", params={"id": tid}, timeout=8.0, max_retries=1)
                    if isinstance(files_data, list):
                        idx = 1
                        for f_entry in files_data:
                            # APIbay returns {"name": ["filename.flac"], "size": [12345]} or ["filename.flac", 12345]
                            fname = ""
                            fsize = 0
                            if isinstance(f_entry, dict):
                                n_val = f_entry.get("name")
                                s_val = f_entry.get("size")
                                fname = str(n_val[0] if isinstance(n_val, list) and n_val else (n_val or ""))
                                fsize = int(s_val[0] if isinstance(s_val, list) and s_val else (s_val or 0))
                            elif isinstance(f_entry, list) and len(f_entry) >= 2:
                                fname = str(f_entry[0])
                                fsize = int(f_entry[1] or 0)
                            if fname and any(fname.lower().endswith(ext) for ext in (".flac", ".wav", ".alac", ".mp3", ".ogg", ".m4a")):
                                f_ext = fname.rsplit(".", 1)[-1]
                                f_fmt = normalize_format_name(f_ext)
                                tracks.append(
                                    NormalizedTrack(
                                        track_number=idx,
                                        disc_number=1,
                                        title=fname.rsplit("/", 1)[-1].rsplit(".", 1)[0],
                                        artist=artist or title.split("-")[0].strip(),
                                        format=f_fmt,
                                        is_lossless=is_lossless_format(f_fmt),
                                        bit_depth=bit_depth if is_lossless_format(f_fmt) else None,
                                        sample_rate=sample_rate,
                                        size_bytes=fsize,
                                        download_url=magnet,
                                    )
                                )
                                idx += 1
                except Exception:
                    pass

            if not tracks:
                tracks.append(
                    NormalizedTrack(
                        track_number=1,
                        disc_number=1,
                        title=title,
                        artist=artist or title.split("-")[0].strip(),
                        format=primary_fmt,
                        is_lossless=lossless,
                        bit_depth=bit_depth,
                        sample_rate=sample_rate,
                        size_bytes=size_bytes,
                        download_url=magnet,
                    )
                )

            parsed_artist = artist or (title.split("-")[0].strip() if "-" in title else "Unknown Artist")
            parsed_album = album or title

            return NormalizedRelease(
                external_id=f"tpb_{tid}",
                source=self.source_id,
                artist=parsed_artist[:250],
                album=parsed_album[:250],
                year=extract_year(title),
                cover_url="",
                primary_format=primary_fmt,
                available_formats=[primary_fmt],
                is_lossless=lossless,
                quality_label=quality_label,
                bit_depth=bit_depth,
                sample_rate=sample_rate,
                track_count=len(tracks) if len(tracks) > 1 else num_files,
                total_size_bytes=size_bytes,
                license="Unverified P2P Torrent — Verify rights before downloading",
                source_url=f"https://thepiratebay.org/description.php?id={tid}",
                download_availability="MAGNET",
                magnet_uri=magnet,
                seeders=seeders,
                leechers=leechers,
                extra_metadata={
                    "torrent_id": tid,
                    "info_hash": info_hash,
                    "uploader": item.get("username", "anonymous"),
                    "uploader_status": item.get("status", "member"),
                    "category_id": cat,
                    "num_files": num_files,
                },
                tracks=tracks,
            )

        results = await asyncio.gather(*(build_release(it) for it in valid_items[:limit]))
        return list(results)
