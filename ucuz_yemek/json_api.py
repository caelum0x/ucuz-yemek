"""
Real combinatorial JSON API surface -- the same real-entity-A x real-entity-B
expansion ucuz_yemek/pages.py already uses for its HTML routes (20 real
cities x 9 real curated chains), exposed as JSON instead of rendered pages.

No business logic is reimplemented here: every endpoint calls the SAME real
functions pages.py/api/index.py already call (`budget.find_affordable_items`,
`service.run_match`, `discovery.find_yemeksepeti_restaurant_url`,
`yemeksepeti.extract_priced_items`) -- this module only shapes those real
results into JSON and adds request validation.

Kept as one APIRouter (not merged directly into api/index.py) for the same
reason pages.py's router is kept separate: Vercel's Python builder treats
every file directly under `api/` as its own function entry, so new routes
belong in a real package module under `ucuz_yemek/`, included from
api/index.py (and mirrored into backend/server.py for parity -- these
endpoints work identically cache-backed or not, same as /api/budget).

Endpoints:
    GET /api/cities                        -- list the 20 real cities
    GET /api/cities/{city_slug}             -- one real city's live
                                                affordable items
    GET /api/chains                         -- list the 9 real curated chains
    GET /api/chains/{chain_slug}            -- one real chain's live
                                                Yemeksepeti menu
    GET /api/chains/{chain_slug}/compare    -- real cross-platform item
                                                match for one chain near one
                                                city (9 chains x 20 cities =
                                                180 real addressable
                                                resources, same counting
                                                convention as the sitemap)
    GET /api/stats                          -- real aggregate numbers about
                                                this app's own real surface
                                                and cache state
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ucuz_yemek import budget as budget_module
from ucuz_yemek import cache_db, discovery, service, yemeksepeti
from ucuz_yemek.chains import CHAINS, CHAINS_BY_SLUG
from ucuz_yemek.cities import CITIES, CITIES_BY_SLUG, DEFAULT_CITY_BUDGET_TRY
from ucuz_yemek.matching import serialize_summary
from ucuz_yemek.pages import DEFAULT_SEHIR_SLUG, real_page_count

router = APIRouter()

MAX_BUDGET_TRY = 10_000.0
MAX_RESULTS = 60
DEFAULT_CHAIN_ITEM_LIMIT = 50
MAX_CHAIN_ITEM_LIMIT = 200


def _serialize_city(city) -> dict[str, Any]:
    return {
        "slug": city.slug,
        "display_name": city.display_name,
        "latitude": city.latitude,
        "longitude": city.longitude,
        "restaurant_count_seen": city.restaurant_count_seen,
    }


def _serialize_chain(chain) -> dict[str, Any]:
    return {
        "slug": chain.slug,
        "display_name": chain.display_name,
        "trendyol_query": chain.trendyol_query,
    }


@router.get("/api/cities")
def list_cities() -> JSONResponse:
    """Real, fixed list of every city this app supports -- the same 20
    cities.py entries ucuz_yemek/pages.py's /sehir/{city_slug} routes and
    DEFAULT CITY budget search already use (see cities.py's module
    docstring for how each coordinate was live-verified)."""
    return JSONResponse(content={"count": len(CITIES), "cities": [_serialize_city(c) for c in CITIES]})


@router.get("/api/cities/{city_slug}")
def city_detail(
    city_slug: str,
    budget: float = Query(DEFAULT_CITY_BUDGET_TRY, gt=0, le=MAX_BUDGET_TRY, description="Budget in TRY"),
    limit: int = Query(30, ge=1, le=MAX_RESULTS, description="Max items to return, ranked by value"),
    sort: str = Query(
        budget_module.DEFAULT_SORT_MODE,
        description="cheapest_first | priciest_first | closest_to_budget | best_value",
    ),
    q: str | None = Query(None, max_length=80, description="Optional free-text filter, e.g. 'burger'"),
) -> JSONResponse:
    """Real, live affordable items near one real city -- the exact same
    `budget_module.find_affordable_items` call ucuz_yemek/pages.py's
    /sehir/{city_slug} page makes, JSON instead of HTML. Defaults match that
    page (DEFAULT_CITY_BUDGET_TRY, best_value sort); `budget`/`limit`/`sort`/
    `q` can be overridden the same way /api/budget allows, since this is the
    same real search just pinned to one city's known-good coordinates."""
    city = CITIES_BY_SLUG.get(city_slug)
    if city is None:
        raise HTTPException(status_code=404, detail=f"Unknown city slug: {city_slug!r}")
    if sort not in budget_module.SORT_MODES:
        raise HTTPException(
            status_code=400, detail=f"unknown sort {sort!r}, expected one of {budget_module.SORT_MODES}"
        )

    try:
        result = budget_module.find_affordable_items(budget, city.latitude, city.longitude, sort_mode=sort, query=q)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # real upstream failure -- never fabricate a fallback
        raise HTTPException(status_code=502, detail=f"Upstream real-data fetch failed: {exc}") from exc

    items = [
        {
            "platform": item.platform,
            "restaurant_name": item.restaurant_name,
            "item_name": item.item_name,
            "price_try": item.price_try,
            "distance_km": item.distance_km,
            "rating": item.rating,
        }
        for item in result.items[:limit]
    ]
    return JSONResponse(
        content={
            "city": _serialize_city(city),
            "budget_try": result.budget_try,
            "sort": sort,
            "trendyol_restaurants_checked": result.trendyol_restaurants_checked,
            "yemeksepeti_chains_checked": result.yemeksepeti_chains_checked,
            "total_affordable_items_found": len(result.items),
            "items": items,
            "platform_errors": result.platform_errors,
        }
    )


