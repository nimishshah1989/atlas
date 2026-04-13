"""v1_1b_decisions_parity — atlas_decisions schema parity with spec §6.

Revision ID: c118008a7781
Revises: b322c43bceff
Create Date: 2026-04-13

Renames, drops, type changes, and new columns on atlas_decisions.
Table is empty at migration time; no data migration needed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op  # type: ignore[attr-defined]
from sqlalchemy.dialects import postgresql

revision: str = "c118008a7781"
down_revision: Union[str, None] = "b322c43bceff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old indexes before structural changes
    op.drop_index(
        "ix_atlas_decisions_symbol",
        table_name="atlas_decisions",
        if_exists=True,
    )

    # Drop columns we're removing outright
    op.drop_column("atlas_decisions", "instrument_id")
    op.drop_column("atlas_decisions", "signal")
    op.drop_column("atlas_decisions", "horizon_days")
    op.drop_column("atlas_decisions", "quadrant")
    op.drop_column("atlas_decisions", "previous_quadrant")

    # Rename: symbol -> entity (VARCHAR(30) -> TEXT)
    op.alter_column(
        "atlas_decisions",
        "symbol",
        new_column_name="entity",
        existing_type=sa.VARCHAR(30),
        type_=sa.Text(),
        existing_nullable=False,
    )

    # Rename: reason -> rationale (stays NOT NULL)
    op.alter_column(
        "atlas_decisions",
        "reason",
        new_column_name="rationale",
        existing_type=sa.Text(),
        existing_nullable=False,
    )

    # Rename: pillar_data -> supporting_data, then make NOT NULL DEFAULT '{}'
    op.alter_column(
        "atlas_decisions",
        "pillar_data",
        new_column_name="supporting_data",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
    )
    op.execute(
        "UPDATE atlas_decisions SET supporting_data = '{}'::jsonb"
        " WHERE supporting_data IS NULL"
    )
    op.alter_column(
        "atlas_decisions",
        "supporting_data",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    # Alter: confidence NUMERIC(5,2) -> NUMERIC(5,4), NOT NULL DEFAULT 0
    op.execute("UPDATE atlas_decisions SET confidence = 0 WHERE confidence IS NULL")
    op.alter_column(
        "atlas_decisions",
        "confidence",
        existing_type=sa.Numeric(5, 2),
        type_=sa.Numeric(5, 4),
        nullable=False,
        server_default=sa.text("0"),
    )

    # Rename: action -> user_action, action_at -> user_action_at,
    #         action_note -> user_notes
    op.alter_column(
        "atlas_decisions",
        "action",
        new_column_name="user_action",
        existing_type=sa.VARCHAR(20),
        existing_nullable=True,
    )
    op.alter_column(
        "atlas_decisions",
        "action_at",
        new_column_name="user_action_at",
        existing_type=sa.TIMESTAMP(timezone=True),
        existing_nullable=True,
    )
    op.alter_column(
        "atlas_decisions",
        "action_note",
        new_column_name="user_notes",
        existing_type=sa.Text(),
        existing_nullable=True,
    )

    # Add new columns
    op.add_column(
        "atlas_decisions",
        sa.Column(
            "decision_type",
            sa.VARCHAR(30),
            nullable=False,
            server_default="HOLD",
        ),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column(
            "entity_type",
            sa.VARCHAR(20),
            nullable=False,
            server_default="equity",
        ),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column("source_agent", sa.VARCHAR(100), nullable=True),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column(
            "horizon",
            sa.VARCHAR(20),
            nullable=False,
            server_default="3m",
        ),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column(
            "horizon_end_date",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column(
            "invalidation_conditions",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column(
            "status",
            sa.VARCHAR(20),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column(
            "invalidated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column("invalidation_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column(
            "outcome",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column(
            "data_as_of",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
    )

    # Create spec indexes
    op.create_index("idx_decisions_entity", "atlas_decisions", ["entity"])
    op.create_index("idx_decisions_status", "atlas_decisions", ["status"])
    op.create_index("idx_decisions_horizon", "atlas_decisions", ["horizon"])
    op.create_index("idx_decisions_agent", "atlas_decisions", ["source_agent"])


def downgrade() -> None:
    # Drop new indexes
    op.drop_index("idx_decisions_agent", table_name="atlas_decisions", if_exists=True)
    op.drop_index("idx_decisions_horizon", table_name="atlas_decisions", if_exists=True)
    op.drop_index("idx_decisions_status", table_name="atlas_decisions", if_exists=True)
    op.drop_index("idx_decisions_entity", table_name="atlas_decisions", if_exists=True)

    # Drop new columns
    op.drop_column("atlas_decisions", "data_as_of")
    op.drop_column("atlas_decisions", "outcome")
    op.drop_column("atlas_decisions", "invalidation_reason")
    op.drop_column("atlas_decisions", "invalidated_at")
    op.drop_column("atlas_decisions", "status")
    op.drop_column("atlas_decisions", "invalidation_conditions")
    op.drop_column("atlas_decisions", "horizon_end_date")
    op.drop_column("atlas_decisions", "horizon")
    op.drop_column("atlas_decisions", "source_agent")
    op.drop_column("atlas_decisions", "entity_type")
    op.drop_column("atlas_decisions", "decision_type")

    # Revert user_* renames
    op.alter_column(
        "atlas_decisions",
        "user_notes",
        new_column_name="action_note",
        existing_type=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "atlas_decisions",
        "user_action_at",
        new_column_name="action_at",
        existing_type=sa.TIMESTAMP(timezone=True),
        existing_nullable=True,
    )
    op.alter_column(
        "atlas_decisions",
        "user_action",
        new_column_name="action",
        existing_type=sa.VARCHAR(20),
        existing_nullable=True,
    )

    # Revert confidence type (drop the NOT NULL / default first)
    op.alter_column(
        "atlas_decisions",
        "confidence",
        existing_type=sa.Numeric(5, 4),
        type_=sa.Numeric(5, 2),
        nullable=True,
        server_default=sa.text("0"),
    )

    # Revert supporting_data -> pillar_data (drop NOT NULL first)
    op.alter_column(
        "atlas_decisions",
        "supporting_data",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
        server_default=sa.text("'{}'::jsonb"),
    )
    op.alter_column(
        "atlas_decisions",
        "supporting_data",
        new_column_name="pillar_data",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
    )

    # Revert rationale -> reason
    op.alter_column(
        "atlas_decisions",
        "rationale",
        new_column_name="reason",
        existing_type=sa.Text(),
        existing_nullable=False,
    )

    # Revert entity -> symbol
    op.alter_column(
        "atlas_decisions",
        "entity",
        new_column_name="symbol",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(30),
        existing_nullable=False,
    )

    # Restore dropped columns
    op.add_column(
        "atlas_decisions",
        sa.Column("previous_quadrant", sa.VARCHAR(20), nullable=True),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column("quadrant", sa.VARCHAR(20), nullable=True),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column("horizon_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column("signal", sa.VARCHAR(30), nullable=True),
    )
    op.add_column(
        "atlas_decisions",
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Restore old index
    op.create_index(
        "ix_atlas_decisions_symbol",
        "atlas_decisions",
        ["symbol"],
        unique=False,
    )
