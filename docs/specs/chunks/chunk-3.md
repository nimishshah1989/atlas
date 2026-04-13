# Chunk 3 — Frontend redesign

**Depends on:** Chunk 1 (backend endpoints live), Chunk 2 (`roadmap.yaml` seeded)
**Blocks:** Chunk 4
**Complexity:** L (2–4h)
**PRD sections:** §6.4, §7

---

## Goal

Redesign `/forge` as a PM view. Replace the flat chunk table with a heartbeat strip on top and a V1–V10 roadmap tree as the primary panel. Repoint Quality and LogTail panels at the new backend endpoints. Stop reading the filesystem directly from Next.js. Add middleware token check for shared-link access.

## Files

### New
- `frontend/src/components/forge/HeartbeatStrip.tsx` — sticky **6-chip** header (MEMORY.md, Wiki, state.db, Quality, Backend, **Last smoke**). Amber >1h, red >6h or any hard fail on the smoke chip. The smoke chip reads `last_smoke_run_at` + `last_smoke_result` + `last_smoke_summary` from the `/heartbeat` endpoint (fields added in Chunk 1) — e.g. `"Smoke · 3/3 green · 12m ago"`. This is the "ATLAS is actually coming to life" signal: chunks can be green while the product is dead, and this chip catches that. Polls `/api/v1/system/heartbeat` every 30s on the client.
- `frontend/src/components/forge/RoadmapTree.tsx` — collapsible V1–V10 cards. Expand → chunks. Expand chunk → steps with live ✓/✗. Uses `/api/v1/system/roadmap`.
- `frontend/src/components/forge/VersionCard.tsx` — one version row. Shows rollup (`V1 · 11/11 · 100%`). Click to expand.
- `frontend/src/components/forge/StepCheckRow.tsx` — one step with status dot, text, and tooltip for `detail:` on failure.
- `frontend/src/lib/systemClient.ts` — thin fetch wrappers for the 4 backend endpoints. Shared types lifted from the Pydantic contracts in Chunk 1 (define as TS interfaces that match PRD §7).
- `frontend/src/middleware.ts` — runs on `/forge/*`. If `FORGE_SHARE_TOKEN` env is set, require `?token=X` matching it (or `forge_token` cookie). Otherwise pass.

### Modified
- `frontend/src/app/forge/page.tsx` — update layout order: HeartbeatStrip → RoadmapTree → QualityScores → ContextFiles → LogTail. Keep `force-dynamic`.
- `frontend/src/app/forge/api/route.ts` — rewrite as thin proxy to backend. **Remove all `fs` imports.** Single `fetch` to `http://localhost:8010/api/v1/system/<path>` per call.
- `frontend/src/components/forge/ForgeDashboard.tsx` — swap panel order and imports.
- `frontend/src/components/forge/QualityScores.tsx` — repoint data source to `systemClient.getQuality()`. Restructure as 3 primary tiles (Architecture/Code/Security) + 4 secondary tiles. Show `as_of` prominently.
- `frontend/src/components/forge/LogTail.tsx` — repoint to `systemClient.getLogsTail(200)`.
- `frontend/src/components/forge/ContextFiles.tsx` — minor: demote visually (smaller headers, collapsed by default).
- `frontend/src/components/forge/ChunkTable.tsx` — kept as a secondary "flat view" tab; not primary. Add a simple tab toggle at the top of RoadmapTree: `[Roadmap | Flat]`.
- `frontend/src/lib/forgeContext.ts` — if it has `fs` calls, either move them behind a Node-runtime check or delete (backend owns fs now).

## Design / visual spec

- **Heartbeat strip:** full-width, `h-12`, sticky top. Six chips (MEMORY / Wiki / state.db / Quality / Backend / Smoke) with pill shape, monospace time-ago, subtle border. Teal (#1D9E75) for fresh, amber for >1h, red for >6h. Smoke chip also turns red on any hard-fail result regardless of age. Chip label + "Xm ago" + dot. On narrow viewports the strip wraps to two rows; never hide chips.
- **Roadmap tree:** cards with `border border-gray-200 rounded-lg`, white background, teal accent on expanded state. Version header shows id, title, rollup (`9/11 · 82%`), and status chip. Chunk rows indented, with small chunk id badge, status dot, title, and `Xh ago` from `updated_at`. Step rows further indented with icon (✓ green, ✗ red, ⋯ gray for slow-skipped, ⚠ amber for error).
- **Quality tiles:** three large cards in a row for Architecture / Code / Security. Each shows score (big number), dimension name, and `as_of`. Four smaller cards below for Frontend / DevOps / Docs / API.
- **Polish target:** Linear / Vercel dashboard feel. Data-dense, no wasted space, readable at a glance.

## Middleware token check

```ts
// frontend/src/middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(req: NextRequest) {
  const expected = process.env.FORGE_SHARE_TOKEN;
  if (!expected) return NextResponse.next();            // dev mode: open
  const provided = req.nextUrl.searchParams.get('token')
                   ?? req.cookies.get('forge_token')?.value;
  if (provided !== expected) {
    return new NextResponse('Unauthorized', { status: 401 });
  }
  return NextResponse.next();
}

export const config = { matcher: ['/forge/:path*'] };
```

On successful token, set `forge_token` cookie so subsequent loads don't need the query param. Cookie: `HttpOnly`, `Secure`, `SameSite=Strict`, 7-day expiry.

## State & data fetching strategy

- Server Component fetches all 4 endpoints in parallel on initial render (fresh data, no client waterfall).
- Client-side revalidation via `useEffect` polling every 30s for `/heartbeat` and `/logs/tail` only (the cheap, frequent-change ones). Roadmap and quality fetched fresh on full page reload (user-initiated via browser refresh — matches "post-chunk only" cadence).
- Cache headers: all client fetches use `cache: 'no-store'`.

## Acceptance criteria

1. `/forge` page loads in <3s on a warm backend. Heartbeat strip shows 6 chips (MEMORY / Wiki / state.db / Quality / Backend / Smoke), all with fresh timestamps. Smoke chip shows `"Smoke · N/M green · Xm ago"` when data is available, or `"Smoke · —"` when no smoke log exists yet.
2. Roadmap tree shows V1 with 11 chunks expandable. V2–V10 show as "PLANNED · 0 chunks" cards.
3. Expanding a chunk shows its steps with ✓/✗ icons matching backend `check` field.
4. Quality panel shows Architecture / Code / Security as the three biggest tiles, with `as_of` timestamp visible.
5. `grep -r "from 'fs'" frontend/src/app/forge/` returns zero matches.
6. Middleware test: `FORGE_SHARE_TOKEN=abc` env → `/forge` without token returns 401; `/forge?token=abc` returns 200 and sets cookie; next request without query param but with cookie returns 200.
7. Middleware test: `FORGE_SHARE_TOKEN` unset → `/forge` returns 200 regardless of token.
8. "Flat" tab still shows C1–C11 list (backward compat for power users).
9. Visual check in browser at `localhost:3000/forge` — layout matches PRD §6.4 order, polish acceptable for sharing with stakeholder.
10. `npm run build` in `frontend/` succeeds with zero errors and zero new warnings beyond baseline.
11. `npm run lint` in `frontend/` clean.
12. No `any` types in new `.tsx` / `.ts` files.

## Out of scope

- Systemd unit and post-chunk hook wiring (Chunk 4).
- Any backend changes beyond what Chunk 1 delivered.
- Adding new quality check types.
- Historical charts / sparklines — cut by PRD §3.
