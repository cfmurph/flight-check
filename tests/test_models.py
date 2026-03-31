"""Tests for data models."""

from datetime import datetime, timedelta, timezone
import pytest

from canada_flight_scanner.models import (
    FlightSegment,
    FlightItinerary,
    PriceBreakdown,
    FlightOffer,
    FlightDeal,
    ScanResult,
)


def _make_segment(origin="YYZ", dest="YVR", duration_mins=300) -> FlightSegment:
    dep = datetime(2026, 6, 15, 8, 0)
    return FlightSegment(
        origin=origin,
        destination=dest,
        departure_time=dep,
        arrival_time=dep + timedelta(minutes=duration_mins),
        carrier_code="AC",
        flight_number="115",
        aircraft="333",
        duration_minutes=duration_mins,
    )


def _make_offer(price=200.0, stops=0) -> FlightOffer:
    seg = _make_segment()
    segs = [seg]
    for _ in range(stops):
        segs.append(_make_segment("YYC", "YVR", 60))
    itin = FlightItinerary(segments=segs, total_duration_minutes=300)
    return FlightOffer(
        offer_id="o1",
        itineraries=[itin],
        price=PriceBreakdown(base=160.0, taxes=40.0, total=price),
        seats_available=5,
        booking_class="ECONOMY",
        validating_carrier="AC",
        last_ticketing_date="2026-06-10",
    )


class TestFlightSegment:
    def test_duration_str_hours_minutes(self):
        seg = _make_segment(duration_mins=285)
        assert seg.duration_str == "4h 45m"

    def test_duration_str_exact_hours(self):
        seg = _make_segment(duration_mins=120)
        assert seg.duration_str == "2h 00m"


class TestFlightItinerary:
    def test_origin_destination(self):
        seg1 = _make_segment("YYZ", "YYC", 120)
        seg2 = _make_segment("YYC", "YVR", 90)
        itin = FlightItinerary(segments=[seg1, seg2], total_duration_minutes=210)
        assert itin.origin == "YYZ"
        assert itin.destination == "YVR"

    def test_stops_nonstop(self):
        itin = FlightItinerary(segments=[_make_segment()], total_duration_minutes=300)
        assert itin.stops == 0

    def test_stops_one_connection(self):
        seg1 = _make_segment("YYZ", "YYC")
        seg2 = _make_segment("YYC", "YVR")
        itin = FlightItinerary(segments=[seg1, seg2], total_duration_minutes=400)
        assert itin.stops == 1


class TestFlightOffer:
    def test_is_one_way(self):
        offer = _make_offer()
        assert offer.is_one_way is True

    def test_origin_destination(self):
        offer = _make_offer()
        assert offer.origin == "YYZ"
        assert offer.destination == "YVR"

    def test_total_stops_nonstop(self):
        assert _make_offer(stops=0).total_stops == 0

    def test_total_stops_connection(self):
        assert _make_offer(stops=1).total_stops == 1


class TestPriceBreakdown:
    def test_total_cad(self):
        p = PriceBreakdown(base=100, taxes=25, total=125, currency="CAD")
        assert p.total_cad == pytest.approx(125.0)


class TestFlightDeal:
    def test_price_cad(self):
        offer = _make_offer(price=199.0)
        deal = FlightDeal(
            offer=offer,
            deal_score=75.0,
            avg_price_on_route=350.0,
            discount_pct=43.1,
            deal_tags=["NONSTOP", "GREAT_DEAL"],
        )
        assert deal.price_cad == pytest.approx(199.0)

    def test_route_label(self):
        offer = _make_offer()
        deal = FlightDeal(
            offer=offer,
            deal_score=60.0,
            avg_price_on_route=300.0,
            discount_pct=33.3,
        )
        assert deal.route_label == "YYZ → YVR"

    def test_departure_date_str(self):
        offer = _make_offer()
        deal = FlightDeal(offer=offer, deal_score=60.0, avg_price_on_route=300.0, discount_pct=33.3)
        assert "2026" in deal.departure_date_str


class TestScanResult:
    def test_duration_seconds(self):
        start = datetime(2026, 1, 1, 12, 0, 0)
        end = datetime(2026, 1, 1, 12, 1, 30)
        result = ScanResult(
            scan_id="abc",
            started_at=start,
            finished_at=end,
            routes_scanned=10,
            offers_evaluated=100,
            deals_found=[],
        )
        assert result.duration_seconds == pytest.approx(90.0)

    def test_top_deals_sorted(self):
        offer = _make_offer()
        deal_low = FlightDeal(offer=offer, deal_score=40.0, avg_price_on_route=300.0, discount_pct=20.0)
        deal_high = FlightDeal(offer=offer, deal_score=85.0, avg_price_on_route=300.0, discount_pct=50.0)
        result = ScanResult(
            scan_id="x",
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            finished_at=datetime.now(timezone.utc).replace(tzinfo=None),
            routes_scanned=1,
            offers_evaluated=2,
            deals_found=[deal_low, deal_high],
        )
        top = result.top_deals
        assert top[0].deal_score >= top[1].deal_score
