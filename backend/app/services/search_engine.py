import asyncio
from datetime import datetime, timezone
from difflib import SequenceMatcher
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from backend.app.adapters.base import NormalizedRelease
from backend.app.adapters.registry import adapter_registry
from backend.app.database import SessionLocal
from backend.app.models import (
    ImportItem,
    SearchJob,
    SearchResult,
    SearchResultTrack,
)
from backend.app.services.logger_service import log_event
from backend.app.services.settings_service import get_effective_settings, get_enabled_sources


def _clean_key_text(value: str) -> str:
    text = (value or "").lower().strip()
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_primary_artist(artist: str) -> str:
    """Extract the primary artist from a multi-artist string (e.g. 'Eminem, Juice WRLD' -> 'Eminem'),
    while preserving suffixes like 'Jr.' or band names like 'Earth, Wind & Fire'.
    """
    raw = (artist or "").replace("\\,", ",").strip()
    if "," not in raw:
        return raw
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) <= 1:
        return raw
    second_lower = parts[1].lower().rstrip(".")
    if second_lower in {"jr", "sr", "ii", "iii", "iv", "inc", "ltd"}:
        return f"{parts[0]}, {parts[1]}"
    if "&" in parts[1] or parts[1].lower().startswith("and "):
        return f"{parts[0]}, {parts[1]}"
    return parts[0]


def build_duplicate_group_key(artist: str, album: str) -> str:
    a_clean = _clean_key_text(extract_primary_artist(artist)) or "unknown"
    b_clean = _clean_key_text(album) or "unknown"
    return f"{a_clean}::{b_clean}"


def compute_match_score(
    query_artist: str,
    query_album: str,
    query_track: str,
    result_artist: str,
    result_album: str,
    result_tracks: List[str],
) -> float:
    scores: List[float] = []
    if query_artist:
        q_a = _clean_key_text(query_artist)
        q_primary = _clean_key_text(extract_primary_artist(query_artist))
        r_a = _clean_key_text(result_artist)
        r_alb = _clean_key_text(result_album)
        if q_a and (q_a in r_a or r_a in q_a or q_a in r_alb):
            scores.append(1.0)
        elif q_primary and (q_primary in r_a or r_a in q_primary or q_primary in r_alb):
            scores.append(1.0)
        else:
            scores.append(
                max(
                    SequenceMatcher(None, q_a, r_a).ratio(),
                    SequenceMatcher(None, q_a, r_alb).ratio(),
                    SequenceMatcher(None, q_primary, r_a).ratio() if q_primary else 0.0,
                )
            )

    if query_album:
        q_b = _clean_key_text(query_album)
        r_b = _clean_key_text(result_album)
        if q_b and (q_b in r_b or r_b in q_b):
            scores.append(1.0)
        else:
            scores.append(SequenceMatcher(None, q_b, r_b).ratio())

    if query_track:
        q_t = _clean_key_text(query_track)
        best_trk = 0.0
        for t_name in result_tracks:
            r_t = _clean_key_text(t_name)
            if q_t in r_t or r_t in q_t:
                best_trk = 1.0
                break
            best_trk = max(best_trk, SequenceMatcher(None, q_t, r_t).ratio())
        scores.append(best_trk)

    if not scores:
        return 1.0
    return round(sum(scores) / len(scores), 3)


class SearchCache:
    """Thread-safe TTL cache for normalized search results."""

    def __init__(self, ttl_seconds: int = 900) -> None:
        self.ttl = ttl_seconds
        self._store: Dict[str, Tuple[float, List[NormalizedRelease]]] = {}

    def _make_key(self, source: str, artist: str, album: str, track: str) -> str:
        return f"{source}|{_clean_key_text(artist)}|{_clean_key_text(album)}|{_clean_key_text(track)}"

    def get(self, source: str, artist: str, album: str, track: str) -> Optional[List[NormalizedRelease]]:
        key = self._make_key(source, artist, album, track)
        entry = self._store.get(key)
        if not entry:
            return None
        ts, data = entry
        if time.monotonic() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        return data

    def set(self, source: str, artist: str, album: str, track: str, releases: List[NormalizedRelease]) -> None:
        key = self._make_key(source, artist, album, track)
        self._store[key] = (time.monotonic(), releases)

    def clear(self) -> None:
        self._store.clear()


