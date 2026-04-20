"""Thin LLM client for ATLAS persona agents.

Uses httpx to call Anthropic Messages API directly — no anthropic SDK dependency.
Every call is recorded in the cost ledger before returning.

Usage:
    text = await complete(
        db=db,
        agent_id="persona-jhunjhunwala",
        system_prompt="You are a value+momentum investor...",
        user_message="Analyse these stocks: ...",
    )
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.cost_ledger import record_llm_call

log = structlog.get_logger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TIMEOUT_SECONDS = 60.0


async def complete(
    db: AsyncSession,
    agent_id: str,
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    request_type: str = "persona_analysis",
    metadata: dict[str, Any] | None = None,
) -> str:
    """Call Anthropic Claude API and record the cost in the ledger.

    Args:
        db: Async SQLAlchemy session (for cost ledger write).
        agent_id: The calling agent's ID.
        system_prompt: System prompt for the LLM.
        user_message: User-turn message content.
        model: Anthropic model ID.
        max_tokens: Maximum completion tokens.
        request_type: Category label for cost ledger.
        metadata: Optional extra context for cost ledger.

    Returns:
        The text content of the first response block.

    Raises:
        RuntimeError: If ANTHROPIC_API_KEY is not set.
        httpx.HTTPStatusError: If the API returns a non-2xx response.
        httpx.TimeoutException: If the request times out.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Set it before running LLM persona agents."
        )

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "content-type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }

    log.info(
        "llm_call_start",
        agent_id=agent_id,
        model=model,
        request_type=request_type,
        user_message_len=len(user_message),
    )

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        resp = await client.post(ANTHROPIC_API_URL, json=payload, headers=headers)
        resp.raise_for_status()

    body_json = resp.json()
    content_blocks: list[dict[str, Any]] = body_json.get("content", [])
    text = content_blocks[0].get("text", "") if content_blocks else ""

    usage: dict[str, Any] = body_json.get("usage", {})
    prompt_tokens: int = int(usage.get("input_tokens", 0))
    completion_tokens: int = int(usage.get("output_tokens", 0))

    await record_llm_call(
        db=db,
        agent_id=agent_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        request_type=request_type,
        metadata=metadata,
    )

    log.info(
        "llm_call_complete",
        agent_id=agent_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        response_len=len(text),
    )
    return text
