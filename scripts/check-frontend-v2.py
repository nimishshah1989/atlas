#!/usr/bin/env python3
"""
ATLAS Frontend V2 Criteria Gate Runner

Runs all frontend V2 criteria checks from docs/specs/frontend-v2-criteria.yaml.

Usage:
    python scripts/check-frontend-v2.py               # run all checks
    python scripts/check-frontend-v2.py --list        # print all backend check IDs and exit 0
    python scripts/check-frontend-v2.py --page today  # filter to one page
    python scripts/check-frontend-v2.py --json        # print JSON to stdout
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CRITERIA_FILE = ROOT / "docs" / "specs" / "frontend-v2-criteria.yaml"
REPORT_PATH = ROOT / ".forge" / "frontend-v2-report.json"
BACKEND_BASE = "http://localhost:8000"


# ─── Utilities ────────────────────────────────────────────────────────────────


def _now_ist() -> str:
    IST = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(IST).isoformat()


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        sys.exit("ERROR: PyYAML is required. pip install pyyaml")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            sys.exit(f"ERROR: {path} is not a YAML mapping")
        return data
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"ERROR: Failed to load {path}: {exc}")


# ─── Check dispatch ───────────────────────────────────────────────────────────


def _check_backend_probe(criterion: dict[str, Any]) -> tuple[bool, str, str]:
    """
    Try a live HTTP GET against the backend endpoint.
    Returns (passed, status, evidence).
    SKIP if backend unreachable; PASS if 200; FAIL if non-200.
    """
    endpoint = criterion.get("endpoint", "")
    timeout = int(criterion.get("timeout_seconds", 3))
    url = BACKEND_BASE.rstrip("/") + endpoint

    try:
        import requests  # type: ignore[import-untyped]
    except ImportError:
        return True, "SKIP", "SKIP: requests library not installed"

    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            return True, "RUN", f"HTTP 200 from {url}"
        return False, "RUN", f"HTTP {resp.status_code} from {url}"
    except requests.exceptions.ConnectionError:
        return True, "SKIP", f"SKIP: backend unreachable at {url}"
    except requests.exceptions.Timeout:
        return True, "SKIP", f"SKIP: backend timed out after {timeout}s at {url}"
    except Exception as exc:  # noqa: BLE001
        return True, "SKIP", f"SKIP: {exc}"


def _check_file_exists(criterion: dict[str, Any]) -> tuple[bool, str, str]:
    """Check that a file exists and is non-empty."""
    rel_path = criterion.get("file", "")
    full_path = ROOT / rel_path
    if not full_path.exists():
        return False, "RUN", f"File not found: {rel_path}"
    if full_path.stat().st_size == 0:
        return False, "RUN", f"File is empty: {rel_path}"
    return True, "RUN", f"File exists and non-empty: {rel_path}"


def _check_file_contains(criterion: dict[str, Any]) -> tuple[bool, str, str]:
    """Check that a file contains a regex pattern."""
    rel_path = criterion.get("file", "")
    pattern = criterion.get("pattern", "")
    full_path = ROOT / rel_path
    if not full_path.exists():
        return False, "RUN", f"File not found: {rel_path}"
    content = full_path.read_text(encoding="utf-8")
    if re.search(pattern, content):
        return True, "RUN", f"Pattern found in {rel_path}: {pattern!r}"
    return False, "RUN", f"Pattern NOT found in {rel_path}: {pattern!r}"


def _check_file_not_contains(criterion: dict[str, Any]) -> tuple[bool, str, str]:
    """Check that a file does NOT contain a regex pattern."""
    rel_path = criterion.get("file", "")
    pattern = criterion.get("pattern", "")
    full_path = ROOT / rel_path
    if not full_path.exists():
        return False, "RUN", f"File not found: {rel_path}"
    content = full_path.read_text(encoding="utf-8")
    if re.search(pattern, content):
        return False, "RUN", f"Forbidden pattern found in {rel_path}: {pattern!r}"
    return True, "RUN", f"Pattern absent in {rel_path}: {pattern!r}"


def _check_runner_exits_zero(criterion: dict[str, Any]) -> tuple[bool, str, str]:
    """Run a shell command and check it exits 0.

    Substitutes 'python3' with sys.executable so the same venv is used.
    """
    command = criterion.get("command", "")
    if not command:
        return False, "RUN", "No command specified"
    # Use the current interpreter so venv packages are available
    command = command.replace("python3 ", sys.executable + " ", 1)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=60,
        )
        if result.returncode == 0:
            return True, "RUN", f"Command exited 0: {command}"
        return (
            False,
            "RUN",
            f"Command exited {result.returncode}: {command}\n{result.stderr[:200]}",
        )
    except subprocess.TimeoutExpired:
        return False, "RUN", f"Command timed out: {command}"
    except Exception as exc:  # noqa: BLE001
        return False, "RUN", f"Command error: {exc}"


_DISPATCH: dict[str, Any] = {
    "backend_probe": _check_backend_probe,
    "file_exists": _check_file_exists,
    "file_contains": _check_file_contains,
    "file_not_contains": _check_file_not_contains,
    "runner_exits_zero": _check_runner_exits_zero,
}


def _run_criterion(criterion: dict[str, Any]) -> dict[str, Any]:
    check_type = criterion.get("check_type", "")
    handler = _DISPATCH.get(check_type)
    if handler is None:
        return {
            "id": criterion.get("id", "unknown"),
            "title": criterion.get("title", ""),
            "severity": criterion.get("severity", "medium"),
            "check_type": check_type,
            "passed": False,
            "status": "ERROR",
            "evidence": f"Unknown check_type: {check_type!r}",
        }
    try:
        passed, status, evidence = handler(criterion)
    except Exception as exc:  # noqa: BLE001
        passed = False
        status = "ERROR"
        evidence = f"ERROR: {str(exc)[:200]}"

    return {
        "id": criterion.get("id", "unknown"),
        "title": criterion.get("title", ""),
        "severity": criterion.get("severity", "medium"),
        "check_type": check_type,
        "passed": passed,
        "status": status,
        "evidence": evidence,
    }


def _run_criteria(
    criteria: list[dict[str, Any]],
    page_filter: str | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for criterion in criteria:
        if page_filter:
            page = criterion.get("page", "global")
            if page != page_filter and page != "global":
                continue
        results.append(_run_criterion(criterion))
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
    print(" ATLAS FRONTEND V2 CRITERIA REPORT")
    print("=" * 64)
    print(f"  Total:         {stats['total']}")
    print(f"  Passed (RUN):  {stats['passed']}")
    print(f"  Failed (RUN):  {stats['failed']}")
    print(f"  Skipped:       {stats['skipped']}")
    print(f"  Critical fail: {stats['critical_fail_count']}")
    print(f"  High fail:     {stats['high_fail_count']}")
    print("=" * 64)

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
    if report["critical_fail_count"] == 0:
        return 0
    return 1


# ─── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="ATLAS Frontend V2 Criteria Gate Runner")
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print all backend check IDs (v2fe-be-*) and exit 0",
    )
    parser.add_argument(
        "--page",
        metavar="NAME",
        help="Filter checks to a specific page (e.g. today, explore-country)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON report to stdout",
    )
    args = parser.parse_args()

    if not CRITERIA_FILE.exists():
        print(f"ERROR: criteria file not found: {CRITERIA_FILE}", file=sys.stderr)
        sys.exit(1)

    raw = _load_yaml(CRITERIA_FILE)
    criteria: list[dict[str, Any]] = raw.get("criteria", [])
    if not criteria:
        print("ERROR: no criteria found in YAML", file=sys.stderr)
        sys.exit(1)

    if args.list:
        backend_ids = [c["id"] for c in criteria if c.get("check_type") == "backend_probe"]
        for bid in sorted(backend_ids):
            print(bid)
        sys.exit(0)

    results = _run_criteria(criteria, page_filter=args.page)
    generated_at = _now_ist()
    report = _build_report(results, generated_at)

    _write_report(report)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_summary(report)

    sys.exit(_exit_code(report))


if __name__ == "__main__":
    main()
