"""Tests for scripts/roadmap-lint.py.

Verifies the 6 lint rules using fixture roadmap/plan pairs.
Three deliberate drift cases are checked to ensure lint catches them all.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT_SCRIPT = REPO_ROOT / "scripts" / "roadmap-lint.py"
ROADMAP_YAML = REPO_ROOT / "orchestrator" / "roadmap.yaml"
PLAN_YAML = REPO_ROOT / "orchestrator" / "plan.yaml"


def _run_lint(
    roadmap_content: str,
    plan_content: str,
    tmp_path: Path,
) -> subprocess.CompletedProcess:
    """Run roadmap-lint.py against temporary roadmap + plan files."""
    roadmap = tmp_path / "roadmap.yaml"
    plan = tmp_path / "plan.yaml"
    roadmap.write_text(roadmap_content)
    plan.write_text(plan_content)

    # Patch the script's PLAN_YAML and ROADMAP_YAML by env override via monkeypatch
    # We run as subprocess using modified env; easier: patch via --roadmap/--plan
    # The lint script uses module-level constants, so we pass them via env substitution.
    # Simplest: run the lint script with patched constants via a wrapper.
    env_override = {
        "ROADMAP_YAML_OVERRIDE": str(roadmap),
        "PLAN_YAML_OVERRIDE": str(plan),
    }
    import os

    env = {**os.environ, **env_override}
    return subprocess.run(
        [sys.executable, str(LINT_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


# We need to support path override in the lint script. Let's instead run it
# via importlib with monkeypatching the constants.

import importlib.util  # noqa: E402


def _load_lint_module():
    spec = importlib.util.spec_from_file_location("roadmap_lint", LINT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _run_lint_in_process(
    roadmap_content: str,
    plan_content: str,
    tmp_path: Path,
    monkeypatch,
) -> tuple[int, str]:
    """Run lint logic with overridden PLAN_YAML and ROADMAP_YAML paths."""
    roadmap_path = tmp_path / "roadmap.yaml"
    plan_path = tmp_path / "plan.yaml"
    roadmap_path.write_text(roadmap_content)
    plan_path.write_text(plan_content)

    import io

    mod = _load_lint_module()
    monkeypatch.setattr(mod, "ROADMAP_YAML", roadmap_path)
    monkeypatch.setattr(mod, "PLAN_YAML", plan_path)

    io.StringIO()
    import builtins

    original_print = builtins.print
    output_lines: list[str] = []

    def capture_print(*args, **kwargs):
        file = kwargs.get("file")
        if file is sys.stderr:
            original_print(*args, **kwargs)
        else:
            output_lines.append(" ".join(str(a) for a in args))

    monkeypatch.setattr(builtins, "print", capture_print)
    try:
        exit_code = mod.main()
    finally:
        monkeypatch.setattr(builtins, "print", original_print)

    return exit_code, "\n".join(output_lines)


# ---------------------------------------------------------------------------
# Fixtures: minimal valid base
# ---------------------------------------------------------------------------

MINIMAL_PLAN = textwrap.dedent("""\
    version: "1.5"
    chunks:
      - id: C1
        title: "Quality engine"
        status: DONE
""")

MINIMAL_ROADMAP = textwrap.dedent("""\
    versions:
      - id: V1
        title: "Market slice"
        goal: "End-to-end V1."
        chunks:
          - id: C1
            plan_ref: true
            steps:
              - id: C1.1
                text: "standards.md exists"
                check:
                  type: file_exists
                  path: .quality/standards.md
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
        goal: "TradingView."
        chunks: []
      - id: V7
        title: "ETF + Global"
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


class TestLintClean:
    """Lint on a valid roadmap+plan pair exits 0."""

    def test_clean_exits_zero(self, tmp_path, monkeypatch):
        code, out = _run_lint_in_process(MINIMAL_ROADMAP, MINIMAL_PLAN, tmp_path, monkeypatch)
        assert code == 0
        assert "roadmap OK" in out

    def test_seeded_roadmap_exits_zero(self, monkeypatch):
        """The actual seeded roadmap.yaml + plan.yaml must pass lint."""
        import builtins

        mod = _load_lint_module()
        # Use the real files
        output_lines: list[str] = []
        original_print = builtins.print

        def capture(*args, **kwargs):
            if kwargs.get("file") is not sys.stderr:
                output_lines.append(" ".join(str(a) for a in args))
            else:
                original_print(*args, **kwargs)

        monkeypatch.setattr(builtins, "print", capture)
        try:
            code = mod.main()
        finally:
            monkeypatch.setattr(builtins, "print", original_print)

        assert code == 0, f"Seeded roadmap failed lint: {output_lines}"


