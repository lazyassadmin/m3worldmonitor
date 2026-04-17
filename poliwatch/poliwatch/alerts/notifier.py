"""Alert dispatch: SMTP email + Discord + Slack webhooks.

Invoked after each scoring pass. Only sends alerts that haven't been
``notified_at`` yet — safe to re-run.
"""

from __future__ import annotations

import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from poliwatch.config import get_settings
from poliwatch.models.alert import SuspiciousTradeAlert
from poliwatch.models.trade import StockTrade


def _format_alert(trade: StockTrade, alert: SuspiciousTradeAlert) -> str:
    member_name = trade.member.name if trade.member else trade.member_id
    ticker = trade.ticker or "(no ticker)"
    amount = trade.amount_range or "n/a"
    url = trade.raw_url or "(no source link)"
    return (
        f"[PoliWatch] Score {alert.score:.0f}/100 — {member_name}\n"
        f"Trade: {trade.trade_type.value} {ticker} on {trade.trade_date} — {amount}\n"
        f"Reason:\n{alert.reason}\n"
        f"Source: {url}\n"
    )


def _send_email(body: str, subject: str) -> bool:
    settings = get_settings()
    if not settings.has_smtp:
        logger.debug("SMTP not configured — skipping email alert")
        return False
    msg = EmailMessage()
    msg["From"] = settings.alert_email_from or settings.smtp_user
    msg["To"] = settings.alert_email_to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        logger.info("email alert → {}", settings.alert_email_to)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("SMTP send failed: {}", exc)
        return False


def _send_webhook(url: str, payload: dict) -> bool:
    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("webhook {} failed: {}", url, exc)
        return False


def _dispatch(trade: StockTrade, alert: SuspiciousTradeAlert) -> bool:
    settings = get_settings()
    body = _format_alert(trade, alert)
    member_name = trade.member.name if trade.member else trade.member_id
    subject = f"[PoliWatch] score {alert.score:.0f} — {member_name} {trade.ticker or ''}".strip()

    sent = False
    sent |= _send_email(body, subject)
    if settings.discord_webhook_url:
        sent |= _send_webhook(settings.discord_webhook_url, {"content": f"```\n{body}\n```"})
    if settings.slack_webhook_url:
        sent |= _send_webhook(settings.slack_webhook_url, {"text": body})
    return sent


def dispatch_pending_alerts(db: Session, *, limit: int = 50) -> int:
    """Send notifications for any alert with ``notified_at IS NULL``. Returns count sent."""
    stmt = (
        select(SuspiciousTradeAlert)
        .where(SuspiciousTradeAlert.notified_at.is_(None))
        .order_by(SuspiciousTradeAlert.score.desc())
        .limit(limit)
    )
    alerts = list(db.execute(stmt).scalars().all())
    if not alerts:
        return 0
    logger.info("dispatching {} pending alerts", len(alerts))

    sent_count = 0
    now = datetime.now(tz=timezone.utc)
    for alert in alerts:
        trade = db.get(StockTrade, alert.trade_id)
        if trade is None:
            continue
        if _dispatch(trade, alert):
            alert.notified_at = now
            db.add(alert)
            sent_count += 1
    db.commit()
    return sent_count
