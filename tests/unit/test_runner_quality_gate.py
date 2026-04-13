"""S1 — orchestrator quality gate iterates per-dim floors, no composite."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator import runner as runner_mod
from orchestrator.plan_loader import ChunkSpec
from orchestrator.runner import Runner, _dims_map


def _make_report(dims: dict[str, dict]) -> dict:
    return {"dims": dims, "generated_at": "2026-04-13T00:00:00+05:30"}


def test_dims_map_reads_s1_shape():
    report = _make_report(
        {
            "security": {"score": 100, "gating": True, "passed": 65, "eligible": 65},
            "code": {"score": 60, "gating": True, "passed": 33, "eligible": 55},
            "backend": {"score": 80, "gating": False, "passed": 40, "eligible": 50},
        }
    )
    out = _dims_map(report)
    assert out["security"]["score"] == 100
    assert out["code"]["gating"] is True
    assert out["backend"]["gating"] is False


def test_dims_map_falls_back_to_legacy_dimensions_list():
    report = {
        "dimensions": [
            {"dimension": "security", "score": 91, "weight": 25},
            {"dimension": "code", "score": 70, "weight": 25},
        ]
    }
    out = _dims_map(report)
    assert out["security"]["score"] == 91
    assert out["security"]["gating"] is True


@pytest.fixture
def runner_with_plan(tmp_path: Path) -> Runner:
    plan_yaml = tmp_path / "plan.yaml"
    plan_yaml.write_text(
        "version: '1.5'\n"
        "name: test\n"
        "settings:\n"
        f"  repo_root: {tmp_path}\n"
        "  quality:\n"
        "    script: .quality/checks.py\n"
        "    report: .quality/report.json\n"
        "    min_per_gating_dim: 80\n"
        "  retry: {max_attempts: 1, backoff_seconds: 0}\n"
        "chunks:\n"
        "  - id: T1\n"
        "    title: test chunk\n"
        "    status: PENDING\n"
    )
    (tmp_path / ".quality").mkdir()
    db_path = tmp_path / "state.db"
    return Runner(plan_yaml, db_path, dry_run=False)


def _spec(targets: dict | None = None) -> ChunkSpec:
    return ChunkSpec(
        id="T1",
        title="test",
        status="PENDING",
        depends_on=[],
        quality_targets=targets or {},
        punch_list=[],
    )


def _patch_subprocess_then_write_report(runner: Runner, report: dict):
    """Make the gate invocation a no-op and pre-stage report.json."""
    report_path = runner.repo_root / ".quality" / "report.json"
    report_path.write_text(json.dumps(report))
    return patch.object(runner_mod.subprocess, "run", return_value=None)


def test_gate_passes_when_all_gating_dims_meet_floor(runner_with_plan: Runner):
    report = _make_report(
        {
            "security": {"score": 100, "gating": True},
            "code": {"score": 85, "gating": True},
            "architecture": {"score": 90, "gating": True},
            "api": {"score": 100, "gating": True},
            "frontend": {"score": 100, "gating": True},
            "backend": {"score": 40, "gating": False},
            "product": {"score": 0, "gating": False},
        }
    )
    with _patch_subprocess_then_write_report(runner_with_plan, report):
        passed, out = runner_with_plan._run_quality_gate(_spec())
    assert passed is True
    # overall_score is the min of gating dims (informational only)
    assert out["overall_score"] == 85


def test_gate_blocks_when_any_gating_dim_below_floor(runner_with_plan: Runner):
    report = _make_report(
        {
            "security": {"score": 100, "gating": True},
            "code": {"score": 60, "gating": True},
            "architecture": {"score": 100, "gating": True},
            "api": {"score": 100, "gating": True},
            "frontend": {"score": 100, "gating": True},
        }
    )
    with _patch_subprocess_then_write_report(runner_with_plan, report):
        passed, _ = runner_with_plan._run_quality_gate(_spec())
    assert passed is False


def test_gate_ignores_non_gating_dim_below_floor(runner_with_plan: Runner):
    report = _make_report(
        {
            "security": {"score": 100, "gating": True},
            "code": {"score": 85, "gating": True},
            "architecture": {"score": 90, "gating": True},
            "api": {"score": 100, "gating": True},
            "frontend": {"score": 100, "gating": True},
            "backend": {"score": 12, "gating": False},
            "product": {"score": 0, "gating": False},
        }
    )
    with _patch_subprocess_then_write_report(runner_with_plan, report):
        passed, _ = runner_with_plan._run_quality_gate(_spec())
    assert passed is True


def test_gate_blocks_when_per_chunk_target_unmet_even_if_floor_met(
    runner_with_plan: Runner,
):
    # Floor is 80, but the chunk targets code: 95.
    report = _make_report(
        {
            "security": {"score": 100, "gating": True},
            "code": {"score": 85, "gating": True},
            "architecture": {"score": 90, "gating": True},
            "api": {"score": 100, "gating": True},
            "frontend": {"score": 100, "gating": True},
        }
    )
    with _patch_subprocess_then_write_report(runner_with_plan, report):
        passed, _ = runner_with_plan._run_quality_gate(_spec({"code": 95}))
    assert passed is False
