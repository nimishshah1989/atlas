"""Tests for V10-1 ORM models: AtlasQlibFeatures, AtlasQlibSignals, AtlasEvents.

Covers:
- Model class existence and correct __tablename__
- instrument_id index present on qlib tables
- Column types (JSONB, Numeric, etc.)
- Unique constraints exist
- AST scan: no float annotations in qlib_models.py
- AST scan: no print() calls in qlib_models.py
- Integration tests (require live DB, auto-marked by conftest.py)
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_QLIB_MODELS_PATH = Path(__file__).parent.parent.parent / "backend" / "db" / "qlib_models.py"


def _load_model_source() -> str:
    return _QLIB_MODELS_PATH.read_text()


# ---------------------------------------------------------------------------
# Unit tests — no DB connection required
# ---------------------------------------------------------------------------


class TestAtlasQlibFeaturesModel:
    def test_tablename(self) -> None:
        from backend.db.qlib_models import AtlasQlibFeatures

        assert AtlasQlibFeatures.__tablename__ == "atlas_qlib_features"

    def test_instrument_id_column_is_indexed(self) -> None:
        """instrument_id on atlas_qlib_features must have index=True."""
        from backend.db.qlib_models import AtlasQlibFeatures

        indexes = {idx.name for idx in AtlasQlibFeatures.__table__.indexes}
        assert any("instrument_id" in name for name in indexes), (
            f"Expected index on instrument_id, found: {indexes}"
        )

    def test_features_column_is_jsonb(self) -> None:
        """features column must be JSONB."""
        from backend.db.qlib_models import AtlasQlibFeatures
        from sqlalchemy.dialects.postgresql import JSONB

        col = AtlasQlibFeatures.__table__.c["features"]
        assert isinstance(col.type, JSONB), (
            f"features column type is {type(col.type)}, expected JSONB"
        )

    def test_unique_constraint_on_date_instrument(self) -> None:
        """Must have UNIQUE(date, instrument_id)."""
        from sqlalchemy import UniqueConstraint

        from backend.db.qlib_models import AtlasQlibFeatures

        constraints = AtlasQlibFeatures.__table__.constraints
        unique_constraints = [c for c in constraints if isinstance(c, UniqueConstraint)]
        names = [c.name for c in unique_constraints]
        assert "uq_qlib_features_date_instrument" in names, (
            f"uq_qlib_features_date_instrument not found, got: {names}"
        )

    def test_unique_constraint_covers_correct_columns(self) -> None:
        """UNIQUE constraint must cover date + instrument_id."""
        from sqlalchemy import UniqueConstraint

        from backend.db.qlib_models import AtlasQlibFeatures

        constraints = AtlasQlibFeatures.__table__.constraints
        uq = next(
            (
                c
                for c in constraints
                if isinstance(c, UniqueConstraint) and c.name == "uq_qlib_features_date_instrument"
            ),
            None,
        )
        assert uq is not None
        col_names = {c.name for c in uq.columns}
        assert col_names == {"date", "instrument_id"}, f"UNIQUE covers wrong columns: {col_names}"

    def test_soft_delete_columns_present(self) -> None:
        from backend.db.qlib_models import AtlasQlibFeatures

        cols = {c.name for c in AtlasQlibFeatures.__table__.columns}
        assert "is_deleted" in cols
        assert "deleted_at" in cols

    def test_standard_audit_columns_present(self) -> None:
        from backend.db.qlib_models import AtlasQlibFeatures

        cols = {c.name for c in AtlasQlibFeatures.__table__.columns}
        assert "id" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_id_is_uuid(self) -> None:
        """id column must be UUID type per project convention."""
        from backend.db.qlib_models import AtlasQlibFeatures
        from sqlalchemy.dialects.postgresql import UUID

        col = AtlasQlibFeatures.__table__.c["id"]
        assert isinstance(col.type, UUID), f"id column type is {type(col.type)}, expected UUID"


class TestAtlasQlibSignalsModel:
    def test_tablename(self) -> None:
        from backend.db.qlib_models import AtlasQlibSignals

        assert AtlasQlibSignals.__tablename__ == "atlas_qlib_signals"

    def test_instrument_id_column_is_indexed(self) -> None:
        """instrument_id on atlas_qlib_signals must have index=True."""
        from backend.db.qlib_models import AtlasQlibSignals

        indexes = {idx.name for idx in AtlasQlibSignals.__table__.indexes}
        assert any("instrument_id" in name for name in indexes), (
            f"Expected index on instrument_id, found: {indexes}"
        )

    def test_signal_score_is_numeric(self) -> None:
        """signal_score must be Numeric (not Float) per financial domain rules."""
        from backend.db.qlib_models import AtlasQlibSignals
        from sqlalchemy import Numeric as SANumeric

        col = AtlasQlibSignals.__table__.c["signal_score"]
        assert isinstance(col.type, SANumeric), (
            f"signal_score type is {type(col.type)}, expected Numeric"
        )

    def test_signal_score_numeric_precision(self) -> None:
        """signal_score must be Numeric(20, 4) per project convention."""
        from backend.db.qlib_models import AtlasQlibSignals
        from sqlalchemy import Numeric as SANumeric

        col = AtlasQlibSignals.__table__.c["signal_score"]
        assert isinstance(col.type, SANumeric)
        assert col.type.precision == 20, f"Expected precision 20, got {col.type.precision}"
        assert col.type.scale == 4, f"Expected scale 4, got {col.type.scale}"

    def test_features_used_is_jsonb(self) -> None:
        """features_used must be JSONB."""
        from backend.db.qlib_models import AtlasQlibSignals
        from sqlalchemy.dialects.postgresql import JSONB

        col = AtlasQlibSignals.__table__.c["features_used"]
        assert isinstance(col.type, JSONB), (
            f"features_used type is {type(col.type)}, expected JSONB"
        )

    def test_unique_constraint_on_date_instrument_model(self) -> None:
        """Must have UNIQUE(date, instrument_id, model_name)."""
        from sqlalchemy import UniqueConstraint

        from backend.db.qlib_models import AtlasQlibSignals

        constraints = AtlasQlibSignals.__table__.constraints
        unique_constraints = [c for c in constraints if isinstance(c, UniqueConstraint)]
        names = [c.name for c in unique_constraints]
        assert "uq_qlib_signals_date_instrument_model" in names, (
            f"uq_qlib_signals_date_instrument_model not found, got: {names}"
        )

    def test_unique_constraint_covers_correct_columns(self) -> None:
        """UNIQUE constraint must cover date + instrument_id + model_name."""
        from sqlalchemy import UniqueConstraint

        from backend.db.qlib_models import AtlasQlibSignals

        constraints = AtlasQlibSignals.__table__.constraints
        uq = next(
            (
                c
                for c in constraints
                if isinstance(c, UniqueConstraint)
                and c.name == "uq_qlib_signals_date_instrument_model"
            ),
            None,
        )
        assert uq is not None
        col_names = {c.name for c in uq.columns}
        assert col_names == {"date", "instrument_id", "model_name"}, (
            f"UNIQUE covers wrong columns: {col_names}"
        )

    def test_signal_score_nullable(self) -> None:
        """signal_score is nullable — a model may produce no score."""
        from backend.db.qlib_models import AtlasQlibSignals

        col = AtlasQlibSignals.__table__.c["signal_score"]
        assert col.nullable, "signal_score should be nullable"

    def test_soft_delete_columns_present(self) -> None:
        from backend.db.qlib_models import AtlasQlibSignals

        cols = {c.name for c in AtlasQlibSignals.__table__.columns}
        assert "is_deleted" in cols
        assert "deleted_at" in cols

    def test_standard_audit_columns_present(self) -> None:
        from backend.db.qlib_models import AtlasQlibSignals

        cols = {c.name for c in AtlasQlibSignals.__table__.columns}
        assert "id" in cols
        assert "created_at" in cols
        assert "updated_at" in cols


class TestAtlasEventsModel:
    def test_tablename(self) -> None:
        from backend.db.qlib_models import AtlasEvents

        assert AtlasEvents.__tablename__ == "atlas_events"

    def test_payload_is_jsonb(self) -> None:
        """payload must be JSONB."""
        from backend.db.qlib_models import AtlasEvents
        from sqlalchemy.dialects.postgresql import JSONB

        col = AtlasEvents.__table__.c["payload"]
        assert isinstance(col.type, JSONB), f"payload type is {type(col.type)}, expected JSONB"

    def test_event_type_is_indexed(self) -> None:
        """event_type column must be indexed."""
        from backend.db.qlib_models import AtlasEvents

        indexes = {idx.name for idx in AtlasEvents.__table__.indexes}
        assert any("event_type" in name for name in indexes), (
            f"Expected index on event_type, found: {indexes}"
        )

    def test_entity_type_is_indexed(self) -> None:
        """entity_type column must be indexed."""
        from backend.db.qlib_models import AtlasEvents

        indexes = {idx.name for idx in AtlasEvents.__table__.indexes}
        assert any("entity_type" in name for name in indexes), (
            f"Expected index on entity_type, found: {indexes}"
        )

    def test_data_as_of_is_indexed(self) -> None:
        """data_as_of column must be indexed."""
        from backend.db.qlib_models import AtlasEvents

        indexes = {idx.name for idx in AtlasEvents.__table__.indexes}
        assert any("data_as_of" in name for name in indexes), (
            f"Expected index on data_as_of, found: {indexes}"
        )

    def test_severity_has_server_default_medium(self) -> None:
        """severity must have server_default='medium'."""
        from backend.db.qlib_models import AtlasEvents

        col = AtlasEvents.__table__.c["severity"]
        assert col.server_default is not None, "severity must have a server_default"
        assert "medium" in str(col.server_default.arg), (
            f"Expected 'medium' in server_default, got: {col.server_default.arg}"
        )

    def test_is_delivered_has_server_default_false(self) -> None:
        """is_delivered must have server_default=false."""
        from backend.db.qlib_models import AtlasEvents

        col = AtlasEvents.__table__.c["is_delivered"]
        assert col.server_default is not None, "is_delivered must have a server_default"

    def test_related_event_ids_is_jsonb(self) -> None:
        """related_event_ids must be JSONB (stores array of UUIDs)."""
        from backend.db.qlib_models import AtlasEvents
        from sqlalchemy.dialects.postgresql import JSONB

        col = AtlasEvents.__table__.c["related_event_ids"]
        assert isinstance(col.type, JSONB), (
            f"related_event_ids type is {type(col.type)}, expected JSONB"
        )

    def test_related_event_ids_nullable(self) -> None:
        from backend.db.qlib_models import AtlasEvents

        col = AtlasEvents.__table__.c["related_event_ids"]
        assert col.nullable, "related_event_ids should be nullable"

    def test_soft_delete_columns_present(self) -> None:
        from backend.db.qlib_models import AtlasEvents

        cols = {c.name for c in AtlasEvents.__table__.columns}
        assert "is_deleted" in cols
        assert "deleted_at" in cols

    def test_standard_audit_columns_present(self) -> None:
        from backend.db.qlib_models import AtlasEvents

        cols = {c.name for c in AtlasEvents.__table__.columns}
        assert "id" in cols
        assert "created_at" in cols
        assert "updated_at" in cols


# ---------------------------------------------------------------------------
# AST anti-pattern detection
# ---------------------------------------------------------------------------


class TestQlibModelsASTScan:
    def test_no_float_annotations(self) -> None:
        """qlib_models.py must not use `: float` annotations (Decimal not float rule)."""
        source = _load_model_source()
        tree = ast.parse(source)
        violations: list[str] = []

        for node in ast.walk(tree):
            # Check function annotations
            if isinstance(node, ast.FunctionDef):
                for arg in node.args.args:
                    if isinstance(arg.annotation, ast.Name) and arg.annotation.id == "float":
                        violations.append(
                            f"Line {arg.annotation.lineno}: arg {arg.arg} annotated as float"
                        )
                if isinstance(node.returns, ast.Name) and node.returns.id == "float":
                    violations.append(f"Line {node.returns.lineno}: return type annotated as float")
            # Check AnnAssign (variable: float = ...)
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.annotation, ast.Name) and node.annotation.id == "float":
                    violations.append(f"Line {node.lineno}: variable annotated as float")

        assert violations == [], "Float annotations found in qlib_models.py:\n" + "\n".join(
            violations
        )

    def test_no_print_calls(self) -> None:
        """qlib_models.py must not contain print() calls (use structlog)."""
        source = _load_model_source()
        tree = ast.parse(source)
        violations: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    violations.append(f"Line {node.lineno}: print() call found")

        assert violations == [], "print() calls found in qlib_models.py:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# Integration tests — require live DB + migrations applied
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_conn():
    """Sync psycopg2 connection for schema introspection tests."""
    raw_url = os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg2://jip_admin:JipDataEngine2026Secure@jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com:5432/data_engine",
    ).replace("postgresql+psycopg2://", "postgresql://")
    import psycopg2  # type: ignore[import-untyped]

    conn = psycopg2.connect(raw_url)
    yield conn
    conn.close()


def _get_columns(conn, table_name: str) -> dict:
    """Return {column_name: (data_type, is_nullable)} for a table."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    rows = cur.fetchall()
    cur.close()
    return {r[0]: (r[1], r[2]) for r in rows}


