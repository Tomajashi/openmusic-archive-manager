"""FLAC Music Finder (https://flacmusicfinder.top/) source adapter.

The site is served by Apache behind Cloudflare and gates every page behind an
app-level JavaScript bot challenge, so this adapter deliberately:

* never tries to solve, emulate or bypass the challenge -- it simply replays the
  session cookie that **you** copied from your own browser
  (Settings -> FLAC Music Finder -> Browser Cookie);
* tries a configurable list of search URLs and accepts the first response that
  is not the challenge page;
* parses a JSON payload when the site returns one and otherwise falls back to
  defensive HTML heuristics (stdlib ``html.parser`` + regex, no new dependency);
* returns an empty result list (or raises an actionable error) instead of
  guessing when the markup is not understood.

The upstream markup is not documented and cannot be inspected from automation
environments, so treat the HTML parsing below as best-effort heuristics.
"""

import asyncio
import hashlib
import json
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx

from backend.app.adapters.base import (
    BaseSourceAdapter,
    NormalizedRelease,
    NormalizedTrack,
    extract_year,
    is_lossless_format,
    normalize_format_name,
)
from backend.app.config import settings
from backend.app.services.logger_service import log_event

DEFAULT_BASE_URL = "https://flacmusicfinder.top"

DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Search URL templates tried in order when ``flacmusicfinder_search_path`` is empty.
# ``{query}`` is replaced with the URL-encoded search terms.
DEFAULT_SEARCH_PATHS: Tuple[str, ...] = (
    "/search?q={query}",
    "/search/{query}",
    "/index.php?do=search&subaction=dload&story={query}",
    "/?q={query}",
)

AUDIO_EXTENSIONS: Tuple[str, ...] = (
    ".flac",
    ".wav",
    ".wave",
    ".alac",
    ".aiff",
    ".ape",
    ".wv",
    ".mp3",
    ".ogg",
    ".opus",
    ".m4a",
    ".m4b",
)

# Whole-album bundles: downloadable, but they must be unpacked before playback.
ARCHIVE_EXTENSIONS: Tuple[str, ...] = (".zip", ".rar", ".7z", ".tar", ".gz")

# Fragments that identify the JavaScript bot-challenge / interstitial page.
_CHALLENGE_MARKERS: Tuple[str, ...] = (
    "var cid=",
    "requires javascript",
    "(![]+[])",
    "just a moment...",
    "checking your browser",
    "cf-chl-",
    "cf_chl_opt",
    "_cf_chl_",
    "unusual access patterns",
    "enable javascript and reload",
)

_LOGIN_HINTS = (
    "please login",
    "please log in",
    "please register",
    "registration required",
    "only registered users",
    "sign up to download",
)

_TITLE_SPLIT = re.compile(r"\s+-\s+")
_BRACKET_GROUP = re.compile(r"[\[(][^\]{}]*[\])]")
_AUDIO_EXT_RE = re.compile(
    r"(?:" + "|".join(re.escape(ext) for ext in AUDIO_EXTENSIONS) + r")\b",
    re.I,
)
_SIZE_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(GB|MB|KB)\b", re.I)
_TRACK_NUM_RE = re.compile(r"^\s*(\d{1,2})\s*[._)-]\s+")
_KHZ_RE = re.compile(r"(\d{2,3}[.,]\d|\d{4,5}|\d{2,3})\s*k\s?hz", re.I)
# Scene-style combined hint, e.g. "[16-44.1]" or "24/96".
_BITS_RATE_RE = re.compile(
    r"(?<![\d.])(8|16|20|24|32)\s*[-_/x]\s*"
    r"(22[.,]05|44[.,]1|88[.,]2|176[.,]4|352[.,]8|384|192|96|48|24)(?![\d.])",
    re.I,
)

_NOISE_WORDS = (
    "register",
    "sign in",
    "sign up",
    "log in",
    "login",
    "password",
    "forgot",
    "contact",
    "privacy",
    "terms",
    "dmca",
    "javascript",
    "rss",
    "sitemap",
    "advertisement",
)


