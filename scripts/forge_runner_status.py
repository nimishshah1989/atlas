"""forge-runner-status — Live status reader for forge-runner (T034).

Reads ``.forge/runner-state.json`` (or ``--log-dir``), determines state and
health, and prints a one-line summary.  Supports ``--json``, ``--watch``,
and ``--tail`` flags per contracts/status-cli.md.

Import strategy: this file lives at ``scripts/forge_runner_status.py`` and is
invoked as ``python -m scripts.forge_runner_status``.  Because the repo root
is the Python path root (``PYTHONPATH=.`` or ``sys.path.insert(0, repo_root)``
added by the launcher), imports from ``scripts.forge_runner.*`` resolve
correctly without modifying sys.path here.

Exit codes (contracts/status-cli.md):
    0 — state file exists and was parsed successfully
    1 — state file does not exist
    2 — state file exists but could not be parsed
    3 — runner state indicates a crash record exists (non-fatal, info printed)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Imports from forge_runner package
# ---------------------------------------------------------------------------

from scripts.forge_runner._time import from_iso, now_ist

# ---------------------------------------------------------------------------
# State / health determination constants
# ---------------------------------------------------------------------------

_STALLED_SECONDS = 30  # last_event_at older than this → stalled
_BETWEEN_CHUNKS_SECONDS = 60  # loop_started_at within this → between-chunks

# ---------------------------------------------------------------------------
# State / health type aliases
# ---------------------------------------------------------------------------

# State values: running | stalled | between-chunks | idle | halted-complete | halted-failed
_STATE = str
# Health values: ok | stalled | crashed | authfail
_HEALTH = str


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _read_state_file(state_path: Path) -> Optional[dict[str, Any]]:
    """Read runner-state.json atomically.

    Retries once after 100 ms if the first read fails (mid-rename guard).
    Returns None if the file does not exist.
    Raises ``ValueError`` if the file exists but cannot be parsed.
    """
    if not state_path.exists():
        return None

    def _try_read() -> dict[str, Any]:
        text = state_path.read_text(encoding="utf-8")
        return json.loads(text)  # type: ignore[no-any-return]

    try:
        return _try_read()
    except (json.JSONDecodeError, OSError):
        # Retry once after 100 ms (atomic rename in progress)
        time.sleep(0.1)
        try:
            return _try_read()
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"Cannot parse runner-state.json: {exc}") from exc


def _age_seconds(ts_str: Optional[str]) -> Optional[float]:
    """Return age in seconds of an ISO timestamp relative to now IST."""
    if not ts_str:
        return None
    try:
        then = from_iso(ts_str)
        delta = now_ist() - then
        return delta.total_seconds()
    except (ValueError, TypeError):
        return None


def _format_age(seconds: Optional[float]) -> str:
    """Format seconds as human-readable age string."""
    if seconds is None:
        return "unknown"
    s = abs(int(seconds))
    if s < 60:
        return f"{s}s ago"
    m = s // 60
    remaining_s = s % 60
    if m < 60:
        return f"{m}m{remaining_s:02d}s ago"
    h = m // 60
    remaining_m = m % 60
    return f"{h}h{remaining_m:02d}m ago"


def _format_elapsed(started_at_str: Optional[str]) -> str:
    """Format elapsed time since loop started."""
    if not started_at_str:
        return "unknown"
    age = _age_seconds(started_at_str)
    if age is None:
        return "unknown"
    s = int(age)
    m = s // 60
    remaining_s = s % 60
    if m < 60:
        return f"{m}m{remaining_s:02d}s"
    h = m // 60
    remaining_m = m % 60
    return f"{h}h{remaining_m:02d}m"


def determine_state(
    runner_state: dict[str, Any],
    log_dir: Path,
) -> _STATE:
    """Determine the current runner state from runner-state.json content.

    Rules (contracts/status-cli.md):
    - halted-complete  : runner-complete.json exists newer than state file
    - halted-failed    : <chunk_id>.failure.json exists newer than state file
    - running          : current_chunk is not null, last_event_at within 30s
    - stalled          : current_chunk is not null, last_event_at older than 30s
    - between-chunks   : current_chunk is null, loop_started_at within 60s
    - idle             : everything else
    """
    state_mtime: Optional[float] = None
    state_path = log_dir / "runner-state.json"
    if state_path.exists():
        state_mtime = state_path.stat().st_mtime

    # halted-complete
    complete_path = log_dir / "runner-complete.json"
    if complete_path.exists():
        if state_mtime is None or complete_path.stat().st_mtime >= state_mtime:
            return "halted-complete"

    # halted-failed
    current_chunk = runner_state.get("current_chunk")
    if current_chunk:
        failure_path = log_dir / f"{current_chunk}.failure.json"
        if failure_path.exists():
            if state_mtime is None or failure_path.stat().st_mtime >= state_mtime:
                return "halted-failed"

    # running / stalled
    if current_chunk:
        last_event_at = runner_state.get("last_event_at")
        age = _age_seconds(last_event_at)
        if age is None or age <= _STALLED_SECONDS:
            return "running"
        return "stalled"

    # between-chunks / idle
    loop_started_at = runner_state.get("loop_started_at")
    age = _age_seconds(loop_started_at)
    if age is not None and age <= _BETWEEN_CHUNKS_SECONDS:
        return "between-chunks"

    return "idle"


def determine_health(
    runner_state: dict[str, Any],
    log_dir: Path,
    state: _STATE,
) -> _HEALTH:
    """Determine health value from runner-state.json and filesystem artifacts."""
    current_chunk = runner_state.get("current_chunk")

    # crashed: crash record exists for current chunk
    if current_chunk:
        crash_path = log_dir / f"{current_chunk}.crash.json"
        if crash_path.exists():
            return "crashed"

    # stalled: last event > 30s ago with running/stalled state
    if state in ("stalled",):
        return "stalled"

    # authfail detection: check runner_log entries (best-effort)
    # The spec says: last runner_log entry before current_chunk was cleared has
    # level=ERROR and error_type=AuthenticationError.  We approximate by checking
    # if the chunk log contains an auth failure pattern.
    if current_chunk:
        log_path = log_dir / f"{current_chunk}.log"
        if log_path.exists():
            try:
                # Read last few lines for auth failure pattern
                lines = log_path.read_text(encoding="utf-8").splitlines()
                for line in reversed(lines[-20:]):
                    try:
                        ev = json.loads(line)
                        payload = ev.get("payload", {})
                        if ev.get("kind") == "error" and "auth" in str(payload).lower():
                            return "authfail"
                    except (json.JSONDecodeError, AttributeError):
                        pass
            except OSError:
                pass

    return "ok"


def build_summary_line(
    runner_state: dict[str, Any],
    state: _STATE,
    health: _HEALTH,
) -> str:
    """Build the one-line summary per contracts/status-cli.md format."""
    chunk_id = runner_state.get("current_chunk") or "—"
    elapsed = _format_elapsed(runner_state.get("loop_started_at"))
    event_count = runner_state.get("event_count") or 0
    last_event_at = runner_state.get("last_event_at")
    age = _age_seconds(last_event_at)
    age_str = _format_age(age)

    last_tool = runner_state.get("last_tool")
    if last_tool:
        tool_name = last_tool.get("name", "")
        tool_preview = last_tool.get("input_preview", "")
        last_part = f"last: {tool_name} {tool_preview} {age_str}"
    else:
        last_part = f"last: {age_str}"

    return f"{chunk_id} {state} {elapsed}, {event_count} events, {health} ({last_part})"


def _read_tail_events(
    runner_state: dict[str, Any],
    log_dir: Path,
    tail_lines: int,
) -> list[dict[str, Any]]:
    """Return the last *tail_lines* events from the current chunk's log."""
    current_chunk = runner_state.get("current_chunk")
    if not current_chunk:
        return []

    log_path = log_dir / f"{current_chunk}.log"
    if not log_path.exists():
        return []

    try:
        raw_lines = log_path.read_text(encoding="utf-8").splitlines()
        selected = raw_lines[-tail_lines:]
        result = []
        for line in selected:
            line = line.strip()
            if line:
                try:
                    result.append(json.loads(line))
                except json.JSONDecodeError:
                    result.append({"raw": line})
        return result
    except OSError:
        return []


