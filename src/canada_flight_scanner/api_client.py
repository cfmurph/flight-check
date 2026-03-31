"""Amadeus API client wrapper for flight offer searches."""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import List, Optional

from amadeus import Client, ResponseError

from .models import (
    FlightItinerary,
    FlightOffer,
    FlightSegment,
    PriceBreakdown,
)

logger = logging.getLogger(__name__)


def _parse_duration(iso_duration: str) -> int:
    """Convert ISO 8601 duration (e.g. PT2H35M) to total minutes."""
    import re
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso_duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    return hours * 60 + minutes


def _parse_datetime(dt_str: str) -> datetime:
    """Parse Amadeus datetime string (ISO 8601 without timezone)."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {dt_str}")


def _parse_segment(seg: dict) -> FlightSegment:
    dep = seg["departure"]
    arr = seg["arrival"]
    return FlightSegment(
        origin=dep["iataCode"],
        destination=arr["iataCode"],
        departure_time=_parse_datetime(dep["at"]),
        arrival_time=_parse_datetime(arr["at"]),
        carrier_code=seg["carrierCode"],
        flight_number=seg.get("number", ""),
        aircraft=seg.get("aircraft", {}).get("code", ""),
        duration_minutes=_parse_duration(seg.get("duration", "PT0M")),
    )


def _parse_itinerary(itin: dict) -> FlightItinerary:
    segments = [_parse_segment(s) for s in itin["segments"]]
    total_minutes = _parse_duration(itin.get("duration", "PT0M"))
    if total_minutes == 0:
        # Fallback: sum individual segment durations
        total_minutes = sum(s.duration_minutes for s in segments)
    return FlightItinerary(segments=segments, total_duration_minutes=total_minutes)


def _parse_offer(raw: dict) -> FlightOffer:
    price_data = raw.get("price", {})
    grand_total = float(price_data.get("grandTotal", price_data.get("total", 0)))
    base = float(price_data.get("base", 0))
    taxes = grand_total - base

    traveler_pricings = raw.get("travelerPricings", [{}])
    booking_class = ""
    if traveler_pricings:
        fare_details = traveler_pricings[0].get("fareDetailsBySegment", [{}])
        if fare_details:
            booking_class = fare_details[0].get("cabin", "")

    validating_carriers = raw.get("validatingAirlineCodes", [""])
    seats_raw = raw.get("numberOfBookableSeats")

    return FlightOffer(
        offer_id=raw.get("id", ""),
        itineraries=[_parse_itinerary(i) for i in raw.get("itineraries", [])],
        price=PriceBreakdown(
            base=base,
            taxes=taxes,
            total=grand_total,
            currency=price_data.get("currency", "CAD"),
        ),
        seats_available=int(seats_raw) if seats_raw is not None else None,
        booking_class=booking_class,
        validating_carrier=validating_carriers[0] if validating_carriers else "",
        last_ticketing_date=raw.get("lastTicketingDate"),
    )


class AmadeusFlightClient:
    """
    Thin wrapper around the Amadeus Python SDK focused on Canadian domestic
    flight offer searches.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        environment: Optional[str] = None,
    ):
        self.client_id = client_id or os.getenv("AMADEUS_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("AMADEUS_CLIENT_SECRET", "")
        env = environment or os.getenv("AMADEUS_ENV", "test")
        hostname = "production" if env == "production" else "test"

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Amadeus credentials not found. Set AMADEUS_CLIENT_ID and "
                "AMADEUS_CLIENT_SECRET environment variables or pass them explicitly."
            )

        self._client = Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            hostname=hostname,
            log_level="silent",
        )
        logger.info("Amadeus client initialised (env=%s)", env)

    def search_one_way(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        adults: int = 1,
        max_results: int = 10,
        currency: str = "CAD",
    ) -> List[FlightOffer]:
        """
        Search one-way flights.

        Args:
            origin: IATA code of origin airport.
            destination: IATA code of destination airport.
            departure_date: Date string in YYYY-MM-DD format.
            adults: Number of adult travellers.
            max_results: Maximum number of offers to return.
            currency: Price currency (default CAD).

        Returns:
            List of FlightOffer objects.
        """
        try:
            response = self._client.shopping.flight_offers_search.get(
                originLocationCode=origin,
                destinationLocationCode=destination,
                departureDate=departure_date,
                adults=adults,
                max=max_results,
                currencyCode=currency,
                nonStop="false",
            )
            return [_parse_offer(offer) for offer in response.data]
        except ResponseError as exc:
            logger.warning(
                "API error for %s→%s on %s: %s", origin, destination, departure_date, exc
            )
            return []

    def search_round_trip(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str,
        adults: int = 1,
        max_results: int = 10,
        currency: str = "CAD",
    ) -> List[FlightOffer]:
        """Search round-trip flights."""
        try:
            response = self._client.shopping.flight_offers_search.get(
                originLocationCode=origin,
                destinationLocationCode=destination,
                departureDate=departure_date,
                returnDate=return_date,
                adults=adults,
                max=max_results,
                currencyCode=currency,
                nonStop="false",
            )
            return [_parse_offer(offer) for offer in response.data]
        except ResponseError as exc:
            logger.warning(
                "API error for RT %s↔%s on %s/%s: %s",
                origin, destination, departure_date, return_date, exc,
            )
            return []

    def get_cheapest_date_offers(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        adults: int = 1,
        currency: str = "CAD",
    ) -> List[FlightOffer]:
        """
        Fetch up to 5 cheapest one-way offers for the given date with a built-in
        rate-limit back-off.
        """
        for attempt in range(3):
            offers = self.search_one_way(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                adults=adults,
                max_results=5,
                currency=currency,
            )
            if offers:
                return offers
            if attempt < 2:
                time.sleep(2 ** attempt)
        return []

    def search_date_range(
        self,
        origin: str,
        destination: str,
        start_date: datetime,
        end_date: datetime,
        adults: int = 1,
        currency: str = "CAD",
        rate_limit_pause: float = 0.25,
    ) -> List[FlightOffer]:
        """
        Search across every date in [start_date, end_date] and return all found offers.

        Args:
            rate_limit_pause: Seconds to sleep between each date request.
        """
        all_offers: List[FlightOffer] = []
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            offers = self.get_cheapest_date_offers(
                origin=origin,
                destination=destination,
                departure_date=date_str,
                adults=adults,
                currency=currency,
            )
            all_offers.extend(offers)
            current += timedelta(days=1)
            if rate_limit_pause > 0:
                time.sleep(rate_limit_pause)
        return all_offers
