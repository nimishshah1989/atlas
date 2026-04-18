# S1-common: Shared prefix for all V1-Frontend-Stage1 page chunks

Every page chunk S1-0 .. S1-11 reads this file in Step 0 **after**
CLAUDE.md and **before** its own page-specific section. Purpose: stop
each page chunk from re-describing the same invariants.

---

## Step 0 — Boot context (every page chunk, in order)

1. `cat CLAUDE.md`
2. `cat docs/specs/chunks/s1-common.md` (this file)
3. `cat docs/design/frontend-v1-spec.md` § covering this page
4. `cat docs/design/design-principles.md` — referenced §§ per chunk
5. `cat docs/specs/frontend-v1-criteria.yaml` — filter to `fe-p<page>-*`
   and the shared groups (`fe-g-*`, `fe-dp-*`, `fe-mob-*`, `fe-state-*`,
   `fe-c-*`, `fe-m-*`)
6. `cat frontend/mockups/components.html` — copy components from here, do
   not reinvent
7. `cat ~/.claude/projects/-home-ubuntu-atlas/memory/project_atlas_frontend_pages.md`

## Hard invariants (apply to every page, enforced by gate)

1. **No inline styles** — use tokens.css classes only
2. **No synthetic data** — every number traces to a fixture which traces
   to a JIP query in a seed script
3. **No BUY/HOLD/SELL/verdict language** — kill_list gate blocks
4. **No $ / million / billion** — `i18n_indian` blocks; Indian formatting only
5. **Every chart carries**: legend + axis labels + source attribution +
   tooltip + interpretation sidecar slot
6. **Every stale-capable block** declares `data-as-of`
7. **Methodology footer** on every page (data-as-of + source + disclaimer)
8. **7 chips on every instrument row** (4 RRG + Gold-RS + Conviction + Divergences)
9. **Four universal benchmarks** row on every performance-context page
10. **Mobile**: no horizontal scroll at 360px viewport
11. **EXPLAIN + DESCRIBE interpretation tiers** present; **RECOMMEND tier
    forbidden** in V1

## Component reuse protocol

For every DP-mandated component:
1. Copy HTML verbatim from `frontend/mockups/components/_<name>.html`
2. Bind `data-as-of` from the fixture's top-level `data_as_of`
3. Bind component-specific attrs per `components.html` contract
4. Never rewrite semantic class names or `data-component` values — the
   gate selectors are hard-coded to them

## Fixture usage

Pages fetch their data via `fetch('./fixtures/<name>.json')` — no
inline JSON. Hydration happens in a single `<script>` per page at the
bottom. No build step.

## Deliverable file pattern (every page chunk)

```
frontend/mockups/<page>.html          (the mockup)
frontend/mockups/fixtures/<page>.json (page-level fixture if the generic
                                       fixtures don't cover it)
tests/unit/fe_pages/test_<page>_structure.py  (DOM-level unit tests)
```

## Points of success (baseline — every page chunk must satisfy)

1. `html5validator frontend/mockups/<page>.html` exits 0
2. `python scripts/check-frontend-criteria.py --only <page-specific ids>,fe-g-*,fe-dp-*,fe-mob-<this-page>,fe-state-*,fe-c-*` exits 0
3. `pytest tests/unit/fe_pages/test_<page>_structure.py -v` green
4. Opening the page in a browser shows no console errors, no missing
   fixture 404s, no layout break at 360px
5. Playwright a11y (axe-core WCAG AA) on the rendered page: zero serious
   violations
6. Screenshot baseline captured at 1440px for S1-11 regression loop

## Post-chunk sync invariant (every page chunk)

`scripts/post-chunk.sh S1-<id>` green — forge-ship commit, forge-compile
into wiki, MEMORY.md append.
