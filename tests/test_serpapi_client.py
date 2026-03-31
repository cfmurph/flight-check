"""Tests for the SerpApi (Google Flights) client — no real API calls."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from canada_flight_scanner.serpapi_client import (
    _parse_datetime_str,
    _parse_flight_block,
    _parse_result_item,
    SerpApiFlightClient,
)


# ── Parser unit tests ──────────────────────────────────────────────────────────

class TestParseDatetimeStr:
    def test_standard_format(self):
        dt = _parse_datetime_str("2026-05-15 08:30")
        assert dt == datetime(2026, 5, 15, 8, 30)

    def test_iso_format(self):
        dt = _parse_datetime_str("2026-05-15T08:30")
        assert dt == datetime(2026, 5, 15, 8, 30)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_datetime_str("not-a-date")


SAMPLE_FLIGHTS = [
    {
        "departure_airport": {"name": "Toronto Pearson", "id": "YYZ", "time": "2026-06-01 07:00"},
        "arrival_airport":   {"name": "Vancouver Intl",  "id": "YVR", "time": "2026-06-01 09:45"},
        "duration": 285,
        "airplane": "Boeing 737",
        "airline": "Air Canada",
        "airline_logo": "https://example.com/ac.png",
        "travel_class": "Economy",
        "flight_number": "AC115",
        "legroom": "31 in",
        "extensions": [],
    }
]

SAMPLE_RESULT_ITEM = {
    "flights": SAMPLE_FLIGHTS,
    "layovers": [],
    "total_duration": 285,
    "price": 189,
    "type": "One way",
    "airline_logo": "https://example.com/ac.png",
    "departure_token": "abc123tok",
}

SAMPLE_SERP_RESPONSE = {
    "search_metadata": {"status": "Success"},
    "best_flights": [SAMPLE_RESULT_ITEM],
    "other_flights": [
        {
            "flights": SAMPLE_FLIGHTS,
            "total_duration": 285,
            "price": 220,
            "departure_token": "def456tok",
        }
    ],
}


class TestParseFlightBlock:
    def test_basic(self):
        itin = _parse_flight_block(SAMPLE_FLIGHTS, 285, "test-1")
        assert len(itin.segments) == 1
        seg = itin.segments[0]
        assert seg.origin == "YYZ"
        assert seg.destination == "YVR"
        assert seg.duration_minutes == 285
        assert seg.flight_number == "AC115"

    def test_carrier_code_extracted(self):
        itin = _parse_flight_block(SAMPLE_FLIGHTS, 285, "test-1")
        assert itin.segments[0].carrier_code == "AC"

    def test_total_duration_stored(self):
        itin = _parse_flight_block(SAMPLE_FLIGHTS, 285, "test-1")
        assert itin.total_duration_minutes == 285

    def test_bad_time_skips_segment(self):
        bad_flights = [
            {
                "departure_airport": {"id": "YYZ", "time": "bad-time"},
                "arrival_airport": {"id": "YVR", "time": "also-bad"},
                "duration": 0,
                "flight_number": "AC1",
            }
        ]
        itin = _parse_flight_block(bad_flights, 0, "test-bad")
        assert len(itin.segments) == 0


class TestParseResultItem:
    def test_normal_offer(self):
        offer = _parse_result_item(SAMPLE_RESULT_ITEM, 0)
        assert offer is not None
        assert offer.price.total == pytest.approx(189.0)
        assert offer.origin == "YYZ"
        assert offer.destination == "YVR"

    def test_price_breakdown(self):
        offer = _parse_result_item(SAMPLE_RESULT_ITEM, 0)
        assert offer.price.currency == "CAD"
        assert offer.price.base + offer.price.taxes == pytest.approx(offer.price.total, rel=1e-2)

    def test_source_is_google_flights(self):
        offer = _parse_result_item(SAMPLE_RESULT_ITEM, 0)
        assert offer.source == "GOOGLE_FLIGHTS"

    def test_no_price_returns_none(self):
        item = {**SAMPLE_RESULT_ITEM, "price": None}
        assert _parse_result_item(item, 0) is None

    def test_no_flights_returns_none(self):
        item = {**SAMPLE_RESULT_ITEM, "flights": []}
        assert _parse_result_item(item, 0) is None


# ── Client integration tests (mocked) ─────────────────────────────────────────

class TestSerpApiFlightClient:
    def test_missing_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="SERPAPI_KEY"):
                SerpApiFlightClient(api_key="")

    def test_search_one_way_returns_offers(self):
        with patch("canada_flight_scanner.serpapi_client.GoogleSearch") as mock_gs:
            mock_instance = MagicMock()
            mock_instance.get_dict.return_value = SAMPLE_SERP_RESPONSE
            mock_gs.return_value = mock_instance

            client = SerpApiFlightClient(api_key="test-key")
            offers = client.search_one_way("YYZ", "YVR", "2026-06-01")

            assert len(offers) == 2
            assert offers[0].origin == "YYZ"
            assert offers[0].price.total == pytest.approx(189.0)

    def test_search_one_way_sorts_cheapest_first(self):
        with patch("canada_flight_scanner.serpapi_client.GoogleSearch") as mock_gs:
            mock_instance = MagicMock()
            mock_instance.get_dict.return_value = SAMPLE_SERP_RESPONSE
            mock_gs.return_value = mock_instance

            client = SerpApiFlightClient(api_key="test-key")
            offers = client.search_one_way("YYZ", "YVR", "2026-06-01")
            # best_flights come first (index 0 = $189, other_flights = $220)
            assert offers[0].price.total <= offers[1].price.total

    def test_search_one_way_api_error_returns_empty(self):
        with patch("canada_flight_scanner.serpapi_client.GoogleSearch") as mock_gs:
            mock_gs.side_effect = Exception("network error")

            client = SerpApiFlightClient(api_key="test-key")
            offers = client.search_one_way("YYZ", "YVR", "2026-06-01")
            assert offers == []

    def test_max_results_respected(self):
        many_items = [SAMPLE_RESULT_ITEM] * 20
        big_response = {"best_flights": many_items, "other_flights": []}
        with patch("canada_flight_scanner.serpapi_client.GoogleSearch") as mock_gs:
            mock_instance = MagicMock()
            mock_instance.get_dict.return_value = big_response
            mock_gs.return_value = mock_instance

            client = SerpApiFlightClient(api_key="test-key")
            offers = client.search_one_way("YYZ", "YVR", "2026-06-01", max_results=3)
            assert len(offers) == 3

    def test_get_cheapest_date_offers(self):
        with patch("canada_flight_scanner.serpapi_client.GoogleSearch") as mock_gs:
            mock_instance = MagicMock()
            mock_instance.get_dict.return_value = SAMPLE_SERP_RESPONSE
            mock_gs.return_value = mock_instance

            client = SerpApiFlightClient(api_key="test-key")
            offers = client.get_cheapest_date_offers("YYZ", "YVR", "2026-06-01")
            assert len(offers) > 0
