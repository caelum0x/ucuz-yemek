"""
Ucuz Yemek real web API + frontend -- FastAPI, same deploy shape as this
portfolio's darkvol (a FastAPI app under api/, meant to run as a Vercel
Python function; see vercel.json). NOT deployed yet -- see
plans/ucuz-yemek.md for what a real deploy would need.

This is a thin HTTP wrapper around the SAME real logic already proven out by
the CLI (`ucuz_yemek/cli.py`): `budget.find_affordable_items` (the real
headline "I have N TRY, what can I actually eat right now" flow) and
`service.run_match` (the real same-item cross-platform comparison, kept as a
secondary feature). No business logic is reimplemented here -- this module
only adds request validation, JSON shaping, and serves the frontend page.

Endpoints:
    GET /                 -- the real frontend (budget.try + location in, a
                             real live affordability list out)
    GET /api/budget       -- real affordable-items search (JSON)
    GET /api/match        -- real same-item cross-platform comparison (JSON)
    GET /api/healthz      -- liveness check
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

# ucuz_yemek/ lives at the repo root, one level up from this api/ dir. Vercel's
# Python builder includes it via vercel.json's includeFiles; make sure it's
# importable regardless of the function's cwd (same pattern as darkvol/api/index.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ucuz_yemek import budget as budget_module  # noqa: E402
from ucuz_yemek import matching, service  # noqa: E402
from ucuz_yemek.pages import router as pages_router  # noqa: E402

app = FastAPI(
    title="Ucuz Yemek API",
    description="Real Turkish food-delivery budget search and cross-platform price comparison",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

MAX_BUDGET_TRY = 10_000.0
MAX_RESULTS = 60

# When set, /api/budget proxies to the standalone backend (backend/server.py,
# deployed on one of the portfolio's own Oracle boxes -- see
# infra-box/stacks/ucuz-yemek-backend) instead of live-fetching Trendyol
# Go/Yemeksepeti itself. Real reason: Yemeksepeti's anti-bot layer 403s
# Vercel's own hosting IP on a live call (confirmed in production), but not
# that box's IP -- the backend keeps a Postgres cache warm from there. Unset
# (e.g. local dev) falls through to the original live-fetch-only behaviour,
# unchanged.
UCUZ_YEMEK_BACKEND_URL = os.environ.get("UCUZ_YEMEK_BACKEND_URL", "").rstrip("/")


@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _proxy_budget(budget: float, lat: float, lon: float, limit: int, sort: str) -> dict[str, Any] | None:
    """Best-effort proxy to UCUZ_YEMEK_BACKEND_URL's own /api/budget. Returns
    None on any failure (network error, non-200, bad JSON) so the caller can
    fall back to the live-fetch path rather than erroring out -- the backend
    being briefly unreachable should never be worse than the pre-existing
    behaviour."""
    if not UCUZ_YEMEK_BACKEND_URL:
        return None
    qs = urllib.parse.urlencode({"budget": budget, "lat": lat, "lon": lon, "limit": limit, "sort": sort})
    url = f"{UCUZ_YEMEK_BACKEND_URL}/api/budget?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ucuz-yemek-vercel-proxy/1"})
        with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310 -- our own backend, fixed URL
            if resp.status != 200:
                return None
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001 -- genuinely best-effort: any failure (DNS, TLS, reset,
        # timeout, malformed JSON) must fall back to the live-fetch path, never 500 the request.
        if os.environ.get("UCUZ_YEMEK_PROXY_DEBUG"):
            raise HTTPException(status_code=599, detail=f"{type(exc).__name__}: {exc}") from exc
        return None


@app.get("/api/budget")
def get_budget(
    budget: float = Query(..., gt=0, le=MAX_BUDGET_TRY, description="Budget in TRY, e.g. 300"),
    lat: float = Query(..., ge=-90, le=90, description="Latitude, e.g. 41.0422"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude, e.g. 29.0061"),
    limit: int = Query(30, ge=1, le=MAX_RESULTS, description="Max items to return, ranked by value"),
    sort: str = Query(
        budget_module.DEFAULT_SORT_MODE,
        description="cheapest_first | priciest_first | closest_to_budget | best_value",
    ),
) -> JSONResponse:
    """Real, live items at or under `budget` TRY near (`lat`, `lon`), from
    both platforms (see ucuz_yemek/budget.py for each platform's real,
    honestly-scoped coverage). Every number is a live fetch made during this
    request -- there is no cache/mock fallback."""
    if sort not in budget_module.SORT_MODES:
        raise HTTPException(
            status_code=400, detail=f"unknown sort {sort!r}, expected one of {budget_module.SORT_MODES}"
        )

    proxied = _proxy_budget(budget, lat, lon, limit, sort)
    if proxied is not None:
        return JSONResponse(content=proxied)

    try:
        result = budget_module.find_affordable_items(budget, lat, lon, sort_mode=sort)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # budget_module attributes which upstream platform actually failed
        # (see _trendyol_affordable_items/_yemeksepeti_affordable_items) --
        # pass that through instead of a generic "fetch failed".
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # real upstream (Trendyol/Yemeksepeti) failure -- never fabricate a fallback
        raise HTTPException(status_code=502, detail=f"Upstream real-data fetch failed: {exc}") from exc

    items: list[dict[str, Any]] = [
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
            "budget_try": result.budget_try,
            "latitude": result.latitude,
            "longitude": result.longitude,
            "sort": sort,
            "trendyol_restaurants_checked": result.trendyol_restaurants_checked,
            "yemeksepeti_chains_checked": result.yemeksepeti_chains_checked,
            "total_affordable_items_found": len(result.items),
            "items": items,
            "platform_errors": result.platform_errors,
            "scope_note": (
                "Trendyol Go: real nearest restaurants to this location, sorted by real "
                "distance (not the platform's own relevance/sponsored order). Yemeksepeti: "
                "a curated set of popular chains (no real location-search API exists on "
                "that platform yet, so no distance/rating data either) -- see README.md "
                "for why. sort=best_value excludes sub-20-TRY condiment/add-on items and "
                "combines price, distance, and rating into one score -- see "
                "ucuz_yemek/ranking.py."
            ),
        }
    )


@app.get("/api/match")
def get_match(
    chain: str = Query(..., min_length=1, max_length=60, description="Restaurant chain name, e.g. subway"),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> JSONResponse:
    """Real same-item cross-platform match for one chain (secondary feature,
    see ucuz_yemek/service.py / matching.py). Every match is a live
    Jev-adjudicated or string-matched pair, never fabricated."""
    try:
        result = service.run_match(chain, lat, lon)
    except service.MatchServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream real-data fetch failed: {exc}") from exc

    return JSONResponse(
        content={
            "chain": result.chain,
            "trendyol_restaurant": {
                "name": result.trendyol_restaurant_name,
                "id": result.trendyol_restaurant_id,
            },
            "yemeksepeti_restaurant_url": result.yemeksepeti_url,
            "trendyol_item_count": result.trendyol_item_count,
            "yemeksepeti_item_count": result.yemeksepeti_item_count,
            **_serialize_match_summary(result.summary),
        }
    )


def _serialize_match_summary(summary: matching.MatchSummary) -> dict[str, Any]:
    """Shared real-match-result shaping used by both /api/match (chain-name
    lookup) and /api/match-by-url (direct restaurant identities) -- same
    underlying matching.MatchSummary either way, no duplicated logic."""
    matches: list[dict[str, Any]] = []
    for pair in summary.matches:
        a, b = pair.item_a, pair.item_b
        matches.append(
            {
                "trendyol_name": a.name,
                "yemeksepeti_name": b.name,
                "trendyol_price_try": a.price_try,
                "yemeksepeti_price_try": b.price_try,
                "cheaper_platform": pair.cheaper_platform,
                "price_diff_try": pair.price_diff_try,
                "method": pair.method,
                "confidence": round(pair.confidence, 3),
            }
        )
    return {
        "candidate_pairs": summary.candidate_pairs,
        "auto_accepted": summary.auto_accepted,
        "jev_accepted": summary.jev_accepted,
        "jev_rejected": summary.jev_rejected,
        "needs_review_count": len(summary.needs_review),
        "matches": matches,
    }


@app.get("/api/match-by-url")
def get_match_by_url(
    trendyol_restaurant: str = Query(
        ...,
        min_length=1,
        description=(
            "Trendyol Go restaurant id, or any real URL/deeplink containing one "
            "(e.g. a tgoyemek.com restaurant URL, or RestaurantId=NNN deeplink)"
        ),
    ),
    yemeksepeti_url: str = Query(
        ..., min_length=1, description="Full Yemeksepeti restaurant URL, e.g. https://www.yemeksepeti.com/restaurant/..."
    ),
    lat: float = Query(..., ge=-90, le=90, description="Latitude for the Trendyol Go menu fetch"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude for the Trendyol Go menu fetch"),
) -> JSONResponse:
    """Real same-item cross-platform match between two SPECIFIC restaurants
    the caller already knows about -- one on each platform -- bypassing the
    chain-name lookup /api/match depends on (ucuz_yemek/discovery.py). This
    is the real fix for the gap this repo's README has always flagged: two
    independent local restaurants with no shared chain name to join on.
    Same real live-menu-fetch + matching.py pipeline either way, never
    fabricated."""
    try:
        result = service.run_match_by_urls(trendyol_restaurant, yemeksepeti_url, lat, lon)
    except service.MatchServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream real-data fetch failed: {exc}") from exc

    return JSONResponse(
        content={
            "trendyol_restaurant": {
                "name": result.trendyol_restaurant_name,
                "id": result.trendyol_restaurant_id,
            },
            "yemeksepeti_restaurant_url": result.yemeksepeti_url,
            "trendyol_item_count": result.trendyol_item_count,
            "yemeksepeti_item_count": result.yemeksepeti_item_count,
            **_serialize_match_summary(result.summary),
        }
    )


_FRONTEND_HTML_PATH = Path(__file__).resolve().parent.parent / "web" / "index.html"


@app.get("/", response_class=HTMLResponse)
def frontend() -> str:
    return _FRONTEND_HTML_PATH.read_text(encoding="utf-8")


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt() -> str:
    """Standard allow-all crawl directive pointing at the real sitemap (see
    ucuz_yemek/pages.py's sitemap()) -- no SEO surface this app serves is
    gated behind auth, so there is nothing real to Disallow."""
    return "User-agent: *\nAllow: /\nSitemap: https://ucuz-yemek.ereboslab.com/sitemap.xml\n"


# Real, server-rendered multi-page frontend (city pages, chain-comparison
# pages, static pages, sitemap) -- see ucuz_yemek/pages.py. Kept as a router
# include so this JS-driven "/" route and the JSON API above stay untouched.
app.include_router(pages_router)
