"""Tests for agent_graph — lightweight DAG executor with fault tolerance.

Punch list assertions:
1. 2-node graph with one source missing still produces result flagged is_stale=True
2. No exception escapes the graph on partial data
"""

from __future__ import annotations

import pytest

from backend.services.agent_graph import AgentGraph, GraphState, NodeStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _succeed(state: GraphState) -> str:
    """Node that always succeeds and returns 'ok'."""
    return "ok"


async def _fail(state: GraphState) -> None:
    """Node that always raises (simulates missing data source)."""
    raise RuntimeError("source data missing")


async def _write_data(state: GraphState) -> str:
    """Node that writes to state.context so downstream can read it."""
    state.context["from_a"] = "hello"
    return "wrote"


async def _read_data(state: GraphState) -> str:
    """Node that reads state.context written by upstream node."""
    return state.context.get("from_a", "missing")


# ---------------------------------------------------------------------------
# Punch list item 1: 2-node graph with missing source → is_stale=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_node_graph_source_missing_produces_stale() -> None:
    """Key integration test: 2-node graph where node A fails, node B still runs.

    Asserts:
    - state.is_stale is True
    - node A status is FAILED
    - node B status is SUCCESS (it still ran)
    - node B result has is_stale=True
    - No exception escaped
    """
    graph = AgentGraph(name="test-stale")
    graph.add_node("source_a", _fail)
    graph.add_node("consumer_b", _succeed, depends_on=["source_a"])

    state = graph.execute()  # returns coroutine
    state = await state

    # Overall graph is stale because source_a failed
    assert state.is_stale is True

    # node A should be marked FAILED
    result_a = state.node_results["source_a"]
    assert result_a.status == NodeStatus.FAILED
    assert result_a.error == "source data missing"

    # node B should still have run and succeeded, but marked stale
    result_b = state.node_results["consumer_b"]
    assert result_b.status == NodeStatus.SUCCESS
    assert result_b.is_stale is True

    # stale_sources includes the failed node
    assert "source_a" in state.stale_sources


# ---------------------------------------------------------------------------
# Punch list item 2: No exception escapes on partial data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_exception_escapes_on_partial_data() -> None:
    """3-node chain where middle fails. Graph completes, no exception."""
    graph = AgentGraph(name="test-no-escape")
    graph.add_node("node_a", _succeed)
    graph.add_node("node_b", _fail, depends_on=["node_a"])
    graph.add_node("node_c", _succeed, depends_on=["node_b"])

    # Must not raise
    state = await graph.execute()

    assert state.is_stale is True
    assert state.node_results["node_a"].status == NodeStatus.SUCCESS
    assert state.node_results["node_b"].status == NodeStatus.FAILED
    assert state.node_results["node_c"].status == NodeStatus.SUCCESS
    assert state.node_results["node_c"].is_stale is True


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_simple_graph_success() -> None:
    """Both nodes succeed → is_stale is False."""
    graph = AgentGraph(name="test-success")
    graph.add_node("a", _succeed)
    graph.add_node("b", _succeed, depends_on=["a"])

    state = await graph.execute()

    assert state.is_stale is False
    assert state.node_results["a"].status == NodeStatus.SUCCESS
    assert state.node_results["b"].status == NodeStatus.SUCCESS
    assert state.node_results["b"].is_stale is False


@pytest.mark.asyncio
async def test_topological_order() -> None:
    """Execution order respects dependencies: a → b → c."""
    execution_order: list[str] = []

    async def track_a(state: GraphState) -> str:
        execution_order.append("a")
        return "a"

    async def track_b(state: GraphState) -> str:
        execution_order.append("b")
        return "b"

    async def track_c(state: GraphState) -> str:
        execution_order.append("c")
        return "c"

    graph = AgentGraph(name="test-order")
    graph.add_node("c", track_c, depends_on=["b"])
    graph.add_node("a", track_a)
    graph.add_node("b", track_b, depends_on=["a"])

    await graph.execute()

    assert execution_order.index("a") < execution_order.index("b")
    assert execution_order.index("b") < execution_order.index("c")


@pytest.mark.asyncio
async def test_cycle_detection() -> None:
    """Graph with a cycle returns stale state without crashing."""
    graph = AgentGraph(name="test-cycle")
    graph.add_node("x", _succeed, depends_on=["y"])
    graph.add_node("y", _succeed, depends_on=["x"])

    # Must not raise; returns stale state
    state = await graph.execute()

    assert state.is_stale is True
    # No node results since sort failed before execution
    assert len(state.node_results) == 0


