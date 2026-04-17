"""/trades routes."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from poliwatch.api.schemas import TradeOut
from poliwatch.database import get_db
from poliwatch.models.trade import StockTrade

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("", response_model=list[TradeOut])
def list_trades(
    chamber: str | None = Query(default=None),
    party: str | None = Query(default=None),
    ticker: str | None = Query(default=None),
    source: str | None = Query(default=None, description="'quiver'|'house'|'senate'"),
    min_score: float | None = Query(default=None, ge=0, le=100),
    since_days: int | None = Query(default=None, ge=1, description="filter to last N days"),
    order_by: str = Query(default="suspicion_score", pattern="^(suspicion_score|trade_date)$"),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[TradeOut]:
    stmt = select(StockTrade).options(joinedload(StockTrade.member))
    if ticker:
        stmt = stmt.where(StockTrade.ticker == ticker.upper())
    if source:
        stmt = stmt.where(StockTrade.source == source.lower())
    if min_score is not None:
        stmt = stmt.where(StockTrade.suspicion_score >= min_score)
    if since_days is not None:
        stmt = stmt.where(StockTrade.trade_date >= date.today() - timedelta(days=since_days))
    if chamber or party:
        from poliwatch.models.member import CongressMember

        stmt = stmt.join(CongressMember, CongressMember.bioguide_id == StockTrade.member_id)
        if chamber:
            stmt = stmt.where(CongressMember.chamber == chamber.lower())
        if party:
            stmt = stmt.where(CongressMember.party.ilike(f"%{party}%"))

    if order_by == "trade_date":
        stmt = stmt.order_by(StockTrade.trade_date.desc())
    else:
        stmt = stmt.order_by(StockTrade.suspicion_score.desc(), StockTrade.trade_date.desc())
    stmt = stmt.offset(offset).limit(limit)

    out: list[TradeOut] = []
    for t in db.execute(stmt).scalars().unique().all():
        payload = TradeOut.model_validate(t)
        payload.member_name = t.member.name if t.member else None
        out.append(payload)
    return out


@router.get("/{trade_id}", response_model=TradeOut)
def get_trade(trade_id: int, db: Session = Depends(get_db)) -> TradeOut:
    trade = db.get(StockTrade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="trade not found")
    payload = TradeOut.model_validate(trade)
    payload.member_name = trade.member.name if trade.member else None
    return payload


@router.get("/ticker/{ticker}", response_model=list[TradeOut])
def ticker_deep_dive(
    ticker: str,
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
) -> list[TradeOut]:
    stmt = (
        select(StockTrade)
        .options(joinedload(StockTrade.member))
        .where(StockTrade.ticker == ticker.upper())
        .order_by(StockTrade.trade_date.desc())
        .limit(limit)
    )
    out: list[TradeOut] = []
    for t in db.execute(stmt).scalars().unique().all():
        payload = TradeOut.model_validate(t)
        payload.member_name = t.member.name if t.member else None
        out.append(payload)
    return out
