"""Tests: V2FE-5 — stock-detail.html data-endpoint bindings (hub-and-spoke equity terminal)."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import pytest


STOCK_DETAIL_HTML = (
    Path(__file__).parent.parent.parent.parent / "frontend" / "mockups" / "stock-detail.html"
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
    collector.feed(STOCK_DETAIL_HTML.read_text())
    return collector.elements


@pytest.fixture(scope="module")
def elements() -> list[dict[str, str]]:
    return _parse()


# ── Sanity ──────────────────────────────────────────────────────────────────────


def test_file_exists() -> None:
    assert STOCK_DETAIL_HTML.exists(), "stock-detail.html not found"


def test_minimum_endpoint_count(elements: list[dict[str, str]]) -> None:
    """≥12 elements must carry a data-endpoint attribute (V2FE-5 exit criterion)."""
    wired = [e for e in elements if e.get("data-endpoint")]
    assert len(wired) >= 12, f"Expected ≥12 data-endpoint attrs, found {len(wired)}"


# ── Hero block ──────────────────────────────────────────────────────────────────


def test_hero_has_stocks_endpoint(elements: list[dict[str, str]]) -> None:
    """[data-block=hero] must have data-endpoint pointing to /api/v1/stocks/${symbol}."""
    heroes = [e for e in elements if e.get("data-block") == "hero"]
    assert len(heroes) >= 1, "No data-block=hero found"
    wired = [e for e in heroes if e.get("data-endpoint") == "/api/v1/stocks/${symbol}"]
    assert len(wired) >= 1, (
        f"data-block=hero does not carry /api/v1/stocks/${{symbol}}; "
        f"found: {[e.get('data-endpoint') for e in heroes]}"
    )


def test_hero_params_include_price_and_chips(elements: list[dict[str, str]]) -> None:
    """Hero data-params must include 'price' and 'chips' in the include field."""
    hero_wired = [
        e
        for e in elements
        if e.get("data-block") == "hero" and e.get("data-endpoint") == "/api/v1/stocks/${symbol}"
    ]
    assert len(hero_wired) >= 1, "No wired hero block found"
    params_str = hero_wired[0].get("data-params", "")
    params = json.loads(params_str)
    include = params.get("include", "")
    assert "price" in include, f"'price' not in hero include: {include}"
    assert "chips" in include, f"'chips' not in hero include: {include}"


# ── Chart-data endpoint ─────────────────────────────────────────────────────────


def test_chart_data_endpoint_present(elements: list[dict[str, str]]) -> None:
    """At least one element must bind to /api/v1/stocks/${symbol}/chart-data."""
    chart_els = [
        e for e in elements if e.get("data-endpoint") == "/api/v1/stocks/${symbol}/chart-data"
    ]
    assert len(chart_els) >= 1, (
        "No element carries data-endpoint=/api/v1/stocks/${symbol}/chart-data"
    )


def test_chart_data_overlays_in_params(elements: list[dict[str, str]]) -> None:
    """Chart-data element must have overlays in data-params (50dma,200dma or rsi14,macd)."""
    chart_els = [
        e
        for e in elements
        if e.get("data-endpoint") == "/api/v1/stocks/${symbol}/chart-data" and e.get("data-params")
    ]
    assert len(chart_els) >= 1, "No chart-data element with data-params found"
    params_str = chart_els[0].get("data-params", "")
    params = json.loads(params_str)
    assert "overlays" in params, f"'overlays' missing from chart-data params: {params}"


# ── RS history endpoint ─────────────────────────────────────────────────────────


def test_rs_history_endpoint_present(elements: list[dict[str, str]]) -> None:
    """At least one element must bind to /api/v1/stocks/${symbol}/rs-history."""
    rs_els = [
        e for e in elements if e.get("data-endpoint") == "/api/v1/stocks/${symbol}/rs-history"
    ]
    assert len(rs_els) >= 1, "No element carries data-endpoint=/api/v1/stocks/${symbol}/rs-history"


# ── Peers UQL query ─────────────────────────────────────────────────────────────


def test_peers_block_has_query_endpoint(elements: list[dict[str, str]]) -> None:
    """[data-block=peers] must carry data-endpoint='/api/v1/query'."""
    peers = [e for e in elements if e.get("data-block") == "peers"]
    assert len(peers) >= 1, "No data-block=peers found"
    wired = [e for e in peers if e.get("data-endpoint") == "/api/v1/query"]
    assert len(wired) >= 1, (
        f"data-block=peers does not carry /api/v1/query; "
        f"found: {[e.get('data-endpoint') for e in peers]}"
    )


def test_peers_params_entity_type_equity(elements: list[dict[str, str]]) -> None:
    """Peers data-params must specify entity_type='equity' (V2FE-5 gate criterion)."""
    peers_wired = [
        e
        for e in elements
        if e.get("data-block") == "peers" and e.get("data-endpoint") == "/api/v1/query"
    ]
    assert len(peers_wired) >= 1, "No wired peers block found"
    params_str = peers_wired[0].get("data-params", "")
    params = json.loads(params_str)
    assert params.get("entity_type") == "equity", (
        f"peers entity_type is not 'equity': {params.get('entity_type')}"
    )


# ── Divergences include ─────────────────────────────────────────────────────────


def test_divergences_include_endpoint(elements: list[dict[str, str]]) -> None:
    """[data-component=divergences-block] must carry include=divergences param."""
    divs = [e for e in elements if e.get("data-component") == "divergences-block"]
    assert len(divs) >= 1, "No data-component=divergences-block found"
    wired = [e for e in divs if e.get("data-endpoint")]
    assert len(wired) >= 1, "divergences-block has no data-endpoint"
    params_str = wired[0].get("data-params", "{}")
    params = json.loads(params_str)
    assert "divergences" in params.get("include", ""), (
        f"'divergences' not in divergences-block params include: {params}"
    )


# ── Fundamentals include ────────────────────────────────────────────────────────


def test_fundamentals_block_endpoint(elements: list[dict[str, str]]) -> None:
    """A fundamentals block must carry data-endpoint with include=fundamentals."""
    fundas = [
        e for e in elements if e.get("data-block") == "fundamentals" and e.get("data-endpoint")
    ]
    assert len(fundas) >= 1, "No data-block=fundamentals with data-endpoint found"
    params_str = fundas[0].get("data-params", "{}")
    params = json.loads(params_str)
    assert "fundamentals" in params.get("include", ""), (
        f"'fundamentals' not in fundamentals block include: {params}"
    )


# ── Signal-history include ──────────────────────────────────────────────────────


def test_signal_history_include_endpoint(elements: list[dict[str, str]]) -> None:
    """[data-component=signal-history-table] must carry include=signal_history param."""
    sh_els = [e for e in elements if e.get("data-component") == "signal-history-table"]
    assert len(sh_els) >= 1, "No data-component=signal-history-table found"
    wired = [e for e in sh_els if e.get("data-endpoint")]
    assert len(wired) >= 1, "signal-history-table has no data-endpoint"
    params_str = wired[0].get("data-params", "{}")
    params = json.loads(params_str)
    assert "signal_history" in params.get("include", ""), (
        f"'signal_history' not in signal-history-table params: {params}"
    )


# ── Insider endpoint ────────────────────────────────────────────────────────────


def test_insider_endpoint_present(elements: list[dict[str, str]]) -> None:
    """An insider block must bind to /api/v1/insider/${symbol}."""
    insider_els = [e for e in elements if e.get("data-endpoint") == "/api/v1/insider/${symbol}"]
    assert len(insider_els) >= 1, "No element carries data-endpoint=/api/v1/insider/${symbol}"


# ── Whitelist / deferred markers ────────────────────────────────────────────────


def test_rec_slots_carry_v2_deferred(elements: list[dict[str, str]]) -> None:
    """≥3 rec-slot elements must carry data-v2-deferred='true'."""
    deferred_slots = [
        e
        for e in elements
        if "rec-slot" in e.get("class", "") and e.get("data-v2-deferred") == "true"
    ]
    assert len(deferred_slots) >= 3, (
        f"Expected ≥3 rec-slots with data-v2-deferred=true, found {len(deferred_slots)}"
    )


def test_simulate_this_links_to_lab_with_symbol(elements: list[dict[str, str]]) -> None:
    """[data-action=simulate-this] must link to lab.html?symbol=... not a backend route."""
    simulate_els = [e for e in elements if e.get("data-action") == "simulate-this"]
    assert len(simulate_els) >= 1, "No data-action=simulate-this element found"
    href = simulate_els[0].get("href", "")
    assert href.startswith("lab.html"), (
        f"simulate-this href should start with 'lab.html', got: {href}"
    )
    assert "symbol=" in href, f"simulate-this href missing ?symbol= param: {href}"


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


def test_data_symbol_on_main(elements: list[dict[str, str]]) -> None:
    """<main> must carry data-symbol='HDFCBANK' for loader symbol resolution."""
    mains_with_symbol = [e for e in elements if e.get("data-symbol") == "HDFCBANK"]
    assert len(mains_with_symbol) >= 1, (
        "No element carries data-symbol=HDFCBANK (expected on <main>)"
    )
