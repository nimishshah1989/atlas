"""
V2FE E2E tests — MF Rank (mf-rank.html) page.

Opens mf-rank.html via file:// and verifies:
1. Page loads without crash
2. [data-endpoint] blocks exist (binding contract)
3. Rank table block is present
4. atlas-data.js + atlas-states.js referenced

Notes:
- file:// protocol blocks XHR/fetch so data-state won't reach "ready"
- Tests verify DOM structure only
- The rank table ≥10 rows assertion is deferred to live-backend E2E
  (with file:// the table renders in its skeleton/empty state)
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
# mf-rank.html E2E
# ---------------------------------------------------------------------------


def test_mf_rank_page_loads(page) -> None:  # type: ignore[no-untyped-def]
    """mf-rank.html loads without crash."""
    html_path = _open_page("mf-rank.html")
    url = f"file://{html_path}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception as exc:
        pytest.fail(f"Failed to load mf-rank.html: {exc}")

    body = page.locator("body")
    assert body.count() > 0, "mf-rank.html: body not found"


def test_mf_rank_has_data_endpoint_blocks(page) -> None:  # type: ignore[no-untyped-def]
    """mf-rank.html must have ≥1 V2 binding block."""
    html_path = _open_page("mf-rank.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    selector = "[data-endpoint], [data-v2-derived], [data-v2-deferred], [data-v2-static]"
    blocks = page.locator(selector)
    count = blocks.count()
    assert count >= 1, f"mf-rank.html: expected ≥1 V2 binding block, got {count}"


def test_mf_rank_table_block_present(page) -> None:  # type: ignore[no-untyped-def]
    """mf-rank.html must have a rank-table element (V2FE-7 exit criterion)."""
    html_path = _open_page("mf-rank.html")
    url = f"file://{html_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    rank_table = page.locator("[data-block=rank-table], [data-component=rank-table], .rank-table")
    assert rank_table.count() >= 1, (
        "mf-rank.html: rank-table element ([data-block=rank-table]) not found"
    )


def test_mf_rank_atlas_data_js_referenced(page) -> None:  # type: ignore[no-untyped-def]
    """mf-rank.html must reference atlas-data.js and atlas-states.js."""
    html_path = _open_page("mf-rank.html")
    content = html_path.read_text(encoding="utf-8")
    assert "atlas-data.js" in content, "mf-rank.html: atlas-data.js not referenced"
    assert "atlas-states.js" in content, "mf-rank.html: atlas-states.js not referenced"
