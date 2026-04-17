"""Senate eFD (Electronic Financial Disclosures) ingestion.

Search index: https://efts.senate.gov/LATEST/search-index

The Senate eFD is an Elasticsearch-style endpoint returning filing metadata.
Like the House scraper this lands filing-level records only; per-filing
transaction detail (HTML/PDF) is a Phase 1.5 follow-up.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from poliwatch.ingestion._amounts import parse_date
from poliwatch.ingestion._health import mark_degraded, mark_success
from poliwatch.ingestion._http import fetch_json
from poliwatch.ingestion._upsert import ensure_placeholder_member, upsert_trade
from poliwatch.models.trade import TradeType

SEARCH_URL = "https://efts.senate.gov/LATEST/search-index"
SOURCE = "senate"


async def ingest_senate_filings(
    db: Session,
    *,
    from_date: date,
    to_date: date | None = None,
) -> int:
    """Pull periodic-transaction filings between the given dates (inclusive)."""
    to_date = to_date or datetime.utcnow().date()
    params = {
        "q": '"periodic transaction"',
        "dateRange": "custom",
        "fromDate": from_date.isoformat(),
        "toDate": to_date.isoformat(),
        "offset": 0,
    }

    logger.info("[senate] search-index {} → {}", from_date, to_date)
    try:
        data = await fetch_json(SEARCH_URL, params=params)
    except Exception as exc:  # noqa: BLE001
        mark_degraded(db, SOURCE, f"fetch failed: {exc}")
        return 0

    results = _extract_results(data)
    if not results:
        mark_success(db, SOURCE, 0)
        return 0

    new_rows = 0
    for row in results:
        try:
            new_rows += _apply_row(db, row)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[senate] skipped bad row: {}", exc)
            continue

    db.commit()
    mark_success(db, SOURCE, new_rows)
    return new_rows


def _extract_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("results", "hits", "data"):
            val = payload.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
            if isinstance(val, dict):
                inner = val.get("hits")
                if isinstance(inner, list):
                    return [r for r in inner if isinstance(r, dict)]
    return []


def _first(row: dict, *keys: str) -> str:
    for k in keys:
        v = row.get(k)
        if v:
            return str(v).strip()
    return ""


def _apply_row(db: Session, row: dict) -> int:
    first = _first(row, "firstName", "first_name", "first")
    last = _first(row, "lastName", "last_name", "last")
    name = f"{first} {last}".strip()
    if not name:
        name = _first(row, "name", "filer")
    if not name:
        return 0

    member = ensure_placeholder_member(db, name, "senate")
    filing_d = parse_date(_first(row, "filingDate", "filing_date", "date"))
    url = _first(row, "reportUrl", "url", "href") or None
    trade_d = filing_d or date.today()

    _trade, created = upsert_trade(
        db,
        member_id=member.bioguide_id,
        ticker=None,
        asset_name="(Senate PTR filing)",
        trade_type=TradeType.OTHER,
        trade_date=trade_d,
        disclosure_date=filing_d,
        disclosure_delay_days=None,
        amount_range=None,
        amount_min=None,
        amount_max=None,
        source=SOURCE,
        raw_url=url,
    )
    return 1 if created else 0
