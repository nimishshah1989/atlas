#!/usr/bin/env python3
"""V5 Completion Validator — checks all criteria from v5-criteria.yaml.

Usage:
    python scripts/validate-v5.py

Exits 0 if all criteria pass, 1 otherwise.

Mirrors scripts/validate-v3.py but targets the V5 Central Intelligence
Engine slice. Uses the same check_types dispatch system so new check
types automatically become available to V5 criteria as well.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load .env for DATABASE_URL
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if key and key not in os.environ:
            os.environ[key] = val

sys.path.insert(0, str(ROOT / ".quality"))
from dimensions.check_types import dispatch  # noqa: E402


def main() -> int:
    try:
        import yaml
    except ImportError:
        print("FAIL: pyyaml not installed")
        return 1

    criteria_path = ROOT / "docs" / "specs" / "v5-criteria.yaml"
    if not criteria_path.exists():
        print(f"FAIL: {criteria_path} not found")
        return 1

    data = yaml.safe_load(criteria_path.read_text())
    criteria = data.get("criteria", [])
    if not criteria:
        print("FAIL: no criteria found")
        return 1

    passed_count = 0
    failed_count = 0
    total = len(criteria)

    print(f"\n  V5 Completion Check — {total} criteria\n")
    print(f"  {'=' * 58}")

    for c in criteria:
        cid = c["id"]
        title = c["title"]
        check_spec = c["check"]
        ok, evidence = dispatch(check_spec)
        status = "PASS" if ok else "FAIL"
        if ok:
            passed_count += 1
        else:
            failed_count += 1
        print(f"  [{status}] {cid}: {title}")
        print(f"          -> {evidence}")

    print(f"\n  {'=' * 58}")
    print(f"  V5 Completion: {passed_count}/{total} criteria passed")
    print(f"  {'=' * 58}")

    if failed_count > 0:
        print(f"\n  {failed_count} criteria FAILED -- V5 not complete")
        return 1
    else:
        print("\n  All criteria PASSED -- V5 complete")
        return 0


if __name__ == "__main__":
    sys.exit(main())
