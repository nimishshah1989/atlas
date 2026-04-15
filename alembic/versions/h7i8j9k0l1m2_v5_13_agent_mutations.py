"""v5_13_agent_mutations — V5-13: Create atlas_agent_mutations table.

Tracks Darwinian evolution mutation lifecycle: shadow testing, merge, and
revert decisions. One row per mutation attempt per agent.

Revision ID: h7i8j9k0l1m2
Revises: g6b7c8d9e0f1
Create Date: 2026-04-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op  # type: ignore[attr-defined]

revision: str = "h7i8j9k0l1m2"
down_revision: Union[str, None] = "g6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "atlas_agent_mutations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("mutation_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("shadow_start_date", sa.Date(), nullable=True),
        sa.Column("shadow_end_date", sa.Date(), nullable=True),
        sa.Column("original_sharpe", sa.Numeric(10, 4), nullable=True),
        sa.Column("mutated_sharpe", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=True),
        sa.Column("outcome_reason", sa.Text(), nullable=True),
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
    op.create_index(
        "ix_atlas_agent_mutations_agent_id",
        "atlas_agent_mutations",
        ["agent_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_atlas_agent_mutations_agent_id", table_name="atlas_agent_mutations")
    op.drop_table("atlas_agent_mutations")
