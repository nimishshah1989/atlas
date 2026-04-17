"""v6_1_tv_cache_watchlist — V6-1: Create atlas_tv_cache, add tv_synced to atlas_watchlists.

Revision ID: i8j9k0l1m2n3
Revises: h7i8j9k0l1m2
Create Date: 2026-04-17 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op  # type: ignore[attr-defined]
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "i8j9k0l1m2n3"
down_revision: Union[str, None] = "h7i8j9k0l1m2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create atlas_tv_cache table
    # interval defaults to 'none' so composite PK works cleanly
    op.create_table(
        "atlas_tv_cache",
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("exchange", sa.String(20), nullable=False, server_default="NSE"),
        sa.Column(
            "data_type", sa.String(30), nullable=False
        ),  # 'ta_summary', 'fundamentals', 'screener'
        sa.Column(
            "interval", sa.String(10), nullable=False, server_default="none"
        ),  # '1D','1W','1M' or 'none'
        sa.Column("data", JSONB(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("symbol", "data_type", "interval"),
    )
    op.create_index("ix_atlas_tv_cache_symbol", "atlas_tv_cache", ["symbol"])
    op.create_index("ix_atlas_tv_cache_fetched_at", "atlas_tv_cache", ["fetched_at"])

    # Add tv_synced to atlas_watchlists
    op.add_column(
        "atlas_watchlists",
        sa.Column("tv_synced", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("atlas_watchlists", "tv_synced")
    op.drop_index("ix_atlas_tv_cache_fetched_at", table_name="atlas_tv_cache")
    op.drop_index("ix_atlas_tv_cache_symbol", table_name="atlas_tv_cache")
    op.drop_table("atlas_tv_cache")
