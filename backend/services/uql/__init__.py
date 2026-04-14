"""UQL (Unified Query Language) service package — spec §17/§18/§20.

Re-exports the engine entry points so callers can ``from backend.services.uql
import execute, execute_template`` without reaching into submodules. The engine
module itself is a pure dispatcher; aggregation, timeseries, registry, safety,
templates, includes, errors, and meta logic live in the sibling modules.

This module is the scaffold landed by chunk V2-UQL-AGG-1. Behavior is added in
the dependent V2-UQL-AGG-* chunks per ``specs/004-uql-aggregations/tasks.md``.
"""

from backend.services.uql import engine

execute = engine.execute
execute_template = engine.execute_template
build_from_legacy = engine.build_from_legacy

__all__ = ["execute", "execute_template", "build_from_legacy", "engine"]
