"""FastAPI endpoint tests."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from poliwatch.api.main import app
from poliwatch.models.alert import SuspiciousTradeAlert
from poliwatch.models.member import CongressMember
from poliwatch.models.source_health import DataSourceHealth
from poliwatch.models.trade import StockTrade, TradeType


@pytest.fixture()
def seeded(db_session):
    alice = CongressMember(
        bioguide_id="A000001",
        name="Alice Alpha",
        party="Democrat",
        state="CA",
        chamber="house",
        committees=["Committee on Financial Services"],
    )
    bob = CongressMember(
        bioguide_id="B000001",
        name="Bob Beta",
        party="Republican",
        state="FL",
        chamber="senate",
        committees=["Committee on Armed Services"],
    )
    db_session.add_all([alice, bob])
    db_session.flush()

    t1 = StockTrade(
        member_id=alice.bioguide_id,
        ticker="NVDA",
        asset_name="Nvidia",
        trade_type=TradeType.PURCHASE,
        trade_date=date(2024, 6, 1),
        amount_range="$15,001 - $50,000",
        amount_min=15001,
        amount_max=50000,
        source="quiver",
        suspicion_score=85.0,
    )
    t2 = StockTrade(
        member_id=bob.bioguide_id,
        ticker="LMT",
        asset_name="Lockheed Martin",
        trade_type=TradeType.SALE,
        trade_date=date(2024, 6, 2),
        amount_range="$1,001 - $15,000",
        amount_min=1001,
        amount_max=15000,
        source="senate",
        suspicion_score=20.0,
    )
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add(
        SuspiciousTradeAlert(
            trade_id=t1.id,
            bill_id=None,
            reason="test alert",
            score=85.0,
        )
    )
    db_session.add(DataSourceHealth(source="quiver", status="ok", records_last_run=42))
    db_session.commit()
    return {"alice": alice, "bob": bob, "t1": t1, "t2": t2}


@pytest.fixture()
def client():
    return TestClient(app)


def test_root_and_healthz(client):
    assert client.get("/").json()["name"] == "PoliWatch"
    assert client.get("/healthz").json() == {"status": "ok"}


def test_members_list_and_filter(client, seeded):
    r = client.get("/members")
    assert r.status_code == 200
    assert len(r.json()) == 2

    r = client.get("/members", params={"chamber": "senate"})
    names = [m["name"] for m in r.json()]
    assert names == ["Bob Beta"]

    r = client.get("/members", params={"q": "alpha"})
    assert [m["bioguide_id"] for m in r.json()] == ["A000001"]


def test_member_trades(client, seeded):
    r = client.get(f"/members/{seeded['alice'].bioguide_id}/trades")
    assert r.status_code == 200
    assert [t["ticker"] for t in r.json()] == ["NVDA"]
    assert r.json()[0]["member_name"] == "Alice Alpha"


def test_member_not_found(client):
    assert client.get("/members/DOES_NOT_EXIST").status_code == 404


def test_trade_filters(client, seeded):
    r = client.get("/trades", params={"min_score": 50})
    assert [t["ticker"] for t in r.json()] == ["NVDA"]

    r = client.get("/trades", params={"source": "senate"})
    assert [t["ticker"] for t in r.json()] == ["LMT"]

    r = client.get("/trades/ticker/LMT")
    assert len(r.json()) == 1
    assert r.json()[0]["member_name"] == "Bob Beta"


def test_alerts_endpoints(client, seeded):
    r = client.get("/alerts")
    assert r.status_code == 200
    assert [a["score"] for a in r.json()] == [85.0]

    r = client.get("/alerts/health")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["source"] == "quiver"
    assert data[0]["status"] == "ok"
