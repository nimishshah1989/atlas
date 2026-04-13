"""Tests for scripts/forge_runner/picker.py (T016).

Tests:
  - eligible V1-1 returned when all deps DONE
  - V1-2 blocked when V1-1 is IN_PROGRESS (dep not satisfied)
  - filter regex excluding V2 chunks
  - empty result on no matches
  - dep outside filter still gates
  - lexicographic ordering: V1-1, V1-10, V1-2 (string sort)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.forge_runner.picker import pick_next


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_chunk(
    conn: sqlite3.Connection,
    chunk_id: str,
    status: str = "PENDING",
    depends_on: str = "[]",
) -> None:
    conn.execute(
        """INSERT INTO chunks (id, title, status, attempts, plan_version,
               depends_on, created_at, updated_at)
           VALUES (?, ?, ?, 0, 'v1', ?, '2026-01-01T00:00:00+05:30',
                   '2026-01-01T00:00:00+05:30')""",
        (chunk_id, f"Title {chunk_id}", status, depends_on),
    )
    conn.commit()


@pytest.fixture
def db_path(fake_state_db: sqlite3.Connection, tmp_path: Path) -> str:
    """Write fake_state_db to a temp file and return the path string."""
    db_file = tmp_path / "state.db"
    # Dump the in-memory DB to file
    disk_conn = sqlite3.connect(str(db_file))
    for line in fake_state_db.iterdump():
        disk_conn.execute(line)
    disk_conn.commit()
    disk_conn.close()
    return str(db_file)


def _db_file_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPickNextEligible:
    def test_eligible_v1_1_returned_when_no_deps(
        self, fake_state_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """V1-1 with no deps and PENDING status is returned."""
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()

        conn = disk_conn
        _insert_chunk(conn, "V1-1", "PENDING", "[]")
        conn.close()

        result = pick_next(".*", str(db_file))
        assert result is not None
        assert result.id == "V1-1"

    def test_eligible_v1_1_when_dep_done(
        self, fake_state_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """V1-1 with a DONE dep is eligible."""
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()

        _insert_chunk(disk_conn, "S4", "DONE", "[]")
        _insert_chunk(disk_conn, "V1-1", "PENDING", '["S4"]')
        disk_conn.close()

        result = pick_next(".*", str(db_file))
        assert result is not None
        assert result.id == "V1-1"


class TestPickNextDepsBlocking:
    def test_v1_2_blocked_when_v1_1_in_progress(
        self, fake_state_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """V1-2 is NOT returned when its dep V1-1 is IN_PROGRESS (not DONE)."""
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()

        _insert_chunk(disk_conn, "V1-1", "IN_PROGRESS", "[]")
        _insert_chunk(disk_conn, "V1-2", "PENDING", '["V1-1"]')
        disk_conn.close()

        result = pick_next(".*", str(db_file))
        assert result is None

    def test_v1_2_blocked_when_dep_not_done(
        self, fake_state_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """V1-2 with dep V1-1 in FAILED state is blocked."""
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()

        _insert_chunk(disk_conn, "V1-1", "FAILED", "[]")
        _insert_chunk(disk_conn, "V1-2", "PENDING", '["V1-1"]')
        disk_conn.close()

        result = pick_next(".*", str(db_file))
        assert result is None

    def test_dep_outside_filter_still_gates(
        self, fake_state_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """V1-1 depending on S4 is blocked even though S4 doesn't match filter."""
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()

        # S4 is PENDING (not DONE) — outside the V1 filter but V1-1 depends on it
        _insert_chunk(disk_conn, "S4", "PENDING", "[]")
        _insert_chunk(disk_conn, "V1-1", "PENDING", '["S4"]')
        disk_conn.close()

        # Filter only V1 chunks — but dep S4 must still be DONE
        result = pick_next(r"^V1-\d+$", str(db_file))
        assert result is None


