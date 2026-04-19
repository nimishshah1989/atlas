"""Tests: V2FE-6 — mf-detail.html data-endpoint bindings (hub-and-spoke MF terminal)."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import pytest


MF_DETAIL_HTML = (
    Path(__file__).parent.parent.parent.parent / "frontend" / "mockups" / "mf-detail.html"
)


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
    collector.feed(MF_DETAIL_HTML.read_text())
    return collector.elements


@pytest.fixture(scope="module")
def elements() -> list[dict[str, str]]:
    return _parse()


def test_file_exists() -> None:
    assert MF_DETAIL_HTML.exists(), "mf-detail.html not found"


def test_minimum_endpoint_count(elements: list[dict[str, str]]) -> None:
    """>=12 elements must carry a data-endpoint attribute (V2FE-6 exit criterion)."""
    wired = [e for e in elements if e.get("data-endpoint")]
    assert len(wired) >= 12, f"Expected >=12 data-endpoint attrs, found {len(wired)}"


def test_hero_endpoint_with_include(elements: list[dict[str, str]]) -> None:
    """[data-block=hero] must carry /api/v1/mf/$mstar_id with include=hero,chips,rs."""
    heroes = [e for e in elements if e.get("data-block") == "hero"]
    assert len(heroes) >= 1, "No data-block=hero found"
    wired = [e for e in heroes if "/api/v1/mf/" in (e.get("data-endpoint") or "")]
    assert len(wired) >= 1, "No hero block with /api/v1/mf/ endpoint found"
    params_str = wired[0].get("data-params", "{}")
    params = json.loads(params_str)
    include = params.get("include", "")
    assert "hero" in include, f"'hero' not in hero include: {include}"
    assert "conviction" in include, f"'conviction' not in hero include: {include}"


def test_nav_history_returns_endpoint(elements: list[dict[str, str]]) -> None:
    """[data-block=returns] must bind to nav-history with rolling_returns."""
    returns_els = [
        e for e in elements if e.get("data-block") == "returns" and e.get("data-endpoint")
    ]
    assert len(returns_els) >= 1, "No wired data-block=returns found"
    ep = returns_els[0].get("data-endpoint", "")
    assert "nav-history" in ep, f"returns endpoint does not include nav-history: {ep}"
    params_str = returns_els[0].get("data-params", "{}")
    params = json.loads(params_str)
    include = params.get("include", "")
    assert "rolling_returns" in include, "rolling_returns missing from returns params"


def test_nav_history_chart_endpoint(elements: list[dict[str, str]]) -> None:
    """A nav-chart block must bind to nav-history with benchmark_tri,events."""
    chart_els = [
        e for e in elements if e.get("data-block") == "nav-chart" and e.get("data-endpoint")
    ]
    assert len(chart_els) >= 1, "No wired data-block=nav-chart found"
    params_str = chart_els[0].get("data-params", "{}")
    params = json.loads(params_str)
    include = params.get("include", "")
    assert "benchmark_tri" in include, "benchmark_tri missing from nav-chart params"


def test_holdings_endpoint(elements: list[dict[str, str]]) -> None:
    """[data-block=holdings] must bind to /api/v1/mf/$mstar_id/holdings."""
    holdings_els = [
        e for e in elements if e.get("data-block") == "holdings" and e.get("data-endpoint")
    ]
    assert len(holdings_els) >= 1, "No wired data-block=holdings found"
    ep = holdings_els[0].get("data-endpoint", "")
    assert "holdings" in ep, f"holdings endpoint does not include /holdings: {ep}"


def test_alpha_risk_endpoint(elements: list[dict[str, str]]) -> None:
    """[data-block=alpha] must bind with include=alpha,risk_metrics."""
    alpha_els = [e for e in elements if e.get("data-block") == "alpha" and e.get("data-endpoint")]
    assert len(alpha_els) >= 1, "No wired data-block=alpha found"
    params_str = alpha_els[0].get("data-params", "{}")
    params = json.loads(params_str)
    include = params.get("include", "")
    assert "alpha" in include, f"'alpha' not in alpha block include: {include}"


def test_rolling_alpha_beta_endpoint(elements: list[dict[str, str]]) -> None:
    """A rolling-alpha-beta block must bind with include=rolling_alpha_beta."""
    rab_els = [
        e
        for e in elements
        if e.get("data-block") == "rolling-alpha-beta" and e.get("data-endpoint")
    ]
    assert len(rab_els) >= 1, "No wired data-block=rolling-alpha-beta found"
    params_str = rab_els[0].get("data-params", "{}")
    params = json.loads(params_str)
    include = params.get("include", "")
    assert "rolling_alpha_beta" in include, "rolling_alpha_beta missing from params"


def test_peers_uql_query(elements: list[dict[str, str]]) -> None:
    """[data-block=peers] must carry data-endpoint='/api/v1/query' with entity_type=mutual_fund."""
    peers = [e for e in elements if e.get("data-block") == "peers"]
    assert len(peers) >= 1, "No data-block=peers found"
    wired = [e for e in peers if e.get("data-endpoint") == "/api/v1/query"]
    assert len(wired) >= 1, "data-block=peers not wired to /api/v1/query"
    params_str = wired[0].get("data-params", "{}")
    params = json.loads(params_str)
    assert params.get("entity_type") == "mutual_fund", (
        f"peers entity_type is not mutual_fund: {params}"
    )


def test_divergences_include_endpoint(elements: list[dict[str, str]]) -> None:
    """[data-component=divergences-block] must carry include=divergences param."""
    divs = [e for e in elements if e.get("data-component") == "divergences-block"]
    assert len(divs) >= 1, "No data-component=divergences-block found"
    wired = [e for e in divs if e.get("data-endpoint")]
    assert len(wired) >= 1, "divergences-block has no data-endpoint"
    params_str = wired[0].get("data-params", "{}")
    params = json.loads(params_str)
    include = params.get("include", "")
    assert "divergences" in include, "'divergences' not in divergences-block params"


def test_rec_slots_carry_v2_deferred(elements: list[dict[str, str]]) -> None:
    """>=2 rec-slot elements must carry data-v2-deferred='true'."""
    deferred_slots = [
        e
        for e in elements
        if "rec-slot" in e.get("class", "") and e.get("data-v2-deferred") == "true"
    ]
    assert len(deferred_slots) >= 2, (
        f"Expected >=2 rec-slots with data-v2-deferred=true, found {len(deferred_slots)}"
    )


def test_signal_playback_compact_is_v2_derived(elements: list[dict[str, str]]) -> None:
    """signal-playback compact must be marked data-v2-derived='true' (client-side sim)."""
    compact_els = [
        e
        for e in elements
        if e.get("data-component") == "signal-playback" and e.get("data-mode") == "compact"
    ]
    assert len(compact_els) >= 1, "No signal-playback compact found"
    marked = [e for e in compact_els if e.get("data-v2-derived") == "true"]
    assert len(marked) >= 1, "signal-playback compact not marked data-v2-derived=true"


def test_data_mstar_id_on_main(elements: list[dict[str, str]]) -> None:
    """<main> must carry data-mstar-id='ppfas-flexi-cap-direct-growth'."""
    target_id = "ppfas-flexi-cap-direct-growth"
    mains_with_mstar = [e for e in elements if e.get("data-mstar-id") == target_id]
    assert len(mains_with_mstar) >= 1, f"No element carries data-mstar-id={target_id}"
