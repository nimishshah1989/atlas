"""Smoke tests for the forge orchestrator (C2-C4).

Covers:
  - plan.yaml loads and validates
  - state DB schema applies cleanly to a fresh file
  - state machine rejects illegal transitions
  - dependency-aware next_ready_chunk picks in plan order, not lexical
  - runner end-to-end in --dry-run drives every chunk to DONE in dep order
  - normalization helper handles both list-shape and dict-shape dimensions
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator import state_machine as sm
from orchestrator.plan_loader import load_plan, PlanError
from orchestrator.runner import Runner, _dims_to_dict
from orchestrator.state import StateStore

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = REPO_ROOT / "orchestrator" / "plan.yaml"


def test_plan_loads_and_validates():
    plan = load_plan(PLAN_PATH)
    assert plan.version == "1.5"
    ids = [c.id for c in plan.chunks]
    assert ids[:4] == ["C1", "C2", "C3", "C4"]
    assert "C11" in ids
    # Every dependency must reference a known chunk.
    known = set(ids)
    for c in plan.chunks:
        for dep in c.depends_on:
            assert dep in known


def test_plan_rejects_unknown_dependency(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: '1'\n"
        "name: bad\n"
        "settings: {}\n"
        "chunks:\n"
        "  - id: A\n"
        "    title: a\n"
        "    depends_on: [Z]\n"
    )
    with pytest.raises(PlanError):
        load_plan(bad)


def test_state_store_roundtrip(tmp_path: Path):
    db = tmp_path / "state.db"
    store = StateStore(db)
    store.upsert_chunk("X1", "title", sm.PENDING, "1.0", [])
    chunk = store.get_chunk("X1")
    assert chunk is not None
    assert chunk["status"] == sm.PENDING
    store.set_status("X1", sm.PLANNING, "go")
    updated_chunk = store.get_chunk("X1")
    assert updated_chunk is not None
    assert updated_chunk["status"] == sm.PLANNING


def test_state_machine_rejects_illegal_transition():
    with pytest.raises(sm.IllegalTransition):
        sm.assert_transition(sm.PENDING, sm.DONE)
    sm.assert_transition(sm.PENDING, sm.PLANNING)  # legal


def test_next_ready_uses_natural_sort_not_lexical():
    chunks = [
        {"id": "C2", "status": sm.DONE, "depends_on": []},
        {"id": "C10", "status": sm.PENDING, "depends_on": ["C2"]},
        {"id": "C5", "status": sm.PENDING, "depends_on": ["C2"]},
    ]
    nxt = sm.next_ready_chunk(chunks)
    assert nxt is not None
    assert nxt["id"] == "C5", "C5 must come before C10 with natural sort"


def test_dims_to_dict_accepts_list_and_dict_shape():
    list_shape = [
        {"dimension": "security", "score": 80},
        {"dimension": "code", "score": 42},
    ]
    assert _dims_to_dict(list_shape) == {"security": 80, "code": 42}

    dict_shape = {"security": {"score": 80}, "code": 42}
    assert _dims_to_dict(dict_shape) == {"security": 80, "code": 42}


def test_runner_dry_run_drives_all_chunks_to_done(tmp_path: Path):
    db = tmp_path / "state.db"
    runner = Runner(PLAN_PATH, db, dry_run=True)
    completed = runner.run_all()
    # In dry-run every chunk should land in DONE.
    statuses = {c["id"]: c["status"] for c in runner.store.list_chunks()}
    assert all(s == sm.DONE for s in statuses.values()), statuses
    # Bootstrap chunks (C1-C4) were already DONE before run_all started,
    # so they shouldn't appear in `completed`.
    for boot in ("C1", "C2", "C3", "C4"):
        assert boot not in completed
    # The runnable chunks should appear in dependency order.
    for runnable in ("C5", "C6", "C7", "C8", "C9", "C10", "C11"):
        assert runnable in completed
    assert completed.index("C5") < completed.index("C11")
    assert completed.index("C7") < completed.index("C11")  # C11 deps on C7
    assert completed.index("C8") < completed.index("C9")  # C9 deps on C8
