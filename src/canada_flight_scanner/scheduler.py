"""Optional continuous scheduler: run scans on a recurring interval."""

import logging
import time
from typing import Callable, Optional

import schedule

from .models import ScanResult

logger = logging.getLogger(__name__)


def run_scheduled(
    scan_fn: Callable[[], ScanResult],
    report_fn: Callable[[ScanResult], None],
    interval_hours: int = 6,
    run_immediately: bool = True,
) -> None:
    """
    Run scan_fn every `interval_hours` hours, passing results to report_fn.

    Args:
        scan_fn: Zero-argument callable that returns a ScanResult.
        report_fn: Callable that accepts a ScanResult and handles output.
        interval_hours: How often to run (in hours).
        run_immediately: If True, run one scan immediately before scheduling.
    """

    def job():
        logger.info("Scheduled scan starting…")
        try:
            result = scan_fn()
            report_fn(result)
        except Exception as exc:
            logger.error("Scheduled scan failed: %s", exc, exc_info=True)

    if run_immediately:
        job()

    schedule.every(interval_hours).hours.do(job)
    logger.info("Scheduler running every %d hours. Press Ctrl+C to stop.", interval_hours)

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")
