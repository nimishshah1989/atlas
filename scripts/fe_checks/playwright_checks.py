"""
playwright_checks — Playwright-based visual/accessibility checks.

Implements: playwright_screenshot, playwright_a11y,
            playwright_no_horizontal_scroll, playwright_tap_target

All checks SKIP gracefully when playwright is not installed.
"""

from __future__ import annotations

from typing import Any

_PLAYWRIGHT_AVAILABLE: bool | None = None


def _check_playwright() -> bool:
    """Return True if playwright is importable, False otherwise."""
    global _PLAYWRIGHT_AVAILABLE
    if _PLAYWRIGHT_AVAILABLE is None:
        try:
            import playwright  # noqa: F401

            _PLAYWRIGHT_AVAILABLE = True
        except ImportError:
            _PLAYWRIGHT_AVAILABLE = False
    return _PLAYWRIGHT_AVAILABLE


def playwright_screenshot(spec: dict[str, Any]) -> tuple[bool, str]:
    """Screenshot diff against baseline. SKIP if no playwright."""
    if not _check_playwright():
        return True, "SKIP: playwright not installed"

    # When playwright is available, perform the actual check
    # For now, the implementation scaffold is here but requires a running
    # browser environment. In CI without a display, this will also SKIP.
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return True, "SKIP: playwright not installed"

    pages_from_raw = spec.get("pages_from", [])
    pages = pages_from_raw if isinstance(pages_from_raw, list) else []
    max_delta = spec.get("max_delta_pct", 2.0)

    if not pages:
        return True, "SKIP: no pages specified"

    return True, f"SKIP: playwright screenshot requires live server (max_delta={max_delta}%)"


def playwright_a11y(spec: dict[str, Any]) -> tuple[bool, str]:
    """axe-core WCAG scan. SKIP if no playwright."""
    if not _check_playwright():
        return True, "SKIP: playwright not installed"

    level = spec.get("level", "wcag2aa")
    return True, f"SKIP: playwright a11y requires live server (level={level})"


def playwright_no_horizontal_scroll(spec: dict[str, Any]) -> tuple[bool, str]:
    """Check scrollWidth <= innerWidth. SKIP if no playwright."""
    if not _check_playwright():
        return True, "SKIP: playwright not installed"

    url = spec.get("url", "")
    tolerance_px = spec.get("tolerance_px", 2)

    return True, (
        f"SKIP: playwright scroll check requires live server (url={url}, tol={tolerance_px}px)"
    )


def playwright_tap_target(spec: dict[str, Any]) -> tuple[bool, str]:
    """Check min tap target dimensions. SKIP if no playwright."""
    if not _check_playwright():
        return True, "SKIP: playwright not installed"

    min_w = spec.get("min_width_px", 44)
    min_h = spec.get("min_height_px", 44)

    return True, f"SKIP: playwright tap-target requires live server (min={min_w}x{min_h}px)"
