"""T045: Audit trail guarantees for per-chunk log files (US5).

Constructs a synthetic log file inline (no full integration harness required),
then verifies the structural guarantees that make the log useful for post-hoc
review:

  - file is non-empty
  - first event kind is ``session_start``
  - last event kind is ``session_end``
  - events are chronologically sorted by the ``t`` field
  - at least 1 ``tool_use`` event and 1 ``tool_result`` event are present
  - every event passes ``validate_log_file`` (manual required-fields check)

Validator choice: ``validate_log_file`` in ``logs.py`` uses manual required-
fields validation because the JSON schema file (contracts/log-event.schema.json)
specifies ``evt``/``session_id`` while the runner's ``write_event`` writes
``kind``/``chunk_id``.  Using jsonschema directly against the schema file would
fail every line.  The manual validator checks the actual written format.
"""

from __future__ import annotations

import json
from pathlib import Path


from scripts.forge_runner._time import now_ist, to_iso
from scripts.forge_runner.logs import validate_log_file, write_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(kind: str, chunk_id: str, payload: dict) -> dict:
    return {
        "t": to_iso(now_ist()),
        "chunk_id": chunk_id,
        "kind": kind,
        "payload": payload,
    }


def _write_fake_log(log_dir: Path, chunk_id: str) -> Path:
    """Write a minimal but structurally correct log file for *chunk_id*."""
    events = [
        _make_event(
            "session_start",
            chunk_id,
            {
                "session_id": f"forge-{chunk_id}-001",
                "cwd": "/home/ubuntu/atlas",
                "allowed_tools_count": 9,
                "max_turns": 10,
            },
        ),
        _make_event(
            "tool_use",
            chunk_id,
            {
                "tool": "Read",
                "input": {"file_path": "/home/ubuntu/atlas/CLAUDE.md"},
            },
        ),
        _make_event(
            "tool_result",
            chunk_id,
            {
                "tool": "Read",
                "is_error": False,
                "summary": "# ATLAS",
            },
        ),
        _make_event(
            "text",
            chunk_id,
            {
                "content": "Implementing the chunk...",
            },
        ),
        _make_event(
            "session_end",
            chunk_id,
            {
                "session_id": f"forge-{chunk_id}-001",
                "stop_reason": "end_turn",
                "turns": 1,
                "usage": {},
            },
        ),
    ]

    for event in events:
        write_event(chunk_id, event, log_dir)

    return log_dir / f"{chunk_id}.log"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAuditTrailStructure:
    def test_log_file_is_nonempty(self, tmp_path: Path) -> None:
        """Log file must exist and contain at least one line."""
        chunk_id = "AUDIT-1"
        log_file = _write_fake_log(tmp_path, chunk_id)
        assert log_file.exists()
        lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        assert len(lines) > 0

    def test_first_event_is_session_start(self, tmp_path: Path) -> None:
        """First event written must have kind='session_start'."""
        chunk_id = "AUDIT-2"
        log_file = _write_fake_log(tmp_path, chunk_id)
        lines = [json.loads(ln) for ln in log_file.read_text().splitlines() if ln.strip()]
        assert lines[0]["kind"] == "session_start"

    def test_last_event_is_session_end(self, tmp_path: Path) -> None:
        """Last event written must have kind='session_end'."""
        chunk_id = "AUDIT-3"
        log_file = _write_fake_log(tmp_path, chunk_id)
        lines = [json.loads(ln) for ln in log_file.read_text().splitlines() if ln.strip()]
        assert lines[-1]["kind"] == "session_end"

    def test_events_chronologically_sorted(self, tmp_path: Path) -> None:
        """The ``t`` field must be non-decreasing across events."""
        chunk_id = "AUDIT-4"
        log_file = _write_fake_log(tmp_path, chunk_id)
        lines = [json.loads(ln) for ln in log_file.read_text().splitlines() if ln.strip()]
        timestamps = [ln["t"] for ln in lines]
        # ISO8601 strings with explicit offset sort lexicographically.
        assert timestamps == sorted(timestamps), "events are not in chronological order"

    def test_at_least_one_tool_use(self, tmp_path: Path) -> None:
        """At least one event must have kind='tool_use'."""
        chunk_id = "AUDIT-5"
        log_file = _write_fake_log(tmp_path, chunk_id)
        lines = [json.loads(ln) for ln in log_file.read_text().splitlines() if ln.strip()]
        tool_use_count = sum(1 for ln in lines if ln["kind"] == "tool_use")
        assert tool_use_count >= 1, f"expected >=1 tool_use, got {tool_use_count}"

    def test_at_least_one_tool_result(self, tmp_path: Path) -> None:
        """At least one event must have kind='tool_result'."""
        chunk_id = "AUDIT-6"
        log_file = _write_fake_log(tmp_path, chunk_id)
        lines = [json.loads(ln) for ln in log_file.read_text().splitlines() if ln.strip()]
        tool_result_count = sum(1 for ln in lines if ln["kind"] == "tool_result")
        assert tool_result_count >= 1, f"expected >=1 tool_result, got {tool_result_count}"

    def test_validate_log_file_returns_valid(self, tmp_path: Path) -> None:
        """validate_log_file must return (True, []) for a well-formed log."""
        chunk_id = "AUDIT-7"
        log_file = _write_fake_log(tmp_path, chunk_id)
        valid, errors = validate_log_file(log_file)
        assert valid, f"validate_log_file returned errors: {errors}"
        assert errors == []

    def test_every_event_has_required_fields(self, tmp_path: Path) -> None:
        """Every line must contain t, chunk_id, kind, payload keys."""
        chunk_id = "AUDIT-8"
        log_file = _write_fake_log(tmp_path, chunk_id)
        lines = [json.loads(ln) for ln in log_file.read_text().splitlines() if ln.strip()]
        for i, event in enumerate(lines):
            for field in ("t", "chunk_id", "kind", "payload"):
                assert field in event, (
                    f"event[{i}] (kind={event.get('kind')!r}) missing field '{field}'"
                )


