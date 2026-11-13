from pathlib import Path
import subprocess
import pytest
from sqlalchemy.orm import Session
from backend.app.models import DownloadJob, LibraryItem, SearchResult, SearchResultTrack
from backend.app.services.audio_verifier import inspect_audio_with_ffprobe
from backend.app.services.download_manager import download_manager
from backend.app.services.organizer import build_organized_track_path


def _generate_audio_file(target: Path, codec_args: list[str]) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=44100:duration=1",
        *codec_args,
        str(target),
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def test_ffprobe_verifies_real_flac_and_flags_fake_flac_corrupt_and_incomplete(tmp_path: Path):
    # 1. Real 16-bit / 44.1kHz FLAC with metadata
    real_flac = tmp_path / "real_lossless.flac"
    _generate_audio_file(
        real_flac,
        [
            "-c:a",
            "flac",
            "-sample_fmt",
            "s16",
            "-metadata",
            "title=One More Time",
            "-metadata",
            "artist=Daft Punk",
        ],
    )
    rep_real = inspect_audio_with_ffprobe(real_flac)
    assert rep_real.is_valid_audio is True
    assert rep_real.codec_name == "flac"
    assert rep_real.sample_rate == 44100
    assert rep_real.is_verified_lossless is True
    assert "FLAC_CONTAINING_LOSSY_AUDIO" not in rep_real.audit_flags
    assert "MISSING_METADATA" not in rep_real.audit_flags

    # 2. Fake FLAC: MP3 stream saved with a .flac extension
    mp3_temp = tmp_path / "lossy.mp3"
    _generate_audio_file(mp3_temp, ["-c:a", "libmp3lame", "-b:a", "128k"])
    fake_flac = tmp_path / "disguised_lossy.flac"
    fake_flac.write_bytes(mp3_temp.read_bytes())

    rep_fake = inspect_audio_with_ffprobe(fake_flac)
    assert rep_fake.is_valid_audio is True
    assert rep_fake.codec_name == "mp3"
    assert rep_fake.is_verified_lossless is False
    assert "FLAC_CONTAINING_LOSSY_AUDIO" in rep_fake.audit_flags
    assert "MISSING_METADATA" in rep_fake.audit_flags

    # 3. Incomplete download (actual size < 90% of expected size)
    rep_incomplete = inspect_audio_with_ffprobe(
        real_flac, expected_size_bytes=real_flac.stat().st_size * 3
    )
    assert "INCOMPLETE_DOWNLOAD" in rep_incomplete.audit_flags

    # 4. Corrupt / invalid audio file
    corrupt_file = tmp_path / "corrupt.flac"
    corrupt_file.write_bytes(b"NOT_A_VALID_AUDIO_STREAM_HEADER_12345")
    rep_corrupt = inspect_audio_with_ffprobe(corrupt_file)
    assert rep_corrupt.is_valid_audio is False
    assert "CORRUPT_AUDIO_FILE" in rep_corrupt.audit_flags


def test_path_traversal_protection_in_organizer(tmp_path: Path):
    music_root = tmp_path / "music"
    music_root.mkdir(exist_ok=True)
    track_path, cover_path = build_organized_track_path(
        music_root=music_root,
        artist="../../etc/passwd",
        album="..\\Windows\\System32",
        title="01/../../EvilTrack",
        track_number=1,
        year=2024,
        extension="flac",
    )
    assert str(track_path.resolve()).startswith(str(music_root.resolve()))
    assert str(cover_path.resolve()).startswith(str(music_root.resolve()))


@pytest.mark.asyncio
async def test_download_approval_gate_interruption_failure_and_success(
    db_session: Session, tmp_path: Path, monkeypatch
):
    rel = SearchResult(
        external_id="ia_test_1",
        source="internet_archive",
        artist="Pink Floyd",
        album="The Dark Side of the Moon",
        year=1973,
        primary_format="FLAC",
        available_formats=["FLAC"],
        is_lossless=True,
        track_count=2,
        total_size_bytes=200000,
    )
    db_session.add(rel)
    db_session.flush()

    trk1 = SearchResultTrack(
        result_id=rel.id,
        track_number=1,
        title="Speak to Me",
        artist="Pink Floyd",
        format="FLAC",
        is_lossless=True,
        size_bytes=50000,
        download_url="https://archive.org/download/ia_test_1/01_speak.flac",
    )
    trk2 = SearchResultTrack(
        result_id=rel.id,
        track_number=2,
        title="Breathe",
        artist="Pink Floyd",
        format="FLAC",
        is_lossless=True,
        size_bytes=50000,
        download_url="https://archive.org/download/ia_test_1/02_breathe_fail.flac",
    )
    db_session.add_all([trk1, trk2])
    db_session.commit()

    # 1. Must reject unapproved downloads
    with pytest.raises(ValueError, match="Explicit user approval"):
        download_manager.queue_downloads(
            db=db_session,
            result_ids=[rel.id],
            track_ids=[],
            approved_by_user=False,
        )

    # Generate valid FLAC bytes for mock HTTP stream
    sample_flac = tmp_path / "fixture.flac"
    _generate_audio_file(sample_flac, ["-c:a", "flac", "-sample_fmt", "s16"])
    flac_bytes = sample_flac.read_bytes()

    async def mock_stream_http(session: Session, job: DownloadJob, temp_file: Path, max_retries: int = 3) -> bool:
        if "fail" in job.download_url:
            job.status = "FAILED"
            job.retries = 3
            job.error_message = "Simulated HTTP 503 failure"
            session.commit()
            return False
        temp_file.write_bytes(flac_bytes)
        job.downloaded_bytes = len(flac_bytes)
        job.total_bytes = len(flac_bytes)
        job.progress_percent = 100.0
        session.commit()
        return True

    monkeypatch.setattr(download_manager, "_stream_http_download", mock_stream_http)

    # Disable remote MusicBrainz network call in unit test
    from backend.app.services.metadata_service import metadata_service

    async def no_op_mb(*args, **kwargs):
        return None

    monkeypatch.setattr(metadata_service, "lookup_release", no_op_mb)

    jobs = download_manager.queue_downloads(
        db=db_session,
        result_ids=[rel.id],
        track_ids=[],
        approved_by_user=True,
    )
    assert len(jobs) == 2

    # Wait for background tasks to finish
    for j in jobs:
        task = download_manager._active_tasks.get(j.id)
        if task:
            await task

    db_session.expire_all()
    j1 = db_session.query(DownloadJob).filter(DownloadJob.track_id == trk1.id).first()
    j2 = db_session.query(DownloadJob).filter(DownloadJob.track_id == trk2.id).first()

    assert j1.status == "COMPLETED"
    assert j1.is_verified_lossless is True
    assert j1.ffprobe_codec == "flac"
    assert Path(j1.final_path).exists()

    assert j2.status == "FAILED"
    assert "Simulated HTTP 503" in j2.error_message

    # Test Pause / Resume state transitions on failed/interrupted job
    paused = download_manager.pause_job(db_session, j2.id)
    assert paused is not None

    lib_items = db_session.query(LibraryItem).all()
    assert len(lib_items) == 1
    assert lib_items[0].artist == "Pink Floyd"
    assert lib_items[0].is_verified_lossless is True
