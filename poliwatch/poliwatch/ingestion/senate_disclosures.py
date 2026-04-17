"""Senate eFD periodic transaction report ingestion."""

from datetime import date, datetime

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade

EFTS_SEARCH = "https://efts.senate.gov/LATEST/search-index"
HEADERS = {"User-Agent": "PoliWatch/0.1.0 (open-source political accountability tool)"}

AMOUNT_RANGES = {
    "$1,001 - $15,000": (1001, 15000),
    "$15,001 - $50,000": (15001, 50000),
    "$50,001 - $100,000": (50001, 100000),
    "$100,001 - $250,000": (100001, 250000),
    "$250,001 - $500,000": (250001, 500000),
    "$500,001 - $1,000,000": (500001, 1000000),
    "$1,000,001 - $5,000,000": (1000001, 5000000),
    "$5,000,001 - $25,000,000": (5000001, 25000000),
}


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(s: str) -> tuple[int | None, int | None]:
    for label, (lo, hi) in AMOUNT_RANGES.items():
        if label.lower() in s.lower():
            return lo, hi
    return None, None


async def _search_efts(
    client: httpx.AsyncClient, from_date: str, to_date: str, offset: int = 0
) -> dict:
    params = {
        "q": "periodic transaction",
        "dateRange": "custom",
        "fromDate": from_date,
        "toDate": to_date,
        "offset": offset,
        "limit": 100,
    }
    resp = await client.get(EFTS_SEARCH, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


async def ingest_senate(
    db: AsyncSession,
    from_date: str | None = None,
    to_date: str | None = None,
) -> int:
    """Ingest Senate eFD PTR filings. Date strings in YYYY-MM-DD format."""
    now = datetime.now()
    from_date = from_date or f"{now.year}-01-01"
    to_date = to_date or now.strftime("%Y-%m-%d")

    logger.info(f"Fetching Senate disclosures {from_date} → {to_date}…")
    inserted = 0

    async with httpx.AsyncClient(timeout=30) as client:
        offset = 0
        while True:
            try:
                data = await _search_efts(client, from_date, to_date, offset)
            except Exception as exc:
                logger.error(f"Senate eFTS fetch failed: {exc}")
                break

            hits = data.get("hits", {})
            records = hits.get("hits", []) if isinstance(hits, dict) else hits
            if not records:
                break

            for rec in records:
                src = rec.get("_source") or rec
                first = src.get("first_name") or ""
                last = src.get("last_name") or ""
                name = f"{first} {last}".strip() or "Unknown"
                bioguide_id = src.get("bioguide_id") or f"SEN_{last[:8].upper()}"

                # Ensure member record
                m_result = await db.execute(
                    select(CongressMember).where(CongressMember.bioguide_id == bioguide_id)
                )
                if not m_result.scalar_one_or_none():
                    db.add(
                        CongressMember(
                            bioguide_id=bioguide_id,
                            name=name,
                            party=src.get("party") or "",
                            state=src.get("state") or "",
                            chamber="senate",
                            committees=[],
                        )
                    )
                    await db.flush()

                ticker = (src.get("ticker") or "").strip().upper()
                if not ticker:
                    continue

                trade_date = _parse_date(src.get("transaction_date"))
                disc_date = _parse_date(src.get("date_received") or src.get("filed_date"))
                if not trade_date or not disc_date:
                    continue

                existing = await db.execute(
                    select(StockTrade).where(
                        StockTrade.member_id == bioguide_id,
                        StockTrade.ticker == ticker,
                        StockTrade.trade_date == trade_date,
                        StockTrade.source == "senate",
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                amount_str = src.get("amount") or ""
                lo, hi = _parse_amount(amount_str)
                txn_type = (src.get("transaction_type") or "purchase").lower()

                db.add(
                    StockTrade(
                        member_id=bioguide_id,
                        ticker=ticker,
                        asset_name=src.get("asset_name") or ticker,
                        trade_type=txn_type,
                        trade_date=trade_date,
                        disclosure_date=disc_date,
                        disclosure_delay_days=(disc_date - trade_date).days,
                        amount_range=amount_str,
                        amount_min=lo,
                        amount_max=hi,
                        source="senate",
                        raw_url=src.get("link") or src.get("pdf_url"),
                        suspicion_score=0.0,
                    )
                )
                inserted += 1

            await db.flush()
            total = hits.get("total", {})
            total_count = total.get("value", 0) if isinstance(total, dict) else int(total or 0)
            offset += len(records)
            if offset >= total_count:
                break

    await db.commit()
    logger.info(f"Senate ingest complete: {inserted} new trades")
    return inserted
