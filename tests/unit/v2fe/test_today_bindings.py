"""Tests: V2FE-2 — today.html data-endpoint bindings."""

from html.parser import HTMLParser
from pathlib import Path

import pytest


TODAY_HTML = Path(__file__).parent.parent.parent.parent / "frontend" / "mockups" / "today.html"


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
    collector.feed(TODAY_HTML.read_text())
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
    assert TODAY_HTML.exists(), "today.html not found"


def test_regime_banner_has_endpoint(elements: list[dict[str, str]]) -> None:
    """data-component=regime-banner elements must carry data-endpoint."""
    banners = [e for e in elements if e.get("data-component") == "regime-banner"]
    assert len(banners) >= 1, "No regime-banner found"
    for b in banners:
        assert b.get("data-endpoint") == "/api/v1/stocks/breadth", (
            f"regime-banner missing correct endpoint: {b}"
        )


def test_signal_strip_has_endpoint(elements: list[dict[str, str]]) -> None:
    """data-component=signal-strip must carry data-endpoint."""
    strips = [e for e in elements if e.get("data-component") == "signal-strip"]
    assert len(strips) >= 1, "No signal-strip found"
    for s in strips:
        assert s.get("data-endpoint") == "/api/v1/stocks/breadth", (
            f"signal-strip missing endpoint: {s}"
        )


def test_sector_board_has_endpoint(elements: list[dict[str, str]]) -> None:
    """data-role=sector-board must carry data-endpoint."""
    boards = [e for e in elements if e.get("data-role") == "sector-board"]
    assert len(boards) >= 1, "No sector-board sentinel found"
    assert boards[0].get("data-endpoint") == "/api/v1/query/template", (
        f"sector-board missing endpoint: {boards[0]}"
    )


def test_movers_has_endpoint(elements: list[dict[str, str]]) -> None:
    """data-role=movers must carry data-endpoint."""
    movers = [e for e in elements if e.get("data-role") == "movers"]
    assert len(movers) >= 1, "No movers sentinel found"
    for m in movers:
        assert m.get("data-endpoint") == "/api/v1/query/template", f"movers missing endpoint: {m}"


def test_fund_strip_has_endpoint(elements: list[dict[str, str]]) -> None:
    """data-role=fund-strip must carry data-endpoint."""
    strips = [e for e in elements if e.get("data-role") == "fund-strip"]
    assert len(strips) >= 1, "No fund-strip sentinel found"
    assert strips[0].get("data-endpoint") == "/api/v1/query/template", (
        f"fund-strip missing endpoint: {strips[0]}"
    )


def test_divergences_block_has_endpoint(elements: list[dict[str, str]]) -> None:
    """data-component=divergences-block must carry correct data-endpoint."""
    divs = [e for e in elements if e.get("data-component") == "divergences-block"]
    assert len(divs) >= 1, "No divergences-block sentinel found"
    assert divs[0].get("data-endpoint") == "/api/v1/stocks/breadth/divergences", (
        f"divergences-block missing endpoint: {divs[0]}"
    )


def test_four_universal_benchmarks_has_endpoint(elements: list[dict[str, str]]) -> None:
    """data-component=four-universal-benchmarks must carry correct data-endpoint."""
    fubs = [e for e in elements if e.get("data-component") == "four-universal-benchmarks"]
    assert len(fubs) >= 1, "No four-universal-benchmarks sentinel found"
    assert fubs[0].get("data-endpoint") == "/api/v1/stocks/breadth", (
        f"four-universal-benchmarks missing endpoint: {fubs[0]}"
    )


def test_four_decision_card_deferred_not_endpoint(elements: list[dict[str, str]]) -> None:
    """four-decision-card must carry data-v2-deferred=true, NOT data-endpoint."""
    cards = [e for e in elements if e.get("data-component") == "four-decision-card"]
    assert len(cards) >= 4, f"Expected ≥4 four-decision-card, got {len(cards)}"
    for c in cards:
        assert "data-endpoint" not in c, f"four-decision-card should not have data-endpoint: {c}"
        assert c.get("data-v2-deferred") == "true", (
            f"four-decision-card missing data-v2-deferred: {c}"
        )


def test_minimum_eight_endpoints(elements: list[dict[str, str]]) -> None:
    """today.html must have ≥8 data-endpoint attributes (exit criterion)."""
    endpoints = [e for e in elements if "data-endpoint" in e]
    assert len(endpoints) >= 8, f"Expected ≥8 data-endpoint blocks, got {len(endpoints)}"


def test_events_overlay_has_endpoint(elements: list[dict[str, str]]) -> None:
    """Events overlay sentinel must carry correct endpoint and fixture."""
    events = [e for e in elements if e.get("data-component") == "events-overlay"]
    assert len(events) >= 1, "No events-overlay sentinel found"
    assert events[0].get("data-endpoint") == "/api/v1/global/events", (
        f"events-overlay missing endpoint: {events[0]}"
    )
    assert events[0].get("data-fixture") == "fixtures/events.json", (
        f"events-overlay missing fixture: {events[0]}"
    )


def test_data_health_sentinel_has_endpoint(elements: list[dict[str, str]]) -> None:
    """data-role=data-health must carry data-endpoint for system health."""
    health = [e for e in elements if e.get("data-role") == "data-health"]
    assert len(health) >= 1, "No data-health sentinel found"
    assert health[0].get("data-endpoint") == "/api/v1/system/data-health", (
        f"data-health missing endpoint: {health[0]}"
    )


def test_breadth_mini_sentinel_has_endpoint(elements: list[dict[str, str]]) -> None:
    """data-role=breadth-mini must carry data-endpoint for EOD breadth deltas."""
    minis = [e for e in elements if e.get("data-role") == "breadth-mini"]
    assert len(minis) >= 1, "No breadth-mini sentinel found"
    assert minis[0].get("data-endpoint") == "/api/v1/stocks/breadth", (
        f"breadth-mini missing endpoint: {minis[0]}"
    )
    assert minis[0].get("data-data-class") == "eod_breadth", (
        f"breadth-mini missing data-data-class: {minis[0]}"
    )


def test_regime_banner_count_at_least_two(elements: list[dict[str, str]]) -> None:
    """Both global and India regime banners must have data-component=regime-banner."""
    banners = [e for e in elements if e.get("data-component") == "regime-banner"]
    # 1 void sentinel in DP SLOTS + 2 structural banners (global + India) = ≥3
    assert len(banners) >= 2, (
        f"Expected ≥2 regime-banner elements (global + India), got {len(banners)}"
    )


def test_signal_strip_count_at_least_two(elements: list[dict[str, str]]) -> None:
    """Both global and India signal strips must have data-component=signal-strip."""
    strips = [e for e in elements if e.get("data-component") == "signal-strip"]
    assert len(strips) >= 2, (
        f"Expected ≥2 signal-strip elements (global + India), got {len(strips)}"
    )
