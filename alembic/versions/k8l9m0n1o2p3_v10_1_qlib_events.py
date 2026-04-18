"""v10_1_qlib_events — V10-1: Create atlas_qlib_features, atlas_qlib_signals, atlas_events.

Revision ID: k8l9m0n1o2p3
Revises: j7k8l9m0n1o2
Create Date: 2026-04-18 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op  # type: ignore[attr-defined]
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "k8l9m0n1o2p3"
down_revision: Union[str, None] = "j7k8l9m0n1o2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- atlas_qlib_features ---
    op.create_table(
        "atlas_qlib_features",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("instrument_id", UUID(as_uuid=True), nullable=False),
        sa.Column("features", JSONB(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.UniqueConstraint("date", "instrument_id", name="uq_qlib_features_date_instrument"),
    )
    op.create_index(
        "ix_atlas_qlib_features_instrument_id",
        "atlas_qlib_features",
        ["instrument_id"],
    )

    # --- atlas_qlib_signals ---
    op.create_table(
        "atlas_qlib_signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("instrument_id", UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(50), nullable=False),
        sa.Column("signal_score", sa.Numeric(20, 4), nullable=True),
        sa.Column("signal_rank", sa.Numeric(10, 0), nullable=True),
        sa.Column("features_used", JSONB(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "date",
            "instrument_id",
            "model_name",
            name="uq_qlib_signals_date_instrument_model",
        ),
    )
    op.create_index(
        "ix_atlas_qlib_signals_instrument_id",
        "atlas_qlib_signals",
        ["instrument_id"],
    )

    # --- atlas_events ---
    op.create_table(
        "atlas_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("entity", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(20), nullable=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("data_as_of", sa.Date(), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column("related_event_ids", JSONB(), nullable=True),
        sa.Column("is_delivered", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
    )
    op.create_index(
        "ix_atlas_events_event_type",
        "atlas_events",
        ["event_type"],
    )
    op.create_index(
        "ix_atlas_events_entity_type",
        "atlas_events",
        ["entity_type"],
    )
    op.create_index(
        "ix_atlas_events_data_as_of",
        "atlas_events",
        ["data_as_of"],
    )
    # Composite index for entity_type + entity lookup
    op.create_index(
        "ix_atlas_events_entity_type_entity",
        "atlas_events",
        ["entity_type", "entity"],
    )


def downgrade() -> None:
    op.drop_index("ix_atlas_events_entity_type_entity", table_name="atlas_events")
    op.drop_index("ix_atlas_events_data_as_of", table_name="atlas_events")
    op.drop_index("ix_atlas_events_entity_type", table_name="atlas_events")
    op.drop_index("ix_atlas_events_event_type", table_name="atlas_events")
    op.drop_table("atlas_events")

    op.drop_index("ix_atlas_qlib_signals_instrument_id", table_name="atlas_qlib_signals")
    op.drop_table("atlas_qlib_signals")

    op.drop_index("ix_atlas_qlib_features_instrument_id", table_name="atlas_qlib_features")
    op.drop_table("atlas_qlib_features")
