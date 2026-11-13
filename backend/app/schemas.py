from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class ImportItemCreate(BaseModel):
    artist: str = Field(..., min_length=1, max_length=255)
    album: str = Field(default="", max_length=255)
    track: str = Field(default="", max_length=255)
    year: Optional[int] = None


class ImportItemUpdate(BaseModel):
    artist: Optional[str] = None
    album: Optional[str] = None
    track: Optional[str] = None
    year: Optional[int] = None
    status: Optional[str] = None


class ImportItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    artist: str
    album: str
    track: str
    year: Optional[int] = None
    status: str
    created_at: datetime


class ImportProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    source_format: str = "MANUAL"
    items: List[ImportItemCreate] = Field(default_factory=list)


class ImportProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_format: str
    description: str
    created_at: datetime
    updated_at: datetime
    items: List[ImportItemOut] = Field(default_factory=list)


class SearchQueryInput(BaseModel):
    artist: str = ""
    album: str = ""
    track: str = ""
    project_id: Optional[int] = None
    sources: Optional[List[str]] = None
    lossless_only: bool = False
    page: int = 1
    limit: int = 25


class SearchResultTrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    result_id: int
    track_number: int
    disc_number: int
    title: str
    artist: str
    duration_seconds: Optional[int] = None
    format: str
    is_lossless: bool
    bit_depth: Optional[int] = None
    sample_rate: Optional[int] = None
    size_bytes: int
    download_url: str
    checksum_md5: str
    checksum_sha1: str


class SearchResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    search_job_id: Optional[int] = None
    external_id: str
    source: str
    artist: str
    album: str
    year: Optional[int] = None
    cover_url: str
    primary_format: str
    available_formats: List[str]
    is_lossless: bool
    quality_label: str
    bit_depth: Optional[int] = None
    sample_rate: Optional[int] = None
    track_count: int
    total_size_bytes: int
    license: str
    source_url: str
    download_availability: str
    magnet_uri: str
    seeders: Optional[int] = None
    leechers: Optional[int] = None
    match_score: float
    duplicate_group_key: str
    extra_metadata: Dict[str, Any]
    created_at: datetime
    tracks: List[SearchResultTrackOut] = Field(default_factory=list)


class SearchJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query_summary: str
    project_id: Optional[int] = None
    status: str
    total_queries: int
    completed_queries: int
    sources_used: List[str]
    error_message: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class DownloadSelectionRequest(BaseModel):
    result_ids: List[int] = Field(default_factory=list, description="Entire albums/releases to download")
    track_ids: List[int] = Field(default_factory=list, description="Specific individual tracks to download")
    approved_by_user: bool = Field(..., description="Explicit user approval flag required to start downloads")
    overwrite_existing: bool = False


class DownloadJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    result_id: Optional[int] = None
    track_id: Optional[int] = None
    source: str
    artist: str
    album: str
    year: Optional[int] = None
    title: str
    track_number: int
    disc_number: int
    format: str
    download_url: str
    magnet_uri: str
    license: str
    status: str
    progress_percent: float
    downloaded_bytes: int
    total_bytes: int
    speed_bps: int
    eta_seconds: Optional[int] = None
    retries: int
    final_path: str
    checksum_verified: Optional[bool] = None
    ffprobe_codec: str
    ffprobe_bit_depth: Optional[int] = None
    ffprobe_sample_rate: Optional[int] = None
    ffprobe_duration: Optional[int] = None
    is_verified_lossless: Optional[bool] = None
    audit_flags: List[str]
    error_message: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class LibraryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    artist: str
    album: str
    year: Optional[int] = None
    title: str
    track_number: int
    disc_number: int
    format: str
    codec: str
    bit_depth: Optional[int] = None
    sample_rate: Optional[int] = None
    duration_seconds: Optional[int] = None
    size_bytes: int
    file_path: str
    cover_path: str
    musicbrainz_id: str
    source: str
    license: str
    is_verified_lossless: bool
    audit_flags: List[str]
    added_at: datetime


class DashboardStats(BaseModel):
    total_artists_requested: int
    albums_found: int
    albums_available_for_download: int
    completed_downloads: int
    failed_downloads: int
    active_downloads: int
    total_downloaded_storage_bytes: int
    enabled_sources_count: int
    total_library_tracks: int
    verified_lossless_tracks: int
    flagged_tracks: int


class SourceInfoOut(BaseModel):
    id: str
    name: str
    website: str
    priority: str
    enabled: bool
    supports_albums: bool
    supports_tracks: bool
    supports_direct_lossless: bool
    requires_api_key: bool
    api_key_configured: bool
    description: str
    limitations: str
    rate_limit_per_sec: float
