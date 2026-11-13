# Phase 1: Music Source API Research & Capabilities Matrix

This document records the verified API endpoints, capabilities, rate limits, lossless availability, and licensing/account constraints for all implemented source adapters in **OpenMusic Archive Manager**.

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
