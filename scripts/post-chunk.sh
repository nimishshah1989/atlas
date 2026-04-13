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

# --- 3.5 Smoke probe: verify deployed slice still responds -------------
# Runs scripts/smoke-probe.sh against scripts/smoke-endpoints.txt. A hard
# failure here exits non-zero, which makes the runner mark this chunk
# BLOCKED — the whole point is to catch "green quality gate, dead product"
# before the next chunk starts building on broken foundations. See
# docs/specs/version-demo-gate.md for the rationale.
if [ -x "$REPO_ROOT/scripts/smoke-probe.sh" ]; then
  log "running post-deploy smoke probe"
  if ! REPO_ROOT="$REPO_ROOT" "$REPO_ROOT/scripts/smoke-probe.sh"; then
    log "smoke probe failed — leaving chunk for runner to mark BLOCKED"
    exit 1
  fi
else
  log "no smoke probe script — skipping slice regression check"
fi

# --- 4. Headless context sync: forge wiki + auto-memory ---------------
# One Claude spawn, two jobs:
#   (a) /forge-compile — fold session learnings into ~/.forge/knowledge/wiki/
#   (b) update the Claude Code auto-memory at
#       ~/.claude/projects/-home-ubuntu-atlas/memory/ so MEMORY.md is a
#       live summary of every chunk shipped so far. The next chunk's
#       boot-context step reads MEMORY.md first, so this is how we keep
#       Claude fully situated across stateless chunk sessions.
if command -v claude >/dev/null 2>&1; then
  log "spawning headless context sync (forge-compile + memory update)"
  COMPILE_LOG="orchestrator/logs/${CHUNK_ID}_context_sync.log"
  mkdir -p "$(dirname "$COMPILE_LOG")"
  MEM_DIR="$HOME/.claude/projects/-home-ubuntu-atlas/memory"
  SYNC_PROMPT="Run two tasks in this single session, in order. Do not modify project source code under /home/ubuntu/atlas except the memory path noted below.

TASK 1 — /forge-compile
Chunk ${CHUNK_ID} just completed the ATLAS V1.5 quality gate. Execute the /forge-compile skill: scan ~/.forge/knowledge/raw/, compare against ~/.forge/knowledge/wiki/index.md, create/update articles for new patterns, promote 2+ sightings from staging, and keep the wiki index under 200 lines.

TASK 2 — Auto-memory sync (MEMORY.md must stay live)
The Claude Code auto-memory lives at ${MEM_DIR}. MEMORY.md there is the index every future chunk reads during its Step 0 boot. Update it so it reflects chunk ${CHUNK_ID} landing:

1. Open ${MEM_DIR}/project_v15_chunk_status.md. Update the row for ${CHUNK_ID} to DONE with the current HEAD commit hash (run \`git -C /home/ubuntu/atlas rev-parse --short HEAD\`). Refresh the 'as of' date and the latest quality gate score from /home/ubuntu/atlas/.quality/report.json.
2. Open ${MEM_DIR}/MEMORY.md and ensure its one-line hook for the chunk ledger matches reality (e.g. 'C1–C9 DONE, C10–C11 PENDING'). Fix any stale counts.
3. Scan the session's git log (\`git -C /home/ubuntu/atlas log -n 20 --oneline\`) and diff summary for anything that should become a NEW memory file: a user feedback rule, a non-obvious project decision, or a reference to an external system. Follow the auto-memory rules in the Claude Code system prompt — write a new file in ${MEM_DIR}/ with proper frontmatter, add a one-line pointer to MEMORY.md. Do not duplicate existing memories; prefer updating.
4. Do NOT write ephemeral task state, code patterns derivable from the repo, or anything already in CLAUDE.md. Memory is for what a fresh future session cannot reconstruct.
5. When both tasks are complete, stage and commit any changes under ${MEM_DIR} with message 'forge: ${CHUNK_ID} — memory sync' (this directory is OUTSIDE the atlas repo, so git there is a separate concern — if it is not a git repo, just leave the files in place).

Report a short summary at the end: wiki articles touched, memory files touched, and the MEMORY.md line count."
  nohup claude -p "$SYNC_PROMPT" \
    --dangerously-skip-permissions \
    >"$COMPILE_LOG" 2>&1 &
  disown
  log "context sync spawned (pid $!), log: $COMPILE_LOG"
else
  log "claude binary not found — skipping context sync"
fi

log "done"
