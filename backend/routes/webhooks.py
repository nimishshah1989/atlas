"""Webhook routes — inbound push endpoints.

POST /api/webhooks/tradingview
    Receives TradingView alert payloads via webhook push.
    Validates X-TV-Signature header, upserts to atlas_tv_cache.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.session import get_db
from backend.services.tv.cache_service import TVCacheService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


class TVWebhookPayload(BaseModel):
    """Inbound TradingView alert webhook payload."""

    symbol: str = Field(..., min_length=1, description="Ticker symbol, e.g. RELIANCE")
    exchange: str = Field(default="NSE", description="Exchange code")
    data_type: str = Field(..., description="One of: ta_summary | screener | fundamentals")
    interval: str = Field(default="none", description="Chart interval or 'none'")
    tv_payload: dict[str, Any] = Field(..., description="The raw TradingView data blob")


class TVWebhookResponse(BaseModel):
    """Response envelope for a successful webhook upsert."""

    status: str
    symbol: str
    data_type: str
    data_as_of: str


@router.post("/tradingview")
async def receive_tradingview_webhook(
    payload: TVWebhookPayload,
    x_tv_signature: str | None = Header(default=None, alias="X-TV-Signature"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Receive and cache a TradingView alert payload.

    Validates the X-TV-Signature header against settings.tv_webhook_secret.
    Upserts the payload into atlas_tv_cache.

    Returns a standard §20.4 envelope:
    ```json
    {"data": {...}, "_meta": {"data_as_of": "..."}}
    ```

    Raises:
        HTTPException 403: If X-TV-Signature is missing or does not match the
            configured secret.
        HTTPException 422: If the request body is malformed (Pydantic auto-raises).
    """
    settings = get_settings()

    if x_tv_signature is None or x_tv_signature != settings.tv_webhook_secret:
        log.warning(
            "tv_webhook_signature_invalid",
            symbol=payload.symbol if x_tv_signature else "<unparsed>",
            has_header=x_tv_signature is not None,
        )
        raise HTTPException(status_code=403, detail="Invalid or missing X-TV-Signature")

    cache_svc = TVCacheService()
    entry = await cache_svc.upsert(
        session=session,
        symbol=payload.symbol,
        exchange=payload.exchange,
        data_type=payload.data_type,
        interval=payload.interval,
        tv_data=payload.tv_payload,
    )

    log.info(
        "tv_webhook_received",
        symbol=payload.symbol,
        exchange=payload.exchange,
        data_type=payload.data_type,
        interval=payload.interval,
    )

    now_iso = datetime.now(tz=UTC).isoformat()
    return {
        "data": {
            "status": "ok",
            "symbol": entry.symbol,
            "data_type": entry.data_type,
            "data_as_of": entry.fetched_at.isoformat(),
        },
        "_meta": {
            "data_as_of": now_iso,
        },
    }
