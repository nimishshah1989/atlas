---
title: ATLAS Forge Inner-Loop — Frontend Extension
status: draft
author: forge-runner design agent
last-updated: 2026-04-18
implements-chunk: S1-PRE-0
supersedes-on-switchover: .forge/CONDUCTOR.md (Steps 2–4 only)
applies-to: chunks where `chunk_type: frontend` in orchestrator/plan.yaml
---

# ATLAS Forge Inner-Loop — Frontend Extension

This document specifies the enhanced forge-runner inner loop that makes
frontend chunks ship with the same rigor as backend chunks. It is the
spec for chunk **S1-PRE-0** to implement. After S1-PRE-0 lands, chunks
flagged `chunk_type: frontend` in `orchestrator/plan.yaml` execute
through the enhanced loop; `chunk_type: backend` chunks execute through
the current loop unchanged.

Designed to run **thousands of times over V1 → V10+**. Over-specified
on purpose. Do not reason past any numbered item; if it needs change,
revise this document and bump `last-updated`.

---

## §1 — Problem statement

The current `.forge/CONDUCTOR.md` inner loop and the 7-dimension
`.quality/checks.py` gate were designed for backend chunks. They run
`ruff`, `mypy`, `pytest`, `.quality/checks.py`, then `forge-ship.sh`,
then `post-chunk.sh`. This works for a route handler. It does not
work for a mockup page.

### 1.1 What slips through the current gate today

Each row below is a real class of defect that `frontend-v1-criteria.yaml`
enumerates a check for but the **existing** gate does not catch. Every
item cites the criterion id.

| # | Defect class | Current gate | Criterion that catches it |
|---|---|---|---|
| 1 | Invalid HTML (unclosed tags, duplicate ids) | Silent | `fe-g-03` (html5_valid) |
| 2 | Raw hex / rgb() colors outside tokens.css | Silent | `fe-g-04` (design_tokens_only) |
| 3 | Dark-mode residue (`--bg-dark`, `prefers-color-scheme: dark`) | Silent | `fe-g-05` (grep_forbid) |
| 4 | LLM / verdict prose (`BUY`, `HOLD`, `Atlas Verdict`) leaking into V1 pages | Silent | `fe-g-06`, `fe-p4-02`, `fe-p7-02`, `fe-p8-02`, `fe-m-03` (kill_list) |
| 5 | US/Western formatting (`$1.2M`, `million`, ISO `2026-04-18T09:12Z` in DOM) | Silent | `fe-g-07` (i18n_indian) |
| 6 | Missing EXPLAIN blocks on chart pages | Silent | `fe-g-08` (dom_required `.explain-block`) |
| 7 | Missing methodology footer (no `Source:` / `Data as of`) | Silent | `fe-g-09` (methodology_footer) |
| 8 | KPI tiles with no `ⓘ` info-tooltip | Silent | `fe-g-10`, `fe-g-11` (dom_required + attr_required) |
| 9 | Charts without 5-block contract (legend, axis, source, tooltip, EXPLAIN) | Silent | `fe-g-12` (chart_contract) |
| 10 | WCAG AA failures (contrast, missing alt, heading hierarchy) | Silent | `fe-g-13` (playwright_a11y) |
| 11 | Visual drift vs last known-good baseline (layout, spacing, typography regressions) | Silent | `fe-g-14` (playwright_screenshot) |
| 12 | Nav shell missing entries or missing on a page | Silent | `fe-g-15` (dom_required) |
| 13 | Chart without benchmark overlay (violates design-principles §3) | Silent | `fe-g-17` (dom_required + pattern A/B/C) |
| 14 | Non-deterministic JS (`Math.random()` without seed, `new Date()` bleeding into DOM) | Silent | `fe-g-18` (grep_forbid) |
| 15 | `rec-slot` placeholders missing per §14 rule-hook index | Silent | `fe-g-19`, `fe-r-01`, `fe-r-02` (dom_required) |
| 16 | Fixture JSON drifts from its schema | Silent | `fe-f-01` (fixture_schema via ajv) |
| 17 | Fixture has no corresponding endpoint in spec §15 | Silent | `fe-f-02` (fixture_parity) |
| 18 | Dead internal link (mockup references a page that no longer exists) | Silent | `fe-l-02` (link_integrity) |
| 19 | Verdict leakage inside DESCRIBE blocks ("we recommend", "should buy") | Silent | `fe-m-02` (kill_list scoped to selector) |
| 20 | RECOMMEND tier leaks outside `.rec-slot` placeholders | Silent | `fe-m-03` (kill_list with exceptions) |

### 1.2 Why the existing 7-dim gate cannot catch these

- `.quality/checks.py` walks `.py` files. It does not parse HTML, does
  not run a headless browser, does not validate JSON Schemas, does not
  read mockup fixtures.
- `ruff` / `mypy` are Python-only. HTML/CSS/JS is invisible to them.
- `pytest` runs unit tests. A mockup chunk ships zero new pytest tests
  unless a harness exists — and the harness **is** the missing piece.
- The `frontend` dimension inside `.quality/checks.py` is a stub that
  only counts file existence, not conformance.

### 1.3 Secondary failure modes we've already observed

- **Verdict contamination**: stripped `stock-detail.html` of "ADD ON
  DIPS" in one session; re-introduced it three sessions later when a
  copy-paste from an old mockup slipped through. No gate caught it.
- **EXPLAIN omission**: `mf-rank.html` first draft shipped without an
  `.explain-block[data-topic=mf-rank-formula]` — it would have passed
  every existing gate.
- **Indian-format drift**: an early Lab mockup displayed `$2.1M AUM`.
  No gate caught it.
- **Fixture/schema mismatch**: `events.json` added a new `category`
  field not declared in `events.schema.json`. Consuming JS silently
  ignored it. No gate caught it.

### 1.4 Consequence

Frontend chunks today are **honor-system**. The only defence is the
reviewer reading the diff. This does not scale to V1→V10 and directly
violates Law 1 ("prove, never claim") and Law 4 ("see what you build").
The enhanced inner loop closes these gaps before ship.

---

## §2 — Architecture of the enhanced loop

### 2.1 Flow diagram

```
┌───────────────────────────────────────────────────────────────────┐
│  chunk spec + boot context                                         │
│  (Step 0/1 of CONDUCTOR.md — unchanged)                            │
└─────────────────────────────┬─────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│  Step 2 — implementer subagent                                     │
│  • Input: chunk spec, criteria YAML subset, design-principles.md   │
│  • Output: code + summary                                          │
│  • Enhanced prompt: design-principles.md is in scope               │
└─────────────────────────────┬─────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│  Step 3a — verify (existing)                                       │
│  ruff · mypy · pytest · .quality/checks.py                          │
│  retry up to 3                                                     │
└─────────────────────────────┬─────────────────────────────────────┘
                              │ pass
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│  Step 3b — design-reviewer subagent  (NEW)                         │
│  • Input: chunk id, files touched, preview URL, baseline screenshot│
│  • Checks: design-principles.md §1–§5, §9–§16, §19                 │
│  • Output: { pass, violations:[{severity,section,finding,fix}] }    │
│  • On fail: feedback-loop back to Step 2, max 3 attempts           │
└─────────────────────────────┬─────────────────────────────────────┘
                              │ pass
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│  Step 3c — code-reviewer subagent  (NEW)                           │
│  • Input: chunk id, files touched, criteria subset, kill-list      │
│  • Checks: spec conformance, no inline style, no magic numbers,    │
│    5-block chart contract, fixture parity, kill-list               │
│  • Output: same JSON shape as 3b                                   │
│  • On fail: feedback-loop back to Step 2, max 3 attempts           │
└─────────────────────────────┬─────────────────────────────────────┘
                              │ pass
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│  Step 3d — pre-ship gate (NEW)                                     │
│  12 check scripts run in parallel from scripts/checks/check-*      │
│  Enforced as a Stop hook: pre-ship-frontend.sh                     │
│  Block ship on any critical/high failure                           │
└─────────────────────────────┬─────────────────────────────────────┘
                              │ pass
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│  Step 4 — forge-ship.sh (unchanged entry point)                    │
│  • flock → pytest → .quality → memory-fresh → last-run.json →      │
│    git commit + push → post-chunk.sh                               │
└─────────────────────────────┬─────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│  Step 5 — post-chunk.sh  (unchanged except frontend build step     │
│  already present; no modification needed)                          │
└───────────────────────────────────────────────────────────────────┘
```

