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
    uv run ucuz-yemek match --chain subway [--lat 41.0422] [--lon 29.0061]
                                  (real cross-platform SAME-ITEM matching: finds
                                   a live branch of --chain on each platform and
                                   matches individual menu items, not just
                                   restaurants, see ucuz_yemek/matching.py)
    uv run ucuz-yemek budget --budget 300 [--lat 41.0422] [--lon 29.0061]
                                  (real headline flow: "I have N TRY, what can I
                                   actually eat right now" -- live affordable
                                   items ranked by value across both platforms,
                                   see ucuz_yemek/budget.py. This is also what
                                   the web frontend in web/index.html calls via
                                   api/index.py's /api/budget.)
"""

from __future__ import annotations

import argparse
import sys

from ucuz_yemek import budget as budget_module
from ucuz_yemek import service, trendyol_go, yemeksepeti

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


def cmd_match(args: argparse.Namespace) -> int:
    print("=" * 60)
    print(f"Ucuz Yemek — real cross-platform SAME-ITEM matching for '{args.chain}'")
    print("=" * 60)
    print()

    print(f"[Trendyol Go] Searching near ({args.lat}, {args.lon}) for '{args.chain}' ...")
    print(f"[Yemeksepeti] Searching the live restaurant sitemap for '{args.chain}' ...")
    try:
        result = service.run_match(args.chain, args.lat, args.lon)
    except service.MatchServiceError as exc:
        print(f"  {exc}")
        return 1
    print(f"  Trendyol Go found: {result.trendyol_restaurant_name} (id {result.trendyol_restaurant_id})")
    print(f"  Yemeksepeti found: {result.yemeksepeti_url}")
    print()

    print(
        f"Live menus fetched: {result.trendyol_item_count} Trendyol Go items, "
        f"{result.yemeksepeti_item_count} Yemeksepeti items."
    )
    print("Ran blocking -> matching -> merge (Jev-adjudicated for ambiguous pairs).")
    print()

    summary = result.summary
    results = summary.matches
    print(
        f"Pipeline stats: {summary.candidate_pairs} candidate pairs considered "
        f"(blocking), {summary.auto_accepted} auto-matched by string alone, "
        f"{summary.jev_accepted} matched by Jev adjudication, "
        f"{summary.jev_rejected} rejected by Jev, "
        f"{len(summary.needs_review)} left needs_review (not matched, not fabricated)."
    )
    print()
    if not results:
        print(
            "No same-item matches found between these two live restaurants. This is a "
            "real, honest result (not an error) when the two branches/platforms don't "
            "share overlapping menu text for this chain right now."
        )
        return 0

    print(f"{len(results)} real same-item matches found:")
    print()
    method_counts: dict[str, int] = {}
    for match_result in results:
        method_counts[match_result.method] = method_counts.get(match_result.method, 0) + 1
        a, b = match_result.item_a, match_result.item_b
        cheaper = match_result.cheaper_platform
        if cheaper is None:
            price_note = f"same price ({a.price_try} TRY on both)"
        else:
            price_note = f"cheaper on {cheaper} by {match_result.price_diff_try} TRY"
        print(f"  - [{match_result.method}, confidence {match_result.confidence:.2f}]")
        print(f"      trendyol_go : {a.name} — {a.price_try} TRY")
        print(f"      yemeksepeti : {b.name} — {b.price_try} TRY")
        print(f"      -> {price_note}")
    print()
    print(f"Match methods used: {method_counts}")
    return 0


def cmd_budget(args: argparse.Namespace) -> int:
    print("=" * 60)
    print(f"Ucuz Yemek — real budget search: what can I eat for {args.budget:.0f} TRY?")
    print("=" * 60)
    print()
    print(f"Searching live near ({args.lat}, {args.lon}) ...")
    result = budget_module.find_affordable_items(args.budget, args.lat, args.lon)
    print(f"  Trendyol Go restaurants checked: {', '.join(result.trendyol_restaurants_checked)}")
    print(f"  Yemeksepeti chains checked: {', '.join(result.yemeksepeti_chains_checked)}")
    for platform, error in result.platform_errors.items():
        print(f"  WARNING: {platform} is offline this run, excluded (not fabricated): {error}")
    print()

    if not result.items:
        print("No real affordable items found for this budget/location right now.")
        return 0

    top = result.items[: args.limit]
    print(f"{len(result.items)} real affordable items found, top {len(top)} by value:")
    print()
    for item in top:
        print(f"    [{item.platform}] {item.restaurant_name} — {item.item_name}: {item.price_try} TRY")
    return 0


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

    p_match = sub.add_parser(
        "match", help="Real cross-platform same-item matching for one chain (Jev-powered)"
    )
    p_match.add_argument("--chain", default="subway")
    p_match.add_argument("--lat", type=float, default=41.0422)  # Beşiktaş, İstanbul
    p_match.add_argument("--lon", type=float, default=29.0061)
    p_match.set_defaults(func=cmd_match)

    p_budget = sub.add_parser(
        "budget",
        help="Real headline flow: live affordable items for a budget, ranked by value",
    )
    p_budget.add_argument("--budget", type=float, required=True, help="Budget in TRY, e.g. 300")
    p_budget.add_argument("--lat", type=float, default=41.0422)  # Beşiktaş, İstanbul
    p_budget.add_argument("--lon", type=float, default=29.0061)
    p_budget.add_argument("--limit", type=int, default=20)
    p_budget.set_defaults(func=cmd_budget)

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
