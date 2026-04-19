#!/usr/bin/env python3
"""
ATLAS Frontend Criteria Gate Runner

Runs all frontend criteria checks from docs/specs/frontend-v1-criteria.yaml.

Usage:
    python scripts/check-frontend-criteria.py                    # run all
    python scripts/check-frontend-criteria.py --list-types       # list 28 check types
    python scripts/check-frontend-criteria.py --only 'fe-g-*'   # filter by id pattern
    python scripts/check-frontend-criteria.py --report-only      # write report, no print
    python scripts/check-frontend-criteria.py --json             # print JSON to stdout
    python scripts/check-frontend-criteria.py --dim frontend     # alias for quality gate
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# Ensure fe_checks is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

ROOT = Path(__file__).resolve().parent.parent
CRITERIA_FILE = ROOT / "docs" / "specs" / "frontend-v1-criteria.yaml"
REPORT_PATH = ROOT / ".forge" / "frontend-report.json"


def _now_ist() -> str:
    """Return current IST ISO timestamp."""
    IST = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(IST).isoformat()


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML file using PyYAML."""
    try:
        import yaml
    except ImportError:
        sys.exit("ERROR: PyYAML is required. Install with: pip install pyyaml")
    try:
        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            sys.exit(f"ERROR: {path} is not a YAML mapping")
        return data
    except Exception as exc:
        sys.exit(f"ERROR: Failed to load {path}: {exc}")


def _resolve_settings_references(criteria: list[dict[str, Any]], settings: dict[str, Any]) -> None:
    """Resolve settings.* references in criteria check specs in-place."""

    def _resolve_value(val: Any) -> Any:
        if isinstance(val, str) and val.startswith("settings."):
            key = val[len("settings.") :]
            return settings.get(key, val)
        return val

    def _resolve_dict(d: dict[str, Any]) -> None:
        for k, v in list(d.items()):
            if isinstance(v, str):
                d[k] = _resolve_value(v)
            elif isinstance(v, list):
                d[k] = [_resolve_value(item) if isinstance(item, str) else item for item in v]
            elif isinstance(v, dict):
                _resolve_dict(v)

    for criterion in criteria:
        check = criterion.get("check", {})
        _resolve_dict(check)


