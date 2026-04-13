# Chunk FD-4 — Deployment pipeline approach

## What was built

Three changes:
1. `backend/systemd/atlas-frontend.service` — new systemd unit, mirrors `atlas-backend.service`, runs `npm run start -- -p 3000` as user ubuntu, `After=atlas-backend.service`, `EnvironmentFile=/etc/atlas/frontend.env`.
2. `scripts/post-chunk.sh` — surgical insertion of `# --- 3.b Frontend build + restart (idempotent) ---` block between the existing backend restart `fi` and `# --- 3.5 Smoke probe` header. Step 3.5 preserved byte-identical (diff empty).
3. `CONTRIBUTING.md` — new section 7 "Deploying the Forge dashboard" with install commands and rollback procedure.
4. `scripts/smoke-endpoints.txt` — added `?http://localhost:3000/forge` as OPTIONAL entry.

## Approach

- Surgical edit with a single `Edit` call targeting the exact `fi` / `# --- 3.5` boundary.
- Preservation check: `awk '/^# --- 3\.5/,/^# --- 4/'` before and after — diff was empty.
- Build-failure semantics: 3.b block logs WARN and continues; smoke probe is the authoritative gate.

## Verification results

- `systemd-analyze verify` exited 0.
- Dry-run `FD4-TEST`: drift guard, residual commit, push, backend skip, frontend build succeeded, smoke probe all PASS, context sync spawned.
- Break test `FD4-BREAKTEST`: build failed, service NOT restarted, hook exited 0, smoke probe still passed (localhost:3000/forge is OPTIONAL).
- Corruption reverted and pushed.
