# Chunk V1FE-14 Approach: QA Sweep — Playwright Baselines + a11y + Full Gate + Smoke Probe

## Data scale
- No database access needed. All work is against static HTML mockup files.
- 21 HTML files in frontend/mockups/ (17 main pages + 2 partials + 2 reference files)
- File sizes: 50–350KB each. Total ~2MB. Trivially fits in memory.

## Approach

### 1. Fix fe-g-04 (styleguide.html exemption)
The `design_tokens_only` handler in `scripts/fe_checks/html_checks.py` already reads
`exceptions_files` at line 103. The YAML entry for fe-g-04 just needs:
```yaml
exceptions_files: [styleguide.html]
```
Added to the `check:` block. This is the only change to the YAML. Handler is already correct.

### 2. Create scripts/check-fe-a11y.py
Pure stdlib regex-based accessibility checker. Checks:
- img alt attributes
- input label associations
- heading hierarchy (no level skips)
- anchor text or aria-label
- html lang attribute
- duplicate IDs
- table headers
- viewport meta tag

Lenient on styleguide.html and components.html (reference pages).
Exits 0 when no critical issues found. Writes .forge/a11y-report.json.

### 3. Create tests/e2e/ Playwright test suite
Uses Python playwright sync API (already installed, Chromium browser confirmed working).
Opens pages via file:// protocol. Parametrized over all 17 main pages.
Tests: page loads, title contains ATLAS, heading visible, screenshot taken.
Baseline comparison: pixel diff check if baseline exists (1% threshold).

### 4. Generate 53 baseline PNGs via scripts/generate-baselines.py
3 viewport sizes × 17 main pages + 2 reference pages at desktop = 53 total.
Headless Chromium. Deterministic (no random data, static files).

### 5. Wire a11y into quality gate (check 5.3)
Read .quality/checks.py to see if dimension 5 has check 5.3 accessible.
Wire check-fe-a11y.py into it.

## Wiki patterns checked
- Criteria-as-YAML Executable Gate — already used for fe-g-04 fix
- Regex HTML Selector with Nesting Depth Counter — reused approach for a11y regex parsing
- Void Sentinel pattern — no new sentinels needed here
- Static HTML Mockup as React Spec — confirms regex approach for static files

## Existing code being reused
- scripts/fe_checks/html_checks.py design_tokens_only() already handles exceptions_files
- tests/unit/fe_pages/ structure mirrors for e2e tests
- .forge/frontend-report.json contract already established

## Edge cases
- Partial files (_nav-shell.html, _shared.html) — skip in a11y and e2e
- Reference files (frontend-v1-spec.html, breadth-simulator-v8.html) — lenient checks
- Styleguide/components pages — explicitly exempted from color token check, lenient a11y
- Components page has intentional non-ATLAS titles — handle gracefully
- Heading skips: some pages may legitimately have h3 without h2 in component islands
  → downgrade to WARNING not FAIL

## Expected runtime
- fe-g-04 YAML fix: instant
- check-fe-a11y.py: ~2s for 21 files
- Playwright tests: ~30s for 17 pages (2s each)
- Baseline generation: ~90s for 53 screenshots (1-2s each)
- Full gate: < 5 min

## No database queries needed — all static file work.
