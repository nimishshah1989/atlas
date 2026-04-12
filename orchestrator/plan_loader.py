"""Load and validate orchestrator/plan.yaml; sync into the state DB.

The plan file is the source of truth for chunk identity, title, dependencies,
and quality targets. The state DB is the source of truth for *runtime* state
(status, attempts, history). Loading reconciles the two without clobbering
runtime state of chunks the operator has not modified in the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from . import state_machine as sm
from .state import StateStore


@dataclass
class ChunkSpec:
    id: str
    title: str
    status: str
    depends_on: list[str] = field(default_factory=list)
    bootstrap: bool = False
    quality_targets: dict[str, int] = field(default_factory=dict)
    punch_list: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)


@dataclass
class Plan:
    version: str
    name: str
    settings: dict[str, Any]
    chunks: list[ChunkSpec]


class PlanError(Exception):
    pass


def load_plan(plan_path: Path) -> Plan:
    raw = yaml.safe_load(Path(plan_path).read_text())
    if not isinstance(raw, dict):
        raise PlanError("plan.yaml root must be a mapping")

    version = str(raw.get("version") or "")
    name = str(raw.get("name") or "")
    settings = raw.get("settings") or {}
    chunks_raw = raw.get("chunks") or []

    if not version:
        raise PlanError("plan.yaml missing 'version'")
    if not isinstance(chunks_raw, list) or not chunks_raw:
        raise PlanError("plan.yaml must contain a non-empty 'chunks' list")

    seen_ids: set[str] = set()
    chunks: list[ChunkSpec] = []
    for entry in chunks_raw:
        if not isinstance(entry, dict):
            raise PlanError(f"chunk entry must be a mapping: {entry!r}")
        cid = entry.get("id")
        if not cid or not isinstance(cid, str):
            raise PlanError(f"chunk missing string id: {entry!r}")
        if cid in seen_ids:
            raise PlanError(f"duplicate chunk id: {cid}")
        seen_ids.add(cid)
        status = entry.get("status") or sm.PENDING
        if status not in sm.STATES:
            raise PlanError(f"chunk {cid}: unknown status {status!r}")
        chunks.append(
            ChunkSpec(
                id=cid,
                title=str(entry.get("title") or cid),
                status=status,
                depends_on=list(entry.get("depends_on") or []),
                bootstrap=bool(entry.get("bootstrap", False)),
                quality_targets=dict(entry.get("quality_targets") or {}),
                punch_list=list(entry.get("punch_list") or []),
                artifacts=list(entry.get("artifacts") or []),
            )
        )

    # Validate dependency references.
    for c in chunks:
        for dep in c.depends_on:
            if dep not in seen_ids:
                raise PlanError(
                    f"chunk {c.id} depends on unknown chunk {dep}"
                )

    return Plan(version=version, name=name, settings=settings, chunks=chunks)


def sync_plan_to_state(plan: Plan, store: StateStore) -> dict[str, str]:
    """Insert new chunks; refresh metadata for existing ones.

    Runtime status is preserved for chunks already known to the DB UNLESS the
    plan declares them as bootstrap=True with an explicit status, in which case
    we honor the plan (this lets C1-C4 mark themselves DONE/IN_PROGRESS).

    Returns a map of chunk_id → final status.
    """
    final: dict[str, str] = {}
    for spec in plan.chunks:
        existing = store.get_chunk(spec.id)
        store.upsert_chunk(
            chunk_id=spec.id,
            title=spec.title,
            status=spec.status if existing is None else existing["status"],
            plan_version=plan.version,
            depends_on=spec.depends_on,
        )
        if spec.bootstrap and (existing is None
                               or existing["status"] != spec.status):
            # Bootstrap chunks: plan wins.
            current = (existing or {}).get("status")
            if current != spec.status:
                _force_status(store, spec.id, spec.status,
                              reason="bootstrap sync")
        final[spec.id] = store.get_chunk(spec.id)["status"]
    return final


def _force_status(
    store: StateStore, chunk_id: str, new_status: str, reason: str
) -> None:
    """Bypass state machine validation for bootstrap reconciliation only."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with store.tx() as c:
        row = c.execute(
            "SELECT status FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        old = row["status"] if row else None
        c.execute(
            "UPDATE chunks SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, chunk_id),
        )
        c.execute(
            """INSERT INTO transitions
               (chunk_id, from_state, to_state, reason, at)
               VALUES (?, ?, ?, ?, ?)""",
            (chunk_id, old, new_status, reason, now),
        )


def find_spec(plan: Plan, chunk_id: str) -> Optional[ChunkSpec]:
    for c in plan.chunks:
        if c.id == chunk_id:
            return c
    return None