def _print_tail_events(events: list[dict[str, Any]]) -> None:
    """Print tail events in human-readable format."""
    for ev in events:
        t = ev.get("t", "")
        if t and "T" in t:
            t_short = t.split("T")[1][:8]  # HH:MM:SS
        else:
            t_short = t[:8] if t else "??"
        kind = ev.get("kind", "?")
        payload = ev.get("payload", {})
        detail = ""
        if kind == "tool_use":
            detail = f"{payload.get('tool', '')} {str(payload.get('input', ''))[:60]}"
        elif kind == "tool_result":
            detail = str(payload.get("summary", ""))[:60]
        elif kind == "text":
            detail = str(payload.get("content", ""))[:60]
        print(f"  [{t_short}] {kind} {detail}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forge-runner-status",
        description="Show live status of the forge-runner.",
    )
    parser.add_argument(
        "--repo",
        default=".",
        metavar="PATH",
        help="Repository root (default: $PWD).",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        metavar="PATH",
        help="Log directory containing runner-state.json (default: <repo>/.forge/logs).",
    )
    parser.add_argument(
        "--tail",
        type=int,
        default=20,
        metavar="INT",
        help="How many recent event lines to show after the summary (default: 20).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit structured JSON output instead of human-readable text.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        default=False,
        help="Keep refreshing every 2 seconds (Ctrl+C to exit).",
    )
    return parser


