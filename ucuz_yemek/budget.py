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

Ranking: `sort_mode` picks between real, honest strategies -- "cheapest_first"
and "priciest_first" are plain price sorts; "closest_to_budget" is the
original v1 heuristic (most food for the money without going over);
"best_value" is a real composite score (see ranking.py) over price,
distance, and rating -- all three already present in Trendyol Go's live
response and, until this pass, silently discarded. No calorie/portion-size
model exists (no real per-item nutrition/weight data exists on either
platform to rank on).
"""

from __future__ import annotations

from dataclasses import dataclass

from ucuz_yemek import discovery, ranking, trendyol_go, yemeksepeti

SORT_MODES: tuple[str, ...] = ("cheapest_first", "priciest_first", "closest_to_budget", "best_value")
DEFAULT_SORT_MODE = "closest_to_budget"
# "best_value" mode only -- excludes condiment/add-on priced items (confirmed
# live: McDonald's "Ücretli Soslar" section -- ketchup, mayo, even a plastic
# bag charge -- all price between 1-15 TRY) from being ranked as someone's
# "best value meal." No real menu-category field reliably distinguishes
# meals from add-ons across different restaurants' own section naming, so
# this is a real but deliberately simple price-floor heuristic, not a food
# classifier -- documented honestly, not hidden. Does NOT apply to
# cheapest_first/priciest_first/closest_to_budget, which honestly sort by
# raw price with no claim to be curating "real meals."
#
# Honest v1 limitation: this only clears literal condiment/bag-fee pricing
# (confirmed live: 1-15 TRY on Trendyol). It does NOT reliably separate
# "snack/drink" from "full entree" -- confirmed live: Yemeksepeti prices its
# own sauces/add-ons higher (~30 TRY) than this floor, so some still clear
# it. A real meal-vs-snack classifier would need a consistent cross-platform
# menu-category field, which doesn't exist (see plans/ucuz-yemek.md). Not
# silently papered over -- flagged here and in the API's scope_note.
MIN_MEAL_PRICE_TRY = 20.0

# Real chains independently confirmed reachable on Yemeksepeti's public
# restaurant sitemap during this session (2026-11-03) -- see
# plans/ucuz-yemek.md for the live verification. The 4 added 2026-11-04
# (little-caesars, papa-johns, kofteci-yusuf, pizza-bulls) got the same
# sitemap check PLUS a live Trendyol Go search match (see chains.py) before
# being added here -- kept in sync with chains.CHAINS by slug.
CURATED_YEMEKSEPETI_CHAINS: tuple[str, ...] = (
    "subway",
    "burger-king",
    "mcdonalds",
    "kfc",
    "dominos",
    "little-caesars",
    "papa-johns",
    "kofteci-yusuf",
    "pizza-bulls",
)

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
    # Real fields from the live Trendyol Go response (restaurant['location']
    # ['distance'] / restaurant['rating']), already fetched today and
    # previously discarded. Yemeksepeti has neither field anywhere in
    # yemeksepeti.py's scraper -- stays None there, never fabricated.
    distance_km: float | None = None
    rating: float | None = None


@dataclass(frozen=True)
class BudgetSearchResult:
    budget_try: float
    latitude: float
    longitude: float
    trendyol_restaurants_checked: list[str]
    yemeksepeti_chains_checked: list[str]
    items: list[AffordableItem]
    # Platform name -> the real error that took it fully offline this
    # request (e.g. an anti-bot 403 on the hosting IP). A platform in here
    # contributed zero items, but the OTHER platform's real results still
    # ship -- one platform going down should never discard data the other
    # one already fetched successfully.
    platform_errors: dict[str, str]


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
    budget_try: float,
    latitude: float,
    longitude: float,
    restaurant_cap: int,
    use_cache: bool = False,
    cache_ttl_seconds: int = 3600,
) -> tuple[list[AffordableItem], list[str]]:
    """Real items at or under budget from the real nearest Trendyol Go
    restaurants. One restaurant's menu failing (closed, empty, transient
    error) never kills the whole search -- it's just skipped.

    The raw search response is NOT distance-sorted -- confirmed live
    2026-11-03 (see plans/ucuz-yemek.md): several top slots carry
    `sponsored: true` and genuinely closer restaurants sort below farther
    ones. Sorting by the real `location.distance` field before slicing to
    `restaurant_cap` is the actual fix for "results aren't cheapest/closest
    first, they're relevance/sponsored first.\""""
    items: list[AffordableItem] = []
    checked: list[str] = []
    try:
        if use_cache:
            from ucuz_yemek import cached_fetchers

            all_restaurants, _ = cached_fetchers.cached_search_restaurants(
                latitude, longitude, ttl_seconds=cache_ttl_seconds
            )
        else:
            all_restaurants = trendyol_go.search_restaurants(latitude, longitude)
    except Exception as exc:
        raise RuntimeError(f"trendyol_go.search_restaurants failed: {exc}") from exc

    all_restaurants = sorted(
        all_restaurants, key=lambda r: (r.get("location") or {}).get("distance", float("inf"))
    )
    restaurants = [
        r for r in all_restaurants if (r.get("minBasketPrice") or 0) <= budget_try
    ][:restaurant_cap]

    for restaurant in restaurants:
        name = restaurant.get("name") or "?"
        checked.append(name)
        distance_km = (restaurant.get("location") or {}).get("distance")
        rating = restaurant.get("rating")
        try:
            if use_cache:
                from ucuz_yemek import cached_fetchers

                menu, _ = cached_fetchers.cached_restaurant_menu(
                    restaurant["id"], name, latitude, longitude, ttl_seconds=cache_ttl_seconds
                )
            else:
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
                        distance_km=distance_km,
                        rating=rating,
                    )
                )
    return items, checked