def cookie_strip_hook(origin_host: str):
    """Build an ``httpx`` request event hook that keeps the session cookie on-site.

    The replayed cookie authenticates the web index only, so it is deleted from any
    request that leaves ``origin_host`` (e.g. a redirect to a third-party file host).
    """
    # ``hostname`` / httpx ``host`` already lowercase; brackets cover IPv6 literals.
    def normalize(value: str) -> str:
        return (value or "").strip().strip("[]").lower()

    origin = normalize(origin_host)

    async def drop_cookie_on_cross_host_redirect(request: httpx.Request) -> None:
        if not origin:
            return
        if normalize(request.url.host) != origin and "cookie" in request.headers:
            del request.headers["Cookie"]

    return drop_cookie_on_cross_host_redirect


def sanitize_cookie_header(cookie: str) -> str:
    """Collapse a pasted cookie string into a single safe ``Cookie`` header value."""
    cleaned = re.sub(r"[\r\n\t]+", " ", cookie or "").strip()
    if cleaned.lower().startswith("cookie:"):
        cleaned = cleaned.split(":", 1)[1].strip()
    pairs = [part.strip() for part in cleaned.split(";")]
    return "; ".join(part for part in pairs if part)


def is_challenge_page(text: str) -> bool:
    """True when the body looks like the bot challenge instead of real content."""
    if not text:
        return True
    low = text.lower()
    if any(marker in low for marker in _CHALLENGE_MARKERS):
        return True
    # A page with no links and a "loading" style message is the gate.
    return "<a " not in low and ("loading" in low or "please wait" in low)


def _bit_depth(text: str) -> Optional[int]:
    low = (text or "").lower()
    if re.search(r"24\s*-?\s*bit|24bit", low):
        return 24
    if re.search(r"32\s*-?\s*bit|32bit", low):
        return 32
    if re.search(r"16\s*-?\s*bit|16bit", low):
        return 16
    if match := _BITS_RATE_RE.search(low):
        return int(match.group(1))
    return None


def _sample_rate(text: str) -> Optional[int]:
    match = _KHZ_RE.search(text or "")
    if match:
        try:
            value = float(match.group(1).replace(",", "."))
        except ValueError:
            return None
        return int(round(value * 1000))
    if pair := _BITS_RATE_RE.search(text or ""):
        try:
            value = float(pair.group(2).replace(",", "."))
        except ValueError:
            return None
        return int(round(value * 1000))
    return None


def _size_str(html: str, url: str) -> str:
    """Human-readable size found near the given link inside the page markup."""
    if not html or not url:
        return ""
    key = unquote(urlparse(url).path).rsplit("/", 1)[-1].lower()
    if not key:
        return ""
    pos = html.lower().find(key)
    if pos < 0:
        return ""
    window = html[max(0, pos - 300): pos + len(key) + 300]
    if match := _SIZE_RE.search(window):
        return match.group(0)
    return ""


def _size_bytes(html: str, url: str) -> int:
    text = _size_str(html, url)
    if not text:
        return 0
    match = re.match(r"([\d.,]+)\s*(B|KB|MB|GB|TB)", text, re.I)
    if not match:
        return 0
    units = {"b": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3, "tb": 1024 ** 4}
    try:
        return int(float(match.group(1).replace(",", ".")) * units[match.group(2).lower()])
    except (TypeError, ValueError, KeyError):
        return 0


def _format_from_text(text: str) -> str:
    low = (text or "").lower()
    if "flac" in low or "lossless" in low:
        return "FLAC"
    if "wav" in low or "wave" in low or "pcm" in low:
        return "WAV"
    if "alac" in low or "apple lossless" in low:
        return "ALAC"
    if "opus" in low:
        return "OPUS"
    if "ogg" in low or "vorbis" in low:
        return "OGG"
    if "m4a" in low or "aac" in low:
        return "AAC"
    if "mp3" in low or "320kbps" in low or "320 kbps" in low:
        return "MP3"
    return ""


def _size_bytes_from_text(text: str) -> int:
    match = _SIZE_RE.search(text or "")
    if not match:
        return 0
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        return 0
    multiplier = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}[match.group(2).upper()]
    return int(value * multiplier)


