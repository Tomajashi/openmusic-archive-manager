export type NavTab =
  | 'dashboard'
  | 'import'
  | 'search'
  | 'results'
  | 'downloads'
  | 'library'
  | 'sources'
  | 'settings'
  | 'logs';

export interface DashboardStats {
  total_artists_requested: number;
  albums_found: number;
  albums_available_for_download: number;
  completed_downloads: number;
  failed_downloads: number;
  active_downloads: number;
  total_downloaded_storage_bytes: number;
  enabled_sources_count: number;
  total_library_tracks: number;
  verified_lossless_tracks: number;
  flagged_tracks: number;
}

export interface ImportItem {
  id?: number;
  project_id?: number;
  artist: string;
  album: string;
  track: string;
  year?: number | null;
  status?: string;
}

export interface ImportProject {
  id: number;
  name: string;
  source_format: string;
  description: string;
  created_at: string;
  updated_at: string;
  items: ImportItem[];
}

export interface SearchJob {
  id: number;
  query_summary: string;
  project_id?: number | null;
  status: string;
  total_queries: number;
  completed_queries: number;
  sources_used: string[];
  error_message: string;
  created_at: string;
  completed_at?: string | null;
}

export interface SearchResultTrack {
  id: number;
  result_id: number;
  track_number: number;
  disc_number: number;
  title: string;
  artist: string;
  duration_seconds?: number | null;
  format: string;
  is_lossless: boolean;
  bit_depth?: number | null;
  sample_rate?: number | null;
  size_bytes: number;
  download_url: string;
  checksum_md5: string;
  checksum_sha1: string;
}

export interface SearchResult {
  id: number;
  search_job_id?: number | null;
  external_id: string;
  source: string;
  artist: string;
  album: string;
  year?: number | null;
  cover_url: string;
  primary_format: string;
  available_formats: string[];
  is_lossless: boolean;
  quality_label: string;
  bit_depth?: number | null;
  sample_rate?: number | null;
  track_count: number;
  total_size_bytes: number;
  license: string;
  source_url: string;
  download_availability: string;
  magnet_uri: string;
  seeders?: number | null;
  leechers?: number | null;
  match_score: number;
  duplicate_group_key: string;
  duplicate_count?: number;
  extra_metadata: Record<string, unknown>;
  created_at: string;
  tracks: SearchResultTrack[];
}

export interface DownloadJob {
  id: number;
  result_id?: number | null;
  track_id?: number | null;
  source: string;
  artist: string;
  album: string;
  year?: number | null;
  title: string;
  track_number: number;
  disc_number: number;
  format: string;
  download_url: string;
  magnet_uri: string;
  license: string;
  status: string;
  progress_percent: number;
  downloaded_bytes: number;
  total_bytes: number;
  speed_bps: number;
  eta_seconds?: number | null;
  retries: number;
  final_path: string;
  checksum_verified?: boolean | null;
  ffprobe_codec: string;
  ffprobe_bit_depth?: number | null;
  ffprobe_sample_rate?: number | null;
  ffprobe_duration?: number | null;
  is_verified_lossless?: boolean | null;
  audit_flags: string[];
  error_message: string;
  created_at: string;
  completed_at?: string | null;
}

export interface LibraryItem {
  id: number;
  artist: string;
  album: string;
  year?: number | null;
  title: string;
  track_number: number;
  disc_number: number;
  format: string;
  codec: string;
  bit_depth?: number | null;
  sample_rate?: number | null;
  duration_seconds?: number | null;
  size_bytes: number;
  file_path: string;
  cover_path: string;
  musicbrainz_id: string;
  source: string;
  license: string;
  is_verified_lossless: boolean;
  audit_flags: string[];
  added_at: string;
}

export interface SourceInfo {
  id: string;
  name: string;
  website: string;
  priority: string;
  enabled: boolean;
  supports_albums: boolean;
  supports_tracks: boolean;
  supports_direct_lossless: boolean;
  requires_api_key: boolean;
  api_key_configured: boolean;
  description: string;
  limitations: string;
  rate_limit_per_sec: number;
}

export interface LogEntry {
  id: number;
  level: string;
  category: string;
  message: string;
  details: Record<string, unknown>;
  created_at: string;
}
