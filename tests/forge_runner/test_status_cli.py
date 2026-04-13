"""Tests for scripts/forge_runner_status.py (T035).

Tests:
- synthetic runner-state.json fixtures for each state + health value
- one-line output format per state
- --json emits valid JSON with expected keys
- stalled detection at 30s threshold (freeze time via monkeypatch on _time.now_ist)
- invoke via main() directly with argv list
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.forge_runner_status import (
    _read_state_file,
    build_summary_line,
    determine_health,
    determine_state,
    main,
)
from scripts.forge_runner._time import IST, to_iso

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_ist() -> datetime:
    return datetime.now(tz=IST)


def _iso(dt: datetime) -> str:
    return to_iso(dt)


def _base_state(
    current_chunk: Any = "V1-3",
    last_event_at: Any = None,
    loop_started_at: Any = None,
    event_count: int = 42,
    last_tool: Any = None,
) -> dict[str, Any]:
    """Build a minimal valid runner-state dict."""
    now = _now_ist()
    return {
        "schema_version": "1",
        "runner_pid": 12345,
        "runner_version": "abc1234",
        "sdk_version": "0.0.1",
        "loop_started_at": loop_started_at or _iso(now - timedelta(minutes=12, seconds=34)),
        "current_chunk": current_chunk,
        "chunk_started_at": _iso(now - timedelta(minutes=10)) if current_chunk else None,
        "last_event_at": last_event_at,
        "event_count": event_count,
        "last_tool": last_tool,
        "chunks_completed_this_run": 1,
        "chunks_failed_this_run": 0,
        "filter_regex": ".*",
        "cumulative_usage": {},
    }


def _write_state(log_dir: Path, state: dict[str, Any]) -> None:
    (log_dir / "runner-state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# _read_state_file
# ---------------------------------------------------------------------------


def test_read_state_file_missing_returns_none(tmp_path: Path) -> None:
    """Missing runner-state.json returns None (not an exception)."""
    result = _read_state_file(tmp_path / "runner-state.json")
    assert result is None


def test_read_state_file_valid_returns_dict(tmp_path: Path) -> None:
    """Valid JSON file returns a dict."""
    state = _base_state()
    _write_state(tmp_path, state)
    result = _read_state_file(tmp_path / "runner-state.json")
    assert result is not None
    assert result["schema_version"] == "1"


def test_read_state_file_invalid_json_raises(tmp_path: Path) -> None:
    """Invalid JSON raises ValueError after retry."""
    (tmp_path / "runner-state.json").write_text("not json{{{")
    with pytest.raises(ValueError, match="Cannot parse"):
        _read_state_file(tmp_path / "runner-state.json")


# ---------------------------------------------------------------------------
# determine_state — each state value
# ---------------------------------------------------------------------------


def test_determine_state_running(tmp_path: Path) -> None:
    """current_chunk set + last_event_at within 30s → running."""
    now = _now_ist()
    state = _base_state(
        current_chunk="V1-3",
        last_event_at=_iso(now - timedelta(seconds=5)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=now):
        result = determine_state(state, tmp_path)

    assert result == "running"


def test_determine_state_stalled_at_threshold(tmp_path: Path) -> None:
    """current_chunk set + last_event_at exactly 31s ago → stalled."""
    now = _now_ist()
    state = _base_state(
        current_chunk="V1-3",
        last_event_at=_iso(now - timedelta(seconds=31)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=now):
        result = determine_state(state, tmp_path)

    assert result == "stalled"


def test_determine_state_running_at_29s_boundary(tmp_path: Path) -> None:
    """last_event_at 29s ago is clearly within the 30s window → running."""
    now = _now_ist()
    state = _base_state(
        current_chunk="V1-3",
        last_event_at=_iso(now - timedelta(seconds=29)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=now):
        result = determine_state(state, tmp_path)

    assert result == "running"


def test_determine_state_between_chunks(tmp_path: Path) -> None:
    """current_chunk null + loop_started_at within 60s → between-chunks."""
    now = _now_ist()
    state = _base_state(
        current_chunk=None,
        loop_started_at=_iso(now - timedelta(seconds=30)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=now):
        result = determine_state(state, tmp_path)

    assert result == "between-chunks"


def test_determine_state_idle(tmp_path: Path) -> None:
    """current_chunk null + loop_started_at older than 60s → idle."""
    now = _now_ist()
    state = _base_state(
        current_chunk=None,
        loop_started_at=_iso(now - timedelta(minutes=10)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=now):
        result = determine_state(state, tmp_path)

    assert result == "idle"


def test_determine_state_halted_complete(tmp_path: Path) -> None:
    """runner-complete.json exists → halted-complete."""
    state = _base_state(current_chunk=None)
    _write_state(tmp_path, state)
    # Write runner-complete.json newer than runner-state.json
    time.sleep(0.01)
    (tmp_path / "runner-complete.json").write_text("{}")

    result = determine_state(state, tmp_path)
    assert result == "halted-complete"


def test_determine_state_halted_failed(tmp_path: Path) -> None:
    """<chunk>.failure.json newer than state file → halted-failed."""
    chunk_id = "V1-3"
    state = _base_state(current_chunk=chunk_id)
    _write_state(tmp_path, state)
    time.sleep(0.01)
    (tmp_path / f"{chunk_id}.failure.json").write_text("{}")

    result = determine_state(state, tmp_path)
    assert result == "halted-failed"


# ---------------------------------------------------------------------------
# determine_health — each health value
# ---------------------------------------------------------------------------


def test_determine_health_ok(tmp_path: Path) -> None:
    """No crash, no stall → ok."""
    state = _base_state(current_chunk="V1-3")
    result = determine_health(state, tmp_path, "running")
    assert result == "ok"


def test_determine_health_stalled(tmp_path: Path) -> None:
    """State = stalled → health = stalled."""
    state = _base_state(current_chunk="V1-3")
    result = determine_health(state, tmp_path, "stalled")
    assert result == "stalled"


def test_determine_health_crashed(tmp_path: Path) -> None:
    """Crash record exists → health = crashed."""
    chunk_id = "V1-3"
    state = _base_state(current_chunk=chunk_id)
    (tmp_path / f"{chunk_id}.crash.json").write_text("{}")
    result = determine_health(state, tmp_path, "running")
    assert result == "crashed"


def test_determine_health_no_chunk_ok(tmp_path: Path) -> None:
    """No current_chunk → health = ok."""
    state = _base_state(current_chunk=None)
    result = determine_health(state, tmp_path, "idle")
    assert result == "ok"


# ---------------------------------------------------------------------------
# build_summary_line — format checks
# ---------------------------------------------------------------------------


def test_build_summary_line_contains_chunk_id() -> None:
    state = _base_state(current_chunk="V1-3", event_count=142)
    line = build_summary_line(state, "running", "ok")
    assert "V1-3" in line


def test_build_summary_line_contains_state() -> None:
    state = _base_state(current_chunk="V1-3", event_count=0)
    line = build_summary_line(state, "stalled", "stalled")
    assert "stalled" in line


def test_build_summary_line_contains_event_count() -> None:
    state = _base_state(current_chunk="V1-3", event_count=142)
    line = build_summary_line(state, "running", "ok")
    assert "142" in line


def test_build_summary_line_contains_health() -> None:
    state = _base_state(current_chunk="V1-3")
    line = build_summary_line(state, "running", "ok")
    assert "ok" in line


def test_build_summary_line_contains_last_tool_name() -> None:
    state = _base_state(
        current_chunk="V1-3",
        last_tool={"name": "Edit", "input_preview": "backend/agents/rs_analyzer.py"},
    )
    line = build_summary_line(state, "running", "ok")
    assert "Edit" in line


def test_build_summary_line_no_last_tool(tmp_path: Path) -> None:
    """When last_tool is None, summary line still prints without crash."""
    state = _base_state(current_chunk="V1-3", last_tool=None)
    line = build_summary_line(state, "running", "ok")
    assert "V1-3" in line


# ---------------------------------------------------------------------------
# main() — human output
# ---------------------------------------------------------------------------


def test_main_exits_1_when_no_state_file(tmp_path: Path, capsys: Any) -> None:
    """Exit code 1 when runner-state.json is absent."""
    code = main(["--log-dir", str(tmp_path)])
    assert code == 1
    captured = capsys.readouterr()
    assert "No runner-state.json" in captured.err


def test_main_exits_0_for_valid_state(tmp_path: Path, capsys: Any) -> None:
    """Exit code 0 when state file exists and is valid."""
    now = _now_ist()
    state = _base_state(
        current_chunk="V1-3",
        last_event_at=_iso(now - timedelta(seconds=5)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=now):
        code = main(["--log-dir", str(tmp_path), "--tail", "0"])
    assert code == 0


def test_main_output_contains_chunk_id(tmp_path: Path, capsys: Any) -> None:
    """Human output line contains the current chunk ID."""
    now = _now_ist()
    state = _base_state(
        current_chunk="V1-5",
        last_event_at=_iso(now - timedelta(seconds=5)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=now):
        main(["--log-dir", str(tmp_path), "--tail", "0"])

    captured = capsys.readouterr()
    assert "V1-5" in captured.out


# ---------------------------------------------------------------------------
# main() — --json flag
# ---------------------------------------------------------------------------


def test_main_json_flag_emits_valid_json(tmp_path: Path, capsys: Any) -> None:
    """--json emits valid JSON with required top-level keys."""
    now = _now_ist()
    state = _base_state(
        current_chunk="V1-3",
        last_event_at=_iso(now - timedelta(seconds=5)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=now):
        code = main(["--log-dir", str(tmp_path), "--json", "--tail", "0"])
    assert code == 0

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert "state_file" in parsed
    assert "runner_state" in parsed
    assert "health" in parsed
    assert "state" in parsed
    assert "summary_line" in parsed
    assert "recent_events" in parsed


def test_main_json_state_field_correct(tmp_path: Path, capsys: Any) -> None:
    """--json output has correct 'state' field for running state."""
    now = _now_ist()
    state = _base_state(
        current_chunk="V1-3",
        last_event_at=_iso(now - timedelta(seconds=5)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=now):
        main(["--log-dir", str(tmp_path), "--json", "--tail", "0"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["state"] == "running"


def test_main_json_health_field_present(tmp_path: Path, capsys: Any) -> None:
    """--json output includes non-null health field."""
    now = _now_ist()
    state = _base_state(
        current_chunk="V1-3",
        last_event_at=_iso(now - timedelta(seconds=5)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=now):
        main(["--log-dir", str(tmp_path), "--json", "--tail", "0"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["health"] in ("ok", "stalled", "crashed", "authfail")


# ---------------------------------------------------------------------------
# Stalled detection at 30s threshold (freeze time)
# ---------------------------------------------------------------------------


def test_stalled_detection_at_30s_threshold_frozen_time(tmp_path: Path) -> None:
    """With frozen time, stalled detected exactly when age > 30s."""
    frozen_now = _now_ist()
    # 31 seconds ago → stalled
    state = _base_state(
        current_chunk="V1-3",
        last_event_at=_iso(frozen_now - timedelta(seconds=31)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=frozen_now):
        result_state = determine_state(state, tmp_path)
        result_health = determine_health(state, tmp_path, result_state)

    assert result_state == "stalled"
    assert result_health == "stalled"


def test_not_stalled_at_29s_frozen_time(tmp_path: Path) -> None:
    """With frozen time, 29 seconds ago → running (not stalled)."""
    frozen_now = _now_ist()
    state = _base_state(
        current_chunk="V1-3",
        last_event_at=_iso(frozen_now - timedelta(seconds=29)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=frozen_now):
        result_state = determine_state(state, tmp_path)

    assert result_state == "running"


def test_stalled_health_from_main_json_output(tmp_path: Path, capsys: Any) -> None:
    """Stalled state propagates to JSON output health field."""
    frozen_now = _now_ist()
    state = _base_state(
        current_chunk="V1-3",
        last_event_at=_iso(frozen_now - timedelta(seconds=60)),
    )
    _write_state(tmp_path, state)

    with patch("scripts.forge_runner_status.now_ist", return_value=frozen_now):
        main(["--log-dir", str(tmp_path), "--json", "--tail", "0"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["state"] == "stalled"
    assert parsed["health"] == "stalled"


# ---------------------------------------------------------------------------
# Tail output
# ---------------------------------------------------------------------------


def test_main_tail_shows_log_events(tmp_path: Path, capsys: Any) -> None:
    """--tail N causes log events to appear in human output."""
    now = _now_ist()
    chunk_id = "V1-3"
    state = _base_state(
        current_chunk=chunk_id,
        last_event_at=_iso(now - timedelta(seconds=3)),
    )
    _write_state(tmp_path, state)

    # Write a few log lines
    log_path = tmp_path / f"{chunk_id}.log"
    for i in range(3):
        ev = {
            "t": _iso(now - timedelta(seconds=3 - i)),
            "chunk_id": chunk_id,
            "kind": "tool_use",
            "payload": {"tool": "Read", "input": {"file_path": f"file-{i}.py"}},
        }
        log_path.open("a").write(json.dumps(ev) + "\n")

    with patch("scripts.forge_runner_status.now_ist", return_value=now):
        code = main(["--log-dir", str(tmp_path), "--tail", "3"])

    assert code == 0
    captured = capsys.readouterr()
    # Tail output should appear below summary
    assert "tool_use" in captured.out or "Read" in captured.out


# ---------------------------------------------------------------------------
# Exit code 3 for crash record
# ---------------------------------------------------------------------------


def test_main_exits_3_when_crash_record_exists(tmp_path: Path, capsys: Any) -> None:
    """Exit code 3 when a crash record exists for current_chunk."""
    now = _now_ist()
    chunk_id = "V1-3"
    state = _base_state(
        current_chunk=chunk_id,
        last_event_at=_iso(now - timedelta(seconds=5)),
    )
    _write_state(tmp_path, state)
    (tmp_path / f"{chunk_id}.crash.json").write_text("{}")

    with patch("scripts.forge_runner_status.now_ist", return_value=now):
        code = main(["--log-dir", str(tmp_path), "--tail", "0"])
    assert code == 3


# ---------------------------------------------------------------------------
# Exit code 2 for corrupt state file
# ---------------------------------------------------------------------------


def test_main_exits_2_when_state_file_corrupt(tmp_path: Path, capsys: Any) -> None:
    """Exit code 2 when runner-state.json cannot be parsed."""
    (tmp_path / "runner-state.json").write_text("{broken json")
    code = main(["--log-dir", str(tmp_path)])
    assert code == 2
