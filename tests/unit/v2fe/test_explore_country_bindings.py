"""Tests: V2FE-3 — explore-country.html data-endpoint bindings."""

from html.parser import HTMLParser
from pathlib import Path

import pytest


EXPLORE_COUNTRY_HTML = (
    Path(__file__).parent.parent.parent.parent / "frontend" / "mockups" / "explore-country.html"
)


class AttrCollector(HTMLParser):
    """Collect all tag attribute dicts."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = dict(attrs)
        if any(k.startswith("data-") for k in d):
            self.elements.append(d)


def _parse() -> list[dict[str, str]]:
    collector = AttrCollector()
    collector.feed(EXPLORE_COUNTRY_HTML.read_text())
    return collector.elements


def _find(elements: list[dict[str, str]], **attrs: str) -> list[dict[str, str]]:
    results = []
    for el in elements:
        if all(el.get(k) == v for k, v in attrs.items()):
            results.append(el)
    return results


@pytest.fixture(scope="module")
def elements() -> list[dict[str, str]]:
    return _parse()


def test_file_exists() -> None:
    assert EXPLORE_COUNTRY_HTML.exists(), "explore-country.html not found"


def test_regime_banner_has_endpoint(elements: list[dict[str, str]]) -> None:
    """regime-banner elements must carry data-endpoint."""
    banners = [e for e in elements if e.get("data-component") == "regime-banner"]
    assert len(banners) >= 1, "No regime-banner found"
    for b in banners:
        assert b.get("data-endpoint") == "/api/v1/stocks/breadth", (
            f"regime-banner missing correct endpoint: {b}"
        )


def test_signal_strip_has_endpoint(elements: list[dict[str, str]]) -> None:
    """signal-strip must carry data-endpoint."""
    strips = [e for e in elements if e.get("data-component") == "signal-strip"]
    assert len(strips) >= 1, "No signal-strip found"
    # Only outer signal-strip divs have data-endpoint (not inner span chips)
    with_endpoint = [s for s in strips if "data-endpoint" in s]
    assert len(with_endpoint) >= 1, f"No signal-strip with data-endpoint: {strips}"
    for s in with_endpoint:
        assert s.get("data-endpoint") == "/api/v1/stocks/breadth", (
            f"signal-strip has wrong endpoint: {s}"
        )


def test_dual_axis_overlay_has_endpoint(elements: list[dict[str, str]]) -> None:
    """dual-axis-overlay must carry data-endpoint and fixture."""
    overlays = [e for e in elements if e.get("data-component") == "dual-axis-overlay"]
    assert len(overlays) >= 1, "No dual-axis-overlay found"
    with_endpoint = [o for o in overlays if "data-endpoint" in o]
    assert len(with_endpoint) >= 1, "No dual-axis-overlay with data-endpoint"
    assert with_endpoint[0].get("data-endpoint") == "/api/v1/stocks/breadth", (
        f"dual-axis-overlay wrong endpoint: {with_endpoint[0]}"
    )
    assert with_endpoint[0].get("data-fixture") == "fixtures/breadth_daily_5y.json", (
        f"dual-axis-overlay missing fixture: {with_endpoint[0]}"
    )


def test_breadth_kpi_blocks_have_endpoint(elements: list[dict[str, str]]) -> None:
    """data-block=breadth-kpi must carry data-endpoint (3 blocks)."""
    kpis = [e for e in elements if e.get("data-block") == "breadth-kpi"]
    assert len(kpis) >= 3, f"Expected >=3 breadth-kpi blocks, got {len(kpis)}"
    for k in kpis:
        assert k.get("data-endpoint") == "/api/v1/stocks/breadth", (
            f"breadth-kpi missing endpoint: {k}"
        )
        assert k.get("data-data-class") == "eod_breadth", f"breadth-kpi missing data-class: {k}"


def test_flows_block_has_endpoint(elements: list[dict[str, str]]) -> None:
    """data-block=flows must carry data-endpoint (at least one instance)."""
    flows = [e for e in elements if e.get("data-block") == "flows"]
    assert len(flows) >= 1, "No flows block found"
    wired = [e for e in flows if e.get("data-endpoint") == "/api/v1/global/flows"]
    assert len(wired) >= 1, f"No flows element with correct endpoint; found: {flows}"


def test_sectors_rrg_has_endpoint(elements: list[dict[str, str]]) -> None:
    """data-block=sectors-rrg must carry data-endpoint and fixture (at least one instance)."""
    rrgs = [e for e in elements if e.get("data-block") == "sectors-rrg"]
    assert len(rrgs) >= 1, "No sectors-rrg block found"
    wired = [e for e in rrgs if e.get("data-endpoint") == "/api/v1/sectors/rrg"]
    assert len(wired) >= 1, f"No sectors-rrg element with correct endpoint; found: {rrgs}"
    assert wired[0].get("data-fixture") == "fixtures/sector_rrg.json", (
        f"sectors-rrg missing fixture: {wired[0]}"
    )


def test_derivatives_block_is_sparse(elements: list[dict[str, str]]) -> None:
    """Derivatives block must carry data-sparse=true and data-endpoint."""
    deriv = [e for e in elements if e.get("data-block") == "derivatives-panel"]
    assert len(deriv) >= 1, "No derivatives-panel block found"
    assert deriv[0].get("data-sparse") == "true", (
        f"derivatives-panel missing data-sparse: {deriv[0]}"
    )
    assert deriv[0].get("data-endpoint") == "/api/v1/derivatives/summary", (
        f"derivatives-panel missing endpoint: {deriv[0]}"
    )


def test_inr_block_is_sparse(elements: list[dict[str, str]]) -> None:
    """INR chart block must carry data-sparse=true."""
    inr = [e for e in elements if e.get("data-block") == "inr-chart"]
    assert len(inr) >= 1, "No inr-chart block found"
    assert inr[0].get("data-sparse") == "true", f"inr-chart missing data-sparse: {inr[0]}"


def test_divergences_block_has_endpoint(elements: list[dict[str, str]]) -> None:
    """divergences-block must carry data-endpoint."""
    divs = [e for e in elements if e.get("data-component") == "divergences-block"]
    assert len(divs) >= 1, "No divergences-block sentinel found"
    assert divs[0].get("data-endpoint") == "/api/v1/stocks/breadth/divergences", (
        f"divergences-block missing endpoint: {divs[0]}"
    )


def test_events_overlay_has_endpoint(elements: list[dict[str, str]]) -> None:
    """events-overlay must carry data-endpoint and fixture."""
    events = [e for e in elements if e.get("data-component") == "events-overlay"]
    assert len(events) >= 1, "No events-overlay sentinel found"
    assert events[0].get("data-endpoint") == "/api/v1/global/events", (
        f"events-overlay missing endpoint: {events[0]}"
    )
    assert events[0].get("data-fixture") == "fixtures/events.json", (
        f"events-overlay missing fixture: {events[0]}"
    )


def test_minimum_ten_endpoints(elements: list[dict[str, str]]) -> None:
    """explore-country.html must have >=10 data-endpoint attributes (exit criterion)."""
    endpoints = [e for e in elements if "data-endpoint" in e]
    assert len(endpoints) >= 10, f"Expected >=10 data-endpoint blocks, got {len(endpoints)}"


def test_interpretation_sidecar_is_derived(elements: list[dict[str, str]]) -> None:
    """interpretation-sidecar must carry data-v2-derived=true, NOT data-endpoint."""
    sidecars = [e for e in elements if e.get("data-component") == "interpretation-sidecar"]
    assert len(sidecars) >= 1, "No interpretation-sidecar found"
    for s in sidecars:
        assert "data-endpoint" not in s, (
            f"interpretation-sidecar should not have data-endpoint: {s}"
        )
        assert s.get("data-v2-derived") == "true", (
            f"interpretation-sidecar missing data-v2-derived: {s}"
        )


def test_signal_playback_compact_has_no_endpoint(elements: list[dict[str, str]]) -> None:
    """signal-playback compact must carry data-v2-derived=true, NOT data-endpoint."""
    playbacks = [
        e
        for e in elements
        if e.get("data-component") == "signal-playback" and e.get("data-mode") == "compact"
    ]
    assert len(playbacks) >= 1, "No signal-playback[compact] found"
    for p in playbacks:
        assert "data-endpoint" not in p, (
            f"signal-playback compact should not have data-endpoint: {p}"
        )
        assert p.get("data-v2-derived") == "true", f"signal-playback missing data-v2-derived: {p}"


def test_atlas_data_js_script_present() -> None:
    """explore-country.html must have a script tag for atlas-data.js."""
    content = EXPLORE_COUNTRY_HTML.read_text()
    assert "atlas-data.js" in content, "atlas-data.js script tag not found in explore-country.html"


def test_atlas_states_js_script_present() -> None:
    """explore-country.html must have a script tag for atlas-states.js."""
    content = EXPLORE_COUNTRY_HTML.read_text()
    assert "atlas-states.js" in content, (
        "atlas-states.js script tag not found in explore-country.html"
    )
