# Chunk 3 — Frontend Redesign: Approach

## Data scale
No database queries. All data comes from 4 HTTP endpoints at localhost:8010. Confirmed live:
- `/api/v1/system/heartbeat` — 12 fields, all nullable timestamps + integers
- `/api/v1/system/roadmap` — versions array (V1 has 11 chunks), each chunk has steps
- `/api/v1/system/quality` — 7 dimensions (security, code, architecture, api, frontend, devops, docs)
- `/api/v1/system/logs/tail` — array of strings

## Chosen approach

### Architecture
- `frontend/src/lib/systemClient.ts` — pure fetch wrappers, TS interfaces from live JSON
- New components: HeartbeatStrip, RoadmapTree, VersionCard, StepCheckRow
- Route handler `/forge/api/route.ts` — thin proxy, zero fs imports
- Middleware at `/forge/*` for optional token gate
- ForgeDashboard reordered: HeartbeatStrip → RoadmapTree → QualityScores → ContextFiles → LogTail

### Middleware (Next.js 16.2.3)
- `NextResponse.next()` for pass-through
- `response.cookies.set()` for setting HttpOnly cookie on successful token auth
- Cookie options: `httpOnly: true, secure: true, sameSite: 'strict', maxAge: 604800`
- Standard `config.matcher` — identical syntax in Next.js 16

### forgeContext.ts
Has `fs` imports (`readdirSync`, `statSync`) but runs only in Node.js runtime (never in Edge).
Since it's imported in `/forge/api/route.ts` (a Route Handler, not middleware), it runs in Node.js.
Strategy: keep `forgeContext.ts` as-is (it's correct), just don't import it from middleware.
The route handler that calls `listContextFiles()` will be kept but the main route rewrite removes this.
After rewrite: `forgeContext.ts` is no longer imported in `/forge/api/route.ts` since backend owns fs.
We keep the file but it becomes unused — acceptable, no deletion required by spec.

### Wiki patterns checked
- Next.js middleware: standard pattern, confirmed API stable in 16.x
- No wiki articles specifically for Next.js frontend patterns in forge wiki

### Existing code reused
- `ChunkTable.tsx` — kept, becomes secondary "Flat view" tab
- `ContextFiles.tsx` — kept, demoted (collapsed by default, smaller header)
- Status color maps from ChunkTable reused in RoadmapTree
- `formatRelative` from ContextFiles reused in HeartbeatStrip (inline copy)

### Edge cases
- All heartbeat fields nullable — gray state when null
- Smoke chip: null fields → "Smoke · —" neutral gray
- Quality scores null → empty state message
- Roadmap empty chunks array → "PLANNED · 0 chunks" card
- Step check values: ok | fail | slow-skipped | error — all handled with icon map

## Expected runtime
- All operations are HTTP fetches to localhost. Under 200ms per call.
- Heartbeat polling every 30s — trivial CPU.
- Build: `npm run build` expected under 60s on t3.large.