class TestPickNextFilter:
    def test_filter_excludes_v2_chunks(
        self, fake_state_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """V2 chunks are excluded by a V1-only filter."""
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()

        _insert_chunk(disk_conn, "V2-1", "PENDING", "[]")
        _insert_chunk(disk_conn, "V1-1", "PENDING", "[]")
        disk_conn.close()

        result = pick_next(r"^V1-\d+$", str(db_file))
        assert result is not None
        assert result.id == "V1-1"

    def test_filter_v2_only_excludes_v1(
        self, fake_state_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """V1 chunks excluded when filter is V2-only."""
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()

        _insert_chunk(disk_conn, "V1-1", "PENDING", "[]")
        disk_conn.close()

        result = pick_next(r"^V2-\d+$", str(db_file))
        assert result is None

    def test_empty_result_on_no_matches(
        self, fake_state_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """No chunks match filter — returns None."""
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()

        _insert_chunk(disk_conn, "V1-1", "PENDING", "[]")
        disk_conn.close()

        result = pick_next(r"^NOPE$", str(db_file))
        assert result is None


class TestPickNextOrdering:
    def test_lexicographic_ordering_v1_1_before_v1_10_before_v1_2(
        self, fake_state_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """String-lex ordering: V1-1 < V1-10 < V1-2 (string sort on ID).

        The picker uses ``ORDER BY id`` which is lexicographic string sort.
        V1-10 sorts before V1-2 because '1' < '2' at position 4.
        """
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()

        # Insert in non-sorted order
        _insert_chunk(disk_conn, "V1-2", "PENDING", "[]")
        _insert_chunk(disk_conn, "V1-10", "PENDING", "[]")
        _insert_chunk(disk_conn, "V1-1", "PENDING", "[]")
        disk_conn.close()

        result = pick_next(".*", str(db_file))
        assert result is not None
        # Lexicographic: V1-1 < V1-10 < V1-2
        assert result.id == "V1-1"

    def test_v1_10_picked_before_v1_2_when_v1_1_done(
        self, fake_state_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """After V1-1 is DONE, V1-10 is next (lex: '10' < '2')."""
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()

        _insert_chunk(disk_conn, "V1-1", "DONE", "[]")
        _insert_chunk(disk_conn, "V1-2", "PENDING", '["V1-1"]')
        _insert_chunk(disk_conn, "V1-10", "PENDING", '["V1-1"]')
        disk_conn.close()

        result = pick_next(r"^V1-\d+$", str(db_file))
        assert result is not None
        # Both V1-2 and V1-10 have dep V1-1 DONE; lex: V1-10 < V1-2
        assert result.id == "V1-10"


class TestPickNextEdgeCases:
    def test_empty_db_returns_none(self, fake_state_db: sqlite3.Connection, tmp_path: Path) -> None:
        """Empty state.db returns None without error."""
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()
        disk_conn.close()

        result = pick_next(".*", str(db_file))
        assert result is None

    def test_unknown_dep_blocks_chunk(
        self, fake_state_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Chunk depending on an unknown ID is blocked (safe default)."""
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()

        _insert_chunk(disk_conn, "V1-1", "PENDING", '["UNKNOWN-DEP"]')
        disk_conn.close()

        result = pick_next(".*", str(db_file))
        assert result is None

    def test_first_eligible_returned_when_multiple_candidates(
        self, fake_state_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """When multiple chunks are eligible, the first in lex order is returned."""
        db_file = tmp_path / "state.db"
        disk_conn = sqlite3.connect(str(db_file))
        for line in fake_state_db.iterdump():
            disk_conn.execute(line)
        disk_conn.commit()

        _insert_chunk(disk_conn, "V1-3", "PENDING", "[]")
        _insert_chunk(disk_conn, "V1-1", "PENDING", "[]")
        _insert_chunk(disk_conn, "V1-2", "PENDING", "[]")
        disk_conn.close()

        result = pick_next(".*", str(db_file))
        assert result is not None
        assert result.id == "V1-1"
