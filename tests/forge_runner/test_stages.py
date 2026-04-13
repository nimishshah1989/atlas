"""T049: Stage protocol + HostedStageBase + StageResult serialization (US6).

Tests:
  - Each local stage satisfies ``isinstance(stage, Stage)`` via runtime_checkable.
  - A minimal concrete ``HostedStageBase`` subclass satisfies the protocol structurally.
  - ``HostedStageBase.run()`` raises ``NotImplementedError`` with a message containing
    "L3-HYBRID-AGENTS".
  - ``StageResult`` is JSON-serializable via ``json.dumps(dataclasses.asdict(result))``.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from typing import Any

import pytest

from scripts.forge_runner._time import to_iso


def _json_dumps_safe(obj: Any) -> str:
    """json.dumps with a default encoder that converts datetime to ISO strings."""

    def _default(val: Any) -> Any:
        if isinstance(val, datetime):
            return to_iso(val)
        raise TypeError(f"Object of type {type(val).__name__} is not JSON serializable")

    return json.dumps(obj, default=_default)


from scripts.forge_runner.stages import (  # noqa: E402 — placed after helper to avoid circular at import time
    HostedStageBase,
    LocalImplementStage,
    LocalLoopAdvanceStage,
    LocalPickStage,
    LocalVerifyStage,
    RunContext,
    Stage,
    StageResult,
)


# ---------------------------------------------------------------------------
# Minimal concrete subclass of HostedStageBase for structural checks
# ---------------------------------------------------------------------------


class _ConcreteHostedStage(HostedStageBase):
    """Minimal concrete subclass — satisfies the three abstract methods."""

    name: str = "hosted-test"

    def agent_definition_id(self) -> str:
        return "forge-test-agent-v1"

    def build_request(self, chunk: Any, ctx: RunContext) -> dict[str, Any]:
        return {
            "agent_definition_id": self.agent_definition_id(),
            "input": {"chunk_id": chunk if isinstance(chunk, str) else "unknown"},
            "max_tokens": 4096,
            "timeout_ms": 60_000,
        }

    def parse_response(self, response: dict[str, Any]) -> StageResult:
        return StageResult(
            stage_name=self.name,
            status="ok",
            chunk_id=response.get("output", {}).get("chunk_id"),
        )


# ---------------------------------------------------------------------------
# Protocol satisfaction tests (local stages)
# ---------------------------------------------------------------------------


class TestLocalStagesSatisfyProtocol:
    """Each local stage must pass the runtime_checkable Protocol check."""

    def test_local_pick_stage_is_stage(self) -> None:
        assert isinstance(LocalPickStage(), Stage)

    def test_local_implement_stage_is_stage(self) -> None:
        assert isinstance(LocalImplementStage(), Stage)

    def test_local_verify_stage_is_stage(self) -> None:
        assert isinstance(LocalVerifyStage(), Stage)

    def test_local_loop_advance_stage_is_stage(self) -> None:
        assert isinstance(LocalLoopAdvanceStage(), Stage)


# ---------------------------------------------------------------------------
# HostedStageBase tests
# ---------------------------------------------------------------------------


class TestHostedStageBase:
    def test_concrete_subclass_satisfies_protocol(self) -> None:
        """A concrete HostedStageBase subclass must pass the runtime Protocol check."""
        stage = _ConcreteHostedStage()
        assert isinstance(stage, Stage)

    def test_run_raises_not_implemented(self) -> None:
        """HostedStageBase.run() must raise NotImplementedError."""
        import asyncio

        stage = _ConcreteHostedStage()
        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(NotImplementedError):
                loop.run_until_complete(stage.run(None))  # type: ignore[arg-type]
        finally:
            loop.close()

    def test_run_error_message_mentions_l3_hybrid_agents(self) -> None:
        """The NotImplementedError message must reference 'L3-HYBRID-AGENTS'."""
        import asyncio

        stage = _ConcreteHostedStage()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(stage.run(None))  # type: ignore[arg-type]
        except NotImplementedError as exc:
            assert "L3-HYBRID-AGENTS" in str(exc), (
                f"Expected 'L3-HYBRID-AGENTS' in error message, got: {exc}"
            )
        else:
            pytest.fail("Expected NotImplementedError was not raised")
        finally:
            loop.close()

    def test_agent_definition_id_implemented(self) -> None:
        stage = _ConcreteHostedStage()
        assert stage.agent_definition_id() == "forge-test-agent-v1"

    def test_build_request_returns_dict(self) -> None:
        stage = _ConcreteHostedStage()
        req = stage.build_request("V1-1", None)  # type: ignore[arg-type]
        assert isinstance(req, dict)
        assert "agent_definition_id" in req
        assert "input" in req

    def test_parse_response_returns_stage_result(self) -> None:
        stage = _ConcreteHostedStage()
        result = stage.parse_response({"output": {"chunk_id": "V1-1"}, "usage": {}})
        assert isinstance(result, StageResult)


# ---------------------------------------------------------------------------
# StageResult JSON serialization
# ---------------------------------------------------------------------------


class TestStageResultSerializable:
    """StageResult must be JSON-serializable via json.dumps(dataclasses.asdict(result)).

    ``StageResult`` contains a ``started_at: datetime`` field.  A custom default
    encoder that converts datetime → ISO string is used so that ``dataclasses.asdict``
    output is fully serializable.  This matches the ``to_json_safe()`` method on
    StageResult, which the runner uses internally.
    """

    def test_ok_result_json_serializable(self) -> None:
        """StageResult(status='ok') must survive json.dumps(dataclasses.asdict(...))."""
        result = StageResult(
            stage_name="pick",
            status="ok",
            chunk_id="V1-1",
            artifacts={"chunk_id": "V1-1"},
            reason="picked V1-1",
        )
        raw = _json_dumps_safe(dataclasses.asdict(result))
        parsed = json.loads(raw)
        assert parsed["stage_name"] == "pick"
        assert parsed["status"] == "ok"
        assert parsed["chunk_id"] == "V1-1"

    def test_failed_result_json_serializable(self) -> None:
        result = StageResult(
            stage_name="verify",
            status="failed",
            chunk_id="V1-2",
            reason="state_db_not_done",
            duration_ms=423,
        )
        raw = _json_dumps_safe(dataclasses.asdict(result))
        parsed = json.loads(raw)
        assert parsed["status"] == "failed"
        assert parsed["duration_ms"] == 423

    def test_none_chunk_id_serializable(self) -> None:
        """chunk_id=None must not break JSON serialization."""
        result = StageResult(
            stage_name="pick",
            status="skipped",
            chunk_id=None,
            reason="halt-stalled",
        )
        raw = _json_dumps_safe(dataclasses.asdict(result))
        parsed = json.loads(raw)
        assert parsed["chunk_id"] is None

    def test_needs_sync_result_json_serializable(self) -> None:
        result = StageResult(
            stage_name="verify",
            status="needs_sync",
            chunk_id="V1-3",
            reason="shipped but state.db not updated",
        )
        raw = _json_dumps_safe(dataclasses.asdict(result))
        assert json.loads(raw)["status"] == "needs_sync"

    def test_to_json_safe_method_works(self) -> None:
        """StageResult.to_json_safe() must return a dict that is json.dumps-able."""
        result = StageResult(
            stage_name="advance",
            status="ok",
            chunk_id="V1-4",
        )
        safe = result.to_json_safe()
        raw = json.dumps(safe)
        parsed = json.loads(raw)
        assert parsed["stage_name"] == "advance"
        assert isinstance(parsed["started_at"], str)  # datetime converted to ISO string
