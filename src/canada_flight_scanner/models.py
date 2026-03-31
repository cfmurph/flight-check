"""Data models for flight offers and deal results."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class FlightSegment:
    """A single flight leg (one takeoff + landing)."""
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    carrier_code: str
    flight_number: str
    aircraft: str
    duration_minutes: int

    @property
    def duration_str(self) -> str:
        hours, mins = divmod(self.duration_minutes, 60)
        return f"{hours}h {mins:02d}m"


@dataclass
class FlightItinerary:
    """One direction of a trip (possibly multi-segment)."""
    segments: List[FlightSegment]
    total_duration_minutes: int

    @property
    def origin(self) -> str:
        return self.segments[0].origin

    @property
    def destination(self) -> str:
        return self.segments[-1].destination

    @property
    def departure_time(self) -> datetime:
        return self.segments[0].departure_time

    @property
    def arrival_time(self) -> datetime:
        return self.segments[-1].arrival_time

    @property
    def stops(self) -> int:
        return len(self.segments) - 1

    @property
    def duration_str(self) -> str:
        hours, mins = divmod(self.total_duration_minutes, 60)
        return f"{hours}h {mins:02d}m"


@dataclass
class PriceBreakdown:
    base: float
    taxes: float
    total: float
    currency: str = "CAD"

    @property
    def total_cad(self) -> float:
        return self.total


@dataclass
class FlightOffer:
    """A complete flight offer (one-way or round-trip) returned from the API."""
    offer_id: str
    itineraries: List[FlightItinerary]
    price: PriceBreakdown
    seats_available: Optional[int]
    booking_class: str
    validating_carrier: str
    last_ticketing_date: Optional[str]
    source: str = "AMADEUS"

    @property
    def is_one_way(self) -> bool:
        return len(self.itineraries) == 1

    @property
    def origin(self) -> str:
        return self.itineraries[0].origin

    @property
    def destination(self) -> str:
        return self.itineraries[0].destination

    @property
    def outbound_departure(self) -> datetime:
        return self.itineraries[0].departure_time

    @property
    def total_stops(self) -> int:
        return sum(itin.stops for itin in self.itineraries)


@dataclass
class FlightDeal:
    """A flight offer that has been identified as a deal."""
    offer: FlightOffer
    deal_score: float          # 0–100; higher = better deal
    avg_price_on_route: float  # baseline average for comparison
    discount_pct: float        # percentage below average
    deal_tags: List[str] = field(default_factory=list)  # e.g. ["FLASH_SALE", "NONSTOP"]
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    @property
    def price_cad(self) -> float:
        return self.offer.price.total_cad

    @property
    def route_label(self) -> str:
        return f"{self.offer.origin} → {self.offer.destination}"

    @property
    def departure_date_str(self) -> str:
        return self.offer.outbound_departure.strftime("%a %b %d, %Y")

    @property
    def departure_time_str(self) -> str:
        return self.offer.outbound_departure.strftime("%H:%M")


@dataclass
class ScanResult:
    """Top-level result from a full scan run."""
    scan_id: str
    started_at: datetime
    finished_at: datetime
    routes_scanned: int
    offers_evaluated: int
    deals_found: List[FlightDeal]
    errors: List[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def top_deals(self) -> List[FlightDeal]:
        return sorted(self.deals_found, key=lambda d: d.deal_score, reverse=True)
