from typing import Any, Dict
import pytest
from sqlalchemy.orm import Session
from backend.app.adapters.etree import EtreeAdapter
from backend.app.adapters.internet_archive import InternetArchiveAdapter
from backend.app.adapters.jamendo import JamendoAdapter
from backend.app.adapters.musopen import MusopenAdapter
from backend.app.adapters.piratebay import PirateBayAdapter
from backend.app.adapters.registry import adapter_registry
from backend.app.adapters.wikimedia import WikimediaCommonsAdapter
from backend.app.models import ImportItem, ImportProject, SearchResult
from backend.app.services.search_engine import (
    build_duplicate_group_key,
    compute_match_score,
    search_engine,
)


@pytest.mark.asyncio
async def test_internet_archive_and_etree_adapters(monkeypatch):
    ia = InternetArchiveAdapter()
    et = EtreeAdapter()
    assert issubclass(EtreeAdapter, InternetArchiveAdapter)

    async def fake_get_json(url: str, params: Dict[str, Any] | None = None, **kwargs):
        if "advancedsearch.php" in url:
            return {
                "response": {
                    "docs": [
                        {
                            "identifier": "gd1977-05-08.sbd.flac16",
                            "title": "Cornell 1977-05-08",
                            "creator": "Grateful Dead",
                            "year": "1977",
                            "licenseurl": "https://creativecommons.org/licenses/by-nc-nd/3.0/",
                        }
                    ]
                }
            }
        return {
            "metadata": {
                "title": "Cornell 1977-05-08",
                "creator": "Grateful Dead",
                "date": "1977-05-08",
                "venue": "Barton Hall",
                "coverage": "Ithaca, NY",
                "source": "SBD > Reel > FLAC",
            },
            "files": [
                {
                    "name": "gd77-05-08d1t01.flac",
                    "format": "Flac",
                    "size": "35000000",
                    "length": "312.5",
                    "title": "Scarlet Begonias",
                    "track": "1",
                    "md5": "d41d8cd98f00b204e9800998ecf8427e",
                },
                {
                    "name": "gd77-05-08d1t01_vbr.mp3",
                    "format": "VBR MP3",
                    "size": "8000000",
                    "length": "312.5",
                    "title": "Scarlet Begonias",
                    "track": "1",
                },
            ],
        }

    monkeypatch.setattr(ia, "_get_json", fake_get_json)
    monkeypatch.setattr(et, "_get_json", fake_get_json)

    ia_res = await ia.search(artist="Grateful Dead", album="Cornell 1977-05-08")
    assert len(ia_res) == 1
    assert ia_res[0].is_lossless is True
    assert ia_res[0].primary_format == "FLAC"
    assert len(ia_res[0].tracks) == 1  # Deduplicated _vbr.mp3 derivative in favor of FLAC
    assert ia_res[0].tracks[0].checksum_md5 == "d41d8cd98f00b204e9800998ecf8427e"

    et_res = await et.search(artist="Grateful Dead", album="Cornell")
    assert len(et_res) == 1
    assert et_res[0].source == "etree"
    assert et_res[0].extra_metadata["venue"] == "Barton Hall"


