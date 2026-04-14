"""ATLAS-owned database models — SQLAlchemy 2.0 mapped_column syntax.

Schema matches alembic revision c118008a7781 (V1-1 parity with spec §6).
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# --- Enums ---


class DecisionTypeEnum(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WATCH = "WATCH"


class DecisionStatusEnum(str, enum.Enum):
    ACTIVE = "active"
    INVALIDATED = "invalidated"
    COMPLETED = "completed"


# --- ATLAS Decisions ---


class AtlasDecision(Base):
    __tablename__ = "atlas_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="equity")
    decision_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="HOLD")
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, server_default="0")
    source_agent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    horizon: Mapped[str] = mapped_column(String(20), nullable=False, server_default="3m")
    horizon_end_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    invalidation_conditions: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    user_action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    user_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_as_of: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# --- ATLAS Intelligence (pgvector) ---


class AtlasIntelligence(Base):
    __tablename__ = "atlas_intelligence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    entity: Mapped[str | None] = mapped_column(Text, nullable=True)
    finding_type: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column("evidence", JSONB, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    data_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    validation_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (Index("ix_atlas_intel_entity_type", "entity_type"),)


# --- ATLAS Simulations (V3) ---


class AtlasSimulation(Base):
    __tablename__ = "atlas_simulations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    daily_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    transactions: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    tax_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    tear_sheet_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_auto_loop: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    auto_loop_cron: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_auto_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_atlas_sim_autoloop_active",
            "user_id",
            "is_auto_loop",
            postgresql_where=("is_auto_loop = true AND is_deleted = false"),
        ),
    )


# --- ATLAS Watchlists ---


class AtlasWatchlist(Base):
    __tablename__ = "atlas_watchlists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
