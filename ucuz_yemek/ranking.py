"""
Real "best value" composite scoring -- a Weighted Sum Model (WSM) over
signals already present in the live Trendyol Go response (price, distance,
star rating), not a relevance/stars-only ranking like every competitor
ships (see plans/ucuz-yemek.md for the live-confirmed sponsored-bias bug
this was built to fix) and not a fabricated nutrition/portion model (no
real structured portion-size data exists on either platform -- confirmed
by inspecting real product payloads this session).

Deliberately dependency-free (no numpy/sklearn) -- this is ~15 real inputs
per request at most, plain Python is correct and fast enough.
"""

from __future__ import annotations


def _normalize(value: float, low: float, high: float, invert: bool = False) -> float:
    """Min-max normalize `value` into [0, 1] against the real range seen in
    THIS request's candidate set (not a global index -- there isn't one yet,
    see plans/ucuz-yemek.md P2.4). `invert=True` means lower is better."""
    if high <= low:
        return 0.5  # every candidate identical on this axis -- no signal, stay neutral
    frac = (value - low) / (high - low)
    frac = max(0.0, min(1.0, frac))
    return 1.0 - frac if invert else frac


def value_score(
    price_try: float,
    distance_km: float | None,
    rating: float | None,
    price_range: tuple[float, float],
    distance_range: tuple[float, float] | None,
    rating_range: tuple[float, float] | None,
    weights: tuple[float, float, float] = (0.5, 0.3, 0.2),
) -> float:
    """Composite value score in [0, 1], higher is better. Weights are
    (price_weight, distance_weight, rating_weight), real/owner-tunable
    constants, not learned -- there is no interaction/purchase history to
    learn from (see plans/ucuz-yemek.md's REJECTED section for why a real
    bandit/ML ranker isn't buildable yet).

    Missing axes (distance_range/rating_range is None, e.g. Yemeksepeti
    items with no rating field anywhere in the scraper) score a fixed
    neutral 0.5 on that axis rather than being dropped from the weighted
    sum -- dropping a missing axis shrinks the weight denominator and lets
    items with LESS real data outscore items with MORE real data purely for
    being data-poor (verified live: without this, a 1 TRY Yemeksepeti
    "Poşet" bag-fee line item outranked every real Trendyol entrée, since
    its only axis, price, is cheap and it has no distance/rating to drag
    the average down). A neutral 0.5 means "no opinion," never a reward."""
    price_w, distance_w, rating_w = weights
    price_score = _normalize(price_try, price_range[0], price_range[1], invert=True)
    distance_score = (
        _normalize(distance_km, distance_range[0], distance_range[1], invert=True)
        if distance_km is not None and distance_range is not None
        else 0.5
    )
    rating_score = (
        _normalize(rating, rating_range[0], rating_range[1], invert=False)
        if rating is not None and rating_range is not None
        else 0.5
    )
    total_weight = price_w + distance_w + rating_w
    if total_weight <= 0:
        return 0.0
    return (price_score * price_w + distance_score * distance_w + rating_score * rating_w) / total_weight