def _run_once(
    log_dir: Path,
    tail_lines: int,
    emit_json: bool,
) -> int:
    """Run one status check.  Returns exit code."""
    state_path = log_dir / "runner-state.json"

    # --- Read state file ---
    try:
        runner_state = _read_state_file(state_path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if runner_state is None:
        print(f"No runner-state.json found in {log_dir}", file=sys.stderr)
        return 1

    # --- Determine state and health ---
    state = determine_state(runner_state, log_dir)
    health = determine_health(runner_state, log_dir, state)
    summary = build_summary_line(runner_state, state, health)

    # --- Determine exit code ---
    exit_code = 0
    current_chunk = runner_state.get("current_chunk")
    if current_chunk:
        crash_path = log_dir / f"{current_chunk}.crash.json"
        if crash_path.exists():
            exit_code = 3

    # --- Output ---
    if emit_json:
        tail_events = _read_tail_events(runner_state, log_dir, tail_lines)
        output = {
            "state_file": str(state_path),
            "runner_state": runner_state,
            "health": health,
            "state": state,
            "summary_line": summary,
            "recent_events": tail_events,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(summary)
        if tail_lines > 0:
            tail_events = _read_tail_events(runner_state, log_dir, tail_lines)
            if tail_events:
                _print_tail_events(tail_events)

    return exit_code


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point for forge-runner-status.  Returns exit code."""
    parser = _make_parser()
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    if args.log_dir is not None:
        log_dir = Path(args.log_dir).resolve()
    else:
        log_dir = repo / ".forge" / "logs"

    if args.watch:
        try:
            while True:
                # Clear screen with ANSI escape (best-effort)
                print("\033[H\033[J", end="")
                _run_once(log_dir, args.tail, args.json)
                time.sleep(2)
        except KeyboardInterrupt:
            return 0

    return _run_once(log_dir, args.tail, args.json)


if __name__ == "__main__":
    sys.exit(main())
