"""
Real cross-platform same-item matching: given two live menu item lists (one
per food-delivery platform), find the pairs that are the SAME real-world
product so their prices can be compared directly.

This is the gap the README explicitly flagged: `compare` fetched two live
restaurants side by side but never matched individual items across them.

Architecture follows the standard entity-fusion pipeline (blocking -> matching
-> merge policy), the same approach used for deduplicating entities across
knowledge-graph sources:

1. Blocking (cheap, deterministic): normalize each item name and score every
   cross-platform pair with token-set Jaccard similarity. Never spend an LLM
   call on a pair with near-zero word overlap.
2. Matching (layered):
   - exact normalized string match -> auto-accept, no API call needed.
   - very high Jaccard -> auto-accept (clear case, string layer alone decides).
   - very low Jaccard -> auto-reject (already filtered by blocking; redundant
     safety net).
   - the ambiguous middle band -> real adjudication via Jev (TypeSafe's Noul
     primitive: "is this the same product?"), because naive string similarity
     cannot tell "Teriyaki Tavuk Sandviç (15 cm) Menü" from the 30 cm version
     (high word overlap, different product/price) -- this is exactly the kind
     of judgment System One is for, not a rule a regex could encode reliably.
3. Merge policy (deterministic code, not model judgment): every match carries
   its own method/confidence and both platforms' real prices with provenance,
   never a silent overwrite. Low-confidence Jev answers are flagged
   "needs_review" rather than forced into match or no-match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ucuz_yemek import jev

# Blocking / matching thresholds. Tuned by hand against real Subway menu data
# pulled live from both platforms during this build (see plans/ucuz-yemek.md).
BLOCK_MIN_JACCARD = 0.45  # below this, don't even consider the pair a candidate
AUTO_ACCEPT_JACCARD = 0.92  # near-identical strings, skip the API call entirely
JEV_ACCEPT_THRESHOLD = 0.7
JEV_REJECT_THRESHOLD = 0.3
JEV_BATCH_SIZE = 20  # keeps each real request well under the API's token limit

_PUNCT_RE = re.compile(r"[.,’'\"®™]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, drop decorative punctuation (periods inside '30 cm.', curly
    quotes, trademark marks), collapse whitespace. Deliberately does NOT strip
    size tokens like '(15 cm)' -- those are part of what makes two items the
    same or different product, so normalization must keep them legible to
    both the Jaccard blocker and the Jev adjudicator."""
    cleaned = _PUNCT_RE.sub("", name.lower())
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def _tokens(normalized_name: str) -> set[str]:
    return set(normalized_name.split())


def jaccard(tokens_a: set[str], tokens_b: set[str]) -> float:
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union


@dataclass(frozen=True)
class MenuItem:
    """A real priced item from one platform's live menu. `platform` and
    `raw` keep provenance so a match result can always be traced back."""

    platform: str
    name: str
    price_try: float
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MatchResult:
    item_a: MenuItem
    item_b: MenuItem
    method: str  # "exact" | "string-high" | "jev" | "needs_review"
    confidence: float  # jaccard for string methods, noul probability for jev
    accepted: bool

    @property
    def cheaper_platform(self) -> str | None:
        if self.item_a.price_try == self.item_b.price_try:
            return None
        return self.item_a.platform if self.item_a.price_try < self.item_b.price_try else self.item_b.platform

    @property
    def price_diff_try(self) -> float:
        return round(abs(self.item_a.price_try - self.item_b.price_try), 2)


def _candidate_pairs(items_a: list[MenuItem], items_b: list[MenuItem]):
    """Blocking stage: yield (item_a, item_b, jaccard) for every pair whose
    normalized token sets overlap enough to be worth a real decision. This
    is what keeps the Jev call count at O(ambiguous pairs), not O(n*m)."""
    normalized_b = [(item, _tokens(normalize_name(item.name))) for item in items_b]
    for item_a in items_a:
        tokens_a = _tokens(normalize_name(item_a.name))
        for item_b, tokens_b in normalized_b:
            score = jaccard(tokens_a, tokens_b)
            if score >= BLOCK_MIN_JACCARD:
                yield item_a, item_b, score


@dataclass(frozen=True)
class MatchSummary:
    """Full transparency on what the pipeline decided and why, not just the
    winning matches -- callers can report how many candidates were ever
    considered, how many Jev correctly rejected, and how many are genuinely
    ambiguous rather than silently dropped."""

    matches: list[MatchResult]
    candidate_pairs: int
    auto_accepted: int  # exact or string-high, no API call
    jev_accepted: int
    jev_rejected: int
    needs_review: list[MatchResult]


