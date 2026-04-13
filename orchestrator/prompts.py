"""Prompt templates for chunk-execution Claude sessions.

Each chunk gets ONE Claude session per attempt. The prompt contains the chunk
spec, the punch list, current quality scores, and explicit success criteria
(must pass quality gate at the configured thresholds). Claude is responsible
for planning + implementing + testing within that single session.
"""

from __future__ import annotations

import json
from typing import Any

from .plan_loader import ChunkSpec, Plan


CHUNK_PROMPT = """\
You are running as a stateless worker in the ATLAS forge orchestrator.
This is chunk **{chunk_id}**: {title}

# STEP 0 — Boot context (MANDATORY before any other action)

You start with zero memory of prior chunks. Before you plan, implement,
or edit a single file you MUST load the project's persistent context so
you know what has already been built, decided, and learned. Read, in
order:

1. `CLAUDE.md` at repo root — the authoritative architect file. Full
   spec pointer, Four Laws, schema facts, build order, conventions, and
   the **post-chunk sync invariant**.
2. `~/.claude/projects/-home-ubuntu-atlas/memory/MEMORY.md` — the
   auto-memory index. One line per prior memory file. Open every memory
   file whose description looks relevant to this chunk's punch list,
   especially `project_v15_chunk_status.md` (the running chunk ledger)
   and any `feedback_*.md` that applies to files you will touch.
3. `~/.forge/knowledge/wiki/index.md` — the cross-project pattern wiki.
   Identify patterns relevant to THIS chunk's files and tech, then read
   ONLY those specific articles. Do NOT read the entire wiki.
4. `ATLAS-DEFINITIVE-SPEC.md` — only the sections your punch list
   touches. Use the table of contents; do not read end-to-end.

If any of those files is missing, HALT and report — do not proceed with
stale context.

# Context
- Repo: {repo_root}
- Plan: orchestrator/plan.yaml (read-only — DO NOT edit)
- Quality engine: .quality/checks.py (run with --gate to verify)
- Standards: .quality/standards.md
- This chunk's attempt number: {attempt}
- Previous attempt error (if any): {last_error}

# Latest quality report
Overall: {overall_score}/100
Per-dimension scores: {dimension_scores}

# Punch list (what THIS chunk must deliver)
{punch_list}

# Quality targets — gate will block DONE until ALL of these are met
{quality_targets}

Global minimums (from plan settings):
- Overall ≥ {min_overall}
- Per-dimension floors: {min_dimensions}

# Rules
1. You may only modify files relevant to this chunk's punch list.
2. Run `python .quality/checks.py --gate` before declaring done.
3. Do not edit orchestrator/plan.yaml or .quality/standards.md.
4. Follow ATLAS conventions in CLAUDE.md (Decimal not float, async, etc.)
5. When you finish, write a single line to stdout:
       FORGE_CHUNK_COMPLETE {chunk_id}
   The runner watches for this sentinel.

Begin.
"""


def build_chunk_prompt(
    plan: Plan,
    spec: ChunkSpec,
    *,
    attempt: int,
    last_error: str | None,
    quality_report: dict[str, Any] | None,
) -> str:
    settings = plan.settings.get("quality", {})
    min_overall = settings.get("min_overall", 80)
    min_dims = settings.get("min_dimensions", {})

    if quality_report:
        overall = quality_report.get(
            "overall", quality_report.get("overall_score", "?")
        )
        from .runner import _dims_to_dict

        dims_map = _dims_to_dict(quality_report.get("dimensions"))
        dim_scores = (
            ", ".join(f"{k}={v}" for k, v in sorted(dims_map.items())) or "(none)"
        )
    else:
        overall = "(no prior run)"
        dim_scores = "(no prior run)"

    punch = (
        "\n".join(f"- {punch_item}" for punch_item in spec.punch_list)
        if spec.punch_list
        else "(none — see plan.yaml)"
    )
    targets = (
        "\n".join(f"- {k}: ≥ {v}" for k, v in spec.quality_targets.items())
        if spec.quality_targets
        else "(use global minimums only)"
    )

    return CHUNK_PROMPT.format(
        chunk_id=spec.id,
        title=spec.title,
        repo_root=plan.settings.get("repo_root", "."),
        attempt=attempt,
        last_error=last_error or "(none)",
        overall_score=overall,
        dimension_scores=dim_scores,
        punch_list=punch,
        quality_targets=targets,
        min_overall=min_overall,
        min_dimensions=json.dumps(min_dims),
    )
