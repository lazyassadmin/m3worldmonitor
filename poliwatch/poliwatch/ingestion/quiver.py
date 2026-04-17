"""Quiver Quantitative free-tier congressional trading data ingestion."""

from datetime import date, datetime

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade

QUIVER_BASE = "https://api.quiverquant.com/beta/live/congresstrading"
HEADERS = {"User-Agent": "PoliWatch/0.1.0 (open-source political accountability tool)"}

AMOUNT_RANGES: dict[str, tuple[int, int]] = {
    "$1,001 - $15,000": (1001, 15000),
    "$15,001 - $50,000": (15001, 50000),
    "$50,001 - $100,000": (50001, 100000),
    "$100,001 - $250,000": (100001, 250000),
    "$250,001 - $500,000": (250001, 500000),
    "$500,001 - $1,000,000": (500001, 1000000),
    "$1,000,001 - $5,000,000": (1000001, 5000000),
    "$5,000,001 - $25,000,000": (5000001, 25000000),
    "$25,000,001 - $50,000,000": (25000001, 50000000),
    "Over $50,000,000": (50000001, 100000000),
}


def _parse_amount(amount_str: str) -> tuple[int | None, int | None]:
    if not amount_str:
        return None, None
    for key, (lo, hi) in AMOUNT_RANGES.items():
        if key.lower() in amount_str.lower():
            return lo, hi
    return None, None


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


async def fetch_quiver_trades() -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(QUIVER_BASE, headers=HEADERS)
        resp.raise_for_status()
        return resp.json()


async def _ensure_member(db: AsyncSession, row: dict) -> str | None:
    """Upsert a minimal CongressMember record from Quiver data; return bioguide_id."""
    bioguide_id = row.get("BioguideID") or row.get("bioguide_id")
    if not bioguide_id:
        return None

    result = await db.execute(
        select(CongressMember).where(CongressMember.bioguide_id == bioguide_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        member = CongressMember(
            bioguide_id=bioguide_id,
            name=row.get("Representative") or row.get("Senator") or "Unknown",
            party=row.get("Party") or "",
            state=row.get("State") or "",
            chamber="house" if row.get("Representative") else "senate",
            committees=[],
        )
        db.add(member)
        await db.flush()
    return bioguide_id


async def ingest_quiver(db: AsyncSession, *, backfill: bool = False) -> int:
    """Fetch Quiver trades and upsert into DB. Returns number of new records inserted."""
    logger.info("Fetching congressional trades from Quiver Quantitative…")
    try:
        rows = await fetch_quiver_trades()
    except Exception as exc:
        logger.error(f"Quiver fetch failed: {exc}")
        return 0

    inserted = 0
    for row in rows:
        bioguide_id = await _ensure_member(db, row)
        if not bioguide_id:
            continue

        ticker = (row.get("Ticker") or "").strip().upper()
        trade_date = _parse_date(row.get("TransactionDate") or row.get("transaction_date"))
        disclosure_date = _parse_date(row.get("DisclosureDate") or row.get("disclosure_date"))

        if not trade_date or not disclosure_date:
            continue

        delay = (disclosure_date - trade_date).days

        # Idempotency: skip if already stored
        existing = await db.execute(
            select(StockTrade).where(
                StockTrade.member_id == bioguide_id,
                StockTrade.ticker == ticker,
                StockTrade.trade_date == trade_date,
                StockTrade.source == "quiver",
            )
        )
        if existing.scalar_one_or_none():
            continue

        amount_str = row.get("Range") or row.get("Amount") or ""
        amount_min, amount_max = _parse_amount(amount_str)

        trade = StockTrade(
            member_id=bioguide_id,
            ticker=ticker,
            asset_name=row.get("Asset") or ticker,
            trade_type=(row.get("Transaction") or "purchase").lower(),
            trade_date=trade_date,
            disclosure_date=disclosure_date,
            disclosure_delay_days=delay,
            amount_range=amount_str,
            amount_min=amount_min,
            amount_max=amount_max,
            source="quiver",
            raw_url=None,
            suspicion_score=0.0,
        )
        db.add(trade)
        inserted += 1

    await db.commit()
    logger.info(f"Quiver ingest complete: {inserted} new trades")
    return inserted
