"""
Real match-and-compare service: the exact discovery -> fetch -> match
pipeline `cli.py`'s `match` subcommand runs, factored out so both the CLI
and the web API (`api/index.py`) call the same real logic once -- no
duplicated business logic, no reimplementation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ucuz_yemek import discovery, matching, trendyol_go, yemeksepeti


class MatchServiceError(RuntimeError):
    """Raised when a real, live restaurant can't be found for the requested
    chain on one or both platforms."""


def _dedupe_items(items) -> list[matching.MenuItem]:
    """Real restaurant menus repeat the same item across multiple display
    sections -- dedupe by (name, price) so matching spends its Jev budget on
    genuinely different items, not the same listing counted several times."""
    seen: set[tuple[str, float]] = set()
    result: list[matching.MenuItem] = []
    for item in items:
        key = (item.name, item.price_try)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


@dataclass(frozen=True)
class MatchServiceResult:
    chain: str
    trendyol_restaurant_name: str
    trendyol_restaurant_id: int
    yemeksepeti_url: str
    trendyol_item_count: int
    yemeksepeti_item_count: int
    summary: matching.MatchSummary


def run_match(chain: str, latitude: float, longitude: float) -> MatchServiceResult:
    """Real end-to-end run: find a live branch of `chain` on both platforms,
    fetch both live menus, and run the real blocking -> matching -> merge
    pipeline. Raises MatchServiceError if a live branch isn't found on
    either platform -- never fabricates a restaurant or a match."""
    trendyol_restaurant = discovery.find_trendyol_restaurant(chain, latitude, longitude)
    if trendyol_restaurant is None:
        raise MatchServiceError(
            f"No live Trendyol Go restaurant matching {chain!r} near ({latitude}, {longitude})."
        )

    yemeksepeti_url = discovery.find_yemeksepeti_restaurant_url(chain)
    if yemeksepeti_url is None:
        raise MatchServiceError(f"No live Yemeksepeti restaurant matching {chain!r} in the sitemap.")

    menu = trendyol_go.get_restaurant_menu(trendyol_restaurant["id"], latitude, longitude)
    trendyol_items = _dedupe_items(
        matching.MenuItem("trendyol_go", item["name"], item["price_try"], item)
        for item in trendyol_go.flatten_menu_items(menu)
        if item["price_try"] is not None
    )

    html = yemeksepeti.fetch_restaurant_html(yemeksepeti_url)
    yemeksepeti_items = _dedupe_items(
        matching.MenuItem("yemeksepeti", item["name"], item["price_try"], item)
        for item in yemeksepeti.extract_priced_items(html, limit=500)
    )

    summary = matching.match_menus_detailed(trendyol_items, yemeksepeti_items)

    return MatchServiceResult(
        chain=chain,
        trendyol_restaurant_name=trendyol_restaurant["name"],
        trendyol_restaurant_id=trendyol_restaurant["id"],
        yemeksepeti_url=yemeksepeti_url,
        trendyol_item_count=len(trendyol_items),
        yemeksepeti_item_count=len(yemeksepeti_items),
        summary=summary,
    )


_TRENDYOL_ID_RE = re.compile(r"(\d+)")


def parse_trendyol_restaurant_id(value: str) -> int:
    """Real callers pass either a bare numeric id ("332791") or a Trendyol Go
    URL/deeplink containing one (e.g. "https://www.tgoyemek.com/restoranlar/332791"
    or "tgo://?...&RestaurantId=332791") -- take the LAST digit run in the
    string, which is the id in every one of those real shapes. Raises
    MatchServiceError (never guesses/defaults) if no digits are present."""
    matches = _TRENDYOL_ID_RE.findall(value)
    if not matches:
        raise MatchServiceError(f"Could not find a restaurant id in {value!r}.")
    return int(matches[-1])


@dataclass(frozen=True)
class MatchByUrlResult:
    trendyol_restaurant_name: str
    trendyol_restaurant_id: int
    yemeksepeti_url: str
    trendyol_item_count: int
    yemeksepeti_item_count: int
    summary: matching.MatchSummary


def run_match_by_urls(
    trendyol_restaurant: str, yemeksepeti_url: str, latitude: float, longitude: float
) -> MatchByUrlResult:
    """Real end-to-end match between two SPECIFIC, caller-supplied restaurants
    -- one on each platform -- bypassing `run_match`'s chain-name lookup
    entirely (ucuz_yemek/discovery.py / chains.py). This is the real fix for
    the gap this repo's README has always flagged: two independent local
    restaurants (e.g. one meze shop on Trendyol Go, an unrelated-by-name
    listing on Yemeksepeti) have no shared chain name to join on, but a
    human who already knows both listings can supply both identities
    directly -- no restaurant-identity fuzzy matching needed, only the
    existing real item-matching pipeline (matching.py) run on two real,
    live menu fetches.

    `latitude`/`longitude` are still required: Trendyol Go's own menu
    endpoint (trendyol_go.get_restaurant_menu) takes them on every real call
    (delivery-zone pricing), the same as `run_match` above -- there is no
    coordinate-free variant of that live API.
    """
    trendyol_id = parse_trendyol_restaurant_id(trendyol_restaurant)

    menu = trendyol_go.get_restaurant_menu(trendyol_id, latitude, longitude)
    trendyol_items = _dedupe_items(
        matching.MenuItem("trendyol_go", item["name"], item["price_try"], item)
        for item in trendyol_go.flatten_menu_items(menu)
        if item["price_try"] is not None
    )

    html = yemeksepeti.fetch_restaurant_html(yemeksepeti_url)
    yemeksepeti_items = _dedupe_items(
        matching.MenuItem("yemeksepeti", item["name"], item["price_try"], item)
        for item in yemeksepeti.extract_priced_items(html, limit=500)
    )

    summary = matching.match_menus_detailed(trendyol_items, yemeksepeti_items)

    return MatchByUrlResult(
        trendyol_restaurant_name=(menu.get("info") or {}).get("name") or f"restaurant {trendyol_id}",
        trendyol_restaurant_id=trendyol_id,
        yemeksepeti_url=yemeksepeti_url,
        trendyol_item_count=len(trendyol_items),
        yemeksepeti_item_count=len(yemeksepeti_items),
        summary=summary,
    )
