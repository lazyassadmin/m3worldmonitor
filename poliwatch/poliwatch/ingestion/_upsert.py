"""Idempotent upsert helpers for trades and members."""

from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade, TradeType


def upsert_member(
    db: Session,
    *,
    bioguide_id: str,
    name: str,
    party: str | None = None,
    state: str | None = None,
    chamber: str = "house",
    committees: list[str] | None = None,
    opensecrets_id: str | None = None,
) -> CongressMember:
    row = db.get(CongressMember, bioguide_id)
    if row is None:
        row = CongressMember(
            bioguide_id=bioguide_id,
            name=name,
            party=party,
            state=state,
            chamber=chamber,
            committees=committees or [],
            opensecrets_id=opensecrets_id,
        )
        db.add(row)
    else:
        row.name = name
        if party:
            row.party = party
        if state:
            row.state = state
        if chamber:
            row.chamber = chamber
        if committees is not None:
            row.committees = committees
        if opensecrets_id is not None:
            row.opensecrets_id = opensecrets_id
    return row


def upsert_trade(
    db: Session,
    *,
    member_id: str,
    ticker: str | None,
    asset_name: str,
    trade_type: TradeType,
    trade_date: date,
    disclosure_date: date | None,
    disclosure_delay_days: int | None,
    amount_range: str | None,
    amount_min: int | None,
    amount_max: int | None,
    source: str,
    raw_url: str | None,
) -> tuple[StockTrade, bool]:
    """Insert a trade if (member, ticker, trade_date, type, amount) is new.

    Returns (trade, created_flag).
    """
    # Flush pending inserts so identical back-to-back calls in one session
    # find their own prior write (we run with autoflush=False).
    db.flush()
    stmt = select(StockTrade).where(
        StockTrade.member_id == member_id,
        StockTrade.ticker == ticker,
        StockTrade.trade_date == trade_date,
        StockTrade.trade_type == trade_type,
        StockTrade.amount_range == amount_range,
    )
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is not None:
        # Refresh disclosure info if it wasn't known before.
        changed = False
        if existing.disclosure_date is None and disclosure_date is not None:
            existing.disclosure_date = disclosure_date
            existing.disclosure_delay_days = disclosure_delay_days
            changed = True
        if existing.raw_url is None and raw_url is not None:
            existing.raw_url = raw_url
            changed = True
        if changed:
            db.add(existing)
        return existing, False

    trade = StockTrade(
        member_id=member_id,
        ticker=ticker,
        asset_name=asset_name,
        trade_type=trade_type,
        trade_date=trade_date,
        disclosure_date=disclosure_date,
        disclosure_delay_days=disclosure_delay_days,
        amount_range=amount_range,
        amount_min=amount_min,
        amount_max=amount_max,
        source=source,
        raw_url=raw_url,
    )
    db.add(trade)
    logger.debug("New trade: {} {} {} {}", member_id, ticker, trade_date, trade_type.value)
    return trade, True


def resolve_member_by_name(
    db: Session, full_name: str, chamber: str
) -> CongressMember | None:
    """Best-effort lookup by exact name within chamber (case-insensitive)."""
    if not full_name:
        return None
    stmt = (
        select(CongressMember)
        .where(CongressMember.chamber == chamber)
        .where(CongressMember.name.ilike(full_name.strip()))
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is not None:
        return row
    # Try last-name match as fallback.
    last = full_name.strip().split(",")[0].split()[-1] if full_name.strip() else ""
    if not last:
        return None
    stmt = (
        select(CongressMember)
        .where(CongressMember.chamber == chamber)
        .where(CongressMember.name.ilike(f"%{last}%"))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def synth_member_id(full_name: str, chamber: str) -> str:
    """Deterministic placeholder bioguide_id when the real one is unknown."""
    slug = "".join(c for c in full_name.upper() if c.isalnum())[:12] or "UNKNOWN"
    return f"X{chamber[0].upper()}{slug}"[:16]


def ensure_placeholder_member(
    db: Session, full_name: str, chamber: str
) -> CongressMember:
    """Return an existing member or create a minimal placeholder row."""
    existing = resolve_member_by_name(db, full_name, chamber)
    if existing is not None:
        return existing
    placeholder_id = synth_member_id(full_name, chamber)
    existing = db.get(CongressMember, placeholder_id)
    if existing is not None:
        return existing
    member = CongressMember(
        bioguide_id=placeholder_id,
        name=full_name,
        party=None,
        state=None,
        chamber=chamber,
        committees=[],
    )
    db.add(member)
    db.flush()
    return member


def _unused(x: Any) -> None:  # pragma: no cover
    del x
