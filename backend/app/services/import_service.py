import csv
import io
import json
import re
from typing import Any, Dict, List, Optional, Tuple
import yaml
from backend.app.schemas import ImportItemCreate

MAX_UPLOAD_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB safety limit for large playlists

ARTIST_HEADER_ALIASES = (
    "artist",
    "artist name(s)",
    "artist names",
    "artist name",
    "artists",
    "artist_name",
    "track artist",
    "performer",
    "creator",
    "author",
)

FALLBACK_ARTIST_HEADER_ALIASES = (
    "album artist name(s)",
    "album artist names",
    "album artist name",
    "album artist",
    "album_artist",
    "album artists",
)

ALBUM_HEADER_ALIASES = (
    "album",
    "album name",
    "album_name",
    "album title",
    "album_title",
    "release",
    "release name",
    "record",
)

TRACK_HEADER_ALIASES = (
    "track",
    "track name",
    "track_name",
    "title",
    "track title",
    "track_title",
    "song",
    "song name",
    "song_name",
    "name",
)

YEAR_HEADER_ALIASES = (
    "year",
    "album release date",
    "release date",
    "release_date",
    "release year",
    "release_year",
    "date",
)

ALL_KNOWN_HEADER_NAMES = set(
    ARTIST_HEADER_ALIASES
    + FALLBACK_ARTIST_HEADER_ALIASES
    + ALBUM_HEADER_ALIASES
    + TRACK_HEADER_ALIASES
    + YEAR_HEADER_ALIASES
    + ("track uri", "artist uri(s)", "album uri", "isrc", "added at", "added by")
)


class ImportValidationError(ValueError):
    """Raised when an imported CSV, YAML, or JSON file fails validation."""


def _clean_csv_cell(value: str) -> str:
    """Clean CSV cell text, including Exportify's backslash-escaped commas."""
    if not value:
        return ""
    cleaned = value.replace("\\,", ",").strip()
    return re.sub(r"\s+", " ", cleaned)


def _extract_year(raw_date: str) -> Optional[int]:
    """Extract a 4-digit release year from strings like '2018-02-02', '1979-06', or '2024'."""
    if not raw_date:
        return None
    text = raw_date.strip()
    if text.isdigit() and len(text) == 4:
        return int(text)
    match = re.search(r"\b(1[6-9]\d{2}|20\d{2})\b", text)
    if match:
        return int(match.group(1))
    return None


def _pick_first_matching_col(row_dict: Dict[str, str], aliases: Tuple[str, ...]) -> str:
    for alias in aliases:
        val = row_dict.get(alias, "")
        if val:
            return val
    return ""


def _is_repeated_header_row(artist_val: str, album_val: str, track_val: str, lower_row: Dict[str, str]) -> bool:
    """Detect repeated header rows in concatenated CSV exports (e.g. multiple Exportify files merged)."""
    a_low = artist_val.strip().lower()
    t_low = track_val.strip().lower()
    alb_low = album_val.strip().lower()
    if a_low in ARTIST_HEADER_ALIASES or a_low in FALLBACK_ARTIST_HEADER_ALIASES:
        if not t_low or t_low in TRACK_HEADER_ALIASES or alb_low in ALBUM_HEADER_ALIASES:
            return True
    if lower_row.get("track uri", "").strip().lower() == "track uri":
        return True
    return False


def _detect_csv_delimiter(sample_line: str) -> str:
    """Auto-detect comma, semicolon, or tab delimiter from the header line."""
    comma_count = sample_line.count(",")
    semi_count = sample_line.count(";")
    tab_count = sample_line.count("\t")
    if semi_count > comma_count and semi_count >= tab_count:
        return ";"
    if tab_count > comma_count and tab_count > semi_count:
        return "\t"
    return ","


def parse_import_content(content: str, fmt: str) -> Tuple[List[ImportItemCreate], List[str]]:
    """Parse CSV, YAML, or JSON content into normalized ImportItemCreate objects.

    Returns (items, warnings).
    """
    if not content:
        raise ImportValidationError("Uploaded file is empty.")
    # Strip UTF-8 BOM (\ufeff) if present
    content = content.lstrip("\ufeff")
    if not content.strip():
        raise ImportValidationError("Uploaded file is empty.")
    if len(content.encode("utf-8", errors="ignore")) > MAX_UPLOAD_SIZE_BYTES:
        raise ImportValidationError("Uploaded file exceeds the 15 MB size limit.")

    norm_fmt = fmt.strip().upper().lstrip(".")
    if norm_fmt in {"YML", "YAML"}:
        return _parse_structured_data(_load_yaml(content), "YAML")
    if norm_fmt == "JSON":
        return _parse_structured_data(_load_json(content), "JSON")
    if norm_fmt == "CSV":
        return _parse_csv(content)

    raise ImportValidationError(f"Unsupported import format '{fmt}'. Supported formats: CSV, YAML, JSON.")


