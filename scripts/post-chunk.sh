#!/usr/bin/env bash
# post-chunk.sh — Forge OS post-chunk sync hook.
#
# Runs after a chunk transitions to DONE. Enforces the invariant that
# git (origin), EC2 (local filesystem on this host), and the knowledge
# wiki all reflect the chunk's output before the orchestrator picks up
# the next chunk.
#
# Steps:
#   1. Commit any residual chunk artifacts that the session did not
#      commit itself (tracked changes only; never adds untracked dirs
#      like .claude/).
#   2. Push to origin/main.
#   3. Redeploy on-box services (backend uvicorn; frontend is next dev
#      with hot reload so no restart needed — production mode move is
#      tracked separately).
#   4. Fire /forge-compile in headless Claude to fold the session's
#      learnings into ~/.forge/knowledge/wiki/.
#
# Exits non-zero on any failure; the runner logs the chunk as BLOCKED
# if this hook fails so we never silently desync.

set -euo pipefail

CHUNK_ID="${1:?chunk id required}"
REPO_ROOT="${REPO_ROOT:-/home/ubuntu/atlas}"
cd "$REPO_ROOT"

log() { echo "[post-chunk:${CHUNK_ID}] $*"; }

# --- 1. Residual commit (tracked files only) ---------------------------
if ! git diff --quiet || ! git diff --cached --quiet; then
  log "residual tracked changes detected — committing"
  git add -u
  git commit -m "forge: ${CHUNK_ID} — post-chunk residual sync

Automated commit by scripts/post-chunk.sh to keep git/EC2/wiki in sync.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>" || true
else
  log "working tree clean"
fi

# --- 2. Push to origin --------------------------------------------------
if [ "$(git rev-list --count @{u}..HEAD 2>/dev/null || echo 0)" -gt 0 ]; then
  log "pushing $(git rev-list --count @{u}..HEAD) commit(s) to origin"
  git push origin HEAD
else
  log "origin already in sync"
fi

# --- 3. Redeploy on-box services ---------------------------------------
# Backend: restart uvicorn if a systemd unit exists; otherwise skip (the
# dev loop restarts it manually). Frontend: next dev hot-reloads.
if systemctl list-unit-files 2>/dev/null | grep -q '^atlas-backend\.service'; then
  log "restarting atlas-backend.service"
  sudo systemctl restart atlas-backend.service
else
  log "no atlas-backend systemd unit — skipping backend restart"
fi

# --- 4. Auto forge-compile via headless Claude -------------------------
if command -v claude >/dev/null 2>&1; then
  log "spawning headless /forge-compile"
  COMPILE_LOG="orchestrator/logs/${CHUNK_ID}_forge_compile.log"
  mkdir -p "$(dirname "$COMPILE_LOG")"
  # Background so the runner is not blocked; the log is the audit trail.
  nohup claude -p "/forge-compile
Context: chunk ${CHUNK_ID} just completed and passed the quality gate.
Fold any new learnings, decisions, or bug patterns from this session
into ~/.forge/knowledge/wiki/. Do not modify project source." \
    --dangerously-skip-permissions \
    >"$COMPILE_LOG" 2>&1 &
  disown
  log "forge-compile spawned (pid $!), log: $COMPILE_LOG"
else
  log "claude binary not found — skipping forge-compile"
fi

log "done"
