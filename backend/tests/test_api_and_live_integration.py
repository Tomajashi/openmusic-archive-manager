import httpx
from httpx import ASGITransport
import pytest
from backend.app.adapters.internet_archive import InternetArchiveAdapter
from backend.app.adapters.wikimedia import WikimediaCommonsAdapter
from backend.app.main import app


@pytest.mark.asyncio
async def test_fastapi_endpoints():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Healthcheck
        r_health = await client.get("/api/v1/health")
        assert r_health.status_code == 200
        assert r_health.json()["status"] == "healthy"

        # 2. Sources
        r_sources = await client.get("/api/v1/sources")
        assert r_sources.status_code == 200
        source_ids = [s["id"] for s in r_sources.json()]
        assert "internet_archive" in source_ids
        assert "etree" in source_ids
        assert "wikimedia" in source_ids
        assert "jamendo" in source_ids
        assert "musopen" in source_ids
        assert "piratebay" in source_ids

        # 3. Settings secret masking check
        r_set_put = await client.put(
            "/api/v1/settings",
            json={"jamendo_client_id": "super_secret_key_123", "search_concurrency": 6},
        )
        assert r_set_put.status_code == 200
        data_set = r_set_put.json()
        assert data_set["jamendo_client_id"] == "********"
        assert data_set["jamendo_client_id_configured"] is True
        assert data_set["search_concurrency"] == 6

        # 4. Preview & Save Project
        r_prev = await client.post(
            "/api/v1/imports/preview",
            data={
                "raw_content": "artist,album,track\nDaft Punk,Discovery,\nPink Floyd,Animals,\n",
                "format_hint": "CSV",
            },
        )
        assert r_prev.status_code == 200
        assert r_prev.json()["count"] == 2

        r_proj = await client.post(
            "/api/v1/imports/projects",
            json={
                "name": "API Test Project",
                "description": "Created in test",
                "source_format": "CSV",
                "items": r_prev.json()["items"],
            },
        )
        assert r_proj.status_code == 200
        proj_id = r_proj.json()["id"]

        # 5. Dashboard stats
        r_dash = await client.get("/api/v1/dashboard/stats")
        assert r_dash.status_code == 200
        assert r_dash.json()["total_artists_requested"] == 2

        # 6. Templates download
        r_tpl = await client.get("/api/v1/imports/templates/yaml")
        assert r_tpl.status_code == 200
        assert "Daft Punk" in r_tpl.text

        # Cleanup project
        r_del = await client.delete(f"/api/v1/imports/projects/{proj_id}")
        assert r_del.status_code == 200


@pytest.mark.asyncio
async def test_live_archive_api_integration():
    """Run a small number of real API requests if internet access is available."""
    ia = InternetArchiveAdapter()
    wm = WikimediaCommonsAdapter()
    try:
        ia_results = await ia.search(artist="Grateful Dead", album="Cornell", limit=1)
        assert isinstance(ia_results, list)
        if ia_results:
            assert ia_results[0].source == "internet_archive"
            assert len(ia_results[0].tracks) > 0

        wm_results = await wm.search(artist="Bach", track="Tocata", limit=2)
        assert isinstance(wm_results, list)
    except httpx.HTTPError:
        pytest.skip("Network access disabled in current test sandbox; live check skipped.")
