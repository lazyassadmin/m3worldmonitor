"""Email + webhook alert notifier for suspicious trades."""

import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from poliwatch.config import settings
from poliwatch.models.alert import SuspiciousTradeAlert
from poliwatch.models.member import CongressMember
from poliwatch.models.trade import StockTrade


def _send_email(subject: str, body: str) -> None:
    if not all([settings.smtp_user, settings.smtp_password, settings.alert_email_to]):
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.alert_email_from or settings.smtp_user
    msg["To"] = settings.alert_email_to
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


async def _send_webhook(payload: dict) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        for url in [settings.discord_webhook_url, settings.slack_webhook_url]:
            if not url:
                continue
            try:
                await client.post(url, json=payload)
            except Exception as exc:
                logger.warning(f"Webhook delivery failed ({url[:30]}…): {exc}")


async def send_alerts_for_new_trades(db: AsyncSession) -> int:
    """Create alert records and send notifications for high-score unalerted trades."""
    threshold = settings.suspicion_alert_threshold

    stmt = (
        select(StockTrade, CongressMember)
        .join(CongressMember, StockTrade.member_id == CongressMember.bioguide_id)
        .where(StockTrade.suspicion_score >= threshold)
        .outerjoin(SuspiciousTradeAlert, SuspiciousTradeAlert.trade_id == StockTrade.id)
        .where(SuspiciousTradeAlert.id.is_(None))  # no alert created yet
    )
    result = await db.execute(stmt)
    rows = result.all()

    sent = 0
    for trade, member in rows:
        from poliwatch.analysis.scoring import suspicion_score

        score, reason, correlated = await suspicion_score(trade, db)
        top_bill = correlated[0] if correlated else None

        alert = SuspiciousTradeAlert(
            trade_id=trade.id,
            bill_id=top_bill.bill_id if top_bill else None,
            reason=reason,
            score=score,
        )
        db.add(alert)
        await db.flush()

        # Compose notification
        subject = f"[PoliWatch] Suspicious trade: {member.name} — {trade.ticker} (score {score:.0f})"
        body = (
            f"Member: {member.name} ({member.party}, {member.state})\n"
            f"Ticker: {trade.ticker}\n"
            f"Trade type: {trade.trade_type}\n"
            f"Trade date: {trade.trade_date}\n"
            f"Disclosure delay: {trade.disclosure_delay_days} days\n"
            f"Amount: {trade.amount_range}\n"
            f"Suspicion score: {score:.1f}/100\n"
            f"Reason: {reason}\n"
        )
        if top_bill:
            body += f"Correlated bill: {top_bill.bill_id} — {top_bill.title}\n"
        if trade.raw_url:
            body += f"Filing: {trade.raw_url}\n"

        try:
            _send_email(subject, body)
        except Exception as exc:
            logger.error(f"Email send failed: {exc}")

        webhook_payload = {
            "content": subject,
            "embeds": [
                {
                    "title": subject,
                    "description": body,
                    "color": 0xFF4444,
                }
            ],
        }
        await _send_webhook(webhook_payload)

        alert.notified_at = datetime.now(timezone.utc)
        sent += 1

    await db.commit()
    logger.info(f"Alerts sent: {sent}")
    return sent
