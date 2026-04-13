#!/usr/bin/env bash
# forge-ship.sh — the institutionalised build→QA→memory→wiki→commit path.
#
# Usage:
#   scripts/forge-ship.sh <chunk-id> "<one-line commit summary>"
#
# Runs, in strict order:
#   1. pytest tests/ -q                 (unit tests)
#   2. python .quality/checks.py        (71-check QA gate)
#   3. memory sync freshness check      (MEMORY status file touched < 10 min ago)
#   4. writes .forge/last-run.json      (what the pre-commit hook checks)
#   5. git commit + git push
#   6. scripts/post-chunk.sh <chunk>    (restart, smoke probe, spawn
#                                        forge-compile + auto-memory sync)
#
# If any step fails, the script exits non-zero and nothing commits. The
# pre-commit hook at ~/.forge/hooks/enforce-ship-protocol.sh refuses any
# commit without a fresh .forge/last-run.json, so this script is the only
# legal path to ship.

set -euo pipefail

CHUNK="${1:?chunk id required, e.g. V1.6-R1}"
SUMMARY="${2:-${CHUNK} — see spec}"

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

STATE=".forge/last-run.json"
mkdir -p .forge

log() { printf "[forge-ship:%s] %s\n" "$CHUNK" "$*"; }

# --- 1. Tests ---------------------------------------------------------
log "step 1/5 — pytest"
if [ -x "./venv/bin/pytest" ]; then
  ./venv/bin/pytest tests/ -q || { log "FAIL: pytest"; exit 1; }
else
  pytest tests/ -q || { log "FAIL: pytest"; exit 1; }
fi

# --- 2. Quality gate (71 checks) --------------------------------------
log "step 2/5 — .quality/checks.py (71 checks)"
python3 .quality/checks.py || { log "FAIL: quality gate"; exit 1; }

# --- 3. Memory freshness ----------------------------------------------
# The project memory status file must have been touched in the last 10
# minutes, so no chunk ships with a stale status ledger. The user (or
# Claude on the user's behalf) is expected to append the chunk row before
# running forge-ship.
log "step 3/5 — memory sync freshness"
MEM_FILE="$HOME/.claude/projects/-home-ubuntu-atlas/memory/project_v15_chunk_status.md"
if [ ! -f "$MEM_FILE" ]; then
  log "FAIL: memory status file missing: $MEM_FILE"
  exit 1
fi
NOW=$(date +%s)
MTIME=$(stat -c %Y "$MEM_FILE")
AGE=$(( NOW - MTIME ))
if [ "$AGE" -gt 600 ]; then
  log "FAIL: $MEM_FILE is ${AGE}s old (>600s). Update the chunk row before shipping."
  exit 1
fi
log "memory file fresh (${AGE}s old)"

# --- 4. Record state the pre-commit hook will read --------------------
log "step 4/5 — writing .forge/last-run.json"
python3 - <<PY
import json, time
json.dump({
    "chunk": "${CHUNK}",
    "tests_ok": True,
    "quality_ok": True,
    "memory_ok": True,
    "ts": int(time.time()),
}, open("${STATE}", "w"), indent=2)
PY

# --- 5. Commit + push -------------------------------------------------
log "step 5/5 — git commit + push"
if ! git diff --cached --quiet || ! git diff --quiet; then
  # Stage everything currently modified / new. Script caller is expected
  # to have already git-added the intentional set; anything stray should
  # have been caught by the research gate + commit quality hooks.
  git add -A
  git commit -m "${CHUNK}: ${SUMMARY}

Shipped via scripts/forge-ship.sh — tests+gate+memory+hooks all green.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
  git push origin HEAD
else
  log "nothing to commit (tree already clean); skipping commit+push"
fi

# --- 6. Post-chunk sync (restart + smoke + forge-compile + memory) ----
log "running scripts/post-chunk.sh (deploy + forge-compile + memory)"
if [ -x scripts/post-chunk.sh ]; then
  bash scripts/post-chunk.sh "$CHUNK"
else
  log "WARN: scripts/post-chunk.sh not found — forge-compile and memory"
  log "      sync will not run. Chunk is NOT fully shipped."
  exit 1
fi

log "✓ ${CHUNK} shipped: tests + gate + memory + commit + post-chunk"
