#!/usr/bin/env python3
"""roadmap-lint.py — lint orchestrator/roadmap.yaml against orchestrator/plan.yaml.

Checks 6 rules:
  1. Every chunk in plan.yaml is claimed by exactly one version in roadmap.yaml.
  2. Every chunk in roadmap.yaml without future:true exists in plan.yaml.
  3. Chunk ids are unique across the whole roadmap.
  4. Version ids are V1–V10 exactly (no out-of-range or missing).
  5. check: specs validate against the Pydantic schema (bad type or missing fields).
  6. command: is a list, never a string.

Exit 0: clean. Exit 1: drift found (prints diagnostic table).
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

# Allow running from repo root or scripts/ directory
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from orchestrator.roadmap_schema import (  # noqa: E402
    CHUNK_ID_RE,
    VERSION_ID_RE,
    RoadmapFile,
    parse_check,
)

PLAN_YAML = _REPO_ROOT / "orchestrator" / "plan.yaml"
ROADMAP_YAML = _REPO_ROOT / "orchestrator" / "roadmap.yaml"

PLAN_CHUNK_ID_RE = re.compile(r"^\s*-\s*id:\s*(\S+)")
VALID_VERSIONS = {f"V{n}" for n in range(1, 11)}


def load_plan_chunk_ids(plan_path: Path) -> set[str]:
    """Extract chunk ids from plan.yaml (simple regex, no YAML parse needed)."""
    ids: set[str] = set()
    if not plan_path.exists():
        return ids
    for line in plan_path.read_text().splitlines():
        m = PLAN_CHUNK_ID_RE.match(line)
        if m:
            cid = m.group(1)
            # Only collect ids that look like chunk ids (C<n> pattern)
            if CHUNK_ID_RE.match(cid):
                ids.add(cid)
    return ids


def check_command_fields(data: Any, path: str, errors: list[str]) -> None:
    """Recursively find any check: blocks and validate command: is list, not string."""
    if isinstance(data, dict):
        if "type" in data and data.get("type") == "command":
            cmd = data.get("cmd")
            if isinstance(cmd, str):
                errors.append(
                    f"Rule 6 — {path}: 'cmd' is a shell string {cmd!r}, must be a list"
                )
        for k, v in data.items():
            check_command_fields(v, f"{path}.{k}", errors)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            check_command_fields(item, f"{path}[{i}]", errors)


def main() -> int:
    t0 = time.monotonic()
    errors: list[str] = []

    # --- Load files ---
    if not ROADMAP_YAML.exists():
        print(f"ERROR: {ROADMAP_YAML} not found", file=sys.stderr)
        return 1
    if not PLAN_YAML.exists():
        print(f"ERROR: {PLAN_YAML} not found", file=sys.stderr)
        return 1

    raw = yaml.safe_load(ROADMAP_YAML.read_text())
    plan_ids = load_plan_chunk_ids(PLAN_YAML)

    # --- Rule 6: command must be list (pre-Pydantic, catches raw YAML strings) ---
    check_command_fields(raw, "roadmap", errors)

    # --- Pydantic validation (Rules 4, 5 partly) ---
    try:
        roadmap = RoadmapFile.model_validate(raw)
    except Exception as exc:
        errors.append(f"Rule 4/5 — Pydantic schema error: {exc}")
        _print_report(errors, t0)
        return 1

    # --- Rule 4: version ids V1–V10 ---
    seen_versions: set[str] = set()
    for v in roadmap.versions:
        if not VERSION_ID_RE.match(v.id):
            errors.append(f"Rule 4 — Version id {v.id!r} does not match V<n>")
        if v.id not in VALID_VERSIONS:
            errors.append(f"Rule 4 — Version id {v.id!r} is outside V1–V10")
        seen_versions.add(v.id)

    # --- Build chunk → version mapping ---
    roadmap_chunk_to_version: dict[str, str] = {}
    # Rule 3: unique chunk ids (also enforced by Pydantic, but emit specific msg)
    for v in roadmap.versions:
        for c in v.chunks:
            if c.id in roadmap_chunk_to_version:
                errors.append(
                    f"Rule 3 — Chunk {c.id!r} appears in both "
                    f"{roadmap_chunk_to_version[c.id]} and {v.id}"
                )
            roadmap_chunk_to_version[c.id] = v.id

    # --- Rule 1: every plan chunk is claimed by exactly one version ---
    for pid in sorted(plan_ids):
        if pid not in roadmap_chunk_to_version:
            errors.append(
                f"Rule 1 — Chunk {pid!r} is in plan.yaml but not claimed by any version"
            )

    # --- Rule 2: every roadmap chunk without future:true exists in plan.yaml ---
    for v in roadmap.versions:
        for c in v.chunks:
            if not c.future and c.id not in plan_ids:
                errors.append(
                    f"Rule 2 — Chunk {c.id!r} in {v.id} is not in plan.yaml "
                    f"(add future: true if intentional)"
                )

    # --- Rule 5: validate check specs ---
    for v in roadmap.versions:
        for c in v.chunks:
            for s in c.steps:
                if s.check is not None:
                    try:
                        parse_check(s.check)
                    except Exception as exc:
                        errors.append(
                            f"Rule 5 — {v.id}/{c.id}/{s.id} check invalid: {exc}"
                        )

    _print_report(errors, t0, roadmap=roadmap)
    return 1 if errors else 0


def _print_report(
    errors: list[str],
    t0: float,
    roadmap: RoadmapFile | None = None,
) -> None:
    elapsed = time.monotonic() - t0
    if not errors:
        n_versions = len(roadmap.versions) if roadmap else 0
        n_chunks = sum(len(v.chunks) for v in roadmap.versions) if roadmap else 0
        n_steps = (
            sum(len(c.steps) for v in roadmap.versions for c in v.chunks)
            if roadmap
            else 0
        )
        print(
            f"roadmap OK: {n_versions} versions, {n_chunks} chunks, "
            f"{n_steps} steps  ({elapsed * 1000:.0f}ms)"
        )
    else:
        print(f"\nroadmap DRIFT — {len(errors)} error(s):\n")
        for i, err in enumerate(errors, 1):
            print(f"  [{i}] {err}")
        print(f"\n({elapsed * 1000:.0f}ms)")


if __name__ == "__main__":
    sys.exit(main())