def parse_release_title(text: str) -> Dict[str, Any]:
    """Best-effort parse of an ``Artist - Album (Year) [FLAC] [16-44.1]`` style title."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    tags = " ".join(_BRACKET_GROUP.findall(raw))
    core = _BRACKET_GROUP.sub(" ", raw)
    core = re.sub(r"\s+", " ", core).strip(" -\u2013\u2014,.|/")

    year = extract_year(raw)
    if year:
        core = re.sub(rf"\(?\b{year}\b\)?", " ", core)
    core = re.sub(r"\s+", " ", core).strip(" -\u2013\u2014,.|/")

    fmt = normalize_format_name(_format_from_text(tags) or _format_from_text(core) or "FLAC")

    track_number = 1
    track_match = _TRACK_NUM_RE.match(core)
    if track_match:
        track_number = max(1, int(track_match.group(1)))
        core = core[track_match.end():]

    if _TITLE_SPLIT.search(core):
        artist, album = (part.strip() for part in _TITLE_SPLIT.split(core, maxsplit=1))
    elif "-" in core:
        artist, album = (part.strip() for part in core.split("-", 1))
    else:
        artist, album = "", core

    title = album or raw
    return {
        "artist": artist,
        "album": album or raw,
        "year": year,
        "format": fmt,
        "bit_depth": _bit_depth(raw),
        "sample_rate": _sample_rate(raw),
        "track_number": track_number,
        "title": title,
        "size_bytes": _size_bytes_from_text(raw),
    }


def looks_like_release_title(text: str) -> bool:
    text = (text or "").strip()
    if len(text) < 8 or len(text) > 250 or "-" not in text:
        return False
    low = text.lower()
    if any(word in low for word in _NOISE_WORDS):
        return False
    return bool(
        _BRACKET_GROUP.search(text)
        or extract_year(text)
        or _AUDIO_EXT_RE.search(text)
        or _format_from_text(text)
    )


class _LinkCollector(HTMLParser):
    """Collect ``<a href>`` targets together with their visible text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: List[Tuple[str, str]] = []
        self._href: Optional[str] = None
        self._fallback = ""
        self._buffer: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag != "a":
            return
        attr_map = {str(key).lower(): (value or "") for key, value in attrs}
        self._href = attr_map.get("href") or attr_map.get("data-href") or ""
        self._fallback = attr_map.get("title") or attr_map.get("alt") or ""
        self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._href is None:
            return
        text = " ".join("".join(self._buffer).split()) or self._fallback.strip()
        self.links.append((self._href.strip(), text))
        self._href = None


def extract_links(html: str) -> List[Tuple[str, str]]:
    collector = _LinkCollector()
    try:
        collector.feed(html or "")
        collector.close()
    except Exception:
        return []
    return collector.links


def extract_cover_url(html: str, base_url: str) -> str:
    match = re.search(
        r"<img[^>]+src=[\"']([^\"']*(?:cover|folder|front|album|art)[^\"']*)[\"']",
        html or "",
        re.I,
    )
    if not match:
        return ""
    return urljoin(base_url, match.group(1))


def _is_asset_link(href: str) -> bool:
    low = (href or "").lower()
    if low.startswith(("javascript:", "#", "mailto:", "tel:", "data:", "about:", "/#")):
        return True
    return low in {"", "/"}


def looks_logged_out(html: str) -> bool:
    low = (html or "").lower()
    return any(hint in low for hint in _LOGIN_HINTS)


def download_links(html: str, base_url: str) -> List[Tuple[str, str]]:
    """Return ``(url, label)`` pairs for files a visitor can actually download."""
    out: List[Tuple[str, str]] = []
    seen = set()
    for href, text in extract_links(html):
        if _is_asset_link(href):
            continue
        absolute = urljoin(base_url, href)
        if urlparse(absolute).scheme not in {"http", "https"} or absolute in seen:
            continue
        path = urlparse(absolute).path.lower()
        is_file = path.endswith(AUDIO_EXTENSIONS + ARCHIVE_EXTENSIONS)
        is_dload = any(
            token in absolute.lower() for token in ("dload", "getfile", "engine/download", "download")
        )
        if not (is_file or (is_dload and text)):
            continue
        seen.add(absolute)
        label = text or path.rsplit("/", 1)[-1]
        out.append((absolute, label))
    return out


