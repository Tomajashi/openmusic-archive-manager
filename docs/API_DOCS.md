# OpenMusic Archive Manager — REST API Documentation

Interactive OpenAPI / Swagger UI is automatically served at `/docs` and ReDoc at `/redoc`.

---

## Health & Dashboard

### `GET /api/v1/health`
Returns service health and version status (used by Docker `HEALTHCHECK`).

### `GET /api/v1/dashboard/stats`
Returns aggregated statistics:
- `total_artists_requested`
- `albums_found`
- `albums_available_for_download`
- `completed_downloads`
- `failed_downloads`
- `active_downloads`
- `total_downloaded_storage_bytes`
- `enabled_sources_count`
- `total_library_tracks`
- `verified_lossless_tracks`
- `flagged_tracks`

---

## Import System (`/api/v1/imports`)

### `POST /api/v1/imports/preview`
Multipart form upload (`file` or `raw_content`, optional `format_hint`). Validates CSV, YAML, or JSON files and returns normalized entries (`artist`, `album`, `track`, `year`) and validation warnings prior to saving or searching.

### `GET /api/v1/imports/templates/{fmt}`
Downloads a ready-to-use example template (`csv`, `yaml`, or `json`).

### `GET /api/v1/imports/projects` & `POST /api/v1/imports/projects`
List or create reusable import projects.

### `POST /api/v1/imports/projects/{project_id}/items`
Add a manual entry to a saved project.

### `PUT /api/v1/imports/items/{item_id}` & `DELETE /api/v1/imports/items/{item_id}`
Edit or remove an individual imported entry.

---

## Search Engine (`/api/v1/search`)

### `POST /api/v1/search/start`
Starts an asynchronous parallel search job across enabled source adapters.
```json
{
  "artist": "Grateful Dead",
  "album": "Cornell 1977-05-08",
  "track": "",
  "project_id": null,
  "sources": ["internet_archive", "etree", "wikimedia", "jamendo", "musopen", "piratebay"],
  "lossless_only": true
}
```

### `GET /api/v1/search/jobs` & `POST /api/v1/search/jobs/{job_id}/cancel`
Track or cancel active background search jobs.

### `GET /api/v1/search/results`
Paginated normalized search results with duplicate release detection (`duplicate_group_key`, `duplicate_count`) and embedded `tracks[]`.

---

## Download Manager (`/api/v1/downloads`)

### `POST /api/v1/downloads/queue`
Queues user-selected albums (`result_ids`) or individual tracks (`track_ids`).
**Requires `"approved_by_user": true`**.

```json
{
  "result_ids": [1, 4],
  "track_ids": [12, 15],
  "approved_by_user": true,
  "overwrite_existing": false
}
```

### `POST /api/v1/downloads/{job_id}/{action}`
Supported actions: `pause`, `resume`, `retry`, `cancel`.

---

## Music Library & Navidrome (`/api/v1/library`)

### `GET /api/v1/library`
List organized library tracks with FFprobe codec/bit-depth metadata and audit flags.

### `POST /api/v1/library/scan-disk`
Scans `/music` directory with `ffprobe` and indexes existing audio files.

### `POST /api/v1/library/navidrome/rescan`
Triggers a Navidrome Subsonic library scan (`/rest/startScan.view`).

---

## Sources, Settings & Logs

- `GET /api/v1/sources` — List all source adapters and capabilities.
- `POST /api/v1/sources/{source_id}/toggle` — Enable/disable a music source adapter.
- `GET /api/v1/settings` & `PUT /api/v1/settings` — Read/update persistent settings (API keys are masked on read).
- `GET /api/v1/logs` & `DELETE /api/v1/logs` — Inspect or clear system/audit logs.
