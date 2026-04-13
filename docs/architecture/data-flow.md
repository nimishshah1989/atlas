# ATLAS Data Flow — JIP → Compute → Own

> Moved out of `CLAUDE.md` in chunk S4. The rulebook points here; this file
> is the source of truth for "which table comes from where".

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

## Three Services

```
ATLAS NEVER queries de_* tables directly.
ATLAS calls JIP Data Core /internal/* API, which abstracts schema.

JIP Data Core (port 8000) → data warehouse, pipelines, /internal/ API
ATLAS API (port 8010)     → decision engine, agents, simulation, intelligence
TradingView MCP (sidecar) → TA signals, fundamentals, 13K screening fields
```

## What comes from JIP (read-only, via /internal/ API)

```
Equity:    2,743 stocks × 47 technicals × RS scores × OHLCV (2007→now)
MF:        13,380 funds × derived metrics × holdings × RS (2006→now)
ETF:       258 ETFs × technicals × RS
Global:    131 instruments × technicals × RS
Market:    breadth (2007→now), regime (2007→now)
Indices:   135 indices × prices × PE/PB
Macro:     826 indicators across 38 countries
Goldilocks: market views, sector rankings, stock ideas, oscillators
```

## What ATLAS computes (not in JIP)

```
RS momentum         = rs_composite(today) − rs_composite(28 days ago)
Quadrant            = LEADING/IMPROVING/WEAKENING/LAGGING from rs + momentum
Sector rollups      = 22 metrics per sector (GROUP BY sector)
MF weighted technicals = holdings × stock technicals
Index breadth       = constituents × technicals (equal-weighted)
MF holder count     = COUNT(DISTINCT mstar_id) per stock
Conviction assessment = 4 transparent pillars (RS, technical, external, institutional)
Decisions           = tracked from creation → outcome with lifecycle
```

## What ATLAS owns (writes to these tables)

```
atlas_intelligence    — central vector store (pgvector)
atlas_briefings       — LLM morning notes
atlas_simulations     — saved backtests + configs
atlas_decisions       — decision lifecycle tracking
atlas_alerts          — unified alerts (TV + RS + breadth + regime)
atlas_watchlists      — user watchlists
atlas_agent_scores    — agent prediction accuracy
atlas_agent_weights   — Darwinian weights (0.3–2.5)
atlas_agent_memory    — per-agent corrections and learnings
atlas_portfolios      — client portfolios (CAMS import)
atlas_tv_cache        — TradingView data cache
atlas_qlib_features   — Alpha158 factor values
atlas_query_log       — UQL query audit trail
```

Anything not in the ATLAS-owns list is read-through-JIP-client. Writing to a
`de_*` table is a hard stop condition.
