"""PoliWatch Streamlit dashboard — 6-page interactive accountability tool."""

import asyncio
from functools import lru_cache

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import func, select

from poliwatch.database import async_session_factory, init_db
from poliwatch.models.alert import SuspiciousTradeAlert
from poliwatch.models.bill import Bill
from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade

st.set_page_config(
    page_title="PoliWatch",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async coroutine from sync Streamlit context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@st.cache_resource
def _init_db_once():
    run_async(init_db())


_init_db_once()


async def _query(coro):
    async with async_session_factory() as db:
        return await coro(db)


# ---------------------------------------------------------------------------
# Data loaders (cached per session via st.cache_data)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def load_trades(min_score: float = 0.0, limit: int = 1000) -> pd.DataFrame:
    async def _fetch(db):
        stmt = (
            select(StockTrade, CongressMember)
            .join(CongressMember, StockTrade.member_id == CongressMember.bioguide_id)
            .where(StockTrade.suspicion_score >= min_score)
            .order_by(StockTrade.trade_date.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "id": t.id,
                "member_id": t.member_id,
                "name": m.name,
                "party": m.party,
                "state": m.state,
                "chamber": m.chamber,
                "ticker": t.ticker,
                "asset_name": t.asset_name,
                "trade_type": t.trade_type,
                "trade_date": t.trade_date,
                "disclosure_date": t.disclosure_date,
                "disclosure_delay_days": t.disclosure_delay_days,
                "amount_range": t.amount_range,
                "amount_min": t.amount_min,
                "amount_max": t.amount_max,
                "suspicion_score": t.suspicion_score,
                "source": t.source,
                "raw_url": t.raw_url,
            }
            for t, m in rows
        ]

    rows = run_async(_query(_fetch))
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=300)
def load_members() -> pd.DataFrame:
    async def _fetch(db):
        result = await db.execute(select(CongressMember))
        members = result.scalars().all()
        return [
            {
                "bioguide_id": m.bioguide_id,
                "name": m.name,
                "party": m.party,
                "state": m.state,
                "chamber": m.chamber,
                "committees": m.committees,
            }
            for m in members
        ]

    rows = run_async(_query(_fetch))
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=300)
def load_alerts(min_score: float = 60.0) -> pd.DataFrame:
    async def _fetch(db):
        stmt = (
            select(SuspiciousTradeAlert, StockTrade, CongressMember)
            .join(StockTrade, SuspiciousTradeAlert.trade_id == StockTrade.id)
            .join(CongressMember, StockTrade.member_id == CongressMember.bioguide_id)
            .where(SuspiciousTradeAlert.score >= min_score)
            .order_by(SuspiciousTradeAlert.score.desc())
            .limit(500)
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "alert_id": a.id,
                "score": a.score,
                "reason": a.reason,
                "bill_id": a.bill_id,
                "created_at": a.created_at,
                "member_name": m.name,
                "party": m.party,
                "state": m.state,
                "ticker": t.ticker,
                "trade_type": t.trade_type,
                "trade_date": t.trade_date,
                "amount_range": t.amount_range,
                "raw_url": t.raw_url,
            }
            for a, t, m in rows
        ]

    rows = run_async(_query(_fetch))
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def page_overview():
    st.title("🏠 PoliWatch — Overview")
    st.caption("Real-time congressional stock trade accountability dashboard")

    df = load_trades()
    if df.empty:
        st.info("No trade data yet. Run the ingestion scheduler to fetch data.")
        st.code("python -m poliwatch.ingestion.scheduler --once")
        return

    now_month = pd.Timestamp.now().month
    this_month = df[pd.to_datetime(df["trade_date"]).dt.month == now_month]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Trades this month", len(this_month))
    col2.metric("Total trades", len(df))
    col3.metric("Avg suspicion score", f"{df['suspicion_score'].mean():.1f}")
    col4.metric("Flagged trades (≥60)", int((df["suspicion_score"] >= 60).sum()))

    st.subheader("Top 10 Most Suspicious Members")
    top = (
        df.groupby(["member_id", "name", "party", "state"])["suspicion_score"]
        .agg(["mean", "count", "max"])
        .reset_index()
        .rename(columns={"mean": "Avg Score", "count": "Trades", "max": "Max Score"})
        .sort_values("Avg Score", ascending=False)
        .head(10)
    )
    top[["Avg Score", "Max Score"]] = top[["Avg Score", "Max Score"]].round(1)
    st.dataframe(top[["name", "party", "state", "Avg Score", "Trades", "Max Score"]], use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.histogram(df, x="suspicion_score", nbins=20, title="Suspicion Score Distribution")
        st.plotly_chart(fig, use_container_width=True)
    with col_b:
        party_counts = df.groupby("party").size().reset_index(name="count")
        fig2 = px.pie(party_counts, values="count", names="party", title="Trades by Party")
        st.plotly_chart(fig2, use_container_width=True)


def page_member_explorer():
    st.title("👤 Member Explorer")
    members_df = load_members()
    if members_df.empty:
        st.info("No member data yet.")
        return

    name_to_id = dict(zip(members_df["name"], members_df["bioguide_id"]))
    selected_name = st.selectbox("Select a member", sorted(name_to_id.keys()))
    if not selected_name:
        return

    bio_id = name_to_id[selected_name]
    member = members_df[members_df["bioguide_id"] == bio_id].iloc[0]

    st.subheader(f"{member['name']} — {member['party']}, {member['state']} ({member['chamber'].title()})")

    committees = member["committees"]
    if committees:
        st.write("**Committees:**", ", ".join(committees))

    trades_df = load_trades()
    member_trades = trades_df[trades_df["member_id"] == bio_id]

    if member_trades.empty:
        st.info("No trades recorded for this member.")
        return

    st.metric("Total trades", len(member_trades))
    st.metric("Avg suspicion score", f"{member_trades['suspicion_score'].mean():.1f}")

    st.subheader("Trades")
    display_cols = ["trade_date", "ticker", "trade_type", "amount_range", "suspicion_score", "source"]
    st.dataframe(
        member_trades[display_cols].sort_values("trade_date", ascending=False),
        use_container_width=True,
    )

    fig = px.scatter(
        member_trades,
        x="trade_date",
        y="suspicion_score",
        color="trade_type",
        hover_data=["ticker", "amount_range"],
        title="Trade Timeline",
    )
    st.plotly_chart(fig, use_container_width=True)


def page_trade_feed():
    st.title("📈 Trade Feed")

    with st.sidebar:
        st.header("Filters")
        party_filter = st.selectbox("Party", ["All", "Republican", "Democrat", "Independent"])
        chamber_filter = st.selectbox("Chamber", ["All", "house", "senate"])
        min_score = st.slider("Min suspicion score", 0, 100, 0)
        ticker_filter = st.text_input("Ticker (optional)").strip().upper()

    df = load_trades(min_score=min_score)
    if df.empty:
        st.info("No trades match the current filters.")
        return

    if party_filter != "All":
        df = df[df["party"].str.contains(party_filter, case=False, na=False)]
    if chamber_filter != "All":
        df = df[df["chamber"] == chamber_filter]
    if ticker_filter:
        df = df[df["ticker"] == ticker_filter]

    st.write(f"Showing {len(df)} trades")

    display_cols = [
        "trade_date", "name", "party", "state", "chamber",
        "ticker", "trade_type", "amount_range", "disclosure_delay_days", "suspicion_score",
    ]
    st.dataframe(df[display_cols].sort_values("suspicion_score", ascending=False), use_container_width=True)


def page_ticker_deep_dive():
    st.title("🔍 Ticker Deep Dive")
    ticker = st.text_input("Enter a stock ticker (e.g. NVDA, AAPL)", "").strip().upper()
    if not ticker:
        st.info("Enter a ticker symbol above.")
        return

    df = load_trades()
    tick_df = df[df["ticker"] == ticker]

    if tick_df.empty:
        st.warning(f"No congressional trades found for {ticker}")
        return

    st.metric("Total congressional trades in " + ticker, len(tick_df))
    st.metric("Avg suspicion score", f"{tick_df['suspicion_score'].mean():.1f}")

    col1, col2 = st.columns(2)
    with col1:
        party_split = tick_df.groupby("party").size().reset_index(name="count")
        fig = px.pie(party_split, values="count", names="party", title="Trades by Party")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig2 = px.scatter(
            tick_df,
            x="trade_date",
            y="suspicion_score",
            color="trade_type",
            hover_data=["name", "amount_range"],
            title="Trade Timeline",
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("All Trades")
    display_cols = ["trade_date", "name", "party", "state", "trade_type", "amount_range", "suspicion_score"]
    st.dataframe(tick_df[display_cols].sort_values("trade_date", ascending=False), use_container_width=True)


def page_alerts():
    st.title("🚨 Suspicious Trade Alerts")
    threshold = st.slider("Min suspicion score", 0, 100, 60)
    df = load_alerts(min_score=threshold)

    if df.empty:
        st.success(f"No trades with suspicion score ≥ {threshold}")
        return

    st.write(f"**{len(df)} alerts** with score ≥ {threshold}")
    for _, row in df.iterrows():
        with st.expander(
            f"[{row['score']:.0f}/100] {row['member_name']} — {row['ticker']} ({row['trade_type']}) on {row['trade_date']}"
        ):
            st.write(f"**Party/State:** {row['party']}, {row['state']}")
            st.write(f"**Amount:** {row['amount_range']}")
            st.write(f"**Score:** {row['score']:.1f}/100")
            st.write(f"**Reason:** {row['reason']}")
            if row.get("bill_id"):
                st.write(f"**Correlated bill:** {row['bill_id']}")
            if row.get("raw_url"):
                st.markdown(f"[View original filing]({row['raw_url']})")


def page_statistics():
    st.title("📊 Statistics")
    df = load_trades()
    if df.empty:
        st.info("No data available.")
        return

    col1, col2 = st.columns(2)

    with col1:
        party_trades = df.groupby("party").size().reset_index(name="count")
        fig = px.bar(party_trades, x="party", y="count", title="Trades by Party", color="party")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig2 = px.histogram(
            df, x="disclosure_delay_days", nbins=30, title="Disclosure Delay Distribution (days)"
        )
        fig2.add_vline(x=30, line_dash="dash", line_color="orange", annotation_text="30-day limit")
        fig2.add_vline(x=45, line_dash="dash", line_color="red", annotation_text="45-day limit")
        st.plotly_chart(fig2, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        chamber_trades = df.groupby("chamber").size().reset_index(name="count")
        fig3 = px.pie(chamber_trades, values="count", names="chamber", title="Trades by Chamber")
        st.plotly_chart(fig3, use_container_width=True)

    with col4:
        fig4 = px.histogram(df, x="suspicion_score", nbins=20, title="Suspicion Score Distribution")
        st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Top 20 Most Traded Tickers")
    top_tickers = df.groupby("ticker").size().reset_index(name="count").sort_values("count", ascending=False).head(20)
    fig5 = px.bar(top_tickers, x="ticker", y="count", title="Most Traded Tickers")
    st.plotly_chart(fig5, use_container_width=True)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

PAGES = {
    "🏠 Overview": page_overview,
    "👤 Member Explorer": page_member_explorer,
    "📈 Trade Feed": page_trade_feed,
    "🔍 Ticker Deep Dive": page_ticker_deep_dive,
    "🚨 Alerts": page_alerts,
    "📊 Statistics": page_statistics,
}

with st.sidebar:
    st.title("PoliWatch")
    st.caption("Congressional trade accountability")
    page = st.radio("Navigate", list(PAGES.keys()))

PAGES[page]()
