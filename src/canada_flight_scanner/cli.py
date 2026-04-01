"""Command-line interface for the Canadian Flight Deal Scanner."""

import logging
import os
import sys
from typing import Optional

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from .airports import AIRPORTS_BY_IATA, TIER_1_AIRPORTS, get_all_routes
from .client_factory import create_client
from .reporter import ConsoleReporter, FileReporter
from .scanner import FlightScanner

console = Console()

load_dotenv()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
def cli():
    """Canadian Flight Deal Scanner – find the best domestic flight deals."""
    pass


@cli.command("scan")
@click.option(
    "--origins", "-o",
    default=None,
    help="Comma-separated IATA origin codes (e.g. YYZ,YVR). Defaults to Tier-1 airports.",
)
@click.option(
    "--destinations", "-d",
    default=None,
    help="Comma-separated IATA destination codes. If omitted, all routes within tier are used.",
)
@click.option(
    "--days", "-n",
    default=90,
    show_default=True,
    help="Number of days ahead to scan.",
)
@click.option(
    "--max-price",
    default=500.0,
    show_default=True,
    help="Maximum price in CAD to consider a deal.",
)
@click.option(
    "--min-discount",
    default=15.0,
    show_default=True,
    help="Minimum discount %% vs route average to flag as a deal.",
)
@click.option(
    "--tier",
    default="2",
    show_default=True,
    type=click.Choice(["1", "2", "3"]),
    help="Max destination tier (1=major cities only, 3=all airports).",
)
@click.option(
    "--date-step",
    default=3,
    show_default=True,
    help="Scan every N days (1 = daily; higher = fewer API calls).",
)
@click.option(
    "--workers", "-w",
    default=4,
    show_default=True,
    help="Number of routes to scan in parallel.",
)
@click.option(
    "--top",
    default=30,
    show_default=True,
    help="Number of top deals to display.",
)
@click.option(
    "--output-dir",
    default="./reports",
    show_default=True,
    help="Directory to save JSON and CSV reports.",
)
@click.option("--no-file", is_flag=True, help="Skip saving report files.")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def scan_cmd(
    origins, destinations, days, max_price, min_discount,
    tier, date_step, workers, top, output_dir, no_file, verbose,
):
    """Scan Canadian domestic routes and report the best flight deals."""
    _setup_logging(verbose)

    try:
        client = create_client()
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    origin_list = (
        [c.strip().upper() for c in origins.split(",")]
        if origins else None
    )
    dest_list = (
        [c.strip().upper() for c in destinations.split(",")]
        if destinations else None
    )

    for code in (origin_list or []) + (dest_list or []):
        if code not in AIRPORTS_BY_IATA:
            console.print(
                f"[red]Unknown airport code:[/red] {code}. "
                "Run [bold]canada-flights airports[/bold] to see valid codes."
            )
            sys.exit(1)

    scanner = FlightScanner(
        client=client,
        origins=origin_list,
        days_ahead=days,
        deal_price_threshold=max_price,
        deal_discount_pct=min_discount,
        max_destination_tier=int(tier),
        date_step_days=date_step,
        workers=workers,
    )

    if dest_list:
        effective_origins = origin_list or TIER_1_AIRPORTS
        routes = [(o, d) for o in effective_origins for d in dest_list if o != d]
    else:
        routes = None

    total_routes = len(routes) if routes else len(
        get_all_routes(origin_list, max_tier=int(tier))
    )

    console.print(
        f"\n[bold cyan]Canadian Flight Deal Scanner[/bold cyan]  "
        f"routes={total_routes}  days_ahead={days}  "
        f"max_price=${max_price:.0f} CAD  workers={workers}\n"
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning routes…", total=total_routes)

        def on_progress(current, total, label):
            progress.update(task, completed=current, description=f"[cyan]{label}[/cyan]")

        result = scanner.run(routes=routes, progress_callback=on_progress)
        progress.update(task, completed=total_routes, description="[green]Done[/green]")

    reporter = ConsoleReporter(max_deals=top)
    reporter.report(result)

    if not no_file and result.deals_found:
        file_reporter = FileReporter(output_dir=output_dir)
        paths = file_reporter.save_all(result)
        console.print(
            f"\n[dim]Reports saved:[/dim]\n"
            f"  JSON → {paths['json']}\n"
            f"  CSV  → {paths['csv']}\n"
        )


@cli.command("route")
@click.argument("origin")
@click.argument("destination")
@click.option(
    "--days", "-n",
    default=30,
    show_default=True,
    help="Number of days ahead to search.",
)
@click.option(
    "--max-price",
    default=500.0,
    show_default=True,
    help="Maximum price in CAD.",
)
@click.option(
    "--top",
    default=10,
    show_default=True,
    help="Number of results to show per direction.",
)
@click.option("--no-file", is_flag=True, help="Skip saving report files.")
@click.option("--output-dir", default="./reports", show_default=True)
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def route_cmd(origin, destination, days, max_price, top, no_file, output_dir, verbose):
    """Search flights between two airports in both directions.

    ORIGIN and DESTINATION are IATA airport codes (e.g. YYC YYZ).
    """
    _setup_logging(verbose)

    origin = origin.upper()
    destination = destination.upper()

    for code in [origin, destination]:
        if code not in AIRPORTS_BY_IATA:
            console.print(
                f"[red]Unknown airport code:[/red] {code}. "
                "Run [bold]canada-flights airports[/bold] to see valid codes."
            )
            sys.exit(1)

    try:
        client = create_client()
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    from datetime import datetime, timedelta, timezone
    from rich.table import Table
    from rich import box
    from .deal_engine import identify_deals
    from .models import ScanResult
    import uuid

    console.print(
        f"\n[bold cyan]Route Search:[/bold cyan]  "
        f"[bold]{origin} ↔ {destination}[/bold]  "
        f"days_ahead={days}  max_price=${max_price:.0f} CAD\n"
    )

    today = datetime.now(timezone.utc).date()
    dates = [
        (today + timedelta(days=d)).strftime("%Y-%m-%d")
        for d in range(1, days + 1, 3)
    ]

    all_deals = []
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)

    for label, orig, dest in [
        (f"{origin} → {destination}", origin, destination),
        (f"{destination} → {origin}", destination, origin),
    ]:
        with console.status(f"[cyan]Scanning {label}…[/cyan]"):
            offers = []
            for date_str in dates:
                offers.extend(
                    client.get_cheapest_date_offers(
                        origin=orig,
                        destination=dest,
                        departure_date=date_str,
                    )
                )

        deals = identify_deals(
            offers=offers,
            min_discount_pct=0.0,   # show all results, not just deals
            max_price_threshold=max_price,
            min_score=0.0,
        )
        # Sort by price so cheapest dates show first
        deals = sorted(deals, key=lambda d: d.price_cad)

        console.print(f"\n[bold]{label}[/bold] — {len(deals)} flights found\n")

        if not deals:
            console.print("  [yellow]No flights found for this direction.[/yellow]")
            continue

        table = Table(box=box.ROUNDED, header_style="bold cyan", show_header=True)
        table.add_column("Date", min_width=14)
        table.add_column("Time", width=6)
        table.add_column("Price (CAD)", justify="right", min_width=11)
        table.add_column("Duration", width=9)
        table.add_column("Stops", width=6)
        table.add_column("Airline", width=7)
        table.add_column("Score", justify="right", width=6)

        for deal in deals[:top]:
            itin = deal.offer.itineraries[0]
            stops_str = "Direct" if deal.offer.total_stops == 0 else str(deal.offer.total_stops)
            from .reporter import _score_color
            color = _score_color(deal.deal_score)
            table.add_row(
                deal.departure_date_str,
                deal.departure_time_str,
                f"[{color}]${deal.price_cad:.0f}[/{color}]",
                itin.duration_str,
                stops_str,
                deal.offer.validating_carrier,
                f"[{color}]{deal.deal_score:.0f}[/{color}]",
            )

        console.print(table)
        all_deals.extend(deals[:top])

    if not no_file and all_deals:
        finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        result = ScanResult(
            scan_id=str(uuid.uuid4())[:8],
            started_at=started_at,
            finished_at=finished_at,
            routes_scanned=2,
            offers_evaluated=len(all_deals),
            deals_found=all_deals,
        )
        file_reporter = FileReporter(output_dir=output_dir)
        paths = file_reporter.save_all(result)
        console.print(
            f"\n[dim]Reports saved:[/dim]\n"
            f"  JSON → {paths['json']}\n"
            f"  CSV  → {paths['csv']}\n"
        )


