# Version demo gate — spec for a future orchestrator chunk

**Status:** SPEC — not yet built. Tracked as a candidate chunk to land after
the forge-dashboard rebuild (FD-1…FD-4) is in. Created 2026-04-13.

## Why this exists

The V1.5 retrofit and the forge dashboard together answer two questions:
"are the chunks green?" (quality gate) and "is the system still responsive?"
(heartbeat + live step checks). Neither answers the third, most important
question for a multi-version build: **is ATLAS actually coming to life, or
are we shipping disconnected parts?**

Without a human-in-the-loop checkpoint at version boundaries, the
orchestrator will happily roll from V2 into V3 while a subtle interface
mismatch sits inside the V2 slice that no automated check catches. The smoke
probe added in this retrofit catches *endpoint-level* regressions
(`scripts/smoke-probe.sh`), but it cannot tell whether a feature is
*usefully* alive — only whether it returns 2xx.

The version demo gate is the answer: a hard stop at the end of every V (V2,
V3, V4, …) that requires a human to walk the vertical slice in a browser and
explicitly unblock the gate before any V+1 chunk can run.

## Shape

### Plan.yaml — new field on a chunk

```yaml
- id: V2-DEMO
  title: "V2 demo gate — walk the MF slice end-to-end"
  status: PENDING
  depends_on: [V2-1, V2-2, …, V2-N]   # every V2 chunk
  gate_type: human_demo
  demo:
    url: https://atlas.jslwealth.in/v2/mf
    walkthrough:
      - "Open MF category grid, verify 38 categories render with RS scores."
      - "Drill into 'Large Cap Growth', verify holdings list loads."
      - "Click into HDFC Top 100, verify deep-dive tabs populate."
    approval_token: V2_DEMO_APPROVED
```

### Runner.py — new transition

When the runner picks up a chunk with `gate_type: human_demo`, it does NOT
spawn a Claude worker. Instead it:

1. Transitions PENDING → DEMO_PENDING.
2. Writes the walkthrough bullets to `orchestrator/demo-queue/<chunk_id>.md`
   along with the URL and a blocked-since timestamp.
3. Posts to the forge dashboard's /roadmap endpoint so the frontend shows a
   "🛑 HUMAN DEMO REQUIRED — V2 MF slice" banner.
4. Exits. The runner does NOT retry, does NOT mark FAILED. It just waits.

To unblock:

```bash
python -m orchestrator.cli unblock V2-DEMO --approve "Reviewed 2026-05-10, all 3 steps work"
```

The `unblock --approve` subcommand is new. It:
- Transitions DEMO_PENDING → DONE.
- Records the approver's note in `transitions.reason`.
- Records the approval wall-clock so retros can measure gate latency.
- Does NOT run the quality gate (there's nothing to score — the chunk
  produced no code).

### State machine — new state

Add `DEMO_PENDING` to `orchestrator/state_machine.py` STATES. Transitions:

```
PENDING → DEMO_PENDING     (runner picks up gate_type chunk)
DEMO_PENDING → DONE        (human unblock --approve)
DEMO_PENDING → BLOCKED     (human unblock --reject "broke: <reason>")
```

BLOCKED → PENDING is only allowed after the underlying V2 chunks are
re-run to fix whatever the human found.

## What it catches that nothing else does

- **Interface drift** between V2 backend and V2 frontend that happens to
  return 2xx but displays wrong data.
- **Data pipeline desync** where V2 ships with yesterday's NAVs and no one
  notices because the heartbeat is green.
- **Cognitive load regressions** — a slice that technically works but is
  unusable because you can't find anything. Only a human walking it catches
  this.
- **The "100 chunks, dead product" failure mode** — the exact thing the user
  is worried about.

## What it costs

- ~5 minutes of human time per version boundary (10 boundaries across V2→V10
  = ~50 min total across the whole build).
- Orchestrator latency: however long it takes the human to notice the banner
  and run `unblock --approve`. Mitigated by Slack/email notification in a
  later enhancement.

## Dependencies

- `orchestrator/roadmap.yaml` (forge dashboard chunk FD-2) — the demo gate
  chunk references a V-level id, so the roadmap must understand V grouping.
- Forge dashboard frontend (FD-3) must render the "🛑 HUMAN DEMO REQUIRED"
  banner when any chunk is in DEMO_PENDING.
- `scripts/post-chunk.sh` — already wired for smoke probe; no changes needed
  for demo gate (demo chunks have no deploy phase).

## Out of scope for this chunk

- Automated walkthrough via Playwright (that would defeat the purpose — the
  point is a human eye).
- Notifications — Slack / email on DEMO_PENDING entry. Add later.
- Approval audit log UI — the raw `transitions` table is enough for now.

## Implementation size

~120 LoC across `orchestrator/state_machine.py`, `orchestrator/runner.py`,
`orchestrator/cli.py`, plus a simple frontend card in the forge dashboard.
One medium chunk. Build after FD-1…FD-4 are in — the dashboard frontend
needs to already be rendering the roadmap to show the gate banner.
