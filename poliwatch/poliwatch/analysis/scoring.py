"""Suspicion-score stub — replaced in the analysis commit."""

from __future__ import annotations

from sqlalchemy.orm import Session


def rescore_recent_trades(db: Session, *, lookback_days: int | None = 180) -> int:
    """Placeholder so the scheduler can import this symbol. Returns 0.

    The real implementation ships in the analysis commit.
    """
    _ = db, lookback_days
    return 0
