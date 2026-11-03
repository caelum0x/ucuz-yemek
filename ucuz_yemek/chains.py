"""
Real, already-verified-reachable chains for the /karsilastir/{chain} page
family -- the same `CURATED_YEMEKSEPETI_CHAINS` budget.py already trusts for
its Yemeksepeti side, paired with a `trendyol_query` that actually matches
Trendyol Go's restaurant names (its search endpoint has no name-search
parameter -- see discovery.find_trendyol_restaurant -- so the query has to be
a plain-language substring of the real restaurant name, e.g. "burger king"
with a space, not the URL slug "burger-king").
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chain:
    slug: str
    display_name: str
    trendyol_query: str


CHAINS: tuple[Chain, ...] = (
    Chain("subway", "Subway", "subway"),
    Chain("burger-king", "Burger King", "burger king"),
    Chain("mcdonalds", "McDonald's", "mcdonalds"),
    Chain("kfc", "KFC", "kfc"),
    Chain("dominos", "Domino's Pizza", "dominos"),
    # Added 2026-11-04, same two-sided verification as the original 5 (see
    # plans/ucuz-yemek.md): real Yemeksepeti sitemap hit (hundreds of branch
    # slugs each, not a one-off) AND a real Trendyol Go search_restaurants
    # name match confirmed live via a ~150-point grid sweep across Istanbul
    # (a single fixed lat/lon doesn't have a branch of every chain nearby).
    Chain("little-caesars", "Little Caesars Pizza", "little caesars"),
    Chain("papa-johns", "Papa John's Pizza", "papa john"),
    Chain("kofteci-yusuf", "Köfteci Yusuf", "köfteci yusuf"),
    Chain("pizza-bulls", "Pizza Bulls", "pizza bulls"),
)

CHAINS_BY_SLUG: dict[str, Chain] = {chain.slug: chain for chain in CHAINS}
