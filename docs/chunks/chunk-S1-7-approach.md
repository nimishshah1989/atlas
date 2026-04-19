---
chunk: S1-7
project: atlas
date: 2026-04-19
title: Navigation + root redirect + build gate
---

## Actual data scale
No database access — pure frontend chunk. No tables touched.

## Chosen approach

### TopNav component
- "use client" component with `usePathname()` from `next/navigation`
- 6 static nav items defined as const array inside the component
- Active detection via custom `isActive()` helper that handles the
  `/funds/rank` vs `/funds/[id]` disambiguation and `/stocks/HDFCBANK` prefix match
- CSS variables only: `--bg-surface`, `--border-default`, `--accent-700`,
  `--text-primary`, `--text-secondary`
- Sticky header via inline style `position: sticky; top: 0; zIndex: 30`
- Mobile hamburger: `React.useState<boolean>(false)` toggle, link row
  hidden below `md` breakpoint via Tailwind `hidden md:flex`
- Next.js `Link` for navigation, no custom router logic

### layout.tsx update
- Server component (no "use client") — imports TopNav client component
  which React handles transparently
- Add `<TopNav />` above `{children}` inside `<body>`

### page.tsx replacement
- Simple server component using `redirect("/pulse")` from `next/navigation`
- No "use client", no hooks — server-side redirect only

### Test file
- Jest + @testing-library/react following S1-6 conventions (rank test pattern)
- Mock `next/navigation` with `usePathname` as jest.fn()
- Mock `next/link` using `jest.requireActual("react")` inside factory
  (jest-mock-factory-no-outer-scope-refs pattern from wiki — S1-5)
- 5 tests:
  1. Renders all 6 nav link labels
  2. /pulse link is active when pathname is "/pulse"
  3. /breadth link is active when pathname is "/breadth"
  4. Hamburger button exists (mobile menu toggle)
  5. TopNav has sticky positioning

## Wiki patterns checked
- `jest-mock-factory-no-outer-scope-refs` (S1-5): factory body cannot ref outer React — use `jest.requireActual("react")` inside
- `useatlasdata-get-post-split` — N/A (no data fetching in this chunk)
- General S1 test file conventions from rank test (S1-6)

## Existing code being reused
- S1-6 test pattern: `jest.mock("next/link", ...)` with requireActual pattern
- globals.css CSS variable tokens already defined (--bg-surface, --border-default, etc.)

## Edge cases
- `/funds/rank` must NOT activate when on `/funds/[id]` and vice versa
- Home redirect: `redirect()` throws internally in Next.js; test by mocking and checking call
- Hamburger state: closes properly when nav item clicked (nice-to-have, not tested)

## Expected runtime
- `npm test` for this file: < 5s
- `npm run build`: < 60s (already passes with prior chunks)
- No new npm packages added
