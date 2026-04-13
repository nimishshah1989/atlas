# Chunk 2 — Roadmap spine + lint

**Depends on:** none (can run in parallel with Chunk 1)
**Blocks:** Chunk 3 (frontend needs non-empty roadmap data)
**Complexity:** S (<1h)
**PRD sections:** §6.2, §4 ("live roadmap" principle)

---

## Goal

Create the single source of truth for the V1–V10 roadmap tree, seeded with V1 fully (joined to existing C1–C11) and V2–V10 as goal-only placeholders. Add a lint script that prevents drift between `roadmap.yaml` and `plan.yaml`. The lint runs in pre-commit so drift can't be committed.

## Files

### New
- `orchestrator/roadmap.yaml` — canonical roadmap. V1 complete with chunks and step-level checks; V2–V10 with goal text and empty `chunks: []`.
- `orchestrator/roadmap_schema.py` — Pydantic v2 models for validation. Shared with `backend/core/roadmap_loader.py` in Chunk 1 (either re-exports or imports this — resolve in Chunk 1 implementation). Includes an optional `DemoGate` sub-model on the `Version` model — see the "demo_gate" amendment below.
- `scripts/roadmap-lint.py` — CLI lint. Usage: `python scripts/roadmap-lint.py`. Exits 0 on clean, non-zero with diagnostics on drift.
- `scripts/plan-to-roadmap.py` — writer companion to the lint. Given a `plan.yaml` chunk id and a target version (`--chunk C12 --version V2`), appends a skeleton `- id: C12\n  plan_ref: true` entry to `roadmap.yaml` under that version's `chunks:` list. Idempotent: if the chunk already exists under any version, exits 0 with "already present" message. Refuses to cross-assign (chunk already under a different version → error). This closes the loop so `scripts/tasks-to-plan.py` → `plan.yaml` → `plan-to-roadmap.py` → `roadmap.yaml` works without hand-editing YAML. Invoked automatically at the end of `scripts/tasks-to-plan.py` when that script's `--auto-roadmap` flag is set (wiring happens in this chunk — add the flag + invocation).
- `tests/scripts/test_roadmap_lint.py` — fixture with 3 deliberate drift cases, asserts lint catches 3/3.
- `tests/scripts/test_plan_to_roadmap.py` — tests the writer: add new chunk, idempotent re-add, cross-version conflict rejection, preserves YAML comments and formatting.

### Modified
- `.pre-commit-config.yaml` (if present) — add `roadmap-lint` hook. If not present, add a git pre-commit hook script in `scripts/hooks/`.

## `roadmap.yaml` structure

```yaml
# Canonical V1-V10 roadmap. Edit this file to add chunks; the dashboard
# picks them up automatically. Lint enforces consistency with plan.yaml.
versions:
  - id: V1
    title: "Market → Sector → Stock → Decision"
    goal: "FM navigates Market → Sector → Stock flow end-to-end; decisions tracked."
    chunks:
      - id: C1
        plan_ref: true         # must exist in plan.yaml
        steps:
          - id: C1.1
            text: ".quality/standards.md exists"
            check:
              type: file_exists
              path: .quality/standards.md
          - id: C1.2
            text: "quality checks run clean"
            check:
              type: command
              cmd: ["python", ".quality/checks.py", "--dry-run"]
      # ... C2 through C11 ...

  - id: V2
    title: "MF slice"
    goal: "Category → fund → holdings drill-down works end-to-end."
    demo_gate:                                   # optional; absent = no gate
      url: https://atlas.jslwealth.in/v2/mf
      walkthrough:
        - "Open MF category grid, verify 38 categories render with RS scores."
        - "Drill into 'Large Cap Growth', verify holdings list loads."
        - "Click into HDFC Top 100, verify deep-dive tabs populate."
    chunks: []

  - id: V3
    title: "Simulation slice"
    goal: "VectorBT + Indian FIFO tax + QuantStats tear sheets."
    chunks: []

  # ... V4 through V10 with goal text lifted from CLAUDE.md Build Order section ...
```

**Rules encoded in YAML schema:**
- `id` for versions must match `^V\d+$`.
- `id` for chunks must match `^C\d+$`.
- `id` for steps must match `^C\d+\.\d+$` and prefix must match parent chunk id.
- `check.type` ∈ {`file_exists`, `command`, `http_ok`, `db_query`, `smoke_list`}.
- `command` field must be a list of strings (never a shell string).
- `path` fields must be relative, no `..`.
- `future: true` on a chunk = allowed to exist in roadmap without being in plan.yaml (for chunks that are planned but not yet dispatched to the orchestrator).
- `slow: true` on a step = only evaluated when endpoint called with `?evaluate_slow=true`. (`smoke_list` steps are implicitly slow — always, without needing the flag in the YAML.)
- **`demo_gate`** (optional, per version): `DemoGate` sub-model with required `url: str` and `walkthrough: list[str]` (min 1 item). Shape validation only at this chunk — the runner side (DEMO_PENDING state, `unblock --approve` CLI, frontend banner) is deferred to the follow-up chunk specced in `docs/specs/version-demo-gate.md`. Adding the field now means that follow-up chunk is zero-migration: every `roadmap.yaml` in git history already parses. Lint rejects a `demo_gate` with missing `url` or empty `walkthrough`.

