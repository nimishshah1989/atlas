#!/usr/bin/env python3
"""Verify every mandatory section of ATLAS-DEFINITIVE-SPEC.md has ≥1 criterion.

Root-cause fix for the "spec drift from criteria" failure that let V1 ship
without UQL (§17), include system (§18), and API design principles (§20):
the criteria file had become the de facto spec, because nothing blocked a
chunk from ignoring spec sections that had no criterion pointing at them.

This script parses the spec for top-level section headers (`## N. TITLE`)
and parses every criteria YAML under docs/specs/ for
`source_spec_section: "§N..."` back-references. If any section in the
MANDATORY set has zero back-references, the script exits 1.

Run via:
    python scripts/check-spec-coverage.py

Wired into CLAUDE.md test commands; required to pass before shipping any
chunk that touches the spec or criteria files.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "ATLAS-DEFINITIVE-SPEC.md"
CRITERIA_GLOB = "docs/specs/*-criteria.yaml"

# Sections that MUST have at least one criterion back-reference. If a section
# is in scope for V1..Vn but has no criterion, the gate fails. Add sections
# here as they enter scope — never remove without an ADR.
MANDATORY_SECTIONS: set[int] = {
    11,  # API Layer
    17,  # Unified Query Layer (Bloomberg-grade API)
    18,  # Composable Response Model
    20,  # API Design Principles
    24,  # Vertical Slice — V1 Delivery Unit
}

HEADER_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
REF_RE = re.compile(r"§(\d+)(?:\.\d+)*")


def parse_spec_sections(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {int(num): title for num, title in HEADER_RE.findall(text)}


def parse_criteria_refs(glob: str) -> dict[int, list[str]]:
    """Return {section_number: [criterion_id_referencing_it, ...]}."""
    refs: dict[int, list[str]] = {}
    for yaml_path in sorted(ROOT.glob(glob)):
        try:
            doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print(f"WARN: failed to parse {yaml_path.name}: {exc}", file=sys.stderr)
            continue
        for crit in (doc or {}).get("criteria", []):
            cid = crit.get("id", "?")
            src = crit.get("source_spec_section", "") or ""
            for match in REF_RE.finditer(src):
                section_num = int(match.group(1))
                refs.setdefault(section_num, []).append(f"{yaml_path.stem}:{cid}")
    return refs


def main() -> int:
    if not SPEC_PATH.exists():
        print(f"FAIL: {SPEC_PATH} not found", file=sys.stderr)
        return 1

    sections = parse_spec_sections(SPEC_PATH)
    refs = parse_criteria_refs(CRITERIA_GLOB)

    print(f"\nATLAS spec-coverage check — {SPEC_PATH.name}")
    print(f"Sections found: {len(sections)}")
    print(f"Mandatory:      {sorted(MANDATORY_SECTIONS)}")
    print()

    uncovered_mandatory: list[int] = []
    for num in sorted(MANDATORY_SECTIONS):
        title = sections.get(num, "<section not found in spec>")
        backrefs = refs.get(num, [])
        if backrefs:
            print(f"  [PASS] §{num:02d}  {title}")
            print(
                f"         └─ {len(backrefs)} criteria: {', '.join(backrefs[:3])}"
                + ("..." if len(backrefs) > 3 else "")
            )
        else:
            uncovered_mandatory.append(num)
            print(f"  [FAIL] §{num:02d}  {title}")
            print("         └─ NO criteria reference this section")

    # Informational: any spec section with a criterion (not in mandatory) is fine;
    # any spec section NOT mandatory AND NOT covered is just reported as a hint.
    optional_uncovered = [
        num for num in sections if num not in MANDATORY_SECTIONS and num not in refs
    ]
    if optional_uncovered:
        nums = ", §".join(f"{n:02d}" for n in sorted(optional_uncovered))
        print(
            f"\n  INFO: {len(optional_uncovered)} non-mandatory sections have no criteria"
            f" (add when they enter scope): §{nums}"
        )

    print()
    if uncovered_mandatory:
        print(
            f"FAIL — {len(uncovered_mandatory)} mandatory spec section(s) uncovered: "
            f"§{', §'.join(str(n) for n in uncovered_mandatory)}"
        )
        print("Fix: add a criterion to a docs/specs/*-criteria.yaml file whose")
        print("source_spec_section references each uncovered §N.")
        return 1
    print(f"PASS — all {len(MANDATORY_SECTIONS)} mandatory sections covered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
