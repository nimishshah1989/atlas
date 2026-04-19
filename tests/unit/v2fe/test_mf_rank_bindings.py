"""Tests: V2FE-7 — mf-rank.html data-endpoint bindings (MF rank 4-factor composite)."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import pytest


MF_RANK_HTML = Path(__file__).parent.parent.parent.parent / "frontend" / "mockups" / "mf-rank.html"


class AttrCollector(HTMLParser):
    """Collect all tags that carry at least one data-* attribute."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = {k: (v or "") for k, v in attrs}
        if any(k.startswith("data-") for k in d):
            self.elements.append(d)


def _parse() -> list[dict[str, str]]:
    collector = AttrCollector()
    collector.feed(MF_RANK_HTML.read_text())
    return collector.elements


@pytest.fixture(scope="module")
def elements() -> list[dict[str, str]]:
    return _parse()


def test_file_exists() -> None:
    assert MF_RANK_HTML.exists(), "mf-rank.html not found"


def test_minimum_endpoint_count(elements: list[dict[str, str]]) -> None:
    """>=5 elements must carry a data-endpoint attribute."""
    wired = [e for e in elements if e.get("data-endpoint")]
    assert len(wired) >= 5, f"Expected >=5 data-endpoint attrs, found {len(wired)}"


def test_rank_table_endpoint_and_template(elements: list[dict[str, str]]) -> None:
    """[data-block=rank-table] must carry /api/v1/query/template and template=mf_rank_composite."""
    rank_tables = [e for e in elements if e.get("data-block") == "rank-table"]
    assert len(rank_tables) >= 1, "No data-block=rank-table found"
    wired = [e for e in rank_tables if e.get("data-endpoint") == "/api/v1/query/template"]
    assert len(wired) >= 1, "rank-table block not wired to /api/v1/query/template"
    params_str = wired[0].get("data-params", "{}")
    params = json.loads(params_str)
    assert params.get("template") == "mf_rank_composite", (
        f"rank-table template is not mf_rank_composite: {params}"
    )


def test_regime_banner_endpoint(elements: list[dict[str, str]]) -> None:
    """[data-component=regime-banner] must carry data-endpoint='/api/v1/stocks/breadth'."""
    regime_els = [e for e in elements if e.get("data-component") == "regime-banner"]
    assert len(regime_els) >= 1, "No data-component=regime-banner found"
    wired = [e for e in regime_els if e.get("data-endpoint") == "/api/v1/stocks/breadth"]
    assert len(wired) >= 1, "regime-banner not wired to /api/v1/stocks/breadth"


def test_methodology_footer_endpoint(elements: list[dict[str, str]]) -> None:
    """footer.methodology-footer must carry data-endpoint='/api/v1/system/data-health'."""
    footers = [e for e in elements if "methodology-footer" in e.get("class", "")]
    assert len(footers) >= 1, "No element with class methodology-footer found"
    wired = [e for e in footers if e.get("data-endpoint") == "/api/v1/system/data-health"]
    assert len(wired) >= 1, "methodology-footer not wired to /api/v1/system/data-health"
    params_str = wired[0].get("data-params", "{}")
    params = json.loads(params_str)
    assert params.get("job") == "mf_rank", f"methodology-footer job is not mf_rank: {params}"


def test_formula_block_has_no_endpoint(elements: list[dict[str, str]]) -> None:
    """[data-role=formula] must NOT have a data-endpoint (whitelisted as static)."""
    formula_els = [e for e in elements if e.get("data-role") == "formula"]
    assert len(formula_els) >= 1, "No data-role=formula found"
    with_endpoint = [e for e in formula_els if e.get("data-endpoint")]
    assert len(with_endpoint) == 0, (
        f"formula block must have no data-endpoint but found {len(with_endpoint)}"
    )


def test_formula_block_is_v2_static(elements: list[dict[str, str]]) -> None:
    """[data-role=formula] must carry data-v2-static='true'."""
    formula_els = [e for e in elements if e.get("data-role") == "formula"]
    assert len(formula_els) >= 1, "No data-role=formula found"
    marked = [e for e in formula_els if e.get("data-v2-static") == "true"]
    assert len(marked) >= 1, "formula block missing data-v2-static=true"


def test_filter_rail_primary_endpoint(elements: list[dict[str, str]]) -> None:
    """[data-block=filter-rail] must carry data-endpoint='/api/v1/mf/categories'."""
    filter_rail_els = [e for e in elements if e.get("data-block") == "filter-rail"]
    assert len(filter_rail_els) >= 1, "No data-block=filter-rail found"
    wired = [e for e in filter_rail_els if e.get("data-endpoint") == "/api/v1/mf/categories"]
    assert len(wired) >= 1, "filter-rail not wired to /api/v1/mf/categories"


def test_interpretation_sidecar_has_no_endpoint(elements: list[dict[str, str]]) -> None:
    """[data-component=interpretation-sidecar] must NOT have a data-endpoint (client-derived)."""
    sidecar_els = [e for e in elements if e.get("data-component") == "interpretation-sidecar"]
    assert len(sidecar_els) >= 1, "No data-component=interpretation-sidecar found"
    with_endpoint = [e for e in sidecar_els if e.get("data-endpoint")]
    assert len(with_endpoint) == 0, (
        "interpretation-sidecar must have no data-endpoint but found one"
    )


def test_mf_rank_js_asset_exists() -> None:
    """assets/mf-rank.js must exist (extracted IIFE)."""
    js_path = MF_RANK_HTML.parent / "assets" / "mf-rank.js"
    assert js_path.exists(), "assets/mf-rank.js not found"


def test_no_inline_script_block_in_html() -> None:
    """mf-rank.html must NOT contain the old inline fixture-loading <script> block."""
    html = MF_RANK_HTML.read_text()
    # The inline script contained these specific function names
    assert "function renderFixture" not in html, (
        "renderFixture function found in mf-rank.html — inline script was not extracted"
    )
    assert "function buildCategoryFilter" not in html, (
        "buildCategoryFilter found in mf-rank.html — inline script was not extracted"
    )


def test_deferred_script_tags_present() -> None:
    """mf-rank.html must have deferred script tags for all three JS assets."""
    html = MF_RANK_HTML.read_text()
    assert 'src="assets/atlas-data.js"' in html, "atlas-data.js deferred script tag missing"
    assert 'src="assets/atlas-states.js"' in html, "atlas-states.js deferred script tag missing"
    assert 'src="assets/mf-rank.js"' in html, "mf-rank.js deferred script tag missing"
