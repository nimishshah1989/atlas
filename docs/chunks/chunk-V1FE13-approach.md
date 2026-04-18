---
chunk: V1FE-13
project: atlas
date: 2026-04-18
files:
  - frontend/mockups/lab.html
  - tests/unit/fe_pages/test_lab_structure.py
---

# V1FE-13 Approach — lab.html Lab / Simulations Page

## Scope
Pure static HTML mockup + structural unit tests. No backend, no JS, no data changes.

## Data scale
Not applicable — static HTML file. No DB queries.

## Approach

### HTML Structure
Follow the exact void-sentinel pattern established in breadth.html (V1FE-11) and portfolios.html (V1FE-12).

The criteria gate (`dom_checks.py`) uses `_VOID_TAG_RE` for `<tag ... />` self-closing forms. Nested div bodies silently fail `_TAG_RE`. Solution: place void sentinels at top of `<body>` for every data-* attribute the gate checks.

Structure:
1. `<head>` — viewport width=1440, link tokens.css + base.css + components.css
2. `<body>` opens with ALL void sentinels (criteria gate sees these)
3. Topbar with 10-link nav, Lab marked active
4. `<main class="page">` with:
   - DP component slots (regime-banner, signal-strip, four-decision-card voids)
   - Rec-slot void sentinels (2: lab-rule-selector, lab-playback-overlay)
   - Breadcrumbs
   - Page header
   - Mode tabs (3: breadth-playback, rule-backtest [aria-disabled=true], compare)
   - Strategy config panel + run button + results area (inside breadth-playback tab)
   - Full signal-playback embed (data-component=signal-playback data-mode=full)
   - Four-decision-card with 4 cards
   - Explain block
5. Methodology footer

### Void sentinels required
- fe-p12-01: data-mode=breadth-playback, data-mode=rule-backtest, data-mode=compare
- fe-p12-02: data-block=strategy-config, data-role=run, data-block=results
- fe-p12-03: data-component=signal-playback data-mode=full
- fe-p10_5-01: 14 inputs with exact IDs (i_initial through i_l_sip_resume)
- fe-p10_5-02: data-overlay=strategy, data-overlay=nifty50-bh, data-overlay=nifty500-bh
- fe-p10_5-03: data-tab=log, data-tab=cashflow, data-tab=tax
- fe-g-08: .explain-block data-tier=explain
- fe-g-09: footer.methodology-footer data-role=methodology + "Source:" + "Data as of"
- fe-g-15: nav sentinel (10 entries)
- fe-g-16: input.atlas-search data-role=global-search
- fe-g-19: 2 rec-slots (lab-rule-selector, lab-playback-overlay)
- fe-dp-01: data-component=regime-banner data-regime data-as-of
- fe-dp-12+13: four-decision-card + 4 data-card values

### fe-dp-10 constraint
FORBIDDEN: data-tier='recommend'. Use data-tier='explain' only.

### fe-state-09 constraint
No naked dashes: no empty td elements without data-staleness or data-state.

### Wiki patterns used
- void-sentinel-regex-parser-dom (PROMOTED 2x) — key pattern for criteria gate compatibility
- static-html-mockup-react-spec (PROMOTED 4x) — HTML as unambiguous spec
- criteria-as-yaml-quality-gate (PROMOTED 5x) — gate reads YAML criteria

### Signal playback embed
The full embed replicates breadth.html lines 658-940 (all 14 params + 3 overlay + 3 tabs + chart).
Note from void-sentinel pattern: main content uses `data-param-id` attributes, NOT `id=` to avoid
duplicate ID collision with the sentinel inputs (which carry the actual IDs).

### Existing code reused
- breadth.html CSS classes (playback-wrap, params-panel, sim-chart-panel, tab-bar, etc.)
- portfolios.html sentinel structure
- today.html four-decision-card void pattern

### Expected runtime
Static HTML write — under 1 second. No DB queries. Tests run in <2 seconds.

### Edge cases
- rule-backtest tab: aria-disabled=true on the void sentinel AND on the visible tab element
- Rec-slot count exactly 2 (lab needs exactly lab-rule-selector + lab-playback-overlay)
- IDs must be unique: sentinel inputs have id=, visible inputs in playback use data-param-id=
- No Math.random(), no new Date() in scripts
- No BUY/SELL/HOLD/RECOMMEND words
- No raw hex in inline styles — use CSS variables
- fe-dp-10: no data-tier='recommend' (forbidden)
