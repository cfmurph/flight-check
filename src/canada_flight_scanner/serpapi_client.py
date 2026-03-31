"""
SerpApi (Google Flights) client — drop-in replacement for AmadeusFlightClient.

Free tier: 100 searches/month at https://serpapi.com
Sign up: https://serpapi.com/users/sign_up
Set SERPAPI_KEY in your .env file.

Response docs: https://serpapi.com/google-flights-api
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import List, Optional

from serpapi import GoogleSearch

from .models import (
    FlightItinerary,
    FlightOffer,
    FlightSegment,
    PriceBreakdown,
)

logger = logging.getLogger(__name__)


def _parse_datetime_str(dt_str: str) -> datetime:
    """Parse Google Flights datetime string 'YYYY-MM-DD HH:MM'."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {dt_str!r}")


def _duration_to_minutes(minutes_int: int) -> int:
    return int(minutes_int)


def _parse_flight_block(flights: list, total_duration: int, offer_id: str) -> FlightItinerary:
    """Convert a SerpApi 'flights' array (one itinerary) into a FlightItinerary."""
    segments = []
    for fl in flights:
        dep_airport = fl.get("departure_airport", {})
        arr_airport = fl.get("arrival_airport", {})
        dep_time_str = dep_airport.get("time", "")
        arr_time_str = arr_airport.get("time", "")

        try:
            dep_dt = _parse_datetime_str(dep_time_str)
            arr_dt = _parse_datetime_str(arr_time_str)
        except ValueError:
            logger.debug("Could not parse times for offer %s, skipping segment", offer_id)
            continue

        duration_mins = fl.get("duration", 0)
        flight_number = fl.get("flight_number", "")
        carrier_code = flight_number[:2] if len(flight_number) >= 2 else ""

        segments.append(FlightSegment(
            origin=dep_airport.get("id", ""),
            destination=arr_airport.get("id", ""),
            departure_time=dep_dt,
            arrival_time=arr_dt,
            carrier_code=carrier_code,
            flight_number=flight_number,
            aircraft=fl.get("airplane", ""),
            duration_minutes=duration_mins,
        ))

    return FlightItinerary(
        segments=segments,
        total_duration_minutes=total_duration,
    )


def _parse_result_item(item: dict, offer_idx: int, currency: str = "CAD") -> Optional[FlightOffer]:
    """Parse one entry from best_flights or other_flights into a FlightOffer."""
    flights = item.get("flights", [])
    if not flights:
        return None

    price_raw = item.get("price")
    if price_raw is None:
        return None
    try:
        price = float(price_raw)
    except (TypeError, ValueError):
        return None

    total_duration = item.get("total_duration", 0)
    offer_id = f"gf-{offer_idx}-{item.get('departure_token', '')[:8]}"

    itinerary = _parse_flight_block(flights, total_duration, offer_id)
    if not itinerary.segments:
        return None

    # Derive the primary carrier from the first segment
    carrier = itinerary.segments[0].carrier_code

    return FlightOffer(
        offer_id=offer_id,
        itineraries=[itinerary],
        price=PriceBreakdown(
            base=round(price * 0.82, 2),   # approximate: ~18% taxes on domestic CA
            taxes=round(price * 0.18, 2),
            total=price,
            currency=currency,
        ),
        seats_available=None,               # Google Flights doesn't expose seat counts
        booking_class="ECONOMY",
        validating_carrier=carrier,
        last_ticketing_date=None,
        source="GOOGLE_FLIGHTS",
    )


class SerpApiFlightClient:
    """
    Google Flights client via SerpApi.

    Implements the same search interface as AmadeusFlightClient so it can be
    used as a drop-in replacement throughout the scanner.

    Env var: SERPAPI_KEY
    Free tier: 100 searches / month (https://serpapi.com)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        currency: str = "CAD",
    ):
        self.api_key = api_key or os.getenv("SERPAPI_KEY", "")
        if not self.api_key:
            raise ValueError(
                "SerpApi key not found. Set SERPAPI_KEY in your .env file.\n"
                "Free account (100 searches/month): https://serpapi.com/users/sign_up"
            )
        self.currency = currency
        logger.info("SerpApi (Google Flights) client initialised")

    def _search(self, params: dict) -> dict:
        """Execute a SerpApi search and return the parsed JSON result."""
        params["api_key"] = self.api_key
        params["engine"] = "google_flights"
        params["hl"] = "en"
        params["gl"] = "ca"
        params["currency"] = self.currency
        search = GoogleSearch(params)
        return search.get_dict()

    def _extract_offers(self, result: dict, offer_id_prefix: str = "") -> List[FlightOffer]:
        """Pull offers out of best_flights + other_flights arrays."""
        offers = []
        for section_key in ("best_flights", "other_flights"):
            for idx, item in enumerate(result.get(section_key, [])):
                offer = _parse_result_item(
                    item,
                    offer_idx=idx,
                    currency=self.currency,
                )
                if offer:
                    offers.append(offer)
        return offers

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
        Search one-way flights between two Canadian airports.

        Args:
            origin: IATA origin code.
            destination: IATA destination code.
            departure_date: YYYY-MM-DD.
            adults: Number of adult passengers.
            max_results: Cap on returned offers (SerpApi returns ~5–15 naturally).
            currency: Price currency.

        Returns:
            List of FlightOffer objects.
        """
        try:
            result = self._search({
                "departure_id": origin,
                "arrival_id": destination,
                "outbound_date": departure_date,
                "type": "2",           # one-way
                "adults": adults,
                "sort_by": "2",        # sort by price
                "currency": currency or self.currency,
            })
            offers = self._extract_offers(result)
            return offers[:max_results]
        except Exception as exc:
            logger.warning("SerpApi error for %s→%s on %s: %s", origin, destination, departure_date, exc)
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
            result = self._search({
                "departure_id": origin,
                "arrival_id": destination,
                "outbound_date": departure_date,
                "return_date": return_date,
                "type": "1",           # round trip
                "adults": adults,
                "sort_by": "2",
                "currency": currency or self.currency,
            })
            offers = self._extract_offers(result)
            return offers[:max_results]
        except Exception as exc:
            logger.warning(
                "SerpApi RT error for %s↔%s on %s/%s: %s",
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
        """Fetch cheapest one-way offers for a single date with back-off on errors."""
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
        rate_limit_pause: float = 0.5,
    ) -> List[FlightOffer]:
        """Search every date in [start_date, end_date] and aggregate results."""
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
