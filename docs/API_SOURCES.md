# Phase 1: Music Source API Research & Capabilities Matrix

This document records the verified API endpoints, capabilities, rate limits, lossless availability, and licensing/account constraints for all implemented source adapters in **OpenMusic Archive Manager**.

> **Rights note**: the first five sources publish material under explicit licenses or public-domain/permission-based terms. The last two (`piratebay`, `flacmusicfinder`) index third-party submissions of commercial releases, so the rights to download a given item depend on your jurisdiction and the item itself. For that reason `flacmusicfinder` ships **disabled by default** and requires your own credentials, and every item still passes the same explicit user-approval gate and `ffprobe` audit.

---

## Summary Matrix

| Source Adapter | ID | Official API Endpoint | Album Search | Track Search | Direct Lossless (FLAC/WAV) | Auth Required | Special Constraints / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Internet Archive** | `internet_archive` | `https://archive.org/advancedsearch.php` & `/metadata/{id}` | Yes | Yes | Yes (`Flac`, `24bit Flac`, `WAVE`) | No | Check individual item `licenseurl` / `rights`. Supports HTTP range resume & MD5/SHA1/CRC32 verification. |
| **etree / Live Music Archive** | `etree` | `https://archive.org/advancedsearch.php` (`collection:etree`) | Yes (Concerts) | Yes | Yes (Primary format is 16/24-bit FLAC) | No | Inherits from `InternetArchiveAdapter`. Exposes `venue`, `coverage`, `date`, `lineage`, and non-commercial trading notices. |
| **Wikimedia Commons** | `wikimedia` | `https://commons.wikimedia.org/w/api.php` | Category / File | Yes | Yes (`audio/flac`, `audio/x-wav`) | No | Requires descriptive `User-Agent` header per Wikimedia User-Agent policy. Returns CC/Public Domain licenses & attribution via `extmetadata`. |
| **Jamendo** | `jamendo` | `https://api.jamendo.com/v3.0/` (`/albums`, `/tracks`) | Yes | Yes | Conditional (`audioformat=flac` where permitted) | `JAMENDO_CLIENT_ID` | Jamendo API v3.0 defaults to MP3 (`mp32`) and only exposes FLAC downloads when the artist/album enables lossless distribution and `audiodlallowed=true`. |
| **Musopen** | `musopen` | Public Catalog / Archive Mirror (`collection:musopen`) | Yes | Yes (Compositions) | Restricted on Musopen.org; Direct via IA Musopen collection | Optional | Musopen discontinued its unauthenticated bulk download REST API and restricts lossless downloads on `musopen.org` to paid subscribers (free accounts have daily lossy limits). Adapter queries public classical metadata & verified Musopen public-domain releases while explicitly surfacing account/subscription restrictions without bypassing them. |
| **PirateBay / Torznab P2P** | `piratebay` | `https://apibay.org/q.php` & Custom Torznab XML/JSON | Yes | Yes | Yes (Category `104` = FLAC, `101` = Audio) | No (Optional API key for Torznab) | P2P BitTorrent indexer. Returns `info_hash`, `magnet:` URI, seeders/leechers, and file list (`apibay.org/f.php?id=`). Can hand off magnets to qBittorrent/Transmission RPC or export `.magnet` / `.torrent` metadata after explicit user approval. |
| **FLAC Music Finder Web Index** | `flacmusicfinder` | `https://flacmusicfinder.top` HTML/JSON search pages (unofficial, no public API) | Yes | Yes | Reported FLAC/lossless links are parsed, not guaranteed | `flacmusicfinder_cookie` (browser session cookie) | **Disabled by default.** No official API and every page is gated by a Cloudflare JavaScript bot challenge. The adapter replays a session cookie you paste from your own browser and parses the HTML it returns; it never solves or bypasses the challenge. Parsing is heuristic and the exact search route may need `flacmusicfinder_search_path`. Results stay `ACCOUNT_REQUIRED` until file links are found, and the file host must be in the download allowlist. |

---

## Detailed Adapter Specifications

### 1. Internet Archive (`internet_archive`)
- **Search API**: `GET https://archive.org/advancedsearch.php`
  - Query syntax: `mediatype:(audio) AND NOT collection:(etree) AND (creator:("...") OR title:("..."))`
  - Returned fields (`fl[]`): `identifier,title,creator,date,year,format,downloads,licenseurl,rights,item_size,description`
