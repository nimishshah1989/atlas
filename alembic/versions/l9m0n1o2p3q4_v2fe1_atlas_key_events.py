"""v2fe1_atlas_key_events — V2FE-1: Create atlas_key_events table + seed from fixture.

Revision ID: l9m0n1o2p3q4
Revises: k8l9m0n1o2p3
Create Date: 2026-04-19 00:00:00.000000
"""

import json
import pathlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op  # type: ignore[attr-defined]
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "l9m0n1o2p3q4"
down_revision: Union[str, None] = "k8l9m0n1o2p3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "atlas_key_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column(
            "affects",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("source", sa.String(200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_color", sa.String(10), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
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
        sa.UniqueConstraint("date", "label", name="uq_key_events_date_label"),
    )
    op.create_index("ix_atlas_key_events_date", "atlas_key_events", ["date"])
    op.create_index("ix_atlas_key_events_category", "atlas_key_events", ["category"])

    # Seed from events.json fixture
    events_file = (
        pathlib.Path(__file__).parent.parent.parent
        / "frontend"
        / "mockups"
        / "fixtures"
        / "events.json"
    )
    if events_file.exists():
        data = json.loads(events_file.read_text())
        events = data.get("events", [])
        if events:
            conn = op.get_bind()
            for event in events:
                affects_val = json.dumps(event.get("affects", []))
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO atlas_key_events
                            (date, category, severity, affects, label, source, description,
                             display_color, source_url)
                        VALUES
                            (:date, :category, :severity, CAST(:affects AS jsonb), :label,
                             :source, :description, :display_color, :source_url)
                        ON CONFLICT (date, label) DO NOTHING
                        """
                    ),
                    {
                        "date": event.get("date"),
                        "category": event.get("category", ""),
                        "severity": event.get("severity", "medium"),
                        "affects": affects_val,
                        "label": event.get("label", ""),
                        "source": event.get("source"),
                        "description": event.get("description"),
                        "display_color": event.get("display_color"),
                        "source_url": event.get("source_url"),
                    },
                )


def downgrade() -> None:
    op.drop_index("ix_atlas_key_events_category", table_name="atlas_key_events")
    op.drop_index("ix_atlas_key_events_date", table_name="atlas_key_events")
    op.drop_table("atlas_key_events")