@cli.command("airports")
@click.option("--tier", default=None, type=click.Choice(["1", "2", "3"]),
              help="Filter by tier.")
def airports_cmd(tier):
    """List all supported Canadian airports."""
    from rich.table import Table
    from rich import box
    from .airports import CANADIAN_AIRPORTS, TIER_1_AIRPORTS, TIER_2_AIRPORTS

    table = Table(title="Supported Canadian Airports", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("IATA", width=6)
    table.add_column("City", min_width=14)
    table.add_column("Province/Territory", min_width=20)
    table.add_column("Airport Name", min_width=30)
    table.add_column("Tier", width=5, justify="center")

    for ap in CANADIAN_AIRPORTS:
        if ap.iata in TIER_1_AIRPORTS:
            ap_tier = "1"
        elif ap.iata in TIER_2_AIRPORTS:
            ap_tier = "2"
        else:
            ap_tier = "3"

        if tier and ap_tier != tier:
            continue

        table.add_row(ap.iata, ap.city, ap.province, ap.name, ap_tier)

    console.print(table)


@cli.command("watch")
@click.option("--interval", default=6, show_default=True, help="Scan interval in hours.")
@click.option("--origins", "-o", default=None, help="Comma-separated origin IATA codes.")
@click.option("--days", "-n", default=90, show_default=True)
@click.option("--max-price", default=500.0, show_default=True)
@click.option("--min-discount", default=15.0, show_default=True)
@click.option("--workers", "-w", default=4, show_default=True, help="Parallel route workers.")
@click.option("--top", default=10, show_default=True)
@click.option("--output-dir", default="./reports", show_default=True)
@click.option("--verbose", "-v", is_flag=True)
def watch_cmd(interval, origins, days, max_price, min_discount, workers, top, output_dir, verbose):
    """Continuously scan and report deals on a schedule."""
    from .scheduler import run_scheduled

    _setup_logging(verbose)

    try:
        client = create_client()
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    origin_list = (
        [c.strip().upper() for c in origins.split(",")]
        if origins else None
    )

    scanner = FlightScanner(
        client=client,
        origins=origin_list,
        days_ahead=days,
        deal_price_threshold=max_price,
        deal_discount_pct=min_discount,
        workers=workers,
    )

    file_reporter = FileReporter(output_dir=output_dir)
    console_reporter = ConsoleReporter(max_deals=top)

    def scan_and_report():
        result = scanner.run()
        console_reporter.report(result)
        if result.deals_found:
            file_reporter.save_all(result)
        return result

    console.print(
        f"\n[bold cyan]Watch mode[/bold cyan] – scanning every {interval} hours. "
        "Press [bold]Ctrl+C[/bold] to stop.\n"
    )
    run_scheduled(scan_and_report, lambda r: None, interval_hours=interval)


def main():
    cli()


if __name__ == "__main__":
    main()
