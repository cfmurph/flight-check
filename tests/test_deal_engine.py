"""Tests for deal scoring engine."""

import pytest
from datetime import datetime, timedelta, timezone

from canada_flight_scanner.deal_engine import (
    _absolute_price_score,
    _nonstop_score,
    _price_discount_score,
    _advance_window_score,
    compute_deal_score,
    identify_deals,
    rank_deals_across_routes,
)
from canada_flight_scanner.models import (
    FlightItinerary,
    FlightOffer,
    FlightSegment,
    PriceBreakdown,
)


def _make_offer(
    price: float,
    stops: int = 0,
    days_from_now: int = 30,
    seats: int = None,
    offer_id: str = "test-1",
) -> FlightOffer:
    departure = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=days_from_now)
    seg = FlightSegment(
        origin="YYZ",
        destination="YVR",
        departure_time=departure,
        arrival_time=departure + timedelta(hours=5),
        carrier_code="AC",
        flight_number="100",
        aircraft="320",
        duration_minutes=300,
    )
    segments = [seg]
    # add connecting segments for stops
    for i in range(stops):
        conn_dep = seg.arrival_time + timedelta(hours=1)
        conn = FlightSegment(
            origin="YYC",
            destination="YVR",
            departure_time=conn_dep,
            arrival_time=conn_dep + timedelta(hours=1),
            carrier_code="AC",
            flight_number=f"20{i}",
            aircraft="E75",
            duration_minutes=60,
        )
        segments.append(conn)

    itin = FlightItinerary(segments=segments, total_duration_minutes=300 + stops * 120)
    return FlightOffer(
        offer_id=offer_id,
        itineraries=[itin],
        price=PriceBreakdown(base=price * 0.8, taxes=price * 0.2, total=price),
        seats_available=seats,
        booking_class="ECONOMY",
        validating_carrier="AC",
        last_ticketing_date=None,
    )


# --- Unit tests for scoring helpers ---

class TestPriceDiscountScore:
    def test_no_discount(self):
        score = _price_discount_score(200, 200)
        assert score == pytest.approx(0.0)

    def test_full_discount(self):
        # 50%+ discount should earn 100
        score = _price_discount_score(100, 200)
        assert score == pytest.approx(100.0)

    def test_mid_discount(self):
        # 25% discount = 50 score
        score = _price_discount_score(150, 200)
        assert 40.0 <= score <= 60.0

    def test_zero_avg(self):
        score = _price_discount_score(100, 0)
        assert score == pytest.approx(50.0)


class TestAbsolutePriceScore:
    def test_very_cheap(self):
        assert _absolute_price_score(49) == pytest.approx(100.0)

    def test_over_threshold(self):
        assert _absolute_price_score(500) == pytest.approx(0.0)

    def test_midrange(self):
        score = _absolute_price_score(225)
        assert 0 < score < 100


class TestNonstopScore:
    def test_nonstop_full_score(self):
        offer = _make_offer(100, stops=0)
        assert _nonstop_score(offer) == pytest.approx(100.0)

    def test_one_stop(self):
        offer = _make_offer(100, stops=1)
        assert _nonstop_score(offer) < 100.0

    def test_two_stops(self):
        offer = _make_offer(100, stops=2)
        assert _nonstop_score(offer) < _nonstop_score(_make_offer(100, stops=1))


class TestAdvanceWindowScore:
    def test_sweet_spot(self):
        assert _advance_window_score(35) == pytest.approx(100.0)

    def test_very_last_minute(self):
        assert _advance_window_score(2) < 30.0

    def test_far_out(self):
        assert _advance_window_score(180) < 50.0


# --- Integration tests ---

class TestComputeDealScore:
    def test_score_range(self):
        offer = _make_offer(150)
        score, discount, tags = compute_deal_score(offer, avg_price=300, days_ahead=35)
        assert 0.0 <= score <= 100.0

    def test_cheap_nonstop_high_score(self):
        offer = _make_offer(99, stops=0)
        score, _, _ = compute_deal_score(offer, avg_price=300, days_ahead=35)
        assert score >= 60.0

    def test_expensive_low_score(self):
        offer = _make_offer(480, stops=2)
        score, _, _ = compute_deal_score(offer, avg_price=300, days_ahead=35)
        assert score < 60.0

    def test_tags_nonstop(self):
        offer = _make_offer(80, stops=0)
        _, _, tags = compute_deal_score(offer, avg_price=300, days_ahead=35)
        assert "NONSTOP" in tags

    def test_tags_flash_sale(self):
        offer = _make_offer(100)
        _, _, tags = compute_deal_score(offer, avg_price=300, days_ahead=35)
        assert "FLASH_SALE" in tags


class TestIdentifyDeals:
    def _make_offers(self):
        return [
            _make_offer(500, offer_id="expensive"),
            _make_offer(120, stops=0, offer_id="cheap-nonstop"),
            _make_offer(89, stops=1, offer_id="very-cheap"),
            _make_offer(450, offer_id="mid"),
        ]

    def test_empty_input(self):
        assert identify_deals([]) == []

    def test_cheap_offers_become_deals(self):
        offers = self._make_offers()
        deals = identify_deals(offers, min_discount_pct=10.0, max_price_threshold=500.0)
        deal_ids = {d.offer.offer_id for d in deals}
        # The very cheap offers should be flagged
        assert "very-cheap" in deal_ids or "cheap-nonstop" in deal_ids

    def test_deals_sorted_by_score(self):
        offers = self._make_offers()
        deals = identify_deals(offers, min_discount_pct=10.0)
        scores = [d.deal_score for d in deals]
        assert scores == sorted(scores, reverse=True)

    def test_past_departures_excluded(self):
        past = _make_offer(50, days_from_now=-5)
        future = _make_offer(80, days_from_now=30, offer_id="future")
        deals = identify_deals([past, future], min_discount_pct=0.0, min_score=0.0)
        deal_ids = {d.offer.offer_id for d in deals}
        assert "test-1" not in deal_ids  # past offer excluded


class TestRankDealsAcrossRoutes:
    def test_top_n_limit(self):
        offers_a = [_make_offer(100, offer_id=f"a{i}") for i in range(5)]
        offers_b = [_make_offer(90, offer_id=f"b{i}") for i in range(5)]
        deals_a = identify_deals(offers_a, min_discount_pct=0.0, min_score=0.0)
        deals_b = identify_deals(offers_b, min_discount_pct=0.0, min_score=0.0)
        result = rank_deals_across_routes({"YYZ-YVR": deals_a, "YUL-YYC": deals_b}, top_n=3)
        assert len(result) <= 3

    def test_global_sort_order(self):
        cheap = [_make_offer(80, offer_id="cheap")]
        expensive = [_make_offer(490, offer_id="exp")]
        cheap_deals = identify_deals(cheap, min_discount_pct=0.0, min_score=0.0)
        exp_deals = identify_deals(expensive, min_discount_pct=0.0, min_score=0.0)
        if cheap_deals and exp_deals:
            result = rank_deals_across_routes(
                {"R1": cheap_deals, "R2": exp_deals}, top_n=10
            )
            scores = [d.deal_score for d in result]
            assert scores == sorted(scores, reverse=True)