def _get_indexes(conn, table_name: str) -> set[str]:
    """Return set of index names for a table."""
    cur = conn.cursor()
    cur.execute(
        "SELECT indexname FROM pg_indexes WHERE tablename = %s",
        (table_name,),
    )
    rows = cur.fetchall()
    cur.close()
    return {r[0] for r in rows}


class TestAtlasQlibFeaturesSchema:
    def test_table_exists(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_qlib_features")
        assert cols, "atlas_qlib_features does not exist or has no columns"

    def test_required_columns_exist(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_qlib_features")
        for col in ["id", "date", "instrument_id", "features", "created_at", "updated_at"]:
            assert col in cols, f"Missing column: {col}"

    def test_features_column_is_jsonb(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_qlib_features")
        assert cols["features"][0] == "jsonb", (
            f"features should be jsonb, got: {cols['features'][0]}"
        )

    def test_instrument_id_is_indexed(self, pg_conn) -> None:
        indexes = _get_indexes(pg_conn, "atlas_qlib_features")
        assert any("instrument_id" in name for name in indexes), (
            f"No instrument_id index found, got: {indexes}"
        )

    def test_no_float_columns(self, pg_conn) -> None:
        cur = pg_conn.cursor()
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'atlas_qlib_features'
              AND data_type IN ('real', 'double precision')
            """
        )
        float_cols = cur.fetchall()
        cur.close()
        assert float_cols == [], f"Float columns found: {float_cols}"

    def test_count_is_zero(self, pg_conn) -> None:
        """New table must be empty — no synthetic data (Four Laws)."""
        cur = pg_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM atlas_qlib_features")
        count = cur.fetchone()[0]
        cur.close()
        assert count == 0, f"Expected 0 rows, got {count}"

    def test_soft_delete_columns(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_qlib_features")
        assert "is_deleted" in cols
        assert "deleted_at" in cols


class TestAtlasQlibSignalsSchema:
    def test_table_exists(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_qlib_signals")
        assert cols, "atlas_qlib_signals does not exist or has no columns"

    def test_required_columns_exist(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_qlib_signals")
        for col in [
            "id",
            "date",
            "instrument_id",
            "model_name",
            "signal_score",
            "features_used",
            "created_at",
            "updated_at",
        ]:
            assert col in cols, f"Missing column: {col}"

    def test_signal_score_is_numeric(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_qlib_signals")
        assert cols["signal_score"][0] == "numeric", (
            f"signal_score should be numeric, got: {cols['signal_score'][0]}"
        )

    def test_features_used_is_jsonb(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_qlib_signals")
        assert cols["features_used"][0] == "jsonb", (
            f"features_used should be jsonb, got: {cols['features_used'][0]}"
        )

    def test_instrument_id_is_indexed(self, pg_conn) -> None:
        indexes = _get_indexes(pg_conn, "atlas_qlib_signals")
        assert any("instrument_id" in name for name in indexes), (
            f"No instrument_id index found, got: {indexes}"
        )

    def test_no_float_columns(self, pg_conn) -> None:
        cur = pg_conn.cursor()
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'atlas_qlib_signals'
              AND data_type IN ('real', 'double precision')
            """
        )
        float_cols = cur.fetchall()
        cur.close()
        assert float_cols == [], f"Float columns found: {float_cols}"

    def test_count_is_zero(self, pg_conn) -> None:
        cur = pg_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM atlas_qlib_signals")
        count = cur.fetchone()[0]
        cur.close()
        assert count == 0, f"Expected 0 rows, got {count}"

    def test_soft_delete_columns(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_qlib_signals")
        assert "is_deleted" in cols
        assert "deleted_at" in cols


class TestAtlasEventsSchema:
    def test_table_exists(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_events")
        assert cols, "atlas_events does not exist or has no columns"

    def test_required_columns_exist(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_events")
        for col in [
            "id",
            "event_type",
            "payload",
            "severity",
            "data_as_of",
            "is_delivered",
            "created_at",
            "updated_at",
        ]:
            assert col in cols, f"Missing column: {col}"

    def test_payload_is_jsonb(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_events")
        assert cols["payload"][0] == "jsonb", f"payload should be jsonb, got: {cols['payload'][0]}"

    def test_event_type_indexed(self, pg_conn) -> None:
        indexes = _get_indexes(pg_conn, "atlas_events")
        assert any("event_type" in name for name in indexes), (
            f"No event_type index found, got: {indexes}"
        )

    def test_data_as_of_indexed(self, pg_conn) -> None:
        indexes = _get_indexes(pg_conn, "atlas_events")
        assert any("data_as_of" in name for name in indexes), (
            f"No data_as_of index found, got: {indexes}"
        )

    def test_no_float_columns(self, pg_conn) -> None:
        cur = pg_conn.cursor()
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'atlas_events'
              AND data_type IN ('real', 'double precision')
            """
        )
        float_cols = cur.fetchall()
        cur.close()
        assert float_cols == [], f"Float columns found: {float_cols}"

    def test_count_is_zero(self, pg_conn) -> None:
        cur = pg_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM atlas_events")
        count = cur.fetchone()[0]
        cur.close()
        assert count == 0, f"Expected 0 rows, got {count}"

    def test_soft_delete_columns(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_events")
        assert "is_deleted" in cols
        assert "deleted_at" in cols


class TestV101AlembicMigration:
    def test_alembic_at_head_after_v10_1(self, pg_conn) -> None:
        """Atlas alembic version must be at V10-1 head after migration."""
        from alembic.config import Config  # type: ignore[import-untyped]
        from alembic.script import ScriptDirectory  # type: ignore[import-untyped]

        cfg = Config("/home/ubuntu/atlas/alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        expected_head = script.get_heads()[0]

        cur = pg_conn.cursor()
        cur.execute("SELECT version_num FROM atlas_alembic_version")
        rows = cur.fetchall()
        cur.close()
        versions = [r[0] for r in rows]
        assert expected_head in versions, (
            f"Expected alembic head {expected_head} in versions, got: {versions}"
        )

    def test_single_alembic_head(self) -> None:
        """Must have exactly one alembic head (no branch split)."""
        from alembic.config import Config  # type: ignore[import-untyped]
        from alembic.script import ScriptDirectory  # type: ignore[import-untyped]

        cfg = Config("/home/ubuntu/atlas/alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        assert len(heads) == 1, f"Expected 1 alembic head, got: {heads}"
        assert heads[0] == "k8l9m0n1o2p3", f"Expected head k8l9m0n1o2p3, got: {heads[0]}"