def match_menus_detailed(items_a: list[MenuItem], items_b: list[MenuItem]) -> MatchSummary:
    """Run the full blocking -> matching -> merge pipeline on two real,
    live-fetched menu item lists and return every accepted/needs-review match
    plus full pipeline stats. Each source item is used in at most one accepted
    match (greedy, highest confidence first) so one Subway sandwich isn't
    matched to five different sizes on the other platform."""
    candidates = list(_candidate_pairs(items_a, items_b))

    # Resolve the cheap, unambiguous cases without ever calling Jev.
    resolved: list[MatchResult] = []
    undecided: list[tuple[MenuItem, MenuItem, float]] = []
    for item_a, item_b, score in candidates:
        norm_a = normalize_name(item_a.name)
        norm_b = normalize_name(item_b.name)
        if norm_a == norm_b:
            resolved.append(MatchResult(item_a, item_b, "exact", 1.0, accepted=True))
        elif score >= AUTO_ACCEPT_JACCARD:
            resolved.append(MatchResult(item_a, item_b, "string-high", score, accepted=True))
        else:
            undecided.append((item_a, item_b, score))

    # The ambiguous middle band: real Jev adjudication, batched in chunks small
    # enough to stay under the API's per-request token limit.
    state = (
        "Matching menu items for a price-comparison tool across two real Turkish "
        "food-delivery platforms (same restaurant chain, different apps)."
    )
    for start in range(0, len(undecided), JEV_BATCH_SIZE):
        chunk = undecided[start : start + JEV_BATCH_SIZE]
        questions = {}
        for i, (item_a, item_b, _score) in enumerate(chunk):
            questions[f"pair_{i}"] = {
                "instructions": {
                    "task": (
                        "Two Turkish food-delivery apps list menu items with slightly "
                        "different text. Do these two listings refer to the exact same "
                        "product, including the same size/variant, just written "
                        "differently (punctuation, spacing, capitalization, word order)?"
                    ),
                    "item_on_platform_a": item_a.name,
                    "item_on_platform_b": item_b.name,
                },
                "criteria": {
                    "true": (
                        "Same food/drink item and same size or variant; differences are "
                        "only cosmetic text formatting."
                    ),
                    "false": (
                        "Different product, different flavor, or a different size/variant "
                        "(e.g. 15 cm vs 30 cm, regular vs zero-sugar, a combo/menu vs the "
                        "item alone)."
                    ),
                },
            }
        answers = jev.ask_noul_batch(state, questions)
        for i, (item_a, item_b, _score) in enumerate(chunk):
            noul = answers[f"pair_{i}"]
            if noul >= JEV_ACCEPT_THRESHOLD:
                resolved.append(MatchResult(item_a, item_b, "jev", noul, accepted=True))
            elif noul <= JEV_REJECT_THRESHOLD:
                resolved.append(MatchResult(item_a, item_b, "jev", noul, accepted=False))
            else:
                # Per TypeSafe's own confidence guidance: a mid-range Noul isn't a
                # weak match, it's a genuinely unclear case -- don't silently merge.
                resolved.append(MatchResult(item_a, item_b, "needs_review", noul, accepted=False))

    # Merge policy: keep only accepted matches, greedy by confidence, each
    # source item used at most once so a 15cm sub never "wins" a match slot
    # for the 30cm listing too.
    accepted_sorted = sorted(
        (r for r in resolved if r.accepted), key=lambda r: r.confidence, reverse=True
    )
    used_a: set[int] = set()
    used_b: set[int] = set()
    final: list[MatchResult] = []
    for result in accepted_sorted:
        key_a, key_b = id(result.item_a), id(result.item_b)
        if key_a in used_a or key_b in used_b:
            continue
        used_a.add(key_a)
        used_b.add(key_b)
        final.append(result)

    final.sort(key=lambda r: r.item_a.name)

    return MatchSummary(
        matches=final,
        candidate_pairs=len(candidates),
        auto_accepted=sum(1 for r in resolved if r.method in ("exact", "string-high")),
        jev_accepted=sum(1 for r in resolved if r.method == "jev" and r.accepted),
        jev_rejected=sum(1 for r in resolved if r.method == "jev" and not r.accepted),
        needs_review=[r for r in resolved if r.method == "needs_review"],
    )


def match_menus(items_a: list[MenuItem], items_b: list[MenuItem]) -> list[MatchResult]:
    """Convenience wrapper returning just the winning matches. Prefer
    `match_menus_detailed` when the caller wants to report pipeline stats."""
    return match_menus_detailed(items_a, items_b).matches


def serialize_summary(summary: MatchSummary) -> dict[str, Any]:
    """Shared real-match-result JSON shaping, used by every HTTP endpoint
    that returns a MatchSummary (api/index.py's /api/match and
    /api/match-by-url, ucuz_yemek/json_api.py's /api/chains/{slug}/compare)
    -- one real serialization, no duplicated logic per endpoint."""
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
