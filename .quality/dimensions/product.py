"""Product dimension — V1 completion criteria from docs/specs/v1-criteria.yaml.

In S1, the YAML file is stubbed. If the file is missing or empty, this
dimension returns eligible=0, score=100, gating=false — so S1 can pass.
V1.6 R1 populates the YAML and flips gating to true.
"""

from __future__ import annotations

from pathlib import Path

from . import CheckResult, DimensionResult

ROOT = Path(__file__).resolve().parent.parent.parent
CRITERIA_PATH = ROOT / "docs" / "specs" / "v1-criteria.yaml"


def dim_product() -> DimensionResult:
    if not CRITERIA_PATH.exists():
        return DimensionResult(
            "product",
            [
                CheckResult(
                    "p0",
                    "V1 criteria file",
                    0,
                    0,
                    f"{CRITERIA_PATH.relative_to(ROOT)} not found — stub until V1.6",
                    "Are V1 completion criteria defined?",
                    "Create docs/specs/v1-criteria.yaml with acceptance criteria.",
                    "info",
                    status="SKIP",
                ),
            ],
            gating=False,
        )

    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(CRITERIA_PATH.read_text()) or {}
    except Exception:
        data = {}

    criteria = data.get("criteria", [])
    if not criteria:
        return DimensionResult(
            "product",
            [
                CheckResult(
                    "p0",
                    "V1 criteria file",
                    0,
                    0,
                    "v1-criteria.yaml exists but has no criteria entries",
                    "",
                    "Add criteria entries to the YAML.",
                    "info",
                ),
            ],
            gating=False,
        )

    checks: list[CheckResult] = []
    for i, c in enumerate(criteria, 1):
        name = c.get("name", f"criterion_{i}")
        met = bool(c.get("met", False))
        checks.append(
            CheckResult(
                f"p{i}",
                name,
                10 if met else 0,
                10,
                "met" if met else "not met",
                c.get("description", ""),
                c.get("fix", ""),
                "info" if met else "medium",
            )
        )

    return DimensionResult("product", checks, gating=False)
