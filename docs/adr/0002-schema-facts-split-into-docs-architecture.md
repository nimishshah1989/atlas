# ADR 0002 — Schema facts / data flow / tech stack live in docs/architecture/

**Status:** Accepted (2026-04-13, chunk S4)
**Depends on:** ADR-0001

## Context

S4 stripped `CLAUDE.md` to an operational rulebook. Three blocks needed a
new home:

1. **Critical Schema Facts** — the "spec v2 was WRONG" table of actual
   column names. Every query author needs this before writing SQL.
2. **Data Flow** — what comes from JIP, what ATLAS computes, what ATLAS
   owns. The single most-referenced diagram during V1 build.
3. **Technology Stack** — the fork/pip-install/build-in-house breakdown.
   Answers "should I write this or import it?"

None of these are "operational rules" (so they don't belong in
`CLAUDE.md`) and none are "full spec" (so they don't belong in
`ATLAS-DEFINITIVE-SPEC.md` — the spec is sacrosanct and versioned).

## Decision

New home: `docs/architecture/`. Three files, each a verbatim move from the
pre-S4 `CLAUDE.md`:

- `docs/architecture/critical-schema-facts.md`
- `docs/architecture/data-flow.md`
- `docs/architecture/tech-stack.md`

`CLAUDE.md` links to all three from its Source-of-truth pointers section.

## Consequences

- Git history on these docs is clean — they get their own blame lines
  instead of drowning in `CLAUDE.md` churn.
- Future chunks that need to update schema facts edit the architecture
  doc, not `CLAUDE.md`, so they don't collide with every other chunk
  touching the rulebook.
- The architecture dim's "ADR count ≥ 3" check now has real ADRs behind
  it instead of leaning on the `## ` section count in `CLAUDE.md`.
