"""ORM model for atlas_tv_cache — TradingView data cache."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base


class AtlasTvCache(Base):
    """TradingView cache — 15-min TTL. PK: (symbol, data_type, interval)."""

    __tablename__ = "atlas_tv_cache"

    symbol: Mapped[str] = mapped_column(String(50), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False, server_default="NSE")
    data_type: Mapped[str] = mapped_column(String(30), primary_key=True)
    interval: Mapped[str] = mapped_column(String(10), primary_key=True, server_default="none")
    tv_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
