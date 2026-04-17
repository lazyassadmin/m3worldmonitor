"""Suspicion scoring — deterministic, 0–100 per trade.

Factor reference (see README for the full table):

  Disclosure delay  > 30 days          → +20
  Disclosure delay  > 45 days          → +35  (instead of +20)
  Committee-sector overlap with ticker → +25
  Trade within ±14 days of related bill action → +25
  Trade notional > $50,000             → +10
  Trade notional > $250,000            → +15  (instead of +10)
  3+ trades in same ticker within 90 days → +10
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from poliwatch.analysis.correlation import CorrelatedBill, correlate_trade_to_legislation
from poliwatch.ingestion._tickers import sector_for_ticker, sectors_for_committee
from poliwatch.models.alert import SuspiciousTradeAlert
from poliwatch.models.trade import StockTrade


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    score: float
    factors: list[str]
    top_bill_id: str | None


def _disclosure_points(trade: StockTrade) -> tuple[int, str | None]:
    delay = trade.disclosure_delay_days
    if delay is None:
        return 0, None
    if delay > 45:
        return 35, f"disclosure delay {delay} days (>45, likely STOCK Act violation)"
    if delay > 30:
        return 20, f"disclosure delay {delay} days (>30)"
    return 0, None


def _committee_overlap_points(trade: StockTrade) -> tuple[int, str | None]:
    ticker = (trade.ticker or "").upper()
    if not ticker or trade.member is None:
        return 0, None
    ticker_sector = sector_for_ticker(ticker)
    if not ticker_sector:
        return 0, None
    member_sectors: set[str] = set()
    for committee in trade.member.committees or []:
        member_sectors |= sectors_for_committee(committee)
    if ticker_sector in member_sectors:
        return 25, (
            f"committee overlap: member on committee overseeing '{ticker_sector}' sector "
            f"while trading {ticker}"
        )
    return 0, None


def _bill_timing_points(correlated: list[CorrelatedBill]) -> tuple[int, str | None, str | None]:
    if not correlated:
        return 0, None, None
    nearest = correlated[0]
    if nearest.proximity_days <= 14:
        return (
            25,
            f"trade within {nearest.proximity_days} days of {nearest.bill.bill_id} — {nearest.reason}",
            nearest.bill.bill_id,
        )
    return 0, None, nearest.bill.bill_id


def _size_points(trade: StockTrade) -> tuple[int, str | None]:
    hi = trade.amount_max or 0
    if hi > 250_000:
        return 15, f"trade size > $250k (max ≈ ${hi:,})"
    if hi > 50_000:
        return 10, f"trade size > $50k (max ≈ ${hi:,})"
    return 0, None


def _pattern_points(trade: StockTrade, db: Session) -> tuple[int, str | None]:
    if not trade.ticker:
        return 0, None
    window_start = trade.trade_date - timedelta(days=90)
    count = (
        db.query(StockTrade)
        .filter(
            StockTrade.member_id == trade.member_id,
            StockTrade.ticker == trade.ticker,
            StockTrade.trade_date >= window_start,
            StockTrade.trade_date <= trade.trade_date,
        )
        .count()
    )
    if count >= 3:
        return 10, f"{count} trades in {trade.ticker} within 90 days"
    return 0, None


def score_trade(trade: StockTrade, db: Session) -> ScoreBreakdown:
    factors: list[str] = []
    score = 0

    delta, msg = _disclosure_points(trade)
    score += delta
    if msg:
        factors.append(f"+{delta}: {msg}")

    delta, msg = _committee_overlap_points(trade)
    score += delta
    if msg:
        factors.append(f"+{delta}: {msg}")

    correlated = correlate_trade_to_legislation(trade, db)
    delta, msg, top_bill = _bill_timing_points(correlated)
    score += delta
    if msg:
        factors.append(f"+{delta}: {msg}")

    delta, msg = _size_points(trade)
    score += delta
    if msg:
        factors.append(f"+{delta}: {msg}")

    delta, msg = _pattern_points(trade, db)
    score += delta
    if msg:
        factors.append(f"+{delta}: {msg}")

    return ScoreBreakdown(score=min(float(score), 100.0), factors=factors, top_bill_id=top_bill)


def apply_score(trade: StockTrade, db: Session) -> ScoreBreakdown:
    breakdown = score_trade(trade, db)
    trade.suspicion_score = breakdown.score
    db.add(trade)
    return breakdown


def maybe_create_alert(
    trade: StockTrade, breakdown: ScoreBreakdown, db: Session, *, threshold: float
) -> SuspiciousTradeAlert | None:
    if breakdown.score < threshold:
        return None
    # One alert per trade — skip if we've already flagged it.
    existing = (
        db.query(SuspiciousTradeAlert)
        .filter(SuspiciousTradeAlert.trade_id == trade.id)
        .first()
    )
    if existing is not None:
        if existing.score != breakdown.score:
            existing.score = breakdown.score
            existing.reason = "\n".join(breakdown.factors)
            existing.bill_id = breakdown.top_bill_id
            db.add(existing)
        return existing
    alert = SuspiciousTradeAlert(
        trade_id=trade.id,
        bill_id=breakdown.top_bill_id,
        reason="\n".join(breakdown.factors),
        score=breakdown.score,
    )
    db.add(alert)
    return alert


def rescore_recent_trades(
    db: Session,
    *,
    lookback_days: int | None = 180,
    threshold: float | None = None,
) -> int:
    """Rescore all trades within ``lookback_days`` (None = all)."""
    from poliwatch.config import get_settings

    settings = get_settings()
    t = threshold if threshold is not None else settings.suspicion_alert_threshold

    stmt = select(StockTrade)
    if lookback_days is not None:
        cutoff: date = date.today() - timedelta(days=lookback_days)
        stmt = stmt.where(StockTrade.trade_date >= cutoff)

    trades = list(db.execute(stmt).scalars().all())
    logger.info("scoring {} trades (threshold={})", len(trades), t)

    count = 0
    for trade in trades:
        breakdown = apply_score(trade, db)
        if breakdown.score > 0:
            count += 1
        maybe_create_alert(trade, breakdown, db, threshold=t)
    db.commit()
    return count
