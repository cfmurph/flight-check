"""Command-line interface for the Canadian Flight Deal Scanner."""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from .airports import AIRPORTS_BY_IATA, TIER_1_AIRPORTS, get_all_routes
from .api_client import AmadeusFlightClient
from .reporter import ConsoleReporter, FileReporter, print_quick_summary
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
    tier, date_step, top, output_dir, no_file, verbose,
):
    """Scan Canadian domestic routes and report the best flight deals."""
    _setup_logging(verbose)

    try:
        client = AmadeusFlightClient()
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        console.print(
            "\n[yellow]Tip:[/yellow] Copy [bold].env.example[/bold] to [bold].env[/bold] "
            "and fill in your Amadeus API credentials.\n"
            "Free credentials: [link=https://developers.amadeus.com]https://developers.amadeus.com[/link]"
        )
        sys.exit(1)

    origin_list = (
        [c.strip().upper() for c in origins.split(",")]
        if origins else None
    )
    dest_list = (
        [c.strip().upper() for c in destinations.split(",")]
        if destinations else None
    )

    # Validate any user-supplied codes
    all_supplied = (origin_list or []) + (dest_list or [])
    for code in all_supplied:
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
    )

    # Build explicit routes if destinations were supplied
    if dest_list:
        effective_origins = origin_list or TIER_1_AIRPORTS
        routes = [(o, d) for o in effective_origins for d in dest_list if o != d]
    else:
        routes = None  # scanner auto-generates

    total_routes = len(routes) if routes else len(
        get_all_routes(origin_list, max_tier=int(tier))
    )

    console.print(
        f"\n[bold cyan]Canadian Flight Deal Scanner[/bold cyan]  "
        f"routes={total_routes}  days_ahead={days}  max_price=${max_price:.0f} CAD\n"
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


@cli.command("airports")
@click.option("--tier", default=None, type=click.Choice(["1", "2", "3"]),
              help="Filter by tier.")
def airports_cmd(tier):
    """List all supported Canadian airports."""
    from rich.table import Table
    from rich import box
    from .airports import CANADIAN_AIRPORTS, TIER_1_AIRPORTS, TIER_2_AIRPORTS, TIER_3_AIRPORTS

    tier_map = {
        "1": set(TIER_1_AIRPORTS),
        "2": set(TIER_2_AIRPORTS),
        "3": set(TIER_3_AIRPORTS),
    }

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
@click.option("--top", default=10, show_default=True)
@click.option("--output-dir", default="./reports", show_default=True)
@click.option("--verbose", "-v", is_flag=True)
def watch_cmd(interval, origins, days, max_price, min_discount, top, output_dir, verbose):
    """Continuously scan and report deals on a schedule."""
    from .scheduler import run_scheduled

    _setup_logging(verbose)

    try:
        client = AmadeusFlightClient()
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
    )

    file_reporter = FileReporter(output_dir=output_dir)
    console_reporter = ConsoleReporter(max_deals=top)

    def scan_and_report():
        result = scanner.run()
        console_reporter.report(result)
        if result.deals_found:
            file_reporter.save_all(result)
        return result

    def report_fn(result):
        pass  # already handled inside scan_and_report

    console.print(
        f"\n[bold cyan]Watch mode[/bold cyan] – scanning every {interval} hours. "
        "Press [bold]Ctrl+C[/bold] to stop.\n"
    )
    run_scheduled(scan_and_report, report_fn, interval_hours=interval)


def main():
    cli()


if __name__ == "__main__":
    main()
