"""Tests for scoring + correlation."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from poliwatch.analysis.correlation import correlate_trade_to_legislation
from poliwatch.analysis.scoring import (
    maybe_create_alert,
    rescore_recent_trades,
    score_trade,
)
from poliwatch.models.alert import SuspiciousTradeAlert
from poliwatch.models.bill import Bill
from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade, TradeType


@pytest.fixture()
def setup_world(db_session):
    """Seed a senator on Armed Services, a defense bill, and a matching trade."""
    trade_day = date(2024, 6, 20)

    member = CongressMember(
        bioguide_id="S000001",
        name="Senator Test",
        party="Republican",
        state="TX",
        chamber="senate",
        committees=["Committee on Armed Services"],
    )
    db_session.add(member)

    bill = Bill(
        bill_id="118-hr-9001",
        congress=118,
        bill_type="hr",
        bill_number=9001,
        title="Defense authorization requiring Lockheed Martin review",
        introduced_date=trade_day - timedelta(days=20),
        latest_action_date=trade_day - timedelta(days=10),
        subjects=["Armed Forces"],
        related_tickers=["LMT", "RTX"],
    )
    db_session.add(bill)
    db_session.flush()

    big = StockTrade(
        member_id=member.bioguide_id,
        ticker="LMT",
        asset_name="Lockheed Martin",
        trade_type=TradeType.PURCHASE,
        trade_date=trade_day,
        disclosure_date=trade_day + timedelta(days=61),
        disclosure_delay_days=61,
        amount_range="$250,001 - $500,000",
        amount_min=250001,
        amount_max=500000,
        source="quiver",
    )
    clean = StockTrade(
        member_id=member.bioguide_id,
        ticker="KO",
        asset_name="Coca-Cola",
        trade_type=TradeType.PURCHASE,
        trade_date=trade_day,
        disclosure_date=trade_day + timedelta(days=16),
        disclosure_delay_days=16,
        amount_range="$1,001 - $15,000",
        amount_min=1001,
        amount_max=15000,
        source="quiver",
    )
    for off in (30, 60, 89):
        db_session.add(
            StockTrade(
                member_id=member.bioguide_id,
                ticker="LMT",
                asset_name="Lockheed Martin",
                trade_type=TradeType.PURCHASE,
                trade_date=trade_day - timedelta(days=off),
                disclosure_date=None,
                disclosure_delay_days=None,
                amount_range="$15,001 - $50,000",
                amount_min=15001,
                amount_max=50000,
                source="quiver",
            )
        )
    db_session.add_all([big, clean])
    db_session.commit()
    return {"member": member, "bill": bill, "big": big, "clean": clean, "trade_day": trade_day}


def test_correlation_finds_bill(setup_world, db_session):
    results = correlate_trade_to_legislation(setup_world["big"], db_session)
    assert len(results) == 1
    top = results[0]
    assert top.bill.bill_id == "118-hr-9001"
    assert top.proximity_days == 10
    assert "LMT" in top.reason


def test_correlation_skips_unrelated_trade(setup_world, db_session):
    assert correlate_trade_to_legislation(setup_world["clean"], db_session) == []


def test_score_big_trade_maxes_out(setup_world, db_session):
    breakdown = score_trade(setup_world["big"], db_session)
    assert breakdown.score == 100.0
    assert breakdown.top_bill_id == "118-hr-9001"
    text = "\n".join(breakdown.factors)
    assert "disclosure delay" in text
    assert "committee overlap" in text
    assert "$250k" in text or "$500" in text
    assert "within 10 days" in text
    assert "4 trades in LMT within 90 days" in text


def test_score_clean_trade_is_zero(setup_world, db_session):
    breakdown = score_trade(setup_world["clean"], db_session)
    assert breakdown.score == 0.0
    assert breakdown.factors == []


def test_alert_created_above_threshold(setup_world, db_session):
    breakdown = score_trade(setup_world["big"], db_session)
    db_session.flush()
    alert = maybe_create_alert(setup_world["big"], breakdown, db_session, threshold=60.0)
    db_session.commit()
    assert alert is not None
    assert alert.score == 100.0
    assert alert.bill_id == "118-hr-9001"


def test_alert_not_duplicated_on_rescore(setup_world, db_session):
    rescore_recent_trades(db_session, lookback_days=3650, threshold=60.0)
    rescore_recent_trades(db_session, lookback_days=3650, threshold=60.0)
    count = (
        db_session.query(SuspiciousTradeAlert)
        .filter(SuspiciousTradeAlert.trade_id == setup_world["big"].id)
        .count()
    )
    assert count == 1


def test_threshold_filters_alerts(setup_world, db_session):
    breakdown = score_trade(setup_world["clean"], db_session)
    result = maybe_create_alert(
        setup_world["clean"], breakdown, db_session, threshold=60.0
    )
    assert result is None
