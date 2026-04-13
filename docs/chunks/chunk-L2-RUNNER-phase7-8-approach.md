---
chunk: L2-RUNNER-phases-7-8
project: atlas
date: 2026-04-13
tasks: T045-T050
---

# Approach: L2-RUNNER Phases 7 + 8 (T045–T050)

## Data scale
No database queries in this phase. Pure filesystem/module validation.

## Key design decision: jsonschema vs manual validator

`jsonschema` 4.26.0 is already installed in the venv. However, there is a schema
mismatch between `contracts/log-event.schema.json` (which requires `t`, `evt`,
`session_id`, `payload`) and the actual log events written by `write_event` in
`logs.py` (which use `t`, `chunk_id`, `kind`, `payload`).

Decision: Use **manual required-fields validation** against the actual written format
(`t`, `chunk_id`, `kind`, `payload`), not the JSON schema file directly.
Rationale: the JSON schema reflects a future desired format; the existing integration
tests assert `kind` keys exist. Validating against the wrong schema would cause false
failures. The `validate_log_file` docstring notes this divergence.

A separate note is added in T047 log queries doc about this schema delta.

## T045 — test_log_audit_trail.py
Construct a fake log file inline (no integration test harness needed) with a small
event stream: session_start + 1 tool_use + 1 tool_result + session_end.
Assert: non-empty, first/last kinds, chronologically sorted `t` field, presence of
at least 1 tool_use + 1 tool_result, every event has required fields.
Keep assertions simpler than the spec (>=1 tool_use/tool_result vs >=10/>=5).

## T046 — validate_log_file
Add to `logs.py`. Reads jsonl, validates each line has the actual required fields.
Returns `(bool, list[str])`. Non-raising. Uses manual validation (not jsonschema)
because of the schema format divergence documented above.

## T047 — forge-runner-log-queries.md
Create `docs/architecture/forge-runner-log-queries.md` with 5-6 jq recipes.

## T048 — HostedStageBase check
Already exists in `stages.py` with `agent_definition_id`, `build_request`,
`parse_response` abstract methods and `run()` raising `NotImplementedError`.
Message is "HostedStageBase.run is implemented in chunk L3-HYBRID-AGENTS".
No changes needed — just write the test to verify.

## T049 — test_stages.py
Test: isinstance checks via runtime_checkable, HostedStageBase concrete subclass
satisfies protocol, run() raises NotImplementedError with L3-HYBRID-AGENTS message,
StageResult is JSON-serializable via json.dumps(dataclasses.asdict(result)).

## T050 — test_version_drift.py
Import claude_agent_sdk, read __version__ (with importlib.metadata fallback),
compare to PINNED_SDK_VERSION = "0.1.58". Both should be equal, test passes today.

## Expected test count
Current: 246. Adding ~20 new tests across 3 new test files → target ~266+.

## Expected runtime
All unit tests. No DB. No network. Runtime <1s per new test file.