@pytest.mark.asyncio
async def test_wikimedia_jamendo_musopen_and_piratebay_adapters(monkeypatch):
    wm = WikimediaCommonsAdapter()

    async def fake_wm_json(url: str, params=None, **kwargs):
        return {
            "query": {
                "pages": {
                    "101": {
                        "title": "File:Bach_Goldberg_Aria.flac",
                        "imageinfo": [
                            {
                                "url": "https://upload.wikimedia.org/wikipedia/commons/a/a1/Bach_Goldberg_Aria.flac",
                                "size": 19500000,
                                "mime": "audio/flac",
                                "sha1": "abc123456789",
                                "user": "KimikoIshizaka",
                                "extmetadata": {
                                    "Artist": {"value": "Johann Sebastian Bach"},
                                    "LicenseShortName": {"value": "CC Zero"},
                                },
                            }
                        ],
                    }
                }
            }
        }

    monkeypatch.setattr(wm, "_get_json", fake_wm_json)
    wm_res = await wm.search(artist="Johann Sebastian Bach", album="Goldberg Variations")
    assert len(wm_res) == 1
    assert wm_res[0].primary_format == "FLAC"
    assert wm_res[0].is_lossless is True

    # Jamendo adapter
    jm = JamendoAdapter()

    async def fake_jm_json(url: str, params=None, **kwargs):
        return {
            "results": [
                {
                    "id": "555",
                    "name": "Discovery Sessions",
                    "artist_name": "Indie Synth",
                    "releasedate": "2023-04-01",
                    "image": "https://img.jamendo.com/albums/555.jpg",
                    "tracks": [
                        {
                            "id": "9001",
                            "position": "1",
                            "name": "Sunrise Synth",
                            "duration": "215",
                            "audiodlallowed": True,
                            "audiodownload": "https://prod-1.storage.jamendo.com/download/track/9001/flac/",
                            "license_ccurl": "https://creativecommons.org/licenses/by/4.0/",
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(jm, "_get_json", fake_jm_json)
    jm_res = await jm.search(artist="Indie Synth", album="Discovery Sessions", client_id="test_cid")
    assert len(jm_res) == 1
    assert jm_res[0].is_lossless is True
    assert jm_res[0].primary_format == "FLAC"

    # PirateBay adapter
    pb = PirateBayAdapter()

    async def fake_pb_json(url: str, params=None, **kwargs):
        if "f.php" in url:
            return [["01 - One More Time.flac", 38500000], ["02 - Aerodynamic.flac", 32100000]]
        return [
            {
                "id": "888111",
                "name": "Daft Punk - Discovery (2001) [24bit FLAC]",
                "info_hash": "1122334455667788990011223344556677889900",
                "leechers": "4",
                "seeders": "42",
                "num_files": "14",
                "size": "520000000",
                "username": "audiophile",
                "status": "vip",
                "category": "104",
            }
        ]

    monkeypatch.setattr(pb, "_get_json", fake_pb_json)
    pb_res = await pb.search(artist="Daft Punk", album="Discovery")
    assert len(pb_res) == 1
    assert pb_res[0].source == "piratebay"
    assert pb_res[0].is_lossless is True
    assert pb_res[0].bit_depth == 24
    assert pb_res[0].seeders == 42
    assert pb_res[0].magnet_uri.startswith("magnet:?xt=urn:btih:11223344556677889900")
    assert len(pb_res[0].tracks) == 2

    # Musopen adapter
    mo = MusopenAdapter()

    async def fake_mo_search(*args, **kwargs):
        return []

    monkeypatch.setattr(InternetArchiveAdapter, "search", fake_mo_search)
    mo_res = await mo.search(artist="Beethoven", album="Symphony No. 9")
    assert len(mo_res) == 1
    assert mo_res[0].download_availability == "ACCOUNT_REQUIRED"


@pytest.mark.asyncio
async def test_search_engine_duplicates_missing_results_and_project_batch(
    db_session: Session, monkeypatch
):
    # Create project with multiple artists, several albums, and an individual track
    proj = ImportProject(name="Test Batch", source_format="JSON")
    db_session.add(proj)
    db_session.flush()
    db_session.add_all(
        [
            ImportItem(project_id=proj.id, artist="Daft Punk", album="Discovery", track=""),
            ImportItem(project_id=proj.id, artist="Daft Punk", album="Discovery", track="One More Time"),
            ImportItem(project_id=proj.id, artist="Nonexistent ArtistXYZ", album="Missing Album", track=""),
        ]
    )
    db_session.commit()

    # Mock Internet Archive and PirateBay to both return "Daft Punk - Discovery" (duplicate release across sources)
    # and make Wikimedia raise an exception to verify graceful handling of unavailable sources.
    ia_adapter = adapter_registry.get("internet_archive")
    pb_adapter = adapter_registry.get("piratebay")
    wm_adapter = adapter_registry.get("wikimedia")

    from backend.app.adapters.base import NormalizedRelease, NormalizedTrack

    async def mock_ia_search(artist="", album="", track="", limit=8):
        if "Nonexistent" in artist:
            return []
        return [
            NormalizedRelease(
                external_id="ia_discovery",
                source="internet_archive",
                artist="Daft Punk",
                album="Discovery (Remastered)",
                year=2001,
                primary_format="FLAC",
                available_formats=["FLAC"],
                is_lossless=True,
                track_count=4,
                total_size_bytes=350_000_000,
                tracks=[
                    NormalizedTrack(
                        track_number=1,
                        title="One More Time",
                        format="FLAC",
                        is_lossless=True,
                        size_bytes=40_000_000,
                        download_url="https://archive.org/download/ia_discovery/01.flac",
                    )
                ],
            )
        ]

    async def mock_pb_search(artist="", album="", track="", limit=8):
        if "Nonexistent" in artist:
            return []
        return [
            NormalizedRelease(
                external_id="pb_discovery",
                source="piratebay",
                artist="Daft Punk",
                album="Discovery",
                year=2001,
                primary_format="FLAC",
                available_formats=["FLAC"],
                is_lossless=True,
                track_count=4,
                total_size_bytes=360_000_000,
                download_availability="MAGNET",
                magnet_uri="magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678",
                tracks=[
                    NormalizedTrack(
                        track_number=1,
                        title="One More Time",
                        format="FLAC",
                        is_lossless=True,
                        size_bytes=40_000_000,
                    )
                ],
            )
        ]

    async def mock_unavailable_search(*args, **kwargs):
        raise RuntimeError("Simulated source timeout")

    monkeypatch.setattr(ia_adapter, "search", mock_ia_search)
    monkeypatch.setattr(pb_adapter, "search", mock_pb_search)
    monkeypatch.setattr(wm_adapter, "search", mock_unavailable_search)

    job = await search_engine.start_async_search_job(
        db=db_session,
        project_id=proj.id,
        sources=["internet_archive", "piratebay", "wikimedia"],
        wait_for_completion=True,
    )

    assert job.status == "COMPLETED"
    results = db_session.query(SearchResult).filter(SearchResult.search_job_id == job.id).all()
    assert len(results) == 2

    # Both releases from different sources share the exact same duplicate_group_key
    assert results[0].duplicate_group_key == build_duplicate_group_key("Daft Punk", "Discovery")
    assert results[0].duplicate_group_key == results[1].duplicate_group_key
    assert compute_match_score("Daft Punk", "Discovery", "", "Daft Punk", "Discovery", []) == 1.0
