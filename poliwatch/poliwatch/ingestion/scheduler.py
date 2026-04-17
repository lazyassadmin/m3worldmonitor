"""APScheduler jobs for periodic data ingestion."""

import asyncio
from datetime import datetime

import typer
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from poliwatch.config import settings
from poliwatch.database import async_session_factory, init_db
from poliwatch.ingestion.congress_api import ingest_bills, ingest_members
from poliwatch.ingestion.house_disclosures import ingest_house
from poliwatch.ingestion.quiver import ingest_quiver
from poliwatch.ingestion.senate_disclosures import ingest_senate

app = typer.Typer()


async def run_full_ingest(*, backfill: bool = False) -> None:
    await init_db()
    async with async_session_factory() as db:
        logger.info("=== Starting full ingest cycle ===")

        await ingest_quiver(db)
        await ingest_members(db)
        await ingest_bills(db, limit_per_type=500 if not backfill else 5000)

        if backfill:
            years = list(range(2012, datetime.now().year + 1))
            await ingest_house(db, years=years)
            from_date = "2012-01-01"
        else:
            await ingest_house(db)
            from_date = None

        await ingest_senate(db, from_date=from_date)

        # Compute suspicion scores after ingest
        from poliwatch.analysis.scoring import score_all_trades
        await score_all_trades(db)

        # Fire alerts for newly scored trades
        from poliwatch.alerts.notifier import send_alerts_for_new_trades
        await send_alerts_for_new_trades(db)

        logger.info("=== Ingest cycle complete ===")


@app.command()
def run(
    backfill: bool = typer.Option(False, "--backfill", help="Fetch all historical data 2012–present"),
    once: bool = typer.Option(False, "--once", help="Run once and exit"),
) -> None:
    """Start the PoliWatch data ingestion scheduler."""

    async def _main() -> None:
        await run_full_ingest(backfill=backfill)

        if once:
            return

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            run_full_ingest,
            "interval",
            hours=settings.data_refresh_interval_hours,
            kwargs={"backfill": False},
        )
        scheduler.start()
        logger.info(
            f"Scheduler started; refresh every {settings.data_refresh_interval_hours}h. "
            "Press Ctrl+C to stop."
        )
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()

    asyncio.run(_main())


if __name__ == "__main__":
    app()
