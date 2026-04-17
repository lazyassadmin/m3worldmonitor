"""Alert API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from poliwatch.config import settings
from poliwatch.database import get_db
from poliwatch.models.alert import SuspiciousTradeAlert
from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade

router = APIRouter()


@router.get("/")
async def list_alerts(
    min_score: float = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    threshold = min_score if min_score is not None else settings.suspicion_alert_threshold

    stmt = (
        select(SuspiciousTradeAlert, StockTrade, CongressMember)
        .join(StockTrade, SuspiciousTradeAlert.trade_id == StockTrade.id)
        .join(CongressMember, StockTrade.member_id == CongressMember.bioguide_id)
        .where(SuspiciousTradeAlert.score >= threshold)
        .order_by(SuspiciousTradeAlert.score.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "alert_id": a.id,
            "trade_id": a.trade_id,
            "bill_id": a.bill_id,
            "score": a.score,
            "reason": a.reason,
            "created_at": a.created_at.isoformat(),
            "notified_at": a.notified_at.isoformat() if a.notified_at else None,
            "member_name": m.name,
            "party": m.party,
            "state": m.state,
            "ticker": t.ticker,
            "trade_type": t.trade_type,
            "trade_date": t.trade_date.isoformat(),
            "amount_range": t.amount_range,
            "raw_url": t.raw_url,
        }
        for a, t, m in rows
    ]
