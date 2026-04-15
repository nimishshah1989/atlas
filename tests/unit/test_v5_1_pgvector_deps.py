"""Tests for V5-1: pgvector dependency pinning and extension migration.

Verifies:
- pgvector package is importable from the venv
- Root requirements.txt contains the pgvector pin
- backend/requirements.txt exists and delegates to root
- Alembic migration file exists and contains the correct DDL
"""

import importlib
import pathlib
import re


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ROOT_REQUIREMENTS = REPO_ROOT / "requirements.txt"
BACKEND_REQUIREMENTS = REPO_ROOT / "backend" / "requirements.txt"
ALEMBIC_VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"
MIGRATION_SLUG = "v5_1_pgvector_extension"


# ---------------------------------------------------------------------------
# Dependency import tests
# ---------------------------------------------------------------------------


def test_pgvector_is_importable() -> None:
    """pgvector must be installable and importable."""
    loader = importlib.util.find_spec("pgvector")
    assert loader is not None, "pgvector is not importable. Run: pip install -r requirements.txt"


# ---------------------------------------------------------------------------
# requirements.txt content tests
# ---------------------------------------------------------------------------


def test_root_requirements_contains_pgvector() -> None:
    """Root requirements.txt must pin pgvector."""
    assert ROOT_REQUIREMENTS.exists(), f"Missing: {ROOT_REQUIREMENTS}"
    content = ROOT_REQUIREMENTS.read_text()
    assert re.search(r"pgvector", content, re.IGNORECASE), "pgvector not found in requirements.txt"


def test_backend_requirements_exists() -> None:
    """backend/requirements.txt must exist."""
    assert BACKEND_REQUIREMENTS.exists(), (
        f"Missing: {BACKEND_REQUIREMENTS}\nCreate it with a single line: -r ../requirements.txt"
    )


def test_backend_requirements_delegates_to_root() -> None:
    """backend/requirements.txt must delegate to root via -r include."""
    assert BACKEND_REQUIREMENTS.exists(), f"Missing: {BACKEND_REQUIREMENTS}"
    content = BACKEND_REQUIREMENTS.read_text().strip()
    assert "-r ../requirements.txt" in content, (
        f"backend/requirements.txt must contain '-r ../requirements.txt', got:\n{content}"
    )


# ---------------------------------------------------------------------------
# Alembic migration tests
# ---------------------------------------------------------------------------


def _find_migration_file() -> pathlib.Path | None:
    """Locate the V5-1 migration by slug name."""
    for f in ALEMBIC_VERSIONS_DIR.glob("*.py"):
        if MIGRATION_SLUG in f.name:
            return f
    return None


def test_v5_1_migration_file_exists() -> None:
    """Migration file with slug v5_1_pgvector_extension must exist."""
    migration = _find_migration_file()
    assert migration is not None, (
        f"No migration file matching '*{MIGRATION_SLUG}*.py' in {ALEMBIC_VERSIONS_DIR}"
    )


def test_v5_1_migration_contains_create_extension() -> None:
    """Migration upgrade() must emit CREATE EXTENSION IF NOT EXISTS vector."""
    migration = _find_migration_file()
    assert migration is not None, "Migration file not found"
    content = migration.read_text()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in content, (
        "Migration upgrade() must contain: CREATE EXTENSION IF NOT EXISTS vector"
    )


def test_v5_1_migration_contains_drop_extension() -> None:
    """Migration downgrade() must emit DROP EXTENSION IF EXISTS vector."""
    migration = _find_migration_file()
    assert migration is not None, "Migration file not found"
    content = migration.read_text()
    assert "DROP EXTENSION IF EXISTS vector" in content, (
        "Migration downgrade() must contain: DROP EXTENSION IF EXISTS vector"
    )


def test_v5_1_migration_down_revision_is_v4_head() -> None:
    """Migration down_revision must point to a1b2c3d4e5f6 (V4 head)."""
    migration = _find_migration_file()
    assert migration is not None, "Migration file not found"
    content = migration.read_text()
    assert "a1b2c3d4e5f6" in content, "Migration down_revision must reference a1b2c3d4e5f6"


def test_v5_1_migration_has_type_ignore_on_op_import() -> None:
    """Migration must use # type: ignore[attr-defined] on alembic op import."""
    migration = _find_migration_file()
    assert migration is not None, "Migration file not found"
    content = migration.read_text()
    # Check the import line has the type ignore comment
    has_type_ignore = any(
        "from alembic import op" in line and "type: ignore" in line for line in content.splitlines()
    )
    assert has_type_ignore, (
        "Migration must have: from alembic import op  # type: ignore[attr-defined]"
    )