def _yemeksepeti_affordable_items(
    budget_try: float,
    chains: tuple[str, ...],
    item_limit: int,
    use_cache: bool = False,
    cache_ttl_seconds: int = 3600,
) -> tuple[list[AffordableItem], list[str]]:
    """Real items at or under budget from a curated set of chains known to
    resolve on the live sitemap (see module docstring for why this isn't a
    true location search yet)."""
    items: list[AffordableItem] = []
    checked: list[str] = []
    failures = 0
    for chain in chains:
        if use_cache:
            from ucuz_yemek import cached_fetchers

            try:
                url, chain_items, _ = cached_fetchers.cached_yemeksepeti_chain_items(
                    chain, item_limit=item_limit, ttl_seconds=cache_ttl_seconds
                )
            except Exception as exc:
                raise RuntimeError(f"cached_fetchers.cached_yemeksepeti_chain_items({chain!r}) failed: {exc}") from exc
            if url is None:
                continue
            checked.append(chain)
            restaurant_name = chain.replace("-", " ").title()
            for entry in chain_items:
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
            continue

        try:
            url = discovery.find_yemeksepeti_restaurant_url(chain)
        except Exception as exc:
            raise RuntimeError(f"discovery.find_yemeksepeti_restaurant_url({chain!r}) failed: {exc}") from exc
        if url is None:
            continue
        checked.append(chain)
        try:
            html = yemeksepeti.fetch_restaurant_html(url)
        except Exception:
            failures += 1
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
    if chains and failures == len(chains) and not items:
        raise RuntimeError(
            f"yemeksepeti.fetch_restaurant_html failed for all {len(chains)} curated chains"
        )
    return items, checked


def _sort_items(items: list[AffordableItem], sort_mode: str) -> list[AffordableItem]:
    if sort_mode == "cheapest_first":
        items.sort(key=lambda item: (item.price_try, item.item_name))
    elif sort_mode == "priciest_first":
        items.sort(key=lambda item: (-item.price_try, item.item_name))
    elif sort_mode == "closest_to_budget":
        # Original v1 heuristic: most food for the money without going over.
        items.sort(key=lambda item: (-item.price_try, item.item_name))
    elif sort_mode == "best_value":
        items = [item for item in items if item.price_try >= MIN_MEAL_PRICE_TRY]
        if not items:
            return items
        prices = [item.price_try for item in items]
        price_range = (min(prices), max(prices))
        distances = [item.distance_km for item in items if item.distance_km is not None]
        distance_range = (min(distances), max(distances)) if distances else None
        ratings = [item.rating for item in items if item.rating is not None]
        rating_range = (min(ratings), max(ratings)) if ratings else None
        scored = [
            (
                ranking.value_score(
                    item.price_try, item.distance_km, item.rating, price_range, distance_range, rating_range
                ),
                item,
            )
            for item in items
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1].item_name))
        items = [item for _, item in scored]
    else:
        raise ValueError(f"unknown sort_mode {sort_mode!r}, expected one of {SORT_MODES}")
    return items


