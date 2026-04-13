"""Regression: chunks with plan_ref but no title should inherit their
title from plan.yaml so the dashboard renders human-readable rows."""

from __future__ import annotations

from pathlib import Path

from backend.core.roadmap_loader import (
    _load_plan_chunk_titles,
    load_roadmap,
)


def test_plan_chunk_titles_loaded(tmp_path: Path) -> None:
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        """\
chunks:
  - id: C1
    title: "Quality engine"
  - id: C2
    title: "Orchestrator skeleton"
  - id: C3
    # no title — should be skipped
""",
        encoding="utf-8",
    )
    titles = _load_plan_chunk_titles(plan)
    assert titles == {"C1": "Quality engine", "C2": "Orchestrator skeleton"}


def test_roadmap_chunk_inherits_title_from_plan(tmp_path: Path, monkeypatch) -> None:
    from backend.core import roadmap_loader

    plan = tmp_path / "plan.yaml"
    plan.write_text(
        'chunks:\n  - id: C1\n    title: "Quality engine + frozen standards"\n',
        encoding="utf-8",
    )
    roadmap = tmp_path / "roadmap.yaml"
    roadmap.write_text(
        """\
versions:
  - id: V1
    title: "V1"
    chunks:
      - id: C1
        plan_ref: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(roadmap_loader, "_PLAN_PATH", plan)
    loaded = load_roadmap(roadmap)
    assert loaded.versions[0].chunks[0].title == "Quality engine + frozen standards"


def test_explicit_roadmap_title_wins_over_plan(tmp_path: Path, monkeypatch) -> None:
    from backend.core import roadmap_loader

    plan = tmp_path / "plan.yaml"
    plan.write_text('chunks:\n  - id: C1\n    title: "from plan"\n', encoding="utf-8")
    roadmap = tmp_path / "roadmap.yaml"
    roadmap.write_text(
        """\
versions:
  - id: V1
    title: "V1"
    chunks:
      - id: C1
        title: "from roadmap"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(roadmap_loader, "_PLAN_PATH", plan)
    loaded = load_roadmap(roadmap)
    assert loaded.versions[0].chunks[0].title == "from roadmap"
