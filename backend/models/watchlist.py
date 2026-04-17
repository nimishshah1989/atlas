"""Pydantic v2 models for watchlist CRUD + TV sync API (V6-6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WatchlistCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    symbols: list[str] = Field(default_factory=list)


class WatchlistUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    symbols: Optional[list[str]] = None


class WatchlistResponse(BaseModel):
    id: uuid.UUID
    name: str
    symbols: list[str]
    tv_synced: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WatchlistListResponse(BaseModel):
    watchlists: list[WatchlistResponse]
    total: int


class SyncTvResponse(BaseModel):
    id: uuid.UUID
    tv_synced: bool
    message: str
