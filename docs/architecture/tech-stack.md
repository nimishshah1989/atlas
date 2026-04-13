# ATLAS Tech Stack — fork / pip-install / build-in-house

> Moved out of `CLAUDE.md` in chunk S4. The rulebook points here; this file
> is the source of truth for "where does capability X come from".

## Fork & adapt (overlay our JIP data)

- **ai-hedge-fund** (virattt, 50K stars) — investor personality agents, risk
  manager, portfolio manager. Swap `src/tools/api.py` with the JIP client.
- **TradingAgents** (TauricResearch, 3K stars) — bull/bear debate, memory
  recall, vendor routing. Port debate + memory into our system.
- **FinRobot** (AI4Finance, 7K stars) — sector analyst templates, report
  generation pipeline.

## Pip install (battle-tested, no custom code)

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

## Build in-house (our moat)

- JIP `/internal/` API service layer
- Central intelligence engine (pgvector orchestration)
- Darwinian evolution framework (scoring, weights, mutation, spawning)
- Indian FIFO tax engine (pre/post July 2024, STCG/LTCG, cess)
- UQL query engine (Bloomberg-grade unified query layer)
- Decision lifecycle system (creation → outcome tracking)
- Event system (16 event types, priority classification)
- TV bidirectional sync
- Indian market contextualization (SEBI, NSE sectors, lakh/crore)
- Three experience shells (Pro, Advisor, Retail)

## Rule of thumb

If a 10k+ star repo does 80% of what you need, **fork it** and swap the data
layer. Don't rewrite library code — rewrite your integration glue.
