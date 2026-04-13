# build-dashboard (DEPRECATED)

The Python FastAPI build dashboard was replaced in C8 by a Next.js page at
`frontend/src/app/forge/page.tsx`. The new dashboard:

- Lives inside the existing ATLAS Next.js app (no extra service)
- Reads chunk state from `orchestrator/state.db` via `/forge/api`
- Reads quality scores from `.quality/report.json`
- Tails the most recent log under `orchestrator/logs/`
- Is served at `https://atlas.jslwealth.in/forge` via the nginx config in
  `infra/nginx/forge.conf` with TLS issued by `infra/certbot/issue.sh`

This directory is kept only as a deprecation marker and may be removed once
the new dashboard is verified in production.
