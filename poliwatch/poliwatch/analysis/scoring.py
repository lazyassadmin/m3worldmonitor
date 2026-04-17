"""Suspicion score (0-100) computation per trade."""

from datetime import timedelta

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from poliwatch.models.bill import Bill
from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade
from poliwatch.analysis.correlation import (
    _member_committee_overlaps_bill,
    correlate_trade_to_legislation,
)


def _disclosure_delay_score(delay_days: int) -> tuple[float, str]:
    if delay_days > 45:
        return 35.0, f"Disclosure delay {delay_days}d (>45d STOCK Act limit)"
    if delay_days > 30:
        return 20.0, f"Disclosure delay {delay_days}d (>30d)"
    return 0.0, ""


def _committee_overlap_score(member: CongressMember | None, bills: list[Bill]) -> tuple[float, str]:
    if not member or not bills:
        return 0.0, ""
    for bill in bills:
        if _member_committee_overlaps_bill(member, bill):
            return 25.0, f"Member sits on committee overseeing sector of {bill.bill_id}"
    return 0.0, ""


def _bill_timing_score(trade: StockTrade, bills: list[Bill]) -> tuple[float, str]:
    if not bills:
        return 0.0, ""
    best_bill = bills[0]
    action_date = best_bill.latest_action_date or best_bill.introduced_date
    if not action_date:
        return 0.0, ""
    delta = abs((trade.trade_date - action_date).days)
    if delta <= 14:
        return 25.0, f"Trade within 14 days of bill action ({best_bill.bill_id})"
    return 0.0, ""


def _trade_size_score(trade: StockTrade) -> tuple[float, str]:
    amount = trade.amount_max or trade.amount_min or 0
    if amount >= 250_000:
        return 15.0, f"Large trade: ≥$250,000"
    if amount >= 50_000:
        return 10.0, f"Significant trade: ≥$50,000"
    return 0.0, ""


async def _pattern_score(trade: StockTrade, db: AsyncSession) -> tuple[float, str]:
    """3+ trades in same ticker within 90 days."""
    window_start = trade.trade_date - timedelta(days=90)
    result = await db.execute(
        select(func.count()).where(
            StockTrade.member_id == trade.member_id,
            StockTrade.ticker == trade.ticker,
            StockTrade.trade_date >= window_start,
            StockTrade.trade_date <= trade.trade_date,
        )
    )
    count = result.scalar_one_or_none() or 0
    if count >= 3:
        return 10.0, f"Pattern: {count} trades in {trade.ticker} within 90 days"
    return 0.0, ""


async def suspicion_score(
    trade: StockTrade, db: AsyncSession
) -> tuple[float, str, list[Bill]]:
    """
    Compute 0-100 suspicion score.
    Returns (score, reason_text, correlated_bills).
    """
    member_result = await db.execute(
        select(CongressMember).where(CongressMember.bioguide_id == trade.member_id)
    )
    member = member_result.scalar_one_or_none()
    correlated = await correlate_trade_to_legislation(trade, db)

    factors: list[str] = []
    total = 0.0

    delay_pts, delay_reason = _disclosure_delay_score(trade.disclosure_delay_days)
    if delay_pts:
        total += delay_pts
        factors.append(delay_reason)

    committee_pts, committee_reason = _committee_overlap_score(member, correlated)
    if committee_pts:
        total += committee_pts
        factors.append(committee_reason)

    timing_pts, timing_reason = _bill_timing_score(trade, correlated)
    if timing_pts:
        total += timing_pts
        factors.append(timing_reason)

    size_pts, size_reason = _trade_size_score(trade)
    if size_pts:
        total += size_pts
        factors.append(size_reason)

    pattern_pts, pattern_reason = await _pattern_score(trade, db)
    if pattern_pts:
        total += pattern_pts
        factors.append(pattern_reason)

    total = min(total, 100.0)
    reason = "; ".join(factors) if factors else "No suspicious indicators"
    return total, reason, correlated


async def score_all_trades(db: AsyncSession) -> None:
    """Recompute suspicion scores for all trades and persist."""
    result = await db.execute(select(StockTrade))
    trades = list(result.scalars().all())
    logger.info(f"Scoring {len(trades)} trades…")

    for trade in trades:
        score, _reason, _bills = await suspicion_score(trade, db)
        trade.suspicion_score = score

    await db.commit()
    logger.info("Scoring complete")
