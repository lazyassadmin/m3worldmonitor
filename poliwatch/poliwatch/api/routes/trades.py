"""Trade API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from poliwatch.database import get_db
from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade

router = APIRouter()


@router.get("/")
async def list_trades(
    ticker: str | None = Query(None),
    member_id: str | None = Query(None),
    party: str | None = Query(None),
    chamber: str | None = Query(None),
    min_score: float = Query(0.0),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = (
        select(StockTrade, CongressMember)
        .join(CongressMember, StockTrade.member_id == CongressMember.bioguide_id)
        .where(StockTrade.suspicion_score >= min_score)
        .order_by(StockTrade.trade_date.desc())
    )
    if ticker:
        stmt = stmt.where(StockTrade.ticker == ticker.upper())
    if member_id:
        stmt = stmt.where(StockTrade.member_id == member_id)
    if party:
        stmt = stmt.where(CongressMember.party.ilike(f"%{party}%"))
    if chamber:
        stmt = stmt.where(CongressMember.chamber == chamber.lower())

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "id": t.id,
            "member_id": t.member_id,
            "member_name": m.name,
            "party": m.party,
            "state": m.state,
            "chamber": m.chamber,
            "ticker": t.ticker,
            "asset_name": t.asset_name,
            "trade_type": t.trade_type,
            "trade_date": t.trade_date.isoformat(),
            "disclosure_date": t.disclosure_date.isoformat(),
            "disclosure_delay_days": t.disclosure_delay_days,
            "amount_range": t.amount_range,
            "suspicion_score": t.suspicion_score,
            "source": t.source,
            "raw_url": t.raw_url,
        }
        for t, m in rows
    ]


@router.get("/ticker/{ticker}")
async def ticker_deep_dive(ticker: str, db: AsyncSession = Depends(get_db)) -> dict:
    stmt = (
        select(StockTrade, CongressMember)
        .join(CongressMember, StockTrade.member_id == CongressMember.bioguide_id)
        .where(StockTrade.ticker == ticker.upper())
        .order_by(StockTrade.trade_date.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    trades = [
        {
            "id": t.id,
            "member_name": m.name,
            "party": m.party,
            "trade_type": t.trade_type,
            "trade_date": t.trade_date.isoformat(),
            "amount_range": t.amount_range,
            "suspicion_score": t.suspicion_score,
        }
        for t, m in rows
    ]

    return {
        "ticker": ticker.upper(),
        "total_trades": len(trades),
        "trades": trades,
    }
