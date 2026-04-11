# ATLAS — Market Intelligence Engine
## Jhaveri Intelligence Platform

> **Full spec:** Read `ATLAS-DEFINITIVE-SPEC.md` in this directory for the complete
> 4,200-line architecture document. This CLAUDE.md is the operational summary —
> what you MUST know before writing any code.

---

## What ATLAS Is

A market intelligence, instrument selection, and investment simulation platform
that replaces MarketPulse, Global Pulse, MF Pulse, and Sector Compass. One engine
serving three audiences: PMS fund managers (Pro), Registered Advisors (Advisor),
and retail MF investors (Retail).

**Core flow:** Global → Country → Sector → Instrument (Stock / MF / ETF)

**NOT a trading system.** Horizon is 1 month to 1 year. No intraday. No algo execution.

---

## Four Laws (non-negotiable, inherited from Forge OS)

1. **Prove, never claim** — run tests, show output, verify visually
2. **No synthetic data** — ever. No hardcoded mocks in production code
3. **Backend first always** — API working before any frontend touches it
4. **See what you build** — verify visually, check the browser, confirm the output

---

## System Guarantees (non-negotiable)

1. **Deterministic** — same data_as_of → same outputs for core computations
2. **Explainable** — every number traceable to source table + formula
3. **Fault-tolerant** — partial data > no data, graceful degradation everywhere
4. **Traceable** — full provenance on every computed value
5. **Idempotent** — pipeline can be re-run safely without side effects

If ANY feature violates these → it MUST NOT be deployed.

---

## Critical Schema Facts (spec v2 was WRONG — these are correct)

| What | WRONG (spec v2) | CORRECT (actual DB) |
|------|-----------------|---------------------|
| Stock primary key | `instrument_id INTEGER` | `id UUID` |
| Stock symbol | `symbol` | `current_symbol` |
| Market cap | column on de_instrument | separate `de_market_cap_history`, column `cap_category` |
| RS columns | `rs_percentile, rs_score` | `rs_1w, rs_1m, rs_3m, rs_6m, rs_12m, rs_composite` |
| RS entity ref | `instrument_id` | `entity_id` |
| RS benchmark | `benchmark` | `vs_benchmark` |
| MF primary key | `fund_code` | `mstar_id` |
| MF category | `category` | `category_name` |
| MF fund house | `fund_house` | `amc_name` |
| MF NAV date | `date` | `nav_date` |
| Breadth columns | `advances, declines` | `advance, decline` (singular) |
| Regime composite | `composite_score` | `confidence` |

**ALWAYS verify column names against this table before writing queries.**

---

## Infrastructure

```
EC2 #1: JIP DATA ENGINE (existing, 13.206.34.214)
  JIP Data Core FastAPI (port 8000) — data warehouse, /internal/* API
  PostgreSQL RDS (private subnet) — 27M rows, 60+ tables
  SSH key: ~/.ssh/jsl-wealth-key.pem

EC2 #2: ATLAS (new, to be provisioned)
  ATLAS FastAPI backend (port 8010)
  ATLAS Next.js frontend (port 3000)
  Build orchestrator + dashboard (port 3001, during dev)
  Same VPC — internal network to JIP EC2 (<1ms latency)

RDS: jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com:5432/data_engine
  Contains: all de_* tables (JIP) + all atlas_* tables (ATLAS-owned)
  pgvector extension for intelligence engine
```

---

## Architecture — Three Services

```
ATLAS NEVER queries de_* tables directly.
ATLAS calls JIP Data Core /internal/* API, which abstracts schema.

JIP Data Core (port 8000) → data warehouse, pipelines, /internal/ API
ATLAS API (port 8010)     → decision engine, agents, simulation, intelligence
TradingView MCP (sidecar) → TA signals, fundamentals, 13K screening fields
```

---

## Data Flow — What Comes From Where

