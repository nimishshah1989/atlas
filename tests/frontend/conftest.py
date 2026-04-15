"""Auto-mark all tests under tests/frontend/ with the 'integration' marker.

These tests require a live backend on localhost:8000. They are skipped by
``pytest -m 'not integration'`` (used by forge-ship.sh).
"""

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "/frontend/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
