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
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import Integer
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
    drift_history: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
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


# --- ATLAS Portfolio (V4) ---


class AtlasPortfolio(Base):
    __tablename__ = "atlas_portfolios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    portfolio_type: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    analysis_cache: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
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


class AtlasPortfolioHolding(Base):
    __tablename__ = "atlas_portfolio_holdings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    mstar_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    scheme_name: Mapped[str] = mapped_column(Text, nullable=False)
    folio_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    units: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    cost_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    mapping_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    mapping_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
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


class AtlasSchemeMappingOverride(Base):
    __tablename__ = "atlas_scheme_mapping_overrides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scheme_name_pattern: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    mstar_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
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


class AtlasPortfolioSnapshot(Base):
    __tablename__ = "atlas_portfolio_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    holdings_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sector_weights: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    quadrant_distribution: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    weighted_rs: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
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
            "uq_portfolio_snapshot_date",
            "portfolio_id",
            "snapshot_date",
            unique=True,
            postgresql_where="is_deleted = false",
        ),
    )


# --- ATLAS Agent Tables (V5) ---


class AtlasAgentScore(Base):
    """Tracks agent prediction accuracy over time.

    id is BIGSERIAL (not UUID) — high-write append table per spec DDL.
    """

    __tablename__ = "atlas_agent_scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    prediction_date: Mapped[date] = mapped_column(Date, nullable=False)
    entity: Mapped[str | None] = mapped_column(Text, nullable=True)
    prediction: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    accuracy_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
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


class AtlasAgentWeight(Base):
    """Darwinian agent weights — controls agent influence in synthesis.

    CHECK constraint enforces weight in [0.3, 2.5] per spec §V5.
    agent_id is the natural primary key (VARCHAR(100)).
    """

    __tablename__ = "atlas_agent_weights"

    agent_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, server_default="1.0")
    rolling_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    mutation_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_mutation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
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
        CheckConstraint("weight >= 0.3 AND weight <= 2.5", name="ck_agent_weight_range"),
    )


class AtlasAgentMemory(Base):
    """Per-agent corrections and learnings persisted across runs.

    id is BIGSERIAL (not UUID) — append-only learning log per spec DDL.
    """

    __tablename__ = "atlas_agent_memory"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
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
