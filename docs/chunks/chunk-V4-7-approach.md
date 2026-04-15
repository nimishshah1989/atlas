# Chunk V4-7 Approach: Portfolio Dashboard Frontend

## Data Scale
Frontend-only chunk. No DB queries. All data from existing backend APIs.

## Chosen Approach
Pure TypeScript/React frontend with Next.js 16 App Router:
1. `frontend/src/lib/api-portfolio.ts` — typed API client mirroring backend Pydantic models
2. `frontend/src/app/pro/portfolio/page.tsx` — portfolio list page
3. `frontend/src/app/pro/portfolio/[id]/page.tsx` — portfolio detail dashboard
4. `frontend/src/app/page.tsx` — add Portfolio tab link

## Wiki Patterns Checked
- Next.js SSR/Browser BACKEND_BASE Split (staging) — resolves API base lazily; not needed here since NEXT_PUBLIC_API_URL is already set
- Extract Fixtures to Pass File-Size Gate — keep components lean, no giant fixtures files
- Next.js Proxy for File Uploads (anti-patterns) — CAMS import goes direct to backend URL

## Existing Code Being Reused
- `frontend/src/lib/api-simulate.ts` — fetchApi pattern (exact same pattern)
- `frontend/src/lib/format.ts` — formatCurrency, formatPercent, quadrantColor, quadrantBg, signColor
- `frontend/src/app/page.tsx` — tab switcher pattern, header layout

## Edge Cases
- Portfolio with no holdings: empty table, zero RS card, empty charts
- Holdings with null NAV/current_value: show "—" via formatCurrency null handling
- Attribution with null effects: show "—"
- Optimizer with empty models list: graceful degradation message
- CAMS import: file upload via FormData directly to backend (not Next.js proxy to avoid 1MB limit)
- API errors: caught and displayed as error state, not crashes

## Implementation Notes
- Use "use client" on both portfolio pages (interactive, client-side data fetching)
- Portfolio tab in page.tsx uses window.location.href navigation (not Next.js Link) per chunk spec advice for Next.js 16
- All ₹ values through formatCurrency
- CSV export: client-side blob download, no new packages
- Recharts PieChart for sector concentration
- Parallel fetches for analysis + attribution + optimize using Promise.all
- Sort state managed with useState, no external sort library needed

## Expected Runtime
No computation — pure UI rendering. API calls should return in <500ms per the backend benchmarks.
