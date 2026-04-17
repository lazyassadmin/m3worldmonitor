"""House STOCK Act periodic transaction report (PTR) ingestion."""

import re
import zipfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade

DATA_DIR = Path("data/house")
BASE_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs"
INDEX_URL = "https://disclosures-clerk.house.gov/FinancialDisclosure#Search"
HEADERS = {"User-Agent": "PoliWatch/0.1.0 (open-source political accountability tool)"}

AMOUNT_MAP = {
    "1": (1001, 15000),
    "2": (15001, 50000),
    "3": (50001, 100000),
    "4": (100001, 250000),
    "5": (250001, 500000),
    "6": (500001, 1000000),
    "7": (1000001, 5000000),
    "8": (5000001, 25000000),
    "9": (25000001, 50000000),
    "10": (50000001, 100000000),
}

AMOUNT_LABELS = {
    "1": "$1,001 - $15,000",
    "2": "$15,001 - $50,000",
    "3": "$50,001 - $100,000",
    "4": "$100,001 - $250,000",
    "5": "$250,001 - $500,000",
    "6": "$500,001 - $1,000,000",
    "7": "$1,000,001 - $5,000,000",
    "8": "$5,000,001 - $25,000,000",
    "9": "$25,000,001 - $50,000,000",
    "10": "Over $50,000,000",
}


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_xml_trades(xml_bytes: bytes, member_id: str, raw_url: str) -> list[dict]:
    """Parse House PTR XML file and return list of trade dicts."""
    try:
        from lxml import etree  # type: ignore[import-untyped]
    except ImportError:
        logger.error("lxml not installed; cannot parse House XML")
        return []

    root = etree.fromstring(xml_bytes)
    trades = []
    for txn in root.findall(".//Transaction"):
        ticker = (txn.findtext("Ticker") or "").strip().upper()
        if not ticker:
            continue
        trade_date = _parse_date(txn.findtext("TransactionDate"))
        disc_date = _parse_date(txn.findtext("NotificationDate"))
        if not trade_date or not disc_date:
            continue
        amount_code = (txn.findtext("Amount") or "").strip()
        lo, hi = AMOUNT_MAP.get(amount_code, (None, None))
        txn_type = (txn.findtext("TransactionType") or "purchase").lower()
        if "sale" in txn_type:
            txn_type = "sale"
        elif "purchase" in txn_type or "buy" in txn_type:
            txn_type = "purchase"
        else:
            txn_type = "exchange"

        trades.append(
            {
                "member_id": member_id,
                "ticker": ticker,
                "asset_name": txn.findtext("AssetName") or ticker,
                "trade_type": txn_type,
                "trade_date": trade_date,
                "disclosure_date": disc_date,
                "disclosure_delay_days": (disc_date - trade_date).days,
                "amount_range": AMOUNT_LABELS.get(amount_code, amount_code),
                "amount_min": lo,
                "amount_max": hi,
                "source": "house",
                "raw_url": raw_url,
            }
        )
    return trades


async def _download_year_index(client: httpx.AsyncClient, year: int) -> list[dict]:
    """Download and parse the House FD bulk ZIP index for a given year."""
    zip_url = f"{BASE_URL}/{year}FD.zip"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading House disclosure index for {year}: {zip_url}")

    try:
        resp = await client.get(zip_url, headers=HEADERS, follow_redirects=True, timeout=60)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(f"House index download failed ({year}): {exc.response.status_code}")
        return []

    records: list[dict] = []
    with zipfile.ZipFile(BytesIO(resp.content)) as zf:
        xml_files = [n for n in zf.namelist() if n.endswith(".xml") and "PTR" in n.upper()]
        for xml_name in xml_files:
            with zf.open(xml_name) as f:
                content = f.read()
            # Extract member ID from filename pattern: LASTNAME_FIRSTNAME_BioguideID_PTR_...
            match = re.search(r"_([A-Z][0-9]{6})_", xml_name)
            member_id = match.group(1) if match else ""
            url = f"{BASE_URL}/{year}FD.zip#{xml_name}"
            records.append({"member_id": member_id, "xml": content, "raw_url": url})

    return records


async def ingest_house(db: AsyncSession, years: list[int] | None = None) -> int:
    """Ingest House PTR disclosures for the given years (default: current year)."""
    if years is None:
        years = [datetime.now().year]

    inserted = 0
    async with httpx.AsyncClient(timeout=60) as client:
        for year in years:
            records = await _download_year_index(client, year)
            for rec in records:
                trades = _parse_xml_trades(rec["xml"], rec["member_id"], rec["raw_url"])
                for t in trades:
                    if not t["member_id"]:
                        continue
                    existing = await db.execute(
                        select(StockTrade).where(
                            StockTrade.member_id == t["member_id"],
                            StockTrade.ticker == t["ticker"],
                            StockTrade.trade_date == t["trade_date"],
                            StockTrade.source == "house",
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue

                    # Ensure member placeholder exists
                    m_result = await db.execute(
                        select(CongressMember).where(
                            CongressMember.bioguide_id == t["member_id"]
                        )
                    )
                    if not m_result.scalar_one_or_none():
                        db.add(
                            CongressMember(
                                bioguide_id=t["member_id"],
                                name="Unknown",
                                party="",
                                state="",
                                chamber="house",
                                committees=[],
                            )
                        )
                        await db.flush()

                    db.add(StockTrade(**t, suspicion_score=0.0))
                    inserted += 1

            await db.commit()
            logger.info(f"House ingest {year}: {inserted} trades so far")

    logger.info(f"House ingest complete: {inserted} new trades")
    return inserted
