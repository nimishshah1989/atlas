"""Shared fixtures for live API integration tests (tests/api/).

These tests hit the backend on localhost:8010 and are rate-limited at
60/minute. When run in bulk (e.g. ``pytest tests/``), early tests
exhaust the rate budget and later tests get 429 responses.

Auto-collected as ``integration`` marker so ``pytest -m 'not integration'``
skips them during the forge-ship gate.
"""

from __future__ import annotations

import httpx
import pytest

BASE_URL = "http://localhost:8010"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test in tests/api/ as integration."""
    integration_marker = pytest.mark.integration
    for item in items:
        if "tests/api" in str(item.fspath):
            item.add_marker(integration_marker)


@pytest.fixture(scope="session")
def api_client() -> httpx.Client:
    """Client for live API tests, skips if backend unreachable."""
    client = httpx.Client(base_url=BASE_URL, timeout=10.0)
    try:
        client.get("/api/v1/health")
    except httpx.ConnectError as exc:
        pytest.skip(f"backend not reachable at {BASE_URL}: {exc}")
    return client
