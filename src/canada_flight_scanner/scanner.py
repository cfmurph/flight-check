"""Core scanner orchestrator: iterates routes and dates, collects deals."""

import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Callable, List, Optional

from .airports import TIER_1_AIRPORTS, get_all_routes
from .client_factory import create_client
from .deal_engine import identify_deals, rank_deals_across_routes
from .models import FlightDeal, ScanResult

logger = logging.getLogger(__name__)


class FlightScanner:
    """
    Orchestrates a full or partial scan of Canadian domestic flight routes.

    Usage::

        scanner = FlightScanner()
        result = scanner.run()
        for deal in result.top_deals[:10]:
            print(deal.route_label, deal.price_cad)
    """

    def __init__(
        self,
        client=None,
        origins: Optional[List[str]] = None,
        days_ahead: int = 90,
        deal_price_threshold: float = 500.0,
        deal_discount_pct: float = 15.0,
        max_destination_tier: int = 2,
        date_step_days: int = 3,
        rate_limit_pause: float = 0.2,
        workers: int = 4,
    ):
        """
        Args:
            client: Flight API client instance. Auto-selected from env vars if None.
            origins: IATA codes to use as scan origins. Defaults to Tier 1 airports.
            days_ahead: How many days into the future to scan.
            deal_price_threshold: Max price (CAD) to consider a deal.
            deal_discount_pct: Min % below average to flag as deal.
            max_destination_tier: Include destinations up to this tier (1–3).
            date_step_days: Scan every N days (1 = daily, reduces API calls when > 1).
            rate_limit_pause: Seconds to sleep between API calls within a route.
            workers: Number of routes to scan in parallel.
        """
        self.client = client or create_client()
        self.origins = origins or self._origins_from_env() or TIER_1_AIRPORTS
        self.days_ahead = int(os.getenv("SCAN_DAYS_AHEAD", days_ahead))
        self.deal_price_threshold = float(
            os.getenv("DEAL_PRICE_THRESHOLD", deal_price_threshold)
        )
        self.deal_discount_pct = float(os.getenv("DEAL_DISCOUNT_PCT", deal_discount_pct))
        self.max_destination_tier = max_destination_tier
        self.date_step_days = date_step_days
        self.rate_limit_pause = rate_limit_pause
        self.workers = workers

    @staticmethod
    def _origins_from_env() -> Optional[List[str]]:
        raw = os.getenv("SCAN_ORIGINS", "")
        if raw:
            return [c.strip().upper() for c in raw.split(",") if c.strip()]
        return None

    def _date_range(self) -> List[str]:
        """Generate list of departure dates to scan."""
        today = datetime.now(timezone.utc).date()
        dates = []
        current = today + timedelta(days=1)
        end = today + timedelta(days=self.days_ahead)
        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=self.date_step_days)
        return dates

    def scan_route(self, origin: str, destination: str) -> List[FlightDeal]:
        """
        Scan all configured dates for a single origin→destination route.

        Returns deals identified for that route.
        """
        dates = self._date_range()
        all_offers = []

        logger.info("Scanning %s → %s across %d dates", origin, destination, len(dates))

        for date_str in dates:
            offers = self.client.get_cheapest_date_offers(
                origin=origin,
                destination=destination,
                departure_date=date_str,
            )
            all_offers.extend(offers)

        deals = identify_deals(
            offers=all_offers,
            min_discount_pct=self.deal_discount_pct,
            max_price_threshold=self.deal_price_threshold,
        )
        logger.info(
            "  %s→%s: %d offers → %d deals",
            origin, destination, len(all_offers), len(deals),
        )
        return deals

    def run(
        self,
        routes: Optional[List[tuple]] = None,
        progress_callback: Optional[Callable] = None,
    ) -> ScanResult:
        """
        Run a full scan, scanning up to `workers` routes in parallel.

        Args:
            routes: List of (origin, destination) tuples. Auto-generated if None.
            progress_callback: Optional callable(completed, total, route_label).

        Returns:
            ScanResult with all discovered deals.
        """
        scan_id = str(uuid.uuid4())[:8]
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        errors: List[str] = []

        if routes is None:
            routes = get_all_routes(
                origins=self.origins,
                max_tier=self.max_destination_tier,
            )

        logger.info(
            "Starting scan %s: %d routes, %d days ahead, %d workers",
            scan_id, len(routes), self.days_ahead, self.workers,
        )

        route_deals: dict = {}
        total_offers = 0
        completed = 0
        lock = Lock()

        def scan_one(route):
            origin, dest = route
            try:
                deals = self.scan_route(origin, dest)
                return (f"{origin}-{dest}", deals, None)
            except Exception as exc:
                return (f"{origin}-{dest}", [], str(exc))

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(scan_one, r): r for r in routes}
            for future in as_completed(futures):
                route_key, deals, error = future.result()
                origin, dest = futures[future]

                with lock:
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(routes), f"{origin} → {dest}")
                    if error:
                        msg = f"Error scanning {origin}→{dest}: {error}"
                        logger.error(msg)
                        errors.append(msg)
                    else:
                        if deals:
                            route_deals[route_key] = deals
                        total_offers += len(deals)

        all_deals = rank_deals_across_routes(route_deals)
        finished_at = datetime.now(timezone.utc).replace(tzinfo=None)

        result = ScanResult(
            scan_id=scan_id,
            started_at=started_at,
            finished_at=finished_at,
            routes_scanned=len(routes),
            offers_evaluated=total_offers,
            deals_found=all_deals,
            errors=errors,
        )

        logger.info(
            "Scan %s complete: %d routes, %d deals found in %.1fs",
            scan_id, len(routes), len(all_deals), result.duration_seconds,
        )
        return result
