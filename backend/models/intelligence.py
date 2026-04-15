"""Pydantic v2 request/response schemas for Intelligence API (§6)."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, model_serializer

from backend.models.schemas import ResponseMeta


# --- Request ---


class FindingCreate(BaseModel):
    """Request body for storing a finding."""

    agent_id: str
    agent_type: str
    entity: str
    entity_type: str = "equity"
    finding_type: str
    title: str
    content: str
    confidence: Decimal = Decimal("0.5")
    evidence: Optional[dict[str, Any]] = None
    tags: Optional[list[str]] = None
    data_as_of: datetime
    expires_hours: int = 168


# --- Response ---


class FindingSummary(BaseModel):
    """Response model for a single intelligence finding."""

    id: UUID
    agent_id: str
    agent_type: str
    entity: Optional[str] = None
    entity_type: Optional[str] = None
    finding_type: str
    title: str
    content: str
    confidence: Optional[Decimal] = None
    evidence: Optional[dict[str, Any]] = None
    tags: Optional[list[str]] = None
    data_as_of: datetime
    expires_at: Optional[datetime] = None
    is_validated: bool = False
    created_at: datetime
    updated_at: datetime


class IntelligenceSearchResponse(BaseModel):
    """Response for vector similarity search.

    Serializes both ``data`` (§20.4 standard envelope key — what
    ``check-api-standard.py`` probes) and ``findings`` (V1 compat key)
    pointing at the same list.  ``_meta`` mirrors ``meta`` so
    ``expect_json_path: '_meta'`` passes the standard gate.
    """

    findings: list[FindingSummary]
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _serialize_with_envelope(self, handler):  # type: ignore[no-untyped-def]
        serialized = handler(self)
        if "findings" in serialized:
            serialized["data"] = serialized["findings"]
        if "meta" in serialized:
            serialized["_meta"] = serialized["meta"]
        return serialized


class IntelligenceListResponse(BaseModel):
    """List response for findings.

    Serializes both ``data`` (§20.4 standard envelope key) and
    ``findings`` (V1 compat key).  ``_meta`` mirrors ``meta``.
    """

    findings: list[FindingSummary]
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _serialize_with_envelope(self, handler):  # type: ignore[no-untyped-def]
        serialized = handler(self)
        if "findings" in serialized:
            serialized["data"] = serialized["findings"]
        if "meta" in serialized:
            serialized["_meta"] = serialized["meta"]
        return serialized


class FindingSummaryEnvelope(BaseModel):
    """Single-finding response envelope (§20.4).

    Wraps a ``FindingSummary`` in the standard ``{data, _meta}`` shape
    required by the API standard checker.
    """

    finding: FindingSummary
    meta: ResponseMeta

    @model_serializer(mode="wrap")
    def _serialize_with_envelope(self, handler):  # type: ignore[no-untyped-def]
        serialized = handler(self)
        if "finding" in serialized:
            serialized["data"] = serialized.pop("finding")
        if "meta" in serialized:
            serialized["_meta"] = serialized["meta"]
        return serialized
