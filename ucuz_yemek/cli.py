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
"""

from __future__ import annotations

import argparse
import sys

from ucuz_yemek import discovery, matching, trendyol_go, yemeksepeti

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


def _dedupe_items(items) -> list[matching.MenuItem]:
    """Real restaurant menus repeat the same item across multiple display
    sections (e.g. a 'recommended' section duplicating the main list) --
    dedupe by (name, price) so matching spends its Jev budget on genuinely
    different items, not the same listing counted five times."""
    seen: set[tuple[str, float]] = set()
    result: list[matching.MenuItem] = []
    for item in items:
        key = (item.name, item.price_try)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def cmd_match(args: argparse.Namespace) -> int:
    print("=" * 60)
    print(f"Ucuz Yemek — real cross-platform SAME-ITEM matching for '{args.chain}'")
    print("=" * 60)
    print()

    print(f"[Trendyol Go] Searching near ({args.lat}, {args.lon}) for '{args.chain}' ...")
    trendyol_restaurant = discovery.find_trendyol_restaurant(args.chain, args.lat, args.lon)
    if trendyol_restaurant is None:
        print(f"  No live Trendyol Go restaurant matching '{args.chain}' near that point.")
        return 1
    print(f"  Found: {trendyol_restaurant['name']} (id {trendyol_restaurant['id']})")

    print(f"[Yemeksepeti] Searching the live restaurant sitemap for '{args.chain}' ...")
    yemeksepeti_url = discovery.find_yemeksepeti_restaurant_url(args.chain)
    if yemeksepeti_url is None:
        print(f"  No live Yemeksepeti restaurant matching '{args.chain}' in the sitemap.")
        return 1
    print(f"  Found: {yemeksepeti_url}")
    print()

    menu = trendyol_go.get_restaurant_menu(trendyol_restaurant["id"], args.lat, args.lon)
    trendyol_items = _dedupe_items(
        matching.MenuItem("trendyol_go", item["name"], item["price_try"], item)
        for item in trendyol_go.flatten_menu_items(menu)
        if item["price_try"] is not None
    )

    html = yemeksepeti.fetch_restaurant_html(yemeksepeti_url)
    yemeksepeti_items = _dedupe_items(
        matching.MenuItem("yemeksepeti", item["name"], item["price_try"], item)
        for item in yemeksepeti.extract_priced_items(html, limit=500)
    )

    print(
        f"Live menus fetched: {len(trendyol_items)} Trendyol Go items, "
        f"{len(yemeksepeti_items)} Yemeksepeti items."
    )
    print("Running blocking -> matching -> merge (Jev-adjudicated for ambiguous pairs) ...")
    print()

    summary = matching.match_menus_detailed(trendyol_items, yemeksepeti_items)
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
    for result in results:
        method_counts[result.method] = method_counts.get(result.method, 0) + 1
        a, b = result.item_a, result.item_b
        cheaper = result.cheaper_platform
        if cheaper is None:
            price_note = f"same price ({a.price_try} TRY on both)"
        else:
            price_note = f"cheaper on {cheaper} by {result.price_diff_try} TRY"
        print(f"  - [{result.method}, confidence {result.confidence:.2f}]")
        print(f"      trendyol_go : {a.name} — {a.price_try} TRY")
        print(f"      yemeksepeti : {b.name} — {b.price_try} TRY")
        print(f"      -> {price_note}")
    print()
    print(f"Match methods used: {method_counts}")
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