class FlacMusicFinderAdapter(BaseSourceAdapter):
    """Optional cookie-enabled web-index source for flacmusicfinder.top (off by default)."""

    source_id = "flacmusicfinder"
    source_name = "FLAC Music Finder"
    website = "https://flacmusicfinder.top/"
    priority = "Optional (Web Index)"
    supports_albums = True
    supports_tracks = True
    supports_direct_lossless = True
    requires_api_key = False
    description = (
        "Cookie-enabled search of the flacmusicfinder.top FLAC web index. Replays a session cookie copied "
        "from your own browser to get past the site's JavaScript bot challenge, then parses the result "
        "markup and collects per-file download links."
    )
    limitations = (
        "Unofficial index of commercial releases: verify item rights in your jurisdiction and rely on the "
        "built-in FFprobe lossless verifier. The site sits behind Cloudflare and serves a JavaScript bot "
        "challenge to visitors without a valid session cookie; this adapter never bypasses that challenge, so "
        "you must paste a fresh browser cookie in Settings -> FLAC Music Finder. Parsing is heuristic: after a "
        "site redesign search may return nothing until the markup is mapped again. Album bundles (.zip/.rar) "
        "are downloaded as-is and must be unpacked before playback."
    )
    rate_limit_per_sec = 0.5

    # --- settings helpers -------------------------------------------------

    def get_base_url(self) -> str:
        return (settings.flacmusicfinder_base_url or DEFAULT_BASE_URL).rstrip("/")

    def get_cookie(self) -> str:
        return sanitize_cookie_header(str(getattr(settings, "flacmusicfinder_cookie", "") or ""))

    def get_user_agent(self) -> str:
        return str(getattr(settings, "flacmusicfinder_user_agent", "") or "").strip() or DEFAULT_BROWSER_USER_AGENT

    def _headers(self, referer: str = "") -> Dict[str, str]:
        headers = {
            "User-Agent": self.get_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        cookie = self.get_cookie()
        if cookie:
            headers["Cookie"] = cookie
        if referer:
            headers["Referer"] = referer
        return headers

    def _candidate_urls(self, query: str) -> List[str]:
        base = self.get_base_url()
        encoded = quote(query)
        templates: List[str] = []
        custom = str(getattr(settings, "flacmusicfinder_search_path", "") or "").strip()
        if custom:
            templates.append(custom if "{query}" in custom else f"{custom}{{query}}")
        templates.extend(DEFAULT_SEARCH_PATHS)

        urls: List[str] = []
        for template in templates:
            rendered = template.replace("{query}", encoded)
            url = rendered if rendered.startswith("http") else urljoin(base + "/", rendered.lstrip("/"))
            if url not in urls:
                urls.append(url)
        return urls

    # --- HTTP -------------------------------------------------------------

    async def _get_text(
        self,
        url: str,
        referer: str = "",
        max_retries: int = 2,
        timeout: float = 25.0,
    ) -> Tuple[int, str, str]:
        """Return ``(status_code, body_text, content_type)`` with light retry/backoff.

        The replayed session cookie is stripped from any redirect that leaves the index host.
        """
        headers = self._headers(referer)
        backoff = 2.0
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            await self._throttle()
            try:
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=True,
                    event_hooks={"request": [cookie_strip_hook(urlparse(url).hostname or "")]},
                ) as client:
                    response = await client.get(url, headers=headers)
                content_type = response.headers.get("Content-Type", "")
                if response.status_code in {429, 500, 502, 503, 504} and attempt < max_retries - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                return response.status_code, response.text, content_type
            except Exception as exc:  # network / TLS / edge resets
                last_exc = exc
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
        raise last_exc if last_exc else RuntimeError(f"Request to {url} failed")

    # --- heuristic parsing ------------------------------------------------

    def _build_release(self, title: str, source_url: str, download_url: str = "") -> Optional[NormalizedRelease]:
        parsed = parse_release_title(title)
        artist = str(parsed.get("artist") or "").strip()
        album = str(parsed.get("album") or "").strip() or str(title).strip()
        if not album:
            return None

        fmt = str(parsed.get("format") or "FLAC")
        lossless = bool(is_lossless_format(fmt))
        bit_depth = parsed.get("bit_depth")
        sample_rate = parsed.get("sample_rate")
        size_bytes = int(parsed.get("size_bytes") or 0)
        track_number = int(parsed.get("track_number") or 1)

        tracks: List[NormalizedTrack] = []
        if download_url:
            tracks.append(
                NormalizedTrack(
                    track_number=track_number,
                    title=str(parsed.get("title") or album),
                    format=fmt,
                    is_lossless=lossless,
                    size_bytes=size_bytes,
                    bit_depth=bit_depth if lossless else None,
                    sample_rate=sample_rate,
                    download_url=download_url,
                )
            )

        quality_label = (
            f"{bit_depth}-bit / {sample_rate / 1000:.1f} kHz ({fmt})"
            if lossless and bit_depth and sample_rate
            else fmt
        )

        return NormalizedRelease(
            external_id="fmf_" + hashlib.md5((source_url or title).encode("utf-8")).hexdigest()[:16],
            source=self.source_id,
            artist=(artist or "Unknown Artist")[:250],
            album=album[:250],
            primary_format=fmt,
            is_lossless=lossless,
            year=parsed.get("year"),
            cover_url="",
            available_formats=[fmt],
            quality_label=quality_label,
            bit_depth=bit_depth if lossless else None,
            sample_rate=sample_rate,
            track_count=len(tracks) or 1,
            total_size_bytes=size_bytes,
            license="Unverified web index \u2014 verify rights before downloading",
            source_url=source_url,
            download_availability="DIRECT" if download_url else "ACCOUNT_REQUIRED",
            extra_metadata={
                "search_title": title,
                "parse": "heuristic",
                "site": self.get_base_url(),
            },
            tracks=tracks,
        )

    def _releases_from_json(self, payload: object, limit: int) -> List[NormalizedRelease]:
        if isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    payload = value
                    break
            else:
                payload = [payload]
        if not isinstance(payload, list):
            return []

        releases: List[NormalizedRelease] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            flat = {key.lower(): val for key, val in item.items()}

            def pick(*keys: str) -> str:
                for key in keys:
                    value = flat.get(key)
                    if isinstance(value, (str, int)) and str(value).strip():
                        return str(value).strip()
                return ""

            title = pick("title", "name", "artist_album", "release", "artist")
            if not title:
                continue
            page_url = pick("url", "link", "slug", "href")
            download_url = pick("download_url", "file_url", "dload", "url_file")
            base = self.get_base_url() + "/"
            if page_url:
                page_url = urljoin(base, page_url)
            if download_url:
                download_url = urljoin(base, download_url)
            release = self._build_release(title=title, source_url=page_url, download_url=download_url)
            if not release:
                continue
            if artist := pick("artist"):
                release.artist = artist[:250]
            if album := pick("album"):
                release.album = album[:250]
            if year_value := pick("year", "date"):
                release.year = extract_year(year_value) or release.year
            if image := pick("image", "cover", "thumb", "artwork"):
                release.cover_url = image
            releases.append(release)
            if len(releases) >= max(1, limit):
                break
        return releases

    def _releases_from_html(self, html: str, page_url: str, limit: int) -> List[NormalizedRelease]:
        releases: List[NormalizedRelease] = []
        seen = set()
        for href, text in extract_links(html):
            title = re.sub(r"\s+", " ", text).strip(" -_\u2013\u2014|")
            if not title or _is_asset_link(href):
                continue
            if not looks_like_release_title(title):
                continue
            absolute = urljoin(page_url, href)
            if urlparse(absolute).scheme not in {"http", "https"}:
                continue
            if absolute in seen:
                continue
            release = self._build_release(title=title, source_url=absolute)
            if not release:
                continue
            seen.add(absolute)
            releases.append(release)
            if len(releases) >= max(1, limit):
                break
        return releases

    async def _attach_tracks(
        self,
        releases: List[NormalizedRelease],
    ) -> None:
        """Open each result page and turn the file links it exposes into downloadable tracks."""
        if not releases:
            return
        try:
            configured = int(getattr(settings, "flacmusicfinder_max_details", 5) or 5)
        except (TypeError, ValueError):
            configured = 5
        detail_limit = max(0, min(20, configured))
        base = self.get_base_url()

        for release in releases[:detail_limit]:
            page_url = release.source_url
            if not page_url:
                continue
            try:
                status, html, _content_type = await self._get_text(page_url, referer=base + "/")
            except Exception:
                continue
            if status != 200 or is_challenge_page(html) or looks_logged_out(html):
                continue

            if not release.cover_url:
                release.cover_url = extract_cover_url(html, page_url)

            files = download_links(html, page_url)
            audio_files = [
                (url, label)
                for url, label in files
                if urlparse(url).path.lower().endswith(AUDIO_EXTENSIONS)
            ]
            bundle = next(
                (entry for entry in files if entry[0].lower().split("?")[0].endswith(ARCHIVE_EXTENSIONS)),
                None,
            )

            if audio_files:
                tracks: List[NormalizedTrack] = []
                total_bytes = 0
                formats: List[str] = []
                for index, (url, label) in enumerate(audio_files, start=1):
                    filename = unquote(urlparse(url).path.rsplit("/", 1)[-1])
                    raw_title = _TITLE_SPLIT.split(label, maxsplit=1)[-1] if _TITLE_SPLIT.search(label) else label
                    title = (raw_title or filename).strip(" -_\u2013") or filename
                    fmt = normalize_format_name(
                        _format_from_text(filename)
                        or _format_from_text(label)
                        or release.primary_format
                        or "FLAC"
                    )
                    number_match = _TRACK_NUM_RE.match(filename)
                    size_bytes = _size_bytes(html, url)
                    total_bytes += size_bytes
                    if fmt not in formats:
                        formats.append(fmt)
                    tracks.append(
                        NormalizedTrack(
                            track_number=int(number_match.group(1)) if number_match else index,
                            title=title[:250],
                            format=fmt,
                            is_lossless=is_lossless_format(fmt),
                            size_bytes=size_bytes,
                            bit_depth=_bit_depth(label) or _bit_depth(filename) or release.bit_depth,
                            sample_rate=_sample_rate(label) or _sample_rate(filename) or release.sample_rate,
                            download_url=url,
                        )
                    )

                release.tracks = tracks
                release.track_count = len(tracks)
                release.available_formats = formats or release.available_formats
                release.primary_format = formats[0] if formats else release.primary_format
                release.is_lossless = any(track.is_lossless for track in tracks)
                release.bit_depth = next((t.bit_depth for t in tracks if t.bit_depth), release.bit_depth)
                release.sample_rate = next((t.sample_rate for t in tracks if t.sample_rate), release.sample_rate)
                if total_bytes:
                    release.total_size_bytes = total_bytes
                release.download_availability = "DIRECT"
                release.magnet_uri = ""
                continue

            if bundle:
                bundle_url, bundle_label = bundle
                release.tracks = [
                    NormalizedTrack(
                        track_number=1,
                        title=(bundle_label or release.album)[:250],
                        format=release.primary_format,
                        is_lossless=release.is_lossless,
                        size_bytes=_size_bytes(html, bundle_url) or release.total_size_bytes,
                        bit_depth=release.bit_depth,
                        sample_rate=release.sample_rate,
                        download_url=bundle_url,
                    )
                ]
                release.track_count = max(1, release.track_count)
                release.download_availability = "DIRECT"
                release.extra_metadata["download_kind"] = "ARCHIVE"
                release.extra_metadata["archive_url"] = bundle_url
                release.extra_metadata["note"] = (
                    "Album archive (.zip/.rar/...) from the FLAC Music Finder web index: unpack it and "
                    "import the audio files before playback."
                )

    # --- public API -------------------------------------------------------

    async def search(
        self,
        artist: str = "",
        album: str = "",
        track: str = "",
        limit: int = 10,
    ) -> List[NormalizedRelease]:
        artist, album, track = (t.strip() for t in (artist, album, track))
        if album:
            query = f"{album} {artist}".strip()
        else:
            query = " ".join(t for t in (artist, track) if t).strip()
        if not query:
            return []

        cookie = self.get_cookie()
        if not cookie:
            log_event(
                "warning",
                "flacmusicfinder",
                "Search skipped: no browser session cookie configured for FLAC Music Finder.",
                {"source": self.source_id, "action": "search"},
            )
            raise RuntimeError(
                "FLAC Music Finder needs a browser session cookie: open https://flacmusicfinder.top/ in "
                "Chrome, copy the value of document.cookie (or the Cookie request header) and paste it into "
                "Settings -> FLAC Music Finder."
            )

        base = self.get_base_url()
        referer = base + "/"
        candidates = self._candidate_urls(query)
        last_failure = ""
        releases: List[NormalizedRelease] = []
        used_html_page = ""

        for url in candidates:
            try:
                status, body, content_type = await self._get_text(url, referer=referer)
            except Exception as exc:
                last_failure = f"{type(exc).__name__} on {url}: {exc}"
                continue
            if status in {401, 403}:
                last_failure = (
                    f"HTTP {status} from {url}: the cookie was rejected (expired or tied to a different "
                    "user-agent). Copy it again and keep the user-agent setting in sync with that browser."
                )
                continue
            if is_challenge_page(body):
                last_failure = (
                    f"{url} returned the JavaScript bot challenge instead of results, so this browser session "
                    "had not been accepted yet."
                )
                continue
            if status < 200 or status >= 300:
                last_failure = f"HTTP {status} from {url}"
                continue

            if "json" in content_type.lower():
                try:
                    releases = self._releases_from_json(json.loads(body), limit)
                except ValueError as exc:
                    last_failure = f"{url} returned unparseable JSON: {exc}"
                    continue
            else:
                releases = self._releases_from_html(body, page_url=url, limit=limit)
                used_html_page = url
            break

        if not releases:
            if last_failure:
                log_event(
                    "warning",
                    "flacmusicfinder",
                    f"Search returned no releases: {last_failure}",
                    {"source": self.source_id, "query": query},
                )
                raise RuntimeError(
                    f"FLAC Music Finder search returned no releases: {last_failure}. If the site changed its "
                    "search URL, set the 'search path' in Settings -> FLAC Music Finder to it (use "
                    "https://... or a path with a {query} placeholder) and retry."
                )
            return []

        if used_html_page:
            await self._attach_tracks(releases)
        return releases


