"""Route tests for /api/v1/system/* endpoints.

Tests all 4 new endpoints: heartbeat, roadmap, quality, logs/tail.
Uses httpx AsyncClient with FastAPI test client.
"""

from __future__ import annotations

import json
from datetime import timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.main import app

IST = timezone(timedelta(hours=5, minutes=30))
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# App fixture (overrides DB dependency to avoid real DB calls)
# ---------------------------------------------------------------------------


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# /api/v1/system/heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_returns_200(self, client):
        resp = await client.get("/api/v1/system/heartbeat")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_heartbeat_all_fields_present(self, client):
        # Clear cache to get a fresh response
        from backend.routes.system import _cache

        _cache.clear()

        resp = await client.get("/api/v1/system/heartbeat")
        body = resp.json()

        required_fields = [
            "memory_md_mtime",
            "wiki_index_mtime",
            "state_db_mtime",
            "last_chunk_done_at",
            "last_chunk_id",
            "last_quality_run_at",
            "last_quality_score",
            "backend_uptime_seconds",
            "as_of",
            "last_smoke_run_at",
            "last_smoke_result",
            "last_smoke_summary",
        ]
        for field in required_fields:
            assert field in body, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_heartbeat_uptime_positive(self, client):
        from backend.routes.system import _cache

        _cache.clear()

        resp = await client.get("/api/v1/system/heartbeat")
        body = resp.json()
        assert body["backend_uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_heartbeat_as_of_is_ist(self, client):
        from backend.routes.system import _cache

        _cache.clear()

        resp = await client.get("/api/v1/system/heartbeat")
        body = resp.json()
        as_of_str = body["as_of"]
        assert as_of_str is not None
        # Should contain +05:30
        assert "+05:30" in as_of_str

    @pytest.mark.asyncio
    async def test_heartbeat_smoke_fields_null_when_no_smoke_logs(self, client):
        from backend.routes.system import _cache

        _cache.clear()

        # Patch _smoke_log_info to return None values
        no_smoke = {
            "last_smoke_run_at": None,
            "last_smoke_result": None,
            "last_smoke_summary": None,
        }
        with patch("backend.routes.system._smoke_log_info", return_value=no_smoke):
            with patch(
                "backend.routes.system._state_db_info",
                return_value={
                    "state_db_mtime": None,
                    "last_chunk_done_at": None,
                    "last_chunk_id": None,
                    "last_quality_score": None,
                    "last_quality_run_at": None,
                },
            ):
                _cache.clear()
                resp = await client.get("/api/v1/system/heartbeat")
        body = resp.json()
        assert body["last_smoke_run_at"] is None
        assert body["last_smoke_result"] is None
        assert body["last_smoke_summary"] is None

    @pytest.mark.asyncio
    async def test_heartbeat_cache_returns_stale_within_ttl(self, client):
        from backend.routes.system import _cache

        _cache.clear()

        # First call
        resp1 = await client.get("/api/v1/system/heartbeat")
        as_of_1 = resp1.json()["as_of"]

        # Second call immediately — should be cached (same as_of)
        resp2 = await client.get("/api/v1/system/heartbeat")
        as_of_2 = resp2.json()["as_of"]

        assert as_of_1 == as_of_2  # Cache hit


# ---------------------------------------------------------------------------
# /api/v1/system/roadmap
# ---------------------------------------------------------------------------

_MINIMAL_ROADMAP_YAML = """
versions:
  - id: V1
    title: Market to Stock
    goal: FM navigates end to end
    chunks:
      - id: C1
        title: First chunk
        steps:
          - id: C1.1
            text: README exists
            check:
              type: file_exists
              path: README.md
  - id: V2
    title: MF slice
    goal: Category to fund
    chunks: []
"""


class TestRoadmap:
    @pytest.mark.asyncio
    async def test_roadmap_returns_200(self, client, tmp_path):
        roadmap_file = tmp_path / "roadmap.yaml"
        roadmap_file.write_text(_MINIMAL_ROADMAP_YAML)

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system_roadmap.load_roadmap") as mock_load:
            from backend.core.roadmap_loader import load_roadmap as real_load

            mock_load.return_value = real_load(roadmap_file)

            resp = await client.get("/api/v1/system/roadmap")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_roadmap_file_exists_step_ok(self, client, tmp_path):
        """file_exists check pointing at README.md returns ok."""
        roadmap_file = tmp_path / "roadmap.yaml"
        roadmap_file.write_text(_MINIMAL_ROADMAP_YAML)

        readme = REPO_ROOT / "README.md"
        if not readme.exists():
            readme.write_text("test")

        from backend.routes.system import _cache

        _cache.clear()

        from backend.core.roadmap_loader import load_roadmap as real_load

        loaded = real_load(roadmap_file)

        with patch("backend.routes.system_roadmap.load_roadmap", return_value=loaded):
            with patch(
                "backend.routes.system_roadmap._load_chunk_states", return_value={}
            ):
                _cache.clear()
                resp = await client.get("/api/v1/system/roadmap")

        body = resp.json()
        v1 = next(v for v in body["versions"] if v["id"] == "V1")
        c1 = v1["chunks"][0]
        step = c1["steps"][0]
        assert step["check"] == "ok"

    @pytest.mark.asyncio
    async def test_roadmap_failing_command_step_returns_fail_not_500(
        self, client, tmp_path
    ):
        """command: ["false"] returns check:fail, not 500."""
        yaml_content = """
versions:
  - id: V1
    title: Test
    goal: Test
    chunks:
      - id: C1
        title: Chunk with failing command
        steps:
          - id: C1.1
            text: Always fails
            check:
              type: command
              cmd: ["false"]
"""
        roadmap_file = tmp_path / "roadmap.yaml"
        roadmap_file.write_text(yaml_content)

        from backend.core.roadmap_loader import load_roadmap as real_load

        loaded = real_load(roadmap_file)

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system_roadmap.load_roadmap", return_value=loaded):
            with patch(
                "backend.routes.system_roadmap._load_chunk_states", return_value={}
            ):
                _cache.clear()
                resp = await client.get("/api/v1/system/roadmap")

        assert resp.status_code == 200
        body = resp.json()
        v1 = body["versions"][0]
        c1 = v1["chunks"][0]
        step = c1["steps"][0]
        assert step["check"] == "fail"

    @pytest.mark.asyncio
    async def test_roadmap_malicious_command_sandboxed(self, client, tmp_path):
        """rm -rf / attempt: blocked by blocklist OR sandboxed — no side effects."""
        yaml_content = """
versions:
  - id: V1
    title: Test
    goal: Test
    chunks:
      - id: C1
        title: Malicious chunk
        steps:
          - id: C1.1
            text: Dangerous command
            check:
              type: command
              cmd: ["rm", "-rf", "/"]
"""
        roadmap_file = tmp_path / "roadmap.yaml"
        roadmap_file.write_text(yaml_content)

        from backend.core.roadmap_loader import load_roadmap as real_load

        loaded = real_load(roadmap_file)

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system_roadmap.load_roadmap", return_value=loaded):
            with patch(
                "backend.routes.system_roadmap._load_chunk_states", return_value={}
            ):
                _cache.clear()
                resp = await client.get("/api/v1/system/roadmap")

        assert resp.status_code == 200
        body = resp.json()
        step = body["versions"][0]["chunks"][0]["steps"][0]
        # Blocked by blocklist — returns error, not ok
        assert step["check"] == "error"
        assert "blocked-command" in step["detail"]

    @pytest.mark.asyncio
    async def test_roadmap_external_url_blocked(self, client, tmp_path):
        """http_ok with external URL returns error:external-url-blocked."""
        yaml_content = """
versions:
  - id: V1
    title: Test
    goal: Test
    chunks:
      - id: C1
        title: External URL chunk
        steps:
          - id: C1.1
            text: External check
            check:
              type: http_ok
              url: "https://example.com"
"""
        roadmap_file = tmp_path / "roadmap.yaml"
        roadmap_file.write_text(yaml_content)

        from backend.core.roadmap_loader import load_roadmap as real_load

        loaded = real_load(roadmap_file)

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system_roadmap.load_roadmap", return_value=loaded):
            with patch(
                "backend.routes.system_roadmap._load_chunk_states", return_value={}
            ):
                _cache.clear()
                resp = await client.get("/api/v1/system/roadmap")

        assert resp.status_code == 200
        step = resp.json()["versions"][0]["chunks"][0]["steps"][0]
        assert step["check"] == "error"
        assert step["detail"] == "external-url-blocked"

    @pytest.mark.asyncio
    async def test_roadmap_no_yaml_returns_empty(self, client, tmp_path):
        """Missing roadmap.yaml returns empty versions list."""
        from backend.core.roadmap_loader import RoadmapFile
        from backend.routes.system import _cache

        _cache.clear()

        with patch(
            "backend.routes.system_roadmap.load_roadmap",
            return_value=RoadmapFile(versions=[]),
        ):
            _cache.clear()
            resp = await client.get("/api/v1/system/roadmap")

        assert resp.status_code == 200
        assert resp.json()["versions"] == []

    @pytest.mark.asyncio
    async def test_roadmap_smoke_list_slow_skipped_by_default(self, client, tmp_path):
        """smoke_list step returns slow-skipped without ?evaluate_slow=true."""
        yaml_content = """
versions:
  - id: V1
    title: Test
    goal: Test
    chunks:
      - id: C1
        title: Smoke chunk
        steps:
          - id: C1.1
            text: Smoke probe
            check:
              type: smoke_list
              file: "scripts/smoke-endpoints.txt"
"""
        roadmap_file = tmp_path / "roadmap.yaml"
        roadmap_file.write_text(yaml_content)

        from backend.core.roadmap_loader import load_roadmap as real_load

        loaded = real_load(roadmap_file)

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system_roadmap.load_roadmap", return_value=loaded):
            with patch(
                "backend.routes.system_roadmap._load_chunk_states", return_value={}
            ):
                _cache.clear()
                resp = await client.get("/api/v1/system/roadmap")

        step = resp.json()["versions"][0]["chunks"][0]["steps"][0]
        assert step["check"] == "slow-skipped"

    @pytest.mark.asyncio
    async def test_roadmap_unsafe_sql_rejected(self, client, tmp_path):
        """db_query with injection SQL returns error:unsafe-sql."""
        yaml_content = """
versions:
  - id: V1
    title: Test
    goal: Test
    chunks:
      - id: C1
        title: SQL injection attempt
        steps:
          - id: C1.1
            text: Dangerous SQL
            check:
              type: db_query
              sql: "SELECT 1; DROP TABLE chunks; --"
"""
        roadmap_file = tmp_path / "roadmap.yaml"
        roadmap_file.write_text(yaml_content)

        from backend.core.roadmap_loader import load_roadmap as real_load

        loaded = real_load(roadmap_file)

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system_roadmap.load_roadmap", return_value=loaded):
            with patch(
                "backend.routes.system_roadmap._load_chunk_states", return_value={}
            ):
                _cache.clear()
                resp = await client.get("/api/v1/system/roadmap")

        assert resp.status_code == 200
        step = resp.json()["versions"][0]["chunks"][0]["steps"][0]
        assert step["check"] == "error"
        assert step["detail"] == "unsafe-sql"

    @pytest.mark.asyncio
    async def test_roadmap_response_shape(self, client):
        """Response has as_of and versions array."""
        from backend.core.roadmap_loader import RoadmapFile
        from backend.routes.system import _cache

        _cache.clear()

        with patch(
            "backend.routes.system_roadmap.load_roadmap",
            return_value=RoadmapFile(versions=[]),
        ):
            _cache.clear()
            resp = await client.get("/api/v1/system/roadmap")

        body = resp.json()
        assert "as_of" in body
        assert "versions" in body
        assert "+05:30" in body["as_of"]


# ---------------------------------------------------------------------------
# /api/v1/system/quality
# ---------------------------------------------------------------------------


class TestQuality:
    @pytest.mark.asyncio
    async def test_quality_returns_200(self, client):
        from backend.routes.system import _cache

        _cache.clear()

        resp = await client.get("/api/v1/system/quality")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_quality_missing_file_returns_null(self, client, tmp_path):
        """Missing report.json → {"as_of": null, "scores": null}."""
        fake_path = tmp_path / "nonexistent_report.json"

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system._QUALITY_REPORT", fake_path):
            _cache.clear()
            resp = await client.get("/api/v1/system/quality")

        assert resp.status_code == 200
        body = resp.json()
        assert body["as_of"] is None
        assert body["scores"] is None

    @pytest.mark.asyncio
    async def test_quality_existing_file_returns_scores(self, client, tmp_path):
        """Existing report.json returned verbatim with as_of."""
        report = {
            "overall": 97,
            "dimensions": [{"dimension": "security", "score": 100}],
        }
        report_file = tmp_path / "report.json"
        report_file.write_text(json.dumps(report))

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system._QUALITY_REPORT", report_file):
            _cache.clear()
            resp = await client.get("/api/v1/system/quality")

        assert resp.status_code == 200
        body = resp.json()
        assert body["as_of"] is not None
        assert body["scores"]["overall"] == 97
        assert "+05:30" in body["as_of"]


# ---------------------------------------------------------------------------
# /api/v1/system/logs/tail
# ---------------------------------------------------------------------------


class TestLogsTail:
    @pytest.mark.asyncio
    async def test_logs_tail_returns_200(self, client):
        from backend.routes.system import _cache

        _cache.clear()

        resp = await client.get("/api/v1/system/logs/tail")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_logs_tail_response_shape(self, client):
        from backend.routes.system import _cache

        _cache.clear()

        resp = await client.get("/api/v1/system/logs/tail")
        body = resp.json()
        assert "file" in body
        assert "lines" in body
        assert "as_of" in body
        assert isinstance(body["lines"], list)

    @pytest.mark.asyncio
    async def test_logs_tail_lines_zero_empty_array(self, client, tmp_path):
        """lines=0 returns empty array."""
        log_file = tmp_path / "test.log"
        log_file.write_text("line1\nline2\nline3\n")

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system._LOGS_DIR", tmp_path):
            _cache.clear()
            resp = await client.get("/api/v1/system/logs/tail?lines=0")

        assert resp.status_code == 200
        assert resp.json()["lines"] == []

    @pytest.mark.asyncio
    async def test_logs_tail_lines_capped_at_1000(self, client, tmp_path):
        """lines=5000 capped at 1000."""
        log_file = tmp_path / "test.log"
        # Write 2000 lines
        log_file.write_text("\n".join(f"line{i}" for i in range(2000)) + "\n")

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system._LOGS_DIR", tmp_path):
            _cache.clear()
            resp = await client.get("/api/v1/system/logs/tail?lines=5000")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["lines"]) <= 1000

    @pytest.mark.asyncio
    async def test_logs_tail_default_200_lines(self, client, tmp_path):
        """Default returns up to 200 lines."""
        log_file = tmp_path / "test.log"
        log_file.write_text("\n".join(f"line{i}" for i in range(300)) + "\n")

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system._LOGS_DIR", tmp_path):
            _cache.clear()
            resp = await client.get("/api/v1/system/logs/tail")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["lines"]) == 200
        # Last 200 lines
        assert body["lines"][0] == "line100"

    @pytest.mark.asyncio
    async def test_logs_tail_no_logs_dir(self, client, tmp_path):
        """Missing logs dir returns empty file and lines."""
        nonexistent = tmp_path / "no_logs_here"

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system._LOGS_DIR", nonexistent):
            _cache.clear()
            resp = await client.get("/api/v1/system/logs/tail")

        assert resp.status_code == 200
        body = resp.json()
        assert body["file"] == ""
        assert body["lines"] == []

    @pytest.mark.asyncio
    async def test_logs_tail_50_lines(self, client, tmp_path):
        """?lines=50 returns last 50 lines."""
        log_file = tmp_path / "test.log"
        log_file.write_text("\n".join(f"line{i}" for i in range(100)) + "\n")

        from backend.routes.system import _cache

        _cache.clear()

        with patch("backend.routes.system._LOGS_DIR", tmp_path):
            _cache.clear()
            resp = await client.get("/api/v1/system/logs/tail?lines=50")

        body = resp.json()
        assert len(body["lines"]) == 50
        assert body["lines"][0] == "line50"


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


