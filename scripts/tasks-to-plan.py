#!/usr/bin/env python3
"""tasks-to-plan.py — compile /forge-build tasks.json into orchestrator plan.yaml rows.

Pipeline:
    docs/specs/prd.md
        │  (/forge-build Phase 1)
        ▼
    docs/specs/chunk-plan.md + docs/specs/chunks/chunk-N.md + docs/specs/tasks.json
        │  (/forge-build Phase 2)
        ▼
    [this script]  ──►  orchestrator/plan.yaml   (appended, never rewritten)
        │
        ▼
    python -m orchestrator.cli sync  ──►  state.db  ──►  runner.py

The bridge derives quality_targets heuristically from each task's `files` list
(backend → code+api, frontend → frontend, scripts/ops → devops, docs → docs)
and derives punch_list from the chunk spec file's "Acceptance criteria"
section if present, falling back to the task's `acceptance` string.

Ids are namespaced with an optional --id-prefix (e.g. "FD" keeps FD-1,
"V2" rewrites FD-1 → V2-1). Existing ids in plan.yaml are never overwritten;
the script refuses to run if any task id already exists in plan.yaml unless
--force-replace is passed.

Usage:
    python scripts/tasks-to-plan.py docs/specs/tasks.json
    python scripts/tasks-to-plan.py docs/specs/tasks.json --id-prefix V2
    python scripts/tasks-to-plan.py docs/specs/tasks.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
PLAN_YAML = REPO_ROOT / "orchestrator" / "plan.yaml"


# --- quality target heuristics -----------------------------------------------
# Map file path prefixes to the dimension(s) that chunk most affects. The
# orchestrator's gate will hold a chunk at QUALITY_GATE until every listed
# dimension is at or above the floor.
DIMENSION_MAP: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("backend/routes", ("api", "code")),
    ("backend/core", ("code", "architecture")),
    ("backend/services", ("code", "architecture")),
    ("backend/", ("code",)),
    ("frontend/", ("frontend",)),
    ("scripts/", ("devops",)),
    ("orchestrator/", ("architecture", "devops")),
    (".github/", ("devops",)),
    ("docs/", ("docs",)),
    ("README", ("docs",)),
    ("CONTRIBUTING", ("docs",)),
    ("tests/", ("code",)),
)

# Floor values per dimension when a task touches that area. Picked to be
# marginally higher than plan.yaml settings.min_dimensions so the chunk must
# actually improve the dimension, not just preserve it.
DIMENSION_FLOORS: dict[str, int] = {
    "api": 85,
    "code": 80,
    "architecture": 85,
    "frontend": 80,
    "devops": 80,
    "docs": 80,
    "security": 85,
}


def derive_quality_targets(files: list[str]) -> dict[str, int]:
    hit: set[str] = set()
    for f in files:
        for prefix, dims in DIMENSION_MAP:
            if f.startswith(prefix) or prefix in f:
                hit.update(dims)
    return {
        dim: DIMENSION_FLOORS[dim] for dim in sorted(hit) if dim in DIMENSION_FLOORS
    }


# --- punch list derivation ----------------------------------------------------
ACCEPTANCE_HEADER_RE = re.compile(r"^##+\s*Acceptance criteria", re.IGNORECASE)
BULLET_RE = re.compile(r"^\s*(?:\d+\.\s+|[-*]\s+)(.+)")


def extract_acceptance_bullets(spec_path: Path) -> list[str]:
    """Read a chunk-N.md file and return the bullets under 'Acceptance criteria'.

    Stops at the next H2/H3 header or EOF. Strips markdown bullet markers and
    numeric prefixes. Returns an empty list if the section is missing.
    """
    if not spec_path.exists():
        return []
    lines = spec_path.read_text().splitlines()
    inside = False
    bullets: list[str] = []
    for ln in lines:
        if ACCEPTANCE_HEADER_RE.match(ln):
            inside = True
            continue
        if inside:
            if ln.startswith("##"):
                break
            m = BULLET_RE.match(ln)
            if m:
                bullets.append(m.group(1).strip())
    return bullets


def derive_punch_list(task: dict, repo_root: Path) -> list[str]:
    spec_rel = task.get("spec")
    if spec_rel:
        bullets = extract_acceptance_bullets(repo_root / spec_rel)
        if bullets:
            return bullets
    # Fallback: split the acceptance string on semicolons / periods.
    acc = task.get("acceptance", "").strip()
    if not acc:
        return [f"Ship {task.get('name', task['id'])}"]
    parts = [p.strip().rstrip(".") for p in re.split(r"[.;]\s+", acc) if p.strip()]
    return parts or [acc]


# --- id mapping --------------------------------------------------------------
def remap_id(task_id: str, prefix: str | None) -> str:
    if not prefix:
        return task_id
    # Replace the alpha part of the id with the new prefix, keep the numeric
    # suffix. E.g. FD-1 → V2-1. If the id has no dash, append it: C11 → V2-11.
    m = re.match(r"^[A-Za-z]+[-]?(\d+.*)$", task_id)
    if not m:
        return f"{prefix}-{task_id}"
    return f"{prefix}-{m.group(1)}"


def remap_deps(deps: list[str], prefix: str | None) -> list[str]:
    return [remap_id(d, prefix) for d in deps]


# --- yaml writer (no PyYAML required — we emit deterministic text) ----------
@dataclass
class ChunkRow:
    id: str
    title: str
    depends_on: list[str]
    quality_targets: dict[str, int]
    punch_list: list[str]

    def to_yaml_lines(self) -> list[str]:
        out: list[str] = [
            f"  - id: {self.id}",
            f'    title: "{self.title.replace("""""", """""")}"',
            "    status: PENDING",
        ]
        if self.depends_on:
            deps = ", ".join(self.depends_on)
            out.append(f"    depends_on: [{deps}]")
        if self.quality_targets:
            out.append("    quality_targets:")
            for dim, score in self.quality_targets.items():
                out.append(f"      {dim}: {score}")
        if self.punch_list:
            out.append("    punch_list:")
            for bullet in self.punch_list:
                safe = bullet.replace('"', '\\"')
                out.append(f'      - "{safe}"')
        return out


CHUNK_ID_RE = re.compile(r"^\s*-\s*id:\s*(\S+)")


def existing_plan_ids(plan_path: Path) -> set[str]:
    if not plan_path.exists():
        return set()
    ids: set[str] = set()
    for ln in plan_path.read_text().splitlines():
        m = CHUNK_ID_RE.match(ln)
        if m:
            ids.add(m.group(1))
    return ids


def append_rows_to_plan(plan_path: Path, rows: Iterable[ChunkRow], marker: str) -> str:
    existing = plan_path.read_text() if plan_path.exists() else ""
    if not existing.endswith("\n"):
        existing += "\n"
    block = [f"\n  # --- {marker} -------------------------------------------------"]
    for row in rows:
        block.append("")
        block.extend(row.to_yaml_lines())
    block.append("")
    return existing + "\n".join(block) + "\n"


# --- main --------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("tasks_json", type=Path)
    ap.add_argument("--id-prefix", default=None, help="Rewrite FD-1 → <prefix>-1 etc.")
    ap.add_argument("--plan", type=Path, default=PLAN_YAML)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the appended block to stdout and exit without writing.",
    )
    ap.add_argument(
        "--force-replace",
        action="store_true",
        help="Allow overwriting ids that already exist in plan.yaml (dangerous).",
    )
    ap.add_argument(
        "--auto-roadmap",
        action="store_true",
        help=(
            "After appending chunks to plan.yaml, also invoke plan-to-roadmap.py "
            "for each newly-added chunk so roadmap.yaml stays in sync. "
            "Version is derived from --id-prefix (e.g. V2 prefix → V2)."
        ),
    )
    args = ap.parse_args()

    try:
        data = json.loads(args.tasks_json.read_text())
    except FileNotFoundError:
        print(f"ERROR: tasks.json not found at {args.tasks_json}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: tasks.json invalid JSON: {exc}", file=sys.stderr)
        return 2

    tasks: list[dict] = data.get("chunks") or data.get("tasks") or []
    if not tasks:
        print("ERROR: tasks.json has no 'chunks' or 'tasks' array", file=sys.stderr)
        return 2

    existing = existing_plan_ids(args.plan)
    rows: list[ChunkRow] = []
    for task in tasks:
        raw_id = task.get("id")
        if not raw_id:
            print(f"ERROR: task missing id: {task}", file=sys.stderr)
            return 2
        new_id = remap_id(raw_id, args.id_prefix)
        if new_id in existing and not args.force_replace:
            print(
                f"ERROR: id {new_id} already in {args.plan}. "
                "Use --id-prefix to namespace or --force-replace to overwrite.",
                file=sys.stderr,
            )
            return 3
        title = task.get("name") or task.get("title") or new_id
        deps = remap_deps(list(task.get("depends_on") or []), args.id_prefix)
        qt = derive_quality_targets(list(task.get("files") or []))
        pl = derive_punch_list(task, REPO_ROOT)
        rows.append(
            ChunkRow(
                id=new_id,
                title=title,
                depends_on=deps,
                quality_targets=qt,
                punch_list=pl,
            )
        )

    # Coverage check: every task id must have a row, every row must map to
    # exactly one task. Trivially true given the loop above, but we assert it
    # so future refactors don't silently drop tasks.
    assert len(rows) == len(tasks), "coverage failure: row/task count mismatch"

    marker = data.get("project") or args.tasks_json.stem
    new_contents = append_rows_to_plan(args.plan, rows, marker)

    if args.dry_run:
        if args.plan.exists():
            diff = new_contents[len(args.plan.read_text()) :]
        else:
            diff = new_contents
        sys.stdout.write(diff)
        msg = f"\n# dry-run: {len(rows)} chunk(s) ready to append to {args.plan}"
        print(msg, file=sys.stderr)
        return 0

    args.plan.write_text(new_contents)
    print(f"Appended {len(rows)} chunk(s) to {args.plan}:", file=sys.stderr)
    for row in rows:
        print(f"  + {row.id} — {row.title}", file=sys.stderr)
    print(
        "Next: run `python -m orchestrator.cli sync` to load them into state.db.",
        file=sys.stderr,
    )

    # --auto-roadmap: invoke plan-to-roadmap.py for each newly-added chunk.
    if args.auto_roadmap:
        import subprocess

        # Derive the version from --id-prefix. Examples:
        #   --id-prefix V2  → V2
        #   --id-prefix FD  → no numeric group → skip with warning
        version_id: str | None = None
        if args.id_prefix:
            m = re.match(r"^(V\d+)", args.id_prefix)
            if m:
                version_id = m.group(1)

        plan_to_roadmap = Path(__file__).resolve().parent / "plan-to-roadmap.py"
        for row in rows:
            if version_id is None:
                print(
                    f"  --auto-roadmap: skipping {row.id} — cannot derive version "
                    f"from id-prefix {args.id_prefix!r} (must start with V<n>)",
                    file=sys.stderr,
                )
                continue
            result = subprocess.run(
                [
                    sys.executable,
                    str(plan_to_roadmap),
                    "--chunk",
                    row.id,
                    "--version",
                    version_id,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print(
                    f"  --auto-roadmap: {row.id} → roadmap.yaml [{version_id}]",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  --auto-roadmap: WARNING — plan-to-roadmap failed for {row.id}: "
                    f"{result.stderr.strip()}",
                    file=sys.stderr,
                )

    return 0


if __name__ == "__main__":
    sys.exit(main())
