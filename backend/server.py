"""
Real standalone backend service for Ucuz Yemek.

Why this exists (owner correction 2026-11-03, see plans/ucuz-yemek.md): the
"backend" up to this point was just `api/index.py`, a stateless Vercel
serverless function that live-calls Trendyol Go/Yemeksepeti on *every single
request* -- no database, no caching, no scheduled job. That's not a real
backend service, it's a thin proxy. This module is the real thing: a
persistent FastAPI process backed by Postgres (see ucuz_yemek/cache_db.py)
that

1. runs a real scheduled job in-process (ucuz_yemek/refresh_job.py) to keep
   the cache warm for every supported city/chain, and
2. serves /api/budget from that cache first, falling back to a live call
   only on a genuine cache miss or stale entry (same budget.find_affordable_items
   logic the CLI and Vercel already use, just with use_cache=True).

This also directly addresses the real, still-open production bug this file
documents elsewhere: Vercel's hosting IP gets 403'd by Yemeksepeti's
anti-bot layer on every cold live call. A request served from this
backend's cache never makes that live call at all for a pre-warmed
city/chain -- it just reads Postgres. Wiring Vercel's own `/api/budget` to
read from the same database (via DATABASE_URL) is the concrete next step to
close that loop in production; not done in this pass because it requires an
actual production deploy + a reachable (not localhost) Postgres, both
deliberately staged rather than executed per the standing
ask-before-deploy/publish rule.

Run locally:
    docker run -d -p 15544:5432 -e POSTGRES_DB=ucuz_yemek -e POSTGRES_USER=ucuz_yemek \
        -e POSTGRES_PASSWORD=ucuz_yemek postgres:16-alpine
    DATABASE_URL=postgresql://ucuz_yemek:ucuz_yemek@localhost:15544/ucuz_yemek \
        uv run uvicorn backend.server:app --port 8811

Run via Docker Compose (backend/docker-compose.yml, staged, not yet deployed
anywhere public): `docker compose -f backend/docker-compose.yml up --build`
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from ucuz_yemek import budget, cache_db, refresh_job
from ucuz_yemek.json_api import router as json_api_router

logger = logging.getLogger("ucuz_yemek.backend")

REFRESH_INTERVAL_SECONDS = int(os.environ.get("UCUZ_YEMEK_REFRESH_INTERVAL_SECONDS", 6 * 60 * 60))
CACHE_TTL_SECONDS = int(os.environ.get("UCUZ_YEMEK_CACHE_TTL_SECONDS", 3600))
MAX_BUDGET_TRY = 10_000.0
MAX_RESULTS = 60


async def _refresh_loop() -> None:
    """The real scheduled job, run in the background for as long as this
    process lives. Runs once immediately on startup (so a fresh deploy
    doesn't serve an empty cache for hours), then every
    UCUZ_YEMEK_REFRESH_INTERVAL_SECONDS (default 6h)."""
    while True:
        try:
            result = await asyncio.to_thread(refresh_job.run_once)
            logger.info("scheduled cache refresh complete: %s", result)
        except Exception:
            logger.exception("scheduled cache refresh failed")
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache_db.init_schema()
    task = asyncio.create_task(_refresh_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="Ucuz Yemek Backend",
    description="Real Postgres-cached budget search backend -- see module docstring for why this exists.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/budget")
def get_budget(
    budget_try: float = Query(..., alias="budget", gt=0, le=MAX_BUDGET_TRY),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    limit: int = Query(30, ge=1, le=MAX_RESULTS),
    sort: str = Query(budget.DEFAULT_SORT_MODE),
    q: str | None = Query(None, max_length=80),
) -> dict[str, Any]:
    """Same real response shape as the Vercel `api/index.py`'s `/api/budget`
    (see that module) -- `cache_backed: true` is the one real difference:
    this reads Postgres first instead of calling Trendyol Go/Yemeksepeti
    live on every request. `q` filters the real cached/fetched items by
    substring match on item/restaurant name, same as api/index.py."""
    if sort not in budget.SORT_MODES:
        raise HTTPException(status_code=400, detail=f"unknown sort {sort!r}, expected one of {budget.SORT_MODES}")
    try:
        result = budget.find_affordable_items(
            budget_try, lat, lon, sort_mode=sort, use_cache=True, cache_ttl_seconds=CACHE_TTL_SECONDS, query=q
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "budget_try": result.budget_try,
        "latitude": result.latitude,
        "longitude": result.longitude,
        "sort": sort,
        "cache_backed": True,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "trendyol_restaurants_checked": result.trendyol_restaurants_checked,
        "yemeksepeti_chains_checked": result.yemeksepeti_chains_checked,
        "total_affordable_items_found": len(result.items),
        "items": [
            {
                "platform": item.platform,
                "restaurant_name": item.restaurant_name,
                "item_name": item.item_name,
                "price_try": item.price_try,
                "distance_km": item.distance_km,
                "rating": item.rating,
            }
            for item in result.items[:limit]
        ],
        "platform_errors": result.platform_errors or None,
    }


@app.post("/admin/refresh")
def trigger_refresh(x_admin_key: str | None = Header(default=None)) -> dict[str, Any]:
    """Manual on-demand trigger for the same real refresh job the
    background loop runs -- useful for ops ("warm the cache right now")
    without waiting for the next scheduled tick. Gated by a shared secret
    (UCUZ_YEMEK_ADMIN_KEY) when one is configured; open in local dev if
    unset, matching this backend's current single-operator scale."""
    expected = os.environ.get("UCUZ_YEMEK_ADMIN_KEY")
    if expected and x_admin_key != expected:
        raise HTTPException(status_code=403, detail="missing or incorrect X-Admin-Key header")
    return refresh_job.run_once()


# Same real combinatorial JSON API surface the Vercel api/index.py mounts
# (see ucuz_yemek/json_api.py) -- mirrored here for parity. /api/stats's
# cache fields are real here (this process always has a reachable
# DATABASE_URL, see lifespan() above), unlike the typically cache-less
# Vercel deployment.
app.include_router(json_api_router)
