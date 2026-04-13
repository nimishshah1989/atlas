---
chunk: L2-RUNNER Phase 9
project: ATLAS
date: 2026-04-13
---

# Phase 9 Polish — Approach

## Tasks: T051–T059 + schema fix + T060/061/062 deferred to conductor

## Data scale
No data-layer work. All file I/O on small config files.

## T051 — API key leak detector
- Add check_1_10_runner_log_keys() to checks.py
- Scans: .forge/logs/**/* + .forge/runner-state.json + specs/003-forge-runner/**/*
- Pattern: sk-ant-api03-[A-Za-z0-9_-]{20,}  (matches real keys, not regex patterns)
- Skip binary files (UnicodeDecodeError)
- Score: 5/5 if no matches, 0/5 if any match
- The tasks.md spec files mention the pattern as a regex string — they do NOT contain
  actual keys, so no false positive expected
- Security dim after: 75/85 eligible = 88% → stays above 80 gate
- NOTE: existing 1.1 scores 10/20 due to test file _FAKE_API_KEY = "sk-ant-api03-..."
  The new check must NOT scan tests/ (it scans only the three listed paths)

## T052 — systemd unit
- Create systemd/ dir + atlas-forge-runner.service
- ExecStart uses `python -m scripts.forge_runner` (module path in venv)

## T053 — forge-runner.md architecture doc
- ~150 lines, ASCII diagram, monitoring, debugging playbook, recovery, systemd cheat-sheet

## T054 — remove ralph
- .ralph/ EXISTS (AGENT.md, PROMPT.md, fix_plan.md, live.log, logs, progress.json, status.json)
- .ralphrc EXISTS
- .gitignore has .ralph/ and .ralphrc lines (line 31-33) — remove them
- git rm -rf .ralph/ and delete .ralphrc

## T055 — CLAUDE.md ralph references
- CLAUDE.md has no ralph references currently (confirmed by read)
- grep -c 'ralph' → already 0; no change needed

## T056 — memory files
- Write feedback_forge_runner.md to ~/.claude/projects/.../memory/
- Append to MEMORY.md
- Update feedback_forge_ship_protocol.md if it has ralph

## T057 — forge-runner-status chmod +x
- Already should be, but verify and ensure
- quickstart.md already has ./scripts/forge-runner-status references

## T051-follow — schema fix
- Update contracts/log-event.schema.json:
  - required: ["t", "chunk_id", "kind", "payload"]
  - Add chunk_id (string) and kind (enum) properties
  - Remove evt/session_id from required
  - Keep legacy properties as optional

## T058 — quality gate run (execute after all changes)

## T059 — test_integration_live.py (write only, do not run)

## Edge cases
- The existing 1.1 false-positive on test_failure_record.py is pre-existing; not our concern
- New check 1.10 must not scan tests/ — it scans specific paths only
- Schema fix must not break existing tests (validate_log_file already uses actual format)
