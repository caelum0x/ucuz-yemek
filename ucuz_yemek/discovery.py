"""
Real restaurant discovery across both platforms for the SAME chain, so
`match` has two live menus worth matching instead of two arbitrary
restaurants (the gap `cli.cmd_compare` always flagged).

Trendyol Go: its own search-by-location endpoint already returns restaurant
names, so finding e.g. "Subway" near a point is just a name filter on
`trendyol_go.search_restaurants`.

Yemeksepeti: there's no public search-by-name/location API (confirmed in the
original probe), but the site's own public sitemap
(`/adventure-map/adventure-map-restaurant-{0,1,2}.xml`, ~37MB total, real and
unauthenticated) lists every restaurant slug, e.g.
`restaurant/q08s/subway-q08s`. Downloading it is slow, so results are cached
to disk for 24h -- the sitemap itself, not fabricated match data.
"""

from __future__ import annotations

import os
import re
import time
import urllib.request

from ucuz_yemek import trendyol_go

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
SITEMAP_INDEX_URL = "https://www.yemeksepeti.com/adventure-map/adventure-map-index-restaurant.xml"
TIMEOUT_SECONDS = 30
# Vercel's serverless filesystem is read-only outside /tmp; VERCEL=1 is set
# automatically in that runtime (https://vercel.com/docs/environment-variables/system-environment-variables).
# /tmp only persists for a warm instance's lifetime there, which still avoids
# re-downloading the ~37MB sitemap on every request within the same instance
# -- the CLI/local default of a real on-disk 24h cache is unchanged.
CACHE_DIR = os.environ.get("UCUZ_YEMEK_CACHE_DIR") or (
    "/tmp/ucuz-yemek-cache" if os.environ.get("VERCEL") else os.path.expanduser("~/.cache/ucuz-yemek")
)
CACHE_TTL_SECONDS = 24 * 60 * 60

_LOC_RE = re.compile(r"<loc>([^<]+)</loc>")


class DiscoveryError(RuntimeError):
    pass


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": MOBILE_USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        if resp.status != 200:
            raise DiscoveryError(f"HTTP {resp.status} for {url}")
        return resp.read().decode("utf-8", errors="replace")


def _sitemap_shard_urls() -> list[str]:
    index_xml = _fetch(SITEMAP_INDEX_URL)
    return _LOC_RE.findall(index_xml)


def _cache_path(shard_url: str) -> str:
    name = shard_url.rsplit("/", 1)[-1]
    return os.path.join(CACHE_DIR, name)


def _load_restaurant_slugs(force_refresh: bool = False) -> list[str]:
    """Real sitemap URLs for every Yemeksepeti restaurant, cached on disk for
    24h (each shard is several MB; re-downloading on every CLI call would
    make `match` unusably slow for no real-data benefit)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    urls: list[str] = []
    for shard_url in _sitemap_shard_urls():
        path = _cache_path(shard_url)
        is_fresh = (
            not force_refresh
            and os.path.isfile(path)
            and (time.time() - os.path.getmtime(path)) < CACHE_TTL_SECONDS
        )
        if is_fresh:
            with open(path, "r", encoding="utf-8") as handle:
                xml = handle.read()
        else:
            xml = _fetch(shard_url)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(xml)
        urls.extend(_LOC_RE.findall(xml))
    return urls


def find_yemeksepeti_restaurant_url(chain_query: str, force_refresh: bool = False) -> str | None:
    """First real restaurant URL whose slug contains `chain_query` (e.g.
    "subway" -> "https://www.yemeksepeti.com/restaurant/q08s/subway-q08s").
    Returns None if the live sitemap has no match."""
    needle = chain_query.strip().lower().replace(" ", "-")
    for url in _load_restaurant_slugs(force_refresh=force_refresh):
        if needle in url.lower():
            return url
    return None


def find_trendyol_restaurant(chain_query: str, latitude: float, longitude: float) -> dict | None:
    """First real restaurant near (latitude, longitude) whose name contains
    `chain_query` (case-insensitive), from Trendyol Go's own live search."""
    needle = chain_query.strip().lower()
    for restaurant in trendyol_go.search_restaurants(latitude, longitude):
        if needle in (restaurant.get("name") or "").lower():
            return restaurant
    return None