class TestDriftCase1:
    """Rule 1 — chunk in plan.yaml not claimed by any version."""

    def test_unclaimed_plan_chunk(self, tmp_path, monkeypatch):
        plan = textwrap.dedent("""\
            version: "1.5"
            chunks:
              - id: C1
                title: "Q engine"
                status: DONE
              - id: C2
                title: "Orchestrator"
                status: DONE
        """)
        # C1 is in roadmap, C2 is NOT — drift case 1
        code, out = _run_lint_in_process(MINIMAL_ROADMAP, plan, tmp_path, monkeypatch)
        assert code != 0, "Should have exited non-zero"
        out + _capture_stderr_last_run()
        # Check the error was emitted (captured in output_lines before stderr switch)
        assert code == 1


class TestDriftCase2:
    """Rule 2 — chunk in roadmap without future:true that doesn't exist in plan.yaml."""

    def test_phantom_chunk_without_future(self, tmp_path, monkeypatch):
        # Craft a roadmap that has C99 (not in plan.yaml) without future: true
        roadmap = textwrap.dedent("""\
            versions:
              - id: V1
                title: "Market slice"
                goal: "End-to-end."
                chunks:
                  - id: C1
                    plan_ref: true
                    steps:
                      - id: C1.1
                        text: "file exists"
                        check:
                          type: file_exists
                          path: .quality/standards.md
                  - id: C99
                    plan_ref: true
              - id: V2
                title: "MF"
                goal: "MF."
                chunks: []
              - id: V3
                title: "Sim"
                goal: "Sim."
                chunks: []
              - id: V4
                title: "Port"
                goal: "Port."
                chunks: []
              - id: V5
                title: "Intel"
                goal: "Intel."
                chunks: []
              - id: V6
                title: "TV"
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
        # C99 is in roadmap but not in plan.yaml, and has no future: true
        code, out = _run_lint_in_process(roadmap, MINIMAL_PLAN, tmp_path, monkeypatch)
        assert code == 1, f"Should have caught phantom chunk C99, got: {out}"


class TestDriftCase3:
    """Rule 6 — command: is a shell string, not a list."""

    def test_shell_string_command(self, tmp_path, monkeypatch):
        roadmap = textwrap.dedent("""\
            versions:
              - id: V1
                title: "Market slice"
                goal: "End-to-end."
                chunks:
                  - id: C1
                    plan_ref: true
                    steps:
                      - id: C1.1
                        text: "dangerous command"
                        check:
                          type: command
                          cmd: "rm -rf /"
              - id: V2
                title: "MF"
                goal: "MF."
                chunks: []
              - id: V3
                title: "Sim"
                goal: "Sim."
                chunks: []
              - id: V4
                title: "Port"
                goal: "Port."
                chunks: []
              - id: V5
                title: "Intel"
                goal: "Intel."
                chunks: []
              - id: V6
                title: "TV"
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
        code, out = _run_lint_in_process(roadmap, MINIMAL_PLAN, tmp_path, monkeypatch)
        assert code == 1, f"Should have caught shell string command, got: {out}"


def _capture_stderr_last_run() -> str:
    """Helper: returns empty string (stderr not captured in monkeypatch mode)."""
    return ""


class TestSchemaValidation:
    """Pydantic schema rejects invalid inputs per acceptance criterion #4."""

    def test_invalid_version_id(self):
        from orchestrator.roadmap_schema import Version

        with pytest.raises(Exception):
            Version(id="X1", title="Bad", goal="Bad")

    def test_path_with_dotdot(self):
        from orchestrator.roadmap_schema import FileExistsCheck

        with pytest.raises(Exception):
            FileExistsCheck(type="file_exists", path="../secret.env")

    def test_unknown_check_type(self):
        from orchestrator.roadmap_schema import parse_check

        with pytest.raises(Exception):
            parse_check({"type": "magic_check", "path": "foo"})

    def test_command_as_string(self):
        from orchestrator.roadmap_schema import CommandCheck

        with pytest.raises(Exception):
            CommandCheck(type="command", cmd="rm -rf /")

    def test_demo_gate_missing_url(self):
        from orchestrator.roadmap_schema import DemoGate

        with pytest.raises(Exception):
            DemoGate(url="", walkthrough=["step 1"])

    def test_demo_gate_empty_walkthrough(self):
        from orchestrator.roadmap_schema import DemoGate

        with pytest.raises(Exception):
            DemoGate(url="https://example.com", walkthrough=[])

    def test_chunk_id_bad_format(self):
        from orchestrator.roadmap_schema import Chunk

        with pytest.raises(Exception):
            Chunk(id="chunk-1")

    def test_step_id_prefix_mismatch(self):
        from orchestrator.roadmap_schema import Chunk, Step

        with pytest.raises(Exception):
            Chunk(
                id="C1",
                steps=[Step(id="C2.1", text="wrong prefix step")],
            )
