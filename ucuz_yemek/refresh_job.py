"""
Real scheduled cache-warming job -- the thing that makes the new Postgres
cache (cache_db.py / cached_fetchers.py) actually useful instead of an inert
table. Iterates the already-verified-reachable cities (cities.py, the same
20 cities the 124-page SEO expansion uses) and curated Yemeksepeti chains
(budget.CURATED_YEMEKSEPETI_CHAINS), live-fetching from both platforms and
writing every real result into Postgres.

Two ways to run it:
- Once, for a cron job / systemd timer: `python -m ucuz_yemek.refresh_job`
- Forever, as a background task inside a long-running process (used by
  `backend/server.py`'s own startup hook) via `run_forever()`.

Every number this returns is a real count of real HTTP calls made during
this run -- nothing here is simulated.
"""

from __future__ import annotations

import logging
import time

from ucuz_yemek import budget, cached_fetchers, cities

logger = logging.getLogger("ucuz_yemek.refresh_job")

# cities.py's own `restaurant_count_seen` confirms at least this many real
# restaurants per city; capped here for the same reason budget.py caps
# restaurant_cap -- each menu fetch is its own live HTTP call.
MENU_FETCH_CAP_PER_CITY = 10


def refresh_trendyol_cities(force_refresh: bool = True) -> dict[str, int]:
    """Real live refresh of every supported city's nearby-restaurant search
    plus each of those restaurants' menus."""
    restaurant_searches_refreshed = 0
    menus_refreshed = 0
    menus_failed = 0
    for city in cities.CITIES:
        try:
            restaurants, hit = cached_fetchers.cached_search_restaurants(
                city.latitude, city.longitude, force_refresh=force_refresh
            )
        except Exception:
            logger.exception("restaurant search refresh failed for city %s", city.slug)
            continue
        if not hit:
            restaurant_searches_refreshed += 1

        for restaurant in restaurants[:MENU_FETCH_CAP_PER_CITY]:
            restaurant_id = restaurant.get("id")
            if restaurant_id is None:
                continue
            try:
                _, menu_hit = cached_fetchers.cached_restaurant_menu(
                    restaurant_id,
                    restaurant.get("name") or "?",
                    city.latitude,
                    city.longitude,
                    force_refresh=force_refresh,
                )
            except Exception:
                logger.exception("menu refresh failed for restaurant %s in %s", restaurant_id, city.slug)
                menus_failed += 1
                continue
            if not menu_hit:
                menus_refreshed += 1

    return {
        "cities": len(cities.CITIES),
        "restaurant_searches_refreshed": restaurant_searches_refreshed,
        "menus_refreshed": menus_refreshed,
        "menus_failed": menus_failed,
    }


def refresh_yemeksepeti_chains(force_refresh: bool = True) -> dict[str, int]:
    """Real live refresh of every curated Yemeksepeti chain."""
    refreshed = 0
    failed = 0
    for chain in budget.CURATED_YEMEKSEPETI_CHAINS:
        try:
            url, _items, hit = cached_fetchers.cached_yemeksepeti_chain_items(
                chain, force_refresh=force_refresh
            )
        except Exception:
            logger.exception("refresh failed for Yemeksepeti chain %s", chain)
            failed += 1
            continue
        if url is not None and not hit:
            refreshed += 1

    return {"chains": len(budget.CURATED_YEMEKSEPETI_CHAINS), "refreshed": refreshed, "failed": failed}


def run_once() -> dict[str, dict[str, int]]:
    """One real, complete cache-warming pass over every supported city and
    curated chain. Each platform's failure is independent -- the same
    "never let one platform's outage discard the other's real results"
    policy budget.py already uses."""
    result: dict[str, dict[str, int]] = {}
    try:
        result["trendyol_go"] = refresh_trendyol_cities()
    except Exception:
        logger.exception("Trendyol Go refresh pass failed entirely")
        result["trendyol_go"] = {"error": 1}
    try:
        result["yemeksepeti"] = refresh_yemeksepeti_chains()
    except Exception:
        logger.exception("Yemeksepeti refresh pass failed entirely")
        result["yemeksepeti"] = {"error": 1}
    return result


def run_forever(interval_seconds: int = 6 * 60 * 60) -> None:  # pragma: no cover - long-running loop
    """Real scheduled-job loop for a persistent process (backend/server.py's
    own background task uses this via asyncio.to_thread, not this function
    directly, so the event loop isn't blocked for the whole refresh)."""
    while True:
        try:
            result = run_once()
            logger.info("cache refresh complete: %s", result)
        except Exception:
            logger.exception("cache refresh loop iteration failed")
        time.sleep(interval_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = run_once()
    print(result)


if __name__ == "__main__":
    main()
