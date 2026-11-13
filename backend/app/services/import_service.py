import csv
import io
import json
from typing import Any, Dict, List, Tuple
import yaml
from backend.app.schemas import ImportItemCreate

MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB safety limit


class ImportValidationError(ValueError):
    """Raised when an imported CSV, YAML, or JSON file fails validation."""


def parse_import_content(content: str, fmt: str) -> Tuple[List[ImportItemCreate], List[str]]:
    """Parse CSV, YAML, or JSON content into normalized ImportItemCreate objects.

    Returns (items, warnings).
    """
    if not content or not content.strip():
        raise ImportValidationError("Uploaded file is empty.")
    if len(content.encode("utf-8", errors="ignore")) > MAX_UPLOAD_SIZE_BYTES:
        raise ImportValidationError("Uploaded file exceeds the 5 MB size limit.")

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
    reader = csv.DictReader(io.StringIO(content.strip()))
    if not reader.fieldnames:
        raise ImportValidationError("CSV file is missing a header row (expected: artist,album,track).")

    normalized_headers = [h.strip().lower() for h in reader.fieldnames if h]
    if "artist" not in normalized_headers:
        raise ImportValidationError("CSV header must include an 'artist' column (e.g. artist,album,track).")

    items: List[ImportItemCreate] = []
    warnings: List[str] = []

    for row_idx, row in enumerate(reader, start=2):
        lower_row: Dict[str, str] = {
            (k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k is not None
        }
        artist = lower_row.get("artist", "")
        album = lower_row.get("album", "")
        track = lower_row.get("track", "")
        year_str = lower_row.get("year", "")
        if not artist:
            if any([album, track]):
                warnings.append(f"Row {row_idx}: skipped because 'artist' is empty.")
            continue
        year_int = int(year_str) if year_str.isdigit() else None
        items.append(ImportItemCreate(artist=artist, album=album, track=track, year=year_int))

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
