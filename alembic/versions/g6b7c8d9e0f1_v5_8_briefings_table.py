"""v5_8_briefings_table — V5-8: Create atlas_briefings table with functional unique index.

One row per trading day per scope.
Idempotent upsert on (date, scope, COALESCE(scope_key, '__null__')).

Revision ID: g6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-04-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op  # type: ignore[attr-defined]
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "g6b7c8d9e0f1"
down_revision: Union[str, None] = "b1c2d3e4f5g6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "atlas_briefings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("scope_key", sa.String(50), nullable=True),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("key_signals", JSONB(), nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("theses", JSONB(), nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("patterns", JSONB(), nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("india_implication", sa.Text(), nullable=True),
        sa.Column("risk_scenario", sa.Text(), nullable=True),
        sa.Column("conviction", sa.String(10), nullable=True),
        sa.Column("model_used", sa.String(50), nullable=True),
        sa.Column("staleness_flags", JSONB(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
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

    # Standard index on date for range queries
    op.create_index("ix_atlas_briefings_date", "atlas_briefings", ["date"])

    # Functional unique index: (date, scope, COALESCE(scope_key, '__null__'))
    # This enables ON CONFLICT upsert with nullable scope_key.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_briefings_date_scope
        ON atlas_briefings (date, scope, COALESCE(scope_key, '__null__'))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_briefings_date_scope")
    op.drop_index("ix_atlas_briefings_date", table_name="atlas_briefings")
    op.drop_table("atlas_briefings")
