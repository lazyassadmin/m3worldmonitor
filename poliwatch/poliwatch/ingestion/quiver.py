"""Quiver Quantitative congressional-trade ingestion.

Endpoint: https://api.quiverquant.com/beta/live/congresstrading

Policy per project spec: warn-and-degrade if the endpoint rejects requests.
We update ``data_source_health`` so the dashboard can surface degraded state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from poliwatch.ingestion._amounts import (
    disclosure_delay,
    parse_amount_range,
    parse_date,
    parse_trade_type,
)
from poliwatch.ingestion._health import mark_degraded, mark_success
from poliwatch.ingestion._http import fetch_json
from poliwatch.ingestion._upsert import ensure_placeholder_member, upsert_trade

QUIVER_URL = "https://api.quiverquant.com/beta/live/congresstrading"
SOURCE = "quiver"


def _chamber_from(row: dict[str, Any]) -> str:
    raw = (row.get("House") or row.get("Chamber") or "").strip().lower()
    if raw.startswith("s") or "senate" in raw:
        return "senate"
    return "house"


def _apply_row(db: Session, row: dict[str, Any]) -> bool:
    name = (row.get("Representative") or row.get("Name") or "").strip()
    if not name:
        return False
    chamber = _chamber_from(row)
    member = ensure_placeholder_member(db, name, chamber)

    ticker = (row.get("Ticker") or "").strip().upper() or None
    asset_name = (row.get("Asset") or row.get("Description") or ticker or name).strip()
    trade_type = parse_trade_type(row.get("Transaction") or row.get("Type"))
    trade_d = parse_date(row.get("TransactionDate") or row.get("Date"))
    disc_d = parse_date(row.get("ReportDate") or row.get("DisclosureDate"))
    if trade_d is None:
        return False
    amount_min, amount_max, amount_range = parse_amount_range(
        row.get("Range") or row.get("Amount")
    )
    raw_url = row.get("ptr_link") or row.get("link") or row.get("url")

    _trade, created = upsert_trade(
        db,
        member_id=member.bioguide_id,
        ticker=ticker,
        asset_name=asset_name,
        trade_type=trade_type,
        trade_date=trade_d,
        disclosure_date=disc_d,
        disclosure_delay_days=disclosure_delay(trade_d, disc_d),
        amount_range=amount_range,
        amount_min=amount_min,
        amount_max=amount_max,
        source=SOURCE,
        raw_url=raw_url,
    )
    return created


async def ingest_quiver(db: Session) -> int:
    """Fetch all available Quiver congressional trades and upsert.

    Returns count of NEW trades inserted. Degraded runs return 0 and mark
    ``data_source_health`` so callers can keep running with House/Senate data.
    """
    logger.info("[quiver] fetching {}", QUIVER_URL)
    try:
        payload = await fetch_json(QUIVER_URL)
    except Exception as exc:  # noqa: BLE001
        mark_degraded(db, SOURCE, f"fetch failed: {exc}")
        return 0

    if not isinstance(payload, list):
        mark_degraded(db, SOURCE, f"unexpected response shape: {type(payload).__name__}")
        return 0

    created_count = 0
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            if _apply_row(db, row):
                created_count += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[quiver] skipped bad row: {} ({})", exc, row.get("Representative"))
            continue
    db.commit()
    mark_success(db, SOURCE, created_count)
    logger.info("[quiver] ingested {} new trades at {}", created_count, datetime.utcnow().isoformat())
    return created_count
