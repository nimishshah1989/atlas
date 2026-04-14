"""v3_1_atlas_simulations — V3 Simulation Engine foundation.

Creates atlas_simulations table with partial index for auto-loop queries.
The table stores simulation configs, results, and auto-loop state.

Revision ID: 2d156b12ed5f
Revises: d4e5f6a7b8c9
Create Date: 2026-04-14 15:16:58.925151
"""

from typing import Sequence, Union

from alembic import op  # type: ignore[attr-defined]
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "2d156b12ed5f"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create atlas_simulations if it does not already exist.
    # The table may exist from a prior worktree run; this is idempotent.
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT FROM information_schema.tables"
            "  WHERE table_name = 'atlas_simulations'"
            ")"
        )
    )
    table_exists = result.scalar()

    if not table_exists:
        op.create_table(
            "atlas_simulations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(200), nullable=True),
            sa.Column("config", postgresql.JSONB(), nullable=False),
            sa.Column("result_summary", postgresql.JSONB(), nullable=True),
            sa.Column("daily_values", postgresql.JSONB(), nullable=True),
            sa.Column("transactions", postgresql.JSONB(), nullable=True),
            sa.Column("tax_summary", postgresql.JSONB(), nullable=True),
            sa.Column("tear_sheet_html", sa.Text(), nullable=True),
            sa.Column(
                "is_auto_loop",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
            sa.Column("auto_loop_cron", sa.String(50), nullable=True),
            sa.Column(
                "last_auto_run",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.Column("user_id", sa.String(50), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    # Ensure user_id index
    _create_index_if_not_exists(
        conn,
        "ix_atlas_simulations_user_id",
        "atlas_simulations",
        ["user_id"],
    )

    # Ensure partial index for active auto-loop queries
    _create_index_if_not_exists(
        conn,
        "ix_atlas_sim_autoloop_active",
        "atlas_simulations",
        ["user_id", "is_auto_loop"],
        where="is_auto_loop = true AND is_deleted = false",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_atlas_sim_autoloop_active",
        table_name="atlas_simulations",
    )
    op.drop_index(
        "ix_atlas_simulations_user_id",
        table_name="atlas_simulations",
    )
    op.drop_table("atlas_simulations")


def _create_index_if_not_exists(
    conn: sa.engine.Connection,
    index_name: str,
    table_name: str,
    columns: list[str],
    where: str | None = None,
) -> None:
    """Create an index only if it doesn't already exist."""
    exists = conn.execute(
        sa.text("SELECT EXISTS (  SELECT 1 FROM pg_indexes  WHERE indexname = :name)"),
        {"name": index_name},
    ).scalar()
    if not exists:
        cols = ", ".join(columns)
        sql = f"CREATE INDEX {index_name} ON {table_name} ({cols})"
        if where:
            sql += f" WHERE {where}"
        conn.execute(sa.text(sql))
