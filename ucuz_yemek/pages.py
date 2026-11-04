"""
Real, server-rendered multi-page frontend -- city pages, chain-comparison
pages, static content pages, and the sitemap. All real data comes from the
SAME live functions the JSON API (`api/index.py`) already calls
(`budget.find_affordable_items`, `service.run_match`) -- no business logic is
duplicated or reimplemented here, this module only shapes real results into
server-rendered HTML.

Kept as one APIRouter (not merged into api/index.py) so the existing
JS-driven "/" route and JSON API stay untouched, and so Vercel's Python
builder -- which treats every file directly under `api/` as its own
function entry -- doesn't accidentally pick up a second file as a separate
route (see vercel.json). This module lives in `ucuz_yemek/`, a real Python
package already included via vercel.json's includeFiles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from ucuz_yemek import budget as budget_module
from ucuz_yemek import service
from ucuz_yemek.chains import CHAINS, CHAINS_BY_SLUG
from ucuz_yemek.cities import CITIES, CITIES_BY_SLUG, DEFAULT_CITY_BUDGET_TRY

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter()

DEFAULT_SEHIR_SLUG = "istanbul"
CITY_PAGE_ITEM_LIMIT = 24


def _origin(request: Request) -> str:
    """Real scheme+host for this request, honoring Vercel's forwarded
    headers (the request's own ASGI scope sees the internal host, not the
    public one, inside Vercel's Python runtime)."""
    host = request.headers.get("x-forwarded-host") or request.url.hostname or "ucuz-yemek.ereboslab.com"
    scheme = request.headers.get("x-forwarded-proto") or "https"
    return f"{scheme}://{host}"


def _canonical_url(request: Request) -> str:
    path = request.url.path
    query = f"?{request.url.query}" if request.url.query else ""
    return f"{_origin(request)}{path}{query}"


@router.get("/sehir/{city_slug}", response_class=Response)
def city_page(request: Request, city_slug: str):
    city = CITIES_BY_SLUG.get(city_slug)
    if city is None:
        raise HTTPException(status_code=404, detail=f"Unknown city slug: {city_slug!r}")

    budget_try = DEFAULT_CITY_BUDGET_TRY
    items: list[dict[str, Any]] = []
    platform_errors: dict[str, str] = {}
    total_found = 0
    try:
        result = budget_module.find_affordable_items(budget_try, city.latitude, city.longitude)
        total_found = len(result.items)
        platform_errors = result.platform_errors
        items = [
            {
                "platform": item.platform,
                "restaurant_name": item.restaurant_name,
                "item_name": item.item_name,
                "price_try": item.price_try,
            }
            for item in result.items[:CITY_PAGE_ITEM_LIMIT]
        ]
    except Exception as exc:  # both platforms down this request -- show honestly, never fabricate
        platform_errors = {"trendyol_go": str(exc), "yemeksepeti": str(exc)}

    return templates.TemplateResponse(
        request,
        "city.html",
        {
            "city": city,
            "budget_try": budget_try,
            "items": items,
            "total_found": total_found,
            "platform_errors": platform_errors,
            "cities": CITIES,
            "chains": CHAINS,
            "canonical_url": _canonical_url(request),
        },
    )


@router.get("/karsilastir/{chain_slug}", response_class=Response)
def chain_compare_page(request: Request, chain_slug: str, sehir: str = DEFAULT_SEHIR_SLUG):
    chain = CHAINS_BY_SLUG.get(chain_slug)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Unknown chain slug: {chain_slug!r}")
    city = CITIES_BY_SLUG.get(sehir)
    if city is None:
        raise HTTPException(status_code=404, detail=f"Unknown city slug: {sehir!r}")

    result = None
    error: str | None = None
    try:
        result = service.run_match(chain.trendyol_query, city.latitude, city.longitude)
    except service.MatchServiceError as exc:
        error = str(exc)
    except Exception as exc:  # real upstream fetch failure -- never fabricate a comparison
        error = f"Upstream real-data fetch failed: {exc}"

    return templates.TemplateResponse(
        request,
        "chain_compare.html",
        {
            "chain": chain,
            "city": city,
            "result": result,
            "error": error,
            "cities": CITIES,
            "chains": CHAINS,
            "canonical_url": _canonical_url(request),
        },
    )


@router.get("/hakkimizda", response_class=Response)
def about_page(request: Request):
    return templates.TemplateResponse(request, "about.html", {"canonical_url": _canonical_url(request)})


@router.get("/gizlilik", response_class=Response)
def privacy_page(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {"canonical_url": _canonical_url(request)})


@router.get("/sss", response_class=Response)
def faq_page(request: Request):
    return templates.TemplateResponse(request, "faq.html", {"canonical_url": _canonical_url(request)})


def _all_real_locs() -> list[str]:
    """Every real, crawlable route this module (plus the existing `/`) adds,
    used both by /sitemap.xml and by the test that counts total new
    routes."""
    locs = ["/"]
    locs += [f"/sehir/{city.slug}" for city in CITIES]
    locs += [f"/karsilastir/{chain.slug}?sehir={city.slug}" for chain in CHAINS for city in CITIES]
    locs += ["/hakkimizda", "/gizlilik", "/sss"]
    return locs


def real_page_count() -> int:
    """Real count of every crawlable HTML route this module (plus the
    existing `/`) adds -- used by /api/stats (ucuz_yemek/json_api.py) so the
    JSON surface reports the real same number the sitemap itself serves,
    not a separately-maintained (and possibly stale) copy."""
    return len(_all_real_locs())


@router.get("/sitemap.xml")
def sitemap(request: Request):
    return templates.TemplateResponse(
        request,
        "sitemap.xml",
        {"base_url": _origin(request), "locs": _all_real_locs()},
        media_type="application/xml",
    )
