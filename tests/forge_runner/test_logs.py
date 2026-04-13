"""Tests for scripts/forge_runner/logs.py (T032).

Covers:
- event is visible in file immediately after write_event returns (flush + fsync)
- update_runner_state is atomic (concurrent reader never sees partial JSON)
- append_event_and_update_state increments event_count and sets last_tool
- last_tool.input_preview is scrubbed + truncated to 200 chars
- rotate_old_logs moves oldest files beyond keep=50 to archive/
- secrets never appear in any log or runner-state file
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


from scripts.forge_runner.logs import (
    append_event_and_update_state,
    rotate_old_logs,
    update_runner_state,
    write_event,
)

# Real key shape that must never appear in output
_REAL_KEY = "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTU1234567890VWXYZ"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_state(chunk_id: str = "TEST-1") -> dict[str, Any]:
    return {
        "schema_version": "1",
        "runner_pid": 12345,
        "runner_version": "abc1234",
        "sdk_version": "0.0.1",
        "loop_started_at": "2026-04-13T10:00:00+05:30",
        "current_chunk": chunk_id,
        "chunk_started_at": None,
        "last_event_at": None,
        "event_count": 0,
        "last_tool": None,
        "chunks_completed_this_run": 0,
        "chunks_failed_this_run": 0,
        "filter_regex": ".*",
        "cumulative_usage": {},
    }


def _tool_use_event(
    chunk_id: str = "TEST-1", tool: str = "Read", input_val: str = "CLAUDE.md"
) -> dict[str, Any]:
    return {
        "t": "2026-04-13T10:00:01+05:30",
        "chunk_id": chunk_id,
        "kind": "tool_use",
        "payload": {"tool": tool, "input": {"file_path": input_val}},
    }


def _text_event(chunk_id: str = "TEST-1") -> dict[str, Any]:
    return {
        "t": "2026-04-13T10:00:02+05:30",
        "chunk_id": chunk_id,
        "kind": "text",
        "payload": {"content": "hello"},
    }


# ---------------------------------------------------------------------------
# T032-1: event is visible in file immediately after write_event returns
# ---------------------------------------------------------------------------


def test_write_event_visible_immediately(tmp_path: Path) -> None:
    """After write_event returns, the line MUST be readable from the file."""
    chunk_id = "FLUSH-1"
    event = _text_event(chunk_id)

    write_event(chunk_id, event, tmp_path)

    log_file = tmp_path / f"{chunk_id}.log"
    assert log_file.exists(), "log file not created"
    content = log_file.read_text()
    assert content.strip(), "log file is empty after write"
    parsed = json.loads(content.splitlines()[0])
    assert parsed["kind"] == "text"


def test_write_event_multiple_lines_all_visible(tmp_path: Path) -> None:
    """Multiple write_event calls produce one JSON line each, all readable."""
    chunk_id = "FLUSH-2"
    for i in range(5):
        ev = {
            "t": "2026-04-13T10:00:00+05:30",
            "chunk_id": chunk_id,
            "kind": "text",
            "payload": {"n": i},
        }
        write_event(chunk_id, ev, tmp_path)

    log_file = tmp_path / f"{chunk_id}.log"
    lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
    assert len(lines) == 5
    for i, line in enumerate(lines):
        assert json.loads(line)["payload"]["n"] == i


# ---------------------------------------------------------------------------
# T032-2: update_runner_state is atomic (concurrent reader never sees partial)
# ---------------------------------------------------------------------------


def test_update_runner_state_atomic_concurrent_reads(tmp_path: Path) -> None:
    """A reader thread looping on runner-state.json must never see invalid JSON.

    The atomic tmp+rename guarantees readers see either the old or the new
    complete file — never a partial write.
    """
    state = _minimal_state("ATOMIC-1")
    # Prime the file so the reader has something to start with
    update_runner_state(state, tmp_path)

    errors: list[str] = []
    stop_event = threading.Event()

    def reader() -> None:
        path = tmp_path / "runner-state.json"
        while not stop_event.is_set():
            try:
                text = path.read_text(encoding="utf-8")
                if text.strip():
                    json.loads(text)
            except json.JSONDecodeError as exc:
                errors.append(str(exc))
            except OSError:
                # File may momentarily not exist during rename — OK
                pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    # Writer: update 100 times rapidly
    for i in range(100):
        s = dict(state)
        s["event_count"] = i
        update_runner_state(s, tmp_path)

    stop_event.set()
    t.join(timeout=2.0)

    assert errors == [], f"JSONDecodeError(s) seen by reader: {errors[:3]}"


# ---------------------------------------------------------------------------
# T032-3: last_tool.input_preview scrubbed + 200-char truncated
# ---------------------------------------------------------------------------


def test_append_event_sets_last_tool_with_scrubbed_preview(tmp_path: Path) -> None:
    """tool_use event: last_tool.input_preview is scrubbed of API keys."""
    chunk_id = "TOOL-1"
    state = _minimal_state(chunk_id)
    event = {
        "t": "2026-04-13T10:00:01+05:30",
        "chunk_id": chunk_id,
        "kind": "tool_use",
        "payload": {"tool": "Bash", "input": {"command": f"echo {_REAL_KEY}"}},
    }

    append_event_and_update_state(chunk_id, event, state, tmp_path)

    assert state["last_tool"] is not None
    preview = state["last_tool"]["input_preview"]
    assert _REAL_KEY not in preview, "API key must be scrubbed from input_preview"
    assert "<redacted-api-key>" in preview


def test_append_event_truncates_preview_to_200_chars(tmp_path: Path) -> None:
    """input_preview must not exceed 200 characters."""
    chunk_id = "TOOL-2"
    state = _minimal_state(chunk_id)
    long_input = "A" * 500
    event = {
        "t": "2026-04-13T10:00:01+05:30",
        "chunk_id": chunk_id,
        "kind": "tool_use",
        "payload": {"tool": "Write", "input": {"content": long_input}},
    }

    append_event_and_update_state(chunk_id, event, state, tmp_path)

    assert state["last_tool"] is not None
    assert len(state["last_tool"]["input_preview"]) <= 200


def test_append_event_non_tool_use_does_not_change_last_tool(tmp_path: Path) -> None:
    """Non-tool_use events must not change last_tool."""
    chunk_id = "TOOL-3"
    state = _minimal_state(chunk_id)
    state["last_tool"] = {"name": "Read", "input_preview": "CLAUDE.md"}
    event = _text_event(chunk_id)

    append_event_and_update_state(chunk_id, event, state, tmp_path)

    # last_tool should remain unchanged
    assert state["last_tool"]["name"] == "Read"


# ---------------------------------------------------------------------------
# T032-4: event_count increments on every call
# ---------------------------------------------------------------------------


def test_append_event_increments_event_count(tmp_path: Path) -> None:
    """event_count in state_dict is incremented on every append call."""
    chunk_id = "COUNT-1"
    state = _minimal_state(chunk_id)
    assert state["event_count"] == 0

    for i in range(5):
        append_event_and_update_state(chunk_id, _text_event(chunk_id), state, tmp_path)
        assert state["event_count"] == i + 1


def test_append_event_initialises_missing_event_count(tmp_path: Path) -> None:
    """If event_count is missing from state_dict, it starts at 1 after first append."""
    chunk_id = "COUNT-2"
    state = _minimal_state(chunk_id)
    del state["event_count"]

    append_event_and_update_state(chunk_id, _text_event(chunk_id), state, tmp_path)

    assert state["event_count"] == 1


def test_append_event_initialises_none_event_count(tmp_path: Path) -> None:
    """If event_count is None, it starts at 1 after first append."""
    chunk_id = "COUNT-3"
    state = _minimal_state(chunk_id)
    state["event_count"] = None

    append_event_and_update_state(chunk_id, _text_event(chunk_id), state, tmp_path)

    assert state["event_count"] == 1


# ---------------------------------------------------------------------------
# T032-5: rotate_old_logs moves oldest beyond keep=50 to archive/
# ---------------------------------------------------------------------------


def test_rotate_old_logs_no_op_when_under_limit(tmp_path: Path) -> None:
    """When log count <= keep, nothing is moved."""
    for i in range(10):
        (tmp_path / f"chunk-{i}.log").write_text("x")

    rotate_old_logs(tmp_path, keep=50)

    archive = tmp_path / "archive"
    assert not archive.exists() or not any(archive.iterdir())
    assert len(list(tmp_path.glob("*.log"))) == 10


def test_rotate_old_logs_moves_oldest_to_archive(tmp_path: Path) -> None:
    """When log count > keep, oldest files move to archive/."""
    # Create 55 log files with distinct mtimes
    for i in range(55):
        p = tmp_path / f"chunk-{i:03d}.log"
        p.write_text(f"line {i}")
        # Spread mtimes so ordering is deterministic
        target_time = time.time() - (55 - i) * 10
        import os

        os.utime(str(p), (target_time, target_time))

    rotate_old_logs(tmp_path, keep=50)

    archive = tmp_path / "archive"
    assert archive.is_dir()
    archived_files = list(archive.glob("*.log"))
    active_files = list(tmp_path.glob("*.log"))

    assert len(archived_files) == 5, f"Expected 5 archived, got {len(archived_files)}"
    assert len(active_files) == 50, f"Expected 50 active, got {len(active_files)}"


def test_rotate_old_logs_archives_oldest_by_mtime(tmp_path: Path) -> None:
    """The oldest files (by mtime) are the ones moved to archive/."""
    import os

    base_time = time.time() - 1000
    for i in range(52):
        p = tmp_path / f"chunk-{i:03d}.log"
        p.write_text(f"content {i}")
        os.utime(str(p), (base_time + i, base_time + i))

    rotate_old_logs(tmp_path, keep=50)

    archive = tmp_path / "archive"
    archived_names = {f.name for f in archive.glob("*.log")}
    # Oldest 2 should be chunk-000.log and chunk-001.log
    assert "chunk-000.log" in archived_names
    assert "chunk-001.log" in archived_names


def test_rotate_old_logs_creates_archive_dir_if_missing(tmp_path: Path) -> None:
    """archive/ directory is created automatically when needed."""
    for i in range(51):
        (tmp_path / f"c-{i}.log").write_text("x")

    rotate_old_logs(tmp_path, keep=50)

    assert (tmp_path / "archive").is_dir()


def test_rotate_old_logs_handles_archive_name_collision(tmp_path: Path) -> None:
    """If archive already contains a file with the same name, a suffix is added."""
    import os

    archive = tmp_path / "archive"
    archive.mkdir()

    base_time = time.time() - 1000
    for i in range(52):
        p = tmp_path / f"chunk-{i:03d}.log"
        p.write_text(f"content {i}")
        os.utime(str(p), (base_time + i, base_time + i))

    # Pre-create a collision in archive
    (archive / "chunk-000.log").write_text("already here")

    # Should not raise; collision handled by adding mtime suffix
    rotate_old_logs(tmp_path, keep=50)

    archived = list(archive.glob("*.log"))
    assert len(archived) >= 2


# ---------------------------------------------------------------------------
# T032-6: no secrets leak in log file or runner-state
# ---------------------------------------------------------------------------


def test_no_secrets_in_log_file_after_write(tmp_path: Path) -> None:
    """API key embedded in event must not appear in the log file."""
    chunk_id = "SECRET-1"
    event = {
        "t": "2026-04-13T10:00:01+05:30",
        "chunk_id": chunk_id,
        "kind": "text",
        "payload": {"content": f"key={_REAL_KEY}"},
    }
    write_event(chunk_id, event, tmp_path)

    log_path = tmp_path / f"{chunk_id}.log"
    assert _REAL_KEY not in log_path.read_text()


def test_no_secrets_in_runner_state_after_update(tmp_path: Path) -> None:
    """API key in state dict must not appear in runner-state.json."""
    state = _minimal_state("SECRET-2")
    state["filter_regex"] = f"key={_REAL_KEY}"

    update_runner_state(state, tmp_path)

    state_path = tmp_path / "runner-state.json"
    assert _REAL_KEY not in state_path.read_text()


def test_no_secrets_in_log_via_append_event(tmp_path: Path) -> None:
    """append_event_and_update_state must not leak key to log or state file."""
    chunk_id = "SECRET-3"
    state = _minimal_state(chunk_id)
    event = {
        "t": "2026-04-13T10:00:01+05:30",
        "chunk_id": chunk_id,
        "kind": "tool_use",
        "payload": {"tool": "Bash", "input": {"command": f"echo {_REAL_KEY}"}},
    }

    append_event_and_update_state(chunk_id, event, state, tmp_path)

    log_text = (tmp_path / f"{chunk_id}.log").read_text()
    state_text = (tmp_path / "runner-state.json").read_text()
    assert _REAL_KEY not in log_text
    assert _REAL_KEY not in state_text


# ---------------------------------------------------------------------------
# T032-7: last_event_at is updated by append_event_and_update_state
# ---------------------------------------------------------------------------


def test_append_event_updates_last_event_at(tmp_path: Path) -> None:
    """last_event_at must be set to a non-null ISO string after append."""
    chunk_id = "EVT-AT-1"
    state = _minimal_state(chunk_id)
    assert state["last_event_at"] is None

    append_event_and_update_state(chunk_id, _text_event(chunk_id), state, tmp_path)

    assert state["last_event_at"] is not None
    assert "+05:30" in state["last_event_at"]


# ---------------------------------------------------------------------------
# T032-8: runner-state.json written by append_event_and_update_state is valid JSON
# ---------------------------------------------------------------------------


def test_append_event_runner_state_is_valid_json(tmp_path: Path) -> None:
    """runner-state.json written by append_event_and_update_state is valid JSON."""
    chunk_id = "VALID-1"
    state = _minimal_state(chunk_id)

    append_event_and_update_state(chunk_id, _tool_use_event(chunk_id), state, tmp_path)

    state_path = tmp_path / "runner-state.json"
    assert state_path.exists()
    parsed = json.loads(state_path.read_text())
    assert parsed["event_count"] == 1
    assert parsed["last_tool"] is not None
    assert parsed["last_tool"]["name"] == "Read"
