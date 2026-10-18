"""Polite HTTP fetching with an optional Firecrawl fallback for sites behind bot walls."""
from __future__ import annotations

import os
import time
from urllib.parse import urlparse

import requests

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 MedoraEvents/1.0 (+https://medoraevents.labs.trlibrary.com)"
)

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
_last_hit: dict[str, float] = {}
MIN_GAP = float(os.environ.get("MEDEVENTS_MIN_GAP", "0.6"))  # seconds between hits to one host

BLOCK_MARKERS = ("cf_chl_", "Just a moment...", "challenge-platform", "Attention Required!")


class FetchError(Exception):
    pass


def _throttle(url: str) -> None:
    host = urlparse(url).netloc
    wait = MIN_GAP - (time.time() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()


def _looks_blocked(resp: requests.Response) -> bool:
    if resp.status_code in (403, 429, 503):
        return True
    head = resp.text[:20000] if "html" in resp.headers.get("content-type", "") else ""
    return any(m in head for m in BLOCK_MARKERS)


def get(url: str, *, params=None, headers=None, timeout=45, retries=2, firecrawl=True) -> requests.Response:
    """GET a URL. If a bot wall blocks it and FIRECRAWL_API_KEY is set, retry through Firecrawl."""
    last_err = None
    for attempt in range(retries + 1):
        _throttle(url)
        try:
            resp = _session.get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
            continue
        if resp.ok and not _looks_blocked(resp):
            if resp.encoding and resp.encoding.lower() in ("iso-8859-1", "latin-1") and "charset" not in resp.headers.get("content-type", "").lower():
                resp.encoding = "utf-8"  # requests' HTTP default; these sites are all UTF-8
            return resp
        last_err = FetchError(f"{resp.status_code} for {resp.url}")
        if _looks_blocked(resp):
            break
        if resp.status_code < 500:
            break
        time.sleep(2 * (attempt + 1))
    if firecrawl and os.environ.get("FIRECRAWL_API_KEY"):
        return firecrawl_get(url if not params else requests.Request("GET", url, params=params).prepare().url)
    raise FetchError(str(last_err))


def get_json(url: str, **kw):
    return get(url, **kw).json()


class _FakeResponse:
    def __init__(self, url, text, markdown=""):
        self.url = url
        self.text = text
        self.markdown = markdown
        self.status_code = 200
        self.ok = True

    def json(self):
        import json
        return json.loads(self.text)


def firecrawl_get(url: str) -> _FakeResponse:
    """Fetch a page through the Firecrawl API (needs FIRECRAWL_API_KEY)."""
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        raise FetchError("FIRECRAWL_API_KEY not set")
    resp = requests.post(
        "https://api.firecrawl.dev/v2/scrape",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"url": url, "formats": ["rawHtml", "markdown"], "onlyMainContent": False},
        timeout=120,
    )
    if not resp.ok:
        raise FetchError(f"Firecrawl {resp.status_code}: {resp.text[:200]}")
    data = resp.json().get("data", {})
    return _FakeResponse(url, data.get("rawHtml") or data.get("html") or "", data.get("markdown") or "")
