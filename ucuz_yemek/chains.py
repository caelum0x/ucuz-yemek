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
)

CHAINS_BY_SLUG: dict[str, Chain] = {chain.slug: chain for chain in CHAINS}
