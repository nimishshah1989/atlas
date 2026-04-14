"""Auto-mark all tests under tests/integration/ with the 'integration' marker.

This ensures ``pytest -m 'not integration'`` (used by forge-ship.sh) skips
these tests, which require a live backend on localhost:8010.
"""

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
