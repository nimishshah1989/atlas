"""Post-session verifier for forge-runner (FR-016..FR-018, FR-021).

Runs four checks in sequence after an inner session completes:
  1. state.db row status == 'DONE'
  2. Latest git commit subject starts with chunk_id prefix
  3. .forge/last-run.json mtime is within the session window (tolerance 120s)
  4. git status --porcelain is empty (ignoring runner-owned paths)

Public API:
    CheckResult     — dataclass with pass/fail details
    run_four_checks(chunk_id, ctx) -> CheckResult
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import structlog

from scripts.forge_runner._time import IST, now_ist
from scripts.forge_runner.state import get_chunk

logger = structlog.get_logger(__name__)

# Paths to exclude from dirty-tree check (runner-owned, always exempt)
_EXEMPT_PREFIXES = (
    ".forge/",
    "scripts/forge_runner/",
)

# NTP + filesystem skew tolerance in seconds
_STAMP_TOLERANCE_SEC = 120


@dataclass
class CheckResult:
    """Result of run_four_checks()."""

    passed: bool
    failed_check: Optional[str]
    detail: str
    needs_sync: bool = field(default=False)


def run_four_checks(chunk_id: str, ctx: Any) -> CheckResult:
    """Run all four post-session verification checks in order.

    Returns a :class:`CheckResult` describing which check (if any) failed.

    Special edge case: if check #1 fails but check #2 passes (a commit with the
    chunk prefix landed but post-chunk sync didn't update state.db), the result
    has ``needs_sync=True, passed=False, failed_check='shipped_needs_sync'``.

    Args:
        chunk_id: The chunk ID to verify.
        ctx:      RunContext-like object; requires .state_db_path, .repo,
                  .session_started_at (datetime | None).
    """
    state_db_path: str = str(ctx.state_db_path)
    repo: Path = Path(str(ctx.repo))

    # ------------------------------------------------------------------ #
    # Check 1: state.db row DONE                                           #
    # ------------------------------------------------------------------ #
    state_db_done, check1_detail = _check_state_db_done(chunk_id, state_db_path)

    # ------------------------------------------------------------------ #
    # Check 2: commit subject starts with chunk_id                        #
    # ------------------------------------------------------------------ #
    commit_ok, check2_detail = _check_commit_prefix(chunk_id, repo)

    if not state_db_done:
        if commit_ok:
            # Ship happened but post-chunk.sh didn't sync state.db → needs_sync
            logger.warning(
                "verifier_needs_sync",
                chunk_id=chunk_id,
                state_detail=check1_detail,
                commit_detail=check2_detail,
            )
            return CheckResult(
                passed=False,
                failed_check="shipped_needs_sync",
                detail=(f"commit landed ({check2_detail}) but state.db not DONE: {check1_detail}"),
                needs_sync=True,
            )
        # Both check 1 and 2 failed — report check 1 (primary gate)
        return CheckResult(
            passed=False,
            failed_check="state_db_not_done",
            detail=check1_detail,
            needs_sync=False,
        )

    if not commit_ok:
        return CheckResult(
            passed=False,
            failed_check="no_commit_with_prefix",
            detail=check2_detail,
            needs_sync=False,
        )

    # ------------------------------------------------------------------ #
    # Check 3: .forge/last-run.json mtime freshness                       #
    # ------------------------------------------------------------------ #
    stamp_ok, check3_detail = _check_stamp_fresh(repo, getattr(ctx, "session_started_at", None))
    if not stamp_ok:
        return CheckResult(
            passed=False,
            failed_check="stamp_not_fresh",
            detail=check3_detail,
            needs_sync=False,
        )

    # ------------------------------------------------------------------ #
    # Check 4: clean working tree (excluding exempt paths)                #
    # ------------------------------------------------------------------ #
    tree_ok, check4_detail = _check_clean_tree(repo)
    if not tree_ok:
        return CheckResult(
            passed=False,
            failed_check="dirty_working_tree",
            detail=check4_detail,
            needs_sync=False,
        )

    logger.info("verifier_all_passed", chunk_id=chunk_id)
    return CheckResult(
        passed=True,
        failed_check=None,
        detail="all four checks passed",
        needs_sync=False,
    )


# ---------------------------------------------------------------------------
# Individual check helpers
# ---------------------------------------------------------------------------


def _check_state_db_done(chunk_id: str, state_db_path: str) -> tuple[bool, str]:
    """Check 1: state.db row has status == 'DONE'."""
    try:
        chunk = get_chunk(chunk_id, state_db_path)
    except Exception as exc:
        return False, f"state.db read error: {exc}"

    if chunk is None:
        return False, f"chunk {chunk_id!r} not found in state.db"

    if chunk.status != "DONE":
        return False, f"chunk {chunk_id!r} status is {chunk.status!r}, not 'DONE'"

    return True, "status=DONE"


def _check_commit_prefix(chunk_id: str, repo: Path) -> tuple[bool, str]:
    """Check 2: one of the last 10 commits starts with chunk_id.

    Scanning a window (not just HEAD) lets post-chunk residual-sync commits
    (e.g. ``forge: <chunk> — post-chunk residual sync``) land on top of the
    real chunk commit without false-alarming.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "log", "-10", "--pretty=%s"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return False, f"git log failed: {exc}"

    if result.returncode != 0:
        return False, f"git log error: {result.stderr.strip()}"

    subjects = [line for line in result.stdout.splitlines() if line.strip()]
    prefix_colon = f"{chunk_id}:"
    prefix_space = f"{chunk_id} "
    for subject in subjects:
        if subject.startswith(prefix_colon) or subject.startswith(prefix_space):
            return True, f"commit subject: {subject!r}"

    head = subjects[0] if subjects else "<none>"
    return False, (
        f"no commit in last 10 starts with {prefix_colon!r} or {prefix_space!r} (HEAD: {head!r})"
    )


