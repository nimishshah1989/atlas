"""roadmap_schema.py — Pydantic v2 models for orchestrator/roadmap.yaml.

This is the single source of truth for roadmap data shapes.
- backend/core/roadmap_loader.py imports from here.
- scripts/roadmap-lint.py imports from here.
- scripts/plan-to-roadmap.py imports from here.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, field_validator, model_validator

# ---------------------------------------------------------------------------
# ID format patterns
# ---------------------------------------------------------------------------
VERSION_ID_RE = re.compile(r"^V\d+$")
CHUNK_ID_RE = re.compile(r"^C\d+$")
STEP_ID_RE = re.compile(r"^C(\d+)\.(\d+)$")

VALID_CHECK_TYPES = frozenset(
    {"file_exists", "command", "http_ok", "db_query", "smoke_list"}
)


# ---------------------------------------------------------------------------
# Check models
# ---------------------------------------------------------------------------


class FileExistsCheck(BaseModel):
    type: Literal["file_exists"]
    path: str

    @field_validator("path")
    @classmethod
    def path_no_dotdot(cls, v: str) -> str:
        if ".." in v.split("/"):
            raise ValueError(f"path must be relative with no '..': {v!r}")
        if v.startswith("/"):
            raise ValueError(f"path must be relative, not absolute: {v!r}")
        return v


class CommandCheck(BaseModel):
    type: Literal["command"]
    cmd: list[str]

    @field_validator("cmd", mode="before")
    @classmethod
    def cmd_must_be_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            raise ValueError(
                f"'cmd' must be a list of strings, not a shell string. Got: {v!r}"
            )
        return v


class HttpOkCheck(BaseModel):
    type: Literal["http_ok"]
    url: str
    timeout_s: Optional[float] = 10.0


class DbQueryCheck(BaseModel):
    type: Literal["db_query"]
    sql: str
    expect_rows_gte: Optional[int] = None


class SmokeListCheck(BaseModel):
    type: Literal["smoke_list"]
    file: str  # path to the smoke endpoints file

    @field_validator("file")
    @classmethod
    def file_no_dotdot(cls, v: str) -> str:
        if ".." in v.split("/"):
            raise ValueError(f"file path must not contain '..': {v!r}")
        return v


Check = Union[FileExistsCheck, CommandCheck, HttpOkCheck, DbQueryCheck, SmokeListCheck]


def parse_check(data: dict[str, Any]) -> Check:
    """Parse a raw dict into the correct Check submodel."""
    check_type = data.get("type")
    if check_type not in VALID_CHECK_TYPES:
        raise ValueError(
            f"Unknown check type {check_type!r}. Valid: {sorted(VALID_CHECK_TYPES)}"
        )
    mapping = {
        "file_exists": FileExistsCheck,
        "command": CommandCheck,
        "http_ok": HttpOkCheck,
        "db_query": DbQueryCheck,
        "smoke_list": SmokeListCheck,
    }
    return mapping[check_type].model_validate(data)  # type: ignore[attr-defined,return-value]


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------


class Step(BaseModel):
    id: str
    text: str
    check: Optional[dict[str, Any]] = None  # raw dict; validated separately
    slow: bool = False

    @field_validator("id")
    @classmethod
    def step_id_format(cls, v: str) -> str:
        if not STEP_ID_RE.match(v):
            raise ValueError(f"Step id must match C<n>.<m> (e.g. C1.1), got {v!r}")
        return v

    def parsed_check(self) -> Optional[Check]:
        if self.check is None:
            return None
        return parse_check(self.check)


# ---------------------------------------------------------------------------
# Chunk
# ---------------------------------------------------------------------------


class Chunk(BaseModel):
    id: str
    plan_ref: bool = False
    future: bool = False
    steps: list[Step] = []

    @field_validator("id")
    @classmethod
    def chunk_id_format(cls, v: str) -> str:
        if not CHUNK_ID_RE.match(v):
            raise ValueError(f"Chunk id must match C<n> (e.g. C1), got {v!r}")
        return v

    @model_validator(mode="after")
    def validate_step_prefixes(self) -> "Chunk":
        """Every step id prefix must match the chunk id."""
        for step in self.steps:
            m = STEP_ID_RE.match(step.id)
            if m:
                # step id is C<a>.<b>; chunk id is C<n>
                chunk_num = self.id[1:]  # strip 'C'
                if m.group(1) != chunk_num:
                    raise ValueError(
                        f"Step {step.id!r} belongs to chunk C{m.group(1)}, "
                        f"but is nested under chunk {self.id!r}"
                    )
        return self


# ---------------------------------------------------------------------------
# DemoGate
# ---------------------------------------------------------------------------


class DemoGate(BaseModel):
    url: str
    walkthrough: list[str]

    @field_validator("url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("demo_gate.url must not be empty")
        return v

    @field_validator("walkthrough")
    @classmethod
    def walkthrough_min_one(cls, v: list[str]) -> list[str]:
        if len(v) < 1:
            raise ValueError("demo_gate.walkthrough must have at least 1 item")
        return v


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


class Version(BaseModel):
    id: str
    title: str
    goal: str
    demo_gate: Optional[DemoGate] = None
    chunks: list[Chunk] = []

    @field_validator("id")
    @classmethod
    def version_id_format(cls, v: str) -> str:
        if not VERSION_ID_RE.match(v):
            raise ValueError(f"Version id must match V<n> (e.g. V1), got {v!r}")
        return v


# ---------------------------------------------------------------------------
# RoadmapFile
# ---------------------------------------------------------------------------


class RoadmapFile(BaseModel):
    versions: list[Version]

    @model_validator(mode="after")
    def validate_unique_chunk_ids(self) -> "RoadmapFile":
        seen: dict[str, str] = {}
        for version in self.versions:
            for chunk in version.chunks:
                if chunk.id in seen:
                    raise ValueError(
                        f"Chunk id {chunk.id!r} appears in both "
                        f"{seen[chunk.id]} and {version.id}"
                    )
                seen[chunk.id] = version.id
        return self

    @model_validator(mode="after")
    def validate_version_ids_v1_to_v10(self) -> "RoadmapFile":
        valid = {f"V{n}" for n in range(1, 11)}
        for v in self.versions:
            if v.id not in valid:
                raise ValueError(f"Version id {v.id!r} is out of range V1–V10")
        return self
