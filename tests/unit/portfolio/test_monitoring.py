"""Unit tests for portfolio monitoring service.

Tests:
- RS declining alert fires when portfolio RS drops > threshold
- RS declining alert does NOT fire when drop is within threshold
- LAGGING holding alert fires at exactly 28 consecutive trading days
- LAGGING holding alert does NOT fire at 27 consecutive trading days
- LAGGING holding alert does NOT fire at 29 non-consecutive days (gap breaks chain)
- Sector concentration alert fires when >40% in one sector
- Sector concentration no alert when all sectors <40%
- Non-trading day returns zero alerts
- Deterministic: same inputs → same outputs (run twice, compare)
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from backend.models.portfolio import (
    HoldingAnalysis,
    PortfolioLevelAnalysis,
)
from backend.models.portfolio_monitoring import (
    MonitoringAlert,
    MonitoringAlertType,
    MonitoringThresholds,
)
from backend.services.portfolio.monitoring import (
    consecutive_trading_days_lagging,
    generate_monitoring_alerts,
    is_trading_day,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_portfolio_level(
    weighted_rs: Decimal | None = Decimal("60"),
    sector_weights: dict[str, Decimal] | None = None,
) -> PortfolioLevelAnalysis:
    return PortfolioLevelAnalysis(
        total_value=Decimal("1000000"),
        holdings_count=3,
        mapped_count=3,
        unmapped_count=0,
        weighted_rs=weighted_rs,
        sector_weights=sector_weights or {},
    )


def _make_holding(
    holding_id: uuid.UUID | None = None,
    quadrant: str = "LEADING",
) -> HoldingAnalysis:
    return HoldingAnalysis(
        holding_id=holding_id or uuid.uuid4(),
        mstar_id="F00000XYZ",
        scheme_name="Test Fund",
        units=Decimal("100"),
    )


def _consecutive_trading_dates(n: int, start: datetime.date | None = None) -> list[datetime.date]:
    """Generate n consecutive trading day dates starting from start (default: 2025-01-02)."""
    if start is None:
        start = datetime.date(2025, 1, 2)  # Thursday
    result = []
    d = start
    while len(result) < n:
        if d.weekday() < 5:  # Mon-Fri
            result.append(d)
        d += datetime.timedelta(days=1)
    return result


# ---------------------------------------------------------------------------
# is_trading_day
# ---------------------------------------------------------------------------


def test_is_trading_day_weekday_returns_true() -> None:
    assert is_trading_day(datetime.date(2025, 1, 6)) is True  # Monday


def test_is_trading_day_saturday_returns_false() -> None:
    assert is_trading_day(datetime.date(2025, 1, 4)) is False  # Saturday


def test_is_trading_day_sunday_returns_false() -> None:
    assert is_trading_day(datetime.date(2025, 1, 5)) is False  # Sunday


# ---------------------------------------------------------------------------
# consecutive_trading_days_lagging
# ---------------------------------------------------------------------------


def test_consecutive_trading_days_lagging_empty_returns_zero() -> None:
    assert consecutive_trading_days_lagging([]) == 0


def test_consecutive_trading_days_lagging_27_consecutive() -> None:
    dates = _consecutive_trading_dates(27)
    assert consecutive_trading_days_lagging(dates) == 27


def test_consecutive_trading_days_lagging_28_consecutive() -> None:
    dates = _consecutive_trading_dates(28)
    assert consecutive_trading_days_lagging(dates) == 28


def test_consecutive_trading_days_lagging_29_non_consecutive_gap_breaks_chain() -> None:
    """29 dates with a gap should NOT produce run of 29."""
    # Build 15 consecutive, skip 5, build 14 more = 29 total but gap breaks chain
    first_run = _consecutive_trading_dates(15, start=datetime.date(2025, 1, 2))
    # Skip 1 week (5 trading days)
    second_start = first_run[-1] + datetime.timedelta(days=8)  # more than 1 trading day gap
    second_run = _consecutive_trading_dates(14, start=second_start)
    dates = first_run + second_run
    run = consecutive_trading_days_lagging(dates)
    # The trailing consecutive run is 14 (second run), not 29
    assert run == 14
    assert run < 28


def test_consecutive_trading_days_lagging_single_date_returns_one() -> None:
    assert consecutive_trading_days_lagging([datetime.date(2025, 1, 2)]) == 1


def test_consecutive_trading_days_lagging_unsorted_input_handled() -> None:
    """Function should sort input internally."""
    dates = _consecutive_trading_dates(10)
    shuffled = list(reversed(dates))
    assert consecutive_trading_days_lagging(shuffled) == 10


# ---------------------------------------------------------------------------
# RS declining alerts
# ---------------------------------------------------------------------------


def test_rs_declining_alert_fires_when_drop_exceeds_threshold() -> None:
    portfolio = _make_portfolio_level(weighted_rs=Decimal("50"))
    # RS dropped from 60 to 50 = 16.7% drop, threshold=5%
    rs_history = [Decimal("60"), Decimal("58"), Decimal("55"), Decimal("50")]
    data_as_of = datetime.date(2025, 1, 6)  # Monday

    alerts = generate_monitoring_alerts(
        holdings=[],
        portfolio_level=portfolio,
        rs_history=rs_history,
        flow_data={},
        lagging_history={},
        thresholds=None,
        data_as_of=data_as_of,
    )

    alert_types = [a.alert_type for a in alerts]
    assert MonitoringAlertType.RS_DECLINING in alert_types


def test_rs_declining_alert_does_not_fire_within_threshold() -> None:
    portfolio = _make_portfolio_level(weighted_rs=Decimal("58"))
    # Drop from 60 to 58 = 3.3%, threshold=5%
    rs_history = [Decimal("60"), Decimal("59"), Decimal("58")]
    data_as_of = datetime.date(2025, 1, 6)

    alerts = generate_monitoring_alerts(
        holdings=[],
        portfolio_level=portfolio,
        rs_history=rs_history,
        flow_data={},
        lagging_history={},
        thresholds=None,
        data_as_of=data_as_of,
    )

    alert_types = [a.alert_type for a in alerts]
    assert MonitoringAlertType.RS_DECLINING not in alert_types


def test_rs_declining_alert_does_not_fire_with_insufficient_history() -> None:
    portfolio = _make_portfolio_level(weighted_rs=Decimal("40"))
    # Only 1 data point — cannot determine trend
    rs_history = [Decimal("60")]
    data_as_of = datetime.date(2025, 1, 6)

    alerts = generate_monitoring_alerts(
        holdings=[],
        portfolio_level=portfolio,
        rs_history=rs_history,
        flow_data={},
        lagging_history={},
        thresholds=None,
        data_as_of=data_as_of,
    )

    alert_types = [a.alert_type for a in alerts]
    assert MonitoringAlertType.RS_DECLINING not in alert_types


# ---------------------------------------------------------------------------
# LAGGING holding alerts
# ---------------------------------------------------------------------------


def test_lagging_holding_alert_fires_at_exactly_28_days() -> None:
    holding_id = uuid.uuid4()
    holding = _make_holding(holding_id=holding_id)
    lagging_dates = _consecutive_trading_dates(28)
    lagging_history = {str(holding_id): lagging_dates}
    data_as_of = datetime.date(2025, 1, 6)

    alerts = generate_monitoring_alerts(
        holdings=[holding],
        portfolio_level=_make_portfolio_level(),
        rs_history=[Decimal("60"), Decimal("60")],
        flow_data={},
        lagging_history=lagging_history,
        thresholds=None,
        data_as_of=data_as_of,
    )

    lagging_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.LAGGING_HOLDING]
    assert len(lagging_alerts) == 1
    assert lagging_alerts[0].current_value == Decimal("28")


def test_lagging_holding_alert_does_not_fire_at_27_days() -> None:
    holding_id = uuid.uuid4()
    holding = _make_holding(holding_id=holding_id)
    lagging_dates = _consecutive_trading_dates(27)
    lagging_history = {str(holding_id): lagging_dates}
    data_as_of = datetime.date(2025, 1, 6)

    alerts = generate_monitoring_alerts(
        holdings=[holding],
        portfolio_level=_make_portfolio_level(),
        rs_history=[Decimal("60"), Decimal("60")],
        flow_data={},
        lagging_history=lagging_history,
        thresholds=None,
        data_as_of=data_as_of,
    )

    lagging_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.LAGGING_HOLDING]
    assert len(lagging_alerts) == 0


def test_lagging_holding_alert_does_not_fire_at_29_non_consecutive_days() -> None:
    """29 total days but with a gap — chain broken, no alert should fire."""
    holding_id = uuid.uuid4()
    holding = _make_holding(holding_id=holding_id)

    # 15 days + gap + 14 days = 29 total, but trailing run = 14
    first_run = _consecutive_trading_dates(15, start=datetime.date(2025, 1, 2))
    second_start = first_run[-1] + datetime.timedelta(days=8)
    second_run = _consecutive_trading_dates(14, start=second_start)
    lagging_dates = first_run + second_run

    lagging_history = {str(holding_id): lagging_dates}
    data_as_of = datetime.date(2025, 6, 2)  # Monday after second run

    alerts = generate_monitoring_alerts(
        holdings=[holding],
        portfolio_level=_make_portfolio_level(),
        rs_history=[Decimal("60"), Decimal("60")],
        flow_data={},
        lagging_history=lagging_history,
        thresholds=None,
        data_as_of=data_as_of,
    )

    lagging_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.LAGGING_HOLDING]
    assert len(lagging_alerts) == 0


# ---------------------------------------------------------------------------
# Sector concentration alerts
# ---------------------------------------------------------------------------


def test_sector_concentration_alert_fires_when_over_40_pct() -> None:
    sector_weights = {
        "Financial Services": Decimal("45"),
        "Technology": Decimal("30"),
        "Healthcare": Decimal("25"),
    }
    portfolio = _make_portfolio_level(sector_weights=sector_weights)
    data_as_of = datetime.date(2025, 1, 6)

    alerts = generate_monitoring_alerts(
        holdings=[],
        portfolio_level=portfolio,
        rs_history=[Decimal("60"), Decimal("60")],
        flow_data={},
        lagging_history={},
        thresholds=None,
        data_as_of=data_as_of,
    )

    concentration_alerts = [
        a for a in alerts if a.alert_type == MonitoringAlertType.SECTOR_CONCENTRATION
    ]
    assert len(concentration_alerts) == 1
    assert "Financial Services" in concentration_alerts[0].message


def test_sector_concentration_no_alert_when_all_sectors_below_40_pct() -> None:
    sector_weights = {
        "Financial Services": Decimal("35"),
        "Technology": Decimal("30"),
        "Healthcare": Decimal("35"),
    }
    portfolio = _make_portfolio_level(sector_weights=sector_weights)
    data_as_of = datetime.date(2025, 1, 6)

    alerts = generate_monitoring_alerts(
        holdings=[],
        portfolio_level=portfolio,
        rs_history=[Decimal("60"), Decimal("60")],
        flow_data={},
        lagging_history={},
        thresholds=None,
        data_as_of=data_as_of,
    )

    concentration_alerts = [
        a for a in alerts if a.alert_type == MonitoringAlertType.SECTOR_CONCENTRATION
    ]
    assert len(concentration_alerts) == 0


def test_sector_concentration_alert_at_exact_boundary_40_pct_no_alert() -> None:
    """Exactly at 40% should NOT fire (strictly >40 required)."""
    sector_weights = {"Financial Services": Decimal("40")}
    portfolio = _make_portfolio_level(sector_weights=sector_weights)
    data_as_of = datetime.date(2025, 1, 6)

    alerts = generate_monitoring_alerts(
        holdings=[],
        portfolio_level=portfolio,
        rs_history=[Decimal("60"), Decimal("60")],
        flow_data={},
        lagging_history={},
        thresholds=None,
        data_as_of=data_as_of,
    )

    concentration_alerts = [
        a for a in alerts if a.alert_type == MonitoringAlertType.SECTOR_CONCENTRATION
    ]
    assert len(concentration_alerts) == 0


# ---------------------------------------------------------------------------
# Non-trading day
# ---------------------------------------------------------------------------


def test_non_trading_day_returns_zero_alerts() -> None:
    """Saturday returns empty list regardless of what alert conditions exist."""
    # Setup conditions that WOULD trigger alerts on a trading day
    portfolio = _make_portfolio_level(
        weighted_rs=Decimal("40"),  # big RS drop
        sector_weights={"Financial Services": Decimal("70")},  # over concentration
    )
    rs_history = [Decimal("80"), Decimal("70"), Decimal("60"), Decimal("40")]
    data_as_of = datetime.date(2025, 1, 4)  # Saturday

    alerts = generate_monitoring_alerts(
        holdings=[],
        portfolio_level=portfolio,
        rs_history=rs_history,
        flow_data={"Large Cap": Decimal("-500000")},
        lagging_history={},
        thresholds=None,
        data_as_of=data_as_of,
    )

    assert alerts == []


def test_sunday_returns_zero_alerts() -> None:
    data_as_of = datetime.date(2025, 1, 5)  # Sunday
    alerts = generate_monitoring_alerts(
        holdings=[],
        portfolio_level=_make_portfolio_level(),
        rs_history=[Decimal("60"), Decimal("40")],
        flow_data={},
        lagging_history={},
        thresholds=None,
        data_as_of=data_as_of,
    )
    assert alerts == []


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_same_inputs_produce_same_alerts() -> None:
    holding_id = uuid.uuid4()
    holding = _make_holding(holding_id=holding_id)
    lagging_dates = _consecutive_trading_dates(28)
    lagging_history = {str(holding_id): lagging_dates}

    sector_weights = {"Financial Services": Decimal("50")}
    portfolio = _make_portfolio_level(
        weighted_rs=Decimal("45"),
        sector_weights=sector_weights,
    )
    rs_history = [Decimal("60"), Decimal("55"), Decimal("50"), Decimal("45")]
    data_as_of = datetime.date(2025, 1, 6)

    def _run() -> list[MonitoringAlert]:
        return generate_monitoring_alerts(
            holdings=[holding],
            portfolio_level=portfolio,
            rs_history=rs_history,
            flow_data={},
            lagging_history=lagging_history,
            thresholds=None,
            data_as_of=data_as_of,
        )

    run1 = _run()
    run2 = _run()

    assert len(run1) == len(run2)
    for a1, a2 in zip(run1, run2):
        assert a1.alert_type == a2.alert_type
        assert a1.severity == a2.severity
        assert a1.current_value == a2.current_value
        assert a1.threshold == a2.threshold


# ---------------------------------------------------------------------------
# Flow negative alerts
# ---------------------------------------------------------------------------


def test_flow_negative_alert_fires_for_negative_flow() -> None:
    data_as_of = datetime.date(2025, 1, 6)
    alerts = generate_monitoring_alerts(
        holdings=[],
        portfolio_level=_make_portfolio_level(),
        rs_history=[Decimal("60"), Decimal("60")],
        flow_data={"Large Cap": Decimal("-500000"), "Mid Cap": Decimal("200000")},
        lagging_history={},
        thresholds=None,
        data_as_of=data_as_of,
    )
    flow_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.FLOW_NEGATIVE]
    assert len(flow_alerts) == 1
    assert "Large Cap" in flow_alerts[0].message


def test_flow_positive_no_alert() -> None:
    data_as_of = datetime.date(2025, 1, 6)
    alerts = generate_monitoring_alerts(
        holdings=[],
        portfolio_level=_make_portfolio_level(),
        rs_history=[Decimal("60"), Decimal("60")],
        flow_data={"Large Cap": Decimal("500000")},
        lagging_history={},
        thresholds=None,
        data_as_of=data_as_of,
    )
    flow_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.FLOW_NEGATIVE]
    assert len(flow_alerts) == 0


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------


def test_custom_thresholds_respected() -> None:
    """Custom lagging_consecutive_days=5 triggers on 5 days."""
    holding_id = uuid.uuid4()
    holding = _make_holding(holding_id=holding_id)
    lagging_dates = _consecutive_trading_dates(5)
    lagging_history = {str(holding_id): lagging_dates}
    data_as_of = datetime.date(2025, 1, 6)

    custom = MonitoringThresholds(lagging_consecutive_days=5)
    alerts = generate_monitoring_alerts(
        holdings=[holding],
        portfolio_level=_make_portfolio_level(),
        rs_history=[Decimal("60"), Decimal("60")],
        flow_data={},
        lagging_history=lagging_history,
        thresholds=custom,
        data_as_of=data_as_of,
    )

    lagging_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.LAGGING_HOLDING]
    assert len(lagging_alerts) == 1
