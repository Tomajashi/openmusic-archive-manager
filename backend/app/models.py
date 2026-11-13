from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    BigInteger,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship
from backend.app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportProject(Base):
    __tablename__ = "import_projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    source_format = Column(String(32), default="MANUAL")
    description = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    items = relationship("ImportItem", back_populates="project", cascade="all, delete-orphan")


class ImportItem(Base):
    __tablename__ = "import_items"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("import_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    artist = Column(String(255), nullable=False, index=True)
    album = Column(String(255), default="")
    track = Column(String(255), default="")
    year = Column(Integer, nullable=True)
    status = Column(String(32), default="PENDING")  # PENDING, SEARCHED, FOUND, DOWNLOADED
    created_at = Column(DateTime, default=utcnow)

    project = relationship("ImportProject", back_populates="items")


class SearchJob(Base):
    __tablename__ = "search_jobs"

    id = Column(Integer, primary_key=True, index=True)
    query_summary = Column(String(512), nullable=False)
    project_id = Column(Integer, ForeignKey("import_projects.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(32), default="RUNNING", index=True)  # QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED
    total_queries = Column(Integer, default=1)
    completed_queries = Column(Integer, default=0)
    sources_used = Column(JSON, default=list)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)

    results = relationship("SearchResult", back_populates="search_job", cascade="all, delete-orphan")


class SearchResult(Base):
    __tablename__ = "search_results"

    id = Column(Integer, primary_key=True, index=True)
    search_job_id = Column(Integer, ForeignKey("search_jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    external_id = Column(String(255), nullable=False, index=True)
    source = Column(String(64), nullable=False, index=True)
    artist = Column(String(255), nullable=False, index=True)
    album = Column(String(255), nullable=False, index=True)
    year = Column(Integer, nullable=True)
    cover_url = Column(Text, default="")
    primary_format = Column(String(32), default="FLAC")
    available_formats = Column(JSON, default=list)
    is_lossless = Column(Boolean, default=False)
    quality_label = Column(String(64), default="")
    bit_depth = Column(Integer, nullable=True)
    sample_rate = Column(Integer, nullable=True)
    track_count = Column(Integer, default=0)
    total_size_bytes = Column(BigInteger, default=0)
    license = Column(String(255), default="Verify individual item rights")
    source_url = Column(Text, default="")
    download_availability = Column(String(64), default="DIRECT")  # DIRECT, MAGNET, ACCOUNT_REQUIRED, STREAM_ONLY
    magnet_uri = Column(Text, default="")
    seeders = Column(Integer, nullable=True)
    leechers = Column(Integer, nullable=True)
    match_score = Column(Float, default=1.0)
    duplicate_group_key = Column(String(255), default="", index=True)
    extra_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow)

    search_job = relationship("SearchJob", back_populates="results")
    tracks = relationship("SearchResultTrack", back_populates="result", cascade="all, delete-orphan")


class SearchResultTrack(Base):
    __tablename__ = "search_result_tracks"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("search_results.id", ondelete="CASCADE"), nullable=False, index=True)
    track_number = Column(Integer, default=1)
    disc_number = Column(Integer, default=1)
    title = Column(String(255), nullable=False)
    artist = Column(String(255), default="")
    duration_seconds = Column(Integer, nullable=True)
    format = Column(String(32), default="FLAC")
    is_lossless = Column(Boolean, default=False)
    bit_depth = Column(Integer, nullable=True)
    sample_rate = Column(Integer, nullable=True)
    size_bytes = Column(BigInteger, default=0)
    download_url = Column(Text, default="")
    checksum_md5 = Column(String(64), default="")
    checksum_sha1 = Column(String(64), default="")
    checksum_crc32 = Column(String(32), default="")

    result = relationship("SearchResult", back_populates="tracks")


class DownloadJob(Base):
    __tablename__ = "download_jobs"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("search_results.id", ondelete="SET NULL"), nullable=True)
    track_id = Column(Integer, ForeignKey("search_result_tracks.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(64), nullable=False)
    artist = Column(String(255), nullable=False)
    album = Column(String(255), nullable=False)
    year = Column(Integer, nullable=True)
    title = Column(String(255), nullable=False)
    track_number = Column(Integer, default=1)
    disc_number = Column(Integer, default=1)
    format = Column(String(32), default="FLAC")
    download_url = Column(Text, default="")
    magnet_uri = Column(Text, default="")
    cover_url = Column(Text, default="")
    license = Column(String(255), default="")
    status = Column(
        String(32), default="QUEUED", index=True
    )  # QUEUED, DOWNLOADING, PAUSED, VERIFYING, ORGANIZING, COMPLETED, FAILED, CANCELLED
    progress_percent = Column(Float, default=0.0)
    downloaded_bytes = Column(BigInteger, default=0)
    total_bytes = Column(BigInteger, default=0)
    speed_bps = Column(BigInteger, default=0)
    eta_seconds = Column(Integer, nullable=True)
    retries = Column(Integer, default=0)
    temp_path = Column(Text, default="")
    final_path = Column(Text, default="")
    expected_md5 = Column(String(64), default="")
    expected_sha1 = Column(String(64), default="")
    checksum_verified = Column(Boolean, nullable=True)
    ffprobe_codec = Column(String(64), default="")
    ffprobe_bit_depth = Column(Integer, nullable=True)
    ffprobe_sample_rate = Column(Integer, nullable=True)
    ffprobe_duration = Column(Integer, nullable=True)
    is_verified_lossless = Column(Boolean, nullable=True)
    audit_flags = Column(JSON, default=list)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)


class LibraryItem(Base):
    __tablename__ = "library_items"

    id = Column(Integer, primary_key=True, index=True)
    download_job_id = Column(Integer, ForeignKey("download_jobs.id", ondelete="SET NULL"), nullable=True)
    artist = Column(String(255), nullable=False, index=True)
    album = Column(String(255), nullable=False, index=True)
    year = Column(Integer, nullable=True)
    title = Column(String(255), nullable=False)
    track_number = Column(Integer, default=1)
    disc_number = Column(Integer, default=1)
    format = Column(String(32), default="FLAC")
    codec = Column(String(64), default="")
    bit_depth = Column(Integer, nullable=True)
    sample_rate = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    size_bytes = Column(BigInteger, default=0)
    file_path = Column(Text, nullable=False)
    cover_path = Column(Text, default="")
    musicbrainz_id = Column(String(64), default="")
    source = Column(String(64), default="")
    license = Column(String(255), default="")
    is_verified_lossless = Column(Boolean, default=False)
    audit_flags = Column(JSON, default=list)
    added_at = Column(DateTime, default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(128), primary_key=True, index=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(16), default="INFO", index=True)  # INFO, WARNING, ERROR
    category = Column(String(64), default="SYSTEM", index=True)  # SYSTEM, IMPORT, SEARCH, DOWNLOAD, AUDIT, NAVIDROME
    message = Column(Text, nullable=False)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow, index=True)
