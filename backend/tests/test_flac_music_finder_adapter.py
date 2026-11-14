"""Tests for the optional cookie-replay web-index source (flacmusicfinder.top)."""

from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
import pytest
from sqlalchemy.orm import Session

from backend.app.adapters import flac_music_finder as fmf
from backend.app.adapters.registry import adapter_registry
from backend.app.config import settings
from backend.app.services.download_manager import is_trusted_download_url
from backend.app.services.settings_service import (
    SECRET_KEYS,
    get_default_settings_dict,
    get_enabled_sources,
    update_settings,
)

SETTING_KEYS = (
    "flacmusicfinder_enabled",
    "flacmusicfinder_base_url",
    "flacmusicfinder_cookie",
    "flacmusicfinder_search_path",
    "flacmusicfinder_user_agent",
    "flacmusicfinder_max_details",
    "flacmusicfinder_extra_download_hosts",
)

SEARCH_HTML = """
<html><body>
  <div class="searchResult">
    <a href="/music/01/No+Name_-Best+Album_(2019)_%5BFLAC%5D_%5B16-44.1%5D">No Name - Best Album (2019) [FLAC] [16-44.1]</a>
    <b>1.2 GB</b>
  </div>
  <div class="searchResult">
    <a href="/music/02/Sampler_Cat-Single_(2021)_%5BFLAC%5D">Sampler Cat - Single (2021) [FLAC]</a>
  </div>
  <a href="/profile?do=register">Register</a>
  <a href="/rss">RSS</a>
</body></html>
"""

DETAIL_HTML = """
<html><body>
  <img src="/uploads/files/2019/04/best-album-front.jpg" alt="cover">
  <a href="/uploads/files/2019/04/01_-_Track_One.flac">01. Track One [16-44.1]</a> <span>Size: 24.5 MB</span>
  <a href="/uploads/files/2019/04/02_-_Track_Two.flac">02. Track Two</a> <span>Size: 20 MB</span>
  <a href="/engine/download.php?id=42">Download full album</a>
</body></html>
"""

CHALLENGE_HTML = """
<html><head><script>var cid="abc"; function x(){return (![]+[]);}</script></head>
<body><noscript>This page requires JavaScript</noscript></body>
</html>
"""


@pytest.fixture(autouse=True)
def _restore_flacmusicfinder_settings() -> Any:
    snapshot = {key: getattr(settings, key) for key in SETTING_KEYS}
    yield
    for key, value in snapshot.items():
        setattr(settings, key, value)


class _StubHttpx:
    """Replacement for the ``httpx`` module attribute used by the adapter."""

    def __init__(self, responder: Callable[[str], Any]) -> None:
        self.calls: List[Tuple[str, Dict[str, str]]] = []
        self.client_kwargs: List[Dict[str, Any]] = []
        self._responder = responder
        self.AsyncClient = self._build_client_class()

    def _build_client_class(self) -> Any:
        outer = self

        class _Client:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                outer.client_kwargs.append(dict(kwargs))

            async def __aenter__(self) -> "_Client":
                return self

            async def __aexit__(self, *exc: Any) -> bool:
                return False

            async def get(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs: Any) -> Any:
                outer.calls.append((url, dict(headers or {})))
                return outer._responder(url)

        return _Client


def _respond_with(pages: Dict[str, Any], default: Any = None) -> Callable[[str], Any]:
    def responder(url: str) -> Any:
        for fragment, page in pages.items():
            if fragment in url:
                return page
        if default is None:
            raise AssertionError(f"Unexpected request to {url}")
        return default

    return responder


def _page(status: int = 200, text: str = "", content_type: str = "text/html; charset=utf-8") -> Any:
    class _Response:
        def __init__(self) -> None:
            self.status_code = status
            self.text = text
            self.headers = {"Content-Type": content_type}

    return _Response()


