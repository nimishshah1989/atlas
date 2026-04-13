"""Embedding adapter: OpenAI primary, nomic-embed-text (Ollama) fallback.

All returned vectors are exactly 1536 dimensions.
nomic-embed-text natively produces 768 dims — zero-padded to 1536.
"""

from __future__ import annotations

import structlog
import httpx

from backend.config import Settings, get_settings

logger = structlog.get_logger(__name__)

DIMENSIONS = 1536
_NOMIC_NATIVE_DIMS = 768


class EmbeddingError(Exception):
    """Raised when all embedding providers fail."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def embed(text: str) -> list[float]:
    """Generate a 1536-dim embedding vector for the given text.

    Tries OpenAI first (if key configured), falls back to nomic/Ollama.

    Raises:
        ValueError: if text is empty or whitespace-only.
        EmbeddingError: if all providers fail.
    """
    if not text or not text.strip():
        raise ValueError("Cannot embed empty string")

    settings = get_settings()

    if settings.openai_api_key:
        try:
            return await _openai_embed(text, settings)
        except EmbeddingError as exc:
            logger.warning("openai_embed_failed", fallback="nomic", error=str(exc))

    return await _nomic_embed(text, settings)


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Generate 1536-dim embeddings for a batch of texts.

    Returns an empty list for an empty input.

    Raises:
        ValueError: if any text in the batch is empty or whitespace-only.
        EmbeddingError: if all providers fail.
    """
    if not texts:
        return []

    for t in texts:
        if not t or not t.strip():
            raise ValueError("Cannot embed empty string in batch")

    settings = get_settings()

    if settings.openai_api_key:
        try:
            return await _openai_embed_batch(texts, settings)
        except EmbeddingError as exc:
            logger.warning(
                "openai_batch_failed",
                fallback="nomic",
                count=len(texts),
                error=str(exc),
            )

    return await _nomic_embed_batch(texts, settings)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_and_pad(vector: list[float], source: str) -> list[float]:
    """Ensure vector is exactly DIMENSIONS long.

    nomic-embed-text returns 768 dims — zero-pad to 1536.
    Vectors already at 1536 pass through unchanged.
    """
    length = len(vector)
    if length == DIMENSIONS:
        return vector
    if length < DIMENSIONS:
        logger.debug(
            "vector_padded",
            source=source,
            original_dims=length,
            target_dims=DIMENSIONS,
        )
        return vector + [0.0] * (DIMENSIONS - length)
    raise EmbeddingError(
        f"Provider {source!r} returned {length}-dim vector; expected <= {DIMENSIONS}"
    )


async def _openai_embed(text: str, settings: Settings) -> list[float]:
    """Call OpenAI embeddings API for a single text."""
    url = "https://api.openai.com/v1/embeddings"
    payload = {
        "model": settings.embedding_model,
        "input": text,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise EmbeddingError(f"OpenAI HTTP transport error: {exc}") from exc

    if response.status_code >= 500:
        raise EmbeddingError(f"OpenAI server error {response.status_code}: {response.text[:200]}")
    if response.status_code >= 400:
        raise EmbeddingError(f"OpenAI client error {response.status_code}: {response.text[:200]}")

    data = response.json()
    vector: list[float] = data["data"][0]["embedding"]
    return _validate_and_pad(vector, "openai")


async def _openai_embed_batch(texts: list[str], settings: Settings) -> list[list[float]]:
    """Call OpenAI embeddings API for a batch of texts."""
    url = "https://api.openai.com/v1/embeddings"
    payload = {
        "model": settings.embedding_model,
        "input": texts,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise EmbeddingError(f"OpenAI batch HTTP transport error: {exc}") from exc

    if response.status_code >= 500:
        raise EmbeddingError(
            f"OpenAI batch server error {response.status_code}: {response.text[:200]}"
        )
    if response.status_code >= 400:
        raise EmbeddingError(
            f"OpenAI batch client error {response.status_code}: {response.text[:200]}"
        )

    data = response.json()
    # OpenAI sorts results by index — preserve original order
    items = sorted(data["data"], key=lambda x: x["index"])
    return [_validate_and_pad(item["embedding"], "openai") for item in items]


async def _nomic_embed(text: str, settings: Settings) -> list[float]:
    """Call Ollama-compatible /api/embeddings endpoint for a single text."""
    url = f"{settings.nomic_api_url}/api/embeddings"
    payload = {
        "model": "nomic-embed-text",
        "prompt": text,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise EmbeddingError(f"Nomic HTTP transport error: {exc}") from exc

    if response.status_code >= 400:
        raise EmbeddingError(f"Nomic error {response.status_code}: {response.text[:200]}")

    data = response.json()
    vector: list[float] = data["embedding"]
    return _validate_and_pad(vector, "nomic")


async def _nomic_embed_batch(texts: list[str], settings: Settings) -> list[list[float]]:
    """Embed a batch via nomic by making sequential single-text calls.

    Ollama's /api/embeddings endpoint takes one prompt at a time.
    """
    results: list[list[float]] = []
    for text in texts:
        vector = await _nomic_embed(text, settings)
        results.append(vector)
    return results