```
FROM JIP (read-only, via /internal/ API):
  Equity: 2,743 stocks × 47 technicals × RS scores × OHLCV (2007→now)
  MF: 13,380 funds × derived metrics × holdings × RS (2006→now)
  ETF: 258 ETFs × technicals × RS
  Global: 131 instruments × technicals × RS
  Market: breadth (2007→now), regime (2007→now)
  Indices: 135 indices × prices × PE/PB
  Macro: 826 indicators across 38 countries
  Goldilocks: market views, sector rankings, stock ideas, oscillators

ATLAS COMPUTES (not in JIP):
  RS momentum = rs_composite(today) - rs_composite(28 days ago)
  Quadrant = LEADING/IMPROVING/WEAKENING/LAGGING from rs + momentum
  Sector rollups = 22 metrics per sector (GROUP BY sector)
  MF weighted technicals = holdings × stock technicals
  Index breadth = constituents × technicals (equal-weighted)
  MF holder count = COUNT(DISTINCT mstar_id) per stock
  Conviction assessment = 4 transparent pillars (RS, technical, external, institutional)
  Decisions = tracked from creation → outcome with lifecycle

ATLAS OWNS (writes to these tables):
  atlas_intelligence — central vector store (pgvector)
  atlas_briefings — LLM morning notes
  atlas_simulations — saved backtests + configs
  atlas_decisions — decision lifecycle tracking
  atlas_alerts — unified alerts (TV + RS + breadth + regime)
  atlas_watchlists — user watchlists
  atlas_agent_scores — agent prediction accuracy
  atlas_agent_weights — Darwinian weights (0.3-2.5)
  atlas_agent_memory — per-agent corrections and learnings
  atlas_portfolios — client portfolios (CAMS import)
  atlas_tv_cache — TradingView data cache
  atlas_qlib_features — Alpha158 factor values
  atlas_query_log — UQL query audit trail
```

---

## Build Order — Vertical Slices (CRITICAL)

**BUILD V1 FIRST. Complete V1 before ANY V2+ work. This is non-negotiable.**

```
V1:  Market → Sector → Stock → Decision (MUST COMPLETE FIRST)
V2:  MF slice (category → fund → holdings drill-down)
V3:  Simulation slice (VectorBT + tax + QuantStats)
V4:  Portfolio slice (casparser + Riskfolio-Lib + attribution)
V5:  Intelligence slice (briefings, debate, Darwinian evolution)
V6:  TradingView slice (MCP bridge, charts, bidirectional sync)
V7:  ETF + Global slice
V8:  Advisor shell
V9:  Retail shell
V10: Qlib + Advanced (Alpha158, ML models, parameter optimization)
```

### V1 Completion Criteria (ALL must pass before V2)

```
□ /api/v1/stocks/universe returns valid data matching contract
□ /api/v1/stocks/sectors returns 31 sectors × 22 metrics
□ /api/v1/stocks/{symbol} returns deep-dive with conviction pillars
□ POST /api/v1/query handles basic equity queries (filters + sort)
□ Frontend: FM navigates Market → Sector → Stock flow
□ Deep-dive panel shows all conviction pillar data
□ Decisions generated for quadrant changes
□ FM can accept/ignore/override decisions
□ Sector rollup stock_count sums to ~2,700
□ RS momentum matches manual calculation
□ Integration tests ALL passing
□ No float in any financial calculation
□ Response times: universe <2s, deep-dive <500ms
```

---

## Technology Stack (what we fork vs build vs install)

### Fork & Adapt (overlay our JIP data)
- **ai-hedge-fund** (virattt, 50K stars) — investor personality agents, risk manager, portfolio manager. Swap `src/tools/api.py` with JIP client.
- **TradingAgents** (TauricResearch, 3K stars) — bull/bear debate, memory recall, vendor routing. Port debate + memory into our system.
- **FinRobot** (AI4Finance, 7K stars) — sector analyst templates, report generation pipeline.

### Pip Install (battle-tested, no custom code)
- **vectorbt** — simulation (1M backtests in 20s)
- **quantstats** — tear sheets (60+ metrics, HTML reports)
- **empyrical-reloaded** — risk/return metrics
- **alphalens-reloaded** — RS factor validation
- **riskfolio-lib** — portfolio optimization (SEBI constraints)
- **optuna** — parameter optimization (TPE sampler)
- **pandas-ta** — 210+ technical indicators
- **casparser** — CAMS/KFintech CAS PDF parsing
- **hmmlearn** — HMM regime detection
- **pgvector** — intelligence engine vectors
- **langgraph** — agent orchestration (90K stars)
- **qlib** — 158 alpha factors + ML model zoo

