"""Deal scoring and identification engine."""

import logging
import statistics
from typing import Dict, List, Tuple

from .models import FlightDeal, FlightOffer

logger = logging.getLogger(__name__)

# Score weights (must sum to 1.0)
WEIGHT_PRICE_DISCOUNT = 0.45   # How much below average the price is
WEIGHT_ABSOLUTE_PRICE = 0.25   # How cheap the fare is in absolute terms
WEIGHT_NONSTOP_BONUS = 0.15    # Bonus for non-stop flights
WEIGHT_SEATS_URGENCY = 0.10    # Scarcity bonus when seats are limited
WEIGHT_ADVANCE_WINDOW = 0.05   # Advance booking window (sweet spot)


def _price_discount_score(price: float, avg_price: float) -> float:
    """Score 0-100 based on how far below average this price is."""
    if avg_price <= 0:
        return 50.0
    discount_ratio = (avg_price - price) / avg_price
    # A 50%+ discount earns full score; negative discount earns 0
    clamped = max(0.0, min(1.0, discount_ratio / 0.50))
    return clamped * 100.0


def _absolute_price_score(price: float, max_deal_price: float = 400.0) -> float:
    """Score 0-100; prices at or below $50 get full score, scaling up to max_deal_price."""
    if price <= 50:
        return 100.0
    if price >= max_deal_price:
        return 0.0
    return ((max_deal_price - price) / (max_deal_price - 50)) * 100.0


def _nonstop_score(offer: FlightOffer) -> float:
    return 100.0 if offer.total_stops == 0 else max(0.0, 100.0 - offer.total_stops * 40.0)


def _seats_urgency_score(seats_available: int | None) -> float:
    if seats_available is None:
        return 50.0
    if seats_available <= 2:
        return 100.0
    if seats_available <= 5:
        return 75.0
    if seats_available <= 9:
        return 40.0
    return 10.0


def _advance_window_score(days_ahead: int) -> float:
    """
    Sweet spot for booking is roughly 3–8 weeks out.
    Very short notice or very far out get lower scores.
    """
    if 21 <= days_ahead <= 56:
        return 100.0
    if 7 <= days_ahead < 21:
        return 60.0 + (days_ahead - 7) * (40.0 / 14.0)
    if 56 < days_ahead <= 120:
        return 100.0 - (days_ahead - 56) * (60.0 / 64.0)
    if days_ahead > 120:
        return 40.0
    return 20.0  # very last minute (< 7 days)


def _build_tags(offer: FlightOffer, discount_pct: float, seats_available) -> List[str]:
    tags = []
    if offer.total_stops == 0:
        tags.append("NONSTOP")
    if discount_pct >= 40:
        tags.append("FLASH_SALE")
    elif discount_pct >= 25:
        tags.append("GREAT_DEAL")
    elif discount_pct >= 15:
        tags.append("GOOD_DEAL")
    if seats_available is not None and seats_available <= 3:
        tags.append("ALMOST_FULL")
    if offer.price.total <= 99:
        tags.append("SUB_$100")
    elif offer.price.total <= 149:
        tags.append("UNDER_$150")
    return tags


def compute_deal_score(
    offer: FlightOffer,
    avg_price: float,
    days_ahead: int,
) -> Tuple[float, float, List[str]]:
    """
    Compute a composite deal score for an offer.

    Returns:
        (score, discount_pct, tags)
    """
    price = offer.price.total
    discount_pct = max(0.0, (avg_price - price) / avg_price * 100.0) if avg_price > 0 else 0.0

    score = (
        WEIGHT_PRICE_DISCOUNT * _price_discount_score(price, avg_price)
        + WEIGHT_ABSOLUTE_PRICE * _absolute_price_score(price)
        + WEIGHT_NONSTOP_BONUS * _nonstop_score(offer)
        + WEIGHT_SEATS_URGENCY * _seats_urgency_score(offer.seats_available)
        + WEIGHT_ADVANCE_WINDOW * _advance_window_score(days_ahead)
    )

    tags = _build_tags(offer, discount_pct, offer.seats_available)
    return round(score, 2), round(discount_pct, 1), tags


def identify_deals(
    offers: List[FlightOffer],
    min_discount_pct: float = 15.0,
    max_price_threshold: float = 500.0,
    min_score: float = 30.0,
) -> List[FlightDeal]:
    """
    Given a list of offers for a single route + date range, identify deals.

    Strategy:
    1. Compute average price across all offers.
    2. Score each offer.
    3. Return offers that meet minimum discount and score thresholds.

    Args:
        offers: All offers for a route (mixed dates).
        min_discount_pct: Minimum percentage below average to qualify.
        max_price_threshold: Absolute price ceiling for deals in CAD.
        min_score: Minimum composite score (0-100).

    Returns:
        List of FlightDeal objects sorted by score descending.
    """
    if not offers:
        return []

    prices = [o.price.total for o in offers]
    avg_price = statistics.mean(prices)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    deals: List[FlightDeal] = []
    for offer in offers:
        days_ahead = (offer.outbound_departure - now).days
        if days_ahead < 0:
            continue  # past departure

        score, discount_pct, tags = compute_deal_score(offer, avg_price, days_ahead)

        qualifies = (
            discount_pct >= min_discount_pct
            or offer.price.total <= max_price_threshold * 0.5  # always flag very cheap fares
        ) and offer.price.total <= max_price_threshold and score >= min_score

        if qualifies:
            deals.append(
                FlightDeal(
                    offer=offer,
                    deal_score=score,
                    avg_price_on_route=round(avg_price, 2),
                    discount_pct=discount_pct,
                    deal_tags=tags,
                )
            )

    return sorted(deals, key=lambda d: d.deal_score, reverse=True)


def rank_deals_across_routes(
    route_deals: Dict[str, List[FlightDeal]],
    top_n: int = 50,
) -> List[FlightDeal]:
    """
    Flatten and rank deals from multiple routes into a single global top-N list.

    Args:
        route_deals: Mapping of "ORIGIN-DEST" → list of FlightDeal.
        top_n: Maximum number of deals to return.
    """
    all_deals = [deal for deals in route_deals.values() for deal in deals]
    return sorted(all_deals, key=lambda d: d.deal_score, reverse=True)[:top_n]
