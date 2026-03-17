"""create_watchlist_assets_table

Revision ID: e7c3f2a1b890
Revises: b31f4f4e8d2a
Create Date: 2026-03-17 00:00:00.000000

This migration was missing from the initial setup — watchlist_assets and
portfolios were defined in the ORM models but never added to any migration
script, so they were never created in the production database.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "e7c3f2a1b890"
down_revision: Union[str, None] = "b31f4f4e8d2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # portfolios was in the initial migration that was stamped (not run)
    if not _table_exists(inspector, "portfolios"):
        op.create_table(
            "portfolios",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_portfolios_user_id", "portfolios", ["user_id"], unique=False)

    # watchlist_assets was added to the ORM model but never added to any migration
    if not _table_exists(inspector, "watchlist_assets"):
        op.create_table(
            "watchlist_assets",
            sa.Column("watchlist_id", sa.UUID(), nullable=False),
            sa.Column("asset_id", sa.UUID(), nullable=False),
            sa.Column(
                "added_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.ForeignKeyConstraint(
                ["asset_id"], ["assets.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["watchlist_id"], ["watchlists.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("watchlist_id", "asset_id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _table_exists(inspector, "watchlist_assets"):
        op.drop_table("watchlist_assets")

    if _table_exists(inspector, "portfolios"):
        op.drop_index("ix_portfolios_user_id", table_name="portfolios")
        op.drop_table("portfolios")