### Build In-House (our moat)
- JIP /internal/ API service layer
- Central intelligence engine (pgvector orchestration)
- Darwinian evolution framework (scoring, weights, mutation, spawning)
- Indian FIFO tax engine (pre/post July 2024, STCG/LTCG, cess)
- UQL query engine (Bloomberg-grade unified query layer)
- Decision lifecycle system (creation → outcome tracking)
- Event system (16 event types, priority classification)
- TV bidirectional sync
- Indian market contextualization (SEBI, NSE sectors, lakh/crore)
- Three experience shells (Pro, Advisor, Retail)

---

## Project Conventions

```python
# Financial values: Decimal, NEVER float
from decimal import Decimal
rs_composite = Decimal("4.53")  # YES
rs_composite = 4.53              # NEVER

# All query params: Optional with defaults
async def get_universe(
    benchmark: Optional[str] = "NIFTY 500",
    sector: Optional[str] = None,
    rs_min: Optional[Decimal] = None,
) -> StockUniverseResponse:

# Indian formatting
format_currency(1234567890) → "₹1,23,45,67,890"  # lakh/crore
format_number(12345678) → "1.23 Cr"

# Dates: IST timezone aware
from datetime import datetime, timezone, timedelta
IST = timezone(timedelta(hours=5, minutes=30))
now_ist = datetime.now(IST)

# Logging: structlog, NEVER print()
import structlog
log = structlog.get_logger()
log.info("sector_rollup_computed", sectors=31, stocks=2689, duration_ms=342)

# API: FastAPI + Pydantic v2
# DB: SQLAlchemy 2.0 async + asyncpg
# Migrations: Alembic
# Tests: pytest + pytest-asyncio
```

---

## Test Commands

```bash
# Backend
pytest tests/ -v --tb=short
pytest tests/integration/ -v  # integration tests (requires JIP API running)

# Lint
ruff check . --select E,F,W

# Type check
mypy . --ignore-missing-imports

# Frontend
cd ~/atlas-frontend && npm test
```

---

## Hard Stop Conditions

**Claude MUST halt immediately and log error if:**

- Schema mismatch between contract and implementation
- Integration test failure after 3 retry attempts
- Data inconsistency (e.g., sector stock_count doesn't sum to universe count)
- Financial calculation producing float instead of Decimal
- Non-deterministic test (different results on consecutive runs)
- Attempting to write to de_* tables (JIP data, read-only)
- Attempting to start V2+ work before V1 completion criteria pass

**On hard stop:** Log full error context to BUILD_STATUS.md.
Do NOT attempt workarounds. Flag for human review.

---

## Key File Locations

```
ATLAS-DEFINITIVE-SPEC.md  — full 4,200-line architecture spec (READ THIS)
contracts/                — Pydantic schemas for ALL API contracts
BUILD_STATUS.md           — current build progress (updated by orchestrator)
backend/                  — FastAPI application
  clients/jip_client.py  — HTTP client to JIP /internal/ API
  core/                  — domain logic (no HTTP, no DB imports)
  models/                — Pydantic request/response schemas
  routes/                — FastAPI routers (thin, delegate to core/)
  db/                    — ATLAS-owned tables only
  agents/                — agent definitions + orchestration
frontend/                — Next.js (in fie2 repo, /atlas/* routes)
tests/                   — unit + integration tests
```

---

## Context Discipline

- **One chunk per session.** Fresh context per chunk.
- All subagents: `context: fork`. Main agent sees summaries only.
- Read THIS file + relevant contracts before every chunk.
- After completing a chunk: commit, update BUILD_STATUS.md, move on.
- Do NOT accumulate state across chunks — each session is independent.

---

## References

- Full spec: `ATLAS-DEFINITIVE-SPEC.md` (same directory)
- JIP Data Core: `/Users/nimishshah/projects/jip data core/`
- MarketPulse (fie2): `github.com/nimishshah1989/fie2`
- Memory files: `~/.claude/projects/-Users-nimishshah-projects-atlas/memory/`
