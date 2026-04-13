"""Tests for scripts/plan-to-roadmap.py.

Covers:
1. Adding a new chunk skeleton under a target version.
2. Idempotent re-add: re-running same args exits 0 with "already present".
3. Cross-version conflict rejection: adding same chunk under different version exits 1.
4. Comment preservation: existing YAML comments survive a round-trip write.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "plan-to-roadmap.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("plan_to_roadmap", SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


MINIMAL_ROADMAP = textwrap.dedent("""\
    # Top-level comment preserved
    versions:
      # V1 comment
      - id: V1
        title: "Market slice"
        goal: "End-to-end V1."
        chunks:
          - id: C1
            plan_ref: true
      - id: V2
        title: "MF slice"
        goal: "MF drill-down."
        chunks: []
      - id: V3
        title: "Simulation"
        goal: "Simulation."
        chunks: []
      - id: V4
        title: "Portfolio"
        goal: "Portfolio."
        chunks: []
      - id: V5
        title: "Intelligence"
        goal: "Intelligence."
        chunks: []
      - id: V6
        title: "TradingView"
        goal: "TV."
        chunks: []
      - id: V7
        title: "ETF"
        goal: "ETF."
        chunks: []
      - id: V8
        title: "Advisor"
        goal: "Advisor."
        chunks: []
      - id: V9
        title: "Retail"
        goal: "Retail."
        chunks: []
      - id: V10
        title: "Qlib"
        goal: "Qlib."
        chunks: []
""")


def _make_roadmap(tmp_path: Path, content: str = MINIMAL_ROADMAP) -> Path:
    p = tmp_path / "roadmap.yaml"
    p.write_text(content)
    return p


def _run(args: list[str], roadmap_path: Path, monkeypatch, capsys) -> int:
    mod = _load_module()
    monkeypatch.setattr(mod, "ROADMAP_YAML", roadmap_path)
    monkeypatch.setattr(sys, "argv", ["plan-to-roadmap.py"] + args)
    try:
        return mod.main()
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0


class TestAddNewChunk:
    def test_appends_skeleton_under_target_version(self, tmp_path, monkeypatch, capsys):
        roadmap = _make_roadmap(tmp_path)
        rc = _run(["--chunk", "C99", "--version", "V2"], roadmap, monkeypatch, capsys)
        assert rc == 0

        content = roadmap.read_text()
        # The chunk should appear in the file
        assert "C99" in content

        # Verify it's under V2 by parsing
        import yaml

        data = yaml.safe_load(content)
        v2 = next(v for v in data["versions"] if v["id"] == "V2")
        chunk_ids = [c["id"] for c in (v2.get("chunks") or [])]
        assert "C99" in chunk_ids

    def test_appended_chunk_has_plan_ref_true(self, tmp_path, monkeypatch, capsys):
        roadmap = _make_roadmap(tmp_path)
        _run(["--chunk", "C77", "--version", "V3"], roadmap, monkeypatch, capsys)

        import yaml

        data = yaml.safe_load(roadmap.read_text())
        v3 = next(v for v in data["versions"] if v["id"] == "V3")
        chunk = next(c for c in v3["chunks"] if c["id"] == "C77")
        assert chunk.get("plan_ref") is True


class TestIdempotentReAdd:
    def test_second_run_exits_zero_with_already_present(self, tmp_path, monkeypatch, capsys):
        roadmap = _make_roadmap(tmp_path)
        # First add
        rc1 = _run(["--chunk", "C55", "--version", "V2"], roadmap, monkeypatch, capsys)
        assert rc1 == 0

        content_after_first = roadmap.read_text()

        # Second add — should be idempotent
        rc2 = _run(["--chunk", "C55", "--version", "V2"], roadmap, monkeypatch, capsys)
        assert rc2 == 0

        content_after_second = roadmap.read_text()
        # File must not change on second run
        assert content_after_first == content_after_second


class TestCrossVersionConflict:
    def test_adding_to_different_version_exits_nonzero(self, tmp_path, monkeypatch, capsys):
        roadmap = _make_roadmap(tmp_path)
        # Add C66 under V2
        rc1 = _run(["--chunk", "C66", "--version", "V2"], roadmap, monkeypatch, capsys)
        assert rc1 == 0

        # Try to add C66 under V3 — should fail
        rc2 = _run(["--chunk", "C66", "--version", "V3"], roadmap, monkeypatch, capsys)
        assert rc2 != 0, "Cross-version conflict should exit non-zero"


class TestCommentPreservation:
    def test_comments_survive_round_trip(self, tmp_path, monkeypatch, capsys):
        roadmap = _make_roadmap(tmp_path)
        original = roadmap.read_text()

        assert "# Top-level comment preserved" in original
        assert "# V1 comment" in original

        rc = _run(["--chunk", "C88", "--version", "V4"], roadmap, monkeypatch, capsys)
        assert rc == 0

        after = roadmap.read_text()
        assert "# Top-level comment preserved" in after, (
            "Top-level comment was lost after round-trip"
        )
        assert "# V1 comment" in after, "V1 comment was lost after round-trip"


class TestInvalidArgs:
    def test_bad_chunk_id_format_exits_nonzero(self, tmp_path, monkeypatch, capsys):
        roadmap = _make_roadmap(tmp_path)
        rc = _run(["--chunk", "chunk-12", "--version", "V2"], roadmap, monkeypatch, capsys)
        assert rc != 0

    def test_bad_version_id_format_exits_nonzero(self, tmp_path, monkeypatch, capsys):
        roadmap = _make_roadmap(tmp_path)
        rc = _run(["--chunk", "C12", "--version", "X2"], roadmap, monkeypatch, capsys)
        assert rc != 0
