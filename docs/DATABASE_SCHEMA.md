# Database Schema

OpenMusic Archive Manager uses **SQLAlchemy 2.0 ORM** and supports **SQLite** (default, stored in `/app/config/openmusic.db` with WAL mode enabled) and **PostgreSQL** (via `DATABASE_URL`).

```mermaid
erDiagram
    IMPORT_PROJECTS ||--o{ IMPORT_ITEMS : contains
    SEARCH_JOBS ||--o{ SEARCH_RESULTS : produces
    SEARCH_RESULTS ||--o{ SEARCH_RESULT_TRACKS : includes
    DOWNLOAD_JOBS }o--|| SEARCH_RESULTS : downloads_from
    LIBRARY_ITEMS }o--o| DOWNLOAD_JOBS : organized_from

    IMPORT_PROJECTS {
        int id PK
        string name
        string source_format
        string description
        datetime created_at
        datetime updated_at
    }

    IMPORT_ITEMS {
        int id PK
        int project_id FK
        string artist
        string album
        string track
        int year
        string status
        datetime created_at
    }

    SEARCH_JOBS {
        int id PK
        string query_summary
        int project_id FK
        string status
        int total_queries
        int completed_queries
        json sources_used
        string error_message
        datetime created_at
        datetime completed_at
    }

    SEARCH_RESULTS {
        int id PK
        int search_job_id FK
        string external_id
        string source
        string artist
        string album
        int year
        string cover_url
        string primary_format
        boolean is_lossless
        int bit_depth
        int sample_rate
        int track_count
        bigint total_size_bytes
        string license
        string source_url
        string download_url
        string magnet_uri
        int seeders
        int leechers
        float match_score
        string duplicate_group_key
        json extra_metadata
        datetime created_at
    }

    SEARCH_RESULT_TRACKS {
        int id PK
        int result_id FK
        int track_number
        int disc_number
        string title
        string artist
        int duration_seconds
        string format
        boolean is_lossless
        int bit_depth
        int sample_rate
        bigint size_bytes
        string download_url
        string checksum_md5
        string checksum_sha1
    }

    DOWNLOAD_JOBS {
        int id PK
        int result_id FK
        int track_id FK
        string source
        string artist
        string album
        string title
        string format
        string download_url
        string magnet_uri
        string status
        float progress_percent
        bigint downloaded_bytes
        bigint total_bytes
        bigint speed_bps
        int eta_seconds
        int retries
        string temp_path
        string final_path
        string expected_checksum
        boolean checksum_verified
        string ffprobe_codec
        int ffprobe_bit_depth
        int ffprobe_sample_rate
        boolean is_verified_lossless
        json audit_flags
        string error_message
        datetime created_at
        datetime completed_at
    }

    LIBRARY_ITEMS {
        int id PK
        string artist
        string album
        int year
        string title
        int track_number
        int disc_number
        string format
        string codec
        int bit_depth
        int sample_rate
        int duration_seconds
        bigint size_bytes
        string file_path
        string cover_path
        string musicbrainz_id
        string source
        string license
        boolean is_verified_lossless
        json audit_flags
        datetime added_at
    }

    APP_SETTINGS {
        string key PK
        json value
        datetime updated_at
    }

    SYSTEM_LOGS {
        int id PK
        string level
        string category
        string message
        json details
        datetime created_at
    }
```
