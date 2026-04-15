# Chunk V5-10: Goldilocks Analyst Agent — Approach

## Data Scale
DB not accessible during research. The de_goldilocks_stock_ideas table is expected
to have O(10-100) rows per day (daily stock recommendations). The de_goldilocks_market_view
and de_goldilocks_sector_view tables are similarly small daily snapshots.
All reads are simple SELECT queries — no aggregation needed.

## Approach

**Pure computation agent** — zero LLM calls. Deterministic cross-validation:
1. Read Goldilocks stock ideas via new JIP client method on JIPDataService facade
2. For each idea, look up RS data via jip.get_stock_detail(symbol)
3. Cross-validate BUY vs RS quadrant: LEADING→aligns, LAGGING→diverges, IMPROVING/WEAKENING→noted
4. Write each finding via store_finding with evidence pointing to both Goldilocks source and RS data
5. Missing ticker: log structlog warning, increment counter, continue (never abort)
6. Write summary finding at end

**Where the code goes:**
- New JIP client methods: `backend/clients/jip_goldilocks_service.py` (clean split following facade-split pattern)
- Wire into facade: `backend/clients/jip_data_service.py`
- Agent: `backend/agents/goldilocks_analyst.py`
- Tests: `tests/agents/test_goldilocks_analyst.py`
- Update docstring: `backend/agents/__init__.py`

## Wiki Patterns Checked
- [Pure Computation Agent](patterns/pure-computation-agent.md) — follows this exactly
- [Facade Split of a God Module](patterns/facade-split-god-module.md) — new goldilocks service module wired into JIPDataService

## Existing Code Reused
- `backend/agents/sector_analyst.py` — exact structural template
- `backend/agents/rs_analyzer.py` — imports Quadrant enum and classify_quadrant
- `backend/services/intelligence.py` — store_finding (already handles JSONB sanitization for Decimal)
- `backend/clients/jip_data_service.py` — facade to wire new methods into
- `backend/clients/jip_equity_service.py` — get_stock_detail pattern to follow for goldilocks SQL

## Edge Cases
- NULL symbol in de_goldilocks_stock_ideas → skip row, log warning
- Missing ticker (get_stock_detail returns None) → log data_gap, count, continue
- NULL rs_composite/rs_momentum in stock detail → treat as LAGGING (cannot classify)
- Empty stock ideas list → write only summary finding
- Naive datetime → raise ValueError (same guard as sector_analyst.py)
- Decimal in evidence dict → store as str (JSONB bug pattern: Decimal breaks JSONB INSERT)
- de_goldilocks tables may not exist on dev → handle TableNotFound gracefully, return []

## Finding Types
- "goldilocks_alignment" — BUY + LEADING quadrant → aligns
- "goldilocks_divergence" — BUY + LAGGING quadrant → DIVERGENT SIGNAL
- "goldilocks_neutral" — BUY + IMPROVING or WEAKENING → cautionary note
- "goldilocks_summary" — run summary

## Confidence
- Decimal("0.85") for alignment/divergence/neutral findings
- Decimal("0.90") for summary

## Expected Runtime on t3.large
Small data (O(10-100) ideas), O(N) JIP calls for get_stock_detail.
Each get_stock_detail is a predicate-pushdown CTE query (STOCK-DETAIL-FAST chunk = ~34ms).
Total runtime: <5 seconds for 100 stocks.
