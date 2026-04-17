from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poliwatch.database import Base
from poliwatch.models.bill import Bill
from poliwatch.models.trade import StockTrade


class SuspiciousTradeAlert(Base):
    __tablename__ = "suspicious_trade_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock_trades.id"))
    bill_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("bills.bill_id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    trade: Mapped[StockTrade] = relationship("StockTrade", back_populates="alerts")
    bill: Mapped[Bill | None] = relationship("Bill", back_populates="alerts")
