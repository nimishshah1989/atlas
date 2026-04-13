"""Product dimension — V1 completion criteria from docs/specs/v1-criteria.yaml.

Each criterion in the YAML becomes one CheckResult. The product dim stays
`gating=False` until V1.6 R1 flips it — it's informational on the forge
dashboard in the meantime, so FMs can watch the V1-completion score climb
as chunks ship.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import CheckResult, DimensionResult
from .check_types import dispatch

ROOT = Path(__file__).resolve().parent.parent.parent
CRITERIA_PATH = ROOT / "docs" / "specs" / "v1-criteria.yaml"
SCHEMA_PATH = ROOT / "docs" / "specs" / "v1-criteria.schema.json"


def _skip(reason: str) -> DimensionResult:
    return DimensionResult(
        "product",
        [
            CheckResult(
                "p0",
                "V1 criteria file",
                0,
                0,
                reason,
                "Is the V1 criteria YAML wired into the product dim?",
                "Fix docs/specs/v1-criteria.yaml or the product dim loader.",
                "info",
                status="SKIP",
            ),
        ],
        gating=False,
    )


def _load_yaml(path: Path) -> dict[str, Any] | None:
    try:
        import yaml
    except ImportError:
        return None
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:  # noqa: BLE001
        return None


def _validate(data: dict[str, Any]) -> str | None:
    """Lightweight schema validation. Returns None on success, else reason."""
    import json as _json

    if not isinstance(data, dict):
        return "criteria file is not a mapping"
    for required in ("version", "slice", "source", "criteria"):
        if required not in data:
            return f"missing top-level key: {required}"
    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return "criteria list is empty"
    # If jsonschema is installed, do a full validation pass. Otherwise fall
    # back to the cheap required-key check above.
    try:
        import jsonschema
    except ImportError:
        return None
    if not SCHEMA_PATH.exists():
        return None
    try:
        schema = _json.loads(SCHEMA_PATH.read_text())
        jsonschema.validate(data, schema)
    except Exception as exc:  # noqa: BLE001
        return f"schema validation failed: {str(exc)[:120]}"
    return None


def dim_product() -> DimensionResult:
    if not CRITERIA_PATH.exists():
        return _skip(f"{CRITERIA_PATH.relative_to(ROOT)} not found")

    data = _load_yaml(CRITERIA_PATH)
    if data is None:
        return _skip("could not parse v1-criteria.yaml (pyyaml missing or invalid)")

    err = _validate(data)
    if err:
        return _skip(err)

    checks: list[CheckResult] = []
    for criterion in data["criteria"]:
        cid = criterion["id"]
        title = criterion["title"]
        severity = criterion.get("severity", "medium")
        check_spec = criterion["check"]
        passed, evidence = dispatch(check_spec)
        checks.append(
            CheckResult(
                cid,
                title,
                10 if passed else 0,
                10,
                evidence,
                criterion.get("description", ""),
                f"See {criterion.get('source_spec_section', '§24.3')} for intent.",
                "info" if passed else severity,
            )
        )

    return DimensionResult("product", checks, gating=True)