def flacmusicfinder_download_hosts(eff_settings: Dict[str, object]) -> List[str]:
    """Hosts whose download URLs the download manager should accept for this source.

    The index host itself is always included; ``flacmusicfinder_extra_download_hosts`` covers the
    case where the site hands off file delivery to a separate host.
    ``download_manager.is_trusted_download_url`` consumes this list.
    """
    hosts: List[str] = []
    primary = (str(eff_settings.get("flacmusicfinder_base_url", "") or DEFAULT_BASE_URL)).strip()
    hosts.append(urlparse(primary).netloc)
    hosts.append(urlparse(DEFAULT_BASE_URL).netloc)
    for host in re.split(r"[,\s]+", str(eff_settings.get("flacmusicfinder_extra_download_hosts", "") or "")):
        stripped = (host or "").strip().lower().lstrip(".")
        stripped = stripped.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        if stripped:
            hosts.append(stripped)
    return [host for host in dict.fromkeys(hosts) if host]


def download_request_headers(eff_settings: Dict[str, object]) -> Dict[str, str]:
    """Headers the download manager must send for flacmusicfinder.top file URLs.

    The site ties the download to the same browser session used for browsing, so the stored
    cookie and a matching user-agent are replayed here. Read from the effective settings so a
    rotated cookie takes effect for queued jobs without restarting the backend.
    """
    headers: Dict[str, str] = {
        "User-Agent": str(eff_settings.get("flacmusicfinder_user_agent", "") or "").strip()
        or DEFAULT_BROWSER_USER_AGENT,
        "Accept": "audio/*,application/octet-stream,application/x-msdownload;q=0.9,*/*;q=0.8",
    }
    cookie = sanitize_cookie_header(str(eff_settings.get("flacmusicfinder_cookie", "") or ""))
    if cookie:
        headers["Cookie"] = cookie
    base = (str(eff_settings.get("flacmusicfinder_base_url", "") or DEFAULT_BASE_URL)).strip().rstrip("/")
    if base:
        headers["Referer"] = base + "/"
    return headers
