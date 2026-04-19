"""
V2FE E2E tests — MF Detail (mf-detail.html) page.

Opens mf-detail.html via file:// and verifies:
1. Page loads without crash
2. [data-endpoint] blocks exist (binding contract)
3. Returns block is present (V2FE-6 exit criterion)
4. page-level scope attr data-fund-code present on <main>
5. atlas-data.js + atlas-states.js referenced

Notes:
- file:// protocol blocks XHR/fetch so data-state won't reach "ready"
- Tests verify DOM structure only
- SKIP if playwright is not installed or mockup missing
"""

from __future__ import annotations

from pathlib import Path

import pytest

MOCKUP_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "mockups"


def _open_page(page_name: str):  # type: ignore[return]
    """Skip if file doesn't exist."""
    html_path = MOCKUP_DIR / page_name
    if not html_path.exists():
        pytest.skip(f"Mockup file not found: {page_name}")
    return html_path


# ---------------------------------------------------------------------------
# mf-detail.html E2E
# ---------------------------------------------------------------------------


def test_mf_detail_page_loads(page) -> None:  # type: ignore[no-untyped-def]
    """mf-detail.html loads without crash."""
    html_path = _open_page("mf-detail.html")
    url = f"file://{html_path}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception as exc:
        pytest.fail(f"Failed to load mf-detail.html: {exc}")

    body = page.locator("body")
    assert body.count() > 0, "mf-detail.html: body not found"


def test_mf_detail_has_data_endpoint_blocks(page) -> None:  # type: ignore[no-untyped-def]
    """mf-detail.html must have ≥5 V2 binding blocks."""
    html_path = _open_page("mf-detail.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    selector = "[data-endpoint], [data-v2-derived], [data-v2-deferred], [data-v2-static]"
    blocks = page.locator(selector)
    count = blocks.count()
    assert count >= 5, f"mf-detail.html: expected ≥5 V2 binding blocks, got {count}"


def test_mf_detail_returns_block_present(page) -> None:  # type: ignore[no-untyped-def]
    """mf-detail.html must have a returns block (V2FE-6 exit criterion)."""
    html_path = _open_page("mf-detail.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    returns_block = page.locator("[data-block=returns], [data-component=returns], .returns-block")
    assert returns_block.count() >= 1, (
        "mf-detail.html: returns block ([data-block=returns]) not found"
    )


def test_mf_detail_main_has_fund_code_scope(page) -> None:  # type: ignore[no-untyped-def]
    """mf-detail.html <main> must have page-level scope attr (data-fund-code or data-mstar-id)."""
    html_path = _open_page("mf-detail.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    # Accept data-fund-code OR data-mstar-id (V2FE-6 page-level scope variants)
    main_with_scope = page.locator("main[data-fund-code], main[data-mstar-id]")
    assert main_with_scope.count() >= 1, (
        "mf-detail.html: <main data-fund-code=...> or <main data-mstar-id=...> "
        "not found (V2FE-6 page-level scope)"
    )


def test_mf_detail_atlas_data_js_referenced(page) -> None:  # type: ignore[no-untyped-def]
    """mf-detail.html must reference atlas-data.js and atlas-states.js."""
    html_path = _open_page("mf-detail.html")
    content = html_path.read_text(encoding="utf-8")
    assert "atlas-data.js" in content, "mf-detail.html: atlas-data.js not referenced"
    assert "atlas-states.js" in content, "mf-detail.html: atlas-states.js not referenced"