## Seed content — V2 through V10 goal text

Lift from `CLAUDE.md` "Build Order — Vertical Slices":
- **V2** MF slice — "Category → fund → holdings drill-down."
- **V3** Simulation — "VectorBT + tax + QuantStats."
- **V4** Portfolio — "casparser + Riskfolio-Lib + attribution."
- **V5** Intelligence — "Briefings, debate, Darwinian evolution."
- **V6** TradingView — "MCP bridge, charts, bidirectional sync."
- **V7** ETF + Global — "ETF and global instrument coverage."
- **V8** Advisor shell — "Advisor experience surface."
- **V9** Retail shell — "Retail MF investor surface."
- **V10** Qlib + Advanced — "Alpha158, ML models, parameter optimization."

## `scripts/roadmap-lint.py` behavior

Parses `orchestrator/plan.yaml` and `orchestrator/roadmap.yaml`. Checks:

1. **Every chunk in `plan.yaml` is claimed by exactly one version in `roadmap.yaml`.** Unclaimed chunks = error.
2. **Every chunk in `roadmap.yaml` without `future: true` exists in `plan.yaml`.** Missing = error.
3. **Chunk ids are unique across the whole roadmap.**
4. **Version ids are V1–V10 exactly.** Out-of-range or missing = error.
5. **`check:` specs validate against the Pydantic schema.** Bad check type or missing fields = error.
6. **`command:` is a list, never a string.** Shell strings = error.

On error: prints a diagnostic table and exits 1. On clean: prints `roadmap OK: 10 versions, N chunks, M steps` and exits 0.

## Acceptance criteria

1. `orchestrator/roadmap.yaml` exists with V1 populated (C1–C11 from current `plan.yaml`, each with at least one step) and V2–V10 as goal-only stubs with empty `chunks: []`. Each version V2+ also carries one optional `smoke_list` step that points at `scripts/smoke-endpoints.txt` so the slice-health chip has data.
2. `python scripts/roadmap-lint.py` exits 0 on the seeded file.
3. Test fixture with 3 drift cases: (a) chunk in `plan.yaml` not claimed by any V, (b) chunk in `roadmap.yaml` without `future: true` that doesn't exist in `plan.yaml`, (c) a `command: "rm -rf /"` shell string. Lint catches 3/3 with non-zero exit.
4. Pydantic schema rejects: invalid `id` format, `path` with `..`, unknown `check.type`, `command` as string, `demo_gate` with missing `url`, `demo_gate` with empty `walkthrough`.
5. Pre-commit hook (or `.pre-commit-config.yaml` entry) wires the lint so `git commit` on a drifted `roadmap.yaml` fails.
6. `pytest tests/scripts/test_roadmap_lint.py tests/scripts/test_plan_to_roadmap.py -v` passes.
7. Lint runs in <1s on the full seeded roadmap.
8. `python scripts/plan-to-roadmap.py --chunk C99 --version V2` on a clean tree appends a skeleton `- id: C99\n  plan_ref: true` under V2's `chunks:` list, preserves the file's existing comments and formatting, and exits 0. Re-running the same command exits 0 with "already present" and no file change. Attempting to add the same chunk under `V3` after it's already under `V2` exits non-zero.
9. `scripts/tasks-to-plan.py --auto-roadmap <tasks.json>` invokes `plan-to-roadmap.py` for every new chunk, so the forge-build Phase 2 → orchestrator pipeline ends with both `plan.yaml` AND `roadmap.yaml` updated in one step.
10. Pydantic `DemoGate` sub-model exists on the `Version` model as `Optional[DemoGate]`, absent by default. V2's seeded entry has a populated `demo_gate` (from `docs/specs/version-demo-gate.md`); V3–V10 do not.

## Out of scope

- Executing `check:` specs at lint time — lint only validates shape, never runs commands. (Execution happens at endpoint request time in Chunk 1.)
- Adding V2 real chunks. V2 chunks get written later when the user plans V2.
- Wiring lint into CI (GitHub Actions) — pre-commit is enough for v1. CI can come later if needed.
