"""/members routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from poliwatch.api.schemas import MemberOut, TradeOut
from poliwatch.database import get_db
from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade

router = APIRouter(prefix="/members", tags=["members"])


@router.get("", response_model=list[MemberOut])
def list_members(
    chamber: str | None = Query(default=None, description="'house' or 'senate'"),
    party: str | None = Query(default=None),
    state: str | None = Query(default=None),
    q: str | None = Query(default=None, description="fuzzy-name search"),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
) -> list[MemberOut]:
    stmt = select(CongressMember)
    if chamber:
        stmt = stmt.where(CongressMember.chamber == chamber.lower())
    if party:
        stmt = stmt.where(CongressMember.party.ilike(f"%{party}%"))
    if state:
        stmt = stmt.where(CongressMember.state == state.upper())
    if q:
        stmt = stmt.where(CongressMember.name.ilike(f"%{q}%"))
    stmt = stmt.order_by(CongressMember.name).limit(limit)
    rows = list(db.execute(stmt).scalars().all())
    return [MemberOut.model_validate(r) for r in rows]


@router.get("/{bioguide_id}", response_model=MemberOut)
def get_member(bioguide_id: str, db: Session = Depends(get_db)) -> MemberOut:
    row = db.get(CongressMember, bioguide_id)
    if row is None:
        raise HTTPException(status_code=404, detail="member not found")
    return MemberOut.model_validate(row)


@router.get("/{bioguide_id}/trades", response_model=list[TradeOut])
def member_trades(
    bioguide_id: str,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
) -> list[TradeOut]:
    member = db.get(CongressMember, bioguide_id)
    if member is None:
        raise HTTPException(status_code=404, detail="member not found")
    stmt = (
        select(StockTrade)
        .where(StockTrade.member_id == bioguide_id)
        .order_by(StockTrade.trade_date.desc())
        .limit(limit)
    )
    out: list[TradeOut] = []
    for t in db.execute(stmt).scalars().all():
        payload = TradeOut.model_validate(t)
        payload.member_name = member.name
        out.append(payload)
    return out
