"""v7_0_atlas_gold_rs_cache — V7-0: Create atlas_gold_rs_cache table.

Revision ID: j7k8l9m0n1o2
Revises: i8j9k0l1m2n3
Create Date: 2026-04-17 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op  # type: ignore[attr-defined]

revision: str = "j7k8l9m0n1o2"
down_revision: Union[str, None] = "i8j9k0l1m2n3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "atlas_gold_rs_cache",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("rs_vs_gold_1m", sa.Numeric(8, 4), nullable=True),
        sa.Column("rs_vs_gold_3m", sa.Numeric(8, 4), nullable=True),
        sa.Column("rs_vs_gold_6m", sa.Numeric(8, 4), nullable=True),
        sa.Column("rs_vs_gold_12m", sa.Numeric(8, 4), nullable=True),
        sa.Column("gold_rs_signal", sa.String(20), nullable=False),
        sa.Column("gold_series", sa.String(16), nullable=False),
        sa.Column(
            "computed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("entity_type", "entity_id", "date", name="uq_gold_rs_cache"),
    )
    op.create_index("ix_gold_rs_entity", "atlas_gold_rs_cache", ["entity_type", "entity_id"])
    op.create_index("ix_gold_rs_date", "atlas_gold_rs_cache", ["date"])
    op.create_index("ix_gold_rs_signal", "atlas_gold_rs_cache", ["gold_rs_signal"])


def downgrade() -> None:
    op.drop_index("ix_gold_rs_signal", table_name="atlas_gold_rs_cache")
    op.drop_index("ix_gold_rs_date", table_name="atlas_gold_rs_cache")
    op.drop_index("ix_gold_rs_entity", table_name="atlas_gold_rs_cache")
    op.drop_table("atlas_gold_rs_cache")
