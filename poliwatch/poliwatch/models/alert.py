"""Suspicious-trade alert model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poliwatch.database import Base

if TYPE_CHECKING:
    from poliwatch.models.trade import StockTrade


class SuspiciousTradeAlert(Base):
    __tablename__ = "suspicious_trade_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    trade_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_trades.id"), nullable=False, index=True
    )
    bill_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("bills.bill_id"), nullable=True, index=True
    )

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, index=True)

    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    trade: Mapped["StockTrade"] = relationship(back_populates="alerts")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SuspiciousTradeAlert trade={self.trade_id} score={self.score:.1f}>"
