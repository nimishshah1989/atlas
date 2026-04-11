# ATLAS — Definitive Architecture & Build Specification
## Jhaveri Intelligence Platform
## Version 4.0 · April 2026

---

## DOCUMENT PURPOSE

This is the single source of truth for building ATLAS. Every detail needed to build
the complete system is in this document. No external documents needed. No ambiguity.

This document will be fed to Claude Code CLI running autonomously on the ATLAS EC2
server. Claude will read this, build the system chunk by chunk, test continuously,
and commit working code — 24/7, no human intervention, all permissions bypassed.

---

## TABLE OF CONTENTS

1. [What ATLAS Is](#1-what-atlas-is)
2. [Infrastructure](#2-infrastructure)
3. [The Data Foundation — JIP Data Core](#3-the-data-foundation)
4. [What ATLAS Computes — Every Metric Explicitly](#4-what-atlas-computes)
5. [Qlib Alpha Layer — 158 Factors](#5-qlib-alpha-layer)
6. [The Central Intelligence Engine](#6-central-intelligence-engine)
7. [The Agent System](#7-the-agent-system)
8. [The Simulation Engine](#8-the-simulation-engine)
9. [The Portfolio Engine](#9-the-portfolio-engine)
10. [TradingView Integration](#10-tradingview-integration)
11. [API Layer — Every Endpoint](#11-api-layer)
12. [Frontend — Three Experience Shells](#12-frontend)
13. [The Autonomous Build System](#13-autonomous-build)
14. [Development Phases & Chunks](#14-development-phases)
15. [Coordination & Quality](#15-coordination)
16. [System Hardening & Execution Discipline](#16-system-hardening)
17. [Unified Query Layer — Bloomberg-Grade API](#17-unified-query-layer)
18. [Composable Response Model](#18-composable-response)
19. [Data Timing Layers](#19-data-timing-layers)
20. [API Design Principles](#20-api-design-principles)
21. [Event & Alert System](#21-event-alert-system)
22. [Query Governance & Execution Engine](#22-query-governance)
23. [Decision Lifecycle System](#23-decision-lifecycle)
24. [Vertical Slice — V1 Delivery Unit](#24-vertical-slice)
25. [Technology Stack — Complete](#25-technology-stack)
26. [Appendices](#26-appendices)

---

## 1. WHAT ATLAS IS

### The Problem

Indian wealth management is 5-10 years behind global platforms in tooling. Fund managers
at PMS firms use 7 separate systems daily — Bloomberg for global data, ACE Equity for
Indian fundamentals, NSE website for bulk deals, Screener.in for quick ratios, Excel for
models, their PMS system for portfolio tracking, and WhatsApp for client communication.
Client reporting takes 2-3 person-days per quarter per 50 clients. When a fund manager
leaves, all research knowledge leaves with them.

Registered Investment Advisors (RIAs) have it worse — no Indian-first fund comparison
tool with institutional-quality analytics exists. Morningstar Direct costs ₹15L+/year
and is US-centric. RIAs use ValueResearch (retail-grade) and Excel.

Retail MF investors use Groww/Kuvera/ET Money — good for buying funds, poor for
understanding what they own. No overlap analysis, no factor exposure, no drawdown
visualization, no tax-optimized rebalancing.

No single platform serves all three audiences from one intelligence engine.

### The Solution

ATLAS is a market intelligence, instrument selection, and investment simulation platform
that replaces MarketPulse, Global Pulse, MF Pulse, and Sector Compass with one unified
system. It serves three audiences through one intelligence engine:

- **ATLAS Pro** — for PMS fund managers: data-dense, Bloomberg-style depth, stock-level
  analysis, portfolio attribution, investment committee workflow
- **ATLAS Advisor** — for RIAs: fund discovery, model portfolio construction, client
  onboarding, portfolio gap analysis, client review reports
- **ATLAS Retail** — for MF investors: fund discovery, portfolio tracking, SIP management,
  goal planning, clean mobile-first UX

### The Core Flow

The same at every level, across all three shells:

```
Global → Country → Sector → Instrument (Stock / Mutual Fund / ETF)
```

At every level: relative strength ranking, breadth metrics, momentum, key technicals.
Click deeper for more detail. Click an instrument for a comprehensive deep-dive page
containing technical analysis, fundamental snapshot, peer comparison, institutional
holdings, research intelligence, pattern history, simulation quick-test, and portfolio
context — all on one page.

### What ATLAS Is NOT

- NOT a trading system. No intraday signals. No algo execution. Horizon is 1 month to 1 year.
- NOT a data warehouse. JIP Data Core is the data warehouse. ATLAS reads from it.
- NOT built from scratch. 70-80% of capabilities come from forking/pip-installing
  battle-tested open-source tools. ATLAS contextualizes, orchestrates, and presents.

### What Makes ATLAS Different

1. **One engine, three experiences.** Same intelligence, appropriate depth per audience.
2. **RS as the organizing principle.** Everything is ranked by relative strength — stocks,
   sectors, funds, ETFs, global instruments. RS is the primary lens.
3. **Central Intelligence Engine.** Every agent writes findings to a shared vector store.
   Every agent reads from it. Intelligence compounds daily. The system has institutional
   memory that survives personnel changes.
4. **Self-improving agents.** Each agent has Darwinian evolution — predictions scored against
   outcomes, weights adjusted, worst performers mutated, new specialists spawned.
5. **Fund manager's brain in the loop.** Voice notes, commentary, qualitative views — all
   ingested, tagged, vectorized, and available to every agent. Two-way system.
6. **Indian-first.** SEBI compliance, Indian tax (FIFO, STCG/LTCG, cess), lakh/crore
   formatting, NSE/BSE sector taxonomy, MF category taxonomy, CAMS report parsing.

---

## 2. INFRASTRUCTURE

### Two-Machine Architecture

```
EC2 #1: "JIP DATA ENGINE" (EXISTING — 13.206.34.214)
  Instance: t3.large → DOWNSIZE to t3.medium after ATLAS launches
  Purpose: Data warehouse + nightly pipelines ONLY
  IP: 13.206.34.214 (public) / 172.31.10.182 (private)
  VPC: vpc-070a59f3d15f253d6
  Subnet: subnet-0aa2d27d016a63938
  AZ: ap-south-1b

  Runs:
    • JIP Data Core FastAPI (port 8000) — data ingestion + /internal/ API
    • Nightly pipelines (OHLCV, technicals, RS, breadth, regime)
    • Redis (pipeline job queue)

  After ATLAS launch — REMOVE:
    • marketpulse container (fie2-api)
    • mf-pulse container
    • champion containers (if migrated)
    • mfsim containers

  Stays lean: JIP Data Core + Redis only.
  Cost after downsize: ~₹2,500/month


EC2 #2: "ATLAS" (NEW — to be provisioned)
  Instance: t3.xlarge (4 vCPU, 16GB RAM)
  Storage: 200GB EBS gp3
  Same VPC: vpc-070a59f3d15f253d6
  Same Subnet: subnet-0aa2d27d016a63938
  AZ: ap-south-1b (same as JIP — internal network latency <1ms)
  Elastic IP: to be assigned → atlas.jslwealth.in

  Runs PERMANENTLY:
    • ATLAS FastAPI backend (port 8010)
    • ATLAS Next.js frontend (port 3000)
    • Nginx reverse proxy (port 80/443)
    • Qlib batch pipeline (daily cron)
    • Agent orchestration daemon
    • Intelligence engine queries (against RDS via pgvector)

  Runs DURING DEVELOPMENT ONLY:
    • Claude Code CLI (autonomous build, 24/7)
    • Build progress dashboard (port 3001)

  Cost: ~₹10,000/month (t3.xlarge)


RDS: "JIP DATA ENGINE" (EXISTING — private subnet)
  Host: jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com
  Port: 5432
  Database: data_engine
  User: jip_admin
  Engine: PostgreSQL
  Region: ap-south-1 (Mumbai)

  Contains:
    • All de_* tables (JIP Data Core — 27M rows, 60+ tables)
    • All atlas_* tables (ATLAS-owned — briefings, simulations, watchlists, alerts, intelligence)
    • pgvector extension for intelligence engine

  Both EC2 instances access RDS via private subnet (no internet traversal).


COMMUNICATION PATTERN:
  User browser → ATLAS EC2 (nginx → Next.js + FastAPI)
  ATLAS EC2 → JIP EC2 (HTTP, internal network, port 8000, /internal/* API)
  ATLAS EC2 → RDS (PostgreSQL, private subnet, port 5432)
  JIP EC2 → RDS (PostgreSQL, private subnet, port 5432)
  TradingView.com → ATLAS EC2 (HTTPS webhook, port 443)
  ATLAS EC2 → TradingView MCP (local Node.js sidecar)
```

### Security Groups

```
ATLAS EC2 Security Group:
  Inbound:
    SSH (22) — your IP only
    HTTP (80) — 0.0.0.0/0
    HTTPS (443) — 0.0.0.0/0
    Custom (3001) — your IP only (build dashboard during development)
  Outbound:
    All traffic — 0.0.0.0/0

  Internal (same VPC):
    JIP EC2 port 8000 — ATLAS calls JIP /internal/ API
    RDS port 5432 — ATLAS queries database

RDS Security Group (existing):
  Add inbound rule: PostgreSQL (5432) from ATLAS EC2 security group
```

### DNS

```
atlas.jslwealth.in → ATLAS EC2 Elastic IP (nginx → port 3000 frontend)
atlas-api.jslwealth.in → ATLAS EC2 Elastic IP (nginx → port 8010 backend)
build.atlas.jslwealth.in → ATLAS EC2 Elastic IP (nginx → port 3001, during dev only)
```

---

## 3. THE DATA FOUNDATION — JIP DATA CORE

### What JIP Already Has (ATLAS reads, never writes)

JIP Data Core is a PostgreSQL data warehouse with 27M+ rows across 60+ tables.
Nightly pipelines ingest data from NSE, BSE, AMFI, Morningstar, yfinance, and FRED.
All data is pre-computed and available via SQL.

ATLAS accesses JIP through a new `/internal/` API layer added to the existing JIP
FastAPI application. ATLAS never queries de_* tables directly — it calls JIP's API,
which abstracts schema details and handles query optimization.

#### Equity Data (2,743 stocks)

```
TABLE: de_instrument (2,743 rows)
  Columns: id (UUID), current_symbol, isin, company_name, exchange, series,
           sector, industry, nifty_50 (bool), nifty_200 (bool), nifty_500 (bool),
           listing_date, bse_symbol, is_active, is_suspended, is_tradeable,
           symbol (legacy), created_at, updated_at

  Key facts:
    • id is UUID, NOT integer (spec v2 was wrong)
    • current_symbol is the NSE ticker (e.g., HDFCBANK)
    • sector has 31 values: Consumer Durables (274), Infrastructure (256),
      Chemicals (223), IT (177), Financial Services (151), FMCG (151),
      Capital Goods (141), Pharma (116), Metal (108), Automobile (104),
      Realty (93), Energy (73), Diversified (71), Capital Markets (65),
      Media (63), Healthcare (59), Tourism (47), Logistics (44),
      Banking (41), Services (40), Oil & Gas (37), Digital (28),
      Defence (21), EV & Auto (10), Conglomerate (10), Telecom (7),
      MNC (6), Rural (6), Consumption (6), Power (2), Housing (1)
    • All 2,743 are marked is_active=true
    • nifty_50: 50 stocks, nifty_200: 200 stocks, nifty_500: 500 stocks


TABLE: de_equity_ohlcv (partitioned by year, ~4.1M total rows)
  Columns: instrument_id (FK→de_instrument.id), date, open, high, low,
           close, close_adj, volume, delivery_pct
  Date range: 2007-01-01 → 2026-04-09 (19+ years)
  Partitions: de_equity_ohlcv_y2007 through de_equity_ohlcv_y2026

  Key facts:
    • close_adj is split/bonus adjusted — USE THIS for backtesting
    • delivery_pct has ~24% coverage (backfill pending)
    • Partitioned by year — JIP handles partition routing


TABLE: de_equity_technical_daily (4,016,598 rows)
  47 columns computed daily from OHLCV:

  Moving Averages (8):
    sma_50, sma_200, ema_10, ema_20, ema_21, ema_50, ema_200, close_adj

  Momentum Oscillators (13):
    rsi_14, rsi_7, rsi_9, rsi_21,
    macd_line, macd_signal, macd_histogram,
    stochastic_k, stochastic_d,
    roc_5, roc_10, roc_21, roc_63

  Trend Strength (3):
    adx_14, plus_di, minus_di

  Volume Indicators (4):
    obv, mfi_14, relative_volume, delivery_vs_avg

  Volatility (7):
    volatility_20d, volatility_60d,
    bollinger_upper, bollinger_lower, bollinger_width,
    disparity_20, disparity_50

  Risk Metrics (5):
    beta_nifty, sharpe_1y, sortino_1y, max_drawdown_1y, calmar_ratio

  Generated Boolean Flags (2):
    above_50dma (close_adj > sma_50), above_200dma (close_adj > sma_200)

  Date range: 2007-01-01 → 2026-04-09


TABLE: de_corporate_actions (14,923 rows)
  Columns: id, instrument_id, ex_date, action_type, dividend_type,
           ratio_from, ratio_to, cash_value, new_instrument_id,
           adj_factor, notes
  Action types: dividends, splits, bonuses, rights, mergers, demergers, buybacks


TABLE: de_market_cap_history (12,217 rows)
  Columns: instrument_id, effective_from, cap_category, effective_to, source
  Current distribution (effective_to IS NULL):
    large: 100 stocks, mid: 149 stocks, small: 1,999 stocks


TABLE: de_symbol_history
  Tracks historical symbol changes (e.g., when a company renames its ticker)
```

#### Relative Strength Data (14,765,737 rows — THE primary signal)

```
TABLE: de_rs_scores (14,765,737 rows)
  Columns: date, entity_type, entity_id, vs_benchmark,
           rs_1w, rs_1m, rs_3m, rs_6m, rs_12m, rs_composite,
           computation_version, created_at, updated_at

  CRITICAL SCHEMA NOTE (spec v2 was wrong):
    • Column is entity_id, NOT instrument_id
    • Column is vs_benchmark, NOT benchmark
    • Columns are rs_1w through rs_composite, NOT rs_percentile/rs_score
    • entity_id is UUID for equities, mstar_id for MFs, ticker for ETFs

  Entity breakdown:
    equity:  10,525,551 rows | 2,281 unique stocks | 2016-04-18 → 2026-04-09
    mf:       3,009,018 rows |   841 unique funds  | 2016-04-18 → 2026-04-09
    etf:        860,456 rows |   185 unique ETFs   | 2016-04-08 → 2026-04-09
    sector:     212,506 rows |    31 sectors        | 2016-04-18 → 2026-04-09
    global:     121,895 rows |    90 instruments    | 2016-04-08 → 2026-03-18

  Benchmarks and row counts:
    NIFTY 50:           4,582,397 rows
    NIFTY 500:          4,582,339 rows
    NIFTY MIDCAP 100:   4,582,339 rows
    ^SPX:                 552,331 rows
    SPY:                  430,020 rows

  RS composite formula: weighted average of (instrument return - benchmark return)
  across 5 periods. Weights: 1w:5%, 1m:15%, 3m:25%, 6m:30%, 12m:25%.
```

#### Market Structure

```
TABLE: de_breadth_daily (4,381 rows, 2007-01-02 → 2026-04-09)
  Columns: date, advance, decline, unchanged, total_stocks, ad_ratio,
           pct_above_200dma, pct_above_50dma, new_52w_highs, new_52w_lows,
           mcclellan_oscillator, mcclellan_summation

  Current (2026-04-09): advance=1043, decline=1202, pct_above_200dma=16.81%,
  pct_above_50dma=49.51%, new_52w_highs=44, new_52w_lows=5


TABLE: de_market_regime (4,383 rows, 2007-01-02 → 2026-04-09)
  Columns: computed_at, date, regime, confidence,
           breadth_score, momentum_score, volume_score,
           global_score, fii_score, indicator_detail (JSONB),
           computation_version

  SCHEMA NOTE: column is confidence, NOT composite_score (spec v2 wrong)
  Sub-scores: breadth_score, momentum_score, volume_score, global_score, fii_score
  (spec v2 said: breadth_score, volume_score, trend_score, volatility_score — WRONG)

  Regime values: BULL, BEAR, SIDEWAYS (possibly RECOVERY)
  Current (2026-04-09): SIDEWAYS, confidence=43.07%,
  breadth_score=46.47, momentum_score=46.50
```

#### Indices

```
TABLE: de_index_master (135 rows)
  Columns: index_code, index_name, category, created_at, updated_at
  Categories: thematic (52), strategy (42), sectoral (22), broad (19)

TABLE: de_index_constituents (2,660 rows)
  Columns: index_code, instrument_id, effective_from, weight_pct,
           effective_to, created_at, updated_at
  NOTE: weight_pct is NULL for all 2,660 rows (weights not backfilled)
  Active constituents (effective_to IS NULL):
    NIFTY 500: 500, NIFTY 200: 200, NIFTY 100: 100, NIFTY 50: 50, etc.

TABLE: de_index_prices (138,493 rows, 2016-04-07 → 2026-04-09)
  Columns: date, index_code, open, high, low, close, volume,
           pe_ratio, pb_ratio, div_yield
  83 indices tracked with daily OHLCV + valuations
```

#### Mutual Funds

```
TABLE: de_mf_master (13,380 rows)
  Columns: mstar_id (PK), amfi_code, isin, fund_name, amc_name,
           category_name, broad_category, is_index_fund, is_etf,
           is_active, inception_date, closure_date, merged_into_mstar_id,
           primary_benchmark, expense_ratio, investment_strategy

  SCHEMA NOTE: primary key is mstar_id (Morningstar ID), NOT fund_code
  Category column is category_name, NOT category
  Fund house column is amc_name, NOT fund_house
  NO plan_type column on master (inferred from fund_name)
  NO aum column on master (from category flows)

TABLE: de_mf_nav_daily (partitioned by year, ~1.4M+ total rows)
  Columns: nav_date, mstar_id, nav (and other columns per partition)
  Date range: 2006-04-01 → 2026-04-09 (20 YEARS)
  NOTE: date column is nav_date, NOT date

TABLE: de_mf_derived_daily (727,398 rows)
  Columns: nav_date, mstar_id,
           derived_rs_composite, nav_rs_composite, manager_alpha,
           coverage_pct,
           sharpe_1y, sharpe_3y, sharpe_5y,
           sortino_1y, sortino_3y, sortino_5y,
           max_drawdown_1y, max_drawdown_3y, max_drawdown_5y,
           volatility_1y, volatility_3y,
           stddev_1y, stddev_3y, stddev_5y,
           beta_vs_nifty, information_ratio, treynor_ratio

  KEY CONCEPT:
    derived_rs_composite = holdings-weighted RS (how strong are the stocks this fund holds)
    nav_rs_composite = NAV-based RS (how the fund itself is performing)
    manager_alpha = derived_rs - nav_rs (manager's stock-picking skill)

TABLE: de_mf_holdings (230,254 rows, 838 funds, 100% mapped)
  Columns: id, mstar_id, as_of_date, holding_name, isin,
           instrument_id, weight_pct, shares_held, market_value,
           sector_code, is_mapped

TABLE: de_mf_sector_exposure (13,211 rows, 824 funds)
  Columns: mstar_id, sector, weight_pct, stock_count, as_of_date

TABLE: de_mf_category_flows (3,125 rows)
  Columns: month_date, category, net_flow_cr, gross_inflow_cr,
           gross_outflow_cr, aum_cr, sip_flow_cr, sip_accounts, folios

TABLE: de_mf_lifecycle (469 rows)
  Events: launches, merges, name changes, closures
```

#### ETFs

```
TABLE: de_etf_master (258 rows)
  Columns: ticker (PK), name, exchange, country, currency, sector,
           asset_class, category, benchmark, expense_ratio,
           inception_date, is_active, source
  Countries: US, India, UK, HK, JP

TABLE: de_etf_ohlcv (435,746 rows, 2016-04-01 → 2026-04-10)

TABLE: de_etf_technical_daily (435,746 rows, 24 columns)
  Columns: date, ticker, close, sma_50, sma_200,
           ema_10, ema_20, ema_50, ema_200,
           rsi_14, rsi_7, macd_line, macd_signal, macd_histogram,
           roc_5, roc_21, volatility_20d, volatility_60d,
           bollinger_upper, bollinger_lower, relative_volume,
           adx_14, above_50dma, above_200dma
```

#### Global & Macro

```
TABLE: de_global_instrument_master (131 rows)
  Columns: ticker, name, instrument_type, exchange, currency, country,
           category, source
  Types: indices, forex, commodities, crypto, bonds

TABLE: de_global_prices (180,835 rows, 2010-01-03 → 2026-04-09)
TABLE: de_global_technical_daily (180,835 rows, same 24 technical columns as ETF)

TABLE: de_macro_master (826 indicators across 38 countries)
TABLE: de_macro_values (115,445 rows, some series back to 1802)
  Key series: US Treasury curve (3M-30Y), global yields, SOFR,
  inflation breakevens, CPI, GDP, PMI, employment, housing
```

#### Goldilocks Research Intelligence

```
TABLE: de_goldilocks_market_view
  Daily market view: trend direction, Nifty/Bank Nifty levels,
  support/resistance, observations

TABLE: de_goldilocks_sector_view
  Sector rankings: sector, rank, momentum_score, commentary

TABLE: de_goldilocks_stock_ideas
  Stock recommendations: symbol, entry_price, target_price,
  stop_loss, rationale (from Stock Bullet, Big Catch reports)

TABLE: de_oscillator_weekly (2,250 rows)
TABLE: de_oscillator_monthly (2,250 rows)
TABLE: de_divergence_signals
TABLE: de_fib_levels (6,654 rows)
TABLE: de_index_pivots (30 rows)
TABLE: de_intermarket_ratios (12 rows)
```

#### Flows & Institutional

```
TABLE: de_institutional_flows (3 rows — sparse, needs backfill)
  Columns: date, category, market_type, gross_buy, gross_sell,
           net_flow, source

TABLE: de_mf_category_flows (3,125 rows)
  Monthly category-level MF flow data (covered above)

TABLE: de_fo_summary (0 rows — schema exists, no data yet)
  F&O summary: pcr_oi, pcr_volume, total_oi, fii positions, max_pain
```

#### Client & Portfolio (existing but unused)

```
TABLE: de_clients (0 rows — PII-encrypted, schema ready)
TABLE: de_client_keys (0 rows)
TABLE: de_portfolios (0 rows)
TABLE: de_portfolio_nav (0 rows)
TABLE: de_portfolio_transactions (0 rows)
TABLE: de_portfolio_holdings (0 rows)
TABLE: de_portfolio_risk_metrics (0 rows)
```

### JIP Internal API (NEW — added to existing JIP FastAPI)

These endpoints are added to the JIP Data Core FastAPI application under
`/internal/` prefix. They are NOT exposed to the internet — only callable
from within the same VPC (ATLAS EC2 → JIP EC2).

```
EQUITY:
  GET /internal/equity/universe?benchmark=NIFTY 500&sector=Banking&nifty_50=true
    Returns: all active instruments joined with latest price, technicals, RS, market cap, MF holder count
    Response: list of StockData objects (see contracts section)

  GET /internal/equity/{instrument_id}
    Returns: full detail for one stock including corporate actions, symbol history

  GET /internal/equity/{instrument_id}/ohlcv?from=2024-01-01&to=2026-04-09
    Returns: OHLCV time series (JIP handles partition routing)

  GET /internal/equity/{instrument_id}/rs-history?benchmark=NIFTY 500&months=12
    Returns: daily RS scores for the specified period

  GET /internal/equity/{instrument_id}/technicals-history?from=...&to=...&columns=rsi_14,macd_histogram
    Returns: daily technicals time series for specified columns

SECTORS:
  GET /internal/sectors/universe
    Returns: all sectors with stock-level aggregations (22 metrics per sector)
    JIP computes GROUP BY de_instrument.sector joining latest technicals + RS + price
    Heavy query — cached 5 minutes

  GET /internal/sectors/{sector_name}/rs-history
    Returns: sector-level RS time series from de_rs_scores WHERE entity_type='sector'

MUTUAL FUNDS:
  GET /internal/mf/universe?benchmark=NIFTY 500&category=Large Cap&broad_category=Equity
    Returns: all funds with latest RS, derived metrics, weighted technicals, category flows

  GET /internal/mf/{mstar_id}/holdings
    Returns: fund's stock holdings with each stock's current RS + technicals

  GET /internal/mf/{mstar_id}/sectors
    Returns: sector exposure with each sector's current RS

  GET /internal/mf/{mstar_id}/nav-history?from=...&to=...
    Returns: NAV time series (JIP handles year-partition routing)

  GET /internal/mf/{mstar_id}/rs-history?months=12
  GET /internal/mf/holding-stock/{instrument_id}
    Returns: which funds hold this stock, sorted by weight

  GET /internal/mf/overlap?funds=A,B
    Returns: common holdings between two funds with overlap percentage

ETFs:
  GET /internal/etf/universe
  GET /internal/etf/{ticker}/ohlcv?from=...&to=...
  GET /internal/etf/{ticker}/rs-history

GLOBAL & MACRO:
  GET /internal/global/universe
  GET /internal/global/{ticker}/price-history
  GET /internal/macro/key-ratios
    Returns: latest values for key macro series with 10-point sparkline data
    Series: US 10Y, US 2Y, DXY, Gold, Crude WTI, VIX, BTC, USD/INR, India 10Y

MARKET STRUCTURE:
  GET /internal/market/breadth
  GET /internal/market/breadth/history?from=...&to=...
  GET /internal/market/regime
  GET /internal/market/regime/history?from=...&to=...

INDICES:
  GET /internal/indices/list
  GET /internal/indices/{index_code}/constituents
  GET /internal/indices/{index_code}/prices?from=...&to=...
  GET /internal/indices/{index_code}/breadth
    Returns: computed breadth for this specific index (equal-weighted from constituents × technicals)

GOLDILOCKS:
  GET /internal/goldilocks/latest
  GET /internal/goldilocks/oscillators
  GET /internal/goldilocks/fib-levels
  GET /internal/goldilocks/pivots
  GET /internal/goldilocks/intermarket-ratios

STATUS:
  GET /internal/status
    Returns: data freshness for all key tables
    { equity_ohlcv_as_of, rs_scores_as_of, mf_nav_as_of,
      breadth_as_of, regime_as_of, global_prices_as_of,
      pipeline_last_run, anomaly_count }
```

---

## 4. WHAT ATLAS COMPUTES — EVERY METRIC EXPLICITLY

ATLAS reads from JIP and computes the following. These are NOT in JIP.

### 4.1 RS Momentum (per instrument)

```
For every entity (stock, MF, ETF, sector, global instrument):
  rs_momentum = rs_composite(today) - rs_composite(28 calendar days ago)

  Source: de_rs_scores (latest date) vs de_rs_scores (date - 28 days)
  Computed for: each benchmark separately (NIFTY 50, NIFTY 500, NIFTY MIDCAP 100)
```

### 4.2 Quadrant Classification (per instrument)

```
Based on rs_composite and rs_momentum:
  LEADING    = rs_composite > 0 AND rs_momentum > 0   (outperforming & accelerating)
  IMPROVING  = rs_composite < 0 AND rs_momentum > 0   (underperforming but improving)
  WEAKENING  = rs_composite > 0 AND rs_momentum < 0   (outperforming but decelerating)
  LAGGING    = rs_composite < 0 AND rs_momentum < 0   (underperforming & decelerating)
```

### 4.3 Sector Rollups (22 metrics per sector)

```
Computed by GROUP BY de_instrument.sector, joining latest technicals + RS + price:

Composition:
  sector                  → group key (31 sectors)
  stock_count             → COUNT(*)

RS:
  avg_rs_composite        → AVG(rs_composite)
  avg_rs_momentum         → AVG(rs_momentum)  [rs_momentum is computed by ATLAS, not JIP]
  sector_quadrant         → derived from avg_rs_composite + avg_rs_momentum

Breadth:
  pct_above_200dma        → COUNT(above_200dma=true) / COUNT(*) × 100
  pct_above_50dma         → COUNT(above_50dma=true) / COUNT(*) × 100
  pct_above_ema21         → COUNT(close_adj > ema_21) / COUNT(*) × 100

Momentum:
  avg_rsi_14              → AVG(rsi_14)
  pct_rsi_overbought      → COUNT(rsi_14 > 70) / COUNT(*) × 100
  pct_rsi_oversold        → COUNT(rsi_14 < 30) / COUNT(*) × 100

Trend:
  avg_adx                 → AVG(adx_14)
  pct_adx_trending        → COUNT(adx_14 > 25) / COUNT(*) × 100
  pct_macd_bullish        → COUNT(macd_histogram > 0) / COUNT(*) × 100
  pct_roc5_positive       → COUNT(roc_5 > 0) / COUNT(*) × 100

Risk:
  avg_beta                → AVG(beta_nifty)
  avg_sharpe              → AVG(sharpe_1y)
  avg_sortino             → AVG(sortino_1y)
  avg_volatility_20d      → AVG(volatility_20d)
  avg_max_dd              → AVG(max_drawdown_1y)
  avg_calmar              → AVG(calmar_ratio)

Institutional:
  avg_mf_holders          → AVG(mf_holder_count)  [mf_holder_count from de_mf_holdings]

Disparity:
  avg_disparity_20        → AVG(disparity_20)
```

### 4.4 MF Weighted Technicals (per fund)

```
Computed from de_mf_holdings × de_equity_technical_daily:
For each fund, weight-average its stock holdings' technicals:

  wtd_rsi_14             → SUM(weight_pct × rsi_14) / SUM(weight_pct)
  wtd_adx_14             → SUM(weight_pct × adx_14) / SUM(weight_pct)
  wtd_beta               → SUM(weight_pct × beta_nifty) / SUM(weight_pct)
  wtd_volatility_20d     → SUM(weight_pct × volatility_20d) / SUM(weight_pct)
  wtd_relative_volume    → SUM(weight_pct × relative_volume) / SUM(weight_pct)
  wtd_sharpe_1y          → SUM(weight_pct × sharpe_1y) / SUM(weight_pct)
  wtd_sortino_1y         → SUM(weight_pct × sortino_1y) / SUM(weight_pct)
  wtd_max_drawdown_1y    → SUM(weight_pct × max_drawdown_1y) / SUM(weight_pct)

  pct_above_200dma       → SUM(weight_pct × above_200dma) / SUM(weight_pct) × 100
  pct_above_50dma        → SUM(weight_pct × above_50dma) / SUM(weight_pct) × 100
  pct_macd_bullish       → SUM(weight_pct × (macd_histogram > 0)) / SUM(weight_pct) × 100
  pct_rsi_overbought     → SUM(weight_pct × (rsi_14 > 70)) / SUM(weight_pct) × 100
  pct_rsi_oversold       → SUM(weight_pct × (rsi_14 < 30)) / SUM(weight_pct) × 100
  pct_adx_trending       → SUM(weight_pct × (adx_14 > 25)) / SUM(weight_pct) × 100

  coverage_pct           → SUM(weight_pct of mapped holdings)
  stock_count            → COUNT(DISTINCT instrument_id)

  This is computed as a new JIP pipeline step (nightly, after technicals).
  Stored in new table: de_mf_weighted_technicals
```

### 4.5 Index Breadth (per index)

```
Computed from de_index_constituents × de_equity_technical_daily:
Equal-weighted (since weight_pct is NULL for all constituents):

  Per index:
    constituent_count     → COUNT(*)
    pct_above_200dma      → COUNT(above_200dma=true) / COUNT(*) × 100
    pct_above_50dma       → COUNT(above_50dma=true) / COUNT(*) × 100
    pct_macd_bullish      → COUNT(macd_histogram > 0) / COUNT(*) × 100
    pct_adx_trending      → COUNT(adx_14 > 25) / COUNT(*) × 100
    avg_rsi               → AVG(rsi_14)
    avg_adx               → AVG(adx_14)
```

### 4.6 MF Holder Count (per stock)

```
  mf_holder_count = COUNT(DISTINCT mstar_id) FROM de_mf_holdings
                    WHERE instrument_id = X
                    AND as_of_date = (SELECT MAX(as_of_date) FROM de_mf_holdings)
```

### 4.7 MF Category Rollups (per category)

```
Computed by GROUP BY de_mf_master.category_name, joining RS + derived:

  category               → group key
  fund_count             → COUNT(*)
  avg_rs_composite       → AVG(rs_composite)
  avg_rs_momentum        → AVG(rs_momentum)
  avg_sharpe_1y          → AVG(sharpe_1y)
  avg_alpha              → AVG(manager_alpha)
  avg_beta               → AVG(beta_vs_nifty)
  avg_max_dd             → AVG(max_drawdown_1y)
  net_flow_cr            → from de_mf_category_flows (latest month)
  sip_flow_cr            → from de_mf_category_flows
  total_aum_cr           → SUM(aum_cr) from de_mf_category_flows
```

### 4.8 Conviction Assessment (per instrument — 4 pillars)

```
NOT a composite score. Four transparent pillars, each explained:

PILLAR 1: Relative Strength
  Inputs: rs_composite, rs_momentum, quadrant
  Output: plain English description
  "RS is +4.5 vs NIFTY 500, improving for 3 weeks, quadrant: LEADING"

PILLAR 2: Technical Health
  Inputs: above_200dma, above_50dma, rsi_14, adx_14, macd_histogram,
          mfi_14, obv, sharpe_1y, relative_volume, delivery_vs_avg
  Output: X/10 checks passing, each with explanation
  "8/10 passing: above both DMAs ✓, RSI 58 healthy ✓, ADX 35 trending ✓..."

PILLAR 3: External Confirmation
  Inputs: TradingView TA summary (1D/1W/1M), Piotroski F-Score, Altman Z-Score,
          Goldilocks stock idea (if exists)
  Output: multi-timeframe TA + fundamental quality assessment
  "TV Daily: STRONG BUY, Weekly: BUY, Monthly: NEUTRAL. Piotroski 7/9."

PILLAR 4: Institutional Conviction
  Inputs: mf_holder_count, delivery_pct, category_net_flow,
          quarter-over-quarter MF position changes
  Output: institutional interest assessment
  "124 MFs hold this stock. Delivery 42% (above average). Category flows positive."

Each pillar is EXPLAINED, not scored. The fund manager reads all four and decides.
No black box. No composite score. No aggressive weightings.
```

---

## 5. QLIB ALPHA LAYER — 158 FACTORS

### What Qlib Is

Microsoft Qlib (40.6K GitHub stars) is an AI-oriented quantitative investment platform.
ATLAS uses it as the ML/alpha research layer — NOT as the primary backend.

Qlib takes raw OHLCV data and computes 158 alpha factors that our JIP technicals
don't cover. These factors are designed for ML model consumption — they're normalized,
cross-sectionally comparable, and proven in academic research.

### How Qlib Integrates

```
JIP PostgreSQL (de_equity_ohlcv)
    │
    ├── CSV export (nightly, automated)
    │   or custom DataLoader that queries PostgreSQL
    │
    ▼
Qlib Alpha158 Feature Engine
    │
    │ Computes 158 factors per stock per day
    │
    ▼
Qlib ML Models (optional, Phase 2+)
    │ LightGBM / XGBoost / Transformer
    │ Predict: P(stock outperforms in next 5/20 days)
    │
    ▼
Signal scores written to PostgreSQL
    │ (new table: atlas_qlib_signals)
    │
    ▼
Available to ATLAS intelligence engine as another data source
```

### The 158 Alpha158 Factors — Explicit

```
KBAR FACTORS (9) — Candlestick quantification:
  KMID:  (close - open) / open                         → intraday direction
  KLEN:  (high - low) / open                           → intraday range
  KMID2: (close - open) / (high - low + 1e-12)         → close position in range
  KUP:   (high - max(open,close)) / open               → upper shadow length
  KUP2:  (high - max(open,close)) / (high - low)       → upper shadow ratio
  KLOW:  (min(open,close) - low) / open                → lower shadow length
  KLOW2: (min(open,close) - low) / (high - low)        → lower shadow ratio
  KSFT:  (2*close - high - low) / open                 → close shift from center
  KSFT2: (2*close - high - low) / (high - low)         → normalized close shift

  WHY: These turn visual candlestick patterns (doji, hammer, engulfing) into
  numerical features that ML models can learn from. JIP doesn't compute these.


ROLLING FACTORS (29 types × 5 windows = 145 factors):
  Each computed for windows: [5, 10, 20, 30, 60] days

  Returns:
    ROC(d):   close / Ref(close, d) - 1                → d-day return

  Moving Averages:
    MA(d):    Mean(close, d) / close                   → MA ratio to current price

  Volatility:
    STD(d):   Std(close, d) / close                    → normalized volatility

  Regression vs Market:
    BETA(d):  slope of (stock returns vs market returns) over d days
    RSQR(d):  R² of above regression (how much market explains)
    RESI(d):  residual of above regression (idiosyncratic return)

  Range Position:
    MAX(d):   Max(high, d) / close                     → distance from d-day high
    MIN(d):   Min(low, d) / close                      → distance from d-day low
    QTLU(d):  80th percentile of close over d / close   → upper quantile distance
    QTLD(d):  20th percentile of close over d / close   → lower quantile distance
    RANK(d):  rank of today's close in d-day window    → percentile rank in window

  Stochastic-like:
    RSV(d):   (close - Min(low,d)) / (Max(high,d) - Min(low,d))

  Time-Index (WHEN did high/low happen?):
    IMAX(d):  index of max high in d days / d          → recency of high
    IMIN(d):  index of min low in d days / d           → recency of low
    IMXD(d):  IMAX - IMIN                              → high-low time spread

  Price-Volume Correlation:
    CORR(d):  Corr(close, log(volume+1), d)            → price-volume agreement
    CORD(d):  Corr(close/Ref(close,1), log(volume), d) → return-volume correlation

  Directional Counting:
    CNTP(d):  mean(close > Ref(close,1) over d days)   → % of up days
    CNTN(d):  mean(close < Ref(close,1) over d days)   → % of down days
    CNTD(d):  CNTP - CNTN                              → net direction

  Cumulative Returns:
    SUMP(d):  sum of positive returns over d days       → cumulative gains
    SUMN(d):  sum of negative returns over d days       → cumulative losses
    SUMD(d):  SUMP - SUMN                              → net gain-loss

  Volume Analysis:
    VMA(d):   Mean(volume, d) / (volume + 1e-12)       → volume MA ratio
    VSTD(d):  Std(volume, d) / (volume + 1e-12)        → volume variability
    WVMA(d):  Std(|return|*vol, d) / Mean(|return|*vol, d)  → weighted volume momentum
    VSUMP(d): sum of volume on up days                 → accumulation volume
    VSUMN(d): sum of volume on down days               → distribution volume
    VSUMD(d): VSUMP - VSUMN                            → volume direction

  PRICE NORMALIZATION (4):
    open/close, high/close, low/close, vwap/close      → price ratios

TOTAL: 9 KBAR + 145 ROLLING + 4 PRICE = 158 factors

WHAT JIP ALREADY HAS (overlap — Qlib still useful for multi-window):
  JIP: sma_50, sma_200 → Qlib adds MA at 5/10/20/30/60
  JIP: rsi_14 → Qlib adds RSV/RANK at 5/10/20/30/60 (different approach)
  JIP: volatility_20d/60d → Qlib adds STD at 5/10/30 too
  JIP: beta_nifty → Qlib adds BETA at 5/10/20/30/60

WHAT QLIB ADDS THAT JIP DOESN'T:
  • KBAR candlestick factors (9) — entirely new
  • Price-volume correlations (CORR, CORD)
  • Directional counting (CNTP, CNTN, CNTD)
  • Volume-weighted momentum (WVMA, VSUMP, VSUMN)
  • Regression decomposition (BETA, RSQR, RESI per window)
  • Quantile distances (QTLU, QTLD)
  • Time-index features (IMAX, IMIN — WHEN was the high/low)
  • Multi-window everything (5/10/20/30/60 for each metric type)
```

### When Qlib Runs

```
NIGHTLY (after JIP pipelines complete, ~19:00 IST):
  1. Export latest OHLCV from de_equity_ohlcv to Qlib format
     (CSV intermediary or custom DataLoader)
  2. Run Alpha158 feature computation for all 2,743 stocks
     (~10-15 minutes on 4 vCPU)
  3. Write 158 features per stock to atlas_qlib_features table

OPTIONAL (Phase 2+):
  4. Train ML models (LightGBM, XGBoost) on features
  5. Generate signal scores (P(outperform) per stock)
  6. Write signals to atlas_qlib_signals table
  7. Intelligence engine picks up: "Qlib model says HDFCBANK has
     82% probability of outperforming NIFTY 500 in next 20 days"
```

---

## 6. THE CENTRAL INTELLIGENCE ENGINE

### Concept

Every agent in ATLAS writes its key findings to a shared vector store.
Every agent reads from this store before acting. Intelligence compounds
because findings accumulate over days, weeks, months.

This is NOT a dashboard. It's an institutional memory that survives personnel
changes, remembers what happened last time similar conditions occurred,
and cross-references insights across different analytical domains.

### Implementation

```sql
-- On RDS (same PostgreSQL as JIP data)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE atlas_intelligence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(100) NOT NULL,          -- which agent wrote this
    agent_type VARCHAR(50) NOT NULL,         -- 'sector_analyst', 'regime', 'briefing', etc.
    entity TEXT,                             -- 'HDFCBANK', 'Banking', 'market', 'NIFTY 50'
    entity_type VARCHAR(20),                 -- 'stock', 'sector', 'index', 'mf', 'market'
    finding_type VARCHAR(50) NOT NULL,       -- 'signal', 'pattern', 'divergence', 'risk',
                                             --  'fm_input', 'correlation', 'alert'
    title TEXT NOT NULL,                     -- short summary
    content TEXT NOT NULL,                   -- full finding with evidence
    confidence NUMERIC(5,4),                 -- 0.0000 to 1.0000
    evidence JSONB DEFAULT '{}',            -- supporting data (RS values, dates, metrics)
    embedding vector(1536),                 -- for semantic similarity search
    tags TEXT[] DEFAULT '{}',               -- for filtering: {'bullish', 'breadth', 'rotation'}
    data_as_of TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,                 -- findings have shelf life
    is_validated BOOLEAN DEFAULT FALSE,     -- set to true after outcome observed
    validation_result JSONB,                -- {predicted: X, actual: Y, accuracy: Z}
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast semantic search
CREATE INDEX idx_intelligence_embedding ON atlas_intelligence
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Standard indexes
CREATE INDEX idx_intelligence_entity ON atlas_intelligence(entity);
CREATE INDEX idx_intelligence_entity_type ON atlas_intelligence(entity_type);
CREATE INDEX idx_intelligence_agent_type ON atlas_intelligence(agent_type);
CREATE INDEX idx_intelligence_finding_type ON atlas_intelligence(finding_type);
CREATE INDEX idx_intelligence_created ON atlas_intelligence(created_at DESC);
CREATE INDEX idx_intelligence_tags ON atlas_intelligence USING gin(tags);
CREATE INDEX idx_intelligence_validated ON atlas_intelligence(is_validated);
```

### How Agents Use It

```python
# Writing a finding
async def store_finding(
    agent_id: str,
    agent_type: str,
    entity: str,
    entity_type: str,
    finding_type: str,
    title: str,
    content: str,
    confidence: Decimal,
    evidence: dict = {},
    tags: list[str] = [],
    expires_hours: int = 168,  # 1 week default shelf life
):
    embedding = await embed(f"{title} | {content} | Entity: {entity}")
    # ... INSERT into atlas_intelligence

# Querying before acting
async def get_relevant_intelligence(
    query: str,
    entity: str = None,
    entity_type: str = None,
    finding_type: str = None,
    min_confidence: Decimal = Decimal("0.5"),
    max_age_hours: int = 168,
    top_k: int = 10,
) -> list[Finding]:
    query_embedding = await embed(query)
    # ... SELECT with vector similarity + metadata filters

# Example: Sector analyst before running
context = await get_relevant_intelligence(
    query="What do we know about Banking sector rotation and breadth?",
    entity="Banking",
    entity_type="sector",
    top_k=5
)
# Returns: previous rotation findings, FM voice notes about Banking,
# simulation results for Banking-heavy portfolios, TV TA signals for Bank Nifty
```

### Embedding Strategy

```
Model: text-embedding-3-small (OpenAI) — 1536 dimensions, $0.02/1M tokens
  OR: nomic-embed-text (self-hosted, free) if cost is a concern

What gets embedded: "{title} | {content} | Entity: {entity} | Tags: {tags}"

Embedding happens at write time (amortized cost), not query time.

Cost estimate: ~500 findings/day × ~200 tokens each = 100K tokens/day = $0.002/day
  (negligible)
```

### Fund Manager Input Ingestion

```
FM provides: voice note, WhatsApp message, typed commentary

Pipeline:
  1. Voice → Whisper transcription (local, free)
  2. Text → Small model extraction (haiku):
     "Extract: entity (stock/sector/market), sentiment (bullish/bearish/neutral),
      key claim, time horizon"
  3. Extracted finding → stored in atlas_intelligence with:
     agent_type = 'fm_input'
     finding_type = 'qualitative'
     confidence = 0.7 (FM views weighted but not absolute)
  4. Next time any agent queries about that entity, FM's input
     appears in context alongside quantitative findings
```

---

## 7. THE AGENT SYSTEM

### Architecture

Agents are capabilities with memory, not microservices. Each agent:
- Has its own AGENT.md (brain: system prompt, domain knowledge, rules)
- Has its own config.yaml (model, schedule, dependencies, I/O contracts)
- Writes findings to the central intelligence engine
- Reads from the intelligence engine before acting
- Has Darwinian evolution (predictions scored, weights adjusted, prompts mutated)
- Uses the appropriate model (haiku for simple, sonnet for reasoning, opus for synthesis)

### Agent Orchestration: LangGraph

All agents are orchestrated via LangGraph (90K GitHub stars, production-proven at Uber/LinkedIn).
The orchestration graph defines execution order, parallelism, and failure handling.

### The Agents (9 capabilities)

```
AGENT 1: rs-analyzer
  Model: haiku (computation, no reasoning)
  Schedule: daily after JIP pipelines
  Input: JIP /internal/equity/universe, /internal/mf/universe, /internal/etf/universe
  Computes: rs_momentum and quadrant for every entity
  Writes to intelligence: "HDFCBANK RS turned positive this week" (when rs_composite crosses 0)
  Writes to intelligence: "Banking sector entered LEADING quadrant" (rotation detection)

AGENT 2: sector-analyst
  Model: sonnet (needs reasoning for divergence detection)
  Schedule: daily after rs-analyzer
  Input: StockData[] from JIP, RS from rs-analyzer
  Computes: 22 sector rollup metrics (see §4.3)
  Detects: sector rotation signals, breadth-RS divergences
  Reads intelligence: "What patterns have I seen before in Banking?"
  Writes to intelligence: "Pharma RS positive but breadth declining = divergence"
  Forked from: FinRobot sector analyst template (prompts adapted for India)

AGENT 3: regime-analyst
  Model: sonnet
  Schedule: daily after JIP pipelines
  Input: de_market_regime, de_breadth_daily, de_institutional_flows
  Computes: enhanced regime classification ("SIDEWAYS with bearish lean")
  Detects: regime transition probability, historical regime duration analysis
  Reads intelligence: "Last time breadth was this low, what happened?"
  Writes to intelligence: "Regime transition probability: 65% chance of BEAR within 2 weeks"
  Uses: hmmlearn (HMM regime detection, 4-state model on NIFTY returns + volatility)

AGENT 4: goldilocks-analyst
  Model: haiku (reading structured data)
  Schedule: daily, after new Goldilocks data arrives
  Input: de_goldilocks_market_view, de_goldilocks_sector_view,
         de_goldilocks_stock_ideas, de_oscillator_*, de_fib_levels, de_index_pivots
  Cross-validates: Goldilocks stock ideas against RS data
  Writes to intelligence: "Goldilocks BUY HDFCBANK aligns with RS LEADING"
  Writes to intelligence: "Goldilocks BUY TATASTEEL conflicts with RS LAGGING — DIVERGENT SIGNAL"

AGENT 5: tv-bridge
  Model: haiku (fetch + cache)
  Schedule: daily (batch for top 100 by RS) + on-demand
  Input: top instruments by RS from rs-analyzer
  Fetches: TradingView TA summary (1D/1W/1M), Piotroski F-Score, Altman Z-Score
  Uses: TradingView MCP servers (tradingview-mcp-server, tradingview-screener)
  Caches: atlas_tv_cache table (15-min TTL)
  Writes to intelligence: "HDFCBANK TV Daily STRONG BUY, Weekly BUY, Monthly NEUTRAL"
  Graceful degradation: if TV MCP down, component scores neutral, system continues

AGENT 6: briefing-writer
  Model: opus (complex narrative synthesis)
  Schedule: daily at 00:30 IST (after all data crons complete)
  Input: ALL intelligence findings, macro data, regime, Goldilocks, TV
  Architecture: FORKED from TradingAgents multi-agent debate protocol:
    Sub-agent A: Macro Analyst (reads FRED, regime, global RS, flows)
    Sub-agent B: Sentiment Analyst (reads Goldilocks views, MF flows)
    Sub-agent C: Technical Analyst (reads RS, breadth, technicals)
    Sub-agent D: Risk Analyst (reads everything, looks for what could go WRONG)
    → Bull/Bear debate with judge resolution
    → Editor synthesizes into briefing
  Output: atlas_briefings table row
  Writes to intelligence: briefing stored for reference
  Uses: Anthropic Claude API (opus for final narrative, sonnet for sub-agents)

AGENT 7: simulation-runner
  Model: haiku (pure computation)
  Schedule: on-demand (user request) + weekly auto-loop (saved configs)
  Input: signal series (breadth, RS, PE, regime, McClellan) + instrument NAV/price
  Engine: VectorBT (1M backtests in 20 seconds)
  Tax: Indian FIFO engine (in-house, pre/post July 2024)
  Metrics: QuantStats (60+ metrics, HTML tearsheets)
  Optimization: Optuna (TPE sampler for parameter search)
  Writes to intelligence: "Breadth timing on PPFAS underperformed plain SIP this quarter"
  (see §8 for full simulation engine spec)

AGENT 8: portfolio-analyzer
  Model: sonnet (needs reasoning for analysis)
  Schedule: on-demand (CAMS upload) + daily (existing portfolios)
  Input: CAMS report (via casparser) OR manual portfolio entry
  Computes: RS overlay on every holding, sector concentration, overlap between funds,
            weighted portfolio RS, rebalancing signals, tax harvesting opportunities
  Attribution: Brinson model (allocation + selection + interaction)
  Optimization: Riskfolio-Lib (SEBI constraints)
  Reads intelligence: "What do we know about this client's sectors?"
  Writes to intelligence: "Client X has 40% in Banking — concentration risk"
  (see §9 for full portfolio engine spec)

AGENT 9: discovery-engine
  Model: sonnet (needs reasoning for recommendations)
  Schedule: on-demand
  Input: user filters + JIP data + TV screener data
  Computes: multi-factor screening (RS + technicals + fundamentals + institutional)
  For stocks: IBD-style RS ranking + breadth confirmation + TV TA
  For MFs: category analysis + rolling returns + holdings quality + flows
  For ETFs: global rotation map + RS vs SPY + TV TA
  Reads intelligence: "What opportunities have been flagged recently?"
  Writes to intelligence: "3 mid-cap funds with rising RS and positive flows surfaced"
```

### Darwinian Evolution (per agent)

```
Every agent that makes predictions has:

1. ACCURACY TRACKING
   Stored in: atlas_agent_scores table
   Schema:
     agent_id, prediction_date, entity, prediction (text),
     evaluation_date, actual_outcome (text), accuracy_score (0-1),
     rolling_sharpe (60-prediction window)

2. DARWINIAN WEIGHTS
   Stored in: atlas_agent_weights table
   Schema: agent_id, weight (Decimal, range 0.3-2.5), updated_at

   Daily adjustment:
     Top quartile accuracy: weight × 1.05 (cap 2.5)
     Bottom quartile: weight × 0.95 (floor 0.3)

3. MUTATION (5-day cycle, from ATLAS-GIC pattern)
   When an agent's weight drops below 0.5:
     a. Analyze last 20 predictions for error patterns
     b. Generate ONE targeted modification to AGENT.md
     c. Create git branch: evolution/{agent_id}/{version}
     d. Run modified agent in shadow mode for 5 trading days
     e. Compare Sharpe: better → merge, worse → revert
   Expected survival rate: ~30% (based on ATLAS-GIC's 54 attempts, 16 survived)

4. SPAWNING
   When accuracy-tracker detects recurring knowledge gap
   (3+ errors in same sector/entity within 5 days):
     → Auto-spawn specialist agent (e.g., pharma-specialist)
     → Starts at weight 1.0
     → Must earn weight through accuracy or dies (weight floor 20+ days → remove)

WHICH AGENTS ARE SCORED:
  rs-analyzer:       rotation signal accuracy (5-day forward sector returns)
  sector-analyst:    divergence detection accuracy (5-day forward)
  regime-analyst:    regime transition calls (20-day forward)
  goldilocks-analyst: Goldilocks-RS alignment prediction accuracy
  briefing-writer:   qualitative (user engagement tracking, not hard scoring)
  simulation-runner: NOT scored (deterministic computation)
  portfolio-analyzer: NOT scored (analysis, not prediction)
  discovery-engine:  opportunity conversion rate (5-day forward)
  tv-bridge:         NOT scored (data fetcher)
```

### Agent Memory (from TradingAgents, upgraded)

```
TradingAgents uses BM25 lexical similarity for situation recall.
We upgrade to pgvector semantic similarity.

Each agent writes to atlas_intelligence (shared).
Each agent also has private memory for self-corrections:

TABLE: atlas_agent_memory (per agent)
  agent_id, memory_type ('correction', 'learning', 'pattern'),
  content, created_at

When an agent is corrected (by risk guardian, by FM, by accuracy tracking),
the correction is stored in agent memory. Next time the agent runs,
it reads its corrections: "Last time I said Pharma was rotating, I was wrong
because breadth was declining. Check breadth before calling rotation."
```

---

## 8. THE SIMULATION ENGINE

### Architecture

NOT hand-coded. Uses battle-tested libraries for every component.

```
┌────────────────────────────────────────────────────┐
│              SIMULATION ENGINE                      │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ INPUT: User Configuration                     │  │
│  │                                                │  │
│  │ Instruments: any stock, MF, ETF, or BASKET    │  │
│  │   (basket = weighted mix of any instruments)   │  │
│  │                                                │  │
│  │ Signal: breadth | RS | PE | regime | McClellan │  │
│  │         | sector_RS | combined (AND/OR)        │  │
│  │                                                │  │
│  │ Parameters:                                    │  │
│  │   sip_amount         ₹10,000 default           │  │
│  │   lumpsum_amount     ₹50,000 default           │  │
│  │   buy_level          signal threshold for entry │  │
│  │   sell_level         signal threshold for exit  │  │
│  │   reentry_level      signal threshold for re-entry│
│  │   sell_pct           % to sell at sell_level    │  │
│  │   redeploy_pct       % of liquid to redeploy   │  │
│  │   cooldown_days      between lumpsums           │  │
│  │                                                │  │
│  │ Date range: start, end                         │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ EXECUTION: VectorBT                           │  │
│  │                                                │  │
│  │ Vectorized backtesting engine                  │  │
│  │ 1M parameter combinations in 20 seconds        │  │
│  │                                                │  │
│  │ For single backtest: ~100ms                    │  │
│  │ For 10K parameter sweep: ~2 seconds            │  │
│  │ For 1M Monte Carlo: ~20 seconds                │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ TAX ENGINE: Indian FIFO (in-house)            │  │
│  │                                                │  │
│  │ Pre 23-Jul-2024:                               │  │
│  │   STCG: 15% | LTCG: 10% | Exemption: ₹1L    │  │
│  │   LTCG threshold: >12 months holding           │  │
│  │                                                │  │
│  │ Post 23-Jul-2024:                              │  │
│  │   STCG: 20% | LTCG: 12.5% | Exemption: ₹1.25L│  │
│  │   LTCG threshold: >12 months holding           │  │
│  │                                                │  │
│  │ 4% Health & Education Cess on all tax          │  │
│  │ FIFO lot tracking: sell oldest units first     │  │
│  │ Tax deducted from proceeds BEFORE redeployment │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ ANALYTICS: QuantStats + empyrical             │  │
│  │                                                │  │
│  │ QuantStats tear sheet (HTML):                  │  │
│  │   60+ metrics, monthly heatmap, rolling Sharpe,│  │
│  │   drawdown chart, return distribution          │  │
│  │                                                │  │
│  │ empyrical individual metrics:                  │  │
│  │   XIRR, CAGR, Sharpe, Sortino, Calmar,        │  │
│  │   max drawdown, information ratio, alpha, beta │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ OPTIMIZATION: Optuna                          │  │
│  │                                                │  │
│  │ When user asks: "What's the optimal buy level?"│  │
│  │ Optuna's TPE sampler searches parameter space  │  │
│  │ Prunes unpromising trials early                │  │
│  │ Integrates with VectorBT for fast evaluation   │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ FACTOR VALIDATION: alphalens-reloaded         │  │
│  │                                                │  │
│  │ "Does RS actually predict returns?"            │  │
│  │ Feed RS percentile as factor + forward returns │  │
│  │ Output: IC by decile, turnover, decay analysis │  │
│  │ Quantitative proof that RS works as a signal   │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ OUTPUT                                        │  │
│  │                                                │  │
│  │ summary: total_invested, final_value, xirr,   │  │
│  │   cagr, vs_plain_sip, vs_benchmark, alpha,     │  │
│  │   max_drawdown, sharpe, sortino                │  │
│  │                                                │  │
│  │ daily_values: [{date, nav, units, fv, liquid,  │  │
│  │   total}]                                      │  │
│  │                                                │  │
│  │ transactions: [{date, action, amount, nav,     │  │
│  │   units, tax_detail}]                          │  │
│  │                                                │  │
│  │ tax_summary: {stcg, ltcg, total_tax,           │  │
│  │   post_tax_xirr, unrealized}                   │  │
│  │                                                │  │
│  │ tear_sheet: HTML file from QuantStats           │  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
```

### Signal Sources (7 + combined)

```
1. BREADTH: de_breadth_daily.pct_above_200dma (2007→now)
   Range: 0-100. Buy < 50 = market oversold. Sell > 75 = overbought.

2. McCLELLAN: de_breadth_daily.mcclellan_oscillator (2007→now)
   Range: -200 to +200. Buy < -100 = deeply oversold. Sell > +100.

3. RS: de_rs_scores.rs_composite (2016→now)
   For any specific instrument. Buy < -5 = underperforming. Sell > +15.

4. PE: de_index_prices.pe_ratio (2016→now, any index)
   Mean-reversion. Buy < 18 = cheap. Sell > 24 = expensive.

5. REGIME: de_market_regime.regime (2007→now)
   Mapped: BULL=100, RECOVERY=75, SIDEWAYS=50, BEAR=0.
   Buy < 40 = entering bear. Sell > 80 = peak bull.

6. SECTOR RS: de_rs_scores WHERE entity_type='sector' (2016→now)
   For sector rotation timing.

7. McCLELLAN SUMMATION: de_breadth_daily.mcclellan_summation (2007→now)
   Longer-term breadth momentum.

8. COMBINED: any two of above with AND/OR logic
   Example: Buy when breadth < 50 AND regime = BEAR (double confirmation)
```

### Auto-Loop Mode

```
Fund manager saves a simulation configuration:
  "Run breadth timing on my 3 core funds every Sunday night"

System:
  1. Stores config in atlas_simulations table
  2. Cron job fires every Sunday at 23:00 IST
  3. Re-runs simulation with latest data
  4. Compares this week's results vs last week
  5. Generates delta report:
     "Strategy XIRR: 16.2% (was 16.8% last week)
      Reason: breadth dropped to 16.8%, buy signal active
      Last lumpsum: 45 days ago, cooldown cleared
      Action needed: consider tactical lumpsum if breadth stays low"
  6. If performance deviates significantly:
     → Optuna auto-runs parameter optimization
     → Proposes adjusted parameters for FM approval
  7. Writes finding to intelligence engine:
     "Breadth timing on PPFAS underperformed this quarter"
```

---

## 9. THE PORTFOLIO ENGINE

### CAMS Import

```
Library: casparser (193 GitHub stars, actively maintained)
  Parses: CAMS, KFintech, Karvy CAS PDF statements
  Extracts: investor details, folios, scheme holdings, transactions, valuations
  Supports: Schedule 112A tax format

Pipeline:
  1. FM uploads CAS PDF via ATLAS UI
  2. casparser extracts holdings: {scheme_name, folio, units, nav, value}
  3. ATLAS maps scheme to JIP: scheme_name → de_mf_master.fund_name → mstar_id
     (fuzzy matching with manual override for ambiguous matches)
  4. Mapped portfolio stored in atlas_portfolios table
  5. Instant analysis runs (see below)
```

### Portfolio Analysis

```
Once holdings are mapped to JIP instruments:

PER HOLDING:
  - Current NAV + returns (from de_mf_nav_daily)
  - RS composite + momentum + quadrant (from de_rs_scores)
  - Derived metrics: Sharpe, Sortino, Alpha (from de_mf_derived_daily)
  - Weighted technicals: RSI, breadth, MACD (from de_mf_weighted_technicals)
  - Category flow status (from de_mf_category_flows)

PORTFOLIO-LEVEL:
  - Weighted portfolio RS (holdings × RS composite)
  - Sector concentration (from de_mf_sector_exposure, aggregated)
  - Holdings overlap between funds
  - Quadrant distribution: how many holdings in LEADING vs LAGGING
  - Weighted average Sharpe, Sortino, Beta
  - Total AUM exposure by sector

ONGOING MONITORING (daily):
  - Portfolio RS trend (declining → alert)
  - Holding enters LAGGING for 4+ weeks → rebalancing signal
  - Sector concentration exceeds threshold → alert
  - Category flows turn negative → alert
  - Tax harvesting: identify holdings with unrealized losses that could offset gains

ATTRIBUTION (Brinson model):
  Allocation effect: did FM overweight the right categories?
  Selection effect: within each category, did FM pick the right funds?
  Interaction effect: (usually shown combined with allocation)
```

### Portfolio Optimization

```
Library: Riskfolio-Lib (4K GitHub stars)
  24 risk measures, 8 optimization models
  SEBI-compatible constraints:
    - Max 10% per stock (for PMS)
    - Sector caps
    - Cardinality constraints (max N positions)
    - Integer constraints

Use case: "I have ₹1Cr to allocate across 6-8 MF schemes.
What's the optimal allocation given my risk tolerance?"

Input: list of candidate funds + risk profile
Output: optimal weights per fund (mean-variance, CVaR, risk parity, HRP)
```

---

## 10. TRADINGVIEW INTEGRATION

### Setup

```
TradingView MCP Servers (Node.js sidecar on ATLAS EC2):
  tradingview-mcp-server (v0.6.1): 12 tools — screening, TA summary, ranking
  tradingview-screener (v2.3.2): 13,000+ screening fields, built-in MCP

Install:
  npm install -g tradingview-mcp-server tradingview-screener
```

### Integration Points

```
ATLAS → TradingView (push):
  • Model portfolio holdings → TV watchlist (auto-sync via TV API)
  • Simulation buy/sell signals → chart annotations
  • Alert rules created in ATLAS → matching TV alert auto-created
  • Sector rotation signals → TV sector watchlist updated

TradingView → ATLAS (pull + webhook):
  • TV webhook alerts → POST /api/webhooks/tradingview → atlas_alerts table
  • TV TA summary (1D/1W/1M) → conviction pillar 3
  • TV Piotroski F-Score / Altman Z-Score → fundamental quality badge
  • TV screener (13K fields) → enrichment for discovery engine

CHARTS (frontend):
  • TradingView Lightweight Charts v5 (already in global-pulse)
  • Multi-pane: candlestick + RSI + MACD + volume (synchronized)
  • Simulation results overlaid: buy ▲ / sell ▼ markers on chart
  • Signal line as secondary pane
```

### TV Cache

```sql
CREATE TABLE atlas_tv_cache (
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(20) DEFAULT 'NSE',
    data_type VARCHAR(30) NOT NULL,   -- 'ta_summary', 'fundamentals', 'screener'
    interval VARCHAR(10),              -- '1D', '1W', '1M' for TA
    data JSONB NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (symbol, data_type, COALESCE(interval, 'none'))
);
```

---

## 11. API LAYER — EVERY ENDPOINT

### ATLAS API (FastAPI, port 8010)

```
# ─── Stock Pulse ─────────────────────────────────────────
GET  /api/stocks/universe
     ?benchmark=NIFTY 500 (default)
     ?sector=Banking (optional)
     ?universe=NIFTY50|NIFTY200|NIFTY500|ALL (optional)
     ?rs_min=0 (optional)
     Response: hierarchical — sectors containing stocks, each with full data

GET  /api/stocks/sectors
     Response: 31 sectors with 22 metrics each (see §4.3)

GET  /api/stocks/breadth
     Response: market-wide + per-sector breadth bars

GET  /api/stocks/movers
     Response: top 15 RS momentum gainers + top 15 losers

GET  /api/stocks/{symbol}
     Response: complete stock deep-dive data (all 4 conviction pillars)

GET  /api/stocks/{symbol}/rs-history?months=12
GET  /api/stocks/{symbol}/mf-holders
GET  /api/stocks/{symbol}/chart-data?from=...&to=...
     Response: OHLCV + technicals for TradingView chart rendering

GET  /api/stocks/{symbol}/tv-ta
     Response: cached TV TA summary (1D/1W/1M)

GET  /api/stocks/{symbol}/peers
     Response: same-sector stocks compared on key metrics

# ─── MF Pulse ────────────────────────────────────────────
GET  /api/mf/universe
     ?benchmark=NIFTY 500
     ?category=Large Cap
     ?broad_category=Equity
     Response: hierarchical — categories containing funds

GET  /api/mf/categories
     Response: category rollup (see §4.7)

GET  /api/mf/flows
     Response: category flow data (net, SIP, AUM)

GET  /api/mf/{mstar_id}
     Response: complete fund deep-dive (all pillars + weighted technicals)

GET  /api/mf/{mstar_id}/holdings
     Response: holdings with each stock's RS + technicals (drills to stock level)

GET  /api/mf/{mstar_id}/sectors
     Response: sector exposure with sector RS overlaid

GET  /api/mf/{mstar_id}/rs-history
GET  /api/mf/{mstar_id}/weighted-technicals
GET  /api/mf/{mstar_id}/nav-history?from=...&to=...
GET  /api/mf/overlap?funds=A,B
GET  /api/mf/holding-stock/{symbol}
     Response: which funds hold this stock, sorted by weight

# ─── ETF Pulse ───────────────────────────────────────────
GET  /api/etf/universe?country=US&asset_class=Equity
GET  /api/etf/{ticker}
GET  /api/etf/{ticker}/chart-data
GET  /api/etf/{ticker}/rs-history

# ─── Global Intelligence ─────────────────────────────────
GET  /api/global/briefing
     Response: latest LLM briefing from atlas_briefings

GET  /api/global/ratios
     Response: key macro ratios with sparklines

GET  /api/global/rs-heatmap
     Response: all global instruments with RS, momentum, price

GET  /api/global/regime
     Response: current regime + breadth summary

GET  /api/global/patterns
     Response: inter-market patterns from intelligence engine

# ─── Simulation Engine ───────────────────────────────────
POST /api/simulate/run
     Body: {signal, instrument, rules, date_range}
     Response: full simulation results

GET  /api/simulate/presets
POST /api/simulate/save
GET  /api/simulate/saved
GET  /api/simulate/{id}

POST /api/simulate/optimize
     Body: {signal, instrument, param_ranges, date_range}
     Response: optimal parameters from Optuna

# ─── Portfolio ───────────────────────────────────────────
POST /api/portfolio/import-cams
     Body: multipart file upload (CAS PDF)
     Response: parsed + mapped portfolio

GET  /api/portfolio/{id}
GET  /api/portfolio/{id}/analysis
GET  /api/portfolio/{id}/attribution
GET  /api/portfolio/{id}/optimize
POST /api/portfolio/create
PUT  /api/portfolio/{id}

# ─── Discovery / Screening ──────────────────────────────
GET  /api/discover/stocks?filters=...
GET  /api/discover/mf?filters=...
GET  /api/discover/etf?filters=...

# ─── TradingView Bridge ──────────────────────────────────
POST /api/webhooks/tradingview
GET  /api/tv/ta/{symbol}
GET  /api/tv/screen?filters=...
GET  /api/tv/fundamentals/{symbol}

# ─── Alerts ──────────────────────────────────────────────
GET  /api/alerts?source=...&unread=true
POST /api/alerts/{id}/read
GET  /api/alerts/rules
POST /api/alerts/rules

# ─── Watchlists ──────────────────────────────────────────
GET  /api/watchlists
POST /api/watchlists
PUT  /api/watchlists/{id}
DELETE /api/watchlists/{id}
POST /api/watchlists/{id}/sync-tv

# ─── Intelligence Engine ─────────────────────────────────
GET  /api/intelligence/query?q=...&entity=...&type=...
GET  /api/intelligence/recent?entity=...&hours=24
GET  /api/intelligence/stats
     Response: total findings, growth rate, agent weights

# ─── System ──────────────────────────────────────────────
GET  /api/status
GET  /api/health
```

---

## 12. FRONTEND — THREE EXPERIENCE SHELLS

### Shared Foundation

All three shells share:
- Same ATLAS API backend
- Same intelligence engine
- Same design system (fonts, colors, components)
- Same flow: Global → Country → Sector → Instrument
- Same deep-dive page structure (4 conviction pillars)

Technology: Next.js 16 + React 19 + TypeScript + Tailwind CSS 4 + shadcn/ui
Added to existing fie2 repo (github.com/nimishshah1989/fie2) as /atlas/* routes.

Charts: TradingView Lightweight Charts v5 (candlestick, multi-pane)
        + Recharts (bubble charts, breadth bars, bar charts)
        + SVG (sparklines, RS bars)

### Design System

```css
/* Fonts */
--font-serif: 'Instrument Serif', Georgia, serif;     /* Page headlines */
--font-sans: 'DM Sans', -apple-system, sans-serif;    /* Body text */
--font-mono: 'IBM Plex Mono', monospace;               /* Data values */

/* Colors */
--bg: #f9f9f7;           /* Page background (warm off-white) */
--white: #ffffff;          /* Cards, panels */
--border: #e4e4e8;         /* Card borders */
--border-light: #f0f0f2;  /* Table row separators */
--ink: #1a1a2e;           /* Primary text */
--t2: #6b6b80;            /* Secondary text */
--t3: #9a9aad;            /* Muted text */
--gold: #8a7235;          /* Section labels */
--green: #1a9a6c;         /* Positive */
--red: #d44040;           /* Negative */
--amber: #c08a20;         /* Caution */
--teal: #0d8a7a;          /* Primary accent */

/* Rules: No box-shadows. No gradients. No rounded-full containers.
   No emoji in UI. No Inter/Roboto. No colored stat cards. No composite scores. */
```

### Shell 1: ATLAS Pro (PMS Fund Managers)

```
URL: atlas.jslwealth.in/pro/*
Target: PMS managers, CIOs, research analysts
Density: HIGH — 50+ data points visible simultaneously
Layout: Desktop-first, multi-panel

Pages:
  /pro                    → Dashboard (exception-driven, what needs attention)
  /pro/global             → Global Intelligence (briefing, ratios, regime, heatmap)
  /pro/stocks             → Stock Pulse (bubble + drill-down table + deep-dive)
  /pro/mf                 → MF Pulse (category → fund → holdings drill-down)
  /pro/etf                → ETF Pulse (global rotation map)
  /pro/simulate           → Simulation Lab (builder + results + auto-loop)
  /pro/portfolio           → Portfolio Dashboard (CAMS import + analysis + attribution)
  /pro/discover           → Stock/MF/ETF Screener (multi-factor)
  /pro/alerts             → Unified Alert Center (TV + RS + breadth + regime)
  /pro/watchlists         → Watchlist Manager (TV sync)
  /pro/intelligence       → Intelligence Engine Explorer (what has the system learned)

Stock Deep-Dive (when clicking any stock):
  EVERYTHING on one page:
  • RS chart (12mo) + quadrant history
  • TradingView candlestick chart (multi-pane: price + RSI + MACD + volume)
  • 4 conviction pillars (RS, technical, external, institutional) — all explained
  • Fundamental snapshot (from TV screener: PE, PB, ROE, revenue growth)
  • Peer comparison table (same-sector stocks)
  • MF holders list (which funds hold this)
  • Goldilocks view (if stock appears in Stock Bullet/Big Catch)
  • Intelligence findings (what the system has learned about this stock)
  • Pattern matches (historical: "last time RS > 4 AND ADX > 30, stock rose 68%")
  • Quick simulation link
  • Portfolio context (if held in any portfolio)

MF Deep-Dive (when clicking any fund):
  • NAV chart + RS chart (NAV-RS vs derived-RS + manager alpha)
  • Risk metrics (Sharpe, Sortino, max DD) — all explained in plain English
  • Weighted technicals ("72% of holdings above 200DMA")
  • Holdings table → drills to stock level (each stock has its own RS + technicals)
  • Sector exposure bars with sector RS overlaid
  • Category flow status
  • Peer comparison within category
  • Holdings overlap checker
  • Simulation link
```

### Shell 2: ATLAS Advisor (RIAs)

```
URL: atlas.jslwealth.in/advisor/*
Target: Registered Investment Advisors managing multiple clients
Density: MEDIUM — dashboard + client management
Layout: Dashboard with client portal

Pages:
  /advisor                → Advisor Dashboard (client overview, pending actions)
  /advisor/clients        → Client List (AUM, risk profile, last review date)
  /advisor/clients/{id}   → Client Detail (portfolio, goals, review history)
  /advisor/discover       → Fund Discovery (category, filters, comparison)
  /advisor/model          → Model Portfolios (create, manage, push to clients)
  /advisor/simulate       → Simplified Simulation (preset strategies)
  /advisor/reports        → Report Generator (quarterly reviews, auto-commentary)
  /advisor/market         → Market View (simplified briefing, sector overview)

Fund Discovery Workflow:
  1. Select category (Large Cap, Flexi Cap, etc.)
  2. Filter: AUM > ₹5000Cr, track record > 5Y
  3. Compare: rolling returns, downside capture, Sharpe, holdings quality
  4. Overlap check against client's existing funds
  5. Add to model portfolio

Client Portfolio Import:
  Upload CAMS CAS → auto-parse → map to JIP → gap analysis
  "Client has 40% in Banking through 3 funds — concentration risk"
  "Model portfolio suggests 15% Banking — rebalancing needed"
```

### Shell 3: ATLAS Retail (MF Investors)

```
URL: atlas.jslwealth.in/ (default experience)
Target: Direct plan MF investors, retail
Density: LOW — 5-7 data points, mobile-first
Layout: Mobile-first, clean, Groww-level simplicity

Pages:
  /                       → Home (market summary, portfolio value, quick actions)
  /discover               → Fund Discovery (simplified, curated lists)
  /discover/{mstar_id}    → Fund Detail (simplified deep-dive)
  /portfolio              → My Portfolio (CAMS import, holdings, returns)
  /portfolio/goals        → Goal Planner (retirement, education, house)
  /simulate               → SIP Calculator (simplified simulation)
  /alerts                 → My Alerts (fund RS changes, rebalancing reminders)
  /learn                  → How It Works (RS methodology explained simply)

Simplified presentation:
  • No raw RS numbers — "This fund is OUTPERFORMING its category"
  • No technical jargon — "8 of 10 health checks pass"
  • No composite scores — traffic light (green/amber/red) for overall health
  • Goal-based framing — "You need ₹2,00,000/month SIP to reach ₹5Cr by 2040"
```

---

## 13. THE AUTONOMOUS BUILD SYSTEM

### How Claude Code Runs 24/7

```
ON ATLAS EC2:

1. Install Claude Code CLI:
   npm install -g @anthropic-ai/claude-code

2. Configure:
   export ANTHROPIC_API_KEY=sk-ant-...
   claude config set --global permissions '{"allow": ["*"]}'

3. Clone repos:
   git clone https://github.com/nimishshah1989/fie2.git ~/atlas-frontend
   mkdir ~/atlas-backend && cd ~/atlas-backend && git init

4. Place this document as CLAUDE.md in ~/atlas-backend/

5. Launch autonomous build (in tmux session):
   tmux new -s atlas-build
   cd ~/atlas-backend
   claude --dangerously-skip-permissions \
     --model claude-opus-4-6 \
     "You are building ATLAS autonomously. Read CLAUDE.md for the complete spec.
      Read BUILD_STATUS.md for current progress. Build the next pending chunk.
      Run tests. Commit. Update BUILD_STATUS.md. Move to next chunk.
      Do not stop until all phases are complete.
      If a chunk fails after 3 attempts, log the error, skip it, and continue."

6. Build progress dashboard (separate process):
   Reads BUILD_STATUS.md + git log + test results
   Serves HTML on port 3001
   Auto-refreshes every 30 seconds
```

### BUILD_STATUS.md Format

```markdown
# ATLAS Build Status
Updated: 2026-04-12T14:30:00Z

## Current Agent
Chunk: 1.4 — JIP /internal/market/* endpoints
Session: #47
Started: 2026-04-12T14:18:00Z
Status: IN_PROGRESS

## Phase Progress
- [x] Phase 0: Contracts + Infrastructure (6/6 chunks)
- [ ] Phase 1: Data Layer (3/6 chunks done)
  - [x] 1.1 JIP /internal/equity/universe
  - [x] 1.2 JIP /internal/sectors/universe
  - [x] 1.3 JIP /internal/mf/universe
  - [ ] 1.4 JIP /internal/market/* ← CURRENT
  - [ ] 1.5 JIP /internal/etf/* + global/*
  - [ ] 1.6 ATLAS JIP client
- [ ] Phase 2: Intelligence Layer (0/7)
- [ ] Phase 3: Agent Layer (0/7)
...

## Integration Tests
- test_data_layer: 12/15 passing (3 pending: market endpoints)
- test_intelligence: not started
...

## Errors
- None

## Last 10 Commits
...
```

---

## 14. DEVELOPMENT PHASES & CHUNKS

### Phase 0: Contracts + Infrastructure (Day 1)

```
Chunk 0.1: Pydantic schemas for ALL API contracts
  Files: contracts/equity.py, contracts/mf.py, contracts/etf.py,
         contracts/global.py, contracts/simulation.py, contracts/portfolio.py,
         contracts/intelligence.py, contracts/alerts.py
  Every request/response model defined with exact field names, types, descriptions.

Chunk 0.2: Database migrations for atlas_* tables
  Tables: atlas_briefings, atlas_simulations, atlas_watchlists, atlas_alerts,
          atlas_intelligence, atlas_tv_cache, atlas_agent_scores, atlas_agent_weights,
          atlas_agent_memory, atlas_portfolios, atlas_portfolio_holdings,
          atlas_qlib_features, atlas_qlib_signals
  pgvector extension enabled on RDS.

Chunk 0.3: ATLAS FastAPI scaffold
  Files: backend/main.py, backend/config.py, backend/dependencies.py,
         backend/db/session.py, backend/db/base.py
  Health endpoint working: GET /api/health → 200

Chunk 0.4: JIP client (HTTP client to /internal/ API)
  Files: backend/clients/jip_client.py
  Handles: schema translation (JIP column names → ATLAS domain types),
           connection pooling, error handling, caching headers

Chunk 0.5: TradingView MCP sidecar setup
  Files: tv-bridge/package.json, tv-bridge/mcp-config.json, tv-bridge/setup.sh
  Test: tv_client.get_ta_summary("NSE:HDFCBANK") returns data

Chunk 0.6: Build progress dashboard
  Simple Next.js or plain HTML page on port 3001
  Reads BUILD_STATUS.md + git log
  Auto-refreshes
```

### Phase 1: JIP Internal API (Days 2-3)

```
Chunk 1.1: /internal/equity/universe endpoint (on JIP Data Core)
Chunk 1.2: /internal/sectors/universe endpoint
Chunk 1.3: /internal/mf/universe + /internal/mf/{id}/holdings endpoints
Chunk 1.4: /internal/market/breadth + /internal/market/regime endpoints
Chunk 1.5: /internal/etf/*, /internal/global/*, /internal/macro/* endpoints
Chunk 1.6: /internal/indices/*, /internal/goldilocks/*, /internal/status
Integration test: ATLAS JIP client fetches full equity universe successfully
```

### Phase 2: Intelligence Layer (Days 3-5)

```
Chunk 2.1: RS momentum + quadrant computation engine
Chunk 2.2: Sector rollup engine (22 metrics per sector)
Chunk 2.3: MF weighted technicals pipeline (new JIP table + computation)
Chunk 2.4: Intelligence engine (pgvector table + store/query functions)
Chunk 2.5: TV bridge client (MCP calls, caching, graceful degradation)
Chunk 2.6: Conviction assessment engine (4 pillars, plain English output)
Chunk 2.7: Qlib Alpha158 pipeline (CSV export → Qlib → features → PostgreSQL)
Integration test: Full intelligence pipeline runs end-to-end
```

### Phase 3: Agent Layer (Days 5-8)

```
Chunk 3.1: LangGraph orchestration scaffold + agent base class
Chunk 3.2: Fork ai-hedge-fund investor agents (Jhunjhunwala + 3 others)
           Swap data source to JIP client. Add Indian market context.
Chunk 3.3: Port TradingAgents debate protocol (bull/bear + judge)
Chunk 3.4: Port TradingAgents memory → pgvector intelligence engine
Chunk 3.5: Briefing generator (debate → narrative, Claude API integration)
Chunk 3.6: Darwinian evolution engine (scoring, weights, mutation, git branches)
Chunk 3.7: Risk guardian agent (adversarial review of all outputs)
Integration test: Briefing generates from debate with memory recall
```

### Phase 4: Simulation Layer (Days 8-10)

```
Chunk 4.1: VectorBT backtest engine wrapper
Chunk 4.2: Signal adapters (7 signal sources + combined)
Chunk 4.3: Indian FIFO tax engine (pre/post July 2024, STCG/LTCG, cess)
Chunk 4.4: QuantStats integration (tear sheets, 60+ metrics)
Chunk 4.5: Optuna parameter optimization integration
Chunk 4.6: Simulation API endpoints + auto-loop scheduler (cron)
Chunk 4.7: Factor validation with alphalens-reloaded (RS as factor)
Integration test: Breadth timing on PPFAS produces correct XIRR matching V8
```

### Phase 5: Portfolio Layer (Days 10-12)

```
Chunk 5.1: casparser integration (CAMS PDF → parsed holdings)
Chunk 5.2: Portfolio mapping engine (scheme name → JIP mstar_id)
Chunk 5.3: Portfolio analysis engine (RS overlay, concentration, overlap, wtd metrics)
Chunk 5.4: Riskfolio-Lib integration (optimization with SEBI constraints)
Chunk 5.5: Brinson attribution engine
Chunk 5.6: Portfolio API endpoints
Integration test: CAMS upload → mapped holdings → full analysis → attribution
```

### Phase 6: Frontend — Pro Shell (Days 12-15)

```
Chunk 6.1: Atlas layout + navigation in fie2 (/pro/* routes)
Chunk 6.2: Global Intelligence page (briefing, ratios, regime, heatmap)
Chunk 6.3: Stock Pulse — bubble chart + drill-down table
Chunk 6.4: Stock deep-dive page (complete, all pillars, TV chart)
Chunk 6.5: MF Pulse — category drill-down + fund deep-dive (holdings drill-through)
Chunk 6.6: ETF Pulse — global rotation + ETF deep-dive
Chunk 6.7: Simulation page (3-step builder + results + tear sheets)
Chunk 6.8: Portfolio page (CAMS import + dashboard + attribution)
Chunk 6.9: Discovery/Screener page
Chunk 6.10: Alert Center + Watchlist Manager
Integration test: Full Pro shell renders with live API data
```

### Phase 7: Frontend — Advisor Shell (Days 15-17)

```
Chunk 7.1: Advisor layout + navigation (/advisor/* routes)
Chunk 7.2: Client management (list, detail, portfolio, goals)
Chunk 7.3: Fund discovery workflow (filter → compare → overlap → select)
Chunk 7.4: Model portfolio management
Chunk 7.5: Report generator (quarterly review template, auto-commentary)
Integration test: Full Advisor shell with client workflows
```

### Phase 8: Frontend — Retail Shell (Days 17-19)

```
Chunk 8.1: Retail layout (/retail/* or default routes)
Chunk 8.2: Simplified fund discovery (curated lists, traffic-light health)
Chunk 8.3: Portfolio tracker (CAMS import, simple returns view)
Chunk 8.4: Goal planner + SIP calculator
Chunk 8.5: Simplified alerts + educational content
Integration test: Full Retail shell, mobile-responsive
```

### Phase 9: TV + Polish + Deployment (Days 19-21)

```
Chunk 9.1: TV webhook handler + alert routing
Chunk 9.2: TV bidirectional sync (portfolio → watchlist)
Chunk 9.3: TV chart embedding across all deep-dive pages
Chunk 9.4: Nginx configuration + SSL + domain setup
Chunk 9.5: Docker containerization (backend + frontend)
Chunk 9.6: End-to-end testing + performance optimization
Chunk 9.7: Cron setup (nightly agent orchestration, weekly simulation auto-loop)
Final: Deploy to production
```

---

## 15. COORDINATION & QUALITY

### Contracts-First Development

```
contracts/ directory contains ALL Pydantic schemas BEFORE any code is written.

Every API endpoint has:
  - Request model (if POST/PUT)
  - Response model
  - Example data

Every inter-agent message has:
  - Input schema
  - Output schema

Every database table has:
  - SQLAlchemy model
  - Migration SQL

If a chunk needs to change a contract:
  1. Update the contract FIRST
  2. Run ALL integration tests for dependent chunks
  3. Fix any breakages
  4. Then proceed with the chunk's implementation
```

### Integration Test Suite

```
tests/integration/
├── test_data_layer.py       → JIP API returns valid data matching contracts
├── test_intelligence.py     → Sector rollups, RS momentum correct
├── test_agents.py           → Briefing generates, debate works, memory recalls
├── test_simulation.py       → Backtest produces correct results, tax calc accurate
├── test_portfolio.py        → CAMS parse → map → analyze works
├── test_api.py              → All ATLAS endpoints return valid contract-matching responses
└── test_frontend.py         → Key pages render without errors (Playwright)

Run after EVERY chunk. If any test fails, the chunk is not committed.
```

### Quality Gates

```
PRE-COMMIT (enforced by hooks):
  • All Pydantic models validate (no Any types)
  • No float in financial calculations (Decimal only)
  • All query params Optional[] with defaults
  • No file > 400 lines
  • Integration tests pass

POST-COMMIT:
  • BUILD_STATUS.md updated
  • Intelligence engine finding logged (what was built, what was learned)
```

---

## 16. SYSTEM HARDENING & EXECUTION DISCIPLINE

This section defines the execution discipline, data semantics, and system guarantees
that make ATLAS production-grade. This layer does NOT change WHAT ATLAS does.
It enforces HOW ATLAS must behave. Every subsystem, agent, API, and computation
must comply with these rules. Violations are hard-stop conditions during build.

### 16.1 System Design Principles

```
DETERMINISM OVER INTELLIGENCE
  Same input → same output, always.
  No stochastic outputs in core system.
  Agents are allowed non-determinism, but their outputs must be bounded
  by structured schemas. Core computations (RS, breadth, sector rollups,
  simulation) must be perfectly reproducible.

EXPLAINABILITY FIRST
  Every metric must be traceable to its source tables and formula.
  No black-box outputs in the decision layer.
  If a value cannot be explained, it must not be shown.

GRACEFUL DEGRADATION
  System must never fail completely.
  Partial data > no data.
  If TradingView MCP is down → TV pillar shows "unavailable", system continues.
  If Qlib pipeline fails → system runs without alpha factors, core RS still works.
  If one agent crashes → other agents continue, orchestrator logs the failure.

DATA > MODEL
  If data conflicts with model output → data wins.
  Models assist, they do not decide.
  Fund manager always sees raw data alongside model interpretation.
```

### 16.2 Time-Series & Data Semantics

```
NO ARTIFICIAL DATA LIMITS
  All systems operate on FULL historical data:
    Equities: 2007 → present (19+ years)
    MF NAV: 2006 → present (20 years)
    RS scores: 2016 → present (10 years)
    Breadth: 2007 → present
    Regime: 2007 → present
    Global: 2010 → present
    Macro: 1802 → present (some series)

  Indicators like sma_200, rsi_14, roc_21 are DERIVED FEATURES,
  NOT data limits. The system must never truncate history
  because of indicator lookback windows.

LOOKBACK FLEXIBILITY
  All APIs must support:
    GET /endpoint?from=YYYY-MM-DD&to=YYYY-MM-DD

  Defaults if not provided:
    Time-series endpoints → last 12 months
    Universe endpoints → latest snapshot only

DATA MODES (mandatory on all data endpoints):
  1. SNAPSHOT → latest state (default)
  2. TIMESERIES → historical data with from/to params
  3. DELTA → change between two dates
  4. ROLLING → rolling window metrics (e.g., rolling 1Y Sharpe)

  Implemented via query parameter: ?mode=snapshot|timeseries|delta|rolling

AGGREGATION RULES
  Daily → default granularity for all data
  > 5 years of data → allow weekly/monthly aggregation via ?granularity=weekly
  > 10 years → must aggregate automatically if client doesn't specify
  Aggregation method: OHLC for prices, AVG for metrics, LAST for RS/regime
```

### 16.3 Data Provenance & Traceability

```
Every computed value returned by ATLAS must include provenance metadata.
This is NON-NEGOTIABLE for explainability.

Response envelope for computed metrics:

{
  "value": 46.2,
  "metric": "pct_above_200dma",
  "computed_from": ["de_equity_technical_daily.above_200dma", "de_instrument.sector"],
  "computation": "COUNT(above_200dma=true) / COUNT(*) × 100 WHERE sector='Banking'",
  "data_as_of": "2026-04-09T15:30:00+05:30",
  "stock_count": 41,
  "staleness": "fresh"  // "fresh" (<30min), "stale" (>30min), "delayed" (>24hr)
}

For API responses, provenance is included in a _meta field:

{
  "data": { ... actual response ... },
  "_meta": {
    "data_as_of": "2026-04-09T15:30:00+05:30",
    "computed_at": "2026-04-09T18:35:12+05:30",
    "sources": ["de_equity_ohlcv", "de_equity_technical_daily", "de_rs_scores"],
    "staleness": "fresh",
    "cache_hit": true,
    "cache_age_seconds": 142
  }
}
```

### 16.4 Data Contract Enforcement

```
STRICT SCHEMAS
  All APIs MUST return typed responses matching Pydantic models.
  No Optional[] without explicit documentation of when it's None.
  No Any types anywhere in the codebase.
  Every field has: name, type, description, example value.

API VERSIONING
  All API paths are versioned: /api/v1/stocks/universe
  Breaking changes → new version only (/api/v2/...)
  v1 endpoints must not break once released.
  Additive changes (new optional fields) are allowed in same version.
  Removal or rename of fields → version bump required.

BACKWARD COMPATIBILITY
  v1 responses are immutable contracts.
  New features add to v2, never modify v1.
  Deprecation: announce in _meta.deprecation_warning for 30 days before removal.
```

### 16.5 Data Quality Layer

```
VALIDATION CHECKS (run before any computation, logged always):

  Missing values:
    If >5% of a column is NULL for a given date → log warning
    If >20% → flag as DATA_QUALITY_ISSUE, halt computation for that entity
    NULL in RS → exclude from averages, never zero-fill
    NULL in financial values → must produce NULL, not 0 or NaN

  Outliers:
    Z-score > 5 on any daily return → flag as ANOMALY
    Price change > 20% in one day → flag (may be corporate action)
    Volume > 10x 20-day average → flag
    RS composite change > 15 in one day → flag
    All anomalies FLAGGED, NOT hidden. Shown to user with explanation.

  Duplicates:
    Check for duplicate (instrument_id, date) rows before computation
    If found → use latest updated_at, log warning

  Timestamp consistency:
    All data for a computation run must share the same data_as_of date
    No mixing timestamps across tables within one computation cycle

DATA FRESHNESS TRACKING
  Each dataset tracks:
  {
    "table": "de_equity_ohlcv",
    "last_updated": "2026-04-09T15:30:00+05:30",
    "expected_frequency": "daily_by_18:00_IST",
    "is_delayed": false,
    "delay_minutes": 0
  }

  Exposed via GET /api/v1/status
  If any critical dataset is >24hr stale → alert generated automatically

ANOMALY FLAGS IN RESPONSES
  When returning data for an instrument with active anomaly flags:
  {
    "symbol": "HDFCBANK",
    "rs_composite": 4.53,
    "_anomalies": [
      {"type": "volume_spike", "message": "Volume 5.2x above 20-day avg", "date": "2026-04-09"}
    ]
  }
```

### 16.6 System State Management

```
CANONICAL TIME
  All systems operate on the data_as_of timestamp.
  This timestamp is set ONCE at the start of each pipeline run.
  Every computation in that run uses the SAME data_as_of.
  No individual queries with their own timestamps during a single run.

SNAPSHOT CONSISTENCY
  When the nightly pipeline runs at 18:30 IST:
    1. Query data_as_of = MAX(date) from de_equity_ohlcv → e.g., 2026-04-09
    2. ALL computations (RS momentum, sector rollups, MF weighted technicals,
       intelligence findings) use this SAME date
    3. If de_rs_scores has a different MAX(date) than de_equity_ohlcv → HALT
       Log: "Data inconsistency: OHLCV as of 2026-04-09 but RS as of 2026-04-08"
       Use the OLDER date (conservative) and flag as stale

IDEMPOTENCY
  Running the same pipeline twice with the same data_as_of must produce
  identical results. No side effects. No accumulated state between runs.
  (Intelligence engine findings are additive and timestamped, so they don't
  violate idempotency — they accumulate but don't modify existing records.)
```

### 16.7 Agent System Constraints

```
OUTPUT STRUCTURE (mandatory for ALL agents)
  Every agent output must follow this schema:

  {
    "agent_id": "sector-analyst",
    "entity": "Banking",
    "entity_type": "sector",
    "claim": "Banking sector entering LEADING quadrant",
    "supporting_data": {
      "rs_composite": 2.37,
      "rs_momentum": 3.2,
      "pct_above_200dma": 62,
      "macd_bullish_pct": 58
    },
    "confidence": 0.78,
    "horizon": "5_trading_days",
    "invalidation_condition": "If rs_momentum drops below 0 or pct_above_200dma drops below 50",
    "data_as_of": "2026-04-09"
  }

NO FREE-TEXT DRIFT
  Agents must not output unstructured text without schema.
  LLM-generated text (briefings, commentary) must be wrapped in structured
  schema with typed fields. The narrative is ONE FIELD within the schema,
  not the entire output.

EVIDENCE REQUIREMENT
  Every claim must reference at least one of:
    • RS data (rs_composite, rs_momentum, quadrant)
    • Technical data (rsi_14, adx_14, macd_histogram, above_200dma)
    • Fundamental data (from TV screener or Goldilocks)
    • Historical pattern (from intelligence engine with sample_size)
  Claims without evidence are rejected by the orchestrator.

BOUNDED CONFIDENCE
  Confidence must be between 0.0 and 1.0.
  Agents must not output confidence > 0.95 (epistemic humility).
  If an agent outputs 1.0, the orchestrator rejects it with:
  "No prediction in financial markets has 100% confidence."
```

### 16.8 Intelligence Engine Quality Control

```
SIGNAL vs NOISE SEPARATION
  Every finding stored in atlas_intelligence must be categorized:
    SIGNAL → actionable, time-bound, has invalidation condition
    CONTEXT → informative background, no specific action
    NOISE → low confidence, contradicted by other findings → auto-discarded

  Only SIGNAL and CONTEXT are stored. NOISE is logged but not persisted.

MEMORY LIMITS (hard caps)
  System-wide: max 1,000 findings per day
  Per entity per agent: max 5 findings per day
  (prevents a runaway agent from flooding the intelligence engine)

  If an agent tries to write more:
    Log: "Agent {id} exceeded daily finding limit for {entity}"
    Reject the finding
    Flag for review in accuracy tracker

RELEVANCE DECAY
  Every finding has an expires_at timestamp (default: 7 days).
  Expired findings remain in the database but are excluded from queries
  unless explicitly requested with ?include_expired=true.

  Findings validated as accurate (is_validated=true) get extended shelf life:
    SIGNAL validated as correct → expires_at extended by 30 days
    SIGNAL validated as incorrect → immediately marked expired

  Similarity search query automatically deprioritizes older findings:
    effective_score = similarity_score × recency_weight
    recency_weight = exp(-0.1 × days_since_creation)
```

### 16.9 Computation Layer Discipline

```
NO DUPLICATE COMPUTATION
  Metrics computed ONCE by the designated system, cached, and reused:
    RS momentum → computed by rs-analyzer, cached in API response
    Sector rollups → computed by sector-analyst, cached 5 minutes
    MF weighted technicals → computed by JIP pipeline, stored in de_mf_weighted_technicals
    Index breadth → computed on-demand, cached 5 minutes

  Agents must READ cached metrics, NOT recompute them.
  If an agent needs a metric, it queries the API or intelligence engine.

PRECOMPUTE vs ON-DEMAND

  PRECOMPUTE (nightly batch, cached):
    RS momentum for all entities
    Quadrant classification for all entities
    Sector rollups (22 metrics × 31 sectors)
    MF weighted technicals (for all 838 funds)
    MF category rollups
    Index breadth (for all 135 indices)
    Qlib Alpha158 features (for all 2,743 stocks)
    MF holder count per stock
    Briefing (one per day)

  ON-DEMAND (computed when requested, cached briefly):
    Simulations (user-triggered, results cached permanently)
    Portfolio analysis (on CAMS upload or portfolio change)
    Discovery/screening queries
    TV TA enrichment (cached 15 minutes)
    Deep-dive page assembly
    Intelligence engine queries
```

### 16.10 Performance Architecture

```
CACHING STRATEGY

  Redis (for hot data, sub-millisecond reads):
    equity_universe → TTL 5 minutes
    sector_rollups → TTL 5 minutes
    mf_universe → TTL 5 minutes
    etf_universe → TTL 5 minutes
    market_breadth → TTL 5 minutes
    market_regime → TTL 5 minutes
    tv_ta_cache → TTL 15 minutes
    briefing_latest → TTL 24 hours

  PostgreSQL (for warm data):
    atlas_intelligence → permanent, queried via pgvector
    atlas_simulations → permanent
    atlas_qlib_features → daily refresh

  In-memory (for session data):
    Active simulation configs
    Current user portfolio state

QUERY OPTIMIZATION
  No joins on de_equity_ohlcv without date range filter (partitioned table).
  No SELECT * from de_rs_scores without entity_type + date filter (14.7M rows).
  Materialized views for heavy aggregations:
    mv_sector_rollup → refreshed every 5 minutes via pg_cron or application trigger
    mv_mf_category_rollup → same
  All foreign keys indexed (already enforced by JIP conventions).
  EXPLAIN ANALYZE on every new query before deployment.

RESPONSE TIME TARGETS
  Universe endpoints (stocks, MF, ETF): < 500ms (cached), < 2s (cold)
  Deep-dive endpoints: < 300ms (cached)
  Simulation (single run): < 5s
  Simulation (10K parameter sweep): < 30s
  Intelligence query: < 100ms
  Portfolio analysis: < 10s (first run), < 1s (cached)
```

### 16.11 Error Handling Standard

```
All errors returned by ATLAS APIs must follow this structure:

{
  "error": {
    "code": "DATA_STALE",
    "message": "Equity OHLCV data is 26 hours old. Expected refresh by 18:00 IST.",
    "module": "jip_client",
    "severity": "warning",  // "info", "warning", "error", "critical"
    "timestamp": "2026-04-10T20:15:00+05:30",
    "fallback_action": "serving_cached_data",
    "details": {
      "expected_as_of": "2026-04-10",
      "actual_as_of": "2026-04-09",
      "delay_hours": 26
    }
  }
}

NO SILENT FAILURES
  Every error is logged with structured JSON (structlog).
  Every error triggers a fallback action (serve stale, skip, retry).
  Every critical error triggers an alert (written to atlas_alerts table).

FALLBACK CHAIN
  For data fetching:
    1. Try live query → success? return
    2. Try Redis cache → success? return with _meta.cache_hit=true
    3. Try last known good snapshot → return with _meta.staleness="stale"
    4. Return error response with fallback_action="no_data_available"

  For agent execution:
    1. Run with assigned model (e.g., sonnet) → success? return
    2. Retry with model escalation (e.g., opus) → success? return
    3. Skip agent, log error, continue pipeline with other agents
    4. After 3 consecutive failures → alert, mark agent as DEGRADED
```

### 16.12 Security & Access Control

```
INTERNAL API ISOLATION
  /internal/* endpoints on JIP (port 8000) are NOT exposed publicly.
  Only accessible from ATLAS EC2 via VPC internal network.
  No API key needed (network-level security via security groups).

ROLE-BASED ACCESS (for frontend shells)
  Pro shell: full API access, all endpoints, all data depth
  Advisor shell: client-scoped access, model portfolio management, reporting
  Retail shell: self-scoped access, own portfolio only, simplified endpoints

  Implemented via JWT claims: { role: "pro" | "advisor" | "retail", org_id, user_id }
  Each API endpoint checks role before returning data.

SENSITIVE DATA
  Client portfolio data: encrypted at rest (PostgreSQL TDE or column-level)
  Client PII (name, PAN, email): NEVER logged, NEVER in error messages
  API keys (Anthropic, TV): stored in environment variables, never in code
  CAMS PDF files: processed and discarded, raw PDFs NOT stored permanently
```

### 16.13 Build Execution Discipline

```
STEPWISE BUILD ORDER (Claude must follow exactly)
  1. Data contracts (Pydantic schemas)
  2. Database migrations (atlas_* tables)
  3. JIP internal API integration
  4. Core metric computations (RS momentum, quadrants, sector rollups)
  5. API endpoints (one by one, tested individually)
  6. Intelligence engine
  7. Agent system
  8. Simulation engine
  9. Portfolio engine
  10. Frontend shells

  NEVER skip ahead. Step N depends on Step N-1 being tested and committed.

VALIDATION AFTER EACH STEP
  After every chunk commit:
    • Run integration tests for this chunk
    • Run ALL previously-passing integration tests (regression)
    • Log sample outputs to BUILD_STATUS.md
    • If any test fails → FIX before proceeding

HARD STOP CONDITIONS (Claude must halt immediately if)
  • Schema mismatch between contract and implementation
  • Integration test failure that can't be resolved in 3 attempts
  • Data inconsistency (e.g., sector rollup stock_count doesn't match universe count)
  • Financial calculation producing float instead of Decimal
  • Any test producing different results on consecutive runs (non-determinism)

  On hard stop: log the full error context to BUILD_STATUS.md,
  DO NOT attempt to work around it, wait for human review.
```

### 16.14 Observability

```
STRUCTURED LOGGING (mandatory)
  All logs in JSON format via structlog:
  {
    "timestamp": "2026-04-10T18:35:12.456Z",
    "level": "info",
    "module": "sector_analyst",
    "event": "sector_rollup_computed",
    "sectors": 31,
    "stocks_processed": 2689,
    "duration_ms": 342,
    "data_as_of": "2026-04-09"
  }

  Log levels:
    DEBUG → detailed computation steps (development only)
    INFO → normal operations (pipeline started, completed, metrics)
    WARNING → degraded state (stale data, agent skipped, cache miss)
    ERROR → failure requiring attention (agent crash, data inconsistency)
    CRITICAL → system-level failure (database unreachable, pipeline halted)

METRICS (tracked continuously)
  API response times (p50, p95, p99) per endpoint
  Agent execution time per agent per run
  Cache hit rate per cache key
  Database query times (slow query log for >500ms)
  Intelligence engine: findings/day, queries/day, avg similarity score
  Pipeline: total run time, per-step time, success/failure rate

ALERTS (auto-generated to atlas_alerts)
  Pipeline failure → immediate alert
  Agent crash (3 consecutive) → alert + mark DEGRADED
  Data staleness (>24hr) → alert
  Disk space < 20% → alert
  Memory usage > 80% → alert
  API error rate > 5% in 5-minute window → alert
```

### 16.15 Evolution Control (Safe Mode)

```
MUTATION GUARDRAILS
  Only 1 agent mutation per 5-day cycle (no simultaneous experiments)
  Shadow testing required: mutated agent runs IN PARALLEL with original,
    both outputs logged, only original's output used for decisions
  5 trading days minimum evaluation before merge/revert decision
  Maximum 3 mutations per agent per month (prevent excessive churn)

ROLLBACK
  All mutations use git branches: evolution/{agent_id}/{version}
  If mutation degrades Sharpe → immediate revert: git branch -D
  Agent weights never go below 0.3 (floor) — agent is still consulted,
    just with reduced influence. Complete removal only after 20+ days at floor.
  System maintains last-known-good AGENT.md for every agent in git history.

SPAWNING SAFETY
  Maximum 3 specialist agents can exist at any time (prevent agent sprawl)
  Spawned agents inherit base domain knowledge + sector-specific additions
  If spawned agent doesn't achieve weight > 0.5 within 20 days → auto-removed
  All spawning decisions logged to atlas_agent_memory with rationale
```

### 16.16 System Guarantees

```
ATLAS MUST BE:

  DETERMINISTIC — same data_as_of → same outputs (for core computations)
  EXPLAINABLE — every number traceable to source + formula
  FAULT-TOLERANT — partial data > no data, graceful degradation at every layer
  TRACEABLE — full provenance on every computed value
  IDEMPOTENT — pipeline can be re-run safely without side effects

IF ANY FEATURE VIOLATES THESE GUARANTEES → IT MUST NOT BE DEPLOYED.

This is checked at build time (hard stop conditions) and at runtime
(data quality layer validation). No exceptions.
```

---

## 17. UNIFIED QUERY LAYER — BLOOMBERG-GRADE API

ATLAS APIs must NOT be endpoint-driven. They must support a query-driven
architecture. The fixed endpoints in Section 11 remain as convenience shortcuts,
but ALL of them are syntactic sugar over the Unified Query Layer (UQL).

### 17.1 Core Principle

Instead of many fixed endpoints, ATLAS exposes ONE flexible query system:

```
POST /api/v1/query
```

Every fixed endpoint (GET /api/v1/stocks/universe, GET /api/v1/mf/categories, etc.)
is internally translated to a UQL query. Agents, frontends, external integrations,
and the discovery engine all use the SAME query system.

### 17.2 Query Structure

```json
{
  "entity_type": "equity",
  
  "filters": [
    { "field": "sector", "op": "=", "value": "Banking" },
    { "field": "rs_composite", "op": ">", "value": 5 },
    { "field": "rsi_14", "op": ">", "value": 60 },
    { "field": "above_200dma", "op": "=", "value": true },
    { "field": "quadrant", "op": "in", "value": ["LEADING", "IMPROVING"] }
  ],
  
  "sort": [
    { "field": "rs_composite", "direction": "desc" }
  ],
  
  "limit": 20,
  "offset": 0,
  
  "fields": [
    "symbol", "company_name", "sector",
    "rs_composite", "rs_momentum", "quadrant",
    "rsi_14", "adx_14", "above_200dma",
    "mf_holder_count", "close", "volume"
  ],
  
  "mode": "snapshot",

  "include": ["technicals", "rs", "conviction"]
}
```

### 17.3 Supported Entity Types

```
"equity"    → queries against stock universe (de_instrument + joins)
"mf"        → queries against MF universe (de_mf_master + joins)
"etf"       → queries against ETF universe (de_etf_master + joins)
"sector"    → queries against sector rollups (computed aggregations)
"index"     → queries against index universe (de_index_master + joins)
"global"    → queries against global instruments
"finding"   → queries against intelligence engine (atlas_intelligence)
"alert"     → queries against alerts (atlas_alerts)
"portfolio" → queries against portfolios (atlas_portfolios)
```

### 17.4 Supported Operators

```
"="          → exact match
"!="         → not equal
">"          → greater than
">="         → greater than or equal
"<"          → less than
"<="         → less than or equal
"in"         → value in list
"not_in"     → value not in list
"between"    → value between [min, max]
"contains"   → text contains (for fund_name, company_name search)
"is_null"    → field is null
"is_not_null" → field is not null
```

### 17.5 Aggregation Queries

```json
{
  "entity_type": "equity",
  "group_by": ["sector"],
  
  "aggregations": [
    { "field": "rs_composite", "function": "avg", "alias": "avg_rs" },
    { "field": "rs_composite", "function": "count", "alias": "stock_count" },
    { "field": "above_200dma", "function": "pct_true", "alias": "pct_above_200dma" },
    { "field": "rsi_14", "function": "avg", "alias": "avg_rsi" },
    { "field": "adx_14", "function": "pct_above", "threshold": 25, "alias": "pct_trending" },
    { "field": "macd_histogram", "function": "pct_positive", "alias": "pct_macd_bullish" }
  ],
  
  "sort": [{ "field": "avg_rs", "direction": "desc" }],
  "limit": 31
}
```

Supported aggregation functions:
```
"avg"          → average of field
"sum"          → sum of field
"min"          → minimum
"max"          → maximum
"count"        → count of non-null values
"count_all"    → count including nulls
"pct_true"     → percentage where boolean field is true
"pct_positive" → percentage where numeric field > 0
"pct_above"    → percentage where field > threshold
"pct_below"    → percentage where field < threshold
"median"       → median value
"stddev"       → standard deviation
```

### 17.6 Time-Series Queries

```json
{
  "entity_type": "equity",
  "mode": "timeseries",
  
  "filters": [
    { "field": "symbol", "op": "=", "value": "HDFCBANK" }
  ],
  
  "fields": ["date", "close", "rs_composite", "rsi_14"],
  
  "time_range": {
    "from": "2025-04-01",
    "to": "2026-04-09"
  },
  
  "granularity": "daily"
}
```

### 17.7 Predefined Query Templates

System exposes named templates that map to common queries:

```
POST /api/v1/query/template

{ "template": "top_rs_gainers", "params": { "benchmark": "NIFTY 500", "limit": 15 } }
{ "template": "sector_rotation", "params": { "benchmark": "NIFTY 500" } }
{ "template": "oversold_candidates", "params": { "rsi_below": 30, "rs_above": 0 } }
{ "template": "high_momentum_funds", "params": { "category": "Large Cap", "limit": 10 } }
{ "template": "breadth_dashboard" }
{ "template": "regime_history", "params": { "months": 12 } }
{ "template": "mf_category_flows", "params": { "months": 6 } }
{ "template": "portfolio_overlap", "params": { "funds": ["A", "B"] } }

Templates are defined in code as UQL query objects. Adding a new template
requires NO API changes — just a new query definition.
```

### 17.8 Query Execution Engine

```
Request arrives at POST /api/v1/query
    │
    ▼
PARSE: Validate query against Pydantic schema
    │
    ▼
AUTHORIZE: Check JWT role — does this user have access to this entity_type?
    │
    ▼
OPTIMIZE: Translate to SQL
    • Map entity_type to source tables + joins
    • Map filters to WHERE clauses with parameterized queries
    • Map aggregations to GROUP BY + aggregate functions
    • Apply sort + limit + offset
    • Check for index availability (reject if full table scan required)
    │
    ▼
CACHE CHECK: Hash the query → check Redis
    • Cache hit → return cached result with _meta.cache_hit=true
    │
    ▼
EXECUTE: Run optimized SQL against PostgreSQL
    • Timeout: 2 seconds hard limit
    • If timeout → return error with suggestion to narrow filters
    │
    ▼
COMPOSE: Apply include= directives (see §18)
    │
    ▼
RESPOND: Return with _meta provenance
```

### 17.9 Safety Constraints

```
Max limit: 500 rows per query (prevents data dumps)
Max filters: 10 per query (prevents query complexity explosion)
Max aggregations: 8 per query
Query timeout: 2 seconds (hard kill)
Rate limit: 60 queries/minute per user (Pro), 20/minute (Advisor), 10/minute (Retail)
No SELECT * — fields must be explicitly requested
No unindexed filters on tables > 1M rows — query planner rejects with suggestion
```

### 17.10 How Fixed Endpoints Map to UQL

```
GET /api/v1/stocks/universe?sector=Banking&rs_min=5
  → UQL: { entity_type: "equity", filters: [{sector=Banking}, {rs_composite>5}], 
           fields: [all stock fields], mode: "snapshot" }

GET /api/v1/stocks/sectors
  → UQL: { entity_type: "equity", group_by: ["sector"], 
           aggregations: [avg_rs, stock_count, pct_above_200dma, ...] }

GET /api/v1/mf/universe?category=Large Cap
  → UQL: { entity_type: "mf", filters: [{category_name="Large Cap"}],
           fields: [all fund fields], mode: "snapshot" }

GET /api/v1/stocks/movers
  → UQL: { entity_type: "equity", sort: [{rs_momentum: desc}], limit: 15 }
     UNION
         { entity_type: "equity", sort: [{rs_momentum: asc}], limit: 15 }

The fixed endpoints remain as convenience shortcuts. They are thin wrappers
that construct UQL queries and call the same execution engine.
```

---

## 18. COMPOSABLE RESPONSE MODEL

APIs must support modular response composition. Clients request only
the data they need, avoiding over-fetching and eliminating the need
for new endpoints when new data dimensions are added.

### 18.1 Include System

```
GET /api/v1/stocks/HDFCBANK?include=rs,technicals,conviction,intelligence,peers,goldilocks

Query parameter: include= (comma-separated list of modules)

Available modules:
  identity     → basic: symbol, name, sector, industry, market_cap (always included)
  price        → latest OHLCV + delivery_pct
  rs           → RS scores (1w through composite) + momentum + quadrant
  technicals   → all 47 technical indicators
  risk         → beta, sharpe, sortino, max_dd, calmar
  conviction   → 4 pillars (RS, technical health, external, institutional)
  intelligence → recent findings from intelligence engine for this entity
  peers        → same-sector stocks compared on key metrics
  goldilocks   → Goldilocks stock ideas, oscillators, fib levels if available
  tv           → TradingView TA summary + Piotroski + Altman
  holders      → MF holders list (for stocks)
  holdings     → stock holdings list (for MFs)
  sectors      → sector exposure (for MFs)
  chart        → OHLCV time series for chart rendering
  qlib         → Qlib Alpha158 factor values
  anomalies    → active anomaly flags
```

### 18.2 Example Response

```json
// GET /api/v1/stocks/HDFCBANK?include=rs,conviction,intelligence

{
  "data": {
    "identity": {
      "symbol": "HDFCBANK",
      "company_name": "HDFC Bank Ltd",
      "sector": "Banking",
      "industry": "Private Bank",
      "cap_category": "large",
      "nifty_50": true
    },
    "rs": {
      "rs_1w": -1.81,
      "rs_1m": 1.57,
      "rs_3m": 4.86,
      "rs_6m": -1.73,
      "rs_12m": 22.47,
      "rs_composite": 4.53,
      "rs_momentum": 1.62,
      "quadrant": "LEADING",
      "vs_benchmark": "NIFTY 500"
    },
    "conviction": {
      "pillar_1_rs": {
        "summary": "Outperforming NIFTY 500, improving for 3 weeks, LEADING quadrant",
        "checks": { "rs_positive": true, "momentum_positive": true, "quadrant": "LEADING" }
      },
      "pillar_2_technical": {
        "summary": "8/10 checks passing",
        "passing": 8,
        "total": 10,
        "checks": [
          { "name": "Above 200-DMA", "pass": true, "value": "₹1,842 > ₹1,756" },
          { "name": "RSI healthy", "pass": true, "value": "58 (not overbought)" }
        ]
      },
      "pillar_3_external": {
        "tv_daily": "STRONG_BUY",
        "tv_weekly": "BUY",
        "tv_monthly": "NEUTRAL",
        "piotroski": 7,
        "goldilocks": "Stock Bullet: entry ₹1,800, target ₹2,100"
      },
      "pillar_4_institutional": {
        "mf_holders": 124,
        "delivery_pct": 42.0,
        "category_flow": "+₹2,300Cr"
      }
    },
    "intelligence": [
      {
        "agent": "sector-analyst",
        "finding": "Banking sector entering LEADING quadrant with breadth support at 62%",
        "confidence": 0.78,
        "age_hours": 18
      },
      {
        "agent": "fm_input",
        "finding": "FM noted: NPA guidance from management was positive in Q3 call",
        "confidence": 0.70,
        "age_hours": 72
      }
    ]
  },
  "_meta": {
    "data_as_of": "2026-04-09T15:30:00+05:30",
    "includes_loaded": ["identity", "rs", "conviction", "intelligence"],
    "staleness": "fresh"
  }
}
```

### 18.3 Include for UQL Queries

The include system also works with POST /api/v1/query:

```json
{
  "entity_type": "equity",
  "filters": [{ "field": "sector", "op": "=", "value": "Banking" }],
  "fields": ["symbol", "rs_composite", "quadrant"],
  "include": ["conviction", "tv"],
  "limit": 10
}
```

Each row in the response gets the requested include modules attached.
For list queries, includes are computed per-row (batch-optimized internally).

---

## 19. DATA TIMING LAYERS

All data in ATLAS belongs to one of three timing layers. Every API response
must declare which layer its data comes from. Mixing layers without
explicit declaration is forbidden.

### 19.1 Layer Classification

```
LAYER 1: SNAPSHOT (daily batch, computed nightly)
  Updated: once per day after market close (~18:30 IST pipeline)
  Staleness: up to 24 hours
  Data:
    • Equity universe (price, technicals, RS, market cap)
    • Sector rollups (22 metrics)
    • MF universe (NAV, derived metrics, weighted technicals)
    • ETF universe (price, technicals, RS)
    • Global universe (prices, technicals, RS)
    • Market breadth + regime
    • Index breadth
    • MF category rollups
    • Qlib Alpha158 features
    • Briefing
    • Agent scores + Darwinian weights

LAYER 2: NEAR REAL-TIME (cached, 5-15 minute refresh)
  Updated: on access, cached with TTL
  Staleness: 5-15 minutes
  Data:
    • TradingView TA summaries (15-min cache)
    • TradingView fundamental scores (15-min cache)
    • Intelligence engine queries (no cache — always fresh query)
    • Alert feed (no cache — always fresh)

LAYER 3: ON-DEMAND (computed when requested)
  Updated: at request time
  Staleness: zero (computed live)
  Data:
    • Simulations (computed fresh each run)
    • Portfolio analysis (computed on upload or change)
    • Discovery/screening queries (computed per query)
    • Portfolio optimization (computed per request)
    • UQL custom queries
```

### 19.2 Response Timing Declaration

Every API response includes timing metadata:

```json
{
  "data": { ... },
  "_meta": {
    "data_layer": "snapshot",
    "data_as_of": "2026-04-09T15:30:00+05:30",
    "computed_at": "2026-04-09T18:35:12+05:30",
    "staleness": "fresh",
    "next_refresh": "2026-04-10T18:30:00+05:30"
  }
}
```

### 19.3 Cross-Layer Consistency

When a response combines data from multiple layers:

```json
{
  "data": {
    "rs_composite": 4.53,           // Layer 1: snapshot
    "tv_daily_ta": "STRONG_BUY",    // Layer 2: near real-time
    "simulation_xirr": 16.2         // Layer 3: on-demand
  },
  "_meta": {
    "layer_mix": true,
    "layers": {
      "rs_composite": { "layer": "snapshot", "as_of": "2026-04-09" },
      "tv_daily_ta": { "layer": "near_realtime", "as_of": "2026-04-10T10:15:00" },
      "simulation_xirr": { "layer": "on_demand", "computed_at": "2026-04-10T10:16:32" }
    }
  }
}
```

The frontend can display timing indicators:
- Snapshot data → show "as of 09-Apr-2026"
- Near real-time → show "updated 5 min ago"
- On-demand → show "computed just now"

---

## 20. API DESIGN PRINCIPLES

ATLAS APIs are not an implementation detail. They ARE the product.
The API must be usable without any frontend — by agents, dashboards,
external integrations, and the fund manager directly via tools like
curl or Postman.

### 20.1 API-First Design

```
Every feature in ATLAS must work through the API FIRST.
The frontend is a consumer of the API, not a co-owner of logic.

This means:
  • No business logic in frontend code
  • No direct database queries from frontend
  • No API endpoints that only make sense with a specific UI
  • Every API endpoint must be testable independently
```

### 20.2 Self-Documenting (OpenAPI)

```
FastAPI auto-generates OpenAPI spec at /api/v1/docs (Swagger UI)
and /api/v1/redoc (ReDoc).

Every endpoint must have:
  • Summary (one line)
  • Description (what it does, when to use it)
  • Request model with field descriptions
  • Response model with field descriptions + examples
  • At least one example request/response pair
  • Error response models (400, 401, 404, 422, 500)
  • Edge case documentation (what happens with empty data? stale data?)
```

### 20.3 Consumer Types

The API serves 5 consumer types simultaneously:

```
1. ATLAS Frontend (Next.js shells)
   → Uses fixed endpoints for page rendering
   → Uses UQL for discovery/screening
   → Needs: fast responses, include system for data composition

2. ATLAS Agents (LangGraph orchestrated)
   → Uses UQL exclusively (agents construct queries dynamically)
   → Needs: structured responses, provenance metadata

3. TradingView Bridge
   → Receives webhooks, maps symbols, writes alerts
   → Needs: symbol resolution, alert storage

4. Fund Manager (direct API access via tools)
   → Uses UQL for ad-hoc queries ("show me X with Y")
   → Needs: intuitive query syntax, good error messages

5. External Integrations (future)
   → Client portals, reporting systems, compliance tools
   → Needs: API key auth, rate limiting, versioned contracts
```

### 20.4 Pagination Standard

```
All list endpoints support cursor-based pagination:

{
  "data": [ ... ],
  "_meta": {
    "total_count": 2743,
    "returned": 50,
    "offset": 0,
    "limit": 50,
    "has_more": true,
    "next_offset": 50
  }
}

Default limit: 50
Max limit: 500
```

### 20.5 Error Response Standard

All errors follow the structure defined in §16.11:

```json
{
  "error": {
    "code": "INVALID_FILTER",
    "message": "Field 'rs_percentile' does not exist. Did you mean 'rs_composite'?",
    "module": "query_engine",
    "severity": "error",
    "timestamp": "2026-04-10T10:15:00+05:30",
    "suggestion": "Available RS fields: rs_1w, rs_1m, rs_3m, rs_6m, rs_12m, rs_composite"
  }
}
```

Errors must be helpful. "Field not found" is not enough.
"Field 'X' not found. Did you mean 'Y'?" — with suggestions.

---

## 21. EVENT & ALERT SYSTEM

ATLAS is currently pull-based (client requests data). But real intelligence
systems are event-driven — the system TELLS you when something important
happens, without you having to ask.

### 21.1 Event Types

```
RS_CROSS_ZERO         → instrument RS composite crossed 0 (direction change)
QUADRANT_CHANGE       → instrument changed quadrant (e.g., LAGGING → IMPROVING)
SECTOR_ROTATION       → sector changed quadrant
BREADTH_THRESHOLD     → pct_above_200dma crossed a threshold (20%, 50%, 80%)
REGIME_TRANSITION     → market regime changed (BULL → SIDEWAYS, etc.)
HOLDING_LAGGING       → portfolio holding entered LAGGING quadrant
CONVICTION_SPIKE      → instrument conviction assessment changed significantly
RS_MOMENTUM_EXTREME   → rs_momentum in top/bottom 5% (fast movers)
VOLUME_ANOMALY        → volume > 5x 20-day average
PRICE_ANOMALY         → price change > 10% in one day
MF_FLOW_REVERSAL      → category flows switched from positive to negative (or vice versa)
GOLDILOCKS_NEW_IDEA   → new stock appeared in Goldilocks Stock Bullet/Big Catch
TV_ALERT              → TradingView webhook alert received
SIMULATION_DRIFT      → auto-loop simulation shows performance deviation
AGENT_MUTATION        → agent underwent Darwinian mutation (accepted or reverted)
DATA_STALE            → critical data source is overdue for refresh
```

### 21.2 Event Schema

```json
{
  "event_id": "evt_2026041009150001",
  "event_type": "QUADRANT_CHANGE",
  "entity": "HDFCBANK",
  "entity_type": "equity",
  "trigger": {
    "field": "quadrant",
    "from": "IMPROVING",
    "to": "LEADING",
    "rs_composite": 4.53,
    "rs_momentum": 1.62
  },
  "timestamp": "2026-04-10T09:15:00+05:30",
  "data_as_of": "2026-04-09",
  "severity": "medium",
  "context": "Banking sector also in LEADING. Breadth support at 62%.",
  "suggested_action": "Review position. Check conviction pillars.",
  "related_events": ["evt_2026040818300045"]
}
```

### 21.3 Event Generation

Events are generated by the nightly pipeline and stored in atlas_alerts:

```
Pipeline runs (18:30 IST)
    │
    ▼
rs-analyzer computes new RS + quadrants
    │
    ├─ Compare today's quadrants with yesterday's → QUADRANT_CHANGE events
    ├─ Compare today's RS with zero crossing → RS_CROSS_ZERO events
    ├─ Check RS momentum extremes → RS_MOMENTUM_EXTREME events
    │
    ▼
sector-analyst computes sector rollups
    │
    ├─ Compare today's sector quadrants with yesterday's → SECTOR_ROTATION events
    │
    ▼
breadth check
    │
    ├─ Compare pct_above_200dma with thresholds → BREADTH_THRESHOLD events
    │
    ▼
regime check
    │
    ├─ Compare today's regime with yesterday's → REGIME_TRANSITION events
    │
    ▼
portfolio check (for each saved portfolio)
    │
    ├─ Check each holding's quadrant → HOLDING_LAGGING events
    │
    ▼
All events written to atlas_alerts table
```

### 21.4 Event Delivery

```
PHASE 1 (now):
  • Stored in atlas_alerts table
  • Available via GET /api/v1/alerts
  • Shown in Alert Center page across all three shells
  • Included in intelligence engine context for agents

PHASE 2 (future):
  • WebSocket push to connected frontends
  • Email digest (daily summary of events)
  • WhatsApp integration (critical events only)
  • Telegram bot (like PKScreener's pattern)

PHASE 3 (future):
  • Webhook push to external systems
  • Slack integration for team alerts
```

### 21.5 Event Priority

```
CRITICAL → immediate attention required:
  REGIME_TRANSITION, DATA_STALE, PRICE_ANOMALY (>20%)

HIGH → action within today:
  BREADTH_THRESHOLD (<20% or >80%), HOLDING_LAGGING (>4 weeks),
  SIMULATION_DRIFT (>5% deviation)

MEDIUM → informational, review when convenient:
  QUADRANT_CHANGE, SECTOR_ROTATION, RS_CROSS_ZERO, TV_ALERT

LOW → background awareness:
  CONVICTION_SPIKE, MF_FLOW_REVERSAL, GOLDILOCKS_NEW_IDEA,
  VOLUME_ANOMALY, AGENT_MUTATION
```

---

## 22. QUERY GOVERNANCE & EXECUTION ENGINE

The Unified Query Layer (§17) must NOT directly execute user-defined queries
against the database. Every query passes through a governance pipeline that
validates, estimates cost, enforces limits, and only then executes.

### 22.1 Query Compiler Layer

```
All queries go through a 5-stage compiler:

POST /api/v1/query
    │
    ▼
STAGE 1: PARSE & VALIDATE
    • Validate JSON against query schema
    • Verify all requested fields exist for the entity_type
    • Verify all filter operators are valid for field types
    • Reject unknown fields with helpful suggestion
    │
    ▼
STAGE 2: WHITELIST CHECK
    • Verify fields are in the approved field list for this entity_type
    • Verify joins are in the approved join list
    • Verify aggregation functions are in the approved list
    • Reject any query that would require unapproved table access
    │
    ▼
STAGE 3: SQL GENERATION
    • Translate validated query → parameterized SQL
    • Inject appropriate indexes (force index hints where needed)
    • Add date range filters automatically for partitioned tables
    • Prevent full table scans (reject if no indexed filter present)
    • Generate EXPLAIN plan
    │
    ▼
STAGE 4: COST ESTIMATION
    • Run EXPLAIN (not EXPLAIN ANALYZE — no actual execution)
    • Estimate: rows to scan, cost units, expected time
    • If estimated_rows > 100,000 → force pagination
    • If estimated_cost > threshold → reject with suggestion to narrow filters
    • Return cost estimate in response _meta
    │
    ▼
STAGE 5: EXECUTE
    • Run parameterized SQL with timeout (2 seconds hard kill)
    • Cache result (keyed by query hash + data_as_of)
    • Log query execution metrics
```

### 22.2 Query Whitelisting

```
APPROVED FIELDS PER ENTITY TYPE:

equity:
  Filterable:  symbol, sector, industry, cap_category, nifty_50, nifty_200, nifty_500,
               is_active, rs_composite, rs_momentum, rs_1w, rs_1m, rs_3m, rs_6m, rs_12m,
               quadrant, rsi_14, adx_14, macd_histogram, above_200dma, above_50dma,
               mfi_14, relative_volume, beta_nifty, sharpe_1y, sortino_1y,
               max_drawdown_1y, volatility_20d, mf_holder_count, close, volume
  Sortable:    all filterable fields
  Aggregatable: all numeric filterable fields

mf:
  Filterable:  mstar_id, fund_name, amc_name, category_name, broad_category,
               is_index_fund, is_etf, is_active, rs_composite, rs_momentum, quadrant,
               derived_rs_composite, nav_rs_composite, manager_alpha,
               sharpe_1y, sortino_1y, max_drawdown_1y, beta_vs_nifty,
               information_ratio, treynor_ratio
  Sortable:    all filterable fields
  Aggregatable: all numeric filterable fields

sector:
  Filterable:  sector, stock_count, avg_rs_composite, avg_rs_momentum,
               pct_above_200dma, pct_above_50dma, avg_rsi_14, avg_adx,
               pct_adx_trending, pct_macd_bullish
  (sector queries always go through precomputed rollups, never raw table scans)

APPROVED JOINS:
  equity:  de_instrument ↔ de_equity_technical_daily (on instrument_id + date)
           de_instrument ↔ de_rs_scores (on id = entity_id + date)
           de_instrument ↔ de_market_cap_history (on instrument_id + effective_to IS NULL)
  mf:      de_mf_master ↔ de_rs_scores (on mstar_id = entity_id + date)
           de_mf_master ↔ de_mf_derived_daily (on mstar_id + nav_date)

NO UNAPPROVED JOINS. If a query requires a join not listed here,
it must be added to the whitelist through a code change, not at runtime.
```

### 22.3 Cost Estimation Response

```json
{
  "data": [ ... results ... ],
  "_meta": {
    "query_cost": {
      "estimated_rows_scanned": 8200,
      "actual_rows_returned": 41,
      "execution_time_ms": 142,
      "cache_hit": false,
      "index_used": "idx_rs_scores_entity_type_date"
    }
  }
}
```

### 22.4 Rate Limiting

```
Per user per minute:
  Pro:     60 queries/minute, max 10 heavy (aggregation/timeseries)
  Advisor: 30 queries/minute, max 5 heavy
  Retail:  10 queries/minute, max 2 heavy

Heavy query = any query with:
  aggregation, timeseries mode, or limit > 100

Exceeding rate limit → 429 Too Many Requests with Retry-After header
```

### 22.5 Query Caching

```
Cache key: SHA256(query_json + data_as_of)

Cache TTL by data layer:
  Snapshot queries (latest universe): 5 minutes
  Aggregation queries (sector rollups): 5 minutes
  Timeseries queries: 30 minutes (data doesn't change intra-day)
  Near real-time (TV data): 15 minutes

Identical queries within TTL → return cached response with _meta.cache_hit=true
Cache invalidation: automatic on new pipeline run (data_as_of changes)
```

### 22.6 Query Logging

```sql
CREATE TABLE atlas_query_log (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(100),
    user_role VARCHAR(20),              -- 'pro', 'advisor', 'retail'
    query_hash VARCHAR(64),             -- SHA256 of query JSON
    query_json JSONB NOT NULL,
    entity_type VARCHAR(20),
    execution_time_ms INTEGER,
    rows_scanned INTEGER,
    rows_returned INTEGER,
    cache_hit BOOLEAN,
    success BOOLEAN,
    error_code VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_query_log_user ON atlas_query_log(user_id, created_at DESC);
CREATE INDEX idx_query_log_slow ON atlas_query_log(execution_time_ms DESC)
    WHERE execution_time_ms > 500;
```

Every query logged. Slow queries (>500ms) flagged for optimization review.
Query patterns analyzed weekly to identify candidates for materialized views
or index additions.

---

## 23. DECISION LIFECYCLE SYSTEM

Every decision generated by ATLAS must be tracked from creation through
outcome. Without this, the system generates insights but never learns
whether they were right. This is the feedback loop that makes the
intelligence engine genuinely intelligent.

### 23.1 Decision Table

```sql
CREATE TABLE atlas_decisions (
    id BIGSERIAL PRIMARY KEY,
    
    -- What
    entity TEXT NOT NULL,                -- 'HDFCBANK', 'Banking', 'PPFAS Flexi Cap'
    entity_type VARCHAR(20) NOT NULL,    -- 'equity', 'sector', 'mf', 'etf'
    decision_type VARCHAR(30) NOT NULL,  -- 'buy_signal', 'sell_signal', 'rotation',
                                         --  'rebalance', 'avoid', 'overweight'
    
    -- Why
    rationale TEXT NOT NULL,             -- structured explanation
    supporting_data JSONB NOT NULL,      -- { rs_composite, rsi_14, quadrant, ... }
    confidence NUMERIC(5,4) NOT NULL,    -- 0.0000 to 0.9500
    source_agent VARCHAR(100),           -- which agent generated this
    
    -- When
    horizon VARCHAR(20) NOT NULL,        -- '5_days', '20_days', '60_days'
    horizon_end_date DATE NOT NULL,      -- explicit date when to evaluate
    invalidation_conditions TEXT[],      -- ["rs_momentum < 0", "regime = BEAR"]
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active',
      -- 'active' → still within horizon, not invalidated
      -- 'invalidated' → conditions met before horizon end
      -- 'expired' → horizon passed, awaiting outcome evaluation
      -- 'evaluated' → outcome recorded
    
    invalidated_at TIMESTAMPTZ,
    invalidation_reason TEXT,
    
    -- Outcome (filled after horizon)
    outcome JSONB,
    -- {
    --   "entity_return": 4.2,
    --   "benchmark_return": 1.8,
    --   "excess_return": 2.4,
    --   "max_drawdown": -3.1,
    --   "hit_target": true,
    --   "success": true
    -- }
    
    -- User interaction
    user_action VARCHAR(20),             -- 'accepted', 'ignored', 'overridden'
    user_action_at TIMESTAMPTZ,
    user_notes TEXT,
    
    -- Metadata
    data_as_of DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_decisions_entity ON atlas_decisions(entity, entity_type);
CREATE INDEX idx_decisions_status ON atlas_decisions(status);
CREATE INDEX idx_decisions_horizon ON atlas_decisions(horizon_end_date)
    WHERE status IN ('active', 'expired');
CREATE INDEX idx_decisions_agent ON atlas_decisions(source_agent);
```

### 23.2 Decision Generation

```
Decisions are generated by agents during the nightly pipeline:

rs-analyzer:
  "HDFCBANK entered LEADING quadrant"
  → decision_type: "buy_signal", horizon: "20_days"
  → invalidation: ["quadrant != LEADING"]

sector-analyst:
  "Banking sector rotating from IMPROVING to LEADING"
  → decision_type: "overweight", horizon: "20_days"
  → invalidation: ["sector rs_momentum < 0"]

regime-analyst:
  "Market transitioning to BEAR with 65% probability"
  → decision_type: "reduce_equity", horizon: "60_days"
  → invalidation: ["regime = BULL", "breadth_score > 60"]

briefing-writer:
  "IT sector vulnerable — deal pipeline weakness + RS LAGGING"
  → decision_type: "avoid", horizon: "20_days"
  → invalidation: ["IT sector rs_composite > 0"]
```

### 23.3 Outcome Tracking

```
Daily check by accuracy-tracker agent:

FOR EACH decision WHERE status = 'active':
  1. Check invalidation conditions against current data
     → If any condition met: status = 'invalidated', log reason

  2. Check if horizon_end_date reached
     → If reached: status = 'expired'

FOR EACH decision WHERE status = 'expired':
  1. Compute outcome:
     entity_return = entity price change from decision date to horizon_end_date
     benchmark_return = benchmark change over same period
     excess_return = entity_return - benchmark_return
     max_drawdown = worst peak-to-trough during the period
     success = (decision_type in ['buy_signal', 'overweight'] AND excess_return > 0)
               OR (decision_type in ['sell_signal', 'avoid'] AND excess_return < 0)

  2. Store outcome in JSONB
  3. Set status = 'evaluated'
  4. Feed into agent scoring (§7 Darwinian evolution):
     → successful decision adds to agent's rolling accuracy
     → failed decision reduces agent's rolling accuracy
```

### 23.4 Feedback Loop

```
DECISIONS → OUTCOMES → AGENT SCORING → AGENT EVOLUTION → BETTER DECISIONS

Concretely:
  1. sector-analyst generates 5 rotation decisions this week
  2. After 20 days, 3 were correct, 2 were wrong
  3. Accuracy: 60% → feeds into sector-analyst rolling_accuracy
  4. If rolling_accuracy drops below bottom quartile:
     → Darwinian weight decreases
     → If weight < 0.5: trigger mutation cycle
     → Mutation: analyze the 2 wrong decisions, identify error pattern
     → Modify AGENT.md to address the pattern
     → Test modified agent for 5 days
     → Keep or revert

  5. Intelligence engine receives:
     "sector-analyst's rotation calls have 60% accuracy over last month.
      Errors concentrated in IT and Pharma sectors (false positives:
      called rotation that didn't sustain beyond 1 week)."

  6. Next time sector-analyst runs, it reads this finding and adjusts:
     "Historical note: my IT/Pharma rotation calls have been unreliable.
      Apply higher confirmation threshold for these sectors (require
      breadth > 60% AND adx > 25 before calling rotation)."
```

### 23.5 User Interaction

```
When a decision is shown to the fund manager, they can:

  ACCEPT → user_action = 'accepted'
    "I agree with this call, I'm acting on it"
    System tracks: accepted decisions have higher weight in future learning

  IGNORE → user_action = 'ignored'
    "Noted but not acting"
    System tracks: ignored decisions still evaluated for accuracy

  OVERRIDE → user_action = 'overridden', user_notes = "..."
    "I disagree because..."
    FM's reasoning stored as qualitative finding in intelligence engine
    System tracks: if FM was right and system was wrong → valuable correction

All user actions logged with timestamp. This becomes training data for
learning the FM's decision-making patterns (§6 intelligence engine:
Portfolio Intelligence → "FM always adds on RS dips, not breakouts").
```

---

## 24. VERTICAL SLICE — V1 DELIVERY UNIT

Development must proceed in vertical slices, NOT horizontal modules.
A vertical slice is a thin, end-to-end working path through the entire stack
— from data to API to frontend to decision — that a user can actually USE.

Building horizontally (all data layer, then all intelligence, then all frontend)
creates 10 half-systems. Building vertically creates 1 working system that
grows wider over time.

### 24.1 First Vertical Slice (V1 — MANDATORY before anything else)

```
SCOPE: Market → Sector → Stock → Decision

This is the MINIMUM viable ATLAS.
A fund manager can:
  1. Open ATLAS
  2. See market regime + breadth (are we in BULL/BEAR/SIDEWAYS?)
  3. See sector RS rankings (which sectors are leading/lagging?)
  4. Drill into a sector → see stocks ranked by RS
  5. Click a stock → see deep-dive with conviction pillars
  6. See a decision object: "HDFCBANK: BUY signal, LEADING quadrant,
     8/10 technicals passing, confidence 0.78, horizon 20 days"
  7. Accept, ignore, or override the decision
```

### 24.2 V1 Scope — Exactly What's Included

```
DATA:
  ✓ JIP /internal/equity/universe endpoint
  ✓ JIP /internal/sectors/universe endpoint
  ✓ JIP /internal/market/breadth endpoint
  ✓ JIP /internal/market/regime endpoint
  ✓ ATLAS JIP client (schema translation)

COMPUTATION:
  ✓ RS momentum (rs_composite today - 28 days ago)
  ✓ Quadrant classification (LEADING/IMPROVING/WEAKENING/LAGGING)
  ✓ Sector rollups (22 metrics per sector)
  ✓ MF holder count per stock

INTELLIGENCE:
  ✓ pgvector table created and operational
  ✓ Findings written by sector-analyst and rs-analyzer
  ✓ Findings queryable via API

AGENTS:
  ✓ rs-analyzer (compute RS momentum + quadrants)
  ✓ sector-analyst (sector rollups + rotation detection)
  ✓ Basic conviction assessment (Pillar 1: RS + Pillar 2: technicals)
  ✗ NO briefing-writer (no LLM narrative yet)
  ✗ NO investor personality agents (no debate yet)
  ✗ NO Darwinian evolution (scores tracked but no mutation yet)

DECISIONS:
  ✓ atlas_decisions table operational
  ✓ Decisions generated for quadrant changes and rotation signals
  ✓ User can accept/ignore/override
  ✗ NO outcome tracking yet (requires 20+ days of data)

API:
  ✓ GET /api/v1/stocks/universe (hierarchical: sectors → stocks)
  ✓ GET /api/v1/stocks/sectors (22 metrics)
  ✓ GET /api/v1/stocks/{symbol} (deep-dive with conviction)
  ✓ GET /api/v1/stocks/breadth
  ✓ POST /api/v1/query (UQL — basic, equity entity_type only)
  ✓ GET /api/v1/status
  ✗ NO /api/v1/mf/* (V2)
  ✗ NO /api/v1/etf/* (V2)
  ✗ NO /api/v1/simulate/* (V2)
  ✗ NO /api/v1/portfolio/* (V2)

FRONTEND:
  ✓ Pro shell only (one shell, not three)
  ✓ Market overview (regime + breadth summary)
  ✓ Sector RS ranking table (sortable, 22 columns)
  ✓ Stock drill-down table (sector → stocks, expandable)
  ✓ Stock deep-dive panel (conviction pillars, RS chart, technicals)
  ✓ Decision display (accept/ignore/override)
  ✗ NO bubble chart (V2 — table is sufficient for V1)
  ✗ NO TradingView charts (V2 — basic RS line chart only)
  ✗ NO simulation page (V2)
  ✗ NO portfolio page (V2)
  ✗ NO MF/ETF pages (V2)
  ✗ NO Advisor or Retail shells (V2/V3)
```

### 24.3 V1 Completion Criteria

```
V1 is DONE when ALL of the following are true:

  □ API stable: /stocks/universe returns valid data matching contract
  □ API stable: /stocks/sectors returns 31 sectors with 22 metrics each
  □ API stable: /stocks/{symbol} returns deep-dive data for any stock
  □ API stable: /query handles basic equity queries with filters + sort
  □ Frontend usable: FM can navigate Market → Sector → Stock flow
  □ Frontend usable: Deep-dive panel shows all conviction pillar data
  □ Decisions generated: at least 5 decisions per pipeline run
  □ Decisions actionable: FM can accept/ignore/override
  □ Data correct: sector rollup stock_count sums to ~2,700
  □ Data correct: RS momentum matches manual calculation
  □ Data correct: pct_above_200dma matches raw SQL verification
  □ Intelligence engine: ≥10 findings stored after first pipeline run
  □ Integration tests: ALL passing
  □ No float in any financial calculation
  □ Response times: universe < 2s, deep-dive < 500ms
```

### 24.4 Vertical Slices After V1

```
V2: MF SLICE
  Add: /api/v1/mf/* endpoints
  Add: MF category → fund → holdings drill-down
  Add: MF deep-dive (NAV-RS, derived-RS, manager alpha, weighted technicals)
  Add: MF page in Pro shell
  Add: MF decisions (fund quadrant changes, category flow reversals)

V3: SIMULATION SLICE
  Add: VectorBT simulation engine
  Add: Signal adapters (breadth, RS, PE, regime)
  Add: Indian FIFO tax engine
  Add: QuantStats tear sheets
  Add: /api/v1/simulate/* endpoints
  Add: Simulation page in Pro shell
  Add: Auto-loop scheduler

V4: PORTFOLIO SLICE
  Add: casparser CAMS import
  Add: Portfolio analysis engine
  Add: Riskfolio-Lib optimization
  Add: Brinson attribution
  Add: /api/v1/portfolio/* endpoints
  Add: Portfolio page in Pro shell

V5: INTELLIGENCE SLICE
  Add: Briefing writer (TradingAgents debate fork)
  Add: Investor personality agents (ai-hedge-fund fork)
  Add: Darwinian evolution engine
  Add: Goldilocks integration
  Add: Decision outcome tracking + feedback loop
  Add: Global Intelligence page

V6: TRADINGVIEW SLICE
  Add: TV MCP bridge
  Add: TV webhook handler
  Add: TV chart embedding (lightweight-charts)
  Add: Bidirectional portfolio ↔ watchlist sync
  Add: TV TA in conviction pillar 3

V7: ETF + GLOBAL SLICE
  Add: ETF universe + deep-dive
  Add: Global instruments + macro ratios
  Add: ETF page in Pro shell

V8: ADVISOR SHELL
  Add: Client management
  Add: Fund discovery workflow
  Add: Model portfolios
  Add: Report generator
  Add: /advisor/* routes

V9: RETAIL SHELL
  Add: Simplified fund discovery
  Add: Portfolio tracker
  Add: Goal planner
  Add: /retail/* routes

V10: QLIB + ADVANCED
  Add: Qlib Alpha158 pipeline
  Add: ML model training
  Add: Factor validation (alphalens)
  Add: Parameter optimization (Optuna)
  Add: Event system (WebSocket push)
```

### 24.5 Build Instruction for Claude

```
CRITICAL: When building ATLAS autonomously, follow this exact sequence:

1. BUILD V1 FIRST. Complete V1 before starting ANY V2+ work.
2. V1 must pass ALL completion criteria in §24.3 before proceeding.
3. After V1 is complete and verified, proceed to V2, then V3, etc.
4. Each vertical slice must be independently deployable and testable.
5. Never start a new slice until the current slice passes its completion criteria.

This is the single most important build discipline in this document.
Violating this order is a HARD STOP condition.
```

---

## 25. TECHNOLOGY STACK — COMPLETE

### Python Backend

```
# Core
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
pydantic>=2.10.0
sqlalchemy>=2.0.36
asyncpg>=0.30.0
alembic>=1.14.0
httpx>=0.28.0
redis[hiredis]>=5.2.0         # caching layer (see §16.10)

# Intelligence Engine
pgvector>=0.3.6
openai>=1.60.0               # for embeddings (text-embedding-3-small)

# Agent Framework
langgraph>=0.2.60
langchain-anthropic>=0.3.0
langchain-openai>=0.3.0

# Simulation
vectorbt>=0.28.0
optuna>=4.1.0
quantstats>=0.0.81

# Portfolio
riskfolio-lib>=6.4.0
casparser>=0.8.0

# Factor Analysis
alphalens-reloaded>=0.4.5
qlib>=0.9.6

# Technical Indicators
pandas-ta>=0.3.14

# Financial Metrics
empyrical-reloaded>=0.5.10

# ML/Statistics
scikit-learn>=1.6.0
hmmlearn>=0.3.3              # regime detection
arch>=7.2.0                  # GARCH volatility

# NLP
finbert                       # financial sentiment (via transformers)
openai-whisper               # voice note transcription

# Data
yfinance>=0.2.50
jugaad-data>=0.3.0
mftool>=3.2.0

# Utilities
structlog>=24.4.0
python-multipart>=0.0.18
python-jose[cryptography]    # JWT
```

### Node.js (TradingView Bridge + Build Dashboard)

```
tradingview-mcp-server
tradingview-screener
```

### Frontend (Next.js, in fie2 repo)

```
next@16
react@19
typescript@5
tailwindcss@4
@radix-ui/* (via shadcn/ui)
recharts@2.15
swr@2.4
lightweight-charts@5.1
lucide-react
```

---

## 26. APPENDICES

### Appendix A: ATLAS-Owned Database Tables

```sql
-- Briefings (LLM-generated morning notes)
CREATE TABLE atlas_briefings (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    scope VARCHAR(20) NOT NULL,
    scope_key VARCHAR(50),
    headline TEXT NOT NULL,
    narrative TEXT NOT NULL,
    key_signals JSONB DEFAULT '[]',
    theses JSONB DEFAULT '[]',
    patterns JSONB DEFAULT '[]',
    india_implication TEXT,
    risk_scenario TEXT,
    conviction VARCHAR(10),
    model_used VARCHAR(50),
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(date, scope, COALESCE(scope_key, '__null__'))
);

-- Simulations (saved backtest configs + results)
CREATE TABLE atlas_simulations (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200),
    config JSONB NOT NULL,
    result_summary JSONB,
    daily_values JSONB,
    transactions JSONB,
    tax_summary JSONB,
    tear_sheet_html TEXT,
    is_auto_loop BOOLEAN DEFAULT FALSE,
    auto_loop_cron VARCHAR(50),
    last_auto_run TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    user_id VARCHAR(50)
);

-- Watchlists
CREATE TABLE atlas_watchlists (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    instruments JSONB DEFAULT '[]',
    tv_synced BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Alerts (unified: TV + ATLAS-generated)
CREATE TABLE atlas_alerts (
    id BIGSERIAL PRIMARY KEY,
    source VARCHAR(20) NOT NULL,
    symbol VARCHAR(50),
    instrument_id UUID,
    alert_type VARCHAR(50),
    message TEXT,
    metadata JSONB DEFAULT '{}',
    rs_at_alert NUMERIC,
    quadrant_at_alert VARCHAR(20),
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Intelligence Engine (see §6 for full schema)
-- atlas_intelligence table with pgvector

-- TV Cache (see §10)
-- atlas_tv_cache table

-- Agent Scores
CREATE TABLE atlas_agent_scores (
    id BIGSERIAL PRIMARY KEY,
    agent_id VARCHAR(100) NOT NULL,
    prediction_date DATE NOT NULL,
    entity TEXT,
    prediction TEXT NOT NULL,
    evaluation_date DATE,
    actual_outcome TEXT,
    accuracy_score NUMERIC(5,4),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agent Weights (Darwinian)
CREATE TABLE atlas_agent_weights (
    agent_id VARCHAR(100) PRIMARY KEY,
    weight NUMERIC(5,4) NOT NULL DEFAULT 1.0,
    rolling_accuracy NUMERIC(5,4),
    mutation_count INTEGER DEFAULT 0,
    last_mutation_date DATE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agent Memory (per-agent corrections and learnings)
CREATE TABLE atlas_agent_memory (
    id BIGSERIAL PRIMARY KEY,
    agent_id VARCHAR(100) NOT NULL,
    memory_type VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Portfolios
CREATE TABLE atlas_portfolios (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200),
    portfolio_type VARCHAR(20),          -- 'cams_import', 'manual', 'model'
    owner_type VARCHAR(20),              -- 'pms', 'ria_client', 'retail'
    holdings JSONB NOT NULL,
    analysis_cache JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Qlib Features (daily alpha factors per stock)
CREATE TABLE atlas_qlib_features (
    date DATE NOT NULL,
    instrument_id UUID NOT NULL,
    features JSONB NOT NULL,             -- {KMID: 0.002, KLEN: 0.015, ...}
    PRIMARY KEY (date, instrument_id)
);

-- Qlib Signals (ML model predictions, Phase 2+)
CREATE TABLE atlas_qlib_signals (
    date DATE NOT NULL,
    instrument_id UUID NOT NULL,
    model_name VARCHAR(50) NOT NULL,
    signal_score NUMERIC,
    signal_rank INTEGER,
    features_used JSONB,
    PRIMARY KEY (date, instrument_id, model_name)
);
```

### Appendix B: Schema Corrections vs Spec v2

| What | Spec v2 says | Actual DB |
|------|-------------|-----------|
| Stock primary key | `instrument_id INTEGER` | `id UUID` |
| Stock symbol column | `symbol` | `current_symbol` |
| Stock name column | `name` | `company_name` |
| Market cap | Column on `de_instrument` | Separate `de_market_cap_history`, column `cap_category` |
| RS score columns | `rs_percentile`, `rs_score` | `rs_1w, rs_1m, rs_3m, rs_6m, rs_12m, rs_composite` |
| RS entity reference | `instrument_id` | `entity_id` |
| RS benchmark column | `benchmark` | `vs_benchmark` |
| MF primary key | `fund_code` | `mstar_id` |
| MF category column | `category` | `category_name` |
| MF fund house | `fund_house` | `amc_name` |
| MF NAV date column | `date` | `nav_date` |
| MF derived key | `fund_code` | `mstar_id` |
| Index master key | `index_name` | `index_code` + `index_name` |
| Index prices key | `index_name` | `index_code` |
| Breadth columns | `advances, declines` | `advance, decline` (singular) |
| Regime composite | `composite_score` | `confidence` |
| Regime sub-scores | `trend_score, volatility_score` | `momentum_score, global_score, fii_score` |
| Technical beta | `beta` (vs N500) | `beta_nifty` (vs N50) |

### Appendix C: Open-Source Dependencies Inventory

| Category | Tool | Stars | What We Use It For |
|----------|------|-------|-------------------|
| Agent Orchestration | LangGraph | 90K | Multi-agent workflow orchestration |
| Agent Base | ai-hedge-fund (virattt) | 50K | Fork: investor agents, risk manager, portfolio manager |
| Agent Debate | TradingAgents (TauricResearch) | 3K | Port: bull/bear debate, memory recall, vendor routing |
| Simulation | VectorBT | 7K | Vectorized backtesting, parameter sweeps |
| Optimization | Optuna | 11K | TPE parameter search |
| Portfolio Opt | Riskfolio-Lib | 4K | SEBI-compatible portfolio optimization |
| Tear Sheets | QuantStats | 7K | 60+ metrics, HTML reports |
| Risk Metrics | empyrical-reloaded | 500 | Individual risk/return metrics |
| Factor Analysis | alphalens-reloaded | 1K | RS factor validation |
| ML/Alpha | Microsoft Qlib | 41K | 158 alpha factors, model zoo |
| TA Indicators | pandas-ta | 6K | 210+ technical indicators |
| CAMS Parser | casparser | 193 | Indian CAS PDF parsing |
| MF Data | mftool | 220 | AMFI NAV data |
| Indian Data | jugaad-data | 500 | NSE/BSE data |
| Sentiment | FinBERT | 3K | Financial text sentiment |
| Vector Store | pgvector | 13K | Intelligence engine |
| Regime Detection | hmmlearn | 3K | HMM-based regime detection |
| Volatility | arch | 2K | GARCH models |
| Report Gen | FinRobot | 7K | Reference: sector analyst templates |
| RRG Charts | RRG-Lite | low | RRG visualization with Nifty 50 |
| Charts | lightweight-charts | 3K | TradingView-style candlestick |

### Appendix D: Existing Repos & Deployment

```
MarketPulse (fie2): github.com/nimishshah1989/fie2
  Next.js 16, deployed at /home/ubuntu/apps/marketpulse/ on EC2 #1
  ATLAS frontend goes INTO this repo as /atlas/* routes

JIP Data Core: /Users/nimishshah/projects/jip data core/
  FastAPI + SQLAlchemy, /internal/ API endpoints added here
  Deployed via Docker on EC2 #1

Global Pulse: /Users/nimishshah/projects/global-pulse/
  React + Vite, reference for drill-down patterns
  NOT deployed at marketpulse.jslwealth.in

ATLAS: /Users/nimishshah/projects/atlas/ (this project)
  Backend + agents + simulation → NEW repo, deployed on EC2 #2
```

---

*This document is the single source of truth for building ATLAS.
It is fed to Claude Code CLI running autonomously on the ATLAS EC2 server.
Every detail needed to build the complete system is here.
Start with Phase 0, Chunk 0.1.*
