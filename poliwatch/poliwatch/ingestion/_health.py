"""Helpers to update the data_source_health table after an ingestion run."""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from poliwatch.models.source_health import DataSourceHealth


def mark_success(db: Session, source: str, records: int) -> None:
    now = datetime.now(tz=timezone.utc)
    row = db.get(DataSourceHealth, source) or DataSourceHealth(source=source, status="ok")
    row.status = "ok"
    row.last_attempt_at = now
    row.last_success_at = now
    row.last_error = None
    row.records_last_run = records
    db.merge(row)
    db.commit()
    logger.info("[{}] OK ({} records)", source, records)


def mark_degraded(db: Session, source: str, error: str) -> None:
    now = datetime.now(tz=timezone.utc)
    row = db.get(DataSourceHealth, source) or DataSourceHealth(source=source, status="degraded")
    row.status = "degraded"
    row.last_attempt_at = now
    row.last_error = error[:2000]
    db.merge(row)
    db.commit()
    logger.warning("[{}] degraded: {}", source, error)


def list_health(db: Session) -> list[DataSourceHealth]:
    return list(db.execute(select(DataSourceHealth)).scalars().all())