def _load_json(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ImportValidationError(f"Invalid JSON syntax: {exc.msg} at line {exc.lineno}") from exc


def _load_yaml(content: str) -> Any:
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ImportValidationError(f"Invalid YAML syntax: {exc}") from exc


def _parse_structured_data(data: Any, fmt_label: str) -> Tuple[List[ImportItemCreate], List[str]]:
    if data is None:
        raise ImportValidationError(f"{fmt_label} document is empty.")

    items: List[ImportItemCreate] = []
    warnings: List[str] = []

    # Support either {"artists": [...]} or a top-level list of entry dicts
    if isinstance(data, dict):
        artists_list = data.get("artists") or data.get("items") or data.get("requests")
        if not isinstance(artists_list, list):
            raise ImportValidationError(
                f"{fmt_label} object must contain an 'artists' or 'items' list."
            )
    elif isinstance(data, list):
        artists_list = data
    else:
        raise ImportValidationError(f"Unexpected root type in {fmt_label}; expected object or array.")

    for idx, entry in enumerate(artists_list, start=1):
        if not isinstance(entry, dict):
            warnings.append(f"Skipped entry #{idx}: not a valid object.")
            continue

        artist_name = str(entry.get("name") or entry.get("artist") or "").strip()
        if not artist_name:
            warnings.append(f"Skipped entry #{idx}: missing artist name.")
            continue

        albums = entry.get("albums")
        tracks = entry.get("tracks")
        single_album = str(entry.get("album") or "").strip()
        single_track = str(entry.get("track") or "").strip()
        year = entry.get("year")
        year_int = int(year) if isinstance(year, int) or (isinstance(year, str) and year.isdigit()) else None

        added_for_artist = False

        if isinstance(albums, list):
            for alb in albums:
                if isinstance(alb, dict):
                    alb_name = str(alb.get("title") or alb.get("name") or "").strip()
                    alb_tracks = alb.get("tracks") or []
                    if alb_tracks and isinstance(alb_tracks, list):
                        for t_name in alb_tracks:
                            items.append(
                                ImportItemCreate(
                                    artist=artist_name,
                                    album=alb_name,
                                    track=str(t_name).strip(),
                                    year=year_int,
                                )
                            )
                            added_for_artist = True
                    elif alb_name:
                        items.append(ImportItemCreate(artist=artist_name, album=alb_name, track="", year=year_int))
                        added_for_artist = True
                elif str(alb).strip():
                    items.append(ImportItemCreate(artist=artist_name, album=str(alb).strip(), track="", year=year_int))
                    added_for_artist = True

        if isinstance(tracks, list):
            for trk in tracks:
                if isinstance(trk, dict):
                    t_title = str(trk.get("title") or trk.get("name") or "").strip()
                    t_album = str(trk.get("album") or single_album).strip()
                    if t_title:
                        items.append(ImportItemCreate(artist=artist_name, album=t_album, track=t_title, year=year_int))
                        added_for_artist = True
                elif str(trk).strip():
                    items.append(
                        ImportItemCreate(artist=artist_name, album=single_album, track=str(trk).strip(), year=year_int)
                    )
                    added_for_artist = True

        if not added_for_artist:
            items.append(
                ImportItemCreate(
                    artist=artist_name,
                    album=single_album,
                    track=single_track,
                    year=year_int,
                )
            )

    if not items:
        raise ImportValidationError(f"No valid artist/album/track entries found in {fmt_label} file.")

    return items, warnings


def _parse_csv(content: str) -> Tuple[List[ImportItemCreate], List[str]]:
    cleaned_content = content.lstrip("\ufeff").strip()
    lines = [ln for ln in cleaned_content.splitlines() if ln.strip()]
    if not lines:
        raise ImportValidationError("CSV file is empty.")

    delimiter = _detect_csv_delimiter(lines[0])
    reader = csv.DictReader(io.StringIO(cleaned_content), delimiter=delimiter)
    if not reader.fieldnames:
        raise ImportValidationError("CSV file is missing a header row (expected: artist,album,track).")

    normalized_headers = [h.strip().lstrip("\ufeff").lower() for h in reader.fieldnames if h]
    has_artist_col = any(
        alias in normalized_headers for alias in (ARTIST_HEADER_ALIASES + FALLBACK_ARTIST_HEADER_ALIASES)
    )
    if not has_artist_col:
        raise ImportValidationError(
            "CSV header must include an artist column (e.g. 'artist', 'Artist Name(s)', 'Artist Name', or 'Album Artist')."
        )

    items: List[ImportItemCreate] = []
    warnings: List[str] = []
    seen_keys: set[Tuple[str, str, str]] = set()
    duplicate_count = 0
    repeated_header_count = 0

    for row_idx, row in enumerate(reader, start=2):
        lower_row: Dict[str, str] = {
            (k or "").strip().lstrip("\ufeff").lower(): (v or "").strip()
            for k, v in row.items()
            if k is not None
        }
        if not any(lower_row.values()):
            continue

        raw_artist = _pick_first_matching_col(lower_row, ARTIST_HEADER_ALIASES)
        if not raw_artist:
            raw_artist = _pick_first_matching_col(lower_row, FALLBACK_ARTIST_HEADER_ALIASES)

        raw_album = _pick_first_matching_col(lower_row, ALBUM_HEADER_ALIASES)
        raw_track = _pick_first_matching_col(lower_row, TRACK_HEADER_ALIASES)
        raw_year = _pick_first_matching_col(lower_row, YEAR_HEADER_ALIASES)

        if _is_repeated_header_row(raw_artist, raw_album, raw_track, lower_row):
            repeated_header_count += 1
            continue

        artist = _clean_csv_cell(raw_artist)
        album = _clean_csv_cell(raw_album)
        track = _clean_csv_cell(raw_track)

        if not artist:
            if any([album, track]):
                warnings.append(f"Row {row_idx}: skipped because artist column is empty.")
            continue

        dedup_key = (artist.lower(), album.lower(), track.lower())
        if dedup_key in seen_keys:
            duplicate_count += 1
            continue
        seen_keys.add(dedup_key)

        year_int = _extract_year(raw_year)
        items.append(ImportItemCreate(artist=artist, album=album, track=track, year=year_int))

    if repeated_header_count > 0:
        warnings.append(f"Skipped {repeated_header_count} repeated header row(s) from concatenated CSV.")
    if duplicate_count > 0:
        warnings.append(f"Skipped {duplicate_count} duplicate track/album entry row(s).")

    if not items:
        raise ImportValidationError("No valid music rows found in CSV file.")

    return items, warnings


def get_template_content(fmt: str) -> Tuple[str, str, str]:
    """Return (content, media_type, filename) for downloadable templates."""
    norm = fmt.strip().lower()
    if norm == "json":
        sample = {
            "artists": [
                {
                    "name": "Daft Punk",
                    "albums": ["Discovery", "Random Access Memories"],
                    "tracks": ["One More Time"],
                },
                {
                    "name": "Pink Floyd",
                    "albums": ["The Dark Side of the Moon"],
                },
                {
                    "name": "Grateful Dead",
                    "albums": ["Cornell 1977-05-08"],
                },
            ]
        }
        return json.dumps(sample, indent=2), "application/json", "openmusic_template.json"

    if norm in {"yaml", "yml"}:
        content = (
            "artists:\n"
            "  - name: Daft Punk\n"
            "    albums:\n"
            "      - Discovery\n"
            "      - Random Access Memories\n"
            "    tracks:\n"
            "      - One More Time\n\n"
            "  - name: Pink Floyd\n"
            "    albums:\n"
            "      - The Dark Side of the Moon\n\n"
            "  - name: Grateful Dead\n"
            "    albums:\n"
            "      - Cornell 1977-05-08\n"
        )
        return content, "application/x-yaml", "openmusic_template.yaml"

    if norm in {"spotify", "spotify_csv", "exportify"}:
        content = (
            '"Track URI","Track Name","Artist URI(s)","Artist Name(s)","Album URI","Album Name",'
            '"Album Artist URI(s)","Album Artist Name(s)","Album Release Date"\n'
            '"spotify:track:2Foc5Q5nqNiosCNqttzHof","Get Lucky (feat. Pharrell Williams)","spotify:artist:4tZwfgrHOc3mvqYlEYSvVi","Daft Punk, Pharrell Williams","spotify:album:4m2880jivSbbyEGAKfITCa","Random Access Memories","spotify:artist:4tZwfgrHOc3mvqYlEYSvVi","Daft Punk","2013-05-17"\n'
            '"spotify:track:3Wrjm47oTz2sjIgck11l5e","Beggin\'","spotify:artist:0lAWpj5szCSwM4rUMHYmrr","Måneskin","spotify:album:2qJw6w5XwQO0PQlSWPu7Tw","Chosen","spotify:artist:0lAWpj5szCSwM4rUMHYmrr","Måneskin","2017-12-08"\n'
        )
        return content, "text/csv", "openmusic_spotify_template.csv"

    # Default CSV
    content = (
        "artist,album,track\n"
        "Daft Punk,Discovery,\n"
        "Daft Punk,Random Access Memories,\n"
        "Daft Punk,Discovery,One More Time\n"
        "Pink Floyd,The Dark Side of the Moon,\n"
        "Grateful Dead,Cornell 1977-05-08,\n"
    )
    return content, "text/csv", "openmusic_template.csv"