def _adapter(base_url: str = "https://fmf.test", cookie: str = "PHPSESSID=abc123; member_id=7") -> fmf.FlacMusicFinderAdapter:
    settings.flacmusicfinder_base_url = base_url
    settings.flacmusicfinder_cookie = cookie
    settings.flacmusicfinder_search_path = ""
    settings.flacmusicfinder_user_agent = ""
    settings.flacmusicfinder_max_details = 5
    settings.flacmusicfinder_extra_download_hosts = ""
    adapter = fmf.FlacMusicFinderAdapter()
    adapter.rate_limit_per_sec = 0.0  # keep unit tests fast
    return adapter


# --- heuristics -----------------------------------------------------------


def test_parse_release_title_reads_scene_quality_hints() -> None:
    parsed = fmf.parse_release_title("No Name - Best Album (2019) [FLAC] [16-44.1]")
    assert parsed["artist"] == "No Name"
    assert parsed["album"] == "Best Album"
    assert parsed["year"] == 2019
    assert parsed["format"] == "FLAC"
    assert parsed["bit_depth"] == 16
    assert parsed["sample_rate"] == 44100


def test_parse_release_title_reads_hi_res_and_24bit_hints() -> None:
    parsed = fmf.parse_release_title("Artist - Hi Res (2020) [24 bit / 96 kHz]")
    assert parsed["bit_depth"] == 24
    assert parsed["sample_rate"] == 96000
    assert parsed["format"] == "FLAC"


def test_size_and_title_filters() -> None:
    assert fmf._size_bytes_from_text("Size: 1.2 GB") == int(1.2 * 1024**3)
    assert fmf.looks_like_release_title("No Name - Best Album (2019) [FLAC]") is True
    assert fmf.looks_like_release_title("Register a new account") is False
    assert fmf.looks_like_release_title("Home") is False


def test_is_challenge_page_detects_jsfuck_gate() -> None:
    assert fmf.is_challenge_page(CHALLENGE_HTML) is True
    assert fmf.is_challenge_page(SEARCH_HTML) is False
    assert fmf.is_challenge_page("") is True


def test_sanitize_cookie_header_flattens_paste() -> None:
    assert fmf.sanitize_cookie_header("  a=1;\n b=2 ;; c=3  ") == "a=1; b=2; c=3"


def test_download_links_only_yields_files() -> None:
    links = dict(fmf.download_links(DETAIL_HTML, "https://fmf.test/music/1.html"))
    assert any(url.endswith("01_-_Track_One.flac") for url in links)
    assert not any("profile" in url for url in links)


# --- search ---------------------------------------------------------------


async def test_search_without_cookie_raises_actionable_error() -> None:
    adapter = _adapter(cookie="")
    with pytest.raises(RuntimeError, match="cookie"):
        await adapter.search(artist="No Name", album="Best Album")


