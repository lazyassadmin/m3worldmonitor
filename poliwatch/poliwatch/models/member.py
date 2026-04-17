"""Congress member model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poliwatch.database import Base

if TYPE_CHECKING:
    from poliwatch.models.trade import StockTrade
    from poliwatch.models.vote import Vote


class CongressMember(Base):
    __tablename__ = "congress_members"

    bioguide_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    party: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)
    chamber: Mapped[str] = mapped_column(String(8), nullable=False, index=True)  # house|senate

    # Stored as JSON list[str] of committee names
    committees: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    opensecrets_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    trades: Mapped[list["StockTrade"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )
    votes: Mapped[list["Vote"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CongressMember {self.bioguide_id} {self.name} ({self.party}-{self.state})>"