def _run_criteria(
    criteria: list[dict[str, Any]],
    id_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Run all criteria (optionally filtered) and return results list."""
    from fe_checks import dispatch

    results: list[dict[str, Any]] = []

    for criterion in criteria:
        cid = criterion.get("id", "unknown")

        # Apply id filter (glob pattern, supports comma-separated)
        if id_filter:
            patterns = [p.strip() for p in id_filter.split(",")]
            if not any(fnmatch.fnmatch(cid, p) for p in patterns):
                continue

        title = criterion.get("title", "")
        severity = criterion.get("severity", "medium")
        check_spec = criterion.get("check", {})
        check_type = check_spec.get("type", "")

        try:
            passed, evidence = dispatch(check_spec)
        except Exception as exc:  # noqa: BLE001
            passed = False
            evidence = f"ERROR: {str(exc)[:200]}"
            status = "ERROR"
        else:
            # Determine status
            if evidence.startswith("SKIP:") or "SKIP" in evidence[:6]:
                status = "SKIP"
            elif evidence.startswith("ERROR"):
                status = "ERROR"
                passed = False
            else:
                status = "RUN"

        results.append(
            {
                "id": cid,
                "title": title,
                "severity": severity,
                "check_type": check_type,
                "passed": passed,
                "evidence": evidence,
                "status": status,
            }
        )

    # Sort by id
    results.sort(key=lambda r: r["id"])
    return results


def _compute_stats(results: list[dict[str, Any]]) -> dict[str, int]:
    total = len(results)
    passed = sum(1 for r in results if r["passed"] and r["status"] == "RUN")
    failed = sum(1 for r in results if not r["passed"] and r["status"] == "RUN")
    skipped = sum(1 for r in results if r["status"] == "SKIP")
    critical_fail = sum(
        1
        for r in results
        if not r["passed"] and r["status"] == "RUN" and r["severity"] == "critical"
    )
    high_fail = sum(
        1 for r in results if not r["passed"] and r["status"] == "RUN" and r["severity"] == "high"
    )
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "critical_fail_count": critical_fail,
        "high_fail_count": high_fail,
    }


def _build_report(results: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    stats = _compute_stats(results)
    return {
        "version": "1.0",
        "generated_at": generated_at,
        "criteria_file": str(CRITERIA_FILE.relative_to(ROOT)),
        **stats,
        "results": results,
    }


def _write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")


def _print_summary(report: dict[str, Any]) -> None:
    stats = {
        k: report[k]
        for k in ("total", "passed", "failed", "skipped", "critical_fail_count", "high_fail_count")
    }
    print("\n" + "=" * 64)
    print(" ATLAS FRONTEND CRITERIA REPORT")
    print("=" * 64)
    print(f"  Total:         {stats['total']}")
    print(f"  Passed (RUN):  {stats['passed']}")
    print(f"  Failed (RUN):  {stats['failed']}")
    print(f"  Skipped:       {stats['skipped']}")
    print(f"  Critical fail: {stats['critical_fail_count']}")
    print(f"  High fail:     {stats['high_fail_count']}")
    print("=" * 64)

    # Print failures
    failures = [r for r in report["results"] if not r["passed"] and r["status"] == "RUN"]
    if failures:
        print("\nFAILURES:")
        for r in failures[:20]:
            sev = r["severity"].upper()
            print(f"  [{sev}] {r['id']}: {r['title']}")
            print(f"         {r['evidence'][:120]}")

    print(f"\nReport: {REPORT_PATH}")
    print()


def _exit_code(report: dict[str, Any]) -> int:
    """Return 0 if no critical failures; 1 otherwise."""
    if report["critical_fail_count"] == 0:
        return 0
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ATLAS Frontend Criteria Gate Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list-types",
        action="store_true",
        help="List all 28 registered check types and exit",
    )
    parser.add_argument(
        "--only",
        metavar="PATTERN",
        help="Filter criteria by id glob pattern (e.g. 'fe-g-*')",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Write report to .forge/frontend-report.json without printing",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON report to stdout",
    )
    parser.add_argument(
        "--dim",
        metavar="NAME",
        help="Compatibility flag for quality gate (e.g. --dim frontend)",
    )
    args = parser.parse_args()

    # --list-types: print sorted check type names and exit
    if args.list_types:
        from fe_checks import list_types

        for t in list_types():
            print(t)
        sys.exit(0)

    # Load and validate criteria YAML
    if not CRITERIA_FILE.exists():
        print(f"ERROR: criteria file not found: {CRITERIA_FILE}", file=sys.stderr)
        sys.exit(1)

    raw = _load_yaml(CRITERIA_FILE)
    settings: dict[str, Any] = raw.get("settings", {})
    criteria: list[dict[str, Any]] = raw.get("criteria", [])

    if not criteria:
        print("ERROR: no criteria found in YAML", file=sys.stderr)
        sys.exit(1)

    # Resolve settings references
    _resolve_settings_references(criteria, settings)

    # Preflight: validate all check types are known
    from fe_checks import validate_types

    unknown = validate_types(criteria)
    if unknown:
        print(f"ERROR: unknown check types in criteria: {unknown}", file=sys.stderr)
        sys.exit(1)

    # Preflight: reject fake-void HTML sentinels across frontend/mockups/.
    # Non-void tags written as `<tag />` break the browser DOM; historically
    # the gate's regex was tolerant enough to let agents satisfy dom_required
    # with sentinel-spam while pages rendered blank. Hard-fail the whole gate
    # if any appear — this is a structural contract, not a content check.
    from fe_checks.dom_checks import find_fake_void_tags  # noqa: E402
    import glob as _glob  # noqa: E402

    _mockups_dir = ROOT / "frontend" / "mockups"
    _fake_void_total = 0
    _fake_void_detail: list[str] = []
    for _path in sorted(_glob.glob(str(_mockups_dir / "*.html"))):
        _txt = Path(_path).read_text(encoding="utf-8")
        _hits = find_fake_void_tags(_txt)
        if _hits:
            _fake_void_total += len(_hits)
            _tags = sorted({t for t, _ in _hits})
            _fake_void_detail.append(
                f"  {Path(_path).name}: {len(_hits)} fake-void [{','.join(_tags)}]"
            )
    if _fake_void_total:
        print(
            f"ERROR: {_fake_void_total} fake-void HTML self-closing tags found. "
            "Non-void tags like <nav/>, <a/>, <div/>, <footer/> break the "
            "browser DOM tree — browsers parse them as unclosed opening tags. "
            "Use <tag></tag> with explicit close, or remove the sentinel.",
            file=sys.stderr,
        )
        for _line in _fake_void_detail:
            print(_line, file=sys.stderr)
        sys.exit(1)

    # Run criteria
    id_filter = args.only
    results = _run_criteria(criteria, id_filter=id_filter)

    generated_at = _now_ist()
    report = _build_report(results, generated_at)

    # Write report
    _write_report(report)

    # Output
    if args.json:
        print(json.dumps(report, indent=2))
    elif not args.report_only:
        _print_summary(report)

    sys.exit(_exit_code(report))


if __name__ == "__main__":
    main()
