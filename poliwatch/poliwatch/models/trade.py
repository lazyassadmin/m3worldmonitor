"""Stock trade disclosure model."""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poliwatch.database import Base

if TYPE_CHECKING:
    from poliwatch.models.alert import SuspiciousTradeAlert
    from poliwatch.models.member import CongressMember


class TradeType(str, enum.Enum):
    PURCHASE = "purchase"
    SALE = "sale"
    EXCHANGE = "exchange"
    SALE_PARTIAL = "sale_partial"
    SALE_FULL = "sale_full"
    OTHER = "other"


class StockTrade(Base):
    __tablename__ = "stock_trades"
    __table_args__ = (
        # De-duplicate across re-ingestion runs.
        UniqueConstraint(
            "member_id",
            "ticker",
            "trade_date",
            "trade_type",
            "amount_range",
            name="uq_trade_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    member_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("congress_members.bioguide_id"), nullable=False, index=True
    )

    ticker: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    asset_name: Mapped[str] = mapped_column(String(500), nullable=False)

    trade_type: Mapped[TradeType] = mapped_column(
        Enum(TradeType, name="trade_type"), nullable=False
    )

    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    disclosure_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    disclosure_delay_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    amount_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_max: Mapped[int | None] = mapped_column(Integer, nullable=True)

    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # house|senate|quiver
    raw_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    suspicion_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    member: Mapped["CongressMember"] = relationship(back_populates="trades")
    alerts: Mapped[list["SuspiciousTradeAlert"]] = relationship(
        back_populates="trade", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<StockTrade {self.ticker or self.asset_name!r} {self.trade_type.value} "
            f"{self.trade_date} score={self.suspicion_score:.1f}>"
        )
