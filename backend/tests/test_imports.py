import pytest
from backend.app.services.import_service import (
    ImportValidationError,
    get_template_content,
    parse_import_content,
)


def test_json_import_multiple_artists_and_albums():
    raw_json = """
    {
      "artists": [
        {
          "name": "Daft Punk",
          "albums": ["Discovery", "Random Access Memories"],
          "tracks": ["One More Time"]
        },
        {
          "name": "Pink Floyd",
          "albums": ["The Dark Side of the Moon"]
        }
      ]
    }
    """
    items, warnings = parse_import_content(raw_json, "JSON")
    assert len(warnings) == 0
    assert len(items) == 4
    assert items[0].artist == "Daft Punk"
    assert items[0].album == "Discovery"
    assert items[2].track == "One More Time"
    assert items[3].artist == "Pink Floyd"
    assert items[3].album == "The Dark Side of the Moon"


def test_yaml_import_artist_with_several_albums_and_single_track():
    raw_yaml = """
    artists:
      - name: Daft Punk
        albums:
          - Discovery
          - Random Access Memories
      - name: Pink Floyd
        albums:
          - The Dark Side of the Moon
      - name: Johann Sebastian Bach
        track: Toccata and Fugue in D minor
    """
    items, warnings = parse_import_content(raw_yaml, "YAML")
    assert len(warnings) == 0
    assert len(items) == 4
    assert items[0].album == "Discovery"
    assert items[1].album == "Random Access Memories"
    assert items[3].artist == "Johann Sebastian Bach"
    assert items[3].track == "Toccata and Fugue in D minor"


def test_csv_import_individual_album_and_tracks():
    raw_csv = (
        "artist,album,track\n"
        "Daft Punk,Discovery,\n"
        "Daft Punk,Random Access Memories,Get Lucky\n"
        "Pink Floyd,The Dark Side of the Moon,\n"
    )
    items, warnings = parse_import_content(raw_csv, "CSV")
    assert len(warnings) == 0
    assert len(items) == 3
    assert items[1].artist == "Daft Punk"
    assert items[1].album == "Random Access Memories"
    assert items[1].track == "Get Lucky"


def test_invalid_import_validation():
    with pytest.raises(ImportValidationError):
        parse_import_content("", "JSON")

    with pytest.raises(ImportValidationError):
        parse_import_content("{broken json", "JSON")

    with pytest.raises(ImportValidationError):
        parse_import_content("wrong_header,col2\nval1,val2", "CSV")


def test_downloadable_templates():
    for fmt in ("csv", "yaml", "json"):
        content, media_type, filename = get_template_content(fmt)
        assert len(content) > 20
        assert filename.endswith(fmt)
        items, _ = parse_import_content(content, fmt)
        assert len(items) >= 3
