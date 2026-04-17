"""Roll-call vote model."""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poliwatch.database import Base

if TYPE_CHECKING:
    from poliwatch.models.bill import Bill
    from poliwatch.models.member import CongressMember


class VotePosition(str, enum.Enum):
    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"
    PRESENT = "present"
    NOT_VOTING = "not_voting"


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("member_id", "bill_id", "vote_date", name="uq_vote_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    member_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("congress_members.bioguide_id"), nullable=False, index=True
    )
    bill_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("bills.bill_id"), nullable=False, index=True
    )

    vote_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    vote_position: Mapped[VotePosition] = mapped_column(
        Enum(VotePosition, name="vote_position"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    member: Mapped["CongressMember"] = relationship(back_populates="votes")
    bill: Mapped["Bill"] = relationship(back_populates="votes")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Vote {self.member_id} {self.bill_id} "
            f"{self.vote_date} {self.vote_position.value}>"
        )
