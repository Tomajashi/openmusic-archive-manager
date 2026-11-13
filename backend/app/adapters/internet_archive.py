import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from backend.app.adapters.base import (
    BaseSourceAdapter,
    NormalizedRelease,
    NormalizedTrack,
    extract_year,
    is_lossless_format,
    normalize_format_name,
    parse_duration,
)

AUDIO_EXTENSIONS = {".flac", ".wav", ".wave", ".alac", ".aiff", ".mp3", ".ogg", ".opus", ".m4a"}


class InternetArchiveAdapter(BaseSourceAdapter):
    source_id = "internet_archive"
    source_name = "Internet Archive"
    website = "https://archive.org/"
    priority = "Very High"
    supports_albums = True
    supports_tracks = True
    supports_direct_lossless = True
    requires_api_key = False
    description = "Official Internet Archive Audio Archive (FLAC, WAV, Live & Studio Collections)."
    limitations = "Rights vary per item; verify individual item license URL before redistribution."
    rate_limit_per_sec = 3.0

    search_url = "https://archive.org/advancedsearch.php"
    metadata_base_url = "https://archive.org/metadata"
    download_base_url = "https://archive.org/download"

    def _build_lucene_query(self, artist: str, album: str, track: str) -> str:
        clauses = ["mediatype:(audio)", "NOT collection:(etree)"]
        if artist:
            safe_artist = artist.replace('"', "")
            clauses.append(f'(creator:("{safe_artist}") OR title:("{safe_artist}"))')
        if album:
            safe_album = album.replace('"', "")
            clauses.append(f'title:("{safe_album}")')
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

        query = self._build_lucene_query(artist, album, track)
        params = {
            "q": query,
            "fl[]": [
                "identifier",
                "title",
                "creator",
                "date",
                "year",
                "format",
                "licenseurl",
                "rights",
                "item_size",
                "downloads",
            ],
            "sort[]": "downloads desc",
            "rows": min(limit, 15),
            "page": 1,
            "output": "json",
        }

        data = await self._get_json(self.search_url, params=params)
        docs = data.get("response", {}).get("docs", [])
        if not docs:
            return []

        sem = asyncio.Semaphore(4)

        async def fetch_detail(doc: Dict[str, Any]) -> Optional[NormalizedRelease]:
            identifier = doc.get("identifier")
            if not identifier:
                return None
            async with sem:
                try:
                    meta = await self._get_json(f"{self.metadata_base_url}/{identifier}")
                    return self._parse_item_metadata(identifier, doc, meta, requested_track=track)
                except Exception:
                    return None

        tasks = [fetch_detail(doc) for doc in docs[:limit]]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None and len(r.tracks) > 0]

    def _parse_item_metadata(
        self,
        identifier: str,
        doc: Dict[str, Any],
        meta: Dict[str, Any],
        requested_track: str = "",
    ) -> Optional[NormalizedRelease]:
        metadata = meta.get("metadata", {}) or {}
        files = meta.get("files", []) or []

        creator = metadata.get("creator") or doc.get("creator") or "Unknown Artist"
        if isinstance(creator, list):
            creator = ", ".join(str(c) for c in creator)
        title = metadata.get("title") or doc.get("title") or identifier
        if isinstance(title, list):
            title = " - ".join(str(t) for t in title)

        year = extract_year(metadata.get("date") or metadata.get("year") or doc.get("year") or doc.get("date"))
        license_info = (
            metadata.get("licenseurl")
            or metadata.get("rights")
            or doc.get("licenseurl")
            or "Verify individual item rights"
        )
        if isinstance(license_info, list):
            license_info = "; ".join(str(x) for x in license_info)

        # Group audio files and prefer lossless originals over derivatives when both exist for same base filename
        raw_audio_files: List[Dict[str, Any]] = []
        available_formats_set = set()

        for f in files:
            fname = str(f.get("name", ""))
            lower_name = fname.lower()
            if not any(lower_name.endswith(ext) for ext in AUDIO_EXTENSIONS):
                continue
            raw_fmt = str(f.get("format", ""))
            norm_fmt = normalize_format_name(raw_fmt or lower_name.rsplit(".", 1)[-1])
            available_formats_set.add(norm_fmt)
            raw_audio_files.append((f, norm_fmt, raw_fmt))

        if not raw_audio_files:
            return None

        # Determine best available format per preference (FLAC > WAV > ALAC > OGG > MP3)
        format_rank = {"FLAC": 1, "WAV": 2, "ALAC": 3, "AIFF": 4, "OGG": 5, "OPUS": 6, "MP3": 7}
        has_lossless = any(is_lossless_format(raw_fmt) or is_lossless_format(norm_fmt) for _, norm_fmt, raw_fmt in raw_audio_files)

        # Deduplicate derivative files by stem if lossless exists
        by_stem: Dict[str, tuple] = {}
        for f, norm_fmt, raw_fmt in raw_audio_files:
            fname = str(f.get("name", ""))
            stem = fname.rsplit(".", 1)[0]
            # Strip IA derivative suffixes like _vbr
            if stem.endswith("_vbr"):
                stem = stem[:-4]
            rank = format_rank.get(norm_fmt, 99)
            if stem not in by_stem or rank < by_stem[stem][0]:
                by_stem[stem] = (rank, f, norm_fmt, raw_fmt)

        selected_entries = sorted(by_stem.values(), key=lambda x: str(x[1].get("name", "")))
        tracks: List[NormalizedTrack] = []
        total_size = 0
        primary_format = "MP3"
        best_rank = 99
        release_bit_depth: Optional[int] = None
        release_sample_rate: Optional[int] = None

        for idx, (rank, f, norm_fmt, raw_fmt) in enumerate(selected_entries, start=1):
            fname = str(f.get("name", ""))
            track_title = str(f.get("title") or fname.rsplit("/", 1)[-1].rsplit(".", 1)[0])
            if requested_track and requested_track.lower() not in track_title.lower() and requested_track.lower() not in title.lower():
                # Keep full album tracks if album matches, or filter if track-only search
                pass

            track_no_raw = str(f.get("track", idx)).split("/")[0]
            try:
                track_no = int(track_no_raw)
            except ValueError:
                track_no = idx

            size_bytes = int(f.get("size") or 0)
            total_size += size_bytes
            duration = parse_duration(f.get("length"))
            lossless = is_lossless_format(raw_fmt) or is_lossless_format(norm_fmt)

            bit_depth = 24 if "24bit" in raw_fmt.lower() else (16 if lossless else None)
            sample_rate = int(f.get("sample_rate") or (96000 if bit_depth == 24 else 44100)) if lossless else 44100

            if rank < best_rank:
                best_rank = rank
                primary_format = norm_fmt
                release_bit_depth = bit_depth
                release_sample_rate = sample_rate

            encoded_name = "/".join(quote(part) for part in fname.split("/"))
            dl_url = f"{self.download_base_url}/{identifier}/{encoded_name}"

            tracks.append(
                NormalizedTrack(
                    track_number=track_no,
                    disc_number=1,
                    title=track_title,
                    artist=str(f.get("artist") or f.get("creator") or creator),
                    duration_seconds=duration,
                    format=norm_fmt,
                    is_lossless=lossless,
                    bit_depth=bit_depth,
                    sample_rate=sample_rate,
                    size_bytes=size_bytes,
                    download_url=dl_url,
                    checksum_md5=str(f.get("md5") or ""),
                    checksum_sha1=str(f.get("sha1") or ""),
                    checksum_crc32=str(f.get("crc32") or ""),
                )
            )

        quality_label = (
            f"{release_bit_depth or 16}-bit / {(release_sample_rate or 44100) / 1000:.1f} kHz"
            if has_lossless
            else f"{primary_format} Standard"
        )

        extra_meta = {
            "identifier": identifier,
            "venue": metadata.get("venue", ""),
            "coverage": metadata.get("coverage", ""),
            "date": metadata.get("date", ""),
            "source_lineage": metadata.get("source", ""),
            "taper": metadata.get("taper", ""),
            "notes": metadata.get("notes", ""),
            "torrent_url": f"{self.download_base_url}/{identifier}/{identifier}_archive.torrent",
        }

        return NormalizedRelease(
            external_id=identifier,
            source=self.source_id,
            artist=str(creator),
            album=str(title),
            year=year,
            cover_url=f"https://archive.org/services/img/{identifier}",
            primary_format=primary_format,
            available_formats=sorted(available_formats_set),
            is_lossless=has_lossless,
            quality_label=quality_label,
            bit_depth=release_bit_depth,
            sample_rate=release_sample_rate,
            track_count=len(tracks),
            total_size_bytes=total_size,
            license=str(license_info),
            source_url=f"https://archive.org/details/{identifier}",
            download_availability="DIRECT",
            extra_metadata=extra_meta,
            tracks=tracks,
        )
