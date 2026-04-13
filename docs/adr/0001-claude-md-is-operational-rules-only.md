# ADR 0001 — CLAUDE.md is an operational rulebook, not an encyclopedia

**Status:** Accepted (2026-04-13, chunk S4)
**Supersedes:** the pre-S4 ~356-line CLAUDE.md

## Context

Before S4, `CLAUDE.md` had grown to ~356 lines and carried shadow copies
of several documents:

- A V1 completion criteria list (13 items — the spec §24.3 actually has 15)
- A full Build Order V1→V10 block
- A Critical Schema Facts table
- A Data Flow section describing what comes from JIP vs what ATLAS owns
- A Technology Stack fork/pip/build breakdown
- An ATLAS-owned tables list
- A three-service architecture diagram

Every one of those was already authoritative somewhere else
(`ATLAS-DEFINITIVE-SPEC.md`, later `docs/specs/v1-criteria.yaml`). Every
one had drifted at least once. The FD chunks were the canary — they ran
with a CLAUDE.md whose V1 criteria count didn't match the spec, and nobody
noticed.

At the same time, every fresh chunk session's Step 0 boot is "read
CLAUDE.md first". Reading a 356-line file eats context budget before any
real work starts.

## Decision

`CLAUDE.md` is now a rulebook of ~80-120 lines. It contains only content
that is:

1. Non-negotiable rules that apply to every chunk (Four Laws, System
   Guarantees, project conventions, hard-stop conditions).
2. Protocol that the orchestrator/runner depends on (post-chunk sync
   invariant, Step 0 boot protocol, context discipline).
3. Pointers to the authoritative location of everything else.

Scope content lives in `ATLAS-DEFINITIVE-SPEC.md`. Schema facts, data
flow, and tech stack live in `docs/architecture/*.md` (see ADR-0002 and
ADR-0003). V1 completion criteria live in `docs/specs/v1-criteria.yaml`
(see ADR 0004 — coming when we write it).

## Consequences

- Every chunk's Step 0 boot is faster and cheaper.
- Drift is harder: if `CLAUDE.md` claims a number, it's a pointer, and
  the pointer either resolves or the architecture dim's
  `claude_md_present_and_live` check fires.
- Adding scope content to `CLAUDE.md` in future chunks is a review
  failure, not a stylistic preference.
