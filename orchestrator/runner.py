"""Chunk runner — the heart of the forge orchestrator.

Workflow per chunk:
  1. Pick the next ready chunk (deps satisfied, status=PENDING).
  2. Transition PENDING → PLANNING.
  3. Spawn `claude` with the chunk prompt; stream stdout to a log file.
  4. When the subprocess exits, transition through IMPLEMENTING → TESTING.
     (We collapse these in the prompt; the spawned Claude is responsible for
     planning, implementing, and testing within its single session.)
  5. Run `.quality/checks.py --gate` and parse `.quality/report.json`.
  6. If pass: → QUALITY_GATE → DONE. If fail: → FAILED, retry up to N times.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from . import state_machine as sm
from .plan_loader import ChunkSpec, Plan, load_plan, sync_plan_to_state
from .prompts import build_chunk_prompt
from .state import StateStore

LOG_DIR_NAME = "logs"
SENTINEL = "FORGE_CHUNK_COMPLETE"


def _dims_map(report: dict[str, Any]) -> dict[str, dict]:
    """Return the per-dimension map from an S1+ report.

    S1+ shape: ``{"dims": {name: {score, gating, passed, eligible, checks}}}``.
    Pre-S1 shape: ``{"dimensions": [{dimension, score, weight, ...}, ...]}``.
    Both shapes are normalised to ``{name: {score, gating, ...}}``.
    """
    dims = report.get("dims")
    if isinstance(dims, dict):
        return {k: v for k, v in dims.items() if isinstance(v, dict)}
    legacy = report.get("dimensions")
    out: dict[str, dict] = {}
    if isinstance(legacy, list):
        for entry in legacy:
            if isinstance(entry, dict) and "dimension" in entry:
                out[entry["dimension"]] = {
                    "score": int(entry.get("score", 0) or 0),
                    "gating": True,
                }
    return out


class RunnerError(Exception):
    pass


class Runner:
    def __init__(
        self,
        plan_path: Path,
        db_path: Path,
        *,
        dry_run: bool = False,
    ) -> None:
        self.plan_path = Path(plan_path)
        self.db_path = Path(db_path)
        self.dry_run = dry_run
        self.plan: Plan = load_plan(self.plan_path)
        self.store = StateStore(self.db_path)
        sync_plan_to_state(self.plan, self.store)
        self.repo_root = Path(
            self.plan.settings.get("repo_root", self.plan_path.parent.parent)
        ).resolve()
        self.log_dir = self.plan_path.parent / LOG_DIR_NAME
        self.log_dir.mkdir(exist_ok=True)

    # ---- top-level loops ---------------------------------------------

    def run_one(self) -> Optional[str]:
        """Pick the next ready chunk and run it. Returns chunk id or None."""
        chunks = self.store.list_chunks()
        chunk = sm.next_ready_chunk(chunks)
        if chunk is None:
            return None
        self._run_chunk(chunk["id"])
        return chunk["id"]

    def run_all(self) -> list[str]:
        """Run chunks until none are ready or one ends BLOCKED."""
        completed: list[str] = []
        while True:
            cid = self.run_one()
            if cid is None:
                break
            final = self.store.get_chunk(cid)
            completed.append(cid)
            if final and final["status"] == sm.BLOCKED:
                break
        return completed

    # ---- single chunk -------------------------------------------------

    def _run_chunk(self, chunk_id: str) -> None:
        try:
            self._run_chunk_inner(chunk_id)
        except BaseException as exc:  # noqa: BLE001 — runner boundary, catch signals too
            # Never leave state stranded at PLANNING/RUNNING on signal or crash.
            # A stranded chunk blocks every future run; record the failure first,
            # then re-raise so the CLI still exits non-zero.
            try:
                self.store.set_status(
                    chunk_id,
                    sm.FAILED,
                    f"runner aborted: {type(exc).__name__}: {exc}",
                )
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
            raise

    def _run_chunk_inner(self, chunk_id: str) -> None:
        spec = next((c for c in self.plan.chunks if c.id == chunk_id), None)
        if spec is None:
            raise RunnerError(f"chunk {chunk_id} not in plan")

        max_attempts = int(self.plan.settings.get("retry", {}).get("max_attempts", 3))
        backoff = int(self.plan.settings.get("retry", {}).get("backoff_seconds", 30))

        while True:
            attempt = self.store.record_attempt(chunk_id)
            self._safe_transition(chunk_id, sm.PLANNING, "starting attempt")

            try:
                self._spawn_claude(spec, attempt)
            except Exception as exc:  # noqa: BLE001 — runner boundary
                self.store.record_attempt(chunk_id, error=str(exc))
                self._safe_transition(chunk_id, sm.FAILED, f"spawn error: {exc}")
                if attempt >= max_attempts:
                    self._safe_transition(chunk_id, sm.BLOCKED, "max attempts exceeded")
                    return
                time.sleep(backoff)
                continue

            # The Claude session is responsible for moving through the work.
            # We collapse PLANNING → IMPLEMENTING → TESTING here so the audit
            # log shows progress, even though one process did all three.
            self._safe_transition(chunk_id, sm.IMPLEMENTING, "claude exited")
            self._safe_transition(chunk_id, sm.TESTING, "running quality gate")
            self._safe_transition(chunk_id, sm.QUALITY_GATE, "scoring")

            passed, report = self._run_quality_gate(spec)
            self.store.record_quality_run(
                chunk_id=chunk_id,
                attempt=attempt,
                overall_score=int(report.get("overall_score", 0)),
                passed=passed,
                report=report,
            )

            if passed:
                self._safe_transition(chunk_id, sm.DONE, "quality gate passed")
                self._run_post_chunk_hook(chunk_id)
                return

            self.store.record_attempt(
                chunk_id,
                error=f"quality gate failed at attempt {attempt}",
            )
            self._safe_transition(
                chunk_id, sm.FAILED, "quality gate did not meet thresholds"
            )
            if attempt >= max_attempts:
                self._safe_transition(
                    chunk_id,
                    sm.BLOCKED,
                    f"max attempts ({max_attempts}) exhausted",
                )
                return
            time.sleep(backoff)

    # ---- helpers ------------------------------------------------------

    def _safe_transition(self, chunk_id: str, to_state: str, reason: str) -> None:
        chunk_state = self.store.get_chunk(chunk_id)
        if chunk_state is None:
            raise RunnerError(f"{chunk_id}: chunk not found")
        current = chunk_state["status"]
        try:
            sm.assert_transition(current, to_state)
        except sm.IllegalTransition as exc:
            raise RunnerError(f"{chunk_id}: {exc} (reason: {reason})") from exc
        self.store.set_status(chunk_id, to_state, reason)

    def _spawn_claude(self, spec: ChunkSpec, attempt: int) -> None:
        chunk_info = self.store.get_chunk(spec.id)
        report = self._read_quality_report()
        prompt = build_chunk_prompt(
            self.plan,
            spec,
            attempt=attempt,
            last_error=chunk_info.get("last_error") if chunk_info else None,
            quality_report=report,
        )

        log_path = self.log_dir / f"{spec.id}_attempt{attempt}.log"
        session_id = self.store.open_session(
            chunk_id=spec.id,
            attempt=attempt,
            phase="CLAUDE",
            log_path=log_path,
        )

        claude_cfg = self.plan.settings.get("claude", {})
        binary = claude_cfg.get("binary", "claude")
        extra = list(claude_cfg.get("extra_args") or [])
        cmd = [binary, "-p", prompt, *extra]

        if self.dry_run:
            log_path.write_text(
                f"DRY RUN — would have spawned:\n{' '.join(cmd[:2])} <prompt>\n"
                f"\n--- prompt ---\n{prompt}\n"
            )
            self.store.close_session(session_id, pid=None, exit_code=0)
            return

        exit_code: int = 1
        proc = None
        with log_path.open("w", buffering=1) as log_fh:
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=self.repo_root,
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    env={**os.environ},
                    start_new_session=True,
                )
                exit_code = proc.wait()
            finally:
                self.store.close_session(
                    session_id,
                    pid=proc.pid if proc else None,
                    exit_code=exit_code,
                )
        if exit_code != 0:
            raise RunnerError(
                f"claude exited {exit_code} for {spec.id}; see {log_path}"
            )

    def _run_quality_gate(self, spec: ChunkSpec) -> tuple[bool, dict[str, Any]]:
        """S1 gate: per-dimension floors only, no composite.

        Two stops:
          1. Every dimension flagged ``gating: true`` in .quality/report.json
             must score ≥ ``settings.quality.min_per_gating_dim`` (default 80).
          2. Every dimension named in ``spec.quality_targets`` must hit its
             per-chunk target (which can be stricter than the global floor).

        Non-gating dimensions (backend, product until V1.6 R1) are recorded
        in the report for visibility but do not block the gate.
        """
        q_cfg = self.plan.settings.get("quality", {})
        script = self.repo_root / q_cfg.get("script", ".quality/checks.py")
        floor = int(q_cfg.get("min_per_gating_dim", 80))

        if self.dry_run:
            report = self._read_quality_report() or {"dims": {}}
            report.setdefault("overall_score", 100)
            return True, report

        subprocess.run(
            [sys.executable, str(script), "--gate"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        report = self._read_quality_report() or {}

        if not report:
            return False, {"overall_score": 0, "error": "no report"}

        dims = _dims_map(report)

        # Stop 1: global per-gating-dim floor. Iterate every gating dim so
        # one strong dim can never carry a weak one — the whole point of S1.
        gating_failed = [
            name
            for name, d in dims.items()
            if d.get("gating", False) and int(d.get("score", 0) or 0) < floor
        ]

        # Stop 2: per-chunk targets. May be stricter than the global floor
        # and may apply to a subset of dimensions.
        target_failed = [
            dim
            for dim, target in (spec.quality_targets or {}).items()
            if int(dims.get(dim, {}).get("score", 0) or 0) < int(target)
        ]

        # Stamp a synthetic overall_score (min of all gating dims) so legacy
        # callers and the audit log have a single number to record. The
        # number is informational only — it does NOT gate.
        gating_scores = [
            int(d.get("score", 0) or 0) for d in dims.values() if d.get("gating", False)
        ]
        report["overall_score"] = min(gating_scores) if gating_scores else 0

        if gating_failed or target_failed:
            return False, report
        return True, report

    def _run_post_chunk_hook(self, chunk_id: str) -> None:
        """Keep git/EC2/wiki in sync after a chunk lands DONE.

        Driven by `settings.post_chunk` in plan.yaml. Failures are logged
        but do not reopen the DONE transition — we never want a passing
        quality gate to silently regress because the push or compile
        flaked. The session row captures the exit code for audit.
        """
        cfg = self.plan.settings.get("post_chunk") or {}
        if not cfg.get("enabled", True):
            return
        script_rel = cfg.get("script", "scripts/post-chunk.sh")
        script = (self.repo_root / script_rel).resolve()
        if not script.exists():
            return
        if self.dry_run:
            return

        log_path = self.log_dir / f"{chunk_id}_post_chunk.log"
        session_id = self.store.open_session(
            chunk_id=chunk_id,
            attempt=0,
            phase="POST_CHUNK",
            log_path=log_path,
        )
        exit_code = 1
        try:
            with log_path.open("w") as log_fh:
                proc = subprocess.run(
                    [str(script), chunk_id],
                    cwd=self.repo_root,
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    env={**os.environ},
                )
                exit_code = proc.returncode
        finally:
            self.store.close_session(session_id, pid=None, exit_code=exit_code)

    def _read_quality_report(self) -> dict[str, Any] | None:
        q_cfg = self.plan.settings.get("quality", {})
        report_path = self.repo_root / q_cfg.get("report", ".quality/report.json")
        if not report_path.exists():
            return None
        try:
            return json.loads(report_path.read_text())
        except json.JSONDecodeError:
            return None
