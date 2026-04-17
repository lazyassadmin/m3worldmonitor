"""Member API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from poliwatch.database import get_db
from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade

router = APIRouter()


@router.get("/")
async def list_members(
    chamber: str | None = Query(None, description="house or senate"),
    party: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = select(CongressMember)
    if chamber:
        stmt = stmt.where(CongressMember.chamber == chamber.lower())
    if party:
        stmt = stmt.where(CongressMember.party.ilike(f"%{party}%"))
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    members = result.scalars().all()
    return [
        {
            "bioguide_id": m.bioguide_id,
            "name": m.name,
            "party": m.party,
            "state": m.state,
            "chamber": m.chamber,
            "committees": m.committees,
        }
        for m in members
    ]


@router.get("/{bioguide_id}")
async def get_member(bioguide_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        select(CongressMember).where(CongressMember.bioguide_id == bioguide_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    trades_result = await db.execute(
        select(StockTrade)
        .where(StockTrade.member_id == bioguide_id)
        .order_by(StockTrade.trade_date.desc())
        .limit(50)
    )
    trades = trades_result.scalars().all()

    return {
        "bioguide_id": member.bioguide_id,
        "name": member.name,
        "party": member.party,
        "state": member.state,
        "chamber": member.chamber,
        "committees": member.committees,
        "recent_trades": [
            {
                "id": t.id,
                "ticker": t.ticker,
                "trade_type": t.trade_type,
                "trade_date": t.trade_date.isoformat(),
                "amount_range": t.amount_range,
                "suspicion_score": t.suspicion_score,
            }
            for t in trades
        ],
    }
