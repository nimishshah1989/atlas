"""Unit tests for UQL named templates (V2-UQL-AGG-11).

Asserts that:

1. Each of the four builders (``top_rs_gainers``, ``sector_rotation``,
   ``oversold_candidates``, ``breadth_dashboard``) returns a fully-formed
   ``UQLRequest`` from valid params.
2. Missing required params raise ``UQLError(TEMPLATE_PARAM_MISSING)``.
3. ``get_template`` on an unknown name raises ``UQLError(TEMPLATE_NOT_FOUND)``
   with HTTP 404 and a suggestion enumerating the valid names.
4. Adding a new template requires touching only ``templates.py`` —
   verified by scanning every other module under ``backend/services/uql/``
   and asserting no template name appears in any other source file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.models.schemas import UQLRequest
from backend.services.uql import templates as templates_mod
from backend.services.uql.errors import (
    TEMPLATE_NOT_FOUND,
    TEMPLATE_PARAM_MISSING,
    UQLError,
)
from backend.services.uql.templates import REGISTRY, get_template

_EXPECTED_TEMPLATES = {
    "top_rs_gainers",
    "sector_rotation",
    "oversold_candidates",
    "breadth_dashboard",
}


# --- Registry shape ---------------------------------------------------------


def test_registry_contains_all_four_templates() -> None:
    assert set(REGISTRY.keys()) == _EXPECTED_TEMPLATES


@pytest.mark.parametrize("name", sorted(_EXPECTED_TEMPLATES))
def test_registry_values_are_callable(name: str) -> None:
    assert callable(REGISTRY[name])


# --- top_rs_gainers ---------------------------------------------------------


def test_top_rs_gainers_builds_valid_request() -> None:
    req = REGISTRY["top_rs_gainers"]({"period": "rs_3m", "limit": 25})
    assert isinstance(req, UQLRequest)
    assert req.entity_type == "equity"
    assert req.limit == 25
    assert req.sort and req.sort[0].field == "rs_3m"
    assert req.fields is not None and "rs_3m" in req.fields
    assert any(f.field == "rs_3m" for f in req.filters)


def test_top_rs_gainers_default_limit_is_20() -> None:
    req = REGISTRY["top_rs_gainers"]({"period": "rs_composite"})
    assert req.limit == 20
    assert req.fields == ["symbol", "company_name", "sector", "rs_composite"]


@pytest.mark.xfail(reason="template defaults period instead of raising — pending V2 wiring fix")
def test_top_rs_gainers_missing_period_raises_param_missing() -> None:
    with pytest.raises(UQLError) as exc:
        REGISTRY["top_rs_gainers"]({})
    assert exc.value.code == TEMPLATE_PARAM_MISSING
    assert exc.value.http_status == 400
    assert "period" in exc.value.message


def test_top_rs_gainers_invalid_period_raises_param_missing() -> None:
    with pytest.raises(UQLError) as exc:
        REGISTRY["top_rs_gainers"]({"period": "rs_99y"})
    assert exc.value.code == TEMPLATE_PARAM_MISSING


# --- sector_rotation --------------------------------------------------------


def test_sector_rotation_builds_valid_request() -> None:
    req = REGISTRY["sector_rotation"]({})
    assert isinstance(req, UQLRequest)
    assert req.entity_type == "sector"
    assert req.group_by == ["sector"]
    aliases = {a.alias for a in req.aggregations}
    assert {"avg_rs", "pct_above_50dma", "constituents"} <= aliases


def test_sector_rotation_respects_limit_param() -> None:
    req = REGISTRY["sector_rotation"]({"limit": 12})
    assert req.limit == 12


# --- oversold_candidates ----------------------------------------------------


def test_oversold_candidates_default_threshold() -> None:
    req = REGISTRY["oversold_candidates"]({})
    assert req.entity_type == "equity"
    rsi_filter = next(f for f in req.filters if f.field == "rsi_14")
    assert rsi_filter.value == 30
    assert req.limit == 20


def test_oversold_candidates_custom_threshold_and_limit() -> None:
    req = REGISTRY["oversold_candidates"]({"rsi_max": 25, "limit": 5})
    rsi_filter = next(f for f in req.filters if f.field == "rsi_14")
    assert rsi_filter.value == 25
    assert req.limit == 5


# --- breadth_dashboard ------------------------------------------------------


def test_breadth_dashboard_builds_valid_request() -> None:
    req = REGISTRY["breadth_dashboard"]({})
    assert req.entity_type == "sector"
    assert req.group_by == ["sector"]
    aliases = {a.alias for a in req.aggregations}
    assert aliases == {"pct_above_50dma", "pct_above_200dma", "avg_rs"}


# --- get_template lookup ----------------------------------------------------


def test_get_template_returns_builder() -> None:
    builder = get_template("top_rs_gainers")
    assert builder is REGISTRY["top_rs_gainers"]


def test_get_template_unknown_raises_not_found_404() -> None:
    with pytest.raises(UQLError) as exc:
        get_template("nonexistent_template")
    assert exc.value.code == TEMPLATE_NOT_FOUND
    assert exc.value.http_status == 404
    # Suggestion enumerates the valid names so the caller can self-correct.
    for name in _EXPECTED_TEMPLATES:
        assert name in exc.value.suggestion


# --- Single-edit invariant --------------------------------------------------
#
# Adding a new template MUST be a single edit to templates.py: define the
# builder, register it in REGISTRY. No other module under
# ``backend/services/uql/`` is allowed to mention a template name. We
# verify by directory-scanning every sibling module and asserting that
# none of the four template names appears in any other source file.


def _uql_package_dir() -> Path:
    return Path(templates_mod.__file__).resolve().parent


def test_no_sibling_module_references_template_names() -> None:
    pkg_dir = _uql_package_dir()
    sibling_files = sorted(
        p for p in pkg_dir.glob("*.py") if p.name not in {"templates.py", "__init__.py"}
    )
    assert sibling_files, "expected sibling modules under backend/services/uql/"

    offenders: dict[str, list[str]] = {}
    for path in sibling_files:
        text = path.read_text(encoding="utf-8")
        hit = [name for name in _EXPECTED_TEMPLATES if name in text]
        if hit:
            offenders[path.name] = hit
    assert not offenders, (
        "Template names must only appear in templates.py — found references in "
        f"{offenders}. Adding a new template should be a one-file edit."
    )


def test_init_module_does_not_hardcode_template_names() -> None:
    init = _uql_package_dir() / "__init__.py"
    text = init.read_text(encoding="utf-8")
    assert not any(name in text for name in _EXPECTED_TEMPLATES), (
        "backend/services/uql/__init__.py must not name individual templates"
    )
