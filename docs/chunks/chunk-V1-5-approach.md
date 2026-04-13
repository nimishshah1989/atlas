# Chunk V1-5 — Sector Analyst Agent: Approach

## Data scale
No new DB tables created. Reads from de_* via JIPDataService.get_sector_rollups() which
returns ~22-31 sector rows (one per NSE sector). All computation is in-memory on these rows.
Scale: <100 rows — Python dict iteration is fine.

## Chosen approach
Follow exact rs_analyzer.py pattern:
- Import Quadrant + classify_quadrant from rs_analyzer (no duplication)
- Add sector-specific helpers: _get_prior_sector_quadrant, _write_sector_quadrant_finding,
  _write_rotation_finding, _write_breadth_divergence_finding, _write_sector_summary
- run() reads via jip.get_sector_rollups(), iterates, calls store_finding for each sector
- Returns dict[str, int] matching the spec signature

## Wiki patterns checked
- Idempotent Upsert: store_finding handles natural key upsert (agent_id+entity+title+data_as_of)
- Decimal Not Float: _to_decimal() imported from rs_analyzer or re-defined locally
- Coverage-Aware Agent Findings: summary includes analyzed/total counts

## Existing code reused
- backend/agents/rs_analyzer.py: Quadrant, classify_quadrant, _to_decimal, AGENT_TYPE pattern
- backend/services/intelligence.py: store_finding, list_findings
- tests/agents/test_rs_analyzer.py: test structure, mock patterns

## Finding types written
1. `sector_quadrant` — written for every sector (upsert, idempotent)
2. `sector_rotation` — written when current quadrant != prior quadrant (3 in test)
3. `breadth_divergence` — written when RS/breadth signal contradicts (2 in test)
4. `analysis_summary` — one per run, entity="market"

## Breadth divergence logic
- Bullish RS, weak breadth: avg_rs_composite > 0 AND pct_above_200dma < 50
- Bearish RS, strong breadth: avg_rs_composite <= 0 AND pct_above_200dma >= 70

## Prior quadrant lookup
Call list_findings(db, entity=sector_name, agent_id=AGENT_ID, finding_type="sector_quadrant", limit=1)
Extract evidence["quadrant"] to get Quadrant enum.

## Edge cases
- NULL avg_rs_composite or avg_rs_momentum: skip sector, log warning
- NULL pct_above_200dma: skip divergence check for that sector
- No prior history (first run): write sector_quadrant only (no rotation)
- Empty sector list: write only summary

## Expected runtime
<1 second — 31 sectors, pure in-memory, no extra DB queries beyond list_findings per sector.

## Test fixture design
- 31 sectors: 8 LEADING, 7 IMPROVING, 7 WEAKENING, 9 LAGGING
- 3 rotations: sector0 (LEADING→was IMPROVING), sector8 (IMPROVING→was LAGGING), sector15 (WEAKENING→was LEADING)
- 2 divergences: sector1 (LEADING RS but pct_above_200dma=30%), sector22 (LAGGING RS but pct_above_200dma=75%)
- Total store_finding calls: 31 sector_quadrant + 3 sector_rotation + 2 breadth_divergence + 1 summary = 37
  But rotation sectors also get sector_quadrant upsert, so it's all 31 + 3 + 2 + 1 = 37 calls
