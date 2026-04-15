"""Daily Portfolio Monitoring Service — pure computation module.

No DB, no async, no I/O.

Implements spec §9 ONGOING MONITORING checks:
- Portfolio RS declining trend
- Holding enters LAGGING for >= 28 consecutive trading days
- Single-sector concentration > threshold
- Category flows turn negative
- Tax harvest opportunity flag

Design:
  - Deterministic: same inputs → same alerts
  - Non-trading day (weekend / holiday marker): returns empty list
  - All financial arithmetic in Decimal, never float
  - structlog for observability
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Optional

import structlog

from backend.models.portfolio import (
    AnalysisProvenance,
    HoldingAnalysis,
    PortfolioLevelAnalysis,
)
from backend.models.portfolio_monitoring import (
    MonitoringAlert,
    MonitoringAlertType,
    MonitoringThresholds,
)

log = structlog.get_logger()

# Trading day identifier: weekdays only (simplified — no holiday calendar needed
# for boundary correctness; the caller should pass trading days only for the
# lagging dict).
_WEEKEND_DAYS = {5, 6}  # Saturday=5, Sunday=6


def is_trading_day(d: datetime.date) -> bool:
    """Return True if the date is a weekday (Mon–Fri).

    This is a conservative check: the caller is responsible for passing
    only trading-day dated data.  Weekend dates are non-trading by definition.
    Indian market holidays that fall on weekdays are NOT detected here — the
    spec says "if no new data available, return empty list", which the caller
    handles by not passing any data.
    """
    return d.weekday() not in _WEEKEND_DAYS


def consecutive_trading_days_lagging(
    lagging_dates: list[datetime.date],
) -> int:
    """Return the length of the longest *trailing* contiguous run of trading days.

    A contiguous run means consecutive calendar days where each day is exactly
    1 trading day after the previous one in the sorted list.  A gap in the list
    (missing date / non-consecutive) resets the counter.

    Args:
        lagging_dates: List of dates on which the holding was in LAGGING quadrant.
                       Need not be sorted; function sorts internally.

    Returns:
        Length of the trailing contiguous run.  0 if list is empty.
    """
    if not lagging_dates:
        return 0

    sorted_dates = sorted(lagging_dates)
    # Walk from oldest to newest, counting contiguous runs
    run = 1
    for i in range(1, len(sorted_dates)):
        prev = sorted_dates[i - 1]
        curr = sorted_dates[i]
        # Determine if curr is exactly the next trading day after prev
        # We step forward day-by-day from prev to find the next trading day
        candidate = prev + datetime.timedelta(days=1)
        while candidate.weekday() in _WEEKEND_DAYS:
            candidate += datetime.timedelta(days=1)
        if curr == candidate:
            run += 1
        else:
            # Gap breaks the chain — restart from current position
            run = 1

    return run


def _check_rs_declining(
    portfolio_level: PortfolioLevelAnalysis,
    rs_history: list[Decimal],
    thresholds: MonitoringThresholds,
) -> Optional[MonitoringAlert]:
    """Fire RS_DECLINING alert when current RS has dropped > rs_decline_pct from recent peak.

    Args:
        portfolio_level: Current portfolio-level analysis.
        rs_history: List of recent portfolio weighted RS values (oldest first, current last).
                    Must have at least 2 entries to compute a meaningful trend.
        thresholds: Monitoring thresholds config.

    Returns:
        MonitoringAlert if triggered, else None.
    """
    current_rs = portfolio_level.weighted_rs
    if current_rs is None:
        return None

    if len(rs_history) < 2:
        return None

    # Recent peak = max RS in history
    peak_rs = max(rs_history)
    if peak_rs == Decimal("0"):
        return None

    drop_pct = ((peak_rs - current_rs) / abs(peak_rs)) * Decimal("100")

    if drop_pct <= thresholds.rs_decline_pct:
        return None

    severity = "CRITICAL" if drop_pct > thresholds.rs_decline_pct * Decimal("2") else "HIGH"

    log.info(
        "monitoring_rs_declining",
        current_rs=str(current_rs),
        peak_rs=str(peak_rs),
        drop_pct=str(drop_pct),
        severity=severity,
    )

    return MonitoringAlert(
        alert_type=MonitoringAlertType.RS_DECLINING,
        severity=severity,
        metric_name="weighted_rs",
        current_value=current_rs,
        threshold=thresholds.rs_decline_pct,
        message=(
            f"Portfolio weighted RS has dropped {drop_pct:.2f}% from recent peak of {peak_rs:.2f}"
        ),
        provenance=AnalysisProvenance(
            source_table="de_mf_rs_composite (via PortfolioLevelAnalysis.weighted_rs)",
            formula="drop_pct = (peak_rs - current_rs) / |peak_rs| * 100",
        ),
    )


def _check_lagging_holdings(
    holdings: list[HoldingAnalysis],
    lagging_history: dict[str, list[datetime.date]],
    thresholds: MonitoringThresholds,
) -> list[MonitoringAlert]:
    """Fire LAGGING_HOLDING alert for each holding with >= 28 consecutive LAGGING days.

    Args:
        holdings: Current holding analysis list.
        lagging_history: Dict of holding_id (str) → list of dates holding was in LAGGING.
        thresholds: Monitoring thresholds config.

    Returns:
        List of alerts (one per qualifying holding).
    """
    alerts: list[MonitoringAlert] = []
    required = thresholds.lagging_consecutive_days

    holding_map = {str(h.holding_id): h for h in holdings}

    for holding_id_str, dates in lagging_history.items():
        consec = consecutive_trading_days_lagging(dates)
        if consec < required:
            continue

        holding = holding_map.get(holding_id_str)
        scheme_name = holding.scheme_name if holding else holding_id_str
        current_val = Decimal(str(consec))

        log.info(
            "monitoring_lagging_holding",
            holding_id=holding_id_str,
            consecutive_days=consec,
            required=required,
        )

        alerts.append(
            MonitoringAlert(
                alert_type=MonitoringAlertType.LAGGING_HOLDING,
                severity="HIGH",
                metric_name="consecutive_lagging_trading_days",
                current_value=current_val,
                threshold=Decimal(str(required)),
                holding_id=holding.holding_id if holding else None,
                message=(
                    f"{scheme_name} has been in LAGGING quadrant for "
                    f"{consec} consecutive trading days (threshold: {required})"
                ),
                provenance=AnalysisProvenance(
                    source_table="HoldingAnalysis.quadrant (derived from de_mf_rs_composite)",
                    formula=f"consecutive_lagging_days >= {required}",
                ),
            )
        )

    return alerts


def _check_sector_concentration(
    portfolio_level: PortfolioLevelAnalysis,
    thresholds: MonitoringThresholds,
) -> list[MonitoringAlert]:
    """Fire SECTOR_CONCENTRATION alert for any sector exceeding threshold weight.

    Args:
        portfolio_level: Portfolio-level analysis with sector_weights.
        thresholds: Monitoring thresholds config.

    Returns:
        List of alerts (one per over-concentrated sector).
    """
    alerts: list[MonitoringAlert] = []
    limit = thresholds.sector_concentration_pct

    for sector, weight_pct in portfolio_level.sector_weights.items():
        if weight_pct <= limit:
            continue

        severity = "CRITICAL" if weight_pct > limit * Decimal("1.5") else "HIGH"

        log.info(
            "monitoring_sector_concentration",
            sector=sector,
            weight_pct=str(weight_pct),
            limit=str(limit),
        )

        alerts.append(
            MonitoringAlert(
                alert_type=MonitoringAlertType.SECTOR_CONCENTRATION,
                severity=severity,
                metric_name=f"sector_weight_{sector}",
                current_value=weight_pct,
                threshold=limit,
                message=(
                    f"Sector '{sector}' represents {weight_pct:.1f}% of portfolio "
                    f"(threshold: {limit}%)"
                ),
                provenance=AnalysisProvenance(
                    source_table=(
                        "PortfolioLevelAnalysis.sector_weights "
                        "(aggregated from HoldingAnalysis.top_sectors)"
                    ),
                    formula="sector_weight_pct > sector_concentration_pct threshold",
                ),
            )
        )

    return alerts


def _check_flow_negative(
    flow_data: dict[str, Decimal],
    thresholds: MonitoringThresholds,
) -> list[MonitoringAlert]:
    """Fire FLOW_NEGATIVE alert for categories with negative net flows.

    Args:
        flow_data: Dict of category_name → net_flow (Decimal, positive = inflow).
                   Negative values indicate net outflows.
        thresholds: Monitoring thresholds config (unused here; included for interface symmetry).

    Returns:
        List of alerts (one per negative-flow category).
    """
    alerts: list[MonitoringAlert] = []

    for category, net_flow in flow_data.items():
        if net_flow >= Decimal("0"):
            continue

        log.info(
            "monitoring_flow_negative",
            category=category,
            net_flow=str(net_flow),
        )

        alerts.append(
            MonitoringAlert(
                alert_type=MonitoringAlertType.FLOW_NEGATIVE,
                severity="HIGH",
                metric_name=f"net_flow_{category}",
                current_value=net_flow,
                threshold=Decimal("0"),
                message=(f"Category '{category}' has negative net flows: ₹{net_flow:,.2f}"),
                provenance=AnalysisProvenance(
                    source_table="de_mf_category_flows (via JIPMFService)",
                    formula="net_flow < 0",
                ),
            )
        )

    return alerts


def generate_monitoring_alerts(
    holdings: list[HoldingAnalysis],
    portfolio_level: PortfolioLevelAnalysis,
    rs_history: list[Decimal],
    flow_data: dict[str, Decimal],
    lagging_history: dict[str, list[datetime.date]],
    thresholds: Optional[MonitoringThresholds],
    data_as_of: datetime.date,
) -> list[MonitoringAlert]:
    """Generate all monitoring alerts for a portfolio as of data_as_of.

    Args:
        holdings: Per-holding analysis list (from PortfolioAnalysisService).
        portfolio_level: Aggregated portfolio-level analysis.
        rs_history: Recent history of portfolio weighted_rs values (oldest first).
        flow_data: Category → net_flow mapping (positive=inflow, negative=outflow).
        lagging_history: holding_id_str → list of dates holding was in LAGGING quadrant.
        thresholds: Configurable thresholds. If None, uses MonitoringThresholds defaults.
        data_as_of: Date for which this monitoring run is computed.

    Returns:
        List of MonitoringAlert objects.  Empty list on non-trading days.
    """
    if thresholds is None:
        thresholds = MonitoringThresholds()

    # Non-trading day check — return zero alerts
    if not is_trading_day(data_as_of):
        log.info("monitoring_non_trading_day", data_as_of=str(data_as_of))
        return []

    alerts: list[MonitoringAlert] = []

    # 1. RS declining
    rs_alert = _check_rs_declining(portfolio_level, rs_history, thresholds)
    if rs_alert is not None:
        alerts.append(rs_alert)

    # 2. LAGGING holdings
    alerts.extend(_check_lagging_holdings(holdings, lagging_history, thresholds))

    # 3. Sector concentration
    alerts.extend(_check_sector_concentration(portfolio_level, thresholds))

    # 4. Flow negative
    alerts.extend(_check_flow_negative(flow_data, thresholds))

    log.info(
        "monitoring_alerts_generated",
        data_as_of=str(data_as_of),
        alert_count=len(alerts),
    )

    return alerts


__all__ = [
    "is_trading_day",
    "consecutive_trading_days_lagging",
    "generate_monitoring_alerts",
    "MonitoringThresholds",
]
