"""Trade ↔ legislation correlation.

A bill is considered *correlated* with a trade when all three hold:
  1. The bill's latest action or introduction is within
     ``window_before_days`` before the trade date (default 30).
  2. The member sits on a committee whose jurisdiction covers the bill's
     sector (best-effort via ``sectors_for_committee``).
  3. The bill's ``related_tickers`` contains the traded ticker, OR the
     bill's subjects/title map to the same sector as the ticker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from poliwatch.ingestion._tickers import sector_for_ticker, sectors_for_committee
from poliwatch.models.bill import Bill
from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade


@dataclass(frozen=True, slots=True)
class CorrelatedBill:
    bill: Bill
    reason: str
    proximity_days: int  # absolute days between trade date and bill's latest action


def _member_sectors(member: CongressMember) -> set[str]:
    sectors: set[str] = set()
    for committee in member.committees or []:
        sectors |= sectors_for_committee(committee)
    return sectors


def correlate_trade_to_legislation(
    trade: StockTrade,
    db: Session,
    *,
    window_before_days: int = 30,
    window_after_days: int = 14,
    max_results: int = 10,
) -> list[CorrelatedBill]:
    """Return a ranked list of bills correlated with ``trade``.

    Ranking: lower ``proximity_days`` first, then exact-ticker hits above
    sector-only hits.
    """
    if trade.trade_date is None:
        return []

    start = trade.trade_date - timedelta(days=window_before_days)
    end = trade.trade_date + timedelta(days=window_after_days)

    stmt = (
        select(Bill)
        .where(
            or_(
                and_(Bill.latest_action_date >= start, Bill.latest_action_date <= end),
                and_(Bill.introduced_date >= start, Bill.introduced_date <= end),
            )
        )
        .limit(500)
    )
    candidates = list(db.execute(stmt).scalars().all())
    if not candidates:
        return []

    member: CongressMember | None = trade.member
    member_sectors = _member_sectors(member) if member else set()
    ticker = (trade.ticker or "").upper()
    ticker_sector = sector_for_ticker(ticker) if ticker else None

    out: list[CorrelatedBill] = []
    for bill in candidates:
        related_tickers = set(bill.related_tickers or [])
        bill_sectors = _bill_sectors(bill)

        exact_ticker_hit = bool(ticker and ticker in related_tickers)
        sector_hit = bool(ticker_sector and ticker_sector in bill_sectors)
        committee_hit = bool(member_sectors & (bill_sectors or set()))

        # Require at least one sector/ticker hit AND a committee overlap
        # to keep the list meaningful (core project spec requirement 2+3).
        if not (exact_ticker_hit or (sector_hit and committee_hit)):
            continue

        anchor = bill.latest_action_date or bill.introduced_date
        proximity = abs((trade.trade_date - anchor).days) if anchor else window_before_days

        reason_bits: list[str] = []
        if exact_ticker_hit:
            reason_bits.append(f"bill.related_tickers includes {ticker}")
        if sector_hit:
            reason_bits.append(f"ticker sector ({ticker_sector}) matches bill sector")
        if committee_hit:
            reason_bits.append(
                f"member committees overlap bill sectors: "
                f"{sorted(member_sectors & bill_sectors)}"
            )
        out.append(
            CorrelatedBill(
                bill=bill,
                reason="; ".join(reason_bits),
                proximity_days=proximity,
            )
        )

    out.sort(key=lambda c: (c.proximity_days, 0 if c.bill.related_tickers else 1))
    return out[:max_results]


def _bill_sectors(bill: Bill) -> set[str]:
    """Infer sector names for a bill from its related_tickers."""
    sectors: set[str] = set()
    for ticker in bill.related_tickers or []:
        s = sector_for_ticker(ticker)
        if s:
            sectors.add(s)
    return sectors
