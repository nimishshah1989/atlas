# ATLAS Security Policy

## Secret management

All runtime secrets — database URLs, API tokens, rate-limit overrides — are
loaded from environment variables via `backend/config.Settings` (Pydantic v2).
The canonical list of variables lives in `backend/.env.example`. The real
`.env` file is git-ignored and must never be committed.

## Secret rotation

Rotation is a deliberate, logged operation. Follow this procedure for every
credential (DB password, JIP internal token, future API keys):

1. **Generate** the new secret in the source-of-truth system (RDS console for
   DB passwords, JIP admin for internal tokens).
2. **Stage** the new value in AWS SSM Parameter Store under
   `/atlas/prod/<var-name>` as a `SecureString`.
3. **Deploy** by restarting the ATLAS API service on EC2 #2; the systemd unit
   pulls the new value from SSM into the process environment on boot.
4. **Verify** `/api/v1/system/health` returns 200 and a tailing
   `journalctl -u atlas-api` shows no auth errors for at least five minutes.
5. **Revoke** the old credential in the source system.
6. **Record** the rotation in `BUILD_STATUS.md` with the date, operator, and
   reason (scheduled rotation, suspected leak, employee offboarding).

Scheduled rotations: database password every 90 days, JIP internal token every
180 days. Unscheduled rotations are mandatory within one hour of any suspected
leak (accidental commit, shared screen, lost device).

## Dependency vulnerabilities

`pip-audit` runs as part of `python .quality/checks.py --dim security` and
also in CI. Any HIGH or CRITICAL advisory must be resolved (upgrade) or
explicitly documented here with a justification and target remediation date.

Current advisories (as of 2026-04-12):

- **CVE-2025-8869 / CVE-2026-1703 (pip)** — tarball/wheel path-traversal in
  the `pip` tool itself. Not reachable from ATLAS runtime: ATLAS does not
  install packages at runtime and the production container is built from a
  pinned lock-file. Tracked for the next base-image refresh.

## CORS

Wildcard origins are forbidden. `CORS_ORIGINS` is a comma-separated allowlist
parsed in `backend/main.py`; the quality gate fails if `allow_origins=["*"]`
is ever reintroduced.

## Rate limiting

All `/api/v1/*` routes are rate-limited via `slowapi` with a per-IP default of
`RATE_LIMIT_DEFAULT` (60/minute). The limiter is attached to `app.state` and
wired through the `SlowAPIMiddleware`.

## Reporting

Report suspected vulnerabilities to security@jslwealth.in. Do not open a
public GitHub issue for security reports.
