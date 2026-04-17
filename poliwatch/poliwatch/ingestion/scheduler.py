"""APScheduler-driven ingestion + scoring.

Usage:
    python -m poliwatch.ingestion.scheduler                 # run forever
    python -m poliwatch.ingestion.scheduler --backfill      # pull 2012→present then exit
    python -m poliwatch.ingestion.scheduler --once          # run all jobs once and exit
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from poliwatch.config import get_settings
from poliwatch.database import session_scope
from poliwatch.ingestion._http import close_client
from poliwatch.ingestion.congress_api import (
    ingest_members,
    ingest_recent_bills,
    ingest_recent_votes,
)
from poliwatch.ingestion.house_disclosures import ingest_house_filings
from poliwatch.ingestion.quiver import ingest_quiver
from poliwatch.ingestion.senate_disclosures import ingest_senate_filings

EARLIEST_BACKFILL_YEAR = 2012


def _setup_logging() -> None:
    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, backtrace=False, diagnose=False)


async def run_all_once(*, score: bool = True) -> dict[str, int]:
    """Run every ingestion source once + rescore trades. Returns per-source counts."""
    today = datetime.utcnow().date()
    results: dict[str, int] = {}

    with session_scope() as db:
        results["members"] = await ingest_members(db)
        results["bills"] = await ingest_recent_bills(db)
        results["votes"] = await ingest_recent_votes(db)
        results["quiver"] = await ingest_quiver(db)
        results["house"] = await ingest_house_filings(db, year=today.year)
        results["senate"] = await ingest_senate_filings(
            db, from_date=date(today.year, 1, 1), to_date=today
        )

    if score:
        from poliwatch.analysis.scoring import rescore_recent_trades

        with session_scope() as db:
            results["scored"] = rescore_recent_trades(db)

    logger.info("ingestion summary: {}", results)
    return results


async def run_backfill() -> None:
    """Pull historical data from ``EARLIEST_BACKFILL_YEAR`` through this year."""
    current_year = datetime.utcnow().year
    logger.info("BACKFILL {} → {}", EARLIEST_BACKFILL_YEAR, current_year)

    with session_scope() as db:
        await ingest_members(db)
        await ingest_recent_bills(db)

    for year in range(EARLIEST_BACKFILL_YEAR, current_year + 1):
        with session_scope() as db:
            try:
                await ingest_house_filings(db, year=year)
            except Exception as exc:  # noqa: BLE001
                logger.warning("house {} backfill failed: {}", year, exc)
            try:
                await ingest_senate_filings(
                    db,
                    from_date=date(year, 1, 1),
                    to_date=date(year, 12, 31),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("senate {} backfill failed: {}", year, exc)

    with session_scope() as db:
        await ingest_quiver(db)

    from poliwatch.analysis.scoring import rescore_recent_trades

    with session_scope() as db:
        rescore_recent_trades(db, lookback_days=None)


async def _scheduled_tick() -> None:
    try:
        await run_all_once()
    except Exception as exc:  # noqa: BLE001
        logger.exception("scheduled tick failed: {}", exc)


async def run_forever() -> None:
    settings = get_settings()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _scheduled_tick,
        trigger=IntervalTrigger(hours=settings.data_refresh_interval_hours),
        id="ingest_all",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.utcnow(),
    )
    scheduler.start()
    logger.info(
        "scheduler started (interval = {}h)",
        settings.data_refresh_interval_hours,
    )
    try:
        # Block forever until cancelled.
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler stopping")
    finally:
        scheduler.shutdown(wait=False)
        await close_client()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PoliWatch ingestion scheduler")
    p.add_argument("--backfill", action="store_true", help="Pull historical data then exit")
    p.add_argument("--once", action="store_true", help="Run all jobs once and exit")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    args = _parse_args(argv)

    async def _run() -> None:
        try:
            if args.backfill:
                await run_backfill()
            elif args.once:
                await run_all_once()
            else:
                await run_forever()
        finally:
            await close_client()

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
