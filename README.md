# ATLAS — Market Intelligence Engine

ATLAS is the Jhaveri Intelligence Platform's market intelligence, instrument
selection, and investment simulation engine. It replaces MarketPulse, Global
Pulse, MF Pulse, and Sector Compass with a single deterministic, explainable,
fault-tolerant system serving PMS fund managers, registered advisors, and
retail MF investors.

**Core flow:** Global → Country → Sector → Instrument (Stock / MF / ETF).
Horizon is 1 month to 1 year. ATLAS is **not** a trading system — no intraday,
no algo execution.

For the full architecture, read [`ATLAS-DEFINITIVE-SPEC.md`](./ATLAS-DEFINITIVE-SPEC.md)
and the operational summary in [`CLAUDE.md`](./CLAUDE.md).

---

## Quickstart

### Prerequisites
- Python 3.11+
- Node 20+
- PostgreSQL 15+ with `pgvector` extension
- Access to the JIP Data Core `/internal/` API (see `backend/clients/jip_client.py`)

### Backend
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn backend.main:app --port 8010 --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

### Tests
```bash
pytest tests/ -v --tb=short
ruff check . --select E,F,W
mypy . --ignore-missing-imports
```

### Docker
```bash
docker compose up --build
```
See [`DEPLOY.md`](./DEPLOY.md) for production deployment on EC2.

---

## Repository layout

```
backend/         FastAPI application (routes, core, models, clients, db, agents)
frontend/        Next.js 14 app (Pro / Advisor / Retail shells)
contracts/       Pydantic schemas — single source of truth for API contracts
alembic/         ATLAS-owned migrations (atlas_* tables)
tests/           pytest suites (unit + integration)
orchestrator/    Forge build orchestrator (plan.yaml, runner, state.db)
.quality/        Quality gate engine (checks.py, standards.md)
build-dashboard/ Read-only build dashboard at atlas.jslwealth.in/forge
infra/           Terraform + systemd units
docs/            Architecture diagrams, ADRs, contributor docs
scripts/         Operational scripts (post-chunk sync, deploy helpers)
```

---

## Architecture (one paragraph)

ATLAS runs on its own EC2 host alongside JIP Data Core in the same VPC.
ATLAS **never** queries `de_*` tables directly — it calls the JIP `/internal/`
API for all warehouse reads, and writes only to its own `atlas_*` tables.
The decision engine, agents, simulation, and intelligence layers live in
`backend/core/`; routes are thin and delegate to core. The frontend consumes
the typed Pydantic contracts under `contracts/`. See
[`docs/architecture.md`](./docs/architecture.md) for diagrams and
[`docs/adr/`](./docs/adr/) for decision records.

---

## Four Laws (non-negotiable)

1. **Prove, never claim** — run tests, show output, verify visually.
2. **No synthetic data** — ever. No hardcoded mocks in production code.
3. **Backend first always** — API working before any frontend touches it.
4. **See what you build** — verify visually, check the browser, confirm output.

## System guarantees

Deterministic · Explainable · Fault-tolerant · Traceable · Idempotent.
If a feature violates any of these, it MUST NOT ship.

---

## Contributing

Read [`CONTRIBUTING.md`](./CONTRIBUTING.md) before opening a PR. ATLAS is
built chunk-by-chunk through the Forge orchestrator (`orchestrator/plan.yaml`);
every chunk must pass `python .quality/checks.py --gate` before it is
considered DONE.

## Security

Report vulnerabilities per [`SECURITY.md`](./SECURITY.md). Never commit
secrets, keys, or production data.

## License

Proprietary — Jhaveri Securities Ltd. All rights reserved.
