# Chunk 4 — Deployment pipeline

**Depends on:** Chunk 3 (frontend must build cleanly first)
**Blocks:** — (last chunk)
**Complexity:** S (<1h)
**PRD sections:** §6.1, §13

---

## Goal

Move the frontend off `next dev` onto `next start` under a systemd unit. Extend `scripts/post-chunk.sh` to rebuild and restart the frontend as part of every post-chunk sync. Keep `next dev` as a 24h fallback; cut over once stable.

## Files

### New
- `backend/systemd/atlas-frontend.service` — mirrors `atlas-backend.service`. Runs `next start -p 3000` from `/home/ubuntu/atlas/frontend`. `Restart=on-failure`. Environment file `/etc/atlas/frontend.env` for `FORGE_SHARE_TOKEN` and `NODE_ENV=production`. `User=ubuntu`. `After=atlas-backend.service`.

### Modified
- `scripts/post-chunk.sh` — **extend Step 3 (deploy), never replace it, and NEVER touch Step 3.5.** The existing Step 3.5 smoke-probe block (lines 62–76 as of 2026-04-13, `scripts/smoke-probe.sh` → BLOCKED on hard fail) is the V2 autonomous build's slice-regression safety net. The whole point of the smoke probe is that it runs AFTER both backend and frontend are redeployed but BEFORE context sync, so it catches "green gate, dead product." Clobbering it by rewriting the file would remove the very thing another in-flight session is relying on.

  **Edit strategy (surgical):**
  1. Keep Step 1 (residual commit), Step 2 (push), and Step 3's backend restart block exactly as they are.
  2. Add a NEW sub-block inside Step 3, AFTER the `atlas-backend.service` restart and BEFORE the Step 3.5 header comment. Label it `# --- 3.b Frontend build + restart (idempotent) ---` so it's clearly part of Step 3.
  3. That sub-block:
     - Checks for `frontend/package.json` + `frontend/src/**` changes since last commit OR a missing `.next/` directory.
     - Runs `cd frontend && npm ci --prefer-offline && npm run build` (output to a per-chunk log so failures are inspectable).
     - On build success: restarts `atlas-frontend.service` if the systemd unit is installed; logs and continues otherwise.
     - On build FAILURE: logs loudly, does NOT restart the service, and does NOT exit non-zero from the hook. Rationale: a broken frontend build is a regression to catch next, but it shouldn't block the chunk from reaching DONE. The stale frontend keeps serving, and Step 3.5's smoke probe will catch it if `/forge` actually returns 5xx. We let the smoke probe be the single gatekeeper.
     - Runs a local curl sanity check: `curl -fsS -o /dev/null -w '%{http_code}' http://localhost:3000/forge | grep -qE '^(200|401)$'`. Log-only, does NOT block — Step 3.5's smoke probe is the authoritative slice check.
  4. Step 3.5 (smoke probe) stays byte-identical. Verify by diffing before and after.
  5. Add the new frontend dashboard URLs to `scripts/smoke-endpoints.txt` as OPTIONAL entries (`?http://localhost:3000/forge`, `?http://localhost:8010/api/v1/system/heartbeat` — already optional from the earlier session's seeding), so the existing probe picks them up without a second script.

### Installation (one-time, not code)
- `sudo cp backend/systemd/atlas-frontend.service /etc/systemd/system/`
- `sudo mkdir -p /etc/atlas && sudo touch /etc/atlas/frontend.env`
- Add `FORGE_SHARE_TOKEN=<random-32-hex>` to `/etc/atlas/frontend.env` (via ssm param or manual).
- `sudo systemctl daemon-reload && sudo systemctl enable --now atlas-frontend.service`
- Document in `CONTRIBUTING.md` under a "Deploying the dashboard" section.

### Documentation
- `CONTRIBUTING.md` — new section "Deploying the Forge dashboard" with the install commands above and the rollback procedure (stop `atlas-frontend.service`, fall back to `next dev` manually).

## Systemd unit spec

```ini
[Unit]
Description=ATLAS Forge dashboard (Next.js)
After=network.target atlas-backend.service
Wants=atlas-backend.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/atlas/frontend
EnvironmentFile=/etc/atlas/frontend.env
Environment=NODE_ENV=production
ExecStart=/usr/bin/npm run start -- -p 3000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=atlas-frontend

[Install]
WantedBy=multi-user.target
```

## post-chunk.sh extension — exact insertion point

The block below goes INSIDE Step 3, AFTER the existing `atlas-backend.service` restart `fi` (around line 60) and BEFORE the `# --- 3.5 Smoke probe` header comment (around line 62). Do NOT touch Step 3.5 or anything after it.

```bash
# --- 3.b Frontend build + restart (idempotent) ---
# Runs AFTER backend restart, BEFORE the smoke probe. Build failures here
# are logged but do NOT block the chunk — Step 3.5's smoke probe is the
# authoritative "did deploy actually work" gate. A broken build leaves the
# old working build serving, and the probe will catch a real regression.
if [ -d "$REPO_ROOT/frontend" ]; then
  FE_LOG="orchestrator/logs/${CHUNK_ID}_frontend_build.log"
  mkdir -p "$(dirname "$FE_LOG")"
  log "building frontend (log: $FE_LOG)"
  if (cd "$REPO_ROOT/frontend" && npm ci --prefer-offline && npm run build) \
       >"$FE_LOG" 2>&1; then
    log "frontend build succeeded"
    if systemctl list-unit-files 2>/dev/null | grep -q '^atlas-frontend\.service'; then
      log "restarting atlas-frontend.service"
      sudo systemctl restart atlas-frontend.service
      sleep 2
      fe_code=$(curl -fsS -o /dev/null -w '%{http_code}' http://localhost:3000/forge 2>/dev/null || echo "000")
      case "$fe_code" in
        200|401) log "frontend local probe $fe_code" ;;
        *)       log "WARN frontend local probe returned $fe_code (smoke probe will confirm)" ;;
      esac
    else
      log "no atlas-frontend systemd unit — skipping frontend restart"
    fi
  else
    log "WARN frontend build failed — leaving old build running (see $FE_LOG)"
  fi
fi
```

## Acceptance criteria

1. `backend/systemd/atlas-frontend.service` exists and parses cleanly (`systemd-analyze verify backend/systemd/atlas-frontend.service` passes).
2. After installation: `systemctl status atlas-frontend.service` shows `active (running)`.
3. `curl http://localhost:3000/forge` returns 200 (or 401 if token set) — not connection refused.
4. Killing the Node process: `sudo pkill -f "next start"` — systemd auto-restarts within 10s.
5. `scripts/post-chunk.sh C12` (dry run against a fake chunk) runs the frontend build and smoke check successfully.
6. Deliberately break `frontend/src/app/forge/page.tsx` (syntax error), run the hook: build fails, service is NOT restarted, old build still serves, hook exits 0 (so the chunk can still reach DONE — smoke probe is the authoritative gate).
6a. **Step 3.5 preservation test:** `diff` the pre- and post-chunk `scripts/post-chunk.sh` restricted to lines between `# --- 3.5 Smoke probe` and the next `# ---` header. Must be zero diff. This is a regression check against clobbering the slice-regression safety net the V2 autonomous build depends on.
6b. **Smoke probe end-to-end:** deliberately break `http://localhost:8010/api/v1/stocks/universe` (a HARD endpoint in `smoke-endpoints.txt`), run the hook: Step 3.5 exits 1, runner marks chunk BLOCKED, chunk does NOT reach DONE. Restore the endpoint, run the hook again: passes.
7. `CONTRIBUTING.md` has a "Deploying the Forge dashboard" section with install + rollback steps.
8. Smoke test from the browser at `https://atlas.jslwealth.in/forge` after deploy: heartbeat strip is fresh, roadmap tree renders V1–V10, quality tiles show current scores.

## Rollback plan

If `atlas-frontend.service` misbehaves in production:
1. `sudo systemctl stop atlas-frontend.service`
2. `sudo systemctl disable atlas-frontend.service`
3. Manually start `next dev` as before (from a tmux session).
4. File a follow-up chunk to fix.

Keep `next dev` procedure documented in `CONTRIBUTING.md` even after cutover so rollback is one command away.

## Out of scope

- Nginx / Cloudflare config changes — out of scope; traffic already routes to port 3000.
- Backend systemd changes — `atlas-backend.service` already exists and works.
- Any code changes to the backend or frontend beyond what Chunks 1–3 delivered.
