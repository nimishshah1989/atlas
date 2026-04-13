"""Tests for backend/services/embedding.py.

All HTTP calls are mocked — no real network traffic.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.embedding import (
    DIMENSIONS,
    EmbeddingError,
    embed,
    embed_batch,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _openai_response(vectors: list[list[float]], status_code: int = 200) -> MagicMock:
    """Build a mock httpx Response for the OpenAI embeddings endpoint."""
    body = {
        "data": [
            {"index": i, "embedding": vec, "object": "embedding"} for i, vec in enumerate(vectors)
        ],
        "model": "text-embedding-3-small",
        "usage": {"prompt_tokens": 8, "total_tokens": 8},
    }
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = body
    mock_response.text = json.dumps(body)
    return mock_response


def _nomic_response(vector: list[float], status_code: int = 200) -> MagicMock:
    """Build a mock httpx Response for the nomic/Ollama embeddings endpoint."""
    body = {"embedding": vector}
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = body
    mock_response.text = json.dumps(body)
    return mock_response


def _make_vector(dims: int = DIMENSIONS) -> list[float]:
    """Return a list of `dims` float values."""
    return [0.1] * dims


def _make_settings(embed_provider_key: str = "test-embed") -> MagicMock:
    """Return a mock Settings object."""
    s = MagicMock()
    s.openai_api_key = embed_provider_key
    s.nomic_api_url = "http://localhost:11434"
    s.embedding_model = "text-embedding-3-small"
    s.embedding_dimensions = DIMENSIONS
    return s


# ---------------------------------------------------------------------------
# Test: OpenAI success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_openai_success_returns_1536_vector() -> None:
    """OpenAI returns a 1536-dim vector — adapter passes it through unchanged."""
    vec = _make_vector(DIMENSIONS)
    mock_response = _openai_response([vec])
    settings = _make_settings(embed_provider_key="test-embed")

    async_client_mock = AsyncMock()
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=False)
    async_client_mock.post = AsyncMock(return_value=mock_response)

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=async_client_mock),
    ):
        result = await embed("hello world")

    assert len(result) == DIMENSIONS
    assert result == vec


# ---------------------------------------------------------------------------
# Test: OpenAI 5xx → fallback to nomic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_openai_5xx_falls_back_to_nomic() -> None:
    """OpenAI 500 triggers nomic fallback; result is still 1536-dim."""
    openai_error_response = MagicMock()
    openai_error_response.status_code = 500
    openai_error_response.text = "Internal Server Error"

    nomic_vec = _make_vector(_NOMIC_NATIVE_DIMS())
    nomic_mock_response = _nomic_response(nomic_vec)

    settings = _make_settings(embed_provider_key="test-embed")

    call_count = {"n": 0}

    async def fake_post(url: str, **kwargs: object) -> MagicMock:
        call_count["n"] += 1
        if "openai" in url:
            return openai_error_response
        return nomic_mock_response

    async_client_mock = AsyncMock()
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=False)
    async_client_mock.post = fake_post

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=async_client_mock),
    ):
        result = await embed("hello world")

    assert len(result) == DIMENSIONS
    # Nomic 768 dims zero-padded to 1536
    assert result[: _NOMIC_NATIVE_DIMS()] == nomic_vec
    assert all(v == 0.0 for v in result[_NOMIC_NATIVE_DIMS() :])


def _NOMIC_NATIVE_DIMS() -> int:
    """Return the native nomic dimension count (768)."""
    from backend.services.embedding import _NOMIC_NATIVE_DIMS as _n

    return _n


# ---------------------------------------------------------------------------
# Test: missing key → nomic direct
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_missing_openai_key_goes_directly_to_nomic() -> None:
    """Empty openai_api_key skips OpenAI entirely and calls nomic."""
    nomic_vec = _make_vector(DIMENSIONS)
    nomic_mock_response = _nomic_response(nomic_vec)
    settings = _make_settings(embed_provider_key="")

    openai_called = {"called": False}

    async def fake_post(url: str, **kwargs: object) -> MagicMock:
        if "openai" in url:
            openai_called["called"] = True
        return nomic_mock_response

    async_client_mock = AsyncMock()
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=False)
    async_client_mock.post = fake_post

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=async_client_mock),
    ):
        result = await embed("test text")

    assert not openai_called["called"], "OpenAI should NOT be called when key is empty"
    assert len(result) == DIMENSIONS


# ---------------------------------------------------------------------------
# Test: empty string raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_empty_string_raises_value_error() -> None:
    """Empty string must raise ValueError before any HTTP call."""
    with pytest.raises(ValueError, match="Cannot embed empty string"):
        await embed("")


@pytest.mark.asyncio
async def test_embed_whitespace_only_raises_value_error() -> None:
    """Whitespace-only string must raise ValueError before any HTTP call."""
    with pytest.raises(ValueError, match="Cannot embed empty string"):
        await embed("   ")


# ---------------------------------------------------------------------------
# Test: batch of 50
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_batch_of_50_returns_50_vectors_of_1536() -> None:
    """Batch of 50 texts via OpenAI returns 50 vectors each of length 1536."""
    texts = [f"text number {i}" for i in range(50)]
    vectors = [_make_vector(DIMENSIONS) for _ in range(50)]
    mock_response = _openai_response(vectors)
    settings = _make_settings(embed_provider_key="test-embed")

    async_client_mock = AsyncMock()
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=False)
    async_client_mock.post = AsyncMock(return_value=mock_response)

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=async_client_mock),
    ):
        results = await embed_batch(texts)

    assert len(results) == 50
    for vec in results:
        assert len(vec) == DIMENSIONS


# ---------------------------------------------------------------------------
# Test: batch with empty string raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_batch_empty_string_raises_value_error() -> None:
    """Batch containing an empty string raises ValueError."""
    with pytest.raises(ValueError, match="Cannot embed empty string"):
        await embed_batch(["valid text", "", "another text"])


@pytest.mark.asyncio
async def test_embed_batch_empty_list_returns_empty() -> None:
    """Empty batch returns an empty list without any HTTP calls."""
    result = await embed_batch([])
    assert result == []


# ---------------------------------------------------------------------------
# Test: vector length always 1536 regardless of path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_vector_length_openai_path_is_1536() -> None:
    """OpenAI path always produces exactly 1536-dim vector."""
    vec = _make_vector(DIMENSIONS)
    mock_response = _openai_response([vec])
    settings = _make_settings(embed_provider_key="test-embed")

    async_client_mock = AsyncMock()
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=False)
    async_client_mock.post = AsyncMock(return_value=mock_response)

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=async_client_mock),
    ):
        result = await embed("OpenAI path vector length check")

    assert len(result) == DIMENSIONS


@pytest.mark.asyncio
async def test_embed_vector_length_nomic_path_is_1536() -> None:
    """Nomic path (768-dim native) is padded to exactly 1536-dim."""
    nomic_vec = _make_vector(768)
    mock_response = _nomic_response(nomic_vec)
    settings = _make_settings(embed_provider_key="")

    async_client_mock = AsyncMock()
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=False)
    async_client_mock.post = AsyncMock(return_value=mock_response)

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=async_client_mock),
    ):
        result = await embed("nomic path vector length check")

    assert len(result) == DIMENSIONS


# ---------------------------------------------------------------------------
# Test: both providers fail → EmbeddingError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_both_providers_fail_raises_embedding_error() -> None:
    """When both OpenAI and nomic fail, EmbeddingError is raised."""
    import httpx as _httpx

    settings = _make_settings(embed_provider_key="test-embed")

    async def fake_post(url: str, **kwargs: object) -> None:
        raise _httpx.ConnectError("connection refused", request=MagicMock())

    async_client_mock = AsyncMock()
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=False)
    async_client_mock.post = fake_post

    with (
        patch("backend.services.embedding.get_settings", return_value=settings),
        patch("backend.services.embedding.httpx.AsyncClient", return_value=async_client_mock),
    ):
        with pytest.raises(EmbeddingError):
            await embed("will fail on both providers")
