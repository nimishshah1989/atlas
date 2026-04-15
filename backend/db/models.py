"""ATLAS database models — SQLAlchemy 2.0 mapped_column syntax."""

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_JEA = text("'[]'::jsonb")  # JSONB empty-array server default


class Base(DeclarativeBase):
    pass


class DecisionTypeEnum(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WATCH = "WATCH"


class DecisionStatusEnum(str, enum.Enum):
    ACTIVE = "active"
    INVALIDATED = "invalidated"
    COMPLETED = "completed"


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


class AtlasAgentScore(Base):
    """Tracks agent prediction accuracy — BIGSERIAL, append-only."""

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
    """Darwinian agent weights — CHECK enforces [0.3, 2.5]."""

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
    """Per-agent corrections and learnings — BIGSERIAL, append-only."""

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


class AtlasAgentMutation(Base):
    """Darwinian mutation lifecycle: shadow → merged | reverted."""

    __tablename__ = "atlas_agent_mutations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    mutation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    shadow_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    shadow_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    original_sharpe: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    mutated_sharpe: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    outcome_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AtlasAlert(Base):
    """System alerts — budget exceeded, anomalies, signals. BIGSERIAL."""

    __tablename__ = "atlas_alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    alert_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, server_default="{}"
    )
    rs_at_alert: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    quadrant_at_alert: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
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


class AtlasCostLedger(Base):
    """LLM API cost tracking — every call recorded. BIGSERIAL."""

    __tablename__ = "atlas_cost_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
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


class AtlasBriefing(Base):
    """LLM-generated morning briefings — one per trading day per scope."""

    __tablename__ = "atlas_briefings"
    __table_args__ = (
        Index(
            "uq_briefings_date_scope",
            "date",
            "scope",
            text("COALESCE(scope_key, '__null__')"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    key_signals: Mapped[Any] = mapped_column(JSONB, nullable=True, server_default=_JEA)
    theses: Mapped[Any] = mapped_column(JSONB, nullable=True, server_default=_JEA)
    patterns: Mapped[Any] = mapped_column(JSONB, nullable=True, server_default=_JEA)
    india_implication: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_scenario: Mapped[str | None] = mapped_column(Text, nullable=True)
    conviction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    staleness_flags: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
