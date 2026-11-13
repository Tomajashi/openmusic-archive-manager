import asyncio
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse
import httpx
from sqlalchemy.orm import Session
from backend.app.database import SessionLocal
from backend.app.models import (
    DownloadJob,
    LibraryItem,
    SearchResult,
    SearchResultTrack,
)
from backend.app.services.audio_verifier import inspect_audio_with_ffprobe
from backend.app.services.logger_service import log_event
from backend.app.services.metadata_service import metadata_service
from backend.app.services.navidrome_service import navidrome_service
from backend.app.services.organizer import (
    build_organized_track_path,
    move_to_library,
    sanitize_component,
)
from backend.app.services.settings_service import get_effective_settings

TRUSTED_DOWNLOAD_DOMAINS = (
    "archive.org",
    "wikimedia.org",
    "jamendo.com",
    "musopen.org",
    "coverartarchive.org",
    "localhost",
    "127.0.0.1",
)


def is_trusted_download_url(url: str) -> bool:
    if not url:
        return False
    if url.startswith("magnet:?xt=urn:btih:"):
        return True
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    return any(host == d or host.endswith(f".{d}") for d in TRUSTED_DOWNLOAD_DOMAINS)


class DownloadManager:
    def __init__(self) -> None:
        self._active_tasks: Dict[int, asyncio.Task] = {}
        self._pause_flags: Dict[int, bool] = {}
        self._cancel_flags: Dict[int, bool] = {}
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._current_concurrency: int = 3

    def _get_semaphore(self, concurrency: int) -> asyncio.Semaphore:
        if self._semaphore is None or self._current_concurrency != concurrency:
            self._current_concurrency = max(1, concurrency)
            self._semaphore = asyncio.Semaphore(self._current_concurrency)
        return self._semaphore

    def queue_downloads(
        self,
        db: Session,
        result_ids: List[int],
        track_ids: List[int],
        approved_by_user: bool,
        overwrite_existing: bool = False,
    ) -> List[DownloadJob]:
        if not approved_by_user:
            raise ValueError("Explicit user approval is required before queuing any downloads.")

        eff = get_effective_settings(db, mask_secrets=False)
        auto_dedup = bool(eff.get("auto_duplicate_detection", True))
        created_jobs: List[DownloadJob] = []

        # 1. Queue full album releases
        for rid in result_ids:
            rel = db.query(SearchResult).filter(SearchResult.id == rid).first()
            if not rel:
                continue
            tracks = (
                db.query(SearchResultTrack)
                .filter(SearchResultTrack.result_id == rel.id)
                .order_by(SearchResultTrack.track_number.asc())
                .all()
            )
            for trk in tracks:
                job = self._create_job_for_track(db, rel, trk, auto_dedup=auto_dedup, overwrite=overwrite_existing)
                if job:
                    created_jobs.append(job)

        # 2. Queue individual selected tracks
        for tid in track_ids:
            trk = db.query(SearchResultTrack).filter(SearchResultTrack.id == tid).first()
            if not trk:
                continue
            rel = db.query(SearchResult).filter(SearchResult.id == trk.result_id).first()
            if not rel:
                continue
            if any(j.track_id == trk.id for j in created_jobs):
                continue
            job = self._create_job_for_track(db, rel, trk, auto_dedup=auto_dedup, overwrite=overwrite_existing)
            if job:
                created_jobs.append(job)

        db.commit()
        job_ids = [j.id for j in created_jobs]
        if created_jobs:
            log_event(
                "INFO",
                "DOWNLOAD",
                f"User approved and queued {len(created_jobs)} download(s).",
                {"job_ids": job_ids},
                db=db,
            )
            db.commit()

        for jid in job_ids:
            self.schedule_job(jid)

        return created_jobs

    def _create_job_for_track(
        self,
        db: Session,
        rel: SearchResult,
        trk: SearchResultTrack,
        auto_dedup: bool,
        overwrite: bool,
    ) -> Optional[DownloadJob]:
        if auto_dedup and not overwrite:
            existing_lib = (
                db.query(LibraryItem)
                .filter(
                    LibraryItem.artist.ilike(rel.artist),
                    LibraryItem.album.ilike(rel.album),
                    LibraryItem.title.ilike(trk.title),
                )
                .first()
            )
            if existing_lib and Path(existing_lib.file_path).exists():
                log_event(
                    "INFO",
                    "DOWNLOAD",
                    f"Skipped duplicate track already in library: {rel.artist} - {trk.title}",
                    {"file_path": existing_lib.file_path},
                    db=db,
                )
                return None

        dl_url = trk.download_url or ""
        magnet = rel.magnet_uri if rel.download_availability == "MAGNET" else ""
        if dl_url.startswith("magnet:"):
            magnet = dl_url
            dl_url = ""

        job = DownloadJob(
            result_id=rel.id,
            track_id=trk.id,
            source=rel.source,
            artist=rel.artist,
            album=rel.album,
            year=rel.year,
            title=trk.title,
            track_number=trk.track_number,
            disc_number=trk.disc_number,
            format=trk.format or rel.primary_format,
            download_url=dl_url,
            magnet_uri=magnet,
            cover_url=rel.cover_url,
            license=rel.license,
            status="QUEUED",
            progress_percent=0.0,
            downloaded_bytes=0,
            total_bytes=trk.size_bytes or 0,
            expected_md5=trk.checksum_md5 or "",
            expected_sha1=trk.checksum_sha1 or "",
        )
        db.add(job)
        return job

    def schedule_job(self, job_id: int) -> None:
        if job_id in self._active_tasks and not self._active_tasks[job_id].done():
            return
        self._pause_flags.pop(job_id, None)
        self._cancel_flags.pop(job_id, None)
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._run_download_job(job_id))
            self._active_tasks[job_id] = task
        except RuntimeError:
            # No running event loop (e.g. synchronous unit test context)
            pass

    async def recover_pending_jobs(self) -> None:
        session = SessionLocal()
        try:
            pending = (
                session.query(DownloadJob)
                .filter(DownloadJob.status.in_(["QUEUED", "DOWNLOADING", "VERIFYING"]))
                .all()
            )
            for job in pending:
                job.status = "QUEUED"
            session.commit()
            for job in pending:
                self.schedule_job(job.id)
        finally:
            session.close()

    def pause_job(self, db: Session, job_id: int) -> Optional[DownloadJob]:
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            return None
        if job.status in {"QUEUED", "DOWNLOADING"}:
            self._pause_flags[job_id] = True
            job.status = "PAUSED"
            job.speed_bps = 0
            db.commit()
            db.refresh(job)
        return job

    def resume_job(self, db: Session, job_id: int) -> Optional[DownloadJob]:
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            return None
        if job.status in {"PAUSED", "FAILED"}:
            self._pause_flags.pop(job_id, None)
            job.status = "QUEUED"
            job.error_message = ""
            db.commit()
            db.refresh(job)
            self.schedule_job(job.id)
        return job

    def cancel_job(self, db: Session, job_id: int) -> Optional[DownloadJob]:
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            return None
        self._cancel_flags[job_id] = True
        job.status = "CANCELLED"
        job.speed_bps = 0
        db.commit()
        db.refresh(job)
        return job

    async def _run_download_job(self, job_id: int) -> None:
        session = SessionLocal()
        try:
            eff = get_effective_settings(session, mask_secrets=False)
            concurrency = int(eff.get("download_concurrency") or 3)
            sem = self._get_semaphore(concurrency)

            async with sem:
                job = session.query(DownloadJob).filter(DownloadJob.id == job_id).first()
                if not job or job.status in {"CANCELLED", "PAUSED", "COMPLETED"}:
                    return

                # Check storage quota
                max_gb = float(eff.get("max_storage_gb") or 500.0)
                music_root = Path(str(eff.get("music_dir") or "./music"))
                download_root = Path(str(eff.get("download_dir") or "./downloads"))
                music_root.mkdir(parents=True, exist_ok=True)
                download_root.mkdir(parents=True, exist_ok=True)

                used_bytes = sum(f.stat().st_size for f in music_root.rglob("*") if f.is_file())
                if used_bytes >= int(max_gb * (1024**3)):
                    job.status = "FAILED"
                    job.error_message = f"Maximum storage quota ({max_gb} GB) reached."
                    session.commit()
                    return

                # Handle Magnet / P2P Torrent jobs
                if job.magnet_uri and not job.download_url:
                    await self._handle_magnet_download(session, job, eff, download_root)
                    return

                if not job.download_url:
                    job.status = "FAILED"
                    job.error_message = "No direct download URL available (source may require account login)."
                    session.commit()
                    return

                if not is_trusted_download_url(job.download_url):
                    job.status = "FAILED"
                    job.error_message = "Blocked untrusted download URL domain."
                    session.commit()
                    log_event(
                        "ERROR",
                        "DOWNLOAD",
                        f"Blocked untrusted download URL for job #{job.id}: {job.download_url}",
                        db=session,
                    )
                    return

                ext = job.format.lower() if job.format else "flac"
                if "." in job.download_url.rsplit("/", 1)[-1]:
                    url_ext = job.download_url.rsplit(".", 1)[-1].split("?")[0].lower()
                    if url_ext in {"flac", "wav", "alac", "mp3", "ogg", "opus", "m4a"}:
                        ext = url_ext

                temp_file = download_root / f"job_{job.id}_{sanitize_component(job.title)}.{ext}.part"
                job.temp_path = str(temp_file)
                job.status = "DOWNLOADING"
                session.commit()

                success = await self._stream_http_download(session, job, temp_file)
                if not success:
                    return

                # Verify & audit with FFprobe
                job.status = "VERIFYING"
                job.speed_bps = 0
                session.commit()

                final_temp = temp_file.with_suffix("")  # Remove .part
                if final_temp.exists():
                    final_temp.unlink()
                temp_file.rename(final_temp)

                report = inspect_audio_with_ffprobe(
                    final_temp,
                    expected_size_bytes=job.total_bytes,
                    expected_md5=job.expected_md5,
                    expected_sha1=job.expected_sha1,
                )

                job.checksum_verified = report.checksum_verified
                job.ffprobe_codec = report.codec_name
                job.ffprobe_bit_depth = report.bit_depth
                job.ffprobe_sample_rate = report.sample_rate
                job.ffprobe_duration = report.duration_seconds
                job.is_verified_lossless = report.is_verified_lossless
                job.audit_flags = report.audit_flags

                if not report.is_valid_audio or "CORRUPT_AUDIO_FILE" in report.audit_flags:
                    job.status = "FAILED"
                    job.error_message = report.error_message or "Corrupt audio file detected by FFprobe."
                    session.commit()
                    log_event(
                        "ERROR",
                        "AUDIT",
                        f"FFprobe flagged corrupt download #{job.id} ({job.title}): {job.audit_flags}",
                        {"job_id": job.id, "flags": job.audit_flags},
                        db=session,
                    )
                    return

                if report.audit_flags:
                    log_event(
                        "WARNING",
                        "AUDIT",
                        f"Audio audit flags on '{job.title}': {', '.join(report.audit_flags)}",
                        {"job_id": job.id, "codec": report.codec_name, "flags": report.audit_flags},
                        db=session,
                    )

                # Organize & enrich with MusicBrainz
                job.status = "ORGANIZING"
                session.commit()

                mb_id = ""
                year = job.year
                cover_url = job.cover_url

                if eff.get("musicbrainz_enabled", True):
                    mb_info = await metadata_service.lookup_release(job.artist, job.album)
                    if mb_info:
                        mb_id = mb_info.mbid
                        if not year and mb_info.year:
                            year = mb_info.year
                        if not cover_url and mb_info.cover_url:
                            cover_url = mb_info.cover_url

                if eff.get("embed_metadata", True):
                    metadata_service.embed_tags(
                        final_temp,
                        artist=job.artist,
                        album=job.album,
                        title=job.title,
                        track_number=job.track_number,
                        disc_number=job.disc_number,
                        year=year,
                        mbid=mb_id,
                    )
                    # Clear MISSING_METADATA flag if we just embedded complete tags
                    if "MISSING_METADATA" in job.audit_flags:
                        job.audit_flags = [f for f in job.audit_flags if f != "MISSING_METADATA"]

                naming_pattern = str(
                    eff.get("naming_pattern") or "{artist}/{album_year}/{track_num} - {title}.{ext}"
                )
                target_path, cover_path = build_organized_track_path(
                    music_root=music_root,
                    artist=job.artist,
                    album=job.album,
                    title=job.title,
                    track_number=job.track_number,
                    disc_number=job.disc_number,
                    year=year,
                    extension=ext,
                    naming_pattern=naming_pattern,
                )

                move_to_library(final_temp, target_path, overwrite=True)

                saved_cover = ""
                if eff.get("download_cover_art", True) and cover_url:
                    ok_cover = await metadata_service.download_cover_art(cover_url, cover_path)
                    if ok_cover:
                        saved_cover = str(cover_path)

                file_size = target_path.stat().st_size if target_path.exists() else job.downloaded_bytes
                job.final_path = str(target_path)
                job.progress_percent = 100.0
                job.downloaded_bytes = file_size
                job.total_bytes = file_size
                job.status = "COMPLETED"
                job.completed_at = datetime.now(timezone.utc)

                lib_item = LibraryItem(
                    download_job_id=job.id,
                    artist=job.artist,
                    album=job.album,
                    year=year,
                    title=job.title,
                    track_number=job.track_number,
                    disc_number=job.disc_number,
                    format=ext.upper(),
                    codec=job.ffprobe_codec,
                    bit_depth=job.ffprobe_bit_depth,
                    sample_rate=job.ffprobe_sample_rate,
                    duration_seconds=job.ffprobe_duration,
                    size_bytes=file_size,
                    file_path=str(target_path),
                    cover_path=saved_cover,
                    musicbrainz_id=mb_id,
                    source=job.source,
                    license=job.license,
                    is_verified_lossless=bool(job.is_verified_lossless),
                    audit_flags=job.audit_flags,
                )
                session.add(lib_item)
                session.commit()

                log_event(
                    "INFO",
                    "DOWNLOAD",
                    f"Completed & organized '{job.artist} - {job.title}' -> {target_path}",
                    {"job_id": job.id, "lossless": job.is_verified_lossless, "codec": job.ffprobe_codec},
                    db=session,
                )

                if eff.get("navidrome_enabled") and eff.get("navidrome_auto_rescan", True):
                    await navidrome_service.trigger_rescan(session)

        except Exception as exc:
            session.rollback()
            job = session.query(DownloadJob).filter(DownloadJob.id == job_id).first()
            if job and job.status not in {"PAUSED", "CANCELLED"}:
                job.status = "FAILED"
                job.error_message = str(exc)
                job.speed_bps = 0
                session.commit()
            log_event("ERROR", "DOWNLOAD", f"Download job #{job_id} error: {exc}", db=session)
        finally:
            self._active_tasks.pop(job_id, None)
            session.close()

    async def _stream_http_download(
        self,
        session: Session,
        job: DownloadJob,
        temp_file: Path,
        max_retries: int = 3,
    ) -> bool:
        for attempt in range(max_retries):
            if self._cancel_flags.get(job.id):
                job.status = "CANCELLED"
                session.commit()
                return False
            if self._pause_flags.get(job.id):
                job.status = "PAUSED"
                session.commit()
                return False

            existing_bytes = temp_file.stat().st_size if temp_file.exists() else 0
            headers = {
                "User-Agent": "OpenMusicArchiveManager/1.0 (self-hosted music manager)",
            }
            if existing_bytes > 0:
                headers["Range"] = f"bytes={existing_bytes}-"

            try:
                async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                    async with client.stream("GET", job.download_url, headers=headers) as resp:
                        if resp.status_code == 416:
                            # Range already satisfied
                            return True
                        resp.raise_for_status()

                        is_resumed = resp.status_code == 206
                        mode = "ab" if is_resumed else "wb"
                        if not is_resumed:
                            existing_bytes = 0

                        content_len = resp.headers.get("Content-Length")
                        if content_len and content_len.isdigit():
                            job.total_bytes = existing_bytes + int(content_len)

                        downloaded = existing_bytes
                        start_ts = time.monotonic()
                        last_commit_ts = start_ts

                        with temp_file.open(mode) as f:
                            async for chunk in resp.aiter_bytes(chunk_size=65536):
                                if self._cancel_flags.get(job.id):
                                    job.status = "CANCELLED"
                                    job.speed_bps = 0
                                    session.commit()
                                    return False
                                if self._pause_flags.get(job.id):
                                    job.status = "PAUSED"
                                    job.speed_bps = 0
                                    session.commit()
                                    return False

                                f.write(chunk)
                                downloaded += len(chunk)
                                now = time.monotonic()
                                if now - last_commit_ts >= 0.4:
                                    elapsed = max(0.001, now - start_ts)
                                    speed = int((downloaded - existing_bytes) / elapsed)
                                    job.downloaded_bytes = downloaded
                                    job.speed_bps = speed
                                    if job.total_bytes > 0:
                                        job.progress_percent = round(min(99.9, (downloaded / job.total_bytes) * 100.0), 1)
                                        remaining = max(0, job.total_bytes - downloaded)
                                        job.eta_seconds = int(remaining / speed) if speed > 0 else None
                                    session.commit()
                                    last_commit_ts = now

                        job.downloaded_bytes = downloaded
                        job.progress_percent = 100.0
                        session.commit()
                        return True

            except Exception as exc:
                job.retries += 1
                session.commit()
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    job.status = "FAILED"
                    job.error_message = f"Download failed after {max_retries} attempts: {exc}"
                    job.speed_bps = 0
                    session.commit()
                    return False
        return False

    async def _handle_magnet_download(
        self,
        session: Session,
        job: DownloadJob,
        eff: Dict,
        download_root: Path,
    ) -> None:
        qbit_url = str(eff.get("qbittorrent_url") or "").rstrip("/")
        if qbit_url:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    user = str(eff.get("qbittorrent_username") or "")
                    pwd = str(eff.get("qbittorrent_password") or "")
                    if user:
                        await client.post(
                            f"{qbit_url}/api/v2/auth/login",
                            data={"username": user, "password": pwd},
                        )
                    resp = await client.post(
                        f"{qbit_url}/api/v2/torrents/add",
                        data={"urls": job.magnet_uri, "savepath": str(download_root)},
                    )
                    resp.raise_for_status()
                    job.status = "COMPLETED"
                    job.progress_percent = 100.0
                    job.final_path = f"qBittorrent ({qbit_url})"
                    job.completed_at = datetime.now(timezone.utc)
                    session.commit()
                    log_event("INFO", "DOWNLOAD", f"Dispatched magnet to qBittorrent: {job.title}", db=session)
                    return
            except Exception as exc:
                log_event("WARNING", "DOWNLOAD", f"qBittorrent RPC error, saving .magnet file instead: {exc}", db=session)

        # Save .magnet descriptor in downloads/torrents watch folder
        torrents_dir = download_root / "torrents"
        torrents_dir.mkdir(parents=True, exist_ok=True)
        magnet_file = torrents_dir / f"{sanitize_component(job.artist)} - {sanitize_component(job.title)}.magnet"
        magnet_file.write_text(job.magnet_uri, encoding="utf-8")

        job.final_path = str(magnet_file)
        job.progress_percent = 100.0
        job.status = "COMPLETED"
        job.audit_flags = ["MAGNET_EXPORTED_VERIFY_WITH_FFPROBE_AFTER_CLIENT_FINISH"]
        job.completed_at = datetime.now(timezone.utc)
        session.commit()
        log_event(
            "INFO",
            "DOWNLOAD",
            f"Exported approved magnet link to watch folder: {magnet_file}",
            {"magnet_file": str(magnet_file)},
            db=session,
        )


download_manager = DownloadManager()
