"""
Shared fixtures for ATLAS frontend e2e Playwright tests.

Uses Python playwright sync API (playwright-1.58.0 installed in venv).
Tests open pages via file:// protocol against the static HTML mockups.
"""

from __future__ import annotations

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Directory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def mockup_dir() -> Path:
    """Absolute path to frontend/mockups/."""
    return Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "mockups"


@pytest.fixture(scope="session")
def baseline_dir() -> Path:
    """Absolute path to the e2e baselines directory."""
    d = Path(__file__).resolve().parent / "baselines"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Playwright browser fixture (session-scoped for speed)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def playwright_instance():
    """Launch a Playwright sync context for the test session."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance):
    """Launch headless Chromium browser for the session."""
    br = playwright_instance.chromium.launch(headless=True)
    yield br
    br.close()


@pytest.fixture
def page(browser):
    """Open a new browser page (function-scoped, closed after each test)."""
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        # Reduce motion for deterministic screenshots
        reduced_motion="reduce",
    )
    pg = ctx.new_page()
    yield pg
    pg.close()
    ctx.close()


# ---------------------------------------------------------------------------
# Auto-marker for e2e tests
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(config, items):
    """Auto-mark all tests in tests/e2e/ as e2e."""
    e2e_marker = pytest.mark.e2e
    for item in items:
        if "tests/e2e" in str(item.fspath):
            item.add_marker(e2e_marker)
