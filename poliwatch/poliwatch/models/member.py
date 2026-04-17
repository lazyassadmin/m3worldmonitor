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

    bioguide_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    party: Mapped[str] = mapped_column(String(50))
    state: Mapped[str] = mapped_column(String(2))
    chamber: Mapped[str] = mapped_column(String(10))  # house / senate
    committees: Mapped[list] = mapped_column(JSON, default=list)
    opensecrets_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    trades: Mapped[list["StockTrade"]] = relationship("StockTrade", back_populates="member")
    votes: Mapped[list["Vote"]] = relationship("Vote", back_populates="member")
