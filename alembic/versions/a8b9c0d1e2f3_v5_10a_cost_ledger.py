"""v5_10a_cost_ledger — V5-10a: Create atlas_cost_ledger for LLM API cost tracking.

Revision ID: a8b9c0d1e2f3
Revises: f5a6b7c8d9e0
Create Date: 2026-04-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op  # type: ignore[attr-defined]
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "atlas_cost_ledger",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(20, 4), nullable=False),
        sa.Column("request_type", sa.String(50), nullable=False),
        sa.Column("metadata_json", JSONB(), nullable=True),
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
        "ix_atlas_cost_ledger_agent_id",
        "atlas_cost_ledger",
        ["agent_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_atlas_cost_ledger_agent_id", table_name="atlas_cost_ledger")
    op.drop_table("atlas_cost_ledger")
