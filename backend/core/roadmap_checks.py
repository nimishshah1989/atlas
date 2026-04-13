"""Check evaluator — turns declarative step specs into live ok/fail/error results.

Check types:
  file_exists  — Path relative to REPO_ROOT must exist. No absolute paths, no ..
  command      — subprocess.run(list, shell=False, timeout=5s). No string commands.
  http_ok      — httpx.get(url, timeout=5). localhost/127.0.0.1 only.
  db_query     — parameterized SQL against state.db. Rejects ; -- /*
  smoke_list   — shells to scripts/smoke-probe.sh. Always slow (opt-in only).

All checks: hard 5s per-check timeout.
smoke_list results: 60s TTL cache (separate from endpoint cache).
"""

import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import httpx
import structlog

from backend.core.roadmap_loader import Check

log = structlog.get_logger()

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_STATE_DB = _REPO_ROOT / "orchestrator" / "state.db"
_SMOKE_SCRIPT = _REPO_ROOT / "scripts" / "smoke-probe.sh"

# Allowed command blocklist (belt-and-suspenders in addition to shell=False)
_BLOCKED_COMMANDS = frozenset(
    [
        "rm",
        "rmdir",
        "dd",
        "mkfs",
        "fdisk",
        "shutdown",
        "reboot",
        "halt",
        "poweroff",
        "kill",
        "killall",
        "pkill",
        "su",
        "sudo",
        "chown",
        "chmod",
        "curl",
        "wget",
        "nc",
        "ncat",
        "netcat",
        "bash",
        "sh",
        "zsh",
        "fish",
        "python",
        "python3",
        "perl",
        "ruby",
        "node",
        "exec",
        "eval",
    ]
)

# smoke_list 60s result cache: {file: (result_dict, timestamp)}
_smoke_cache: dict[str, tuple[dict[str, Any], float]] = {}
_SMOKE_CACHE_TTL = 60.0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def evaluate_check(
    check: Optional[Check],
    evaluate_slow: bool = False,
) -> tuple[str, str]:
    """Evaluate a single check spec.

    Returns (check_result, detail) where check_result is one of:
      "ok" | "fail" | "slow-skipped" | "error"
    """
    if check is None:
        return "ok", ""

    check_type = check.type

    try:
        if check_type == "file_exists":
            return _check_file_exists(check)
        elif check_type == "command":
            return _check_command(check)
        elif check_type == "http_ok":
            return _check_http_ok(check)
        elif check_type == "db_query":
            return _check_db_query(check)
        elif check_type == "smoke_list":
            return _check_smoke_list(check, evaluate_slow)
        else:
            return "error", f"unknown-check-type:{check_type}"
    except Exception as exc:
        log.warning("check_evaluate_exception", check_type=check_type, error=str(exc))
        return "error", str(exc)[:200]


# ---------------------------------------------------------------------------
# file_exists
# ---------------------------------------------------------------------------


def _check_file_exists(check: Check) -> tuple[str, str]:
    path_str = check.path or ""
    if not path_str:
        return "error", "missing-path"

    # Reject absolute paths
    if Path(path_str).is_absolute():
        return "error", "absolute-path-blocked"

    # Reject .. traversal
    if ".." in path_str.split("/"):
        return "error", "path-traversal-blocked"

    # Also reject any .. substring in Windows-style paths
    if ".." in path_str:
        return "error", "path-traversal-blocked"

    target = _REPO_ROOT / path_str
    exists = target.exists()
    return ("ok", "") if exists else ("fail", f"not-found:{path_str}")


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------


