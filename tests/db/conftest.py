"""Shared fixtures for DB schema tests (tests/db/).

These tests connect directly to the live PostgreSQL instance via psycopg2
for low-level schema introspection. Auto-marked as ``integration`` so
``pytest -m 'not integration'`` skips them during the forge-ship gate.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test in tests/db/ as integration."""
    integration_marker = pytest.mark.integration
    for item in items:
        if "tests/db" in str(item.fspath):
            item.add_marker(integration_marker)
