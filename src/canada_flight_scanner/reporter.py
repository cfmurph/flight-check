"""Report generation: rich console output and JSON/CSV file reports."""

import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from .models import FlightDeal, ScanResult

logger = logging.getLogger(__name__)

console = Console()

DEAL_SCORE_COLORS = {
    80: "bright_green",
    60: "green",
    40: "yellow",
    0: "red",
}


def _score_color(score: float) -> str:
    for threshold, color in DEAL_SCORE_COLORS.items():
        if score >= threshold:
            return color
    return "red"


def _tags_str(tags: List[str]) -> str:
    return " ".join(f"[{t}]" for t in tags) if tags else ""


class ConsoleReporter:
    """Renders a scan result to the terminal using Rich."""

    def __init__(self, max_deals: int = 30, show_stops: bool = True):
        self.max_deals = max_deals
        self.show_stops = show_stops

    def print_summary(self, result: ScanResult) -> None:
        console.rule("[bold blue]Canadian Flight Deal Scanner[/bold blue]")
        console.print(
            f"\n[dim]Scan ID:[/dim] {result.scan_id}  "
            f"[dim]Completed:[/dim] {result.finished_at.strftime('%Y-%m-%d %H:%M UTC')}  "
            f"[dim]Duration:[/dim] {result.duration_seconds:.1f}s\n"
        )
        console.print(
            f"  Routes scanned : [bold]{result.routes_scanned}[/bold]\n"
            f"  Offers evaluated: [bold]{result.offers_evaluated}[/bold]\n"
            f"  Deals found    : [bold bright_green]{len(result.deals_found)}[/bold bright_green]\n"
        )

        if result.errors:
            console.print(f"[yellow]⚠ {len(result.errors)} routes had errors[/yellow]")

    def print_deals_table(self, result: ScanResult) -> None:
        deals = result.top_deals[: self.max_deals]
        if not deals:
            console.print("[yellow]No deals found matching your criteria.[/yellow]")
            return

        table = Table(
            title=f"Top {len(deals)} Flight Deals in Canada",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
            row_styles=["", "dim"],
        )

        table.add_column("#", style="dim", width=3, justify="right")
        table.add_column("Route", min_width=14)
        table.add_column("Date", min_width=14)
        table.add_column("Time", width=6)
        table.add_column("Price (CAD)", justify="right", min_width=11)
        table.add_column("Avg Price", justify="right", min_width=9)
        table.add_column("Discount", justify="right", width=9)
        table.add_column("Score", justify="right", width=7)
        table.add_column("Stops", width=6)
        table.add_column("Airline", width=7)
        table.add_column("Tags", min_width=14)

        for rank, deal in enumerate(deals, 1):
            color = _score_color(deal.deal_score)
            stops_str = "Direct" if deal.offer.total_stops == 0 else str(deal.offer.total_stops)
            table.add_row(
                str(rank),
                f"[bold]{deal.route_label}[/bold]",
                deal.departure_date_str,
                deal.departure_time_str,
                f"[{color}]${deal.price_cad:.0f}[/{color}]",
                f"${deal.avg_price_on_route:.0f}",
                f"[{color}]-{deal.discount_pct:.0f}%[/{color}]",
                f"[{color}]{deal.deal_score:.0f}[/{color}]",
                stops_str,
                deal.offer.validating_carrier,
                _tags_str(deal.deal_tags),
            )

        console.print(table)

    def report(self, result: ScanResult) -> None:
        self.print_summary(result)
        self.print_deals_table(result)


class FileReporter:
    """Saves scan results to JSON and CSV files."""

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = Path(output_dir or os.getenv("REPORT_DIR", "./reports"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _base_filename(self, result: ScanResult) -> str:
        ts = result.finished_at.strftime("%Y%m%d_%H%M%S")
        return f"scan_{result.scan_id}_{ts}"

    def save_json(self, result: ScanResult) -> Path:
        """Save full scan result to a JSON file."""
        path = self.output_dir / f"{self._base_filename(result)}.json"

        def deal_to_dict(d: FlightDeal) -> dict:
            itin = d.offer.itineraries[0]
            seg = itin.segments[0]
            return {
                "rank": None,
                "route": d.route_label,
                "origin": d.offer.origin,
                "destination": d.offer.destination,
                "departure_date": d.departure_date_str,
                "departure_time": d.departure_time_str,
                "price_cad": d.price_cad,
                "avg_price_cad": d.avg_price_on_route,
                "discount_pct": d.discount_pct,
                "deal_score": d.deal_score,
                "stops": d.offer.total_stops,
                "duration": itin.duration_str,
                "airline": d.offer.validating_carrier,
                "flight_number": f"{seg.carrier_code}{seg.flight_number}",
                "tags": d.deal_tags,
                "seats_available": d.offer.seats_available,
                "scanned_at": d.scanned_at.isoformat(),
            }

        data = {
            "scan_id": result.scan_id,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
            "duration_seconds": result.duration_seconds,
            "routes_scanned": result.routes_scanned,
            "offers_evaluated": result.offers_evaluated,
            "deals_count": len(result.deals_found),
            "deals": [
                {**deal_to_dict(d), "rank": i + 1}
                for i, d in enumerate(result.top_deals)
            ],
            "errors": result.errors,
        }

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

        logger.info("JSON report saved to %s", path)
        return path

    def save_csv(self, result: ScanResult) -> Path:
        """Save top deals to a CSV file."""
        path = self.output_dir / f"{self._base_filename(result)}.csv"

        fieldnames = [
            "rank", "origin", "destination", "departure_date", "departure_time",
            "price_cad", "avg_price_cad", "discount_pct", "deal_score",
            "stops", "duration", "airline", "tags", "seats_available",
        ]

        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for rank, deal in enumerate(result.top_deals, 1):
                itin = deal.offer.itineraries[0]
                writer.writerow({
                    "rank": rank,
                    "origin": deal.offer.origin,
                    "destination": deal.offer.destination,
                    "departure_date": deal.departure_date_str,
                    "departure_time": deal.departure_time_str,
                    "price_cad": f"{deal.price_cad:.2f}",
                    "avg_price_cad": f"{deal.avg_price_on_route:.2f}",
                    "discount_pct": f"{deal.discount_pct:.1f}",
                    "deal_score": f"{deal.deal_score:.1f}",
                    "stops": deal.offer.total_stops,
                    "duration": itin.duration_str,
                    "airline": deal.offer.validating_carrier,
                    "tags": "|".join(deal.deal_tags),
                    "seats_available": deal.offer.seats_available or "",
                })

        logger.info("CSV report saved to %s", path)
        return path

    def save_all(self, result: ScanResult) -> dict:
        """Save both JSON and CSV, return dict of {format: path}."""
        return {
            "json": self.save_json(result),
            "csv": self.save_csv(result),
        }


def print_quick_summary(result: ScanResult, top_n: int = 5) -> None:
    """
    Print a quick one-liner summary suitable for log output or email subjects.
    """
    deals = result.top_deals[:top_n]
    console.print(
        Panel(
            "\n".join(
                f"  #{i+1}  {d.route_label}  ${d.price_cad:.0f} CAD  "
                f"({d.departure_date_str})  -{d.discount_pct:.0f}%  score={d.deal_score:.0f}"
                for i, d in enumerate(deals)
            ) or "  No deals found.",
            title="[bold green]Top Canadian Flight Deals[/bold green]",
            border_style="green",
        )
    )