- **Item Metadata API**: `GET https://archive.org/metadata/{identifier}`
  - Provides `files[]` array with exact `name`, `format` (`Flac`, `24bit Flac`, `VBR MP3`, `WAVE`, `Ogg Vorbis`), `size`, `length`, `track`, `title`, `album`, `artist`, `md5`, `sha1`, `crc32`.
- **Direct Download URL**: `https://archive.org/download/{identifier}/{url_encoded_filename}`
- **Cover Art**: `https://archive.org/services/img/{identifier}`

### 2. etree / Live Music Archive (`etree`)
- **Architecture**: Subclasses `InternetArchiveAdapter` to avoid code duplication.
- **Search Filter**: Restricts Lucene query to `collection:(etree) AND mediatype:(audio)` and prioritizes `format:(Flac OR "24bit Flac")`.
- **Specialized Metadata**: Extracts `venue`, `coverage` (city/state), `date` (concert date), `source` (microphone/board lineage), `taper`, `transferer`, and `notes` (trading restrictions).

### 3. Wikimedia Commons (`wikimedia`)
- **Search API**: `GET https://commons.wikimedia.org/w/api.php`
  - Parameters: `action=query&generator=search&gsrnamespace=6&gsrsearch=filetype:audio ...&prop=imageinfo&iiprop=url|size|mime|mediatype|extmetadata|sha1|user|timestamp&format=json`
- **Format Detection**: Inspects `mime` (`audio/flac`, `audio/x-flac`, `audio/wav`, `audio/x-wav`, `audio/ogg`, `audio/mpeg`).
- **License & Attribution**: Parses `extmetadata.LicenseShortName.value`, `extmetadata.UsageTerms.value`, `extmetadata.Artist.value`, and `extmetadata.Credit.value`.

### 4. Jamendo (`jamendo`)
- **Search API**:
  - Albums: `GET https://api.jamendo.com/v3.0/albums/?client_id={ID}&format=json&namesearch={q}&artist_name={artist}`
  - Album Tracks: `GET https://api.jamendo.com/v3.0/albums/tracks/?client_id={ID}&format=json&id={album_id}&audioformat=flac`
  - Tracks: `GET https://api.jamendo.com/v3.0/tracks/?client_id={ID}&format=json&search={q}&audioformat=flac&include=licenses+musicinfo`
- **Verified Limitation**:
  - Not all Jamendo tracks are available in FLAC via the public v3.0 API, and some artists set `audiodlallowed: false`.
  - Our adapter inspects `audiodlallowed` and the actual `audiodownload` URL parameters before marking a release as downloadable or lossless, and clearly labels whether the stream/download is `FLAC` or `MP3`.

### 5. Musopen (`musopen`)
- **Verified Limitation**:
  - Musopen (`https://musopen.org`) no longer offers an open unauthenticated REST API for direct FLAC downloads; direct downloads on `musopen.org` require user authentication and a supporter subscription for lossless audio.
  - However, Musopen's public domain classical recordings are cataloged publicly and mirrored in the official Internet Archive `musopen` collection (`https://archive.org/details/musopen`) as well as OpenOpus classical metadata.
  - Our `MusopenAdapter` queries public domain classical recordings from the Musopen collection and links back to both `musopen.org` and the public archive files, explicitly displaying account/subscription requirements where applicable and never bypassing download limits.

### 6. PirateBay / Torznab P2P (`piratebay`)
- **Search API**:
  - Default Apibay endpoint: `GET https://apibay.org/q.php?q={query}&cat=101,104`
    - Category `104`: Audio FLAC / Lossless
    - Category `101`: Audio / Music
  - File list endpoint: `GET https://apibay.org/f.php?id={torrent_id}`
  - Optional Custom Torznab endpoint (`TORZNAB_URL` & `TORZNAB_API_KEY`) for Prowlarr/Jackett integration.
- **Download Handling**:
  - Builds standard BitTorrent magnet links (`magnet:?xt=urn:btih:{info_hash}&dn={name}&tr=...`)
  - Supports sending approved magnet downloads to a configured **qBittorrent WebUI API** (`QBITTORRENT_URL`) or **Transmission RPC** (`TRANSMISSION_URL`), or saving `.magnet` descriptor files in the staging directory for external torrent client pickup.
  - Clearly marks P2P results with seeders/leechers counts and `"Unverified P2P — Verify Rights & Audio Integrity"` warnings.