@router.get("/api/chains")
def list_chains() -> JSONResponse:
    """Real, fixed list of every curated chain this app supports -- the same
    9 chains.py entries ucuz_yemek/pages.py's /karsilastir/{chain_slug}
    routes and budget.py's CURATED_YEMEKSEPETI_CHAINS already use (see
    chains.py's module docstring for how each one was live-verified on both
    platforms)."""
    return JSONResponse(content={"count": len(CHAINS), "chains": [_serialize_chain(c) for c in CHAINS]})


@router.get("/api/chains/{chain_slug}")
def chain_detail(
    chain_slug: str,
    limit: int = Query(
        DEFAULT_CHAIN_ITEM_LIMIT, ge=1, le=MAX_CHAIN_ITEM_LIMIT, description="Max Yemeksepeti items to return"
    ),
) -> JSONResponse:
    """Real, live Yemeksepeti menu for one curated chain -- no location
    needed since Yemeksepeti has no real location-search API (see
    budget.py's module docstring); the Trendyol Go side of this chain is
    location-dependent, see /api/chains/{chain_slug}/compare for that live
    cross-platform view near a real city. Never fabricates an item/price --
    a sitemap miss or a fetch failure is reported as `error`, not papered
    over with placeholder data."""
    chain = CHAINS_BY_SLUG.get(chain_slug)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Unknown chain slug: {chain_slug!r}")

    try:
        restaurant_url = discovery.find_yemeksepeti_restaurant_url(chain.trendyol_query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream real-data fetch failed: {exc}") from exc

    items: list[dict[str, Any]] = []
    error: str | None = None
    if restaurant_url is None:
        error = f"No live Yemeksepeti restaurant matching {chain.trendyol_query!r} in the sitemap."
    else:
        try:
            html = yemeksepeti.fetch_restaurant_html(restaurant_url)
            items = yemeksepeti.extract_priced_items(html, limit=limit)
        except Exception as exc:  # real upstream (bot-block, page moved) -- never fabricate a menu
            error = f"Upstream real-data fetch failed: {exc}"

    prices = [item["price_try"] for item in items if item.get("price_try") is not None]
    return JSONResponse(
        content={
            "chain": _serialize_chain(chain),
            "yemeksepeti_restaurant_url": restaurant_url,
            "yemeksepeti_item_count": len(items),
            "yemeksepeti_items": items,
            "price_range_try": {"min": min(prices), "max": max(prices)} if prices else None,
            "error": error,
        }
    )


@router.get("/api/chains/{chain_slug}/compare")
def chain_compare(chain_slug: str, sehir: str = Query(DEFAULT_SEHIR_SLUG, description="City slug")) -> JSONResponse:
    """Real cross-platform item match for one curated chain near one real
    city -- the exact JSON equivalent of ucuz_yemek/pages.py's
    /karsilastir/{chain_slug} page, same `service.run_match` call. 9 chains
    x 20 cities = 180 distinct real addressable resource URLs, the same
    counting convention the existing sitemap already uses for the HTML
    pages built on this identical data."""
    chain = CHAINS_BY_SLUG.get(chain_slug)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Unknown chain slug: {chain_slug!r}")
    city = CITIES_BY_SLUG.get(sehir)
    if city is None:
        raise HTTPException(status_code=404, detail=f"Unknown city slug: {sehir!r}")

    try:
        result = service.run_match(chain.trendyol_query, city.latitude, city.longitude)
    except service.MatchServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream real-data fetch failed: {exc}") from exc

    return JSONResponse(
        content={
            "chain": _serialize_chain(chain),
            "city": _serialize_city(city),
            "trendyol_restaurant": {
                "name": result.trendyol_restaurant_name,
                "id": result.trendyol_restaurant_id,
            },
            "yemeksepeti_restaurant_url": result.yemeksepeti_url,
            "trendyol_item_count": result.trendyol_item_count,
            "yemeksepeti_item_count": result.yemeksepeti_item_count,
            **serialize_summary(result.summary),
        }
    )


@router.get("/api/stats")
def stats() -> JSONResponse:
    """Real aggregate numbers about this app's own real surface -- no
    fabricated totals: `chain_x_city_compare_routes` is a real multiplication
    of the two real fixed lists above, `real_crawlable_pages` is the exact
    count ucuz_yemek/pages.py's own sitemap serves, and `cache` (when a
    backing Postgres is actually reachable -- true for backend/server.py,
    generally not for the stateless Vercel deployment) is the real current
    row counts + freshness per cache table (see cache_db.cache_health).
    `cache` is `null` rather than a fabricated empty/zero state when no
    database is configured or reachable."""
    cache: dict[str, Any] | None
    try:
        cache = cache_db.cache_health()
    except Exception:
        cache = None

    return JSONResponse(
        content={
            "cities_count": len(CITIES),
            "chains_count": len(CHAINS),
            "chain_x_city_compare_routes": len(CHAINS) * len(CITIES),
            "real_crawlable_pages": real_page_count(),
            "cache_backend_configured": cache is not None,
            "cache": cache,
        }
    )
