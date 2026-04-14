"""v4_1_atlas_portfolios — V4 Portfolio Management foundation.

Creates four portfolio tables:
  - atlas_portfolios
  - atlas_portfolio_holdings
  - atlas_scheme_mapping_overrides
  - atlas_portfolio_snapshots

Revision ID: a1b2c3d4e5f6
Revises: 64e4b418add2
Create Date: 2026-04-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op  # type: ignore[attr-defined]
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "64e4b418add2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # --- atlas_portfolios ---
    if not _table_exists(conn, "atlas_portfolios"):
        op.create_table(
            "atlas_portfolios",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(200), nullable=True),
            sa.Column("portfolio_type", sa.String(20), nullable=False),
            sa.Column("owner_type", sa.String(20), nullable=False),
            sa.Column("user_id", sa.String(50), nullable=True),
            sa.Column("analysis_cache", postgresql.JSONB(), nullable=True),
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

    _create_index_if_not_exists(
        conn, "ix_atlas_portfolios_user_id", "atlas_portfolios", ["user_id"]
    )

    # --- atlas_portfolio_holdings ---
    if not _table_exists(conn, "atlas_portfolio_holdings"):
        op.create_table(
            "atlas_portfolio_holdings",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("mstar_id", sa.String(50), nullable=True),
            sa.Column("scheme_name", sa.Text(), nullable=False),
            sa.Column("folio_number", sa.String(50), nullable=True),
            sa.Column("units", sa.Numeric(20, 4), nullable=False),
            sa.Column("nav", sa.Numeric(20, 4), nullable=True),
            sa.Column("current_value", sa.Numeric(20, 4), nullable=True),
            sa.Column("cost_value", sa.Numeric(20, 4), nullable=True),
            sa.Column("mapping_confidence", sa.Numeric(5, 4), nullable=True),
            sa.Column("mapping_status", sa.String(20), nullable=False, server_default="pending"),
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

    _create_index_if_not_exists(
        conn,
        "ix_atlas_portfolio_holdings_portfolio_id",
        "atlas_portfolio_holdings",
        ["portfolio_id"],
    )
    _create_index_if_not_exists(
        conn, "ix_atlas_portfolio_holdings_mstar_id", "atlas_portfolio_holdings", ["mstar_id"]
    )

    # --- atlas_scheme_mapping_overrides ---
    if not _table_exists(conn, "atlas_scheme_mapping_overrides"):
        op.create_table(
            "atlas_scheme_mapping_overrides",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("scheme_name_pattern", sa.Text(), nullable=False),
            sa.Column("mstar_id", sa.String(50), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(50), nullable=True),
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

    _create_unique_index_if_not_exists(
        conn,
        "uq_scheme_mapping_override_pattern",
        "atlas_scheme_mapping_overrides",
        ["scheme_name_pattern"],
    )
    _create_index_if_not_exists(
        conn,
        "ix_atlas_scheme_mapping_overrides_mstar_id",
        "atlas_scheme_mapping_overrides",
        ["mstar_id"],
    )

    # --- atlas_portfolio_snapshots ---
    if not _table_exists(conn, "atlas_portfolio_snapshots"):
        op.create_table(
            "atlas_portfolio_snapshots",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("total_value", sa.Numeric(20, 4), nullable=False),
            sa.Column("total_cost", sa.Numeric(20, 4), nullable=True),
            sa.Column("holdings_count", sa.Integer(), nullable=False),
            sa.Column("sector_weights", postgresql.JSONB(), nullable=True),
            sa.Column("quadrant_distribution", postgresql.JSONB(), nullable=True),
            sa.Column("weighted_rs", sa.Numeric(20, 4), nullable=True),
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

    _create_index_if_not_exists(
        conn,
        "ix_atlas_portfolio_snapshots_portfolio_id",
        "atlas_portfolio_snapshots",
        ["portfolio_id"],
    )
    # Unique partial index: one non-deleted snapshot per portfolio per date
    _create_partial_unique_index_if_not_exists(
        conn,
        "uq_portfolio_snapshot_date",
        "atlas_portfolio_snapshots",
        ["portfolio_id", "snapshot_date"],
        where="is_deleted = false",
    )


def downgrade() -> None:
    op.drop_table("atlas_portfolio_snapshots")
    op.drop_table("atlas_scheme_mapping_overrides")
    op.drop_table("atlas_portfolio_holdings")
    op.drop_table("atlas_portfolios")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _table_exists(conn: sa.engine.Connection, table_name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (  SELECT FROM information_schema.tables  WHERE table_name = :name)"
        ),
        {"name": table_name},
    )
    return bool(result.scalar())


def _create_index_if_not_exists(
    conn: sa.engine.Connection,
    index_name: str,
    table_name: str,
    columns: list[str],
) -> None:
    exists = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = :name)"),
        {"name": index_name},
    ).scalar()
    if not exists:
        cols = ", ".join(columns)
        conn.execute(sa.text(f"CREATE INDEX {index_name} ON {table_name} ({cols})"))


def _create_unique_index_if_not_exists(
    conn: sa.engine.Connection,
    index_name: str,
    table_name: str,
    columns: list[str],
) -> None:
    exists = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = :name)"),
        {"name": index_name},
    ).scalar()
    if not exists:
        cols = ", ".join(columns)
        conn.execute(sa.text(f"CREATE UNIQUE INDEX {index_name} ON {table_name} ({cols})"))


def _create_partial_unique_index_if_not_exists(
    conn: sa.engine.Connection,
    index_name: str,
    table_name: str,
    columns: list[str],
    where: str,
) -> None:
    exists = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = :name)"),
        {"name": index_name},
    ).scalar()
    if not exists:
        cols = ", ".join(columns)
        conn.execute(
            sa.text(f"CREATE UNIQUE INDEX {index_name} ON {table_name} ({cols}) WHERE {where}")
        )