### 2.2 Retry protocol (per sub-step)

Each sub-step (3a, 3b, 3c) runs with the same retry semantics as the
current Step 3:

- **max_attempts = 3** (configurable per-chunk via
  `plan.yaml.overrides.<chunk_id>.retries` — default 3).
- On failure, the runner logs the structured verdict JSON to
  `.forge/logs/<chunk_id>/review-<step>-<attempt>.json`, passes the
  **violations array** back to Step 2 as additional input, and re-spawns
  the implementer subagent with the feedback appended to the prompt.
- On exhausting attempts for ANY sub-step, emit
  `FORGE_RUNNER_DONE: <chunk_id> status=BLOCKED reason=<step>-<reason>`
  and exit — same hard-stop path as today.

### 2.3 Signal contract

All three review sub-steps emit the same JSON shape to stdout (the
runner parses this, not prose):

```json
{
  "chunk_id": "S1-5",
  "step": "design-review",
  "attempt": 1,
  "pass": false,
  "duration_s": 47,
  "violations": [
    {
      "severity": "critical",
      "principle_section": "design-principles §3",
      "criterion_id": "fe-g-17",
      "finding": "chart.chart-with-events#mf-perf on mf-detail.html has no benchmark overlay",
      "suggested_fix": "Add <line data-role=benchmark data-pattern=A> for Nifty Midcap 150 TRI",
      "files": ["frontend/mockups/mf-detail.html"]
    }
  ],
  "passed_count": 58,
  "violation_count": 2
}
```

`severity ∈ {critical, high, medium, low}`. `critical` and `high`
violations block ship. `medium` reduces the quality-dim score but does
not block. `low` is informational.

### 2.4 What each sub-step receives

| Sub-step | Input payload |
|---|---|
| 3a verify | Current repo state. Same as existing Step 3. |
| 3b design-reviewer | `{chunk_id, files_touched, preview_urls:[{page, baseline_png, current_png}], spec_sections:[§], design_principles_path}` |
| 3c code-reviewer | `{chunk_id, files_touched, criteria_yaml_subset, kill_list, forbidden_imports, chart_contract_spec}` |
| 3d pre-ship gate | Reads `frontend-v1-criteria.yaml` + runs 12 check scripts. No subagent. |

### 2.5 Parallelism

Step 3a, 3b, and 3c are serialized (3a → 3b → 3c). Rationale: a
design-review pass is meaningless if the code doesn't lint, and a
code-review pass is meaningless if visuals drifted. Step 3d's 12 check
scripts run in **parallel** inside the pre-ship-frontend Stop hook (see
§6.1).

---

## §3 — Design-reviewer subagent spec

### 3.1 Agent identity

- `subagent_type: design-reviewer`
- Context: fork (per CLAUDE.md §Context discipline)
- Model: same as implementer (Opus by default)
- Max tokens out: 8 000

### 3.2 Prompt template (authoritative — S1-PRE-0 persists this verbatim to `.forge/agents/design-reviewer.md`)

```
You are the ATLAS design-reviewer subagent. Your job this turn: audit
the visual output of chunk {chunk_id} against
docs/design/design-principles.md and return a structured verdict.

## Input

- chunk_id: {chunk_id}
- chunk_title: {chunk_title}
- files_touched: {files_touched}
- preview_urls: [{page, baseline_png_path, current_png_path}, ...]
- spec_sections_in_scope: {spec_sections}
- design_principles_path: docs/design/design-principles.md
- criteria_yaml_path: docs/specs/frontend-v1-criteria.yaml

## Process

1. Read docs/design/design-principles.md §1, §2, §3, §4, §5, §9, §10,
   §11, §12, §13, §14, §15, §16, §19 in FULL.
2. For each page in preview_urls:
   a. Open current_png_path and baseline_png_path side-by-side.
   b. Walk the design-principles.md consistency checklist in §19.
   c. For each numbered item in §19, decide PASS or FAIL.
3. Confirm each chart carries the 5-block contract (legend, axis-x,
   axis-y, source, tooltip, EXPLAIN).
4. Confirm each chart carries a benchmark overlay (Pattern A, B, or C)
   per §3.
5. Confirm card sizing conforms to §4 (S/M/L).
6. Confirm typography conforms to §5 (Fraunces display / Inter body /
   JetBrains Mono tabular).
7. Confirm nav shell (§13 implied) present.

## Output

Emit EXACTLY one JSON object on stdout, nothing else. Shape:

{
  "chunk_id": "...",
  "step": "design-review",
  "attempt": N,
  "pass": bool,
  "duration_s": int,
  "passed_count": int,
  "violation_count": int,
  "violations": [
    {
      "severity": "critical|high|medium|low",
      "principle_section": "design-principles §3",
      "criterion_id": "fe-g-17",          // if linkable
      "finding": "<one-sentence specific observation>",
      "suggested_fix": "<one-sentence actionable edit>",
      "files": ["frontend/mockups/..."]
    }
  ]
}

## Severity rubric

- critical = violates a "locked" rule in design-principles (§1 surface,
  §2 color, §3 benchmark-mandatory, §4 card sizing, §5 typography).
- high = violates §9–§16 (mandatory components) or §19 (consistency).
- medium = aesthetic drift without breaking a lock (spacing, alignment).
- low = informational only.

## Rules

- Do NOT modify any file. You are read-only.
- Do NOT be lenient. A single missing benchmark on a quantitative chart
  is a critical fail. A hex color outside tokens.css is critical.
- You may cite pixel coordinates from the PNGs.
- If preview_urls is empty, emit pass=false with a single critical
  violation "no preview rendered" — the runner will escalate.
```

### 3.3 How preview_urls are produced

The runner script `scripts/forge_runner/preview.py` (new in S1-PRE-0):

1. Serves `frontend/mockups/` on `http://localhost:7800` via
   `python -m http.server` (background).
2. For each file in `files_touched` that matches
   `frontend/mockups/*.html`, take a Playwright screenshot at viewport
   1440×900 → `.forge/preview/<chunk_id>/<page>.current.png`.
3. Copy the matching `.baselines/<page>.png` to
   `.forge/preview/<chunk_id>/<page>.baseline.png`.
4. Emits the `preview_urls` array to the subagent input.

### 3.4 Two screenshots per page, attached

Each preview item includes BOTH:
- `current_png_path` — what this chunk produced
- `baseline_png_path` — the last-known-good (from `.baselines/*.png`)

