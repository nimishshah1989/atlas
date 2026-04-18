---
chunk: V1FE-11
project: ATLAS
date: 2026-04-18
---

# Chunk V1FE-11 Approach: breadth.html Breadth Terminal

## Task
Create `frontend/mockups/breadth.html` — the canonical Breadth Terminal page.

## Data scale
No database queries needed. This is a static HTML mockup that loads fixture JSON via fetch().
Fixtures: `breadth_daily_5y.json` (5Y daily series), `zone_events.json` (4 zone events).

## Chosen approach
Single self-contained HTML file following identical structure to `mf-rank.html`:
- tokens.css + base.css + components.css imports
- Nav sentinels (aria-hidden void tags for fe-g-15, fe-g-16)
- Sticky topbar with full 10-entry nav, active=Breadth
- Page body with all required DOM attributes
- Inline `<style>` for page-specific styles
- `<script>` at bottom loading fixtures via fetch()

## DOM requirements checklist

### fe-p10-01: 3 headline counts
- `[data-headline="ema21"]`, `[data-headline="dma50"]`, `[data-headline="dma200"]`

### fe-p10-02: regime band + blocks
- `[data-role="regime-band"]`
- `[data-block="breadth-kpi"]` x3 (each with `.info-tooltip[title]`)
- `[data-block="oscillator"]`
- `[data-block="zone-reference"]`
- `.describe-block`
- `[data-block="signal-history"]`

### fe-p10-03: selectors
- `[data-role="universe-selector"]`
- `[data-role="ma-selector"]`

### fe-p10-04: zone bands
- `[data-zone="overbought"]`
- `[data-zone="oversold"]`
- `[data-zone="midline"]`

### fe-p10_5-01: 14 input params (exact IDs)
#i_initial, #i_sip, #i_lumpsum, #i_sell400, #i_furtherLvl, #i_furtherPct,
#i_redeployLvl, #i_redeployPct, #i_redeploy2Lvl, #i_redeploy2Pct,
#i_l_os, #i_l_ob, #i_l_exit, #i_l_sip_resume

### fe-p10_5-02: 3 overlay benchmarks
- `[data-overlay="strategy"]`, `[data-overlay="nifty50-bh"]`, `[data-overlay="nifty500-bh"]`

### fe-p10_5-03: 3 tabs
- `[data-tab="log"]`, `[data-tab="cashflow"]`, `[data-tab="tax"]`

### fe-g-08: explain block
- `.explain-block[data-tier="explain"]`

### fe-g-09: methodology footer
- `footer.methodology-footer[data-role="methodology"]` with "Source:" and "Data as of"

### fe-g-10/11: KPI info-tooltips
- Every `.kpi-tile`/`[data-role="kpi"]` must have `.info-tooltip[title]` (min 10 chars)

### fe-g-12: chart contract
- Every `.chart` / `.chart-with-events` must have:
  `[data-role="legend"]`, `[data-role="axis-x"]`, `[data-role="axis-y"]`,
  `[data-role="source"]`, `[data-role="tooltip"]`, `[data-role="explain"]`

### fe-g-17: benchmark overlay
- Every quantitative chart: `[data-role="benchmark"]` or `[data-pattern="A/B/C"]`

### fe-g-19 + fe-r-01: rec-slots
- `div.rec-slot[data-slot-id="breadth-regime"]`
- `div.rec-slot[data-slot-id="breadth-signal-header"]`
- `div.rec-slot[data-slot-id="breadth-playback-halo"]`

### fe-p10_5-04: no dark tokens
No #080810, #0f0f1e, #7c7cff, IBM Plex Mono, Plus Jakarta Sans

### fe-p10_5-05: FIFO tax date
Include "2024-07-23" cutoff in the tax tab content

## Wiki patterns checked
- `static-html-mockup-react-spec` — canonical pattern, use same structure as mf-rank.html
- `criteria-as-yaml-quality-gate` — verified all criteria IDs in frontend-v1-criteria.yaml

## Existing code reused
- Full nav shell from mf-rank.html (void sentinel tags + visible topbar)
- Methodology footer pattern from mf-rank.html
- explain-block structure from mf-rank.html
- Chart SVG skeleton pattern from explore-sector.html

## Edge cases
- fe-p10_5-04 forbids dark tokens — all colors via CSS custom properties only
- fe-g-06 forbids BUY/HOLD/SELL/ADD ON DIPS/REDUCE — checked prose carefully
- fe-g-18 forbids Math.random() and unseeded new Date().toString() — use fixture data_as_of
- fe-g-07 forbids $[0-9] and "million"/"billion" — Indian formatting only

## Expected runtime
Static file creation — no DB, no compute. Tests run in ~5 seconds.
