from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DATE, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poliwatch.database import Base

if TYPE_CHECKING:
    from poliwatch.models.alert import SuspiciousTradeAlert
    from poliwatch.models.member import CongressMember


class StockTrade(Base):
    __tablename__ = "stock_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    member_id: Mapped[str] = mapped_column(String(20), ForeignKey("congress_members.bioguide_id"))
    ticker: Mapped[str] = mapped_column(String(20))
    asset_name: Mapped[str] = mapped_column(String(300))
    trade_type: Mapped[str] = mapped_column(String(20))  # purchase / sale / exchange
    trade_date: Mapped[date] = mapped_column(DATE)
    disclosure_date: Mapped[date] = mapped_column(DATE)
    disclosure_delay_days: Mapped[int] = mapped_column(Integer)
    amount_range: Mapped[str] = mapped_column(String(50))
    amount_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20))  # house / senate / quiver
    raw_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    suspicion_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    member: Mapped["CongressMember"] = relationship("CongressMember", back_populates="trades")
    alerts: Mapped[list["SuspiciousTradeAlert"]] = relationship(
        "SuspiciousTradeAlert", back_populates="trade"
    )
