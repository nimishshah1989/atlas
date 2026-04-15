"""Unit tests for embedding.py fallback behaviour.

Covers four key scenarios:
1. Primary (OpenAI) success — 1536-dim passthrough
2. Primary 5xx — fallback to nomic, zero-padded to 1536
3. Both providers down — EmbeddingError raised
4. Dimensionality invariance — both paths always produce exactly DIMENSIONS

All HTTP calls are mocked — no real network traffic.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.services.embedding import (
    DIMENSIONS,
    _NOMIC_NATIVE_DIMS,
    EmbeddingError,
    embed,
    embed_batch,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(embed_provider_key: str = "test-embed") -> MagicMock:
    """Return a mock Settings object."""
    s = MagicMock()
    s.openai_api_key = embed_provider_key
    s.nomic_api_url = "http://localhost:11434"
    s.embedding_model = "text-embedding-3-small"
    s.embedding_dimensions = DIMENSIONS
    return s


def _make_openai_response(vectors: list[list[float]], status_code: int = 200) -> MagicMock:
    """Build a mock httpx Response for the OpenAI embeddings endpoint."""
    body = {
        "data": [
            {"index": i, "embedding": vec, "object": "embedding"} for i, vec in enumerate(vectors)
        ],
        "model": "text-embedding-3-small",
        "usage": {"prompt_tokens": 8, "total_tokens": 8},
    }
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = body
    mock_resp.text = json.dumps(body)
    return mock_resp


def _make_nomic_response(vector: list[float], status_code: int = 200) -> MagicMock:
    """Build a mock httpx Response for the nomic/Ollama embeddings endpoint."""
    body = {"embedding": vector}
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = body
    mock_resp.text = json.dumps(body)
    return mock_resp


def _make_vector(dims: int = DIMENSIONS) -> list[float]:
    """Return a list of `dims` distinct float values."""
    return [float(i) / dims for i in range(dims)]


def _make_async_client(post_fn: object) -> AsyncMock:
    """Wrap a post callable in an async context manager mock."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = post_fn
    return client


# ---------------------------------------------------------------------------
# 1. Primary success — OpenAI returns 1536-dim, passes through unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_primary_success_returns_1536_vector() -> None:
    """OpenAI returns a 1536-dim vector; adapter passes it through unchanged."""
    vec = _make_vector(DIMENSIONS)
    openai_resp = _make_openai_response([vec])
    settings = _make_settings()

    client = _make_async_client(AsyncMock(return_value=openai_resp))

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=client),
    ):
        result = await embed("hello world")

    assert len(result) == DIMENSIONS
    assert result == vec


# ---------------------------------------------------------------------------
# 2. Primary 5xx → fallback to nomic, 768 dims zero-padded to 1536
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_primary_5xx_fallback_to_nomic_returns_1536() -> None:
    """OpenAI 500 triggers nomic fallback; result is exactly 1536-dim."""
    openai_error_resp = MagicMock()
    openai_error_resp.status_code = 500
    openai_error_resp.text = "Internal Server Error"

    nomic_vec = _make_vector(_NOMIC_NATIVE_DIMS)
    nomic_resp = _make_nomic_response(nomic_vec)

    settings = _make_settings()

    async def fake_post(url: str, **kwargs: object) -> MagicMock:
        if "openai" in url:
            return openai_error_resp
        return nomic_resp

    client = _make_async_client(fake_post)

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=client),
    ):
        result = await embed("hello world")

    assert len(result) == DIMENSIONS
    # Original nomic values preserved in first 768 slots
    assert result[:_NOMIC_NATIVE_DIMS] == nomic_vec
    # Remaining slots are zero-padded
    assert all(v == 0.0 for v in result[_NOMIC_NATIVE_DIMS:])


# ---------------------------------------------------------------------------
# 3. Both providers down → EmbeddingError raised
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_both_providers_down_raises_embedding_error() -> None:
    """When both OpenAI and nomic fail, EmbeddingError is raised."""
    settings = _make_settings()

    async def fake_post(url: str, **kwargs: object) -> None:
        raise httpx.ConnectError("connection refused", request=MagicMock())

    client = _make_async_client(fake_post)

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(EmbeddingError):
            await embed("will fail on both providers")


# ---------------------------------------------------------------------------
# 4. Dimensionality invariance — OpenAI path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_dimensionality_invariant_openai_path() -> None:
    """OpenAI path always produces exactly DIMENSIONS (1536) elements."""
    vec = _make_vector(DIMENSIONS)
    openai_resp = _make_openai_response([vec])
    settings = _make_settings()

    client = _make_async_client(AsyncMock(return_value=openai_resp))

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=client),
    ):
        result = await embed("dimensionality check openai")

    assert len(result) == DIMENSIONS, f"Expected {DIMENSIONS}, got {len(result)}"


# ---------------------------------------------------------------------------
# 5. Dimensionality invariance — nomic path (768 padded to 1536)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_dimensionality_invariant_nomic_path() -> None:
    """Nomic path (768-dim native) is always padded to exactly DIMENSIONS (1536)."""
    nomic_vec = _make_vector(_NOMIC_NATIVE_DIMS)
    nomic_resp = _make_nomic_response(nomic_vec)
    # No OpenAI key → goes directly to nomic
    settings = _make_settings(embed_provider_key="")

    client = _make_async_client(AsyncMock(return_value=nomic_resp))

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=client),
    ):
        result = await embed("dimensionality check nomic")

    assert len(result) == DIMENSIONS, f"Expected {DIMENSIONS}, got {len(result)}"


# ---------------------------------------------------------------------------
# 6. Batch: primary 5xx → fallback to nomic (sequential)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_batch_primary_5xx_fallback_nomic() -> None:
    """Batch: OpenAI 500 triggers nomic fallback; all results are 1536-dim."""
    openai_error_resp = MagicMock()
    openai_error_resp.status_code = 500
    openai_error_resp.text = "Internal Server Error"

    nomic_vec = _make_vector(_NOMIC_NATIVE_DIMS)
    nomic_resp = _make_nomic_response(nomic_vec)

    settings = _make_settings()

    async def fake_post(url: str, **kwargs: object) -> MagicMock:
        if "openai" in url:
            return openai_error_resp
        return nomic_resp

    client = _make_async_client(fake_post)

    texts = ["text one", "text two", "text three"]

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=client),
    ):
        results = await embed_batch(texts)

    assert len(results) == len(texts)
    for vec in results:
        assert len(vec) == DIMENSIONS
        # Nomic padding invariant: first 768 are from nomic, rest are 0.0
        assert vec[:_NOMIC_NATIVE_DIMS] == nomic_vec
        assert all(v == 0.0 for v in vec[_NOMIC_NATIVE_DIMS:])


# ---------------------------------------------------------------------------
# 7. Batch: both providers down → EmbeddingError raised
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_batch_both_down_raises_embedding_error() -> None:
    """Batch: when both OpenAI and nomic fail, EmbeddingError is raised."""
    settings = _make_settings()

    async def fake_post(url: str, **kwargs: object) -> None:
        raise httpx.ConnectError("connection refused", request=MagicMock())

    client = _make_async_client(fake_post)

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(EmbeddingError):
            await embed_batch(["will fail on both providers", "second text"])
