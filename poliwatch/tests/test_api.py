"""Tests for FastAPI routes."""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from poliwatch.database import Base, get_db
from poliwatch.api.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(TEST_DB_URL)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


async def override_get_db():
    async with _test_session_factory() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_members_empty(client):
    resp = client.get("/members/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_trades_empty(client):
    resp = client.get("/trades/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_alerts_empty(client):
    resp = client.get("/alerts/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_member_not_found(client):
    resp = client.get("/members/NONEXISTENT")
    assert resp.status_code == 404
