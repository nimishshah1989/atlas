"""Roadmap YAML loader — parses orchestrator/roadmap.yaml into Pydantic models.

This module is imported by orchestrator/roadmap_schema.py (FD-2) which re-exports
the models. Define all models here; FD-2 just imports and re-exports.

If roadmap.yaml does not exist (FD-2 hasn't run yet), returns RoadmapFile(versions=[])
without raising.
"""

from pathlib import Path
from typing import Any, List, Optional

import structlog
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Pydantic models (frozen=True for hashability / cache-key safety)
# ---------------------------------------------------------------------------


class DemoGate(BaseModel):
    """Optional demo gate on a Version."""

    url: str
    walkthrough: List[str] = Field(default_factory=list)


class Check(BaseModel):
    """Declarative step check spec from roadmap.yaml."""

    type: str  # file_exists | command | http_ok | db_query | smoke_list
    # type-specific fields — all optional so loader stays lenient
    path: Optional[str] = None
    cmd: Optional[List[str]] = None
    url: Optional[str] = None
    sql: Optional[str] = None
    target: Optional[str] = None
    file: Optional[str] = None  # for smoke_list: endpoints file path (YAML key: file)
    slow: Optional[bool] = None  # explicit slow flag (smoke_list always slow)

    model_config = {"extra": "ignore"}


class Step(BaseModel):
    """A single acceptance-criterion step inside a Chunk."""

    id: str
    text: str
    check: Optional["Check"] = None


class Chunk(BaseModel):
    """A single chunk inside a Version."""

    id: str
    title: str
    steps: List[Step] = Field(default_factory=list)


class Rollup(BaseModel):
    done: int = 0
    total: int = 0
    pct: int = 0


class Version(BaseModel):
    """A vertical slice version (V1–V10)."""

    id: str
    title: str
    goal: str = ""
    chunks: List[Chunk] = Field(default_factory=list)
    demo_gate: Optional[DemoGate] = None


class RoadmapFile(BaseModel):
    """Top-level parsed roadmap.yaml structure."""

    versions: List[Version] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ROADMAP_PATH = _REPO_ROOT / "orchestrator" / "roadmap.yaml"


def load_roadmap(path: Optional[Path] = None) -> RoadmapFile:
    """Parse roadmap.yaml and return a RoadmapFile.

    Returns RoadmapFile(versions=[]) if the file does not exist.
    Logs a warning but does NOT raise on parse errors — returns empty roadmap.
    """
    target = path or _ROADMAP_PATH

    if not target.exists():
        log.info("roadmap_yaml_not_found", path=str(target))
        return RoadmapFile(versions=[])

    try:
        raw: Any = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        log.warning("roadmap_yaml_parse_error", path=str(target), error=str(exc))
        return RoadmapFile(versions=[])

    if not isinstance(raw, dict):
        log.warning("roadmap_yaml_invalid_root", path=str(target))
        return RoadmapFile(versions=[])

    versions_raw = raw.get("versions", [])
    versions: list[Version] = []
    for v_data in versions_raw:
        try:
            version = _parse_version(v_data)
            versions.append(version)
        except Exception as exc:
            log.warning(
                "roadmap_version_parse_error",
                version_id=v_data.get("id", "?"),
                error=str(exc),
            )

    log.info("roadmap_loaded", versions=len(versions), path=str(target))
    return RoadmapFile(versions=versions)


def _parse_version(data: dict) -> Version:
    chunks: list[Chunk] = []
    for c_data in data.get("chunks", []):
        chunks.append(_parse_chunk(c_data))

    demo_gate_data = data.get("demo_gate")
    demo_gate = DemoGate(**demo_gate_data) if demo_gate_data else None

    return Version(
        id=data["id"],
        title=data.get("title", ""),
        goal=data.get("goal", ""),
        chunks=chunks,
        demo_gate=demo_gate,
    )


def _parse_chunk(data: dict) -> Chunk:
    steps: list[Step] = []
    for s_data in data.get("steps", []):
        steps.append(_parse_step(s_data))
    return Chunk(
        id=data["id"],
        title=data.get("title", ""),
        steps=steps,
    )


def _parse_step(data: dict) -> Step:
    check_data = data.get("check")
    check: Optional[Check] = None
    if check_data:
        check = Check(**check_data)
    return Step(
        id=data["id"],
        text=data.get("text", ""),
        check=check,
    )
