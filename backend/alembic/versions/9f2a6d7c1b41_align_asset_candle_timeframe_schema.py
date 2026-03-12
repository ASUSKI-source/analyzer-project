"""align_asset_candle_timeframe_schema

Revision ID: 9f2a6d7c1b41
Revises: 47579633dcbb
Create Date: 2026-03-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "9f2a6d7c1b41"
down_revision: Union[str, None] = "47579633dcbb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("asset_candles")}

    if "timeframe" not in columns:
        op.add_column(
            "asset_candles",
            sa.Column("timeframe", sa.String(), nullable=False, server_default="1d"),
        )
        op.alter_column("asset_candles", "timeframe", server_default=None)

    unique_constraints = {uc["name"] for uc in inspector.get_unique_constraints("asset_candles")}
    if "uix_asset_timestamp" in unique_constraints:
        op.drop_constraint("uix_asset_timestamp", "asset_candles", type_="unique")

    # Ensure expected unique shape matches the SQLAlchemy model.
    # Using try/except here keeps upgrade idempotent across partially-migrated dev DBs.
    try:
        op.create_unique_constraint(
            "uix_asset_timestamp_tf",
            "asset_candles",
            ["asset_id", "timestamp", "timeframe"],
        )
    except Exception:
        pass

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("asset_candles")}
    if "ix_asset_candles_timeframe" not in existing_indexes:
        op.create_index("ix_asset_candles_timeframe", "asset_candles", ["timeframe"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    unique_constraints = {uc["name"] for uc in inspector.get_unique_constraints("asset_candles")}
    if "uix_asset_timestamp_tf" in unique_constraints:
        op.drop_constraint("uix_asset_timestamp_tf", "asset_candles", type_="unique")
    if "uix_asset_timestamp" not in unique_constraints:
        op.create_unique_constraint("uix_asset_timestamp", "asset_candles", ["asset_id", "timestamp"])

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("asset_candles")}
    if "ix_asset_candles_timeframe" in existing_indexes:
        op.drop_index("ix_asset_candles_timeframe", table_name="asset_candles")

    columns = {col["name"] for col in inspector.get_columns("asset_candles")}
    if "timeframe" in columns:
        op.drop_column("asset_candles", "timeframe")
