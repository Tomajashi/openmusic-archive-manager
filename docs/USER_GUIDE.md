# User Guide — OpenMusic Archive Manager

## 1. Importing Desired Music (CSV, YAML, JSON)
1. Open the **Import Music** tab in the sidebar.
2. Download one of the ready-made templates (`CSV Template`, `YAML Template`, or `JSON Template`) or upload your own file.
3. Click **Validate & Preview Entries**.
4. Review the staged table:
   - Edit artist, album, or track names inline.
   - Add extra rows manually or delete unwanted rows.
5. Enter a project name and click **Save as Reusable Project**.

---

## 2. Searching Multiple Archives Simultaneously
1. Open **Music Search** (or click **Search All Archives** directly on a saved project card).
2. Enter an Artist, Album, and/or Track, or choose a saved Import Project.
3. Select which archives to query:
   - **Internet Archive** (`archive.org`)
   - **etree / Live Music Archive** (`archive.org/details/etree`)
   - **Wikimedia Commons** (`commons.wikimedia.org`)
   - **Jamendo Music** (`jamendo.com`)
   - **Musopen Classical** (`musopen.org`)
   - **PirateBay / Torrent P2P** (`apibay.org` / Torznab)
4. Toggle **Strict Lossless Filter** if you only want FLAC/WAV releases.
5. Searches run asynchronously in the background so you can continue browsing.

---

## 3. Reviewing Results & Approving Downloads
1. Open **Search Results**.
2. Each release displays:
   - Source archive, primary format (`FLAC`, `WAV`, `MP3`), bit depth & sample rate (`16-bit / 44.1 kHz`, `24-bit / 96.0 kHz`), track count, total size, and license/trading permissions.
   - For P2P torrents, active **Seeders / Leechers** and magnet availability are shown.
3. If the same album was found on multiple archives, click **Compare N Duplicate Releases** to compare quality, track count, and licenses side-by-side.
4. Click **View Tracks** to inspect individual tracks and select specific tracks, or click **Select Album** to select the entire release.
5. Click **Review & Approve** in the top bar and confirm in the approval dialog. **Nothing is ever downloaded without your explicit approval.**

---

## 4. Download Manager & FFprobe Audio Audit
1. In **Download Manager**, monitor live progress, download speed, ETA, and retry count.
2. You can **Pause**, **Resume**, **Retry**, or **Cancel** any download.
3. Once a file finishes downloading, `ffprobe` inspects its audio stream:
   - **Verified Lossless**: Confirms the actual audio stream codec is `flac`, `alac`, or `pcm_*`.
   - **Audit Flags**: Alerts you if a `.flac` file actually wraps a lossy stream (`FLAC_CONTAINING_LOSSY_AUDIO`), has missing tags (`MISSING_METADATA`), is truncated (`INCOMPLETE_DOWNLOAD`), or is corrupt (`CORRUPT_AUDIO_FILE`).

---

## 5. Music Library & Navidrome Integration
1. Verified files are automatically organized into:
   ```text
   /music/
     Artist/
       Album (Year)/
         01 - Track.flac
         02 - Track.flac
         cover.jpg
   ```
2. MusicBrainz and Cover Art Archive metadata are embedded automatically when enabled.
3. Click **Trigger Navidrome Rescan** in **Music Library** (or enable automatic rescan in **Settings**) to immediately update your Navidrome server.
