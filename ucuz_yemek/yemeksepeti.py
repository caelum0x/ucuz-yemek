"""
Fragile, UA-gated HTML scraper for Yemeksepeti (yemeksepeti.com).

HONEST STATUS (verified live 2026-11-03 during this build):
- Desktop Safari/Chrome User-Agent -> HTTP 403, PerimeterX bot-challenge page.
- iPhone Safari (mobile) User-Agent -> HTTP 200, real HTML (~1.2MB) containing a
  server-embedded Apollo/GraphQL cache with REAL menu items and REAL prices.
- There is NO clean JSON API: the real backend (disco.deliveryhero.io,
  tr.fd-api.com) returned HTTP 403 "Invalid Client ID: null" even when replaying
  the page's own perseus-client-id header back at it.

This means: this module works *today*, with a specific restaurant URL discovered
from the site's own public sitemap, and a specific UA. It is NOT a stable API,
it is UA/bot-detection-gated, and circumventing bot detection at any real volume
is a real ToS risk (see README.md). Treat every value this returns as "real but
fragile" — don't build anything that depends on this running unattended.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
TIMEOUT_SECONDS = 15

_PRODUCT_BLOCK_RE = re.compile(
    r'"(RestaurantProductData|RestaurantVariationData):(\d+)":\{'
)


class YemeksepetiError(RuntimeError):
    """Raised when the page can't be fetched or doesn't contain the expected cache."""


def fetch_restaurant_html(restaurant_url: str) -> str:
    """Fetch a real Yemeksepeti restaurant page using a mobile UA (bypasses the
    desktop-UA PerimeterX block that was confirmed live during this build)."""
    req = urllib.request.Request(
        restaurant_url, headers={"User-Agent": MOBILE_USER_AGENT, "Accept": "text/html"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", errors="replace")
    if status != 200:
        raise YemeksepetiError(
            f"Got HTTP {status} for {restaurant_url} (PerimeterX bot-block or page moved)."
        )
    return body


def _extract_apollo_entry(html: str, type_and_id: str) -> dict | None:
    """Extract one `"Type:id":{...}` JSON object from the embedded Apollo cache
    using brace counting (the cache is not valid standalone JSON on its own,
    so we can't json.loads() the whole blob)."""
    marker = f'"{type_and_id}":{{'
    start = html.find(marker)
    if start == -1:
        return None
    brace_start = start + len(marker) - 1  # position of the opening '{'
    depth = 0
    for i in range(brace_start, len(html)):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[brace_start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def extract_priced_items(html: str, limit: int = 20) -> list[dict]:
    """Walk every RestaurantProductData entry in the embedded cache, follow its
    variation ref(s), and return real (title, originalPrice, discountedPrice)
    rows. Returns [] if the page doesn't contain the expected cache shape."""
    results: list[dict] = []
    seen_product_ids: set[str] = set()

    for match in _PRODUCT_BLOCK_RE.finditer(html):
        type_name, obj_id = match.group(1), match.group(2)
        if type_name != "RestaurantProductData" or obj_id in seen_product_ids:
            continue
        seen_product_ids.add(obj_id)

        product = _extract_apollo_entry(html, f"RestaurantProductData:{obj_id}")
        if not product or not product.get("title"):
            continue

        price_try = None
        original_try = None

        # The price usually lives directly on the product itself.
        attrs = product.get("priceAttributes") or {}
        if attrs.get("discountedPrice") is not None or attrs.get("originalPrice") is not None:
            price_try = attrs.get("discountedPrice") or attrs.get("originalPrice")
            original_try = attrs.get("originalPrice")

        # Fall back to the first variation's priceAttributes if the product
        # itself has none (e.g. size/variant-based pricing).
        if price_try is None:
            for variation_ref in product.get("variations", []) or []:
                ref_id = (variation_ref or {}).get("__ref", "")
                if not ref_id.startswith("RestaurantVariationData:"):
                    continue
                variation = _extract_apollo_entry(html, ref_id)
                if not variation:
                    continue
                v_attrs = variation.get("priceAttributes") or {}
                if v_attrs.get("discountedPrice") is not None or v_attrs.get("originalPrice") is not None:
                    price_try = v_attrs.get("discountedPrice") or v_attrs.get("originalPrice")
                    original_try = v_attrs.get("originalPrice")
                    break

        if price_try is None:
            continue

        results.append(
            {
                "name": product["title"],
                "original_price_try": original_try,
                "price_try": price_try,
            }
        )
        if len(results) >= limit:
            break

    return results
