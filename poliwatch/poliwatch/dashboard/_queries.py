"""Cached query helpers for the Streamlit dashboard."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from poliwatch.models.alert import SuspiciousTradeAlert
from poliwatch.models.member import CongressMember
from poliwatch.models.source_health import DataSourceHealth
from poliwatch.models.trade import StockTrade


def trades_dataframe(db: Session, *, since_days: int = 365, limit: int = 5000) -> pd.DataFrame:
    cutoff = date.today() - timedelta(days=since_days)
    stmt = (
        select(StockTrade)
        .options(joinedload(StockTrade.member))
        .where(StockTrade.trade_date >= cutoff)
        .order_by(StockTrade.trade_date.desc())
        .limit(limit)
    )
    rows = list(db.execute(stmt).scalars().unique().all())
    records = [
        {
            "id": t.id,
            "member": t.member.name if t.member else t.member_id,
            "party": t.member.party if t.member else None,
            "chamber": t.member.chamber if t.member else None,
            "state": t.member.state if t.member else None,
            "ticker": t.ticker,
            "asset_name": t.asset_name,
            "trade_type": t.trade_type.value,
            "trade_date": t.trade_date,
            "disclosure_date": t.disclosure_date,
            "disclosure_delay_days": t.disclosure_delay_days,
            "amount_range": t.amount_range,
            "amount_min": t.amount_min,
            "amount_max": t.amount_max,
            "source": t.source,
            "raw_url": t.raw_url,
            "suspicion_score": t.suspicion_score,
        }
        for t in rows
    ]
    df = pd.DataFrame.from_records(records)
    if df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


def members_dataframe(db: Session) -> pd.DataFrame:
    rows = list(db.execute(select(CongressMember)).scalars().all())
    return pd.DataFrame.from_records(
        [
            {
                "bioguide_id": m.bioguide_id,
                "name": m.name,
                "party": m.party,
                "state": m.state,
                "chamber": m.chamber,
                "committees": m.committees or [],
            }
            for m in rows
        ]
    )


def alerts_dataframe(db: Session, *, min_score: float = 60.0) -> pd.DataFrame:
    stmt = (
        select(SuspiciousTradeAlert, StockTrade, CongressMember)
        .join(StockTrade, StockTrade.id == SuspiciousTradeAlert.trade_id)
        .join(CongressMember, CongressMember.bioguide_id == StockTrade.member_id)
        .where(SuspiciousTradeAlert.score >= min_score)
        .order_by(SuspiciousTradeAlert.score.desc())
    )
    records = []
    for alert, trade, member in db.execute(stmt).all():
        records.append(
            {
                "alert_id": alert.id,
                "score": alert.score,
                "bill_id": alert.bill_id,
                "member": member.name,
                "party": member.party,
                "chamber": member.chamber,
                "ticker": trade.ticker,
                "trade_type": trade.trade_type.value,
                "trade_date": trade.trade_date,
                "amount_range": trade.amount_range,
                "disclosure_delay_days": trade.disclosure_delay_days,
                "raw_url": trade.raw_url,
                "reason": alert.reason,
                "notified_at": alert.notified_at,
            }
        )
    return pd.DataFrame.from_records(records)


def most_suspicious_members(df_trades: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    if df_trades.empty:
        return df_trades
    agg = (
        df_trades.groupby("member", as_index=False)
        .agg(
            trades=("id", "count"),
            avg_score=("suspicion_score", "mean"),
            max_score=("suspicion_score", "max"),
        )
        .sort_values(["avg_score", "max_score"], ascending=False)
        .head(n)
    )
    agg["avg_score"] = agg["avg_score"].round(1)
    return agg


def source_health_df(db: Session) -> pd.DataFrame:
    rows = list(db.execute(select(DataSourceHealth)).scalars().all())
    return pd.DataFrame.from_records(
        [
            {
                "source": r.source,
                "status": r.status,
                "records_last_run": r.records_last_run,
                "last_attempt_at": r.last_attempt_at,
                "last_success_at": r.last_success_at,
                "last_error": r.last_error,
            }
            for r in rows
        ]
    )


def counts_summary(db: Session) -> dict[str, int]:
    return {
        "members": db.execute(select(func.count()).select_from(CongressMember)).scalar_one(),
        "trades": db.execute(select(func.count()).select_from(StockTrade)).scalar_one(),
        "alerts": db.execute(select(func.count()).select_from(SuspiciousTradeAlert)).scalar_one(),
    }
