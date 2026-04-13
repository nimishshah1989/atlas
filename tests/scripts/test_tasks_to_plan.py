"""Tests for scripts/tasks-to-plan.py — the /forge-build → orchestrator bridge.

Covers the three paths a V2+ autonomous build leans on:

1. Deriving quality_targets from a task's files list (backend vs frontend vs
   devops) — if this drifts, the orchestrator's per-dimension floors stop
   matching reality and chunks either pass with too-low bars or block forever.
2. Extracting punch_list from a chunk spec's "Acceptance criteria" section.
   When /forge-build Phase 2 writes per-chunk specs, the bridge must pull the
   acceptance bullets verbatim; a regression here ships chunks with empty
   punch lists and the runner has no idea when they're done.
3. Id remapping under --id-prefix. V2 chunks emitted by /forge-build will
   conflict with FD-* dashboard chunks unless the bridge rewrites them; a
   regression here collides rows in plan.yaml and breaks sync.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "tasks-to-plan.py"


def _load_module():
    """Load tasks-to-plan.py as a module despite the dash in the filename."""
    spec = importlib.util.spec_from_file_location("tasks_to_plan", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tasks_to_plan"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


# --- quality target derivation ----------------------------------------------


def test_derive_quality_targets_backend_routes(mod) -> None:
    out = mod.derive_quality_targets(["backend/routes/system.py", "tests/routes/test_system.py"])
    assert "api" in out and out["api"] >= 80
    assert "code" in out and out["code"] >= 70


def test_derive_quality_targets_frontend(mod) -> None:
    out = mod.derive_quality_targets(
        [
            "frontend/src/components/forge/HeartbeatStrip.tsx",
            "frontend/src/app/forge/page.tsx",
        ]
    )
    assert "frontend" in out
    assert "api" not in out  # pure frontend chunk must not require api floor


def test_derive_quality_targets_devops_scripts(mod) -> None:
    out = mod.derive_quality_targets(["scripts/post-chunk.sh"])
    assert "devops" in out
    assert "frontend" not in out


def test_derive_quality_targets_empty_files(mod) -> None:
    """Empty file list = no targets. Runner still applies global floors."""
    assert mod.derive_quality_targets([]) == {}


# --- acceptance-criteria extraction -----------------------------------------


def test_extract_acceptance_bullets_numbered(tmp_path, mod) -> None:
    spec = tmp_path / "chunk-x.md"
    spec.write_text(
        "# Chunk X — Example\n\n"
        "## Goal\n\nSomething.\n\n"
        "## Acceptance criteria\n\n"
        "1. First bullet.\n"
        "2. Second bullet with `code`.\n"
        "3. Third.\n\n"
        "## Out of scope\n\n"
        "- not counted\n"
    )
    bullets = mod.extract_acceptance_bullets(spec)
    assert bullets == [
        "First bullet.",
        "Second bullet with `code`.",
        "Third.",
    ]


def test_extract_acceptance_bullets_dash(tmp_path, mod) -> None:
    spec = tmp_path / "chunk-y.md"
    spec.write_text("## Acceptance criteria\n\n- alpha\n- beta\n\n## Next section\n\n- excluded\n")
    assert mod.extract_acceptance_bullets(spec) == ["alpha", "beta"]


def test_extract_acceptance_bullets_missing_section(tmp_path, mod) -> None:
    spec = tmp_path / "chunk-z.md"
    spec.write_text("# no acceptance header here\n\nbody\n")
    assert mod.extract_acceptance_bullets(spec) == []


def test_extract_acceptance_bullets_missing_file(mod) -> None:
    assert mod.extract_acceptance_bullets(Path("/does/not/exist.md")) == []


# --- id remapping ------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,prefix,expected",
    [
        ("FD-1", "V2", "V2-1"),
        ("FD-10", "V3", "V3-10"),
        ("C11", "V2", "V2-11"),
        ("FD-1", None, "FD-1"),
        ("weird", "V2", "V2-weird"),
    ],
)
def test_remap_id(mod, raw, prefix, expected) -> None:
    assert mod.remap_id(raw, prefix) == expected


def test_remap_deps_preserves_order(mod) -> None:
    assert mod.remap_deps(["FD-1", "FD-2"], "V2") == ["V2-1", "V2-2"]


# --- end-to-end append to a fresh plan --------------------------------------


def test_append_rows_to_plan_produces_valid_yaml_block(tmp_path, mod) -> None:
    plan = tmp_path / "plan.yaml"
    plan.write_text("version: '1.5'\nchunks:\n  - id: C1\n    title: existing\n")

    row = mod.ChunkRow(
        id="V2-1",
        title="Test chunk",
        depends_on=["C1"],
        quality_targets={"api": 85, "code": 80},
        punch_list=["Endpoint returns 200", 'Quote "inside" bullet'],
    )
    new_contents = mod.append_rows_to_plan(plan, [row], marker="V2 test block")

    # existing content preserved verbatim
    assert new_contents.startswith("version: '1.5'\nchunks:\n  - id: C1\n")
    # new row present
    assert "- id: V2-1" in new_contents
    assert 'title: "Test chunk"' in new_contents
    assert "depends_on: [C1]" in new_contents
    assert "api: 85" in new_contents
    assert "code: 80" in new_contents
    # quotes inside punch_list items escaped, not bare
    assert '\\"inside\\"' in new_contents
    # marker comment included
    assert "V2 test block" in new_contents


def test_existing_plan_ids_detects_all(tmp_path, mod) -> None:
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        "chunks:\n  - id: C1\n    title: a\n  - id: C2\n    title: b\n  - id: FD-1\n    title: c\n"
    )
    assert mod.existing_plan_ids(plan) == {"C1", "C2", "FD-1"}


# --- full-script smoke test via subprocess ----------------------------------


def test_cli_dry_run_does_not_modify_plan(tmp_path, mod) -> None:
    """Full CLI path: build tasks.json + plan.yaml, run --dry-run, assert
    plan.yaml is byte-identical afterwards and the printed diff contains
    every task id."""
    import subprocess

    tasks = {
        "project": "test",
        "chunks": [
            {
                "id": "T-1",
                "name": "Backend chunk",
                "files": ["backend/routes/foo.py"],
                "acceptance": "Does the thing.",
                "depends_on": [],
            },
            {
                "id": "T-2",
                "name": "Frontend chunk",
                "files": ["frontend/src/app/foo.tsx"],
                "acceptance": "Renders.",
                "depends_on": ["T-1"],
            },
        ],
    }
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(json.dumps(tasks))
    plan_path = tmp_path / "plan.yaml"
    plan_path.write_text("chunks:\n  - id: C1\n    title: existing\n")

    before = plan_path.read_text()
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(tasks_path),
            "--plan",
            str(plan_path),
            "--dry-run",
            "--id-prefix",
            "V9",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert plan_path.read_text() == before  # dry-run never writes
    assert "V9-1" in result.stdout
    assert "V9-2" in result.stdout
    assert "depends_on: [V9-1]" in result.stdout
