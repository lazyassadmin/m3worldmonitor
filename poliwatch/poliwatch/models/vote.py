from datetime import date, datetime

from sqlalchemy import DATE, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poliwatch.database import Base
from poliwatch.models.bill import Bill
from poliwatch.models.member import CongressMember


class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    member_id: Mapped[str] = mapped_column(String(20), ForeignKey("congress_members.bioguide_id"))
    bill_id: Mapped[str] = mapped_column(String(50), ForeignKey("bills.bill_id"))
    vote_date: Mapped[date] = mapped_column(DATE)
    vote_position: Mapped[str] = mapped_column(String(20))  # yes / no / abstain / not voting
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    member: Mapped[CongressMember] = relationship("CongressMember", back_populates="votes")
    bill: Mapped[Bill] = relationship("Bill", back_populates="votes")
