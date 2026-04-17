"""Pydantic response schemas for the REST API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bioguide_id: str
    name: str
    party: str | None
    state: str | None
    chamber: str
    committees: list[str] = Field(default_factory=list)
    opensecrets_id: str | None = None


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_id: str
    member_name: str | None = None
    ticker: str | None
    asset_name: str
    trade_type: str
    trade_date: date
    disclosure_date: date | None
    disclosure_delay_days: int | None
    amount_range: str | None
    amount_min: int | None
    amount_max: int | None
    source: str
    raw_url: str | None
    suspicion_score: float


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trade_id: int
    bill_id: str | None
    reason: str
    score: float
    notified_at: datetime | None
    created_at: datetime


class HealthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    status: Literal["ok", "degraded", "down"]
    last_attempt_at: datetime
    last_success_at: datetime | None
    last_error: str | None
    records_last_run: int
