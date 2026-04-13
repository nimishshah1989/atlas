# ATLAS Architecture

This document is the visual companion to [`ATLAS-DEFINITIVE-SPEC.md`](../ATLAS-DEFINITIVE-SPEC.md)
and [`CLAUDE.md`](../CLAUDE.md). It captures the deployment topology, request
flow, and data ownership boundaries as Mermaid diagrams.

---

## 1. Service topology

ATLAS runs on its own EC2 host inside the same VPC as the JIP Data Core, so
internal API calls are sub-millisecond. ATLAS never touches `de_*` tables
directly — JIP owns the warehouse, ATLAS owns `atlas_*`.

```mermaid
graph LR
    subgraph VPC[AWS VPC ap-south-1]
        subgraph JIP[EC2 #1 — JIP Data Engine]
            JIPAPI[JIP Data Core FastAPI :8000<br/>/internal/* API]
        end
        subgraph ATLAS[EC2 #2 — ATLAS]
            BE[ATLAS FastAPI :8010<br/>routes → core → clients]
            FE[Next.js Frontend :3000<br/>Pro / Advisor / Retail]
            DASH[Build Dashboard :3001<br/>atlas.jslwealth.in/forge]
        end
        subgraph Data[RDS PostgreSQL + pgvector]
            DE[(de_* tables<br/>JIP-owned, read-only)]
            AT[(atlas_* tables<br/>ATLAS-owned)]
        end
        subgraph Side[Sidecars]
            TV[TradingView MCP<br/>TA + 13K screening fields]
        end
    end
    User[FM / Advisor / Retail user] -->|HTTPS| FE
    FE -->|REST| BE
    BE -->|HTTP /internal/*| JIPAPI
    BE -->|asyncpg| AT
    BE -->|MCP| TV
    JIPAPI -->|asyncpg| DE
    JIPAPI -->|asyncpg| AT
```

---

## 2. Request flow — Market → Sector → Stock → Decision (V1)

```mermaid
sequenceDiagram
    autonumber
    participant U as Fund Manager
    participant FE as Next.js
    participant API as ATLAS API :8010
    participant CORE as core/decision_engine
    participant JIP as JIP /internal/
    participant ATDB as atlas_* DB

    U->>FE: Open Pro shell
    FE->>API: GET /api/v1/stocks/sectors
    API->>JIP: GET /internal/equity/universe
    JIP-->>API: 2,743 stocks + RS + technicals
    API->>CORE: rollup_sectors(universe)
    CORE-->>API: 31 sectors × 22 metrics
    API-->>FE: SectorRollupResponse
    U->>FE: Drill into SECTOR
    FE->>API: GET /api/v1/stocks/{symbol}
    API->>JIP: deep-dive joins
    API->>CORE: assess_conviction(stock)
    CORE-->>API: 4 pillars (RS, TA, ext, inst)
    API-->>FE: StockDeepDive
    U->>FE: Accept decision
    FE->>API: POST /api/v1/decisions
    API->>ATDB: INSERT atlas_decisions
    ATDB-->>API: decision_id
    API-->>FE: Decision created
```

---

## 3. Data ownership boundary

```mermaid
flowchart TB
    subgraph Read[READ-ONLY for ATLAS — JIP owns]
        DE1[de_instrument]
        DE2[de_market_cap_history]
        DE3[de_relative_strength]
        DE4[de_mf_funds / de_mf_nav]
        DE5[de_breadth / de_regime]
        DE6[de_macro_indicators]
    end
    subgraph Write[READ + WRITE — ATLAS owns]
        A1[atlas_intelligence pgvector]
        A2[atlas_briefings]
        A3[atlas_decisions]
        A4[atlas_simulations]
        A5[atlas_alerts]
        A6[atlas_watchlists]
        A7[atlas_agent_scores / weights / memory]
        A8[atlas_portfolios]
        A9[atlas_tv_cache]
        A10[atlas_qlib_features]
        A11[atlas_query_log]
    end
    JIPAPI[/JIP /internal/ API/] --> Read
    ATLASBE[ATLAS backend] --> JIPAPI
    ATLASBE --> Write
    style Read fill:#fff4e6,stroke:#d97706
    style Write fill:#e6f7ef,stroke:#1d9e75
```

**Hard rule:** any code that imports `de_*` directly into ATLAS is rejected by
the quality gate. All warehouse reads go through `backend/clients/jip_client.py`.

---

## 4. Forge build pipeline

```mermaid
flowchart LR
    PLAN[orchestrator/plan.yaml] --> RUN[runner.py]
    RUN -->|spawn fresh session| WORKER[Claude worker — one chunk]
    WORKER -->|edit + commit| GIT[(git working tree)]
    WORKER -->|FORGE_CHUNK_COMPLETE| RUN
    RUN -->|python .quality/checks.py --gate| GATE{Quality gate}
    GATE -- pass --> POST[scripts/post-chunk.sh]
    GATE -- fail --> RUN
    POST --> COMMIT[residual commit + git push]
    POST --> DEPLOY[restart atlas-backend.service]
    POST --> COMPILE[/forge-compile → wiki/]
    POST --> MEM[update auto-memory MEMORY.md]
    MEM --> NEXT[next chunk]
```

The pipeline enforces the **post-chunk sync invariant**: a chunk is not DONE
until git, EC2, the Forge wiki, and `MEMORY.md` all agree.

---

## 5. Quality gate dimensions

| Dimension     | Weight | Floor | What it measures                                  |
|---------------|--------|-------|---------------------------------------------------|
| security      | 15%    | 80    | secrets, auth, OWASP-style checks                 |
| code          | 20%    | 70    | lint, types, complexity, duplication              |
| architecture  | 20%    | 80    | layering, contract adherence, no `de_*` imports   |
| frontend      | 15%    | 70    | bundle size, a11y, Lighthouse, Playwright         |
| devops        | 15%    | 70    | CI, Dockerfile, migrations, deploy scripts        |
| docs          | 5%     | 75    | README, CLAUDE.md, API docstrings, ADRs           |
| api           | 10%    | —     | contract coverage, endpoint test depth            |

Targets are defined in `orchestrator/plan.yaml` and enforced by
`.quality/checks.py`. See [`.quality/standards.md`](../.quality/standards.md)
for the rubric.

---

## 6. Further reading

- [`ATLAS-DEFINITIVE-SPEC.md`](../ATLAS-DEFINITIVE-SPEC.md) — full 4,200-line spec
- [`CLAUDE.md`](../CLAUDE.md) — operational rules and schema facts
- [`docs/adr/`](./adr/) — architecture decision records
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — contributor workflow
