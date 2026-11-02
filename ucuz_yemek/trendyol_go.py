"""
Real, unauthenticated fetcher for Trendyol Go Yemek (tgoyemek.com consumer site,
backend: api.tgoapis.com).

Confirmed working 2026-11-03 (fresh request made during this build, not just the
earlier probe): a plain GET with no cookies, no auth header and no API key returns
HTTP 200 and real JSON — both the restaurant-search endpoint and the per-restaurant
menu/price endpoint.

Base URL was found in the site's own public Next.js JS bundles (grep for the string
"api.tgoapis.com"); it is undocumented anywhere official. tgoyemek.com's robots.txt
explicitly *allows* crawling /restoranlar and /restoranlar/:id* — the exact UI pages
this API backs — which is the strongest (not risk-free, just least-contradicted)
signal found for this platform. See README.md for the full ToS-risk note.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

BASE_URL = "https://api.tgoapis.com/web-restaurant-apirestaurant-santral"
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    ),
}
TIMEOUT_SECONDS = 15


class TrendyolGoError(RuntimeError):
    """Raised when the Trendyol Go API does not return the expected shape."""


def _get_json(url: str, params: dict) -> dict:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full_url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        if resp.status != 200:
            raise TrendyolGoError(f"HTTP {resp.status} for {full_url}")
        return json.loads(resp.read().decode("utf-8"))


def search_restaurants(latitude: float, longitude: float) -> list[dict]:
    """Search restaurants near a lat/lon. Returns the real raw restaurant list."""
    data = _get_json(f"{BASE_URL}/restaurants/in/search", {"latitude": latitude, "longitude": longitude})
    restaurants = data.get("restaurants")
    if restaurants is None:
        raise TrendyolGoError(f"Unexpected response shape, no 'restaurants' key: {data!r}")
    return restaurants


def get_restaurant_menu(restaurant_id: int, latitude: float, longitude: float) -> dict:
    """Fetch the full menu (sections -> products -> price.salePrice) for one restaurant."""
    data = _get_json(
        f"{BASE_URL}/restaurants/{restaurant_id}", {"latitude": latitude, "longitude": longitude}
    )
    restaurant = data.get("restaurant")
    if restaurant is None:
        raise TrendyolGoError(f"Unexpected response shape, no 'restaurant' key: {data!r}")
    return restaurant


def flatten_menu_items(restaurant: dict) -> list[dict]:
    """Flatten restaurant['sections'][*]['products'] into (name, price) rows."""
    items: list[dict] = []
    for section in restaurant.get("sections", []):
        for product in section.get("products", []):
            price = product.get("price", {}).get("salePrice")
            items.append(
                {
                    "section": section.get("name"),
                    "name": product.get("name"),
                    "price_try": price,
                }
            )
    return items
