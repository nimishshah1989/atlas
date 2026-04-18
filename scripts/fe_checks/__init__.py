"""
fe_checks — Registry and dispatcher for frontend criteria check types.

Each check type handler takes a spec dict and returns (passed: bool, evidence: str).
Handlers never raise — exceptions are caught and returned as (False, error_message).
"""

from __future__ import annotations

from typing import Any, Callable

from .grep_checks import grep_forbid, grep_require, kill_list, i18n_indian
from .file_checks import file_exists, url_reachable, link_integrity
from .dom_checks import dom_required, dom_forbidden, attr_required, attr_enum, attr_numeric_range
from .html_checks import html5_valid, design_tokens_only, chart_contract, methodology_footer
from .playwright_checks import (
    playwright_screenshot,
    playwright_a11y,
    playwright_no_horizontal_scroll,
    playwright_tap_target,
)
from .fixture_checks import (
    fixture_schema,
    fixture_parity,
    fixture_field_required,
    fixture_numeric_range,
    fixture_array_length,
    fixture_enum,
    fixture_endpoint_reference,
)
from .rule_checks import rule_coverage

Handler = Callable[[dict[str, Any]], tuple[bool, str]]

CHECK_TYPES: dict[str, Handler] = {
    # Static / grep
    "grep_forbid": grep_forbid,
    "grep_require": grep_require,
    "kill_list": kill_list,
    "i18n_indian": i18n_indian,
    # File system
    "file_exists": file_exists,
    "url_reachable": url_reachable,
    "link_integrity": link_integrity,
    # DOM / selector
    "dom_required": dom_required,
    "dom_forbidden": dom_forbidden,
    "attr_required": attr_required,
    "attr_enum": attr_enum,
    "attr_numeric_range": attr_numeric_range,
    # HTML / accessibility
    "html5_valid": html5_valid,
    "design_tokens_only": design_tokens_only,
    "chart_contract": chart_contract,
    "methodology_footer": methodology_footer,
    # Playwright
    "playwright_screenshot": playwright_screenshot,
    "playwright_a11y": playwright_a11y,
    "playwright_no_horizontal_scroll": playwright_no_horizontal_scroll,
    "playwright_tap_target": playwright_tap_target,
    # Fixture / JSON
    "fixture_schema": fixture_schema,
    "fixture_parity": fixture_parity,
    "fixture_field_required": fixture_field_required,
    "fixture_numeric_range": fixture_numeric_range,
    "fixture_array_length": fixture_array_length,
    "fixture_enum": fixture_enum,
    "fixture_endpoint_reference": fixture_endpoint_reference,
    # Rule engine
    "rule_coverage": rule_coverage,
}


def dispatch(check_spec: dict[str, Any]) -> tuple[bool, str]:
    """Look up check type, call handler, return (passed, evidence).

    Never raises. Unknown types return (False, evidence).
    """
    check_type = check_spec.get("type", "")
    handler = CHECK_TYPES.get(check_type)
    if handler is None:
        return False, f"unknown check type: {check_type!r}"
    try:
        return handler(check_spec)
    except Exception as exc:  # noqa: BLE001
        return False, f"{check_type} handler crashed: {str(exc)[:200]}"


def list_types() -> list[str]:
    """Return sorted list of registered check type names."""
    return sorted(CHECK_TYPES.keys())


def validate_types(criteria: list[dict[str, Any]]) -> list[str]:
    """Return list of unknown check types found in criteria.

    Used for preflight validation — if any unknown types are returned,
    the runner should abort before running any checks.
    """
    known = set(CHECK_TYPES.keys())
    unknown: list[str] = []
    for c in criteria:
        check = c.get("check", {})
        t = check.get("type", "")
        if t and t not in known and t not in unknown:
            unknown.append(t)
    return unknown