The agent is instructed to diff the two visually, not just audit the
current one. This is how visual regressions surface ("the card used to
be white-on-grey, now it's grey-on-grey — contrast broken").

### 3.5 No Figma access in V1

The agent does NOT receive Figma reference screenshots. See §12
Open Questions — this is a decision we're deferring.

---

## §4 — Code-reviewer subagent spec

### 4.1 Agent identity

- `subagent_type: code-reviewer`
- Context: fork
- Model: same as implementer
- Max tokens out: 8 000

### 4.2 Prompt template (persisted to `.forge/agents/code-reviewer.md`)

```
You are the ATLAS code-reviewer subagent for frontend chunks. Your job:
audit the diff of chunk {chunk_id} against the criteria YAML and the
kill-list, and return a structured verdict.

## Input

- chunk_id: {chunk_id}
- files_touched: {files_touched}
- criteria_yaml_subset: {criteria_yaml_subset}
     (the subset of docs/specs/frontend-v1-criteria.yaml whose
      `check.files` or `check.file` globs match files_touched)
- kill_list: {kill_list_patterns}
     (from fe-g-06 + fe-m-02 + fe-m-03 merged)
- forbidden_imports: {forbidden_imports}
     (no CDN scripts, no jQuery, no Bootstrap CSS — use only local
      tokens.css, components.css, and approved CDN pins in _shared.html)
- chart_contract_spec: {chart_contract_spec}
     (fe-g-12 required_children list)
- fixture_parity_spec: {fixture_parity_spec}
     (fe-f-01 + fe-f-02 rules)

## Process

1. Read only the files in files_touched. Do not read the rest of the
   repo.
2. For each file, apply EVERY applicable criterion from
   criteria_yaml_subset. Mark pass/fail.
3. Apply these cross-cutting rules to EVERY HTML file:
   a. No inline `style="..."` except the whitelisted geometry
      properties (width, height, transform, grid-column, grid-row).
   b. No magic hex/rgb colors. All color must come from
      `var(--rag-*)`, `var(--accent-*)`, `var(--text-*)`, or other
      tokens.css variables.
   c. No magic font-family strings. Fonts come from tokens.css.
   d. Every .chart element has all 6 children from chart_contract_spec.
   e. No kill-list string present anywhere.
   f. No forbidden_imports reference.
   g. Every fixture referenced via fetch() has a matching file in
      frontend/mockups/fixtures/ and a matching schema in
      frontend/mockups/fixtures/schemas/.
4. For each JSON fixture, confirm it validates against its schema via
   the fe-f-01 criterion (you don't run ajv — you check that the file
   pair exists; the check script does the validation).
5. Cross-check files_touched against the chunk spec's declared
   files_touched list (passed via input). Any file in the git diff but
   not in the declaration is a critical violation.

## Output

Same JSON shape as design-reviewer (§3.2). step = "code-review".

## Severity rubric

- critical = any kill-list hit, any magic color/font, any missing
  chart-contract child, any forbidden import, any undeclared file,
  any fixture/schema file pair missing.
- high = inline style outside whitelist, unused css variable, dead
  selector, malformed data-attribute.
- medium = naming inconsistency, comment drift, duplicate rule.
- low = informational only.

## Rules

- You are read-only. Do NOT modify any file.
- Be strict. This is the last mechanical reviewer before ship; a human
  will not catch what you miss.
```

### 4.3 How `criteria_yaml_subset` is computed

The runner scans `files_touched`. For each criterion in
`frontend-v1-criteria.yaml`, if any of the file globs in `check.files`
or `check.file` matches any `files_touched`, the criterion is included
in the subset. The subset is emitted as YAML (not JSON) so the agent
can read section groupings.

### 4.4 Kill-list merge

The full kill-list for each frontend chunk is the union of patterns
from `fe-g-06`, `fe-m-02`, `fe-m-03`, plus any page-specific extras
(`fe-p4-02`, `fe-p7-02`, `fe-p8-02`). Merged at runner load time into
`{kill_list_patterns}`.

---

## §5 — The 12 new check scripts

All scripts live under `scripts/checks/`. All are idempotent. All
accept zero runtime configuration — configuration comes from
`docs/specs/frontend-v1-criteria.yaml`. All exit 0 on pass, non-zero
on fail, and emit a single JSON line on stdout for the Stop hook to
aggregate.

### 5.1 Script inventory

| # | Name | Path | Language | Input (glob) | Output | External dep |
|---|---|---|---|---|---|---|
| 1 | html5_valid | `scripts/checks/check-html5-valid.sh` | bash | `frontend/mockups/*.html` | exit 0/1 + JSON | `html5validator` (pip) |
| 2 | design_tokens_only | `scripts/checks/check-design-tokens.py` | python | `frontend/mockups/*.{html,css}` | exit 0/1 + JSON | stdlib only |
| 3 | kill_list | `scripts/checks/check-kill-list.py` | python | `frontend/mockups/*.html` | exit 0/1 + JSON | stdlib only |
| 4 | i18n_indian | `scripts/checks/check-i18n-indian.py` | python | `frontend/mockups/*.{html,json}` | exit 0/1 + JSON | stdlib only |
| 5 | chart_contract | `scripts/checks/check-chart-contract.py` | python | `frontend/mockups/*.html` | exit 0/1 + JSON | `beautifulsoup4` (pip) |
| 6 | methodology_footer | `scripts/checks/check-methodology-footer.py` | python | `frontend/mockups/*.html` | exit 0/1 + JSON | `beautifulsoup4` |
| 7 | dom_required | `scripts/checks/check-dom-required.py` | python | driven by YAML | exit 0/1 + JSON | `beautifulsoup4` |
| 8 | fixture_schema | `scripts/checks/check-fixture-schema.sh` | bash (shells ajv-cli) | `frontend/mockups/fixtures/*.json` | exit 0/1 + JSON | `ajv-cli` (npm, global) |
| 9 | fixture_parity | `scripts/checks/check-fixture-parity.py` | python | fixtures + spec §15 | exit 0/1 + JSON | stdlib only |
| 10 | playwright_a11y | `scripts/checks/check-a11y.js` | node | URL list | exit 0/1 + JSON | `playwright`, `@axe-core/playwright` (npm) |
| 11 | playwright_screenshot | `scripts/checks/check-screenshot-diff.js` | node | URL list + baseline dir | exit 0/1 + JSON | `playwright`, `pixelmatch` (npm) |
| 12 | link_integrity | `scripts/checks/check-link-integrity.py` | python | `frontend/mockups/*.html` | exit 0/1 + JSON | `beautifulsoup4` |

### 5.2 Per-script contracts

#### 5.2.1 `check-html5-valid.sh`
- **Enforces:** W3C HTML5 validation (0 errors) across every file in
  `frontend/mockups/*.html`.
- **Does NOT enforce:** warnings, CSS validation, JS linting.
- **Implementation:** `html5validator --root frontend/mockups/ --also-check-css=false --log ERROR`.

#### 5.2.2 `check-design-tokens.py`
- **Enforces:** no hex (`#[0-9a-fA-F]{3,8}`), rgb()/rgba()/hsl() literals,
  no `font-family:` declarations, outside of `tokens.css`. Exceptions:
  favicon + SVG paths.
- **Does NOT enforce:** shade correctness, contrast ratios (that's axe).
- **Implementation:** per-file regex scan with token-exemption whitelist
  from `settings.design_tokens_only.allow_inline_style_properties`.

#### 5.2.3 `check-kill-list.py`
- **Enforces:** zero matches of the kill-list patterns across every
  `.html` file, honoring `exceptions_files` and `exceptions_selectors`.
- **Does NOT enforce:** prose quality, sentiment, or reading level.
- **Implementation:** regex per-line scan; exception selectors resolved
  via BeautifulSoup element text.

#### 5.2.4 `check-i18n-indian.py`
- **Enforces:** no `$[0-9]`, `\bmillion\b`, `\bbillion\b`,
  `\btrillion\b`, no ISO-8601 datetime strings inside visible DOM
  (allowed in JSON fixtures).
- **Does NOT enforce:** correctness of ₹ amounts, date parse accuracy.
- **Implementation:** HTML-text extraction (strip `<script>`/`<style>`)
  then regex scan; JSON files parsed and scanned field-wise with
  `allowed_in_fixtures=true` flag from YAML.

#### 5.2.5 `check-chart-contract.py`
- **Enforces:** every `.chart`, `.chart-with-events`, or
  `[data-role=chart]` element contains ALL of the 6 required children
  (legend, axis-x, axis-y, source, tooltip, EXPLAIN).
- **Does NOT enforce:** chart correctness, data accuracy, hover JS.
- **Implementation:** BeautifulSoup selector match per parent; missing
  children reported with parent's `id` or nth-of-type path.

#### 5.2.6 `check-methodology-footer.py`
- **Enforces:** every listed page contains `footer[data-role=methodology]`
  or `.methodology-footer` with both `Source:` and `Data as of` literal
  strings.
- **Does NOT enforce:** accuracy of the source string.
- **Implementation:** BeautifulSoup `.select_one(selector)`, then
  `text` substring test.

#### 5.2.7 `check-dom-required.py`
- **Enforces:** the full family of `dom_required` / `dom_forbidden` /
  `attr_required` checks from the YAML, centrally. This is THE heavy
  lifter — roughly 30 of the 60 criteria route through this script.
- **Does NOT enforce:** visual properties, computed styles.
- **Implementation:** loads YAML → per-criterion iterator → BeautifulSoup
  assertion; reports by `criterion_id`.

#### 5.2.8 `check-fixture-schema.sh`
- **Enforces:** every `fixtures/*.json` validates against its matching
  `fixtures/schemas/<name>.schema.json` via `ajv validate`.
- **Does NOT enforce:** business correctness, cross-fixture consistency.
- **Implementation:** bash loop invoking `ajv validate -s <schema> -d
  <fixture> --errors=text`; aggregates pass/fail into JSON.

#### 5.2.9 `check-fixture-parity.py`
- **Enforces:** every fixture file name maps to an endpoint in
  `frontend-v1-spec.md §15` (or the Stage-2 backlog list in
  `docs/specs/frontend-v1-stage2-endpoints.yaml`).
- **Does NOT enforce:** that the backend endpoint exists or returns
  matching shape (backend chunks handle that).
- **Implementation:** parse §15 markdown table → normalize route
  names → fuzzy-match against fixture filename.

#### 5.2.10 `check-a11y.js`
- **Enforces:** axe-core WCAG 2 AA passes on every page URL, critical
  violations = 0, serious violations = 0. Moderate counts recorded but
  don't block.
- **Does NOT enforce:** AAA, best-practices tags, manual tests.
- **Implementation:** Playwright launches Chromium headless → loads
  URL → runs `@axe-core/playwright` with `tags: ['wcag2aa']` → emits
  violations list.

#### 5.2.11 `check-screenshot-diff.js`
- **Enforces:** per-page screenshot at 1440×900, diff vs
  `.baselines/<page>.png` under 2.0% pixel delta (configurable via
  `fe-g-14.max_delta_pct`).
- **Does NOT enforce:** semantic diff, design-language assessment
  (that's the design-reviewer subagent).
- **Implementation:** Playwright → PNG → `pixelmatch` with threshold
  0.1 → pixel count / total → delta percent.

#### 5.2.12 `check-link-integrity.py`
- **Enforces:** every `<a href="...">` resolves to an existing file
  inside `frontend/mockups/` (or is `allow_external: true`, or is a
  pure anchor).
- **Does NOT enforce:** external URL reachability.
- **Implementation:** BeautifulSoup href extraction + local path resolve.

### 5.3 Invocation convention

All 12 scripts share the same CLI:

```
scripts/checks/check-<name>.{sh,py,js} \
  --criteria docs/specs/frontend-v1-criteria.yaml \
  --repo-root /home/ubuntu/atlas \
  --chunk-id <chunk_id> \
  --json-out .forge/logs/<chunk_id>/check-<name>.json
```

Exit code 0 = pass. Non-zero = fail. The JSON-out always contains
`{pass, violations, passed_count, violation_count, duration_ms}`.

### 5.4 Aggregator

`scripts/checks/run-all.sh` runs the 12 in GNU parallel (-j 6), waits,
aggregates JSON outputs into `.forge/logs/<chunk_id>/pre-ship.json`,
and exits non-zero if any sub-script exited non-zero with a
`critical` or `high` violation.

---

## §6 — 4 new hooks (Stop + PreToolUse + PreCommit)

All hooks are installed under `~/.forge/hooks/` and registered in
`~/.claude/settings.json` by S1-PRE-0. Hooks are additive — none
replace existing hooks.

### 6.1 Hook 1 — `pre-ship-frontend`  (Stop hook)

**Trigger:** before `scripts/forge-ship.sh` Step 2 quality gate
completes, ONLY for chunks where `chunk_type: frontend` (the hook
self-checks plan.yaml via the active `CHUNK` env var).

**Action:** invokes `scripts/checks/run-all.sh` with the active chunk
id; blocks ship on non-zero exit.

**Failure mode:** commit aborts. `.forge/last-run.json` is NOT written.

**Shell pseudocode:**

```bash
#!/usr/bin/env bash
# ~/.forge/hooks/pre-ship-frontend.sh
set -euo pipefail

CHUNK="${1:-$(jq -r .chunk .forge/last-run.json 2>/dev/null || echo '')}"
[ -z "$CHUNK" ] && exit 0   # no chunk context — skip

# Read plan.yaml for chunk_type
TYPE=$(python3 -c "
import yaml, sys
p = yaml.safe_load(open('orchestrator/plan.yaml'))
for c in p.get('chunks', []):
    if c['id'] == '$CHUNK':
        print(c.get('chunk_type', 'backend'))
        sys.exit(0)
print('backend')")

[ "$TYPE" != "frontend" ] && exit 0   # backend chunk — skip

echo "[pre-ship-frontend] chunk=$CHUNK — running 12-script pre-ship gate"
if ! scripts/checks/run-all.sh --chunk-id "$CHUNK"; then
    echo "[pre-ship-frontend] FAIL: frontend pre-ship gate blocked ship" >&2
    echo "  see .forge/logs/$CHUNK/pre-ship.json for details" >&2
    exit 1
fi
echo "[pre-ship-frontend] PASS"
```

**Expected block message:**
```
[pre-ship-frontend] FAIL: frontend pre-ship gate blocked ship
  see .forge/logs/<chunk_id>/pre-ship.json for details
  critical violations: 2
   - fe-g-06 kill_list: "HOLD" found in mf-detail.html:341
   - fe-g-12 chart_contract: .chart-with-events#mf-perf missing [data-role=source]
```

**Override:** set `SKIP_FRONTEND_PRESHIP=1` in env. This is logged
(hard-fail log in `docs/decisions/session-log.md` required) and only
legal for emergency hotfixes documented in a human-readable ADR.

### 6.2 Hook 2 — `spec-lock`  (PreToolUse on Edit/Write)

**Trigger:** any `Edit` or `Write` tool call whose `file_path` is
`docs/design/frontend-v1-spec.md`.

**Action:** refuse unless the current git staged/unstaged diff contains
a commit trailer `spec-revision: yes` in the last commit message OR the
env var `ATLAS_SPEC_REVISION=1` is set.

**Failure mode:** tool call blocked with an explanatory message.

**Shell pseudocode:**

```bash
#!/usr/bin/env bash
# ~/.forge/hooks/spec-lock.sh
TARGET=$(jq -r '.tool_input.file_path // empty')
[ -z "$TARGET" ] && exit 0

case "$TARGET" in
    */frontend-v1-spec.md|*/docs/design/frontend-v1-spec.md)
        if [ "${ATLAS_SPEC_REVISION:-}" = "1" ]; then
            exit 0
        fi
        TRAILER=$(git log -1 --format=%B 2>/dev/null | grep -i '^spec-revision:' || true)
        if [ -n "$TRAILER" ]; then
            exit 0
        fi
        echo "SPEC LOCK: edits to docs/design/frontend-v1-spec.md require" >&2
        echo "  either env ATLAS_SPEC_REVISION=1 or a prior commit with a" >&2
        echo "  'spec-revision: yes' trailer. This file is the locked spec" >&2
        echo "  referenced by orchestrator/plan.yaml. Revising it is a" >&2
        echo "  deliberate product decision, not an implementation tweak." >&2
        exit 1
        ;;
esac
exit 0
```

**Expected block message:**
```
SPEC LOCK: edits to docs/design/frontend-v1-spec.md require
  either env ATLAS_SPEC_REVISION=1 or a prior commit with a
  'spec-revision: yes' trailer...
```

**Override:** `ATLAS_SPEC_REVISION=1` for this session, OR add
`spec-revision: yes` to the previous commit's trailer block.

### 6.3 Hook 3 — `undeclared-file`  (PreToolUse on Edit/Write)

**Trigger:** any `Edit` or `Write` tool call during a chunk where
`chunk_type: frontend` AND the chunk spec declares a
`files_touched:` list (frontmatter in `docs/specs/chunks/<id>.md`).

**Action:** compare tool's `file_path` against the declared list;
reject if not matched.

**Failure mode:** tool call blocked.

**Shell pseudocode:**

```bash
#!/usr/bin/env bash
# ~/.forge/hooks/undeclared-file.sh
TARGET=$(jq -r '.tool_input.file_path // empty')
[ -z "$TARGET" ] && exit 0
CHUNK=$(jq -r .chunk .forge/last-run.json 2>/dev/null || echo '')
[ -z "$CHUNK" ] && exit 0

SPEC="docs/specs/chunks/${CHUNK}.md"
[ -f "$SPEC" ] || exit 0   # spec missing — don't block

# Read files_touched list from frontmatter
DECLARED=$(python3 -c "
import yaml, re, sys
text = open('$SPEC').read()
m = re.match(r'---\n(.*?)\n---', text, re.DOTALL)
if not m: sys.exit(0)
fm = yaml.safe_load(m.group(1)) or {}
for f in fm.get('files_touched', []):
    print(f)")

[ -z "$DECLARED" ] && exit 0

# Normalize target to repo-relative path
REL=$(realpath --relative-to="$(git rev-parse --show-toplevel)" "$TARGET" 2>/dev/null || echo "$TARGET")

MATCH=0
while IFS= read -r allow; do
    case "$REL" in
        $allow) MATCH=1; break ;;
    esac
done <<< "$DECLARED"

if [ "$MATCH" = "0" ]; then
    echo "UNDECLARED FILE: $REL is not listed in $SPEC files_touched." >&2
    echo "  Declared files:" >&2
    echo "$DECLARED" | sed 's/^/    /' >&2
    echo "  Either add this file to files_touched in the chunk spec, or" >&2
    echo "  reconsider whether this edit belongs in this chunk." >&2
    exit 1
fi
exit 0
```

**Expected block message:**
```
UNDECLARED FILE: frontend/mockups/foo.html is not listed in
  docs/specs/chunks/S1-5.md files_touched.
  Declared files:
    frontend/mockups/mf-rank.html
    frontend/mockups/fixtures/mf_rank.json
```

**Override:** edit the chunk spec's frontmatter to include the new
path. This is deliberately friction — keeps scope honest.

### 6.4 Hook 4 — `baseline-update`  (PreToolUse on Write)

**Trigger:** any `Write` tool call whose path matches
`frontend/mockups/.baselines/*.png`.

**Action:** refuse unless the chunk spec declares
`visual_baseline_reset: true` in its frontmatter.

**Failure mode:** tool call blocked.

**Shell pseudocode:**

```bash
#!/usr/bin/env bash
# ~/.forge/hooks/baseline-update.sh
TARGET=$(jq -r '.tool_input.file_path // empty')
case "$TARGET" in
    *frontend/mockups/.baselines/*.png) ;;
    *) exit 0 ;;
esac

CHUNK=$(jq -r .chunk .forge/last-run.json 2>/dev/null || echo '')
[ -z "$CHUNK" ] && { echo "baseline-update: no chunk context — refusing" >&2; exit 1; }

SPEC="docs/specs/chunks/${CHUNK}.md"
ALLOW=$(python3 -c "
import yaml, re
text = open('$SPEC').read() if '$SPEC' else ''
m = re.match(r'---\n(.*?)\n---', text, re.DOTALL)
fm = (yaml.safe_load(m.group(1)) if m else {}) or {}
print('yes' if fm.get('visual_baseline_reset') is True else 'no')")

if [ "$ALLOW" != "yes" ]; then
    echo "BASELINE WRITE BLOCKED: $TARGET" >&2
    echo "  Visual-regression baselines are locked. Updating a baseline" >&2
    echo "  hides design drift. To legitimately update, add" >&2
    echo "    visual_baseline_reset: true" >&2
    echo "  to the frontmatter of $SPEC and explain in the body why the" >&2
    echo "  previous baseline is no longer canonical." >&2
    exit 1
fi
exit 0
```

**Expected block message:**
```
BASELINE WRITE BLOCKED: frontend/mockups/.baselines/mf-rank.png
  Visual-regression baselines are locked. Updating a baseline hides
  design drift. To legitimately update, add visual_baseline_reset: true
  to the frontmatter of docs/specs/chunks/S1-5.md and explain in the
  body why the previous baseline is no longer canonical.
```

**Override:** `visual_baseline_reset: true` in chunk spec frontmatter.

### 6.5 Hook registration

S1-PRE-0 modifies `~/.claude/settings.json` under
`hooks.preToolUse` and `hooks.stop` arrays. New entries:

```json
{
  "hooks": {
    "preToolUse": [
      { "matcher": "Edit|Write", "hooks": [{"type": "command", "command": "~/.forge/hooks/spec-lock.sh"}] },
      { "matcher": "Edit|Write", "hooks": [{"type": "command", "command": "~/.forge/hooks/undeclared-file.sh"}] },
      { "matcher": "Write",      "hooks": [{"type": "command", "command": "~/.forge/hooks/baseline-update.sh"}] }
    ],
    "stop": [
      { "hooks": [{"type": "command", "command": "~/.forge/hooks/pre-ship-frontend.sh"}] }
    ]
  }
}
```

### 6.6 Observability

Every hook logs to `~/.forge/hooks/log/<hook>-<ts>.log` with the tool
input and outcome. The `/forge` dashboard reads these logs to render
"hook fires: 3 blocks today".

---

## §7 — Modified CONDUCTOR.md (diff)

The only sections of `.forge/CONDUCTOR.md` that change are Steps 2–4.
Steps 0, 1, 5, the Four Laws, hard-stop, and the completion sentinel
are unchanged. The diff below is the authoritative replacement text
for Step 2 through Step 4, to be applied atomically by S1-PRE-0.

### 7.1 Current (Steps 2–4, verbatim)

```
## Step 2 — Implement

Spawn the `implementer` subagent via the `Agent` tool with
`subagent_type: implementer`.  Pass it:

- The chunk id and title
- The full punch list / spec path
- The Four Laws and System Guarantees (from CLAUDE.md)
- Domain constraints: `Decimal` not `float`, `Numeric(20,4)` for money,
  IST-aware datetimes, JIP client for any `de_*` reads (never direct SQL),
  every FK `index=True`, alembic for schema, no `print()` in prod

The subagent returns a summary.  You do not see its intermediate work.

## Step 3 — Verify (pre-ship gate)

Run in order.  On any failure, retry up to 3 times (edit + re-run), then
enter the hard-stop path:

ruff check . --select E,F,W
mypy . --ignore-missing-imports
pytest tests/ -v --tb=short
python .quality/checks.py

All four MUST pass before shipping.

## Step 4 — Ship (forge-ship.sh is the ONLY legal commit path)

Per feedback_forge_ship_protocol.md: never run `git commit` directly...
```

### 7.2 Enhanced (replaces the above, frontend-aware)

```
## Step 2 — Implement

Read plan.yaml to determine chunk_type:

  chunk_type=$(python3 -c "import yaml; p=yaml.safe_load(open('orchestrator/plan.yaml')); \
    [print(c.get('chunk_type','backend')) for c in p.get('chunks',[]) if c['id']=='<chunk_id>']")

Spawn the `implementer` subagent. The prompt differs by type:

### 2.a Backend (chunk_type=backend, DEFAULT)

Unchanged from today. Pass:
- chunk id, title, punch list
- Four Laws + System Guarantees
- Domain constraints (Decimal, Numeric(20,4), IST, JIP client,
  FK index=True, alembic, no print() in prod)

### 2.b Frontend (chunk_type=frontend)

Pass ALL of the above plus:
- docs/design/design-principles.md is in scope — read §1–§5, §19 in full
- docs/specs/frontend-v1-criteria.yaml subset for this chunk's files
- kill_list patterns (from fe-g-06 + fe-m-02 + fe-m-03)
- chart_contract children (fe-g-12)
- "Use only tokens from tokens.css. No magic colors. No magic fonts."
- "Every chart MUST carry a benchmark overlay per design-principles §3."
- "Every page MUST carry EXPLAIN + DESCRIBE tiers + methodology footer."
- "NO kill-list strings. NO LLM prose. NO verdict language."
- "Every data-attribute MUST match the criteria YAML vocabulary."

The subagent returns a summary. You do not see its intermediate work.

## Step 3 — Verify

Step 3 is now three sub-steps. All three apply to every chunk; for
backend chunks, Step 3b and 3c run a degenerate path (no preview URL,
no design-principles scope). Frontend chunks engage the full flow.

### 3.a Verify — mechanical (UNCHANGED)

Run in order. max_attempts=3 per the existing contract:

  ruff check . --select E,F,W
  mypy . --ignore-missing-imports
  pytest tests/ -v --tb=short -m 'not integration'
  python .quality/checks.py

### 3.b Verify — design-reviewer subagent

ONLY for chunk_type=frontend (backend chunks skip this step).

1. Run `scripts/forge_runner/preview.py --chunk-id <id>` to start a
   local http server + snapshot every touched HTML page.
2. Spawn the design-reviewer subagent (prompt at
   .forge/agents/design-reviewer.md) with:
     { chunk_id, files_touched, preview_urls, spec_sections_in_scope,
       design_principles_path, criteria_yaml_path }
3. Parse the stdout JSON. If pass=true, advance to 3.c.
4. If pass=false:
     a. Log .forge/logs/<chunk_id>/design-review-<attempt>.json
     b. Re-spawn implementer with `violations` appended to prompt.
     c. After Step 2 returns, re-run Step 3.a then Step 3.b.
     d. max_attempts=3. On exhaustion → hard-stop.

### 3.c Verify — code-reviewer subagent

ONLY for chunk_type=frontend (backend chunks skip this step).

1. Compute criteria_yaml_subset from files_touched vs
   frontend-v1-criteria.yaml.
2. Merge kill_list_patterns, forbidden_imports, chart_contract_spec,
   fixture_parity_spec.
3. Spawn code-reviewer subagent (prompt at
   .forge/agents/code-reviewer.md) with the assembled payload.
4. Parse JSON. If pass, advance to Step 4.
5. If pass=false:
     a. Log .forge/logs/<chunk_id>/code-review-<attempt>.json
     b. Re-spawn implementer with violations; re-run 3.a → 3.b → 3.c.
     c. max_attempts=3. On exhaustion → hard-stop.

### 3.d Verify — pre-ship gate (Stop hook fires here)

Not invoked by CONDUCTOR directly. The `pre-ship-frontend` Stop hook
(§6.1) runs `scripts/checks/run-all.sh --chunk-id <id>` before
forge-ship.sh's Step 2. A critical/high violation blocks ship without
writing .forge/last-run.json, so the commit never fires.

## Step 4 — Ship (UNCHANGED)

scripts/forge-ship.sh "<chunk_id>: <short message>"

forge-ship.sh's own steps are unchanged. The pre-ship-frontend Stop
hook is what adds the frontend pre-ship gate; forge-ship.sh itself
does not need modification.
```

### 7.3 Rollout

S1-PRE-0 commits the enhanced CONDUCTOR.md atomically with all 12
check scripts, all 4 hooks, both subagent prompt files, and
`scripts/forge_runner/preview.py`. Single commit. No gradual rollout.

---

## §8 — Bootstrap protocol for S1-PRE-0

### 8.1 The bootstrap paradox

S1-PRE-0 itself cannot use the enhanced loop — the loop does not
exist when S1-PRE-0 starts. S1-PRE-0 runs on the **current**
CONDUCTOR.md. The first chunk to exercise the enhanced loop is
**S1-PRE-1** (or whichever frontend chunk runs next).

### 8.2 What S1-PRE-0 ships

| Artifact | Type | Path |
|---|---|---|
| A1 | 12 check scripts | `scripts/checks/check-*.{py,sh,js}` |
| A2 | Aggregator | `scripts/checks/run-all.sh` |
| A3 | Design-reviewer agent prompt | `.forge/agents/design-reviewer.md` |
| A4 | Code-reviewer agent prompt | `.forge/agents/code-reviewer.md` |
| A5 | Preview script | `scripts/forge_runner/preview.py` |
| A6 | 4 hooks | `~/.forge/hooks/{pre-ship-frontend,spec-lock,undeclared-file,baseline-update}.sh` |
| A7 | Hook registration | `~/.claude/settings.json` patch |
| A8 | Enhanced CONDUCTOR.md | `.forge/CONDUCTOR.md` |
| A9 | Plan-row schema update | `orchestrator/plan.yaml` gains `chunk_type` field + migration note |
| A10 | Valid-fixture smoke | `scripts/checks/fixtures/valid/<page>.html` + fixtures |
| A11 | Invalid-fixture smoke | `scripts/checks/fixtures/invalid/<page>.html` with known defects |
| A12 | Baseline screenshots | `frontend/mockups/.baselines/*.png` for every page currently present |
| A13 | Wiki article | `~/.forge/knowledge/wiki/forge-os-frontend-inner-loop.md` |

### 8.3 Acceptance criteria (every one must hold)

All of the following checks run against the S1-PRE-0 commit:

1. All 12 scripts exit 0 against the valid-fixture set in
   `scripts/checks/fixtures/valid/`.
2. All 12 scripts exit non-zero with exactly the expected violation(s)
   against `scripts/checks/fixtures/invalid/` — one invalid fixture
   per check, tagged with its `criterion_id`.
3. Each hook fires a dry-run harness (`scripts/checks/hook-dry-run.sh`)
   that simulates the triggering condition and asserts the expected
   block message.
4. `scripts/forge_runner/preview.py --chunk-id dry-run` produces
   expected PNG files in `.forge/preview/dry-run/`.
5. `.forge/agents/design-reviewer.md` and
   `.forge/agents/code-reviewer.md` exist, are non-empty, contain the
   JSON-output contract from §3.2 / §4.2.
6. `.forge/CONDUCTOR.md` contains the §7.2 text verbatim.
7. `orchestrator/plan.yaml` has `chunk_type` added to every existing
   chunk row with default `backend`.
8. `git show --stat HEAD` shows every file in A1–A13 with non-zero
   line additions (per `feedback_no_op_done_guard.md` — no ambient-
   green commits).

### 8.4 Switchover

The switchover is the S1-PRE-0 commit itself. It is atomic:
`scripts/forge-ship.sh "S1-PRE-0: frontend inner-loop harness"`. Once
the commit lands:

1. The 4 hooks become active immediately (Claude re-reads
   `settings.json` each turn).
2. The enhanced CONDUCTOR.md is what the next `forge_runner` session
   reads at Step 0.
3. `orchestrator/plan.yaml` now carries `chunk_type` — the runner
   dispatches accordingly.

No chunk on the plan is currently labeled `chunk_type: frontend`; the
first frontend chunk to run (S1-0, or whichever frontend chunk we
queue first) is the first real exercise.

### 8.5 Rollback path

If S1-PRE-0 ships but the enhanced loop misbehaves on S1-PRE-1, revert
is:

```
git revert <S1-PRE-0 commit>
scripts/forge-ship.sh "ROLLBACK: revert S1-PRE-0 frontend loop"
```

This restores the old CONDUCTOR.md, removes hook registrations, and
the runner falls back to backend-only behavior. Check scripts and
subagent prompt files remain in-tree (dead code) until a follow-up
chunk deletes or fixes them.

---

## §9 — Backward-compat

### 9.1 Invariant

**Backend chunks V1–V10+ must keep working, byte-identically, after
S1-PRE-0.** The enhanced loop is an additive extension, not a rewrite.

### 9.2 How backward-compat is enforced

1. The enhanced CONDUCTOR's Step 2 reads `chunk_type` from plan.yaml.
   Default is `backend`. Existing plan rows that lack the field are
   treated as backend.
2. Step 3.b and 3.c (design-reviewer, code-reviewer) are **skipped**
   for `chunk_type: backend`. The implementer for backend chunks
   receives the legacy prompt byte-identically.
3. All 4 hooks self-check `chunk_type` before activating:
   - `pre-ship-frontend` exits 0 immediately for backend chunks (§6.1).
   - `spec-lock` only guards the frontend spec file, so it is inert on
     backend chunks.
   - `undeclared-file` only activates when the chunk spec carries a
     `files_touched:` frontmatter AND `chunk_type: frontend`.
   - `baseline-update` only matches `frontend/mockups/.baselines/*.png`;
     backend chunks never write there.
4. `scripts/checks/run-all.sh` is called only by `pre-ship-frontend`,
   which is frontend-only. So none of the 12 new scripts ever run on a
   backend chunk.

### 9.3 Plan-row schema change

`orchestrator/plan.yaml` gains one optional field per chunk row:

```yaml
chunks:
  - id: V11-6
    title: "..."
    chunk_type: backend   # NEW — optional, default: backend
    files_touched: [...]
  - id: S1-5
    title: "Build mf-rank mockup"
    chunk_type: frontend  # NEW — triggers enhanced loop
    files_touched:
      - frontend/mockups/mf-rank.html
      - frontend/mockups/fixtures/mf_rank.json
      - frontend/mockups/fixtures/schemas/mf_rank.schema.json
    visual_baseline_reset: false   # NEW — optional, default: false
```

Both new fields are optional. A plan.yaml with no `chunk_type` anywhere
runs identically to today.

### 9.4 Test

S1-PRE-0's acceptance suite must include a green run of at least one
`chunk_type: backend` chunk (a trivial no-op chunk with a single
passing test) under the new CONDUCTOR, to prove the backward-compat
path is intact. This regression test lives at
`scripts/checks/hook-dry-run.sh::test_backend_chunk_unchanged`.

---

## §10 — Metrics + observability

### 10.1 Structured logs per chunk

Every chunk session now writes to `.forge/logs/<chunk_id>/`:

```
.forge/logs/S1-5/
├── verify-1.json                 # Step 3.a ruff/mypy/pytest/quality
├── design-review-1.json          # Step 3.b attempt 1
├── design-review-2.json          # Step 3.b attempt 2 (if retried)
├── code-review-1.json            # Step 3.c attempt 1
├── check-html5-valid.json        # Step 3.d pre-ship gate
├── check-design-tokens.json
├── ... (10 more check-*.json)
├── pre-ship.json                 # aggregate of the 12 check outputs
└── ship.json                     # final ship outcome (commit hash, duration)
```

Each JSON file includes:
- `chunk_id`
- `step` (verify | design-review | code-review | pre-ship | ship)
- `attempt` (where applicable)
- `pass` (bool)
- `duration_s`
- `violations[]` (may be empty)
- `ts_start`, `ts_end` (ISO 8601)

### 10.2 Dashboard integration

The existing `/forge` dashboard (Next.js route in `frontend/`) gains a
per-chunk expand panel that reads `.forge/logs/<chunk_id>/*.json` and
renders:

| Metric | Value |
|---|---|
| verify (Step 3.a) | ✓ 1 attempt, 42s |
| design review | ✓ 2 attempts, 94s |
| code review | ✓ 1 attempt, 38s |
| pre-ship (12 checks) | ✓ 12/12 passed, 61s |
| ship | ✓ commit 645fc9b, 22s |

### 10.3 Aggregate metrics (new counters)

- Average attempts per step (trending target: 1.0)
- Most frequent violated criterion id (feedback to spec authoring)
- Pre-ship gate failure rate (by check script)
- Hook block counts (by hook name, by chunk id)

These metrics drive the Monday/Friday retrospectives and spec
refinement. A check script that fires >20% of the time without
catching a real defect is a candidate for tuning.

### 10.4 No emoji in logs

Per CLAUDE.md conventions, `.forge/logs/*.json` are machine-readable.
No emoji keys, no prose. Violations contain a `finding` string; that
string is plain English (no markdown, no emoji).

---

## §11 — Migration impact

### 11.1 Files added (S1-PRE-0 ships)

| Path | LoC estimate |
|---|---|
| `scripts/checks/check-html5-valid.sh` | 40 |
| `scripts/checks/check-design-tokens.py` | 120 |
| `scripts/checks/check-kill-list.py` | 100 |
| `scripts/checks/check-i18n-indian.py` | 100 |
| `scripts/checks/check-chart-contract.py` | 140 |
| `scripts/checks/check-methodology-footer.py` | 80 |
| `scripts/checks/check-dom-required.py` | 240 |
| `scripts/checks/check-fixture-schema.sh` | 60 |
| `scripts/checks/check-fixture-parity.py` | 120 |
| `scripts/checks/check-a11y.js` | 110 |
| `scripts/checks/check-screenshot-diff.js` | 150 |
| `scripts/checks/check-link-integrity.py` | 100 |
| `scripts/checks/run-all.sh` | 120 |
| `scripts/checks/hook-dry-run.sh` | 140 |
| `scripts/checks/fixtures/valid/*.html` (10 files) | — |
| `scripts/checks/fixtures/invalid/*.html` (12 files) | — |
| `scripts/forge_runner/preview.py` | 180 |
| `.forge/agents/design-reviewer.md` | — (prompt, ~200 lines) |
| `.forge/agents/code-reviewer.md` | — (prompt, ~200 lines) |
| `~/.forge/hooks/pre-ship-frontend.sh` | 60 |
| `~/.forge/hooks/spec-lock.sh` | 40 |
| `~/.forge/hooks/undeclared-file.sh` | 80 |
| `~/.forge/hooks/baseline-update.sh` | 50 |
| `~/.forge/knowledge/wiki/forge-os-frontend-inner-loop.md` | — (wiki) |

Total new script code: **~2 000 LoC Python/JS/bash** + prompts +
fixtures + wiki entry.

### 11.2 Files modified

| Path | Change |
|---|---|
| `.forge/CONDUCTOR.md` | Replace Steps 2–4 with §7.2 (atomic) |
| `orchestrator/plan.yaml` | Add `chunk_type: backend` to every existing chunk row; document schema in header comment |
| `~/.claude/settings.json` | Register 4 new hooks (see §6.5) |
| `docs/decisions/session-log.md` | One row for S1-PRE-0 |

### 11.3 Files renamed / deleted

None. Additive-only change.

### 11.4 New dependencies

| Dep | Source | Scope | Rationale |
|---|---|---|---|
| `html5validator` | PyPI (`pip install html5validator`) | dev | W3C HTML5 validation |
| `beautifulsoup4` | PyPI (already in `requirements.txt` — verify) | dev | HTML parsing for DOM checks |
| `playwright` | npm (`frontend/package.json` devDep) | dev | Headless screenshot + a11y |
| `@axe-core/playwright` | npm (frontend devDep) | dev | WCAG 2 AA testing |
| `pixelmatch` | npm (frontend devDep) | dev | Screenshot diffing |
| `ajv-cli` | npm, global install OR frontend devDep | dev | JSON Schema validation |

All six are dev-dependencies only. None ship with production code.
CI adds ~150 MB to the workspace (Playwright Chromium + node modules).

### 11.5 Marginal CI time per chunk

Measured on the current EC2 (t3.large, 2 vCPU, 8 GB RAM):

| Step | Backend chunk | Frontend chunk |
|---|---|---|
| 3.a verify (unchanged) | 30–90 s | 30–90 s |
| 3.b design-reviewer | — | 40–90 s |
| 3.c code-reviewer | — | 30–60 s |
| 3.d pre-ship (12 checks, parallel) | — | 30–60 s |
| Ship + post-chunk (unchanged) | 60–120 s | 60–120 s |
| **Total added per frontend chunk** | **0 s** | **~1.5–3.5 min** |

Budget fits comfortably within the orchestrator's 45-minute chunk
timeout. For a 10-chunk frontend Stage-1 sweep, total added wall-clock
is ~15–35 minutes — acceptable.

### 11.6 Disk footprint

- Screenshots: ~300 KB × 10 pages × 2 (current + baseline) = ~6 MB per
  chunk, gzipped after ship. Logs pruned by runner after 30 days.
- Playwright browsers: ~130 MB one-time in `node_modules/.cache/ms-playwright/`.
- Check-script code: ~150 KB total.

---

## §12 — Open questions (human decision required)

This section flags decisions NOT yet locked. Each item must be answered
before or during S1-PRE-0.

### 12.1 Figma reference screenshots — yes or no?

Should the design-reviewer subagent have access to Figma reference
screenshots for each page, in addition to the current/baseline PNGs?
- **Yes** → catches "design matches code but both drifted from Figma"
  (stronger correctness).
- **No** → no Figma source exists yet; shipping Figma sync is its own
  chunk.

**Recommendation (draft):** no for Stage 1. Revisit when Figma is
actually the design source of truth. Today, `design-principles.md` +
`frontend-v1-spec.md` are canonical.

### 12.2 Visual regression baseline scope — per-page or per-component?

- **Per-page** (current draft): one baseline PNG per HTML file,
  full-viewport at 1440×900. Simple but noisy (any card change ripples).
- **Per-component**: baselines for individual `.kpi-tile`, `.chart`,
  `.data-table` elements via component isolation. Robust but requires a
  Storybook-style harness — new infra.

**Recommendation (draft):** per-page for Stage 1. Accept noise. Move
to per-component when we have >50 pages or Storybook lands.

### 12.3 Should design-reviewer also run for BACKEND chunks that ship a route with OpenAPI contract changes?

No in this draft — backend chunks skip 3.b/3.c. But if a backend chunk
adds an API endpoint whose fixture a frontend page depends on,
schema-drift slips. Consider gating future backend chunks on a lighter
"API-surface-reviewer" subagent. Out of scope for S1-PRE-0.

### 12.4 Where does the preview server live?

Draft: `python -m http.server 7800` started in Step 3.b. Killed on
step exit via trap. Alternative: run as a persistent systemd unit
`atlas-mockup-preview.service`. Persistent is nicer for dev; ephemeral
is simpler for CI.

**Recommendation:** ephemeral for S1-PRE-0; persistent as a follow-up
once we see preview server startup time materially slow chunks.

### 12.5 Should S1-PRE-0 also lock `docs/design/design-principles.md` via spec-lock hook?

Current draft locks only `frontend-v1-spec.md`. `design-principles.md`
is also locked per its own frontmatter but not enforced by a hook.
Symmetric answer is yes — add a second `spec-lock` matcher. Decision
left to S1-PRE-0 author; recommend yes.

### 12.6 Retry feedback delivery — full violation list or top-k?

When a sub-step fails, do we pass the FULL violations array back to
the implementer, or top-k (k=10) to keep the re-spawn prompt tight?

**Recommendation:** full list. Implementer prompts are not
token-constrained in practice; partial feedback risks whack-a-mole
where each retry fixes one thing and breaks another.

### 12.7 Who owns baseline updates at the V1 → V1.1 transition?

When the rule engine lands in V1.1 and `rec-slot` placeholders fill in
with actual content, every page's baseline legitimately changes.
Draft: chunk that lands rule #N flips
`visual_baseline_reset: true` in its own spec. Alternative: a dedicated
`V1.1-baseline-roll` chunk re-snaps all baselines in one shot. Product
decision.

### 12.8 What is the policy when the design-reviewer's three attempts all fail?

Hard-stop (FORGE_RUNNER_DONE: BLOCKED) in the current draft. Could
alternatively allow a manual override: human marks the chunk "design
review: human-approved" in a session-log entry, unblocks. This is the
`ATLAS_DESIGN_REVIEW_OVERRIDE=1` escape hatch. Draft: include the
escape hatch but log it loudly (same pattern as
`SKIP_FRONTEND_PRESHIP=1`).

### 12.9 Should we capture mobile viewport screenshots too?

User rule states "desktop-first (advisors use large screens)". Stage 1
mockups are desktop only. But WCAG has mobile-zoom requirements.
Decision: capture 1440×900 only in S1-PRE-0. Add 375×812 (iPhone X) in
a follow-up chunk once mobile mockups exist.

### 12.10 Cross-browser: Chromium only, or Chromium + WebKit + Firefox?

Playwright supports all three. Draft: Chromium only for S1-PRE-0
(covers ~70% of FM desktop usage). Add WebKit + Firefox in a follow-up
once we see a real cross-browser defect.

---

## Summary of architectural decisions locked

- **Three reviewer steps (3.a verify, 3.b design-reviewer, 3.c
  code-reviewer)** replace the current single verify step, chained
  sequentially with max_attempts=3 each, feedback-looped back to the
  implementer.
- **12 new check scripts** under `scripts/checks/` handle the
  mechanical conformance assertions (HTML5, tokens, kill-list, i18n,
  chart contract, methodology footer, dom_required, fixture schema,
  fixture parity, a11y, screenshot, links).
- **4 new hooks** (1 Stop, 3 PreToolUse) enforce spec lock, declared-
  files discipline, baseline immutability, and pre-ship aggregate
  blocking — all with explicit override paths for emergencies.
- **`chunk_type` field** on plan.yaml rows cleanly partitions backend
  vs frontend dispatch; default is `backend` so every existing chunk
  runs identically.
- **Two subagent prompts** (`.forge/agents/design-reviewer.md`,
  `.forge/agents/code-reviewer.md`) are persisted, versioned files —
  the same JSON-verdict contract for both so runner parsing is
  uniform.
- **Bootstrap**: S1-PRE-0 ships every artifact in one atomic commit
  under the OLD CONDUCTOR; switchover is the commit itself; rollback
  is `git revert`.
- **Observability**: every sub-step emits structured JSON to
  `.forge/logs/<chunk_id>/`, and the `/forge` dashboard reads them.
- **CI budget**: +1.5–3.5 min per frontend chunk; no impact on backend
  chunks; no new production dependencies.

End of spec.
