"""v5_6_atlas_alerts — V5-6: Create atlas_alerts table for system alerts.

Revision ID: b1c2d3e4f5g6
Revises: a8b9c0d1e2f3
Create Date: 2026-04-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op  # type: ignore[attr-defined]
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "b1c2d3e4f5g6"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "atlas_alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(50), nullable=True),
        sa.Column("instrument_id", UUID(as_uuid=True), nullable=True),
        sa.Column("alert_type", sa.String(50), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("metadata_json", JSONB(), nullable=True, server_default="{}"),
        sa.Column("rs_at_alert", sa.Numeric(20, 4), nullable=True),
        sa.Column("quadrant_at_alert", sa.String(20), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_atlas_alerts_symbol", "atlas_alerts", ["symbol"])
    op.create_index("ix_atlas_alerts_instrument_id", "atlas_alerts", ["instrument_id"])
    op.create_index("ix_atlas_alerts_alert_type", "atlas_alerts", ["alert_type"])
    # Index on created_at for rolling window queries
    op.create_index("ix_atlas_alerts_created_at", "atlas_alerts", ["created_at"])
    # Also add index on atlas_cost_ledger.created_at for rolling window budget queries
    op.create_index("ix_atlas_cost_ledger_created_at", "atlas_cost_ledger", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_atlas_cost_ledger_created_at", table_name="atlas_cost_ledger")
    op.drop_index("ix_atlas_alerts_created_at", table_name="atlas_alerts")
    op.drop_index("ix_atlas_alerts_alert_type", table_name="atlas_alerts")
    op.drop_index("ix_atlas_alerts_instrument_id", table_name="atlas_alerts")
    op.drop_index("ix_atlas_alerts_symbol", table_name="atlas_alerts")
    op.drop_table("atlas_alerts")
