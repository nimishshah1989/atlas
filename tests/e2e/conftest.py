"""
Shared fixtures for V2FE E2E tests in tests/e2e/.

These fixtures are scoped to the tests/e2e/ directory so both the
fe_pages/ subdir and the v2fe_*.py specs can use them.

The `page` fixture requires playwright to be installed. Tests that
use `page` will SKIP automatically if playwright is not available via
the skip guard in each test function.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def playwright_session():
    """Launch a Playwright sync context for the test session.

    Returns None if playwright is not installed so callers can skip.
    """
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            yield p
    except ImportError:
        yield None


@pytest.fixture(scope="session")
def browser(playwright_session):
    """Launch headless Chromium browser for the session.

    Returns None if playwright is not available.
    """
    if playwright_session is None:
        yield None
        return
    try:
        br = playwright_session.chromium.launch(headless=True)
        yield br
        br.close()
    except Exception:  # noqa: BLE001
        yield None


@pytest.fixture
def page(browser):
    """Open a new browser page (function-scoped, closed after each test).

    SKIP if browser is not available (playwright not installed).
    """
    if browser is None:
        pytest.skip("playwright not installed or browser unavailable")
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        reduced_motion="reduce",
    )
    pg = ctx.new_page()
    yield pg
    pg.close()
    ctx.close()