class TestCacheBehavior:
    @pytest.mark.asyncio
    async def test_heartbeat_cached(self, client):
        """Two consecutive calls return same as_of (cache hit)."""
        from backend.routes.system import _cache

        _cache.clear()

        resp1 = await client.get("/api/v1/system/heartbeat")
        resp2 = await client.get("/api/v1/system/heartbeat")

        assert resp1.json()["as_of"] == resp2.json()["as_of"]

    @pytest.mark.asyncio
    async def test_quality_cached(self, client):
        """Two consecutive calls return same as_of (cache hit)."""
        from backend.routes.system import _cache

        _cache.clear()

        resp1 = await client.get("/api/v1/system/quality")
        resp2 = await client.get("/api/v1/system/quality")

        body1 = resp1.json()
        body2 = resp2.json()
        # as_of should be identical (same cached response)
        assert body1["as_of"] == body2["as_of"]


class TestStateDbReadOnly:
    """Regression: state.db must open in sqlite URI ro mode so systemd
    hardening (ProtectHome=read-only + ReadWritePaths excluding orchestrator/)
    can't break chunk status readout. Previously the backend opened rw and
    failed with 'unable to open database file' on the live host, which
    caused the dashboard to show V1 PENDING while state.db had DONE.
    """

    def test_load_chunk_states_reads_done_from_readonly_db(self, tmp_path):
        """_load_chunk_states should return DONE even if the db file path
        is in a dir the process cannot write to."""
        import sqlite3

        from backend.routes import system_roadmap as system_roadmap_mod

        db_path = tmp_path / "state.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE chunks (id TEXT, status TEXT, attempts INT, updated_at TEXT)"
        )
        conn.execute(
            "INSERT INTO chunks VALUES ('C1','DONE',0,'2026-04-13T06:52:14+00:00')"
        )
        conn.commit()
        conn.close()

        with patch.object(system_roadmap_mod, "_STATE_DB", db_path):
            states = system_roadmap_mod._load_chunk_states()

        assert "C1" in states
        assert states["C1"]["status"] == "DONE"

    def test_load_chunk_states_uses_uri_ro_mode(self, tmp_path, monkeypatch):
        """sqlite3.connect must be called with a file: URI that includes
        mode=ro. This is what lets us open the db under systemd
        ProtectHome=read-only."""
        import sqlite3

        from backend.routes import system_roadmap as system_roadmap_mod

        db_path = tmp_path / "state.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE chunks (id TEXT, status TEXT, attempts INT, updated_at TEXT)"
        )
        conn.commit()
        conn.close()

        captured: dict = {}
        real_connect = sqlite3.connect

        def spy_connect(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(system_roadmap_mod.sqlite3, "connect", spy_connect)
        with patch.object(system_roadmap_mod, "_STATE_DB", db_path):
            system_roadmap_mod._load_chunk_states()

        assert captured["kwargs"].get("uri") is True
        assert "mode=ro" in captured["args"][0]
