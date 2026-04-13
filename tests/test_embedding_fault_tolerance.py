"""Tests for embedding fault tolerance in intelligence writer."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_store_finding_without_embedding() -> None:
    """store_finding should succeed even when embedding service is down."""
    from backend.services.embedding import EmbeddingError

    mock_db = AsyncMock()

    # Mock the INSERT upsert — returns a scalar UUID
    mock_upsert_result = MagicMock()
    import uuid

    fake_id = uuid.uuid4()
    mock_upsert_result.scalar_one.return_value = fake_id

    # Mock the SELECT fetch — returns an ORM row
    from backend.db.models import AtlasIntelligence

    mock_row = MagicMock(spec=AtlasIntelligence)
    mock_row.id = fake_id
    mock_fetch_result = MagicMock()
    mock_fetch_result.scalar_one.return_value = mock_row

    # EmbeddingError means only 2 execute calls: INSERT upsert + SELECT fetch
    # (no UPDATE embedding call)
    mock_db.execute.side_effect = [mock_upsert_result, mock_fetch_result]

    with patch("backend.services.intelligence.embed", side_effect=EmbeddingError("service down")):
        from backend.services.intelligence import store_finding

        result = await store_finding(
            db=mock_db,
            agent_id="test-agent",
            agent_type="test",
            entity="TESTSTOCK",
            entity_type="equity",
            finding_type="technical",
            title="Test Finding",
            content="Test content for fault tolerance",
            confidence=Decimal("0.8"),
            data_as_of=datetime.now(timezone.utc),
        )

    # Finding was stored successfully
    assert result is not None
    assert result.id == fake_id

    # Only 2 execute calls — INSERT upsert + SELECT fetch (NO embedding UPDATE)
    assert mock_db.execute.call_count == 2, (
        f"Expected 2 execute calls (upsert + fetch), got {mock_db.execute.call_count}. "
        "The embedding UPDATE must be skipped when EmbeddingError is raised."
    )

    # commit was called
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_store_finding_with_embedding() -> None:
    """store_finding should call UPDATE embedding when embedding succeeds."""
    mock_db = AsyncMock()

    import uuid

    fake_id = uuid.uuid4()
    fake_vector = [0.1] * 1536

    mock_upsert_result = MagicMock()
    mock_upsert_result.scalar_one.return_value = fake_id

    mock_embed_result = MagicMock()  # UPDATE result

    from backend.db.models import AtlasIntelligence

    mock_row = MagicMock(spec=AtlasIntelligence)
    mock_row.id = fake_id
    mock_fetch_result = MagicMock()
    mock_fetch_result.scalar_one.return_value = mock_row

    # 3 calls: INSERT upsert + UPDATE embedding + SELECT fetch
    mock_db.execute.side_effect = [mock_upsert_result, mock_embed_result, mock_fetch_result]

    with patch("backend.services.intelligence.embed", return_value=fake_vector):
        from backend.services.intelligence import store_finding

        result = await store_finding(
            db=mock_db,
            agent_id="test-agent",
            agent_type="test",
            entity="TESTSTOCK",
            entity_type="equity",
            finding_type="technical",
            title="Test Finding With Embedding",
            content="Test content with embedding available",
            confidence=Decimal("0.9"),
            data_as_of=datetime.now(timezone.utc),
        )

    assert result is not None
    # 3 calls: upsert + embedding UPDATE + fetch
    assert mock_db.execute.call_count == 3, (
        f"Expected 3 execute calls (upsert + embed UPDATE + fetch), "
        f"got {mock_db.execute.call_count}"
    )


def test_embedding_error_importable() -> None:
    """EmbeddingError must be importable from the embedding module."""
    from backend.services.embedding import EmbeddingError

    assert issubclass(EmbeddingError, Exception)
