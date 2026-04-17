"""/alerts routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from poliwatch.api.schemas import AlertOut, HealthOut
from poliwatch.database import get_db
from poliwatch.models.alert import SuspiciousTradeAlert
from poliwatch.models.source_health import DataSourceHealth

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(
    min_score: float | None = Query(default=None, ge=0, le=100),
    unnotified_only: bool = Query(default=False),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
) -> list[AlertOut]:
    stmt = select(SuspiciousTradeAlert)
    if min_score is not None:
        stmt = stmt.where(SuspiciousTradeAlert.score >= min_score)
    if unnotified_only:
        stmt = stmt.where(SuspiciousTradeAlert.notified_at.is_(None))
    stmt = stmt.order_by(SuspiciousTradeAlert.score.desc()).limit(limit)
    return [AlertOut.model_validate(r) for r in db.execute(stmt).scalars().all()]


@router.get("/health", response_model=list[HealthOut])
def source_health(db: Session = Depends(get_db)) -> list[HealthOut]:
    rows = list(db.execute(select(DataSourceHealth)).scalars().all())
    return [HealthOut.model_validate(r) for r in rows]
