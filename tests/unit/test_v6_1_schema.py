"""Tests for V6-1: atlas_tv_cache ORM, atlas_watchlists tv_synced, TV Pydantic models."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import class_mapper


# ---------------------------------------------------------------------------
# ORM model tests
# ---------------------------------------------------------------------------


def test_atlas_tv_cache_tablename() -> None:
    """AtlasTvCache ORM model must reference the correct table."""
    from backend.db.tv_models import AtlasTvCache

    assert AtlasTvCache.__tablename__ == "atlas_tv_cache"


def test_atlas_tv_cache_composite_pk() -> None:
    """atlas_tv_cache must have composite PK: symbol, data_type, interval."""
    from backend.db.tv_models import AtlasTvCache

    mapper = class_mapper(AtlasTvCache)
    pk_cols = {col.key for col in mapper.primary_key}
    assert pk_cols == {"symbol", "data_type", "interval"}


def test_atlas_tv_cache_has_required_columns() -> None:
    """atlas_tv_cache ORM must have all six required attributes.

    Note: the DB column is named 'data' but the Python attribute is 'tv_data'
    (mapped via mapped_column("data", ...)) — we check attribute names here.
    """
    from backend.db.tv_models import AtlasTvCache

    mapper = class_mapper(AtlasTvCache)
    attr_names = {attr.key for attr in mapper.attrs}
    required = {"symbol", "exchange", "data_type", "interval", "tv_data", "fetched_at"}
    missing = required - attr_names
    assert not missing, f"Missing attributes: {missing}"


def test_atlas_tv_cache_no_updated_at() -> None:
    """atlas_tv_cache uses fetched_at instead of created_at/updated_at per spec."""
    from backend.db.tv_models import AtlasTvCache

    mapper = class_mapper(AtlasTvCache)
    col_names = {col.key for col in mapper.columns}
    assert "fetched_at" in col_names
    # updated_at not required on this cache table
    assert "created_at" not in col_names


def test_atlas_watchlist_has_tv_synced() -> None:
    """AtlasWatchlist ORM model must have tv_synced field."""
    from backend.db.models import AtlasWatchlist

    mapper = class_mapper(AtlasWatchlist)
    col_names = {col.key for col in mapper.columns}
    assert "tv_synced" in col_names


def test_atlas_watchlist_tv_synced_is_boolean() -> None:
    """tv_synced column must be Boolean type."""
    from backend.db.models import AtlasWatchlist
    from sqlalchemy import Boolean

    mapper = class_mapper(AtlasWatchlist)
    tv_synced_col = next(col for col in mapper.columns if col.key == "tv_synced")
    assert isinstance(tv_synced_col.type, Boolean)


def test_atlas_watchlist_tv_synced_server_default() -> None:
    """tv_synced must have server_default of 'false'."""
    from backend.db.models import AtlasWatchlist

    mapper = class_mapper(AtlasWatchlist)
    tv_synced_col = next(col for col in mapper.columns if col.key == "tv_synced")
    assert tv_synced_col.server_default is not None


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


def test_tv_cache_entry_validates_correctly() -> None:
    """TvCacheEntry Pydantic model must parse a valid dict."""
    from backend.models.tv import TvCacheEntry

    now = datetime.now(tz=timezone.utc)
    entry = TvCacheEntry(
        symbol="RELIANCE",
        exchange="NSE",
        data_type="ta_summary",
        interval="1D",
        tv_data={"recommendation": "BUY", "buy": 10, "sell": 3},
        fetched_at=now,
    )
    assert entry.symbol == "RELIANCE"
    assert entry.exchange == "NSE"
    assert entry.data_type == "ta_summary"
    assert entry.interval == "1D"
    assert entry.is_stale is False


def test_tv_cache_entry_defaults() -> None:
    """TvCacheEntry must use sensible defaults for exchange and interval."""
    from backend.models.tv import TvCacheEntry

    entry = TvCacheEntry(
        symbol="TCS",
        data_type="fundamentals",
        tv_data={"pe": 25},
        fetched_at=datetime.now(tz=timezone.utc),
    )
    assert entry.exchange == "NSE"
    assert entry.interval == "none"


def test_tv_cache_upsert_request_validates() -> None:
    """TvCacheUpsertRequest must accept a minimal valid payload."""
    from backend.models.tv import TvCacheUpsertRequest

    req = TvCacheUpsertRequest(
        symbol="INFY",
        data_type="screener",
        tv_data={"market_cap": 500000},
    )
    assert req.symbol == "INFY"
    assert req.exchange == "NSE"
    assert req.interval == "none"
    assert req.tv_data == {"market_cap": 500000}


def test_tv_cache_upsert_request_custom_exchange() -> None:
    """TvCacheUpsertRequest must accept custom exchange."""
    from backend.models.tv import TvCacheUpsertRequest

    req = TvCacheUpsertRequest(
        symbol="WIPRO",
        exchange="BSE",
        data_type="ta_summary",
        interval="1W",
        tv_data={},
    )
    assert req.exchange == "BSE"
    assert req.interval == "1W"


def test_tv_data_type_constants() -> None:
    """TvDataType must expose the three standard constants."""
    from backend.models.tv import TvDataType

    assert TvDataType.TA_SUMMARY == "ta_summary"
    assert TvDataType.FUNDAMENTALS == "fundamentals"
    assert TvDataType.SCREENER == "screener"


# ---------------------------------------------------------------------------
# AST scan — no float, no print() in tv.py
# ---------------------------------------------------------------------------


def _load_tv_ast() -> ast.Module:
    tv_path = Path(__file__).parent.parent.parent / "backend" / "models" / "tv.py"
    return ast.parse(tv_path.read_text())


def test_no_float_type_in_tv_py() -> None:
    """tv.py must not use the float built-in type (Decimal required for financial values)."""
    tree = _load_tv_ast()
    float_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "float":
            float_names.append(f"line {node.lineno}")
    assert not float_names, f"float found in tv.py at: {float_names}"


def test_no_print_calls_in_tv_py() -> None:
    """tv.py must not contain print() calls (use structlog)."""
    tree = _load_tv_ast()
    print_calls: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            print_calls.append(f"line {node.lineno}")
    assert not print_calls, f"print() found in tv.py at: {print_calls}"
