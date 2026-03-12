"""add_canonical_snapshot_tables

Revision ID: b31f4f4e8d2a
Revises: 9f2a6d7c1b41
Create Date: 2026-03-12 22:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "b31f4f4e8d2a"
down_revision: Union[str, None] = "9f2a6d7c1b41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _table_exists(inspector, "asset_technical_snapshots"):
        op.create_table(
            "asset_technical_snapshots",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("asset_id", sa.UUID(), nullable=False),
            sa.Column("timeframe", sa.String(), nullable=False),
            sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
            sa.Column("rsi_14", sa.Float(), nullable=True),
            sa.Column("macd_line", sa.Float(), nullable=True),
            sa.Column("macd_signal", sa.Float(), nullable=True),
            sa.Column("macd_histogram", sa.Float(), nullable=True),
            sa.Column("ema_9", sa.Float(), nullable=True),
            sa.Column("ema_21", sa.Float(), nullable=True),
            sa.Column("sma_20", sa.Float(), nullable=True),
            sa.Column("sma_50", sa.Float(), nullable=True),
            sa.Column("sma_200", sa.Float(), nullable=True),
            sa.Column("trend_signal", sa.String(), nullable=True),
            sa.Column("data_quality", sa.String(), nullable=False, server_default="ok"),
            sa.Column("source", sa.String(), nullable=False, server_default="derived"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("asset_id", "timeframe", "as_of", name="uix_asset_technical_snapshot"),
        )
        op.create_index("ix_asset_technical_snapshots_asset_id", "asset_technical_snapshots", ["asset_id"], unique=False)
        op.create_index("ix_asset_technical_snapshots_timeframe", "asset_technical_snapshots", ["timeframe"], unique=False)
        op.create_index("ix_asset_technical_snapshots_as_of", "asset_technical_snapshots", ["as_of"], unique=False)

    if not _table_exists(inspector, "asset_fundamental_snapshots"):
        op.create_table(
            "asset_fundamental_snapshots",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("asset_id", sa.UUID(), nullable=False),
            sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
            sa.Column("market_cap", sa.Float(), nullable=True),
            sa.Column("pe_ratio", sa.Float(), nullable=True),
            sa.Column("dividend_yield", sa.Float(), nullable=True),
            sa.Column("eps", sa.Float(), nullable=True),
            sa.Column("high_52week", sa.Float(), nullable=True),
            sa.Column("low_52week", sa.Float(), nullable=True),
            sa.Column("beta", sa.Float(), nullable=True),
            sa.Column("sector", sa.String(), nullable=True),
            sa.Column("industry", sa.String(), nullable=True),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("source", sa.String(), nullable=False, server_default="finnhub"),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("asset_id", "as_of", name="uix_asset_fundamental_snapshot"),
        )
        op.create_index("ix_asset_fundamental_snapshots_asset_id", "asset_fundamental_snapshots", ["asset_id"], unique=False)
        op.create_index("ix_asset_fundamental_snapshots_as_of", "asset_fundamental_snapshots", ["as_of"], unique=False)

    if not _table_exists(inspector, "asset_event_snapshots"):
        op.create_table(
            "asset_event_snapshots",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("asset_id", sa.UUID(), nullable=False),
            sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("event_type", sa.String(), nullable=False),
            sa.Column("headline", sa.String(), nullable=True),
            sa.Column("sentiment_score", sa.Float(), nullable=True),
            sa.Column("relevance_score", sa.Float(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("source", sa.String(), nullable=False, server_default="finnhub"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("asset_id", "event_time", "event_type", "headline", name="uix_asset_event_snapshot"),
        )
        op.create_index("ix_asset_event_snapshots_asset_id", "asset_event_snapshots", ["asset_id"], unique=False)
        op.create_index("ix_asset_event_snapshots_event_time", "asset_event_snapshots", ["event_time"], unique=False)
        op.create_index("ix_asset_event_snapshots_event_type", "asset_event_snapshots", ["event_type"], unique=False)

    if not _table_exists(inspector, "asset_coverage_snapshots"):
        op.create_table(
            "asset_coverage_snapshots",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("asset_id", sa.UUID(), nullable=False),
            sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
            sa.Column("asset_type", sa.String(), nullable=False),
            sa.Column("timeframe", sa.String(), nullable=False),
            sa.Column("expected_field_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("available_field_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("coverage_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("freshness_seconds", sa.Integer(), nullable=True),
            sa.Column("anomaly_flags", sa.JSON(), nullable=True),
            sa.Column("source", sa.String(), nullable=False, server_default="snapshot_pipeline"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("asset_id", "as_of", "timeframe", name="uix_asset_coverage_snapshot"),
        )
        op.create_index("ix_asset_coverage_snapshots_asset_id", "asset_coverage_snapshots", ["asset_id"], unique=False)
        op.create_index("ix_asset_coverage_snapshots_as_of", "asset_coverage_snapshots", ["as_of"], unique=False)
        op.create_index("ix_asset_coverage_snapshots_timeframe", "asset_coverage_snapshots", ["timeframe"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _table_exists(inspector, "asset_coverage_snapshots"):
        op.drop_index("ix_asset_coverage_snapshots_timeframe", table_name="asset_coverage_snapshots")
        op.drop_index("ix_asset_coverage_snapshots_as_of", table_name="asset_coverage_snapshots")
        op.drop_index("ix_asset_coverage_snapshots_asset_id", table_name="asset_coverage_snapshots")
        op.drop_table("asset_coverage_snapshots")

    if _table_exists(inspector, "asset_event_snapshots"):
        op.drop_index("ix_asset_event_snapshots_event_type", table_name="asset_event_snapshots")
        op.drop_index("ix_asset_event_snapshots_event_time", table_name="asset_event_snapshots")
        op.drop_index("ix_asset_event_snapshots_asset_id", table_name="asset_event_snapshots")
        op.drop_table("asset_event_snapshots")

    if _table_exists(inspector, "asset_fundamental_snapshots"):
        op.drop_index("ix_asset_fundamental_snapshots_as_of", table_name="asset_fundamental_snapshots")
        op.drop_index("ix_asset_fundamental_snapshots_asset_id", table_name="asset_fundamental_snapshots")
        op.drop_table("asset_fundamental_snapshots")

    if _table_exists(inspector, "asset_technical_snapshots"):
        op.drop_index("ix_asset_technical_snapshots_as_of", table_name="asset_technical_snapshots")
        op.drop_index("ix_asset_technical_snapshots_timeframe", table_name="asset_technical_snapshots")
        op.drop_index("ix_asset_technical_snapshots_asset_id", table_name="asset_technical_snapshots")
        op.drop_table("asset_technical_snapshots")
