"""Tests for Amadeus API client (uses mocks - no real API calls)."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from canada_flight_scanner.api_client import (
    _parse_duration,
    _parse_datetime,
    _parse_segment,
    _parse_itinerary,
    _parse_offer,
    AmadeusFlightClient,
)


# --- Parser unit tests ---

class TestParseDuration:
    def test_hours_and_minutes(self):
        assert _parse_duration("PT2H35M") == 155

    def test_hours_only(self):
        assert _parse_duration("PT5H") == 300

    def test_minutes_only(self):
        assert _parse_duration("PT45M") == 45

    def test_invalid(self):
        assert _parse_duration("invalid") == 0

    def test_zero(self):
        assert _parse_duration("PT0M") == 0


class TestParseDatetime:
    def test_with_seconds(self):
        dt = _parse_datetime("2026-05-15T14:30:00")
        assert dt == datetime(2026, 5, 15, 14, 30, 0)

    def test_without_seconds(self):
        dt = _parse_datetime("2026-05-15T14:30")
        assert dt == datetime(2026, 5, 15, 14, 30)

    def test_invalid(self):
        with pytest.raises(ValueError):
            _parse_datetime("not-a-date")


SAMPLE_SEGMENT = {
    "departure": {"iataCode": "YYZ", "at": "2026-05-15T08:00"},
    "arrival": {"iataCode": "YVR", "at": "2026-05-15T10:45"},
    "carrierCode": "AC",
    "number": "115",
    "aircraft": {"code": "333"},
    "duration": "PT4H45M",
}

SAMPLE_OFFER = {
    "id": "offer-001",
    "itineraries": [
        {
            "duration": "PT4H45M",
            "segments": [SAMPLE_SEGMENT],
        }
    ],
    "price": {
        "currency": "CAD",
        "base": "150.00",
        "grandTotal": "200.00",
    },
    "numberOfBookableSeats": 4,
    "validatingAirlineCodes": ["AC"],
    "lastTicketingDate": "2026-05-10",
    "travelerPricings": [
        {
            "fareDetailsBySegment": [{"cabin": "ECONOMY"}]
        }
    ],
}


class TestParseSegment:
    def test_basic_parse(self):
        seg = _parse_segment(SAMPLE_SEGMENT)
        assert seg.origin == "YYZ"
        assert seg.destination == "YVR"
        assert seg.carrier_code == "AC"
        assert seg.flight_number == "115"
        assert seg.duration_minutes == 285

    def test_departure_time(self):
        seg = _parse_segment(SAMPLE_SEGMENT)
        assert seg.departure_time == datetime(2026, 5, 15, 8, 0)


class TestParseOffer:
    def test_offer_price(self):
        offer = _parse_offer(SAMPLE_OFFER)
        assert offer.price.total == pytest.approx(200.0)
        assert offer.price.base == pytest.approx(150.0)
        assert offer.price.taxes == pytest.approx(50.0)
        assert offer.price.currency == "CAD"

    def test_offer_seats(self):
        offer = _parse_offer(SAMPLE_OFFER)
        assert offer.seats_available == 4

    def test_offer_carrier(self):
        offer = _parse_offer(SAMPLE_OFFER)
        assert offer.validating_carrier == "AC"

    def test_offer_itineraries(self):
        offer = _parse_offer(SAMPLE_OFFER)
        assert len(offer.itineraries) == 1
        assert offer.origin == "YYZ"
        assert offer.destination == "YVR"

    def test_is_one_way(self):
        offer = _parse_offer(SAMPLE_OFFER)
        assert offer.is_one_way is True


class TestAmadeusFlightClient:
    def test_missing_credentials_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="credentials"):
                AmadeusFlightClient(client_id="", client_secret="")

    def test_init_with_credentials(self):
        with patch("canada_flight_scanner.api_client.Client") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            client = AmadeusFlightClient(
                client_id="test_id",
                client_secret="test_secret",
                environment="test",
            )
            assert client.client_id == "test_id"

    def test_search_one_way_returns_offers(self):
        with patch("canada_flight_scanner.api_client.Client") as mock_client_cls:
            mock_amadeus = MagicMock()
            mock_client_cls.return_value = mock_amadeus

            # Simulate a valid API response
            mock_response = MagicMock()
            mock_response.data = [SAMPLE_OFFER]
            mock_amadeus.shopping.flight_offers_search.get.return_value = mock_response

            client = AmadeusFlightClient(
                client_id="test_id", client_secret="test_secret"
            )
            offers = client.search_one_way("YYZ", "YVR", "2026-05-15")

            assert len(offers) == 1
            assert offers[0].origin == "YYZ"
            assert offers[0].price.total == pytest.approx(200.0)

    def test_search_one_way_api_error_returns_empty(self):
        from amadeus import ResponseError
        with patch("canada_flight_scanner.api_client.Client") as mock_client_cls:
            mock_amadeus = MagicMock()
            mock_client_cls.return_value = mock_amadeus

            mock_amadeus.shopping.flight_offers_search.get.side_effect = ResponseError(
                MagicMock(status_code=429, result={"errors": [{"detail": "rate limit"}]})
            )

            client = AmadeusFlightClient(
                client_id="test_id", client_secret="test_secret"
            )
            offers = client.search_one_way("YYZ", "YVR", "2026-05-15")
            assert offers == []
