"""
Read-through / write-back cache around the real live fetchers in
trendyol_go.py / discovery.py / yemeksepeti.py. Every function here returns
the exact same real data shape its non-cached counterpart does -- this layer
never fabricates a restaurant/menu/price, it only decides whether to serve a
recent real fetch from Postgres or go live and store the result for next
time.

Each function returns `(data, cache_hit: bool)` so callers (refresh_job.py,
budget.py) can report real refresh counts instead of guessing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Json

from ucuz_yemek import discovery, trendyol_go, yemeksepeti
from ucuz_yemek.cache_db import get_connection

DEFAULT_TTL_SECONDS = 3600


def _age_seconds(fetched_at: datetime | None) -> float:
    if fetched_at is None:
        return float("inf")
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - fetched_at).total_seconds()


def _restaurant_search_key(latitude: float, longitude: float) -> str:
    # Rounded to ~1.1km grid cells -- real nearby-restaurant results don't
    # meaningfully change at finer granularity than that, and this keeps the
    # cache table small instead of one row per exact float pair.
    return f"{round(latitude, 2)}:{round(longitude, 2)}"


def cached_search_restaurants(
    latitude: float,
    longitude: float,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    force_refresh: bool = False,
) -> tuple[list[dict], bool]:
    """Real Trendyol Go nearby-restaurant search, cache-first. Returns
    (restaurants, cache_hit)."""
    key = _restaurant_search_key(latitude, longitude)
    with get_connection() as conn:
        if not force_refresh:
            row = conn.execute(
                "SELECT restaurants, fetched_at FROM trendyol_restaurant_search_cache WHERE cache_key = %s",
                (key,),
            ).fetchone()
            if row is not None and _age_seconds(row[1]) < ttl_seconds:
                return row[0], True

        restaurants = trendyol_go.search_restaurants(latitude, longitude)
        conn.execute(
            """
            INSERT INTO trendyol_restaurant_search_cache (cache_key, latitude, longitude, restaurants, fetched_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (cache_key) DO UPDATE SET
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                restaurants = EXCLUDED.restaurants,
                fetched_at = EXCLUDED.fetched_at
            """,
            (key, latitude, longitude, Json(restaurants)),
        )
        conn.commit()
        return restaurants, False


def cached_restaurant_menu(
    restaurant_id: int | str,
    restaurant_name: str,
    latitude: float,
    longitude: float,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    force_refresh: bool = False,
) -> tuple[dict, bool]:
    """Real Trendyol Go per-restaurant menu, cache-first. Returns
    (restaurant_menu_payload, cache_hit)."""
    key = str(restaurant_id)
    with get_connection() as conn:
        if not force_refresh:
            row = conn.execute(
                "SELECT menu, fetched_at FROM trendyol_menu_cache WHERE restaurant_id = %s", (key,)
            ).fetchone()
            if row is not None and _age_seconds(row[1]) < ttl_seconds:
                return row[0], True

        menu = trendyol_go.get_restaurant_menu(int(restaurant_id), latitude, longitude)
        conn.execute(
            """
            INSERT INTO trendyol_menu_cache (restaurant_id, restaurant_name, latitude, longitude, menu, fetched_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (restaurant_id) DO UPDATE SET
                restaurant_name = EXCLUDED.restaurant_name,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                menu = EXCLUDED.menu,
                fetched_at = EXCLUDED.fetched_at
            """,
            (key, restaurant_name, latitude, longitude, Json(menu)),
        )
        conn.commit()
        return menu, False


def cached_yemeksepeti_chain_items(
    chain: str,
    item_limit: int = 200,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    force_refresh: bool = False,
) -> tuple[str | None, list[dict], bool]:
    """Real Yemeksepeti curated-chain items (see budget.py's module
    docstring for why this is chain-curated, not true location search),
    cache-first. Returns (restaurant_url, items, cache_hit)."""
    with get_connection() as conn:
        if not force_refresh:
            row = conn.execute(
                "SELECT restaurant_url, items, fetched_at FROM yemeksepeti_chain_cache WHERE chain = %s",
                (chain,),
            ).fetchone()
            if row is not None and _age_seconds(row[2]) < ttl_seconds:
                return row[0], row[1], True

        url = discovery.find_yemeksepeti_restaurant_url(chain)
        items: list[dict[str, Any]] = []
        if url is not None:
            html = yemeksepeti.fetch_restaurant_html(url)
            items = yemeksepeti.extract_priced_items(html, limit=item_limit)

        conn.execute(
            """
            INSERT INTO yemeksepeti_chain_cache (chain, restaurant_url, items, fetched_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (chain) DO UPDATE SET
                restaurant_url = EXCLUDED.restaurant_url,
                items = EXCLUDED.items,
                fetched_at = EXCLUDED.fetched_at
            """,
            (chain, url, Json(items)),
        )
        conn.commit()
        return url, items, False
