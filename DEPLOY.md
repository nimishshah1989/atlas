# ATLAS Deploy Runbook

## Overview

ATLAS runs on a single EC2 host alongside the existing JIP Data Engine VPC. The
backend is a FastAPI app packaged via a multi-stage `Dockerfile`. Schema changes
are shipped through Alembic migrations that target the shared RDS instance under
a dedicated version table (`atlas_alembic_version`), so ATLAS and JIP do not
collide on migration history.

## Prerequisites

- Docker 24+ on the target host
- Network access to `jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com:5432`
- `.env` populated from `.env.example` (DB URL, CORS origins, JIP API base)
- IAM role or SSH key for the ATLAS EC2 host

## Local development

```bash
docker compose up --build
# backend  → http://localhost:8010
# frontend → http://localhost:3000
```

Hot reload on the frontend is served from a bind-mounted `frontend/` volume;
the backend image is rebuilt whenever `requirements.txt` or `backend/` changes.

## CI/CD

`.github/workflows/ci.yml` runs on every push to `main` and on PRs:

1. Install Python 3.12 + pinned deps
2. `ruff check` + `ruff format --check`
3. `mypy backend`
4. `pytest tests/ --cov=backend`
5. `python .quality/checks.py --gate --save` — any dimension < 80 fails CI
6. Frontend `npm ci && npm run build`
7. Docker image build (no push) to validate the Dockerfile

Artifacts: `quality-report` (`.quality/report.json`) is uploaded on every run.

## Database migrations

ATLAS owns only `atlas_*` tables. JIP's `de_*` tables are read-only and
excluded from autogenerate via `alembic/env.py::include_object`.

```bash
# create a new migration from model changes
alembic revision --autogenerate -m "short description"

# apply pending migrations
alembic upgrade head

# roll back the latest migration
alembic downgrade -1
```

The baseline is `alembic/versions/4fcfc8621e91_baseline_atlas_schema.py`. It
aligns the live `atlas_decisions`, `atlas_intelligence`, and `atlas_watchlists`
tables with the current SQLAlchemy models. The JIP `alembic_version` table is
intentionally left untouched.

## Production deploy (host)

```bash
# 1. pull latest
git pull origin main

# 2. apply migrations (dry-run first in a staging DB if possible)
docker compose run --rm backend alembic upgrade head

# 3. rebuild + restart
docker compose up -d --build backend

# 4. smoke test
curl -fsS http://localhost:8010/health
curl -fsS http://localhost:8010/api/v1/stocks/universe?limit=1
```

## Rollback

```bash
# revert to previous image tag
docker compose pull backend:previous-sha
docker compose up -d backend

# if schema rollback is required
docker compose run --rm backend alembic downgrade -1
```

Never run `alembic downgrade base` in production — ATLAS shares the RDS with
JIP and that would drop JIP alignment state.

## Health checks

- `GET /health` — liveness (Dockerfile `HEALTHCHECK` and compose)
- `GET /ready` — readiness (DB + JIP client reachable)
- CloudWatch metrics on the EC2 host: CPU, memory, disk
- Application logs via `structlog` to stdout → captured by Docker log driver

## Secrets management

- `.env` lives only on the host, never committed (see `.gitignore`)
- Secrets are rotated quarterly; rotate on the host and `docker compose up -d`
  to pick up new values
- CI does not need DB credentials — quality gate runs in offline mode