def _check_command(check: Check) -> tuple[str, str]:
    cmd = check.cmd
    if cmd is None:
        return "error", "missing-cmd"

    # Must be a list, not a string
    if isinstance(cmd, str):
        return "error", "cmd-must-be-list"

    if not cmd:
        return "error", "empty-cmd"

    # Blocklist check (first token)
    base_cmd = Path(cmd[0]).name.lower()
    if base_cmd in _BLOCKED_COMMANDS:
        return "error", f"blocked-command:{base_cmd}"

    # Sandbox: no shell, restricted env, repo cwd, 5s timeout
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    try:
        proc = subprocess.run(
            cmd,
            shell=False,
            cwd=str(_REPO_ROOT),
            env=env,
            timeout=5,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        return "error", "timeout"
    except FileNotFoundError as exc:
        return "error", f"command-not-found:{exc}"
    except OSError as exc:
        return "error", f"os-error:{exc}"

    if proc.returncode == 0:
        return "ok", ""
    else:
        stderr = proc.stderr.decode("utf-8", errors="replace")[:200]
        return "fail", stderr or f"exit-code:{proc.returncode}"


# ---------------------------------------------------------------------------
# http_ok
# ---------------------------------------------------------------------------


def _check_http_ok(check: Check) -> tuple[str, str]:
    url = check.url or ""
    if not url:
        return "error", "missing-url"

    # Only allow localhost/127.0.0.1
    if not (
        url.startswith("http://localhost:")
        or url.startswith("http://127.0.0.1:")
        or url == "http://localhost"
        or url == "http://127.0.0.1"
    ):
        return "error", "external-url-blocked"

    try:
        resp = httpx.get(url, timeout=5.0)
        if 200 <= resp.status_code < 300:
            return "ok", ""
        return "fail", f"status:{resp.status_code}"
    except httpx.TimeoutException:
        return "error", "timeout"
    except Exception as exc:
        return "error", str(exc)[:200]


# ---------------------------------------------------------------------------
# db_query
# ---------------------------------------------------------------------------

_UNSAFE_SQL_PATTERN = re.compile(r";|--|/\*")


def _check_db_query(check: Check) -> tuple[str, str]:
    sql = check.sql or ""
    if not sql:
        return "error", "missing-sql"

    # Reject unsafe patterns
    if _UNSAFE_SQL_PATTERN.search(sql):
        return "error", "unsafe-sql"

    # Only target state.db for now
    target = check.target or "state.db"
    if target not in ("state.db", "state"):
        return "error", f"unknown-db-target:{target}"

    if not _STATE_DB.exists():
        return "error", "state-db-not-found"

    try:
        conn = sqlite3.connect(str(_STATE_DB))
        conn.execute("PRAGMA query_only = ON")
        try:
            cursor = conn.execute(sql)
            row = cursor.fetchone()
            if row is None:
                return "fail", "no-rows"
            row_value = row[0]
            if row_value:
                return "ok", ""
            return "fail", f"zero-result:{row_value}"
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        return "error", f"sql-error:{exc}"
    except Exception as exc:
        return "error", str(exc)[:200]


# ---------------------------------------------------------------------------
# smoke_list
# ---------------------------------------------------------------------------


def _check_smoke_list(check: Check, evaluate_slow: bool) -> tuple[str, str]:
    """Run scripts/smoke-probe.sh and parse summary.

    Always implicitly slow. Returns slow-skipped unless evaluate_slow=True.
    Caches results 60s to avoid repeated curl probes.
    """
    list_path_str = check.file or "scripts/smoke-endpoints.txt"

    # Validate path stays under scripts/
    list_path = Path(list_path_str)
    if list_path.is_absolute():
        return "error", "unsafe-list-path"
    parts = list_path.parts
    if not parts or parts[0] != "scripts":
        return "error", "unsafe-list-path"
    if ".." in parts:
        return "error", "unsafe-list-path"

    if not evaluate_slow:
        return "slow-skipped", ""

    # Check cache
    cache_key = list_path_str
    now = time.monotonic()
    cached = _smoke_cache.get(cache_key)
    if cached is not None:
        result_dict, ts = cached
        if now - ts < _SMOKE_CACHE_TTL:
            return result_dict["check"], result_dict["detail"]

    # Run smoke probe
    probe_result = _run_smoke_probe(list_path_str)
    _smoke_cache[cache_key] = (probe_result, now)
    return probe_result["check"], probe_result["detail"]


def _run_smoke_probe(list_path_str: str) -> dict[str, Any]:
    if not _SMOKE_SCRIPT.exists():
        return {"check": "error", "detail": "smoke-probe-script-not-found"}

    abs_list_path = _REPO_ROOT / list_path_str
    if not abs_list_path.exists():
        return {"check": "error", "detail": f"smoke-list-not-found:{list_path_str}"}

    env = {**os.environ, "SMOKE_QUIET": "1"}
    try:
        smoke_proc = subprocess.run(
            [str(_SMOKE_SCRIPT), str(abs_list_path)],
            shell=False,
            cwd=str(_REPO_ROOT),
            env=env,
            timeout=60,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        return {"check": "error", "detail": "smoke-probe-timeout"}
    except OSError as exc:
        return {"check": "error", "detail": str(exc)[:200]}

    stdout = smoke_proc.stdout.decode("utf-8", errors="replace")
    return _parse_smoke_output(stdout)


_SMOKE_SUMMARY_RE = re.compile(
    r"summary:\s*total=(\d+)\s+passed=(\d+)\s+hard_fail=(\d+)\s+soft_skip=(\d+)",
    re.IGNORECASE,
)


def _parse_smoke_output(stdout: str) -> dict[str, Any]:
    """Parse smoke-probe.sh stdout for summary line."""
    match = _SMOKE_SUMMARY_RE.search(stdout)
    if not match:
        # Try to find any summary-like info
        log.warning("smoke_summary_not_found_in_output", stdout_snippet=stdout[:200])
        return {"check": "error", "detail": "smoke-summary-parse-failed"}

    total = int(match.group(1))
    passed = int(match.group(2))
    hard_fail = int(match.group(3))
    soft_skip = int(match.group(4))

    detail = f"total={total} passed={passed} hard_fail={hard_fail} soft_skip={soft_skip}"

    if hard_fail == 0:
        return {"check": "ok", "detail": detail}
    return {"check": "fail", "detail": detail}
