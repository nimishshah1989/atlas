"""Smoke tests for the Alembic configuration shipped in C7."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_alembic_ini_is_loadable() -> None:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    assert cfg.get_main_option("script_location") == "alembic"


def test_alembic_has_baseline_revision() -> None:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    revisions = list(script.walk_revisions())
    assert revisions, "alembic/versions should contain at least the baseline"
    heads = script.get_heads()
    assert len(heads) == 1, f"expected single head, got {heads}"