class TestValidateLogFile:
    """Unit tests for the validate_log_file helper itself."""

    def test_valid_file_passes(self, tmp_path: Path) -> None:
        chunk_id = "VAL-1"
        log_file = _write_fake_log(tmp_path, chunk_id)
        valid, errors = validate_log_file(log_file)
        assert valid
        assert errors == []

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.log"
        valid, errors = validate_log_file(missing)
        assert not valid
        assert any("not found" in e for e in errors)

    def test_empty_file_fails(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.log"
        empty.write_text("")
        valid, errors = validate_log_file(empty)
        assert not valid
        assert any("empty" in e for e in errors)

    def test_invalid_json_line_reported(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.log"
        bad.write_text("{not valid json}\n")
        valid, errors = validate_log_file(bad)
        assert not valid
        assert any("invalid JSON" in e for e in errors)

    def test_missing_required_field_reported(self, tmp_path: Path) -> None:
        """A line missing 'kind' must produce a specific error."""
        partial = tmp_path / "partial.log"
        # Write a line missing the 'kind' field
        line = json.dumps({"t": to_iso(now_ist()), "chunk_id": "X", "payload": {}})
        partial.write_text(line + "\n")
        valid, errors = validate_log_file(partial)
        assert not valid
        assert any("'kind'" in e for e in errors)

    def test_non_object_line_reported(self, tmp_path: Path) -> None:
        """A JSON array on a line should be reported as invalid."""
        arr_file = tmp_path / "array.log"
        arr_file.write_text("[1, 2, 3]\n")
        valid, errors = validate_log_file(arr_file)
        assert not valid
        assert any("JSON object" in e for e in errors)

    def test_multiple_errors_all_reported(self, tmp_path: Path) -> None:
        """Two bad lines produce two separate error entries."""
        multi = tmp_path / "multi.log"
        line1 = json.dumps({"t": to_iso(now_ist()), "chunk_id": "X", "payload": {}})  # missing kind
        line2 = "{broken"
        multi.write_text(line1 + "\n" + line2 + "\n")
        _, errors = validate_log_file(multi)
        assert len(errors) >= 2
