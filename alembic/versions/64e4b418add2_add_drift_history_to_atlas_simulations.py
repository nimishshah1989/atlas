"""add drift_history to atlas_simulations

Revision ID: 64e4b418add2
Revises: 2d156b12ed5f
Create Date: 2026-04-14 17:49:50.122515

"""

from typing import Sequence, Union

from alembic import op  # type: ignore[attr-defined]
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "64e4b418add2"
down_revision: Union[str, None] = "2d156b12ed5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "atlas_simulations",
        sa.Column("drift_history", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("atlas_simulations", "drift_history")
