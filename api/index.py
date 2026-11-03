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

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

# ucuz_yemek/ lives at the repo root, one level up from this api/ dir. Vercel's
# Python builder includes it via vercel.json's includeFiles; make sure it's
# importable regardless of the function's cwd (same pattern as darkvol/api/index.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ucuz_yemek import budget as budget_module  # noqa: E402
from ucuz_yemek import service  # noqa: E402
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


@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/budget")
def get_budget(
    budget: float = Query(..., gt=0, le=MAX_BUDGET_TRY, description="Budget in TRY, e.g. 300"),
    lat: float = Query(..., ge=-90, le=90, description="Latitude, e.g. 41.0422"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude, e.g. 29.0061"),
    limit: int = Query(30, ge=1, le=MAX_RESULTS, description="Max items to return, ranked by value"),
) -> JSONResponse:
    """Real, live items at or under `budget` TRY near (`lat`, `lon`), from
    both platforms (see ucuz_yemek/budget.py for each platform's real,
    honestly-scoped coverage). Every number is a live fetch made during this
    request -- there is no cache/mock fallback."""
    try:
        result = budget_module.find_affordable_items(budget, lat, lon)
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
        }
        for item in result.items[:limit]
    ]

    return JSONResponse(
        content={
            "budget_try": result.budget_try,
            "latitude": result.latitude,
            "longitude": result.longitude,
            "trendyol_restaurants_checked": result.trendyol_restaurants_checked,
            "yemeksepeti_chains_checked": result.yemeksepeti_chains_checked,
            "total_affordable_items_found": len(result.items),
            "items": items,
            "platform_errors": result.platform_errors,
            "scope_note": (
                "Trendyol Go: real nearest restaurants to this location. "
                "Yemeksepeti: a curated set of popular chains (no real "
                "location-search API exists on that platform yet) -- see "
                "README.md for why."
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

    matches: list[dict[str, Any]] = []
    for pair in result.summary.matches:
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
            "candidate_pairs": result.summary.candidate_pairs,
            "auto_accepted": result.summary.auto_accepted,
            "jev_accepted": result.summary.jev_accepted,
            "jev_rejected": result.summary.jev_rejected,
            "needs_review_count": len(result.summary.needs_review),
            "matches": matches,
        }
    )


_FRONTEND_HTML_PATH = Path(__file__).resolve().parent.parent / "web" / "index.html"


@app.get("/", response_class=HTMLResponse)
def frontend() -> str:
    return _FRONTEND_HTML_PATH.read_text(encoding="utf-8")


# Real, server-rendered multi-page frontend (city pages, chain-comparison
# pages, static pages, sitemap) -- see ucuz_yemek/pages.py. Kept as a router
# include so this JS-driven "/" route and the JSON API above stay untouched.
app.include_router(pages_router)
