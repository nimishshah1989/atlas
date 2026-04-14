#!/usr/bin/env bash
# Waits for the currently-running V3 forge-runner (pid from arg) to exit,
# verifies V3-9 reached DONE, then launches a fresh runner for V4-[1-7].
# If V3-9 did not end DONE, stops and leaves a note for the human.
set -u
WAIT_PID="${1:?usage: $0 <v3_runner_pid>}"
REPO="/home/ubuntu/atlas"
LOG="$REPO/.forge/logs/chain-v4.out"
cd "$REPO"

echo "[$(date -Is)] chain-v4 waiting on pid=$WAIT_PID" >> "$LOG"
while kill -0 "$WAIT_PID" 2>/dev/null; do
  sleep 30
done
echo "[$(date -Is)] v3 runner pid=$WAIT_PID exited" >> "$LOG"

V39_STATUS=$(sqlite3 "$REPO/orchestrator/state.db" "SELECT status FROM chunks WHERE id='V3-9';")
echo "[$(date -Is)] V3-9 status=$V39_STATUS" >> "$LOG"

if [ "$V39_STATUS" != "DONE" ]; then
  echo "[$(date -Is)] ABORT: V3-9 not DONE — refusing to start V4. Inspect .forge/logs/V3-9.log" >> "$LOG"
  exit 1
fi

echo "[$(date -Is)] launching V4 runner" >> "$LOG"
source "$REPO/venv/bin/activate"
exec python -m scripts.forge_runner \
  --filter 'V4-[1-7]' \
  --timeout 60m \
  --max-turns 400 \
  >> "$REPO/.forge/logs/v4-runner.out" 2>&1
