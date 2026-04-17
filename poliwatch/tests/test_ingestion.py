"""Tests for ingestion parsers and idempotent upserts."""

from __future__ import annotations

from datetime import date

import pytest

from poliwatch.ingestion._amounts import (
    disclosure_delay,
    parse_amount_range,
    parse_date,
    parse_trade_type,
)
from poliwatch.ingestion._tickers import (
    match_bill_text_to_tickers,
    sector_for_ticker,
    sectors_for_committee,
)
from poliwatch.ingestion._upsert import ensure_placeholder_member, upsert_trade
from poliwatch.models.trade import TradeType


# ---------------------------------------------------------------- amounts

@pytest.mark.parametrize(
    "raw,expected_lo,expected_hi,expected_label",
    [
        ("$1,001 - $15,000", 1001, 15000, "$1,001 - $15,000"),
        ("$50,001 - $100,000", 50001, 100000, "$50,001 - $100,000"),
        ("$500,001 - $1,000,000", 500001, 1000000, "$500,001 - $1,000,000"),
        ("Over $50,000,000", 50000001, 100000000, "Over $50,000,000"),
        (None, None, None, None),
        ("", None, None, None),
    ],
)
def test_parse_amount_range(raw, expected_lo, expected_hi, expected_label):
    lo, hi, label = parse_amount_range(raw)
    assert lo == expected_lo
    assert hi == expected_hi
    assert label == expected_label


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Purchase", TradeType.PURCHASE),
        ("P", TradeType.PURCHASE),
        ("Sale", TradeType.SALE),
        ("S (partial)", TradeType.SALE_PARTIAL),
        ("S (Full)", TradeType.SALE_FULL),
        ("Exchange", TradeType.EXCHANGE),
        ("weird", TradeType.OTHER),
        ("", TradeType.OTHER),
        (None, TradeType.OTHER),
    ],
)
def test_parse_trade_type(raw, expected):
    assert parse_trade_type(raw) is expected


def test_parse_date_and_delay():
    assert parse_date("2024-03-15") == date(2024, 3, 15)
    assert parse_date("03/15/2024") == date(2024, 3, 15)
    assert parse_date("garbage") is None
    assert parse_date(None) is None
    assert disclosure_delay(date(2024, 3, 15), date(2024, 5, 1)) == 47
    assert disclosure_delay(None, date(2024, 5, 1)) is None


# ---------------------------------------------------------------- tickers

def test_sector_for_ticker():
    assert sector_for_ticker("NVDA") == "technology"
    assert sector_for_ticker("LMT") == "defense"
    assert sector_for_ticker("JNJ") == "healthcare"
    assert sector_for_ticker("ZZZ") is None


def test_sectors_for_committee():
    assert "defense" in sectors_for_committee("House Committee on Armed Services")
    assert "financial" in sectors_for_committee("Senate Committee on Banking, Housing")
    assert "healthcare" in sectors_for_committee("Subcommittee on Health")
    assert sectors_for_committee("Random Subcommittee") == set()


def test_match_bill_text_defense_keyword():
    matches = match_bill_text_to_tickers(
        "Defense appropriations requiring compliance review",
        subjects=["Armed Forces"],
    )
    tickers = {m.ticker for m in matches}
    assert {"LMT", "RTX", "GD", "NOC"}.issubset(tickers)


def test_match_bill_text_company_fuzzy():
    matches = match_bill_text_to_tickers("A bill concerning Lockheed Martin supply chain")
    assert any(m.ticker == "LMT" and m.matched_on == "company" for m in matches) or any(
        m.ticker == "LMT" for m in matches
    )


# ---------------------------------------------------------------- upserts

def test_upsert_trade_idempotent(db_session):
    member = ensure_placeholder_member(db_session, "Jane Sample", "house")
    db_session.flush()
    kwargs = {
        "member_id": member.bioguide_id,
        "ticker": "NVDA",
        "asset_name": "Nvidia",
        "trade_type": TradeType.PURCHASE,
        "trade_date": date(2024, 5, 10),
        "disclosure_date": date(2024, 6, 1),
        "disclosure_delay_days": 22,
        "amount_range": "$15,001 - $50,000",
        "amount_min": 15001,
        "amount_max": 50000,
        "source": "quiver",
        "raw_url": None,
    }
    _t1, c1 = upsert_trade(db_session, **kwargs)
    _t2, c2 = upsert_trade(db_session, **kwargs)
    db_session.commit()
    assert c1 is True
    assert c2 is False


def test_upsert_trade_backfills_missing_disclosure(db_session):
    member = ensure_placeholder_member(db_session, "Jane Sample", "house")
    db_session.flush()
    base = {
        "member_id": member.bioguide_id,
        "ticker": "NVDA",
        "asset_name": "Nvidia",
        "trade_type": TradeType.PURCHASE,
        "trade_date": date(2024, 5, 10),
        "amount_range": "$15,001 - $50,000",
        "amount_min": 15001,
        "amount_max": 50000,
        "source": "quiver",
        "raw_url": None,
    }
    # First insert with no disclosure info.
    t1, _ = upsert_trade(
        db_session, disclosure_date=None, disclosure_delay_days=None, **base
    )
    db_session.commit()
    assert t1.disclosure_date is None

    # Re-ingest with disclosure info — should patch the existing row.
    t2, created = upsert_trade(
        db_session,
        disclosure_date=date(2024, 6, 1),
        disclosure_delay_days=22,
        **base,
    )
    db_session.commit()
    assert created is False
    assert t2.id == t1.id
    assert t2.disclosure_date == date(2024, 6, 1)
    assert t2.disclosure_delay_days == 22


def test_placeholder_member_stable_id(db_session):
    m1 = ensure_placeholder_member(db_session, "Foo Bar", "senate")
    m2 = ensure_placeholder_member(db_session, "Foo Bar", "senate")
    db_session.commit()
    assert m1.bioguide_id == m2.bioguide_id
    assert m1.bioguide_id.startswith("XS")
