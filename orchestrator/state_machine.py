"""Forge orchestrator state machine.

States are represented as plain strings (cheap, debuggable, JSON-friendly).
Transitions are validated against ALLOWED below — anything else raises.

Lifecycle (happy path):
    PENDING → PLANNING → IMPLEMENTING → TESTING → QUALITY_GATE → DONE

Failure paths:
    Any active state → FAILED → (retry, back to PLANNING) or → BLOCKED
"""

from __future__ import annotations

from typing import Any, Iterable

PENDING = "PENDING"
PLANNING = "PLANNING"
IMPLEMENTING = "IMPLEMENTING"
TESTING = "TESTING"
QUALITY_GATE = "QUALITY_GATE"
DONE = "DONE"
FAILED = "FAILED"
BLOCKED = "BLOCKED"
IN_PROGRESS = "IN_PROGRESS"  # bootstrap chunks (C1-C4) reuse this

STATES = frozenset(
    {
        PENDING,
        PLANNING,
        IMPLEMENTING,
        TESTING,
        QUALITY_GATE,
        DONE,
        FAILED,
        BLOCKED,
        IN_PROGRESS,
    }
)

# Active = currently consuming runner attention.
ACTIVE_STATES = frozenset({PLANNING, IMPLEMENTING, TESTING, QUALITY_GATE})
TERMINAL_STATES = frozenset({DONE, BLOCKED})

ALLOWED: dict[str, frozenset[str]] = {
    PENDING: frozenset({PLANNING, BLOCKED}),
    PLANNING: frozenset({IMPLEMENTING, FAILED}),
    IMPLEMENTING: frozenset({TESTING, FAILED}),
    TESTING: frozenset({QUALITY_GATE, FAILED}),
    QUALITY_GATE: frozenset({DONE, FAILED}),
    FAILED: frozenset({PLANNING, BLOCKED}),  # retry or give up
    DONE: frozenset(),
    BLOCKED: frozenset({PENDING}),  # manual unblock
    IN_PROGRESS: frozenset({DONE, FAILED}),  # bootstrap chunks
}


class IllegalTransition(Exception):
    pass


def assert_transition(from_state: str, to_state: str) -> None:
    if from_state not in STATES:
        raise IllegalTransition(f"unknown from_state: {from_state}")
    if to_state not in STATES:
        raise IllegalTransition(f"unknown to_state: {to_state}")
    if to_state not in ALLOWED[from_state]:
        raise IllegalTransition(f"illegal transition: {from_state} → {to_state}")


def is_terminal(state: str) -> bool:
    return state in TERMINAL_STATES


def is_active(state: str) -> bool:
    return state in ACTIVE_STATES


def next_ready_chunk(
    chunks: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the next chunk eligible to start work.

    A chunk is ready when:
      - status is PENDING
      - every dependency is in DONE
    Chunks are returned in plan order (caller pre-sorts by id).
    """

    def _key(c: dict[str, Any]) -> tuple[int, str]:
        cid = c["id"]
        digits = "".join(ch for ch in cid if ch.isdigit())
        return (int(digits) if digits else 0, cid)

    sorted_chunks = sorted(chunks, key=_key)
    by_id = {c["id"]: c for c in sorted_chunks}
    for chunk in sorted_chunks:
        if chunk["status"] != PENDING:
            continue
        deps = chunk.get("depends_on") or []
        if all(by_id.get(d, {}).get("status") == DONE for d in deps):
            return chunk
    return None
