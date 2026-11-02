"""
Ucuz Yemek CLI — prints REAL, live-fetched prices. Nothing in this file is
hardcoded/fabricated; every number comes from a live HTTP request made at run
time against the real platform(s).

Usage:
    uv run ucuz-yemek trendyol [--lat 40.9833] [--lon 29.0333] [--limit 10]
    uv run ucuz-yemek yemeksepeti --url https://www.yemeksepeti.com/restaurant/...
    uv run ucuz-yemek compare   (best-effort cross-platform view; see README for
                                  why this is NOT a real apples-to-apples
                                  comparison yet)
"""

from __future__ import annotations

import argparse
import sys

from ucuz_yemek import trendyol_go, yemeksepeti

DEFAULT_LAT = 40.9833  # Kadıköy, İstanbul
DEFAULT_LON = 29.0333

# Real restaurant URL pulled from Yemeksepeti's own public sitemap
# (/adventure-map/adventure-map-restaurant-0.xml), used in the probe and
# re-verified live during this build.
DEFAULT_YEMEKSEPETI_URL = "https://www.yemeksepeti.com/restaurant/eoa3/kadikoy-mezecisi-eoa3"


def cmd_trendyol(args: argparse.Namespace) -> int:
    restaurants = trendyol_go.search_restaurants(args.lat, args.lon)
    if not restaurants:
        print("No restaurants returned — the search itself may be rate-limited.")
        return 1

    target = restaurants[0]
    print(f"[Trendyol Go] Nearest result for ({args.lat}, {args.lon}):")
    print(f"  {target['name']} — rating {target.get('rating')} — id {target['id']}")
    print()

    menu = trendyol_go.get_restaurant_menu(target["id"], args.lat, args.lon)
    items = trendyol_go.flatten_menu_items(menu)[: args.limit]
    if not items:
        print("  (menu came back empty — restaurant may be temporarily closed)")
        return 0

    print(f"  Real menu prices for '{menu['info']['name']}':")
    for item in items:
        print(f"    - {item['name']}: {item['price_try']} TRY")
    return 0


def cmd_yemeksepeti(args: argparse.Namespace) -> int:
    print(f"[Yemeksepeti] Fetching {args.url} with a mobile User-Agent ...")
    html = yemeksepeti.fetch_restaurant_html(args.url)
    items = yemeksepeti.extract_priced_items(html, limit=args.limit)
    if not items:
        print(
            "  Got HTTP 200 but found no priced items in the embedded cache — "
            "the page layout may have changed, or PerimeterX served a soft block."
        )
        return 1

    print(f"  Real menu prices extracted from the live page ({len(items)} items):")
    for item in items:
        orig = item["original_price_try"]
        price = item["price_try"]
        suffix = f" (was {orig} TRY)" if orig and orig != price else ""
        print(f"    - {item['name']}: {price} TRY{suffix}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    print("=" * 60)
    print("Ucuz Yemek — cross-platform comparison (BEST EFFORT, NOT A REAL")
    print("apples-to-apples comparison yet — see README 'Known limitations')")
    print("=" * 60)
    print()
    trendyol_rc = cmd_trendyol(args)
    print()
    yemeksepeti_rc = cmd_yemeksepeti(
        argparse.Namespace(url=DEFAULT_YEMEKSEPETI_URL, limit=args.limit)
    )
    print()
    print(
        "NOTE: these are two DIFFERENT restaurants in two DIFFERENT systems — "
        "this prototype does not yet match the same restaurant/item across "
        "platforms (Yemeksepeti restaurant IDs and Trendyol Go restaurant IDs "
        "are unrelated, and there is no shared catalog to join on). This proves "
        "both fetchers work on real live data; it is NOT yet a real price "
        "comparison for the same order. See README.md."
    )
    return max(trendyol_rc, yemeksepeti_rc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ucuz-yemek")
    sub = parser.add_subparsers(dest="command", required=True)

    p_trendyol = sub.add_parser("trendyol", help="Fetch real Trendyol Go Yemek prices")
    p_trendyol.add_argument("--lat", type=float, default=DEFAULT_LAT)
    p_trendyol.add_argument("--lon", type=float, default=DEFAULT_LON)
    p_trendyol.add_argument("--limit", type=int, default=10)
    p_trendyol.set_defaults(func=cmd_trendyol)

    p_ys = sub.add_parser("yemeksepeti", help="Fetch real Yemeksepeti prices (fragile)")
    p_ys.add_argument("--url", default=DEFAULT_YEMEKSEPETI_URL)
    p_ys.add_argument("--limit", type=int, default=10)
    p_ys.set_defaults(func=cmd_yemeksepeti)

    p_compare = sub.add_parser("compare", help="Run both fetchers (see limitations)")
    p_compare.add_argument("--lat", type=float, default=DEFAULT_LAT)
    p_compare.add_argument("--lon", type=float, default=DEFAULT_LON)
    p_compare.add_argument("--limit", type=int, default=5)
    p_compare.set_defaults(func=cmd_compare)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 - CLI boundary, report and exit non-zero
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
