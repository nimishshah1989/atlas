"""ORM models for V10-1: atlas_qlib_features, atlas_qlib_signals, atlas_events."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base


class AtlasQlibFeatures(Base):
    """Per-instrument daily Qlib feature vectors — V10-1.

    Spec DDL has composite PK (date, instrument_id). Project convention requires
    a UUID id as primary key; the spec semantics are enforced via UNIQUE constraint.
    """

    __tablename__ = "atlas_qlib_features"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    instrument_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
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
        UniqueConstraint("date", "instrument_id", name="uq_qlib_features_date_instrument"),
    )


class AtlasQlibSignals(Base):
    """Per-instrument per-model Qlib signal scores — V10-1.

    Spec DDL has composite PK (date, instrument_id, model_name). Enforced via UNIQUE.
    signal_score uses Numeric(20, 4) per project convention for numeric columns.
    """

    __tablename__ = "atlas_qlib_signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    instrument_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    signal_score: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    signal_rank: Mapped[int | None] = mapped_column(Numeric(10, 0), nullable=True)
    features_used: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
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
        UniqueConstraint(
            "date", "instrument_id", "model_name", name="uq_qlib_signals_date_instrument_model"
        ),
    )


class AtlasEvents(Base):
    """V10 event bus table for WebSocket push events — V10-1.

    Stores QUADRANT_CHANGE, RS_CROSS_ZERO and similar derived signal events.
    is_delivered tracks WebSocket delivery lifecycle.
    """

    __tablename__ = "atlas_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, server_default="medium")
    data_as_of: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_event_ids: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    is_delivered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
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
