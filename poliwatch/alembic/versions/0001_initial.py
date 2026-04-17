"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-17

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "congress_members",
        sa.Column("bioguide_id", sa.String(length=16), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("party", sa.String(length=32), nullable=True),
        sa.Column("state", sa.String(length=4), nullable=True),
        sa.Column("chamber", sa.String(length=8), nullable=False),
        sa.Column("committees", sa.JSON(), nullable=False),
        sa.Column("opensecrets_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_congress_members_name", "congress_members", ["name"])
    op.create_index("ix_congress_members_party", "congress_members", ["party"])
    op.create_index("ix_congress_members_state", "congress_members", ["state"])
    op.create_index("ix_congress_members_chamber", "congress_members", ["chamber"])

    op.create_table(
        "bills",
        sa.Column("bill_id", sa.String(length=64), primary_key=True),
        sa.Column("congress", sa.Integer(), nullable=False),
        sa.Column("bill_type", sa.String(length=8), nullable=False),
        sa.Column("bill_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("introduced_date", sa.Date(), nullable=True),
        sa.Column("latest_action_date", sa.Date(), nullable=True),
        sa.Column("latest_action_text", sa.String(length=1000), nullable=True),
        sa.Column("subjects", sa.JSON(), nullable=False),
        sa.Column("related_tickers", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bills_congress", "bills", ["congress"])
    op.create_index("ix_bills_introduced_date", "bills", ["introduced_date"])
    op.create_index("ix_bills_latest_action_date", "bills", ["latest_action_date"])

    trade_type_enum = sa.Enum(
        "purchase",
        "sale",
        "exchange",
        "sale_partial",
        "sale_full",
        "other",
        name="trade_type",
    )
    op.create_table(
        "stock_trades",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("member_id", sa.String(length=16), sa.ForeignKey("congress_members.bioguide_id"), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=True),
        sa.Column("asset_name", sa.String(length=500), nullable=False),
        sa.Column("trade_type", trade_type_enum, nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("disclosure_date", sa.Date(), nullable=True),
        sa.Column("disclosure_delay_days", sa.Integer(), nullable=True),
        sa.Column("amount_range", sa.String(length=64), nullable=True),
        sa.Column("amount_min", sa.Integer(), nullable=True),
        sa.Column("amount_max", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("raw_url", sa.String(length=1000), nullable=True),
        sa.Column("suspicion_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "member_id",
            "ticker",
            "trade_date",
            "trade_type",
            "amount_range",
            name="uq_trade_identity",
        ),
    )
    op.create_index("ix_stock_trades_member_id", "stock_trades", ["member_id"])
    op.create_index("ix_stock_trades_ticker", "stock_trades", ["ticker"])
    op.create_index("ix_stock_trades_trade_date", "stock_trades", ["trade_date"])
    op.create_index("ix_stock_trades_source", "stock_trades", ["source"])
    op.create_index("ix_stock_trades_suspicion_score", "stock_trades", ["suspicion_score"])

    vote_position_enum = sa.Enum(
        "yes", "no", "abstain", "present", "not_voting", name="vote_position"
    )
    op.create_table(
        "votes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("member_id", sa.String(length=16), sa.ForeignKey("congress_members.bioguide_id"), nullable=False),
        sa.Column("bill_id", sa.String(length=64), sa.ForeignKey("bills.bill_id"), nullable=False),
        sa.Column("vote_date", sa.Date(), nullable=False),
        sa.Column("vote_position", vote_position_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("member_id", "bill_id", "vote_date", name="uq_vote_identity"),
    )
    op.create_index("ix_votes_member_id", "votes", ["member_id"])
    op.create_index("ix_votes_bill_id", "votes", ["bill_id"])
    op.create_index("ix_votes_vote_date", "votes", ["vote_date"])

    op.create_table(
        "suspicious_trade_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trade_id", sa.Integer(), sa.ForeignKey("stock_trades.id"), nullable=False),
        sa.Column("bill_id", sa.String(length=64), sa.ForeignKey("bills.bill_id"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_suspicious_trade_alerts_trade_id", "suspicious_trade_alerts", ["trade_id"])
    op.create_index("ix_suspicious_trade_alerts_bill_id", "suspicious_trade_alerts", ["bill_id"])
    op.create_index("ix_suspicious_trade_alerts_score", "suspicious_trade_alerts", ["score"])


def downgrade() -> None:
    op.drop_table("suspicious_trade_alerts")
    op.drop_table("votes")
    op.drop_table("stock_trades")
    op.drop_table("bills")
    op.drop_table("congress_members")
    sa.Enum(name="vote_position").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="trade_type").drop(op.get_bind(), checkfirst=True)
