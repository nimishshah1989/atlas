# ATLAS Forge Orchestrator

Stateless-worker orchestrator that drives chunks of work through a state machine,
spawning fresh `claude` sessions for each chunk and gating completion on the
quality engine in `.quality/`.

## Why

V1 of ATLAS shipped without a real quality bar. V1.5 retrofits that bar (`.quality/checks.py`)
and then runs every subsequent chunk through this orchestrator, so:

- Each chunk gets a fresh Claude context (no cross-chunk state pollution).
- No chunk is marked DONE until the quality gate passes.
- Failures retry automatically up to `settings.retry.max_attempts`.
- The full audit trail (state transitions, quality runs, sessions) lives in SQLite.

## Layout

```
orchestrator/
├── plan.yaml             # source of truth for chunk identity + dependencies
├── schema.sql            # SQLite schema (chunks, transitions, quality_runs, sessions)
├── state.py              # state-store wrapper
├── plan_loader.py        # YAML → state DB sync
├── state_machine.py      # legal transitions + next-ready selection
├── prompts.py            # Claude prompt templates
├── runner.py             # main runner (spawn + gate + transition)
├── cli.py                # `python -m orchestrator.cli ...`
├── logging_config.py     # structlog setup
├── systemd/
│   └── atlas-forge.service
├── logs/                 # per-chunk subprocess logs (gitignored)
└── state.db              # SQLite (gitignored)
```

## State machine

```
PENDING → PLANNING → IMPLEMENTING → TESTING → QUALITY_GATE → DONE
              ↓           ↓             ↓            ↓
              └───────────┴─────────────┴────────────┘
                                ↓
                              FAILED → (retry) PLANNING
                                  ↓
                              BLOCKED  (manual unblock with `forge unblock`)
```

## CLI

```bash
# from repo root
python -m orchestrator.cli sync             # load plan.yaml into state.db
python -m orchestrator.cli status           # table view
python -m orchestrator.cli status --json    # machine-readable
python -m orchestrator.cli show C5          # chunk + latest quality run
python -m orchestrator.cli run              # run next ready chunk
python -m orchestrator.cli run --all        # run until none ready
python -m orchestrator.cli run C5           # force-run a specific chunk
python -m orchestrator.cli run --dry-run    # don't spawn claude or score
python -m orchestrator.cli unblock C7       # BLOCKED → PENDING
```

## systemd

```bash
sudo cp orchestrator/systemd/atlas-forge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now atlas-forge.service
sudo journalctl -u atlas-forge -f
```

## Quality gate

The runner shells out to `python .quality/checks.py --gate` after every chunk
attempt. A chunk passes when:

1. `overall_score ≥ settings.quality.min_overall`
2. Every dimension meets `settings.quality.min_dimensions`
3. Every dimension in the chunk's `quality_targets` meets that target

Otherwise the attempt is recorded as FAILED and retried up to
`settings.retry.max_attempts` times before going BLOCKED.

## Bootstrap chunks

C1–C4 are marked `bootstrap: true` in `plan.yaml`. They built the orchestrator
itself and so cannot have run through it. From C5 onward every chunk runs here.

## What this does NOT do

- It does not edit `plan.yaml`. The plan is human-curated.
- It does not edit `.quality/standards.md` or `.quality/checks.py`.
- It does not push to git. A separate skill handles commits.
- It does not manage credentials. Inherits the calling user's environment.