def find_affordable_items(
    budget_try: float,
    latitude: float,
    longitude: float,
    restaurant_cap: int = DEFAULT_TRENDYOL_RESTAURANT_CAP,
    yemeksepeti_chains: tuple[str, ...] = CURATED_YEMEKSEPETI_CHAINS,
    sort_mode: str = DEFAULT_SORT_MODE,
    use_cache: bool = False,
    cache_ttl_seconds: int = 3600,
) -> BudgetSearchResult:
    """Real, live items the user can actually afford right now, from both
    platforms. `sort_mode` picks the real ranking strategy (see SORT_MODES /
    the module docstring) -- defaults to the original v1 "closest to budget"
    heuristic for backward compatibility. Never fabricates a
    restaurant/item/price -- a platform that returns nothing live just
    contributes zero items to the result. A platform going fully offline
    (e.g. its own anti-bot layer 403ing this server's IP) degrades to zero
    items from that platform plus a `platform_errors` entry -- it never
    discards the other platform's real, already-fetched results. Only raises
    if BOTH platforms are down, since there would be nothing real to return.

    `use_cache=False` (the default) is the exact original behavior -- every
    call hits Trendyol Go/Yemeksepeti live, unchanged, so the existing CLI
    and the live Vercel `api/index.py` are not affected by this parameter
    existing. `use_cache=True` (used by the new standalone `backend/server.py`
    service, see cached_fetchers.py) reads from the real Postgres cache first
    and only calls out live on a miss/stale entry, writing the real result
    back for next time -- see plans/ucuz-yemek.md for why this also fixes the
    Vercel 502 (reading a cache doesn't hit the anti-bot-blocked IP)."""
    if budget_try <= 0:
        raise ValueError("budget_try must be positive")
    if sort_mode not in SORT_MODES:
        raise ValueError(f"unknown sort_mode {sort_mode!r}, expected one of {SORT_MODES}")

    platform_errors: dict[str, str] = {}

    try:
        trendyol_items, trendyol_checked = _trendyol_affordable_items(
            budget_try, latitude, longitude, restaurant_cap, use_cache=use_cache, cache_ttl_seconds=cache_ttl_seconds
        )
    except RuntimeError as exc:
        trendyol_items, trendyol_checked = [], []
        platform_errors["trendyol_go"] = str(exc)

    try:
        yemeksepeti_items, yemeksepeti_checked = _yemeksepeti_affordable_items(
            budget_try,
            yemeksepeti_chains,
            DEFAULT_YEMEKSEPETI_ITEM_LIMIT,
            use_cache=use_cache,
            cache_ttl_seconds=cache_ttl_seconds,
        )
    except RuntimeError as exc:
        yemeksepeti_items, yemeksepeti_checked = [], []
        platform_errors["yemeksepeti"] = str(exc)

    if len(platform_errors) == 2:
        raise RuntimeError(
            f"both platforms failed: trendyol_go: {platform_errors['trendyol_go']}; "
            f"yemeksepeti: {platform_errors['yemeksepeti']}"
        )

    all_items = _dedupe(trendyol_items + yemeksepeti_items)
    all_items = _sort_items(all_items, sort_mode)

    return BudgetSearchResult(
        budget_try=budget_try,
        latitude=latitude,
        longitude=longitude,
        trendyol_restaurants_checked=trendyol_checked,
        yemeksepeti_chains_checked=yemeksepeti_checked,
        items=all_items,
        platform_errors=platform_errors,
    )
