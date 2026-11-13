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

    spotify_content, _, spotify_filename = get_template_content("spotify")
    assert spotify_filename.endswith(".csv")
    sp_items, _ = parse_import_content(spotify_content, "CSV")
    assert len(sp_items) == 2
    assert sp_items[0].artist == "Daft Punk, Pharrell Williams"
    assert sp_items[0].album == "Random Access Memories"
    assert sp_items[0].year == 2013


def test_spotify_exportify_csv_with_repeated_headers_and_escaped_commas():
    spotify_csv = (
        '\ufeff"Track URI","Track Name","Artist URI(s)","Artist Name(s)","Album URI","Album Name",'
        '"Album Artist URI(s)","Album Artist Name(s)","Album Release Date","Album Image URL",'
        '"Disc Number","Track Number","Track Duration (ms)","Track Preview URL","Explicit",'
        '"Popularity","ISRC","Added By","Added At"\n'
        '"spotify:track:3ggtU1ZOKO8ZNiqPNyXGcm","Dinero","spotify:artist:4wP1kxjUsc9IR4Iy2smL7o","Trinidad Cardona","spotify:album:6FfydthOJNOSCM8BeSqKh3","Dinero","spotify:artist:4wP1kxjUsc9IR4Iy2smL7o","Trinidad Cardona","2018-02-02","https://i.scdn.co/image/1","1","1","160880","","true","69","USUM71800195","spotify:user:1","2021-08-09T15:49:11Z"\n'
        '"spotify:track:1","Just the Two of Us","spotify:artist:2","Grover Washington\\, Jr., Bill Withers","spotify:album:3","Winelight","spotify:artist:2","Grover Washington\\, Jr.","1980-06","https://i.scdn.co/image/2","1","2","238000","","false","80","US1","spotify:user:1","2021-08-09T15:50:00Z"\n'
        '"spotify:track:2","September","spotify:artist:3","Earth\\, Wind & Fire","spotify:album:4","The Best Of Earth\\, Wind & Fire Vol. 1","spotify:artist:3","Earth\\, Wind & Fire","1978","https://i.scdn.co/image/3","1","1","215000","","false","85","US2","spotify:user:1","2021-08-09T15:51:00Z"\n'
        '"Track URI","Track Name","Artist URI(s)","Artist Name(s)","Album URI","Album Name","Album Artist URI(s)","Album Artist Name(s)","Album Release Date","Album Image URL","Disc Number","Track Number","Track Duration (ms)","Track Preview URL","Explicit","Popularity","ISRC","Added By","Added At"\n'
        '"spotify:track:3ggtU1ZOKO8ZNiqPNyXGcm","Dinero","spotify:artist:4wP1kxjUsc9IR4Iy2smL7o","Trinidad Cardona","spotify:album:6FfydthOJNOSCM8BeSqKh3","Dinero","spotify:artist:4wP1kxjUsc9IR4Iy2smL7o","Trinidad Cardona","2018-02-02","https://i.scdn.co/image/1","1","1","160880","","true","69","USUM71800195","spotify:user:1","2021-08-09T15:49:11Z"\n'
        '"spotify:track:6qyS9qBy0mEk3qYaH8mPss","Murder In My Mind","spotify:artist:2W6WP4pHQTFlbr2z9S4n54","Kordhell","spotify:album:68GI09qAs2XLJmA3hj5K7y","Murder In My Mind","spotify:artist:2W6WP4pHQTFlbr2z9S4n54","Kordhell","2022-01-21","https://i.scdn.co/image/4","1","1","145000","","true","74","QM4TW2218315","spotify:user:1","2023-10-19T14:20:32Z"\n'
    )
    items, warnings = parse_import_content(spotify_csv, "CSV")
    assert len(items) == 4
    assert items[0].artist == "Trinidad Cardona"
    assert items[0].album == "Dinero"
    assert items[0].track == "Dinero"
    assert items[0].year == 2018

    assert items[1].artist == "Grover Washington, Jr., Bill Withers"
    assert items[1].year == 1980

    assert items[2].artist == "Earth, Wind & Fire"
    assert items[2].album == "The Best Of Earth, Wind & Fire Vol. 1"
    assert items[2].year == 1978

    assert items[3].artist == "Kordhell"
    assert items[3].track == "Murder In My Mind"
    assert items[3].year == 2022

    # Should have reported skipped repeated header and duplicate row
    assert any("repeated header" in w.lower() for w in warnings)
    assert any("duplicate" in w.lower() for w in warnings)


def test_semicolon_and_tunemymusic_csv_variants():
    semi_csv = (
        "Track Name;Artist Name;Album Title;Release Date\n"
        "Don't Stop The Music;Rihanna;Good Girl Gone Bad: Reloaded;2008-06-02\n"
        "Just Dance;Lady Gaga, Colby O'Donis;The Fame;2008-01-01\n"
    )
    items, warnings = parse_import_content(semi_csv, "CSV")
    assert len(warnings) == 0
    assert len(items) == 2
    assert items[0].artist == "Rihanna"
    assert items[0].album == "Good Girl Gone Bad: Reloaded"
    assert items[0].track == "Don't Stop The Music"
    assert items[0].year == 2008
    assert items[1].artist == "Lady Gaga, Colby O'Donis"
    assert items[1].track == "Just Dance"


def test_extract_primary_artist_and_multi_artist_scoring():
    from backend.app.services.search_engine import compute_match_score, extract_primary_artist

    assert extract_primary_artist("Lady Gaga, Colby O'Donis") == "Lady Gaga"
    assert extract_primary_artist("Grover Washington, Jr., Bill Withers") == "Grover Washington, Jr."
    assert extract_primary_artist("Earth, Wind & Fire") == "Earth, Wind & Fire"
    assert extract_primary_artist("S3BZS, Dragon Boys, DJ FKU") == "S3BZS"

    score = compute_match_score(
        query_artist="Lady Gaga, Colby O'Donis",
        query_album="The Fame",
        query_track="Just Dance",
        result_artist="Lady Gaga",
        result_album="The Fame",
        result_tracks=["Just Dance"],
    )
    assert score == 1.0
