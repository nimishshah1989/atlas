"""AtlasGoldRSCache ORM model — V7-0 Gold RS foundation."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base


class AtlasGoldRSCache(Base):
    """Gold RS (Relative Strength vs Gold) cache — V7-0."""

    __tablename__ = "atlas_gold_rs_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    rs_vs_gold_1m: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    rs_vs_gold_3m: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    rs_vs_gold_6m: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    rs_vs_gold_12m: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    gold_rs_signal: Mapped[str] = mapped_column(String(20), nullable=False)
    gold_series: Mapped[str] = mapped_column(String(16), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "date", name="uq_gold_rs_cache"),
    )
