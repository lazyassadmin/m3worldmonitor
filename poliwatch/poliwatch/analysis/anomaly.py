"""Simple statistical anomaly detection for outlier trade behavior.

Intentionally lightweight — the primary signal is the rule-based
``scoring.score_trade``; this module supplies *additional* context for
the dashboard (z-scores and ticker concentration).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from poliwatch.models.trade import StockTrade


@dataclass(frozen=True, slots=True)
class Anomaly:
    kind: str
    description: str
    z_score: float | None = None


def ticker_concentration(db: Session, *, days: int = 90, min_trades: int = 5) -> list[Anomaly]:
    """Flag tickers with an unusually high concentration of congressional trades."""
    cutoff = date.today() - timedelta(days=days)
    rows = list(
        db.execute(
            select(StockTrade.ticker).where(
                StockTrade.ticker.isnot(None), StockTrade.trade_date >= cutoff
            )
        ).scalars()
    )
    if not rows:
        return []
    unique, counts = np.unique(np.array([t for t in rows if t]), return_counts=True)
    if counts.size < 2:
        return []
    mean, std = counts.mean(), counts.std()
    out: list[Anomaly] = []
    for ticker, count in zip(unique, counts, strict=False):
        if count < min_trades:
            continue
        if std <= 0:
            continue
        z = float((count - mean) / std)
        if z >= 2.0:
            out.append(
                Anomaly(
                    kind="ticker_concentration",
                    description=f"{ticker}: {count} trades in last {days}d (z={z:.2f})",
                    z_score=z,
                )
            )
    return sorted(out, key=lambda a: -(a.z_score or 0))


def late_disclosure_cluster(db: Session, *, days: int = 90) -> list[Anomaly]:
    """Members with repeated late disclosures in the recent window."""
    cutoff = date.today() - timedelta(days=days)
    rows = list(
        db.execute(
            select(StockTrade.member_id, StockTrade.disclosure_delay_days).where(
                StockTrade.trade_date >= cutoff,
                StockTrade.disclosure_delay_days.isnot(None),
            )
        ).all()
    )
    by_member: dict[str, list[int]] = {}
    for member_id, delay in rows:
        if delay is None:
            continue
        by_member.setdefault(member_id, []).append(int(delay))

    out: list[Anomaly] = []
    for member_id, delays in by_member.items():
        late = [d for d in delays if d > 45]
        if len(late) >= 3:
            out.append(
                Anomaly(
                    kind="late_disclosure_cluster",
                    description=f"{member_id}: {len(late)} late (>45d) disclosures in {days}d",
                )
            )
    return out
