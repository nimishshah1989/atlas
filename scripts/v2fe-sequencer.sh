#!/usr/bin/env bash
# v2fe-sequencer.sh — autonomous V2FE-0..V2FE-9 build sequencer
# Runs in background; monitor tails .forge/logs/v2fe-sequencer.log
# Usage: bash scripts/v2fe-sequencer.sh >> .forge/logs/v2fe-sequencer.log 2>&1

set -euo pipefail

PYTHON="/home/ubuntu/atlas/venv/bin/python"
REPO="/home/ubuntu/atlas"
DB="$REPO/orchestrator/state.db"

log() { echo "[$(date -u +%H:%M:%SZ)] $*"; }

chunk_status() {
  sqlite3 "$DB" "SELECT status FROM chunks WHERE id='$1';" 2>/dev/null || echo "NOT_FOUND"
}

wait_for_done() {
  local id="$1"
  local timeout_mins="${2:-120}"
  local elapsed=0
  log "Waiting for $id ..."
  while true; do
    s=$(chunk_status "$id")
    if [ "$s" = "DONE" ]; then
      log "$id DONE"
      return 0
    elif [ "$s" = "FAILED" ]; then
      reason=$(sqlite3 "$DB" "SELECT failure_reason FROM chunks WHERE id='$id';" 2>/dev/null || echo "unknown")
      log "SEQUENCER_BLOCKED: $id FAILED — $reason"
      exit 1
    fi
    sleep 30
    elapsed=$((elapsed + 1))
    if [ $elapsed -ge $((timeout_mins * 2)) ]; then
      log "SEQUENCER_BLOCKED: $id timed out after ${timeout_mins}m"
      exit 1
    fi
  done
}

run_chunk() {
  local id="$1"
  local s
  s=$(chunk_status "$id")
  if [ "$s" = "DONE" ]; then
    log "$id already DONE — skipping"
    return 0
  fi
  log "Starting forge_runner for $id ..."
  cd "$REPO"
  "$PYTHON" -m scripts.forge_runner --filter "^${id}$" --once --timeout 90m
  wait_for_done "$id" 120
}

smoke_check_page() {
  local page="$1"
  local html="$REPO/frontend/mockups/${page}.html"
  if [ ! -f "$html" ]; then
    log "SMOKE WARN: $html not found"
    return
  fi
  local fixture_count
  fixture_count=$(grep -c 'fixtures/' "$html" 2>/dev/null || echo 0)
  local endpoint_count
  endpoint_count=$(grep -c 'data-endpoint=' "$html" 2>/dev/null || echo 0)
  log "SMOKE $page: data-endpoint=$endpoint_count fixture-refs=$fixture_count"
  if [ "$fixture_count" -gt 5 ]; then
    log "SMOKE WARN $page: $fixture_count fixture refs still present — wiring may be incomplete"
  fi
  if grep -q 'atlas-data.js' "$html" 2>/dev/null; then
    log "SMOKE $page: atlas-data.js loader present OK"
  else
    log "SMOKE WARN $page: atlas-data.js loader NOT found"
  fi
  for state in atlas-loading atlas-empty atlas-stale atlas-error; do
    if grep -q "$state" "$html" 2>/dev/null; then
      log "SMOKE $page: $state OK"
    else
      log "SMOKE WARN $page: $state class missing"
    fi
  done
}

log "=== V2FE sequencer started (state.db synced) ==="
log "Chunks: V2FE-0 → V2FE-1 → V2FE-2..7 → V2FE-8 → V2FE-9"

# Phase 0: loader + criteria
run_chunk "V2FE-0"

# Phase 1: backend gaps (longest, must land before pages)
run_chunk "V2FE-1"

# Phase 2: per-page wiring
for chunk in V2FE-2 V2FE-3 V2FE-4 V2FE-5 V2FE-6 V2FE-7; do
  run_chunk "$chunk"
done

smoke_check_page "today"
smoke_check_page "explore-country"
smoke_check_page "breadth"
smoke_check_page "stock-detail"
smoke_check_page "mf-detail"
smoke_check_page "mf-rank"

# Phase 3: states rollout
run_chunk "V2FE-8"

# Phase 4: E2E gate
run_chunk "V2FE-9"

log "=== SEQUENCER_DONE: V2FE-0..V2FE-9 all DONE ==="
