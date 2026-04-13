"""Tests for scripts/forge_runner/secrets.py (T010 / T033).

Security gate: this module has high weight — API keys must NEVER appear in
any log file, runner-state, failure record, or crash record.

Test naming: test_<function>_<scenario>_<expected>
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.forge_runner.secrets import scrub

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REAL_KEY = "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTU1234567890VWXYZ"
REDACTED_KEY = "<redacted-api-key>"
REDACTED = "<redacted>"


# ---------------------------------------------------------------------------
# String-level redaction
# ---------------------------------------------------------------------------


def test_scrub_string_containing_api_key_redacts_it() -> None:
    result = scrub(f"Bearer {REAL_KEY}")
    assert REAL_KEY not in result
    assert REDACTED_KEY in result


def test_scrub_plain_string_without_key_passes_through() -> None:
    s = "hello world"
    assert scrub(s) == s


def test_scrub_api_key_alone_redacted() -> None:
    assert scrub(REAL_KEY) == REDACTED_KEY


def test_scrub_short_sk_ant_not_redacted() -> None:
    # Pattern requires 20+ chars after the prefix — a short string is not a key.
    short = "sk-ant-api03-SHORTKEY"
    result = scrub(short)
    # 19 chars — should NOT be redacted (needs 20+)
    assert result == short


def test_scrub_long_sk_ant_redacted() -> None:
    long_key = "sk-ant-api03-" + "X" * 20
    assert scrub(long_key) == REDACTED_KEY


# ---------------------------------------------------------------------------
# Dict-level redaction
# ---------------------------------------------------------------------------


def test_scrub_dict_sensitive_key_api_key_redacted() -> None:
    d = {"api_key": REAL_KEY}
    result = scrub(d)
    assert result["api_key"] == REDACTED
    assert REAL_KEY not in str(result)


def test_scrub_dict_sensitive_key_anthropic_api_key_redacted() -> None:
    d = {"anthropic_api_key": "some_value"}
    assert scrub(d)["anthropic_api_key"] == REDACTED


def test_scrub_dict_sensitive_key_authorization_redacted() -> None:
    d = {"authorization": f"Bearer {REAL_KEY}"}
    assert scrub(d)["authorization"] == REDACTED


def test_scrub_dict_sensitive_key_bearer_token_redacted() -> None:
    d = {"bearer_token": "mytoken"}
    assert scrub(d)["bearer_token"] == REDACTED


def test_scrub_dict_sensitive_keys_case_insensitive() -> None:
    d = {"API_KEY": "value", "Authorization": "value2"}
    result = scrub(d)
    assert result["API_KEY"] == REDACTED
    assert result["Authorization"] == REDACTED


def test_scrub_dict_non_sensitive_key_passes_through() -> None:
    d = {"status": "ok", "count": 42}
    assert scrub(d) == {"status": "ok", "count": 42}


def test_scrub_nested_dict_key_in_api_key_value_redacted() -> None:
    d = {"outer": {"api_key": REAL_KEY, "safe": "value"}}
    result = scrub(d)
    assert result["outer"]["api_key"] == REDACTED
    assert result["outer"]["safe"] == "value"


def test_scrub_dict_string_value_containing_key_redacted() -> None:
    d = {"message": f"Error: key={REAL_KEY}"}
    result = scrub(d)
    assert REAL_KEY not in result["message"]
    assert REDACTED_KEY in result["message"]


# ---------------------------------------------------------------------------
# List / tuple traversal
# ---------------------------------------------------------------------------


def test_scrub_list_traversal_redacts_key_in_items() -> None:
    lst = ["safe", REAL_KEY, "also_safe"]
    result = scrub(lst)
    assert isinstance(result, list)
    assert result[0] == "safe"
    assert result[1] == REDACTED_KEY
    assert result[2] == "also_safe"


def test_scrub_tuple_traversal_redacts_key_in_items() -> None:
    t = ("safe", REAL_KEY)
    result = scrub(t)
    assert isinstance(result, tuple)
    assert result[0] == "safe"
    assert result[1] == REDACTED_KEY


def test_scrub_nested_list_in_dict() -> None:
    d = {"events": [{"tool": "Read", "api_key": REAL_KEY}]}
    result = scrub(d)
    assert result["events"][0]["api_key"] == REDACTED
    assert REAL_KEY not in str(result)


# ---------------------------------------------------------------------------
# Non-string scalar pass-through
# ---------------------------------------------------------------------------


def test_scrub_integer_passes_through() -> None:
    assert scrub(42) == 42


def test_scrub_none_passes_through() -> None:
    assert scrub(None) is None


def test_scrub_bool_passes_through() -> None:
    assert scrub(True) is True


def test_scrub_float_passes_through() -> None:
    assert scrub(3.14) == pytest.approx(3.14)


# ---------------------------------------------------------------------------
# Immutability / no side effects
# ---------------------------------------------------------------------------


def test_scrub_does_not_mutate_original_dict() -> None:
    original = {"api_key": REAL_KEY, "safe": "value"}
    original_copy = copy.deepcopy(original)
    scrub(original)
    assert original == original_copy


def test_scrub_does_not_mutate_original_list() -> None:
    original = [REAL_KEY, "safe"]
    original_copy = list(original)
    scrub(original)
    assert original == original_copy


def test_scrub_returns_new_dict_not_same_object() -> None:
    d = {"safe": "value"}
    result = scrub(d)
    assert result is not d


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_scrub_empty_dict() -> None:
    assert scrub({}) == {}


def test_scrub_empty_list() -> None:
    assert scrub([]) == []


def test_scrub_empty_string() -> None:
    assert scrub("") == ""


def test_scrub_multiple_keys_in_same_string() -> None:
    s = f"key1={REAL_KEY} key2={REAL_KEY}"
    result = scrub(s)
    assert REAL_KEY not in result
    assert result.count(REDACTED_KEY) == 2


# ---------------------------------------------------------------------------
# T033 extensions: nested dicts, case-insensitive keys, list non-strings,
# deepcopy immutability, integration scan of canned test output files
# ---------------------------------------------------------------------------


def test_scrub_nested_dict_deep_api_key_shape_redacted() -> None:
    """API-key-shaped string three levels deep must be redacted."""
    d = {
        "outer": {
            "middle": {
                "deep_value": REAL_KEY,
                "safe_value": "hello",
            }
        }
    }
    result = scrub(d)
    assert REAL_KEY not in str(result)
    assert result["outer"]["middle"]["deep_value"] == REDACTED_KEY
    assert result["outer"]["middle"]["safe_value"] == "hello"


def test_scrub_sensitive_key_api_key_case_insensitive() -> None:
    """Key ``API_KEY`` (uppercase) → value redacted regardless of key casing."""
    d = {"API_KEY": "some_value_here"}
    result = scrub(d)
    assert result["API_KEY"] == REDACTED


def test_scrub_sensitive_key_authorization_uppercase() -> None:
    """Key ``AUTHORIZATION`` (uppercase) → value redacted."""
    d = {"AUTHORIZATION": "Bearer token123"}
    assert scrub(d)["AUTHORIZATION"] == REDACTED


def test_scrub_sensitive_key_bearer_token_mixed_case() -> None:
    """Key ``Bearer_Token`` (mixed case) → value redacted."""
    d = {"Bearer_Token": "mysecret"}
    assert scrub(d)["Bearer_Token"] == REDACTED


def test_scrub_list_preserves_non_string_types() -> None:
    """Integers, booleans, and None in a list are passed through unchanged."""
    lst = [1, True, None, 3.14, "safe string", REAL_KEY]
    result = scrub(lst)
    assert result[0] == 1
    assert result[1] is True
    assert result[2] is None
    assert abs(result[3] - 3.14) < 1e-9
    assert result[4] == "safe string"
    assert result[5] == REDACTED_KEY


def test_scrub_deepcopy_no_side_effects_on_original_nested() -> None:
    """scrub() must not mutate the original nested structure."""
    original = {
        "level1": {
            "api_key": REAL_KEY,
            "data": [REAL_KEY, "safe"],
        }
    }
    import copy

    original_snapshot = copy.deepcopy(original)

    scrub(original)

    assert original == original_snapshot, "scrub() mutated the original object"


def test_scrub_list_nested_dict_no_side_effects() -> None:
    """scrub() on a list of dicts must not mutate the original dicts."""
    import copy

    original = [{"api_key": REAL_KEY}, {"safe": "value"}]
    snapshot = copy.deepcopy(original)

    scrub(original)

    assert original == snapshot


def test_scrub_integration_no_key_in_canned_log_output(tmp_path: Path) -> None:
    """Integration: write events containing the real key → log file must be clean.

    This test does NOT depend on test_integration_canned.py running first.
    Instead it directly exercises write_event (which calls scrub internally)
    and checks that the output file contains zero occurrences of sk-ant-api03-.
    """
    from scripts.forge_runner.logs import write_event, update_runner_state

    chunk_id = "INTEG-SECRET-1"
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    events = [
        {
            "t": "2026-04-13T10:00:01+05:30",
            "chunk_id": chunk_id,
            "kind": "text",
            "payload": {"content": f"auth key = {REAL_KEY}"},
        },
        {
            "t": "2026-04-13T10:00:02+05:30",
            "chunk_id": chunk_id,
            "kind": "tool_use",
            "payload": {"tool": "Bash", "input": {"command": f"export KEY={REAL_KEY}"}},
        },
    ]
    for ev in events:
        write_event(chunk_id, ev, log_dir)

    state = {
        "schema_version": "1",
        "runner_pid": 1,
        "runner_version": "abc1234",
        "sdk_version": "0.0.1",
        "loop_started_at": "2026-04-13T10:00:00+05:30",
        "current_chunk": chunk_id,
        "chunk_started_at": None,
        "last_event_at": None,
        "event_count": 0,
        "last_tool": {"name": "Bash", "input_preview": f"echo {REAL_KEY}"},
        "chunks_completed_this_run": 0,
        "chunks_failed_this_run": 0,
        "filter_regex": f"key={REAL_KEY}",
        "cumulative_usage": {},
    }
    update_runner_state(state, log_dir)

    # Check ALL files in log_dir for key leakage
    log_files = list(log_dir.iterdir())
    assert log_files, "No files written"
    for fpath in log_files:
        content = fpath.read_text(encoding="utf-8")
        assert "sk-ant-api03-" not in content, (
            f"Secret key pattern found in {fpath.name}: {content[:200]}"
        )
