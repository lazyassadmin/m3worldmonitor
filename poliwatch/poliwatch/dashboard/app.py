"""Streamlit dashboard entry point.

Run: streamlit run poliwatch/dashboard/app.py
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from poliwatch import __version__
from poliwatch.config import get_settings
from poliwatch.dashboard._queries import (
    alerts_dataframe,
    counts_summary,
    members_dataframe,
    most_suspicious_members,
    source_health_df,
    trades_dataframe,
)
from poliwatch.database import session_scope

st.set_page_config(
    page_title="PoliWatch",
    page_icon="🗳️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=300)
def _load_trades(since_days: int = 365) -> pd.DataFrame:
    with session_scope() as db:
        return trades_dataframe(db, since_days=since_days)


@st.cache_data(ttl=300)
def _load_members() -> pd.DataFrame:
    with session_scope() as db:
        return members_dataframe(db)


@st.cache_data(ttl=300)
def _load_alerts(min_score: float) -> pd.DataFrame:
    with session_scope() as db:
        return alerts_dataframe(db, min_score=min_score)


@st.cache_data(ttl=300)
def _load_health() -> pd.DataFrame:
    with session_scope() as db:
        return source_health_df(db)


@st.cache_data(ttl=300)
def _load_counts() -> dict[str, int]:
    with session_scope() as db:
        return counts_summary(db)


def _header(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)


def _sidebar() -> str:
    settings = get_settings()
    with st.sidebar:
        st.markdown("### 🗳️  PoliWatch")
        st.caption(f"v{__version__} · threshold {settings.suspicion_alert_threshold:.0f}")
        page = st.radio(
            "Page",
            options=[
                "🏠 Overview",
                "👤 Member Explorer",
                "📈 Trade Feed",
                "🔍 Ticker Deep Dive",
                "🚨 Alerts",
                "📊 Statistics",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        health = _load_health()
        if not health.empty:
            st.caption("**Data source health**")
            for _, row in health.iterrows():
                emoji = {"ok": "🟢", "degraded": "🟡"}.get(row["status"], "🔴")
                st.caption(f"{emoji} `{row['source']}` — {row['records_last_run']} records")
        if st.button("🔄 Refresh cache"):
            st.cache_data.clear()
            st.rerun()
    return page


def _page_overview() -> None:
    _header("Overview", "Top-level summary of recent congressional trading activity.")
    counts = _load_counts()
    trades = _load_trades(since_days=30)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Members tracked", f"{counts['members']:,}")
    c2.metric("Trades (30d)", f"{len(trades):,}")
    c3.metric(
        "Avg suspicion score (30d)",
        f"{trades['suspicion_score'].mean():.1f}" if not trades.empty else "—",
    )
    c4.metric("Open alerts", f"{counts['alerts']:,}")

    if trades.empty:
        st.info("No trades ingested yet. Run the scheduler with `--once` or `--backfill`.")
        return

    st.markdown("### Most suspicious members (30d)")
    st.dataframe(
        most_suspicious_members(trades, n=10),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Recent high-score trades")
    hot = (
        trades[trades["suspicion_score"] > 0]
        .sort_values("suspicion_score", ascending=False)
        .head(15)
    )
    st.dataframe(
        hot[
            [
                "trade_date",
                "member",
                "party",
                "chamber",
                "ticker",
                "trade_type",
                "amount_range",
                "suspicion_score",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


def _page_member_explorer() -> None:
    _header("Member Explorer", "Drill into an individual member's trades and context.")
    members = _load_members()
    if members.empty:
        st.info("No members loaded. Run the scheduler first.")
        return

    label = st.selectbox(
        "Select a member",
        options=members.apply(
            lambda r: f"{r['name']} ({r['party'] or '?'}-{r['state'] or '?'}, {r['chamber']})",
            axis=1,
        ).tolist(),
    )
    member_row = members.iloc[
        members.apply(
            lambda r: f"{r['name']} ({r['party'] or '?'}-{r['state'] or '?'}, {r['chamber']})",
            axis=1,
        )
        .tolist()
        .index(label)
    ]
    bioguide = member_row["bioguide_id"]

    st.caption(f"**Bioguide:** `{bioguide}`")
    if member_row["committees"]:
        st.caption("**Committees:** " + ", ".join(member_row["committees"]))

    trades = _load_trades(since_days=3650)
    member_trades = trades[trades["member"] == member_row["name"]]

    c1, c2, c3 = st.columns(3)
    c1.metric("Trades", f"{len(member_trades):,}")
    c2.metric(
        "Avg score",
        f"{member_trades['suspicion_score'].mean():.1f}" if not member_trades.empty else "—",
    )
    c3.metric(
        "Max score",
        f"{member_trades['suspicion_score'].max():.1f}" if not member_trades.empty else "—",
    )

    if member_trades.empty:
        st.info("No trades for this member in the loaded window.")
        return

    fig = px.scatter(
        member_trades,
        x="trade_date",
        y="suspicion_score",
        color="trade_type",
        hover_data=["ticker", "amount_range", "disclosure_delay_days"],
        title="Trade timeline — suspicion score",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        member_trades.sort_values("trade_date", ascending=False)[
            [
                "trade_date",
                "ticker",
                "trade_type",
                "amount_range",
                "disclosure_delay_days",
                "suspicion_score",
                "source",
                "raw_url",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


def _page_trade_feed() -> None:
    _header("Trade Feed", "All recent trades — sortable, filterable.")
    trades = _load_trades(since_days=365)
    if trades.empty:
        st.info("No trades to show.")
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        chamber = st.selectbox("Chamber", options=["All", "house", "senate"])
    with c2:
        parties = ["All", *sorted(trades["party"].dropna().unique().tolist())]
        party = st.selectbox("Party", options=parties)
    with c3:
        tickers = ["All", *sorted(trades["ticker"].dropna().unique().tolist())]
        ticker = st.selectbox("Ticker", options=tickers)
    with c4:
        min_score = st.slider("Min suspicion score", 0, 100, 0)

    filtered = trades.copy()
    if chamber != "All":
        filtered = filtered[filtered["chamber"] == chamber]
    if party != "All":
        filtered = filtered[filtered["party"] == party]
    if ticker != "All":
        filtered = filtered[filtered["ticker"] == ticker]
    filtered = filtered[filtered["suspicion_score"] >= min_score]

    st.caption(f"Showing {len(filtered):,} trades")
    st.dataframe(
        filtered.sort_values("suspicion_score", ascending=False)[
            [
                "trade_date",
                "member",
                "party",
                "ticker",
                "trade_type",
                "amount_range",
                "disclosure_delay_days",
                "suspicion_score",
                "source",
                "raw_url",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


def _page_ticker_deep_dive() -> None:
    _header("Ticker Deep Dive", "All congressional activity in a single ticker.")
    trades = _load_trades(since_days=3650)
    if trades.empty:
        st.info("No trades to show.")
        return

    tickers = sorted(trades["ticker"].dropna().unique().tolist())
    ticker = st.selectbox("Ticker", options=tickers) if tickers else None
    if not ticker:
        return

    t_df = trades[trades["ticker"] == ticker]
    c1, c2, c3 = st.columns(3)
    c1.metric("Trades", f"{len(t_df):,}")
    c2.metric("Unique members", f"{t_df['member'].nunique():,}")
    c3.metric("Avg suspicion", f"{t_df['suspicion_score'].mean():.1f}")

    fig = px.scatter(
        t_df,
        x="trade_date",
        y="suspicion_score",
        color="party",
        symbol="trade_type",
        hover_data=["member", "amount_range", "disclosure_delay_days"],
        title=f"{ticker} — congressional trades over time",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        t_df.sort_values("trade_date", ascending=False)[
            [
                "trade_date",
                "member",
                "party",
                "chamber",
                "trade_type",
                "amount_range",
                "suspicion_score",
                "raw_url",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


def _page_alerts() -> None:
    settings = get_settings()
    _header(
        "Alerts",
        f"Trades with suspicion score ≥ {settings.suspicion_alert_threshold:.0f}.",
    )
    alerts = _load_alerts(min_score=settings.suspicion_alert_threshold)
    if alerts.empty:
        st.info("No alerts at or above the configured threshold.")
        return

    st.dataframe(
        alerts[
            [
                "score",
                "member",
                "party",
                "chamber",
                "ticker",
                "trade_date",
                "amount_range",
                "disclosure_delay_days",
                "bill_id",
                "notified_at",
                "raw_url",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Reason detail")
    for _, alert in alerts.head(10).iterrows():
        notified = (
            "✅ notified"
            if pd.notna(alert["notified_at"])
            else "⏳ pending notification"
        )
        with st.expander(
            f"{alert['score']:.0f} — {alert['member']} · {alert['ticker'] or '—'} · {alert['trade_date']} ({notified})"
        ):
            st.code(alert["reason"])
            if alert["raw_url"]:
                st.markdown(f"[Original filing]({alert['raw_url']})")


def _page_statistics() -> None:
    _header("Statistics", "Aggregate views over the last 365 days.")
    trades = _load_trades(since_days=365)
    if trades.empty:
        st.info("No trades to summarize yet.")
        return

    c1, c2 = st.columns(2)
    with c1:
        party_agg = trades.groupby("party", dropna=False, as_index=False).size().rename(columns={"size": "trades"})
        fig = px.bar(party_agg, x="party", y="trades", title="Trades by party")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        chamber_agg = trades.groupby("chamber", dropna=False, as_index=False).size().rename(columns={"size": "trades"})
        fig = px.pie(chamber_agg, names="chamber", values="trades", title="Trades by chamber")
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        delay = trades.dropna(subset=["disclosure_delay_days"])
        if not delay.empty:
            fig = px.histogram(
                delay,
                x="disclosure_delay_days",
                nbins=40,
                title="Disclosure delay (days)",
            )
            fig.add_vline(x=30, line_dash="dash", annotation_text="STOCK Act 30d")
            fig.add_vline(x=45, line_dash="dash", annotation_text="45d cap")
            st.plotly_chart(fig, use_container_width=True)
    with c4:
        fig = px.histogram(
            trades,
            x="suspicion_score",
            nbins=20,
            title="Suspicion score distribution",
        )
        st.plotly_chart(fig, use_container_width=True)


_PAGES = {
    "🏠 Overview": _page_overview,
    "👤 Member Explorer": _page_member_explorer,
    "📈 Trade Feed": _page_trade_feed,
    "🔍 Ticker Deep Dive": _page_ticker_deep_dive,
    "🚨 Alerts": _page_alerts,
    "📊 Statistics": _page_statistics,
}


def main() -> None:
    page = _sidebar()
    _PAGES[page]()
    st.caption(f"Rendered {datetime.utcnow().isoformat()} UTC")


def run() -> None:
    """Console-script entry point: ``poliwatch-dashboard``."""
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", __file__],
        check=False,
    )


if __name__ == "__main__":
    main()