@pytest.mark.asyncio
async def test_unknown_dependency_returns_stale() -> None:
    """Reference to undefined node returns stale state, no crash."""
    graph = AgentGraph(name="test-unknown-dep")
    graph.add_node("orphan", _succeed, depends_on=["nonexistent"])

    state = await graph.execute()

    assert state.is_stale is True
    assert len(state.node_results) == 0


@pytest.mark.asyncio
async def test_state_passing() -> None:
    """Node A writes to state.context, Node B reads it correctly."""
    graph = AgentGraph(name="test-state-pass")
    graph.add_node("writer", _write_data)
    graph.add_node("reader", _read_data, depends_on=["writer"])

    state = await graph.execute()

    assert state.is_stale is False
    reader_result = state.node_results["reader"]
    assert reader_result.status == NodeStatus.SUCCESS
    assert reader_result.output == "hello"
    # Data is also in state.context
    assert state.context["from_a"] == "hello"


@pytest.mark.asyncio
async def test_parallel_independent_nodes_all_execute() -> None:
    """Nodes with no dependencies all execute even if one fails."""
    graph = AgentGraph(name="test-independent")
    graph.add_node("p1", _succeed)
    graph.add_node("p2", _fail)
    graph.add_node("p3", _succeed)

    state = await graph.execute()

    assert state.node_results["p1"].status == NodeStatus.SUCCESS
    assert state.node_results["p2"].status == NodeStatus.FAILED
    assert state.node_results["p3"].status == NodeStatus.SUCCESS
    assert state.is_stale is True


@pytest.mark.asyncio
async def test_get_node_output_returns_none_for_failed() -> None:
    """GraphState.get_node_output returns None when the node failed."""
    graph = AgentGraph(name="test-get-output")
    graph.add_node("bad_node", _fail)
    graph.add_node("good_node", _succeed)

    state = await graph.execute()

    assert state.get_node_output("bad_node") is None
    assert state.get_node_output("good_node") == "ok"
    # Unknown node also returns None
    assert state.get_node_output("does_not_exist") is None


@pytest.mark.asyncio
async def test_duplicate_node_id_raises() -> None:
    """add_node raises ValueError on duplicate id."""
    graph = AgentGraph(name="test-dupe")
    graph.add_node("x", _succeed)

    with pytest.raises(ValueError, match="Duplicate node id"):
        graph.add_node("x", _succeed)


@pytest.mark.asyncio
async def test_empty_graph_succeeds() -> None:
    """Empty graph executes successfully with is_stale=False."""
    graph = AgentGraph(name="test-empty")

    state = await graph.execute()

    assert state.is_stale is False
    assert len(state.node_results) == 0


@pytest.mark.asyncio
async def test_initial_state_passed_through() -> None:
    """initial_state dict is available in state.context for nodes."""

    async def read_initial(state: GraphState) -> str:
        return state.context.get("seed", "missing")

    graph = AgentGraph(name="test-initial")
    graph.add_node("reader", read_initial)

    state = await graph.execute(initial_state={"seed": "planted"})

    assert state.node_results["reader"].output == "planted"


@pytest.mark.asyncio
async def test_completed_at_set_after_execution() -> None:
    """GraphState.completed_at is populated (IST-aware) after execute()."""
    graph = AgentGraph(name="test-timestamps")
    graph.add_node("node", _succeed)

    state = await graph.execute()

    assert state.started_at is not None
    assert state.completed_at is not None
    assert state.completed_at >= state.started_at
    # Timezone-aware (UTC offset +05:30)
    assert state.started_at.utcoffset() is not None


@pytest.mark.asyncio
async def test_has_failures_property() -> None:
    """GraphState.has_failures is True when any node failed."""
    graph = AgentGraph(name="test-has-failures")
    graph.add_node("ok", _succeed)
    graph.add_node("bad", _fail)

    state = await graph.execute()

    assert state.has_failures is True


@pytest.mark.asyncio
async def test_no_failures_property_on_clean_run() -> None:
    """GraphState.has_failures is False when all nodes succeed."""
    graph = AgentGraph(name="test-no-failures")
    graph.add_node("ok1", _succeed)
    graph.add_node("ok2", _succeed, depends_on=["ok1"])

    state = await graph.execute()

    assert state.has_failures is False
