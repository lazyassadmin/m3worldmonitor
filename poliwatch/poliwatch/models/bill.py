from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DATE, JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poliwatch.database import Base

if TYPE_CHECKING:
    from poliwatch.models.alert import SuspiciousTradeAlert
    from poliwatch.models.vote import Vote


class Bill(Base):
    __tablename__ = "bills"

    bill_id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g. "118-hr-1234"
    congress: Mapped[int] = mapped_column()
    bill_type: Mapped[str] = mapped_column(String(10))  # hr, s, hres, sres, …
    bill_number: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(String(1000))
    introduced_date: Mapped[date | None] = mapped_column(DATE, nullable=True)
    latest_action_date: Mapped[date | None] = mapped_column(DATE, nullable=True)
    subjects: Mapped[list] = mapped_column(JSON, default=list)
    related_tickers: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    votes: Mapped[list["Vote"]] = relationship("Vote", back_populates="bill")
    alerts: Mapped[list["SuspiciousTradeAlert"]] = relationship(
        "SuspiciousTradeAlert", back_populates="bill"
    )