search_cache = SearchCache()


class SearchEngine:
    def __init__(self) -> None:
        self._active_tasks: Dict[int, asyncio.Task] = {}

    async def start_async_search_job(
        self,
        db: Session,
        artist: str = "",
        album: str = "",
        track: str = "",
        project_id: Optional[int] = None,
        sources: Optional[List[str]] = None,
        lossless_only: bool = False,
        wait_for_completion: bool = False,
    ) -> SearchJob:
        enabled = sources if sources else get_enabled_sources(db)
        queries: List[Tuple[str, str, str, Optional[int]]] = []

        if project_id is not None:
            items = db.query(ImportItem).filter(ImportItem.project_id == project_id).all()
            # Album-first requirement: order complete album searches before individual track searches
            album_items = [it for it in items if it.album and not it.track]
            artist_only_items = [it for it in items if not it.album and not it.track]
            track_items = [it for it in items if it.track]
            for it in album_items + artist_only_items + track_items:
                queries.append((it.artist, it.album, it.track, it.id))
            summary = f"Project #{project_id} ({len(queries)} items)"
        else:
            queries.append((artist.strip(), album.strip(), track.strip(), None))
            parts = [p for p in (artist, album, track) if p]
            summary = " - ".join(parts) if parts else "General Search"

        job = SearchJob(
            query_summary=summary[:500],
            project_id=project_id,
            status="RUNNING",
            total_queries=max(1, len(queries)),
            completed_queries=0,
            sources_used=enabled,
        )
        db.add(job)
        db.commit()
        job_id = job.id

        log_event(
            "INFO",
            "SEARCH",
            f"Started search job #{job_id}: '{summary}' across sources {enabled}",
            {"job_id": job_id, "sources": enabled},
            db=db,
        )
        db.commit()

        if wait_for_completion:
            await self._execute_job(job_id, queries, enabled, lossless_only)
            db.expire_all()
        else:
            task = asyncio.create_task(self._execute_job(job_id, queries, enabled, lossless_only))
            self._active_tasks[job_id] = task

        return db.query(SearchJob).filter(SearchJob.id == job_id).first()

    async def _execute_job(
        self,
        job_id: int,
        queries: List[Tuple[str, str, str, Optional[int]]],
        sources: List[str],
        lossless_only: bool,
    ) -> None:
        session = SessionLocal()
        try:
            eff = get_effective_settings(session, mask_secrets=False)
            concurrency = max(1, int(eff.get("search_concurrency") or 5))
            min_quality = str(eff.get("min_audio_quality") or "ANY")
            if min_quality in {"LOSSLESS_ONLY", "HI_RES_ONLY"}:
                lossless_only = True

            sem = asyncio.Semaphore(concurrency)
            found_albums_set = set()

            for q_artist, q_album, q_track, item_id in queries:
                job = session.query(SearchJob).filter(SearchJob.id == job_id).first()
                if not job or job.status == "CANCELLED":
                    break

                # If searching a specific track whose album was already found in full during this batch, still allow or optimize
                dup_key = build_duplicate_group_key(q_artist, q_album)
                if q_track and q_album and dup_key in found_albums_set:
                    job.completed_queries += 1
                    session.commit()
                    continue

                releases = await self._search_all_sources_for_query(
                    q_artist, q_album, q_track, sources, sem, eff
                )

                saved_count = 0
                for rel in releases:
                    if lossless_only and not rel.is_lossless:
                        continue
                    score = compute_match_score(
                        q_artist,
                        q_album,
                        q_track,
                        rel.artist,
                        rel.album,
                        [t.title for t in rel.tracks],
                    )
                    if score < 0.22:
                        continue

                    rel_dup_key = build_duplicate_group_key(rel.artist, rel.album)
                    if rel.track_count >= 3:
                        found_albums_set.add(rel_dup_key)

                    db_result = SearchResult(
                        search_job_id=job_id,
                        external_id=rel.external_id,
                        source=rel.source,
                        artist=rel.artist,
                        album=rel.album,
                        year=rel.year,
                        cover_url=rel.cover_url,
                        primary_format=rel.primary_format,
                        available_formats=rel.available_formats,
                        is_lossless=rel.is_lossless,
                        quality_label=rel.quality_label,
                        bit_depth=rel.bit_depth,
                        sample_rate=rel.sample_rate,
                        track_count=rel.track_count,
                        total_size_bytes=rel.total_size_bytes,
                        license=rel.license,
                        source_url=rel.source_url,
                        download_availability=rel.download_availability,
                        magnet_uri=rel.magnet_uri,
                        seeders=rel.seeders,
                        leechers=rel.leechers,
                        match_score=score,
                        duplicate_group_key=rel_dup_key,
                        extra_metadata=rel.extra_metadata,
                    )
                    session.add(db_result)
                    session.flush()

                    for trk in rel.tracks:
                        session.add(
                            SearchResultTrack(
                                result_id=db_result.id,
                                track_number=trk.track_number,
                                disc_number=trk.disc_number,
                                title=trk.title,
                                artist=trk.artist or rel.artist,
                                duration_seconds=trk.duration_seconds,
                                format=trk.format,
                                is_lossless=trk.is_lossless,
                                bit_depth=trk.bit_depth,
                                sample_rate=trk.sample_rate,
                                size_bytes=trk.size_bytes,
                                download_url=trk.download_url,
                                checksum_md5=trk.checksum_md5,
                                checksum_sha1=trk.checksum_sha1,
                                checksum_crc32=trk.checksum_crc32,
                            )
                        )
                    saved_count += 1

                if item_id is not None:
                    imp_item = session.query(ImportItem).filter(ImportItem.id == item_id).first()
                    if imp_item:
                        imp_item.status = "FOUND" if saved_count > 0 else "SEARCHED"

                job.completed_queries += 1
                session.commit()

            job = session.query(SearchJob).filter(SearchJob.id == job_id).first()
            if job and job.status != "CANCELLED":
                job.status = "COMPLETED"
                job.completed_at = datetime.now(timezone.utc)
                session.commit()
                log_event("INFO", "SEARCH", f"Completed search job #{job_id}", {"job_id": job_id}, db=session)

        except Exception as exc:
            session.rollback()
            job = session.query(SearchJob).filter(SearchJob.id == job_id).first()
            if job:
                job.status = "FAILED"
                job.error_message = str(exc)
                job.completed_at = datetime.now(timezone.utc)
                session.commit()
            log_event("ERROR", "SEARCH", f"Search job #{job_id} failed: {exc}", {"job_id": job_id}, db=session)
        finally:
            self._active_tasks.pop(job_id, None)
            session.close()

    async def _search_all_sources_for_query(
        self,
        artist: str,
        album: str,
        track: str,
        sources: List[str],
        sem: asyncio.Semaphore,
        eff_settings: Dict[str, Any],
    ) -> List[NormalizedRelease]:
        effective_artist = extract_primary_artist(artist)

        async def run_one_source(src_id: str) -> List[NormalizedRelease]:
            cached = search_cache.get(src_id, effective_artist, album, track)
            if cached is not None:
                return cached

            adapter = adapter_registry.get(src_id)
            if not adapter:
                return []

            async with sem:
                try:
                    # Album-first search: if searching artist+album, query album first
                    res = await adapter.search(artist=effective_artist, album=album, track=track, limit=8)
                    search_cache.set(src_id, effective_artist, album, track, res)
                    return res
                except Exception as exc:
                    log_event(
                        "WARNING",
                        "SEARCH",
                        f"Source '{src_id}' unavailable or failed during search: {exc}",
                        {"source": src_id, "artist": artist, "album": album},
                    )
                    return []

        nested = await asyncio.gather(*(run_one_source(s) for s in sources))
        combined: List[NormalizedRelease] = []
        for sublist in nested:
            combined.extend(sublist)

        # Sort according to user's preferred audio formats & lossless priority
        pref_formats: List[str] = eff_settings.get("preferred_formats") or ["FLAC", "WAV", "ALAC"]
        fmt_order = {fmt.upper(): idx for idx, fmt in enumerate(pref_formats)}

        combined.sort(
            key=lambda r: (
                0 if r.is_lossless else 1,
                fmt_order.get(r.primary_format.upper(), 99),
                -r.track_count,
            )
        )
        return combined


search_engine = SearchEngine()
