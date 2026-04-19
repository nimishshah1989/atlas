"""Tests: V2FE-4 — breadth.html data-endpoint bindings."""

from html.parser import HTMLParser
from pathlib import Path

import pytest


BREADTH_HTML = Path(__file__).parent.parent.parent.parent / "frontend" / "mockups" / "breadth.html"


class AttrCollector(HTMLParser):
    """Collect all tag attribute dicts that carry at least one data-* attribute."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = {k: (v or "") for k, v in attrs}
        if any(k.startswith("data-") for k in d):
            self.elements.append(d)


def _parse() -> list[dict[str, str]]:
    collector = AttrCollector()
    collector.feed(BREADTH_HTML.read_text())
    return collector.elements


@pytest.fixture(scope="module")
def elements() -> list[dict[str, str]]:
    return _parse()


def test_file_exists() -> None:
    assert BREADTH_HTML.exists(), "breadth.html not found"


def test_oscillator_block_has_endpoint(elements: list[dict[str, str]]) -> None:
    """At least one data-block=oscillator must carry data-endpoint for breadth."""
    _ep = "/api/v1/stocks/breadth"
    osc_with_endpoint = [
        e for e in elements if e.get("data-block") == "oscillator" and e.get("data-endpoint") == _ep
    ]
    assert len(osc_with_endpoint) >= 1, (
        "No data-block=oscillator element carries data-endpoint=/api/v1/stocks/breadth"
    )


def test_signal_history_has_zone_events_endpoint(elements: list[dict[str, str]]) -> None:
    """data-block=signal-history must carry data-endpoint=/api/v1/stocks/breadth/zone-events."""
    histories = [e for e in elements if e.get("data-block") == "signal-history"]
    assert len(histories) >= 1, "No data-block=signal-history element found"
    wired = [e for e in histories if e.get("data-endpoint") == "/api/v1/stocks/breadth/zone-events"]
    assert len(wired) >= 1, (
        f"data-block=signal-history does not carry /api/v1/stocks/breadth/zone-events; "
        f"found: {[e.get('data-endpoint') for e in histories]}"
    )


def test_divergences_block_has_endpoint(elements: list[dict[str, str]]) -> None:
    """data-component=divergences-block must carry the divergences endpoint."""
    divs = [e for e in elements if e.get("data-component") == "divergences-block"]
    assert len(divs) >= 1, "No data-component=divergences-block element found"
    wired = [e for e in divs if e.get("data-endpoint") == "/api/v1/stocks/breadth/divergences"]
    assert len(wired) >= 1, (
        f"divergences-block missing /api/v1/stocks/breadth/divergences; "
        f"found: {[e.get('data-endpoint') for e in divs]}"
    )


def test_conviction_series_include_present(elements: list[dict[str, str]]) -> None:
    """At least one breadth endpoint element must have conviction_series in data-params."""
    _ep = "/api/v1/stocks/breadth"
    breadth_blocks = [
        e
        for e in elements
        if e.get("data-endpoint") == _ep and "conviction_series" in (e.get("data-params") or "")
    ]
    assert len(breadth_blocks) >= 1, (
        "No breadth endpoint element contains conviction_series in data-params"
    )


def test_hero_card_has_endpoint(elements: list[dict[str, str]]) -> None:
    """At least one .hero-card element must carry data-endpoint=/api/v1/stocks/breadth."""
    hero_with_endpoint = [
        e
        for e in elements
        if "hero-card" in (e.get("class") or "")
        and e.get("data-endpoint") == "/api/v1/stocks/breadth"
    ]
    assert len(hero_with_endpoint) >= 1, (
        "No hero-card element carries data-endpoint=/api/v1/stocks/breadth"
    )


def test_methodology_footer_has_data_health_endpoint(elements: list[dict[str, str]]) -> None:
    """footer[data-role=methodology] must carry data-endpoint=/api/v1/system/data-health."""
    footers = [e for e in elements if e.get("data-role") == "methodology"]
    assert len(footers) >= 1, "No data-role=methodology element found"
    wired = [e for e in footers if e.get("data-endpoint") == "/api/v1/system/data-health"]
    assert len(wired) >= 1, (
        f"methodology footer missing /api/v1/system/data-health; "
        f"found: {[e.get('data-endpoint') for e in footers]}"
    )


def test_regime_banner_has_endpoint(elements: list[dict[str, str]]) -> None:
    """At least one data-component=regime-banner must carry data-endpoint."""
    banners_with_endpoint = [
        e
        for e in elements
        if e.get("data-component") == "regime-banner"
        and e.get("data-endpoint") == "/api/v1/stocks/breadth"
    ]
    assert len(banners_with_endpoint) >= 1, (
        "No data-component=regime-banner carries data-endpoint=/api/v1/stocks/breadth"
    )


def test_signal_history_params_reference_zone_events(elements: list[dict[str, str]]) -> None:
    """signal-history endpoint must be zone-events (endpoint OR params verification)."""
    histories = [e for e in elements if e.get("data-block") == "signal-history"]
    assert len(histories) >= 1, "No data-block=signal-history found"
    # The endpoint itself IS /api/v1/stocks/breadth/zone-events — already asserted above.
    # Here we verify the data-params includes universe param (belt-and-suspenders).
    wired = [
        e
        for e in histories
        if e.get("data-endpoint") == "/api/v1/stocks/breadth/zone-events"
        and "universe" in (e.get("data-params") or "")
    ]
    assert len(wired) >= 1, (
        "signal-history block at zone-events endpoint must include universe param"
    )


def test_minimum_nine_endpoints(elements: list[dict[str, str]]) -> None:
    """breadth.html must have ≥9 data-endpoint attributes (exit criterion)."""
    endpoints = [e for e in elements if "data-endpoint" in e]
    assert len(endpoints) >= 9, f"Expected ≥9 data-endpoint blocks, got {len(endpoints)}"


def test_signal_playback_has_no_endpoint(elements: list[dict[str, str]]) -> None:
    """signal-playback must NOT have data-endpoint (it is a client-side simulator)."""
    playback = [
        e
        for e in elements
        if e.get("id") == "signal-playback" or e.get("data-block") == "signal-playback"
    ]
    assert len(playback) >= 1, "No signal-playback element found"
    with_endpoint = [e for e in playback if "data-endpoint" in e]
    assert len(with_endpoint) == 0, (
        f"signal-playback must NOT have data-endpoint (client-side only): {with_endpoint}"
    )