def _check_stamp_fresh(repo: Path, session_started_at: Optional[datetime]) -> tuple[bool, str]:
    """Check 3: .forge/last-run.json mtime is within the session window."""
    stamp_path = repo / ".forge" / "last-run.json"

    if not stamp_path.exists():
        return False, f"{stamp_path} does not exist"

    try:
        mtime = stamp_path.stat().st_mtime
    except OSError as exc:
        return False, f"stat error on {stamp_path}: {exc}"

    # Convert mtime to IST-aware datetime for comparison
    stamp_dt = datetime.fromtimestamp(mtime, tz=IST)

    if session_started_at is None:
        # No session start time recorded — fall back to "stamp must be recent"
        threshold = now_ist() - timedelta(seconds=3600)  # 1h grace
    else:
        # Stamp must be >= session_started_at - tolerance
        threshold = session_started_at - timedelta(seconds=_STAMP_TOLERANCE_SEC)

    if stamp_dt >= threshold:
        return True, f"stamp mtime={stamp_dt.isoformat()}"

    return False, (
        f"stamp mtime={stamp_dt.isoformat()} is older than threshold "
        f"{threshold.isoformat()} (session_started_at={session_started_at})"
    )


def _check_clean_tree(repo: Path) -> tuple[bool, str]:
    """Check 4: git status --porcelain is empty, ignoring exempt paths."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return False, f"git status failed: {exc}"

    if result.returncode != 0:
        return False, f"git status error: {result.stderr.strip()}"

    dirty_lines = []
    for line in result.stdout.splitlines():
        # line format: "XY path" or "XY path -> path"
        # Extract the path (everything after the two-char status + space)
        if len(line) < 3:
            continue
        path_part = line[3:]
        # Normalise: strip leading/trailing whitespace
        path_clean = path_part.strip()
        # If rename, take the destination path
        if " -> " in path_clean:
            path_clean = path_clean.split(" -> ")[-1].strip()

        # An exempt prefix, or a parent directory that is a prefix of an
        # exempt path (e.g. "scripts/" as parent of "scripts/forge_runner/")
        if any(path_clean.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            continue
        if any(prefix.startswith(path_clean) for prefix in _EXEMPT_PREFIXES):
            # path_clean is a parent dir of an exempt path (e.g. "scripts/")
            continue
        dirty_lines.append(line)

    if dirty_lines:
        return False, "dirty: " + "; ".join(dirty_lines[:10])

    return True, "working tree clean"
