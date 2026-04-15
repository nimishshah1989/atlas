"""Agent graph orchestrator — lightweight DAG execution with fault tolerance.

Implements the LangGraph-equivalent orchestration pattern without the langchain
dependency. Agents are nodes; edges define execution order. If a node fails,
downstream nodes still execute with partial state and is_stale=True flagging.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

import structlog

log = structlog.get_logger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


class NodeStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class NodeResult:
    """Result from a single node execution."""

    status: NodeStatus
    output: Any = None
    error: Optional[str] = None
    duration_ms: int = 0
    is_stale: bool = False


@dataclass
class GraphState:
    """Shared state passed through the graph execution."""

    context: dict[str, Any] = field(default_factory=dict)
    node_results: dict[str, NodeResult] = field(default_factory=dict)
    is_stale: bool = False
    stale_sources: list[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def get_node_output(self, node_id: str) -> Any:
        """Get output from a completed node, or None if it failed/hasn't run."""
        node_result = self.node_results.get(node_id)
        if node_result and node_result.status == NodeStatus.SUCCESS:
            return node_result.output
        return None

    @property
    def has_failures(self) -> bool:
        """True if any node in the graph failed."""
        return any(r.status == NodeStatus.FAILED for r in self.node_results.values())


# Type alias for node functions
NodeFunc = Callable[["GraphState"], Coroutine[Any, Any, Any]]


@dataclass
class Node:
    """A single node in the agent graph."""

    id: str
    func: NodeFunc
    depends_on: list[str] = field(default_factory=list)


class AgentGraph:
    """Directed acyclic graph executor for agent orchestration.

    Nodes are async callables that receive GraphState and return output.
    Edges (depends_on) define execution order. Topological sort determines
    execution sequence. Failed nodes mark downstream results as is_stale.
    """

    def __init__(self, name: str = "agent-graph") -> None:
        self.name = name
        self._nodes: dict[str, Node] = {}

    def add_node(
        self,
        node_id: str,
        func: NodeFunc,
        depends_on: Optional[list[str]] = None,
    ) -> None:
        """Register a node in the graph.

        Args:
            node_id: Unique identifier for this node.
            func: Async callable (GraphState) -> Any. Must be a coroutine function.
            depends_on: List of node_ids this node depends on. Must run after them.

        Raises:
            ValueError: If node_id is already registered.
        """
        if node_id in self._nodes:
            raise ValueError(f"Duplicate node id: {node_id}")
        self._nodes[node_id] = Node(
            id=node_id,
            func=func,
            depends_on=depends_on or [],
        )

    def _topological_sort(self) -> list[str]:
        """Kahn's algorithm for topological ordering.

        Returns:
            Node ids in a valid execution order (all deps before dependents).

        Raises:
            ValueError: If graph has cycles or unknown dependency references.
        """
        # Validate all dependencies reference known nodes
        for node in self._nodes.values():
            for dep in node.depends_on:
                if dep not in self._nodes:
                    raise ValueError(f"Node '{node.id}' depends on unknown node '{dep}'")

        # in_degree[nid] = number of unresolved dependencies
        in_degree: dict[str, int] = {nid: len(self._nodes[nid].depends_on) for nid in self._nodes}

        # Start with nodes that have no dependencies
        queue: list[str] = [nid for nid, deg in in_degree.items() if deg == 0]
        order: list[str] = []

        while queue:
            # Sort for determinism across runs
            queue.sort()
            current = queue.pop(0)
            order.append(current)

            # Reduce in-degree for all nodes that depend on current
            for nid, node in self._nodes.items():
                if current in node.depends_on:
                    in_degree[nid] -= 1
                    if in_degree[nid] == 0:
                        queue.append(nid)

        if len(order) != len(self._nodes):
            raise ValueError(
                f"Graph '{self.name}' has cycles — topological sort incomplete "
                f"({len(order)} of {len(self._nodes)} nodes ordered)"
            )

        return order

    async def execute(self, initial_state: Optional[dict[str, Any]] = None) -> GraphState:
        """Execute the graph with fault tolerance.

        Nodes run in topological order. If a node fails:
        - Its downstream nodes still execute.
        - Downstream node results are marked is_stale=True.
        - The overall GraphState.is_stale is set to True.

        No exception escapes this method. Even invalid graphs return a
        stale GraphState rather than raising.

        Args:
            initial_state: Optional initial data dict merged into GraphState.context.

        Returns:
            GraphState with node_results for every node that ran.
        """
        state = GraphState(
            context=initial_state or {},
            started_at=datetime.now(IST),
        )

        try:
            order = self._topological_sort()
        except ValueError as exc:
            log.error(
                "graph_invalid",
                graph=self.name,
                error=str(exc),
            )
            state.completed_at = datetime.now(IST)
            state.is_stale = True
            return state

        # Track which nodes have failed so dependents can be marked stale
        failed_nodes: set[str] = set()

        for node_id in order:
            node = self._nodes[node_id]

            # Check if any dependency failed — this node's output will be stale
            has_failed_dep = any(dep in failed_nodes for dep in node.depends_on)

            t0 = time.monotonic()
            try:
                output = await node.func(state)
                duration_ms = int((time.monotonic() - t0) * 1000)

                node_result = NodeResult(
                    status=NodeStatus.SUCCESS,
                    output=output,
                    duration_ms=duration_ms,
                    is_stale=has_failed_dep,
                )
                state.node_results[node_id] = node_result

                if has_failed_dep:
                    state.stale_sources.append(node_id)
                    log.warning(
                        "node_stale_dependency",
                        graph=self.name,
                        node=node_id,
                        failed_deps=[d for d in node.depends_on if d in failed_nodes],
                    )

                log.info(
                    "node_complete",
                    graph=self.name,
                    node=node_id,
                    status="SUCCESS",
                    duration_ms=duration_ms,
                    is_stale=has_failed_dep,
                )

            except Exception as exc:
                duration_ms = int((time.monotonic() - t0) * 1000)
                failed_nodes.add(node_id)

                node_result = NodeResult(
                    status=NodeStatus.FAILED,
                    error=str(exc),
                    duration_ms=duration_ms,
                    is_stale=True,
                )
                state.node_results[node_id] = node_result
                state.stale_sources.append(node_id)

                log.error(
                    "node_failed",
                    graph=self.name,
                    node=node_id,
                    error=str(exc),
                    duration_ms=duration_ms,
                )

        state.is_stale = len(failed_nodes) > 0
        state.completed_at = datetime.now(IST)

        log.info(
            "graph_complete",
            graph=self.name,
            total_nodes=len(self._nodes),
            failed=len(failed_nodes),
            is_stale=state.is_stale,
        )

        return state