### 7. FLAC Music Finder Web Index (`flacmusicfinder`) — opt-in, cookie replay
- **No public API**: the site exposes no documented endpoints (probe results: `/api/search`, `/api/v1/search`, `/feed`, `/rss`, `/manifest.json`, `/browse`, `/login` all return Apache `404`, and `robots.txt` / `sitemap.xml` are absent), so the adapter scrapes the HTML search pages instead and accepts a JSON array/object response if the site ever returns one.
- **Bot challenge policy**: every page is fronted by Cloudflare and served as a JSFuck challenge (`var cid=…`, `<noscript>This page requires JavaScript`) to visitors without a valid session. The adapter **detects** that page and stops with an actionable error; it never solves, emulates, or otherwise bypasses it. The only supported route is replaying a session cookie that *you* obtained by logging into the site in your own browser.
- **Required settings** (Settings → *FLAC Music Finder*, or the `FLACMUSICFINDER_*` variables in `.env`):

  | Setting | Purpose |
  | :--- | :--- |
  | `flacmusicfinder_enabled` | Master switch. Off by default; also toggled by `POST /api/v1/sources/flacmusicfinder/toggle`. |
  | `flacmusicfinder_cookie` | Secret (masked by `GET /api/v1/settings` as `********` + `flacmusicfinder_cookie_configured`). Sent verbatim as the `Cookie` header, flattened onto one line. |
  | `flacmusicfinder_base_url` | Site root, default `https://flacmusicfinder.top`. |
  | `flacmusicfinder_search_path` | Exact search request template with a `{query}` placeholder. Leave empty to try built-in guesses (`/search?q=`, `/search/{query}`, `/index.php?do=search&subaction=dload&story=`, `/?q=`). |
  | `flacmusicfinder_user_agent` | Must match the browser the cookie came from, otherwise the session is usually rejected (default: a Chrome 131 UA). |
  | `flacmusicfinder_max_details` | How many result pages are opened per search to collect per-file links (`0-20`, default `5`). |
  | `flacmusicfinder_extra_download_hosts` | Comma-separated hosts that actually serve the files; added to the download allowlist **only** while this source is enabled. |

- **Parsing heuristics**: release titles are read from result links shaped like `Artist - Album (Year) [FLAC] [16-44.1]`; year, format, bit depth, sample rate and sizes are extracted from the title/ surrounding markup, `-` split for artist/album, `[bits]-[rate]` / `kHz` hints for quality, and `(MB|GB|KB)` sizes near each file link. Result pages that expose audio links produce `download_availability="DIRECT"` tracks; a page with only a `.zip/.rar/.7z/.tar/.gz` bundle is marked `DIRECT` with `extra_metadata.download_kind="ARCHIVE"`; a page with neither stays `ACCOUNT_REQUIRED`.
- **Request behaviour**: rate-limited to 1 request per 2 s (adapter-level throttle inherited from `BaseSourceAdapter._throttle`, sequential requests, `httpx` follows redirects), challenge/`401`/`403` responses raise a descriptive `RuntimeError` shown in the search job log, and the cookie is **deleted from any cross-host redirect** (`cookie_strip_hook` runs both in the adapter and in the downloader, and `download_request_headers` supplies it for downloads) so your session is never forwarded to a third-party file host.
- **Verification status**: the route, markup and file host of the live site could not be inspected from the development environment (the JavaScript gate blocks all unauthenticated HTML), so the parsing layer is deliberately defensive and covered by unit tests against representative fixtures (`backend/tests/test_flac_music_finder_adapter.py`) rather than captured traffic. If a search returns nothing, set `flacmusicfinder_search_path` to the real search URL (DevTools → Network → *Copy as cURL*) and check the logged request path.

---

## 8. Adding another cookie-gated web index

1. Copy `backend/app/adapters/flac_music_finder.py` and change `source_id`, `source_name`, `website`, `description`, `limitations`, `DEFAULT_BASE_URL` and the parsing helpers.
2. Add its settings to `backend/app/config.py`, `get_default_settings_dict()` and (for any secret) `SECRET_KEYS` in `backend/app/services/settings_service.py`; add the key to `get_enabled_sources()` so it stays opt-in.
3. Register the adapter in `backend/app/adapters/registry.py`, and add its id to `toggle_source` in `backend/app/routers/sources.py` if the toggle must flip a `*_enabled` flag.
4. Add its file hosts to the download allowlist through an `<source>_download_hosts()` helper consumed by `backend/app/services/download_manager.py`; keep the extra hosts conditional on the source being enabled.