async def test_search_sends_cookie_and_parses_results(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    stub = _StubHttpx(
        _respond_with(
            {
                "/search?": _page(text=SEARCH_HTML),
                "/music/01/": _page(text=DETAIL_HTML),
            },
            default=_page(text="<html><body><a href='/x'>Nothing Here - Album (2000) [MP3]</a></body></html>"),
        )
    )
    monkeypatch.setattr(fmf, "httpx", stub)

    releases = await adapter.search(artist="No Name", album="Best Album", limit=5)

    assert [r.album for r in releases] == ["Best Album", "Single"]
    assert releases[0].source == "flacmusicfinder"
    assert releases[0].artist == "No Name"
    assert releases[0].year == 2019
    assert releases[0].primary_format == "FLAC"
    assert releases[0].is_lossless is True
    assert releases[0].external_id.startswith("fmf_")

    # Second result had no detail page fixture, so it stays a downloadable-unknown hit.
    assert releases[1].download_availability in {"ACCOUNT_REQUIRED", "DIRECT"}

    assert any(headers.get("Cookie") == "PHPSESSID=abc123; member_id=7" for _, headers in stub.calls)
    assert all(headers.get("User-Agent", "").startswith("Mozilla/") for _, headers in stub.calls)


async def test_get_text_strips_cookie_when_redirected_off_site(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    stub = _StubHttpx(lambda url: _page(text="<html><body>empty</body></html>"))
    monkeypatch.setattr(fmf, "httpx", stub)

    await adapter._get_text("https://fmf.test/music/album")

    hooks = stub.client_kwargs[0]["event_hooks"]["request"]
    strip_cookie = hooks[0]

    offsite = httpx.Request("GET", "https://some-file-host.example/file.flac", headers={"Cookie": "PHPSESSID=abc123"})
    await strip_cookie(offsite)
    assert "cookie" not in offsite.headers

    onsite = httpx.Request("GET", "https://fmf.test/uploads/file.flac", headers={"Cookie": "PHPSESSID=abc123"})
    await strip_cookie(onsite)
    assert onsite.headers["Cookie"] == "PHPSESSID=abc123"


async def test_cookie_strip_hook_is_case_insensitive_and_keeps_other_headers() -> None:
    strip_cookie = fmf.cookie_strip_hook("FMF.Test")
    request = httpx.Request(
        "GET",
        "http://fmf.test:8080/search?q=x",
        headers={"Cookie": "a=1", "User-Agent": "test"},
    )
    await strip_cookie(request)
    assert request.headers["Cookie"] == "a=1"

    offsite = httpx.Request("GET", "https://cdn.example/file.flac", headers={"Cookie": "a=1", "Range": "bytes=0-"})
    await strip_cookie(offsite)
    assert "cookie" not in offsite.headers
    assert offsite.headers["Range"] == "bytes=0-"


async def test_cookie_never_survives_a_real_cross_host_redirect() -> None:
    """End-to-end through httpx: the cookie goes to the index, nowhere else."""
    seen: List[Dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        if request.url.host == "fmf.test":
            return httpx.Response(302, headers={"location": "https://cdn.example/file.flac"})
        return httpx.Response(200, text="bytes")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        event_hooks={"request": [fmf.cookie_strip_hook("fmf.test")]},
    ) as client:
        response = await client.get(
            "https://fmf.test/file.flac",
            headers={"Cookie": "PHPSESSID=abc123", "Referer": "https://fmf.test/"},
        )

    assert response.status_code == 200
    assert len(seen) == 2
    assert seen[0]["cookie"] == "PHPSESSID=abc123"
    assert "cookie" not in seen[1]
    assert seen[1]["referer"] == "https://fmf.test/"


async def test_search_attaches_tracks_and_marks_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    stub = _StubHttpx(
        _respond_with(
            {
                "/search?": _page(text=SEARCH_HTML),
                "Best+Album": _page(text=DETAIL_HTML),
            }
        )
    )
    monkeypatch.setattr(fmf, "httpx", stub)

    releases = await adapter.search(artist="No Name", album="Best Album", limit=1)
    release = releases[0]

    assert release.download_availability == "DIRECT"
    assert len(release.tracks) == 2
    assert [t.track_number for t in release.tracks] == [1, 2]
    assert all(t.download_url.startswith("https://fmf.test/uploads/") for t in release.tracks)
    assert release.tracks[0].is_lossless is True
    assert release.total_size_bytes > 0
    assert release.cover_url == "https://fmf.test/uploads/files/2019/04/best-album-front.jpg"
    assert release.bit_depth == 16
    assert release.sample_rate == 44100


async def test_search_raises_when_challenge_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    stub = _StubHttpx(lambda url: _page(text=CHALLENGE_HTML))
    monkeypatch.setattr(fmf, "httpx", stub)

    with pytest.raises(RuntimeError, match="bot challenge"):
        await adapter.search(artist="No Name", album="Best Album")

    # Every candidate search URL was attempted, and none of them solved the challenge.
    assert len(stub.calls) == len(fmf.DEFAULT_SEARCH_PATHS)


async def test_search_reports_rejected_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    monkeypatch.setattr(fmf, "httpx", _StubHttpx(lambda url: _page(status=403, text="Forbidden")))

    with pytest.raises(RuntimeError, match="cookie was rejected"):
        await adapter.search(artist="No Name", album="Best Album")


async def test_search_uses_configured_search_path(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    settings.flacmusicfinder_search_path = "/custom/search?do=search&story={query}"
    monkeypatch.setattr(
        fmf,
        "httpx",
        _StubHttpx(
            _respond_with(
                {
                    "/custom/search": _page(text=SEARCH_HTML),
                    "Best+Album": _page(text=DETAIL_HTML),
                }
            )
        ),
    )

    releases = await adapter.search(album="Best Album", limit=1)
    assert releases
    first_url = releases[0].source_url
    assert first_url.startswith("https://fmf.test/music/")


async def test_search_parses_json_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    payload = (
        '[{"title": "Json Artist - Json Album (2018) [FLAC]", "url": "/r/1",'
        ' "download_url": "/files/json.flac", "image": "/img/1.jpg"}]'
    )
    monkeypatch.setattr(
        fmf,
        "httpx",
        _StubHttpx(
            _respond_with({"/search?": _page(text=payload, content_type="application/json; charset=utf-8")})
        ),
    )

    releases = await adapter.search(album="Json Album", limit=3)
    assert len(releases) == 1
    assert releases[0].download_availability == "DIRECT"
    assert releases[0].tracks[0].download_url == "https://fmf.test/files/json.flac"
    assert releases[0].cover_url == "/img/1.jpg"


# --- download plumbing ----------------------------------------------------


def test_download_hosts_include_index_and_extras() -> None:
    eff = {
        "flacmusicfinder_base_url": "https://fmf.test/path",
        "flacmusicfinder_extra_download_hosts": "cdn.example.com, https://other.example/x y.log",
    }
    hosts = fmf.flacmusicfinder_download_hosts(eff)
    assert "fmf.test" in hosts
    assert "flacmusicfinder.top" in hosts
    assert "cdn.example.com" in hosts
    assert "other.example" in hosts

    assert is_trusted_download_url("https://fmf.test/files/a.flac") is False
    assert is_trusted_download_url("https://fmf.test/files/a.flac", hosts) is True
    assert is_trusted_download_url("https://evil.example/files/a.flac", hosts) is False


def test_download_request_headers_replay_cookie() -> None:
    headers = fmf.download_request_headers(
        {
            "flacmusicfinder_base_url": "https://fmf.test",
            "flacmusicfinder_cookie": "PHPSESSID=abc123",
            "flacmusicfinder_user_agent": "CustomUA/1.0",
        }
    )
    assert headers["Cookie"] == "PHPSESSID=abc123"
    assert headers["User-Agent"] == "CustomUA/1.0"
    assert headers["Referer"] == "https://fmf.test/"

    anonymous = fmf.download_request_headers({"flacmusicfinder_cookie": ""})
    assert "Cookie" not in anonymous
    assert anonymous["User-Agent"] == fmf.DEFAULT_BROWSER_USER_AGENT


# --- wiring ---------------------------------------------------------------


def test_registry_lists_source() -> None:
    assert "flacmusicfinder" in adapter_registry.ids()
    adapter = adapter_registry.get("flacmusicfinder")
    assert adapter is not None
    assert adapter.requires_api_key is False


def test_settings_defaults_secret_masking_and_opt_in(db_session: Session) -> None:
    defaults = get_default_settings_dict()
    for key in SETTING_KEYS:
        assert key in defaults
    assert defaults["flacmusicfinder_enabled"] is False
    assert "flacmusicfinder_cookie" in SECRET_KEYS

    # Off by default: even when listed in enabled_sources it is stripped.
    update_settings(db_session, {"enabled_sources": ["internet_archive", "flacmusicfinder"]})
    assert "flacmusicfinder" not in get_enabled_sources(db_session)

    update_settings(db_session, {"flacmusicfinder_enabled": True})
    assert "flacmusicfinder" in get_enabled_sources(db_session)

    masked = update_settings(db_session, {"flacmusicfinder_cookie": "secret=value"})
    assert masked["flacmusicfinder_cookie"] == "********"
    assert masked["flacmusicfinder_cookie_configured"] is True
