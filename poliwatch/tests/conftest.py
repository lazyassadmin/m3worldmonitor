"""Shared pytest fixtures — isolated SQLite DB per test session."""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Ensure the project root is on sys.path for ``import poliwatch``.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _sqlite_db() -> Iterator[str]:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp.name}"
    os.environ["SUSPICION_ALERT_THRESHOLD"] = "60"
    os.environ["LOG_LEVEL"] = "WARNING"

    # Reset cached settings/engine created from any earlier import.
    from poliwatch.config import get_settings

    get_settings.cache_clear()

    # Rebuild engine with the new URL.
    import poliwatch.database as dbmod

    dbmod.engine.dispose()
    dbmod.engine = dbmod._make_engine()  # type: ignore[attr-defined]
    dbmod.SessionLocal.configure(bind=dbmod.engine)
    dbmod.init_db()

    yield tmp.name

    try:
        os.unlink(tmp.name)
    except OSError:
        pass


@pytest.fixture()
def db_session() -> Iterator:
    from poliwatch.database import SessionLocal
    from poliwatch.models.alert import SuspiciousTradeAlert
    from poliwatch.models.bill import Bill
    from poliwatch.models.member import CongressMember
    from poliwatch.models.source_health import DataSourceHealth
    from poliwatch.models.trade import StockTrade
    from poliwatch.models.vote import Vote

    session = SessionLocal()
    try:
        # Clean slate per test.
        for model in (
            SuspiciousTradeAlert,
            Vote,
            StockTrade,
            Bill,
            CongressMember,
            DataSourceHealth,
        ):
            session.query(model).delete()
        session.commit()
        yield session
    finally:
        session.close()
