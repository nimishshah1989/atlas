"""Verify standards.md and checks.py describe the same set of checks.

Used as architecture check 3.10. Run standalone:
    python .quality/verify_doc_matches_code.py            # exit 0 if in sync
    python .quality/verify_doc_matches_code.py --json     # JSON drift report

Contract (S2):
- Every CheckResult("ID", "name", ...) declared in .quality/checks.py or any
  .quality/dimensions/*.py must have a matching `### <ID> <name>` heading in
  .quality/standards.md.
- Every `### <ID> <name>` heading in standards.md must map back to a
  CheckResult declared in code.
- The (ID, name) tuple must match exactly. A rename in code without a
  matching rename in the doc is drift.

This is what keeps the rubric and the engine bidirectionally honest.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUALITY = ROOT / ".quality"
STANDARDS_PATH = QUALITY / "standards.md"

# CheckResult("1.1", "No hardcoded secrets", ...)
CHECK_RESULT_RE = re.compile(
    r'CheckResult\(\s*"([A-Za-z0-9_.]+)"\s*,\s*"([^"]+)"',
)

# Loop-driven check registrations: `("4.2", "Endpoint response time", 15),`
# Several dimensions register skip-path checks via a list of tuples that gets
# fanned out into CheckResult calls. The literal CheckResult regex misses those,
# so we also pick up ("ID", "Name", ...) tuples that look like check entries.
CHECK_TUPLE_RE = re.compile(
    r'\(\s*"([0-9]+\.[0-9]+|b[0-9]+|p[0-9]+)"\s*,\s*"([^"]+)"\s*,\s*[0-9]+\s*\)',
)

# ### 1.1 No hardcoded secrets   (ID followed by space then name)
HEADING_RE = re.compile(
    r"^###\s+([A-Za-z0-9_.]+)\s+(.+?)\s*$",
    re.MULTILINE,
)


def collect_code_checks() -> dict[str, str]:
    """Scan checks.py + dimensions/*.py for declared CheckResult IDs/names."""
    out: dict[str, str] = {}
    sources = [QUALITY / "checks.py"]
    dims_dir = QUALITY / "dimensions"
    if dims_dir.exists():
        sources.extend(sorted(dims_dir.glob("*.py")))
    for src in sources:
        text = src.read_text(encoding="utf-8", errors="replace")
        for regex in (CHECK_RESULT_RE, CHECK_TUPLE_RE):
            for m in regex.finditer(text):
                cid, name = m.group(1), m.group(2)
                existing = out.get(cid)
                if (
                    existing
                    and existing != name
                    and not existing.startswith("__CONFLICT__")
                ):
                    out[cid] = f"__CONFLICT__ {existing} vs {name}"
                elif not existing:
                    out[cid] = name
    return out


def collect_doc_checks() -> dict[str, str]:
    """Scan standards.md for `### <ID> <name>` headings."""
    if not STANDARDS_PATH.exists():
        return {}
    text = STANDARDS_PATH.read_text(encoding="utf-8", errors="replace")
    out: dict[str, str] = {}
    for m in HEADING_RE.finditer(text):
        cid, name = m.group(1), m.group(2)
        # Heading IDs always look like 1.1, 3.10, b1, p0 — skip prose headings.
        if not re.match(r"^([0-9]+\.[0-9]+|b[0-9]+|p[0-9]+)$", cid):
            continue
        out[cid] = name.strip()
    return out


def diff(code: dict[str, str], doc: dict[str, str]) -> dict[str, list[str]]:
    code_ids = set(code)
    doc_ids = set(doc)
    missing_in_doc = sorted(code_ids - doc_ids)
    missing_in_code = sorted(doc_ids - code_ids)
    name_mismatch: list[str] = []
    for cid in sorted(code_ids & doc_ids):
        if code[cid] != doc[cid]:
            name_mismatch.append(f"{cid}: code={code[cid]!r} doc={doc[cid]!r}")
    return {
        "missing_in_doc": missing_in_doc,
        "missing_in_code": missing_in_code,
        "name_mismatch": name_mismatch,
    }


def total_drift(report: dict[str, list[str]]) -> int:
    return sum(len(v) for v in report.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    code = collect_code_checks()
    doc = collect_doc_checks()
    report = diff(code, doc)
    drift = total_drift(report)
    if args.json:
        print(json.dumps({"drift": drift, **report}, indent=2))
    else:
        print(f"code checks: {len(code)}  doc checks: {len(doc)}  drift: {drift}")
        for k, v in report.items():
            if v:
                print(f"\n{k} ({len(v)}):")
                for item in v:
                    print(f"  - {item}")
    return 0 if drift == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
