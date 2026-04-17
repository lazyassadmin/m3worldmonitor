"""Bill / legislation model."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poliwatch.database import Base

if TYPE_CHECKING:
    from poliwatch.models.vote import Vote


class Bill(Base):
    __tablename__ = "bills"

    # e.g. "118-hr-1234" — congress-billtype-billnumber
    bill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    congress: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    bill_type: Mapped[str] = mapped_column(String(8), nullable=False)
    bill_number: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    introduced_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    latest_action_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    latest_action_text: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    subjects: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    related_tickers: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    votes: Mapped[list["Vote"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Bill {self.bill_id} {self.title[:60]!r}>"
