# OpenMusic Archive Manager

**OpenMusic Archive Manager** is a self-hosted, modular music discovery, lossless verification, and download management web application built for **Navidrome** and NAS music libraries.

---

## Key Features

- **Multi-Format Music Request Imports**: Import artists, albums, and tracks via **CSV**, **YAML**, and **JSON** with validation, inline editing, downloadable templates, and reusable saved projects.
- **Parallel Modular Source Adapters**:
  1. **Internet Archive** (`archive.org` Official Search & Metadata APIs — FLAC, 24-bit FLAC, WAV, checksums, direct downloads)
  2. **etree / Live Music Archive** (`archive.org/details/etree` — specialized concert adapter inheriting from `InternetArchiveAdapter` with venue, lineage, and trading policy metadata)
  3. **Wikimedia Commons** (`commons.wikimedia.org` Official MediaWiki API — FLAC, WAV, OGG with Creative Commons/Public Domain license & uploader attribution)
  4. **Jamendo** (`api.jamendo.com/v3.0` — album & track search with verified FLAC/MP3 capability checks)
  5. **Musopen** (`musopen.org` — classical recordings & public domain catalog search with explicit account/subscription requirement notices)
  6. **PirateBay / Torrent P2P Indexer** (`apibay.org` Categories 104=FLAC & 101=Audio + optional qBittorrent/Transmission handoff and `.magnet` watch-folder export)
  7. **FLAC Music Finder Web Index** (`flacmusicfinder.top` — **opt-in, disabled by default**: replays a session cookie you copy from your own browser to read that site's search pages and collect per-file links; the site's JavaScript bot challenge is never bypassed)
- **Strict User Approval Gate**: Never downloads anything automatically; users inspect tracklists, formats, bit depth, sample rate, file sizes, duplicate releases across archives, and licenses before approving downloads.
- **True Lossless Verification with FFprobe**: Every downloaded audio file is audited using `ffprobe` and MD5/SHA1 checksums. Flags fake FLACs (`FLAC_CONTAINING_LOSSY_AUDIO`), missing metadata, incomplete downloads, and corrupt streams without ever silently re-encoding lossy files.
- **Automated Library Organization & Navidrome Sync**: Enriches tags via **MusicBrainz** and **Cover Art Archive**, organizes tracks into `/music/Artist/Album (Year)/01 - Track.flac` with `cover.jpg`, and optionally triggers a Navidrome Subsonic library scan.

---

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy 2.0 (SQLite WAL default / PostgreSQL optional), Pydantic v2, `httpx`, `mutagen`, `ffprobe` / `ffmpeg`
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons
- **Deployment**: Multi-stage Docker + Docker Compose with `PUID`/`PGID` NAS permission support and healthchecks

---

## Quick Start (Docker Compose)

```bash
cp .env.example .env
docker compose up -d --build
```

Open **`http://localhost:8080`** in your browser.

---

## Documentation

- [System Architecture](docs/ARCHITECTURE.md)
- [Source API Capabilities & Limitations](docs/API_SOURCES.md)
- [Database Schema](docs/DATABASE_SCHEMA.md)
- [REST API Documentation](docs/API_DOCS.md)
- [Installation & NAS Deployment Guide](docs/INSTALLATION.md)
- [User Guide](docs/USER_GUIDE.md)
