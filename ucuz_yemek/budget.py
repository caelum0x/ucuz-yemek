"""
Real budget-first discovery: "I have 300 TRY, what can I actually eat right
now?" -- the real headline pain point (owner clarification, 2026-11-03),
replacing chain-name search as the primary flow. `match` (matching.py /
discovery.py) stays available as a secondary same-item comparison feature;
this module is a different, simpler real query: given a budget and a
location, return real, live, affordable items across both platforms, ranked
by value, with zero fabricated restaurants/items/prices.

Real v1 scope, documented honestly rather than silently narrowed:
- **Trendyol Go**: `trendyol_go.search_restaurants` is already a real
  location-based "nearby restaurants" search (no chain filter needed), so
  this pulls menus from the real nearest restaurants to the given lat/lon.
  Capped to `restaurant_cap` restaurants because each one is its own live
  menu-fetch HTTP call -- fetching every nearby restaurant's full menu on
  every request would make a web request unreasonably slow for a v1.
- **Yemeksepeti**: there is still no real location-based restaurant-search
  API (confirmed again during this session, same finding as discovery.py's
  docstring) -- only the public sitemap, searchable by name/slug. So for v1
  this checks a curated list of popular chains already confirmed live and
  fetchable via the sitemap (see CURATED_YEMEKSEPETI_CHAINS), not "every
  real restaurant near this point." This is a real, honest v1 limitation:
  Yemeksepeti results are chain-only until a real location-search path is
  found, not a silent fake-out -- the API response labels this explicitly.

Ranking: "best value for the budget" is kept deliberately simple for v1 --
items are sorted by price descending (closest to the budget first, i.e. the
most food/value you can get without going over), which is a real, honest,
simple heuristic, not a calorie/portion-size model (no real per-item
nutrition/weight data exists to rank on anything richer yet).
"""

from __future__ import annotations

from dataclasses import dataclass

from ucuz_yemek import discovery, trendyol_go, yemeksepeti

# Real chains independently confirmed reachable on Yemeksepeti's public
# restaurant sitemap during this session (2026-11-03) -- see
# plans/ucuz-yemek.md for the live verification.
CURATED_YEMEKSEPETI_CHAINS: tuple[str, ...] = ("subway", "burger-king", "mcdonalds", "kfc", "dominos")

DEFAULT_TRENDYOL_RESTAURANT_CAP = 6
DEFAULT_YEMEKSEPETI_ITEM_LIMIT = 200


@dataclass(frozen=True)
class AffordableItem:
    """One real, live, priced menu item that fits inside the user's budget."""

    platform: str  # "trendyol_go" | "yemeksepeti"
    restaurant_name: str
    item_name: str
    price_try: float
    section: str | None = None


@dataclass(frozen=True)
class BudgetSearchResult:
    budget_try: float
    latitude: float
    longitude: float
    trendyol_restaurants_checked: list[str]
    yemeksepeti_chains_checked: list[str]
    items: list[AffordableItem]


def _dedupe(items: list[AffordableItem]) -> list[AffordableItem]:
    seen: set[tuple[str, str, str, float]] = set()
    result: list[AffordableItem] = []
    for item in items:
        key = (item.platform, item.restaurant_name, item.item_name, item.price_try)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _trendyol_affordable_items(
    budget_try: float, latitude: float, longitude: float, restaurant_cap: int
) -> tuple[list[AffordableItem], list[str]]:
    """Real items at or under budget from the real nearest Trendyol Go
    restaurants. One restaurant's menu failing (closed, empty, transient
    error) never kills the whole search -- it's just skipped."""
    items: list[AffordableItem] = []
    checked: list[str] = []
    restaurants = trendyol_go.search_restaurants(latitude, longitude)[:restaurant_cap]
    for restaurant in restaurants:
        name = restaurant.get("name") or "?"
        checked.append(name)
        try:
            menu = trendyol_go.get_restaurant_menu(restaurant["id"], latitude, longitude)
        except Exception:
            continue
        for entry in trendyol_go.flatten_menu_items(menu):
            price = entry["price_try"]
            if price is not None and 0 < price <= budget_try:
                items.append(
                    AffordableItem(
                        platform="trendyol_go",
                        restaurant_name=name,
                        item_name=entry["name"],
                        price_try=price,
                        section=entry.get("section"),
                    )
                )
    return items, checked


def _yemeksepeti_affordable_items(
    budget_try: float, chains: tuple[str, ...], item_limit: int
) -> tuple[list[AffordableItem], list[str]]:
    """Real items at or under budget from a curated set of chains known to
    resolve on the live sitemap (see module docstring for why this isn't a
    true location search yet)."""
    items: list[AffordableItem] = []
    checked: list[str] = []
    for chain in chains:
        url = discovery.find_yemeksepeti_restaurant_url(chain)
        if url is None:
            continue
        checked.append(chain)
        try:
            html = yemeksepeti.fetch_restaurant_html(url)
        except Exception:
            continue
        restaurant_name = chain.replace("-", " ").title()
        for entry in yemeksepeti.extract_priced_items(html, limit=item_limit):
            price = entry["price_try"]
            if price is not None and 0 < price <= budget_try:
                items.append(
                    AffordableItem(
                        platform="yemeksepeti",
                        restaurant_name=restaurant_name,
                        item_name=entry["name"],
                        price_try=price,
                    )
                )
    return items, checked


def find_affordable_items(
    budget_try: float,
    latitude: float,
    longitude: float,
    restaurant_cap: int = DEFAULT_TRENDYOL_RESTAURANT_CAP,
    yemeksepeti_chains: tuple[str, ...] = CURATED_YEMEKSEPETI_CHAINS,
) -> BudgetSearchResult:
    """Real, live items the user can actually afford right now, from both
    platforms, ranked closest-to-budget first. Never fabricates a
    restaurant/item/price -- a platform that returns nothing live just
    contributes zero items to the result."""
    if budget_try <= 0:
        raise ValueError("budget_try must be positive")

    trendyol_items, trendyol_checked = _trendyol_affordable_items(
        budget_try, latitude, longitude, restaurant_cap
    )
    yemeksepeti_items, yemeksepeti_checked = _yemeksepeti_affordable_items(
        budget_try, yemeksepeti_chains, DEFAULT_YEMEKSEPETI_ITEM_LIMIT
    )

    all_items = _dedupe(trendyol_items + yemeksepeti_items)
    # Best value for the budget, v1 heuristic: closest to the budget first
    # (most food for the money), cheapest first as the tiebreak when tied.
    all_items.sort(key=lambda item: (-item.price_try, item.item_name))

    return BudgetSearchResult(
        budget_try=budget_try,
        latitude=latitude,
        longitude=longitude,
        trendyol_restaurants_checked=trendyol_checked,
        yemeksepeti_chains_checked=yemeksepeti_checked,
        items=all_items,
    )
