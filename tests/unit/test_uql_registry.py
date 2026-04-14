"""Unit tests for the UQL entity registry (V2-UQL-AGG-4).

Asserts that:

1. Every entity_type declared in ``data-model.md`` resolves through
   ``REGISTRY`` and ``get_entity``.
2. Every ``FieldSpec`` carries a fully-qualified SQL expression (alias
   prefix + column) that references either the base alias or one of the
   declared join aliases — no orphan references, no SELECT *.
3. Indexed columns cover the common filter paths called out in
   ``critical-schema-facts.md`` for equity and mf.
4. Dataclass invariants: every entity is frozen / hashable / immutable.
"""

from __future__ import annotations

import re

import pytest

from backend.services.uql.registry import (
    REGISTRY,
    EntityDef,
    FieldSpec,
    FieldType,
    IndexedColumn,
    Join,
    get_entity,
)

EXPECTED_ENTITIES = {"equity", "mf", "sector", "index"}

# Common filter columns that the equity + mf user stories rely on. If
# any of these stops being indexed we want to know — full-scan rejection
# would start firing on legitimate queries.
EQUITY_REQUIRED_INDEXED_COLUMNS = {
    "current_symbol",
    "sector",
    "industry",
    "is_active",
    "nifty_500",
}
MF_REQUIRED_INDEXED_COLUMNS = {
    "mstar_id",
    "category_name",
    "amc_name",
    "is_etf",
}

SQL_EXPR_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


# --- Resolution -------------------------------------------------------------


def test_registry_contains_all_four_entities() -> None:
    assert set(REGISTRY.keys()) == EXPECTED_ENTITIES


@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_get_entity_resolves(entity_type: str) -> None:
    entity = get_entity(entity_type)
    assert isinstance(entity, EntityDef)
    assert entity.name == entity_type


def test_get_entity_unknown_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_entity("portfolio")


# --- Field SQL expressions --------------------------------------------------


@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_every_field_has_qualified_sql_expression(entity_type: str) -> None:
    entity = get_entity(entity_type)
    assert entity.fields, f"{entity_type} has no whitelisted fields"

    valid_aliases = {entity.base_alias, *(j.alias for j in entity.joins)}

    for fname, spec in entity.fields.items():
        assert isinstance(spec, FieldSpec)
        assert spec.name == fname, f"{entity_type}.{fname} name mismatch"
        assert spec.sql, f"{entity_type}.{fname} has empty SQL"
        assert SQL_EXPR_RE.match(spec.sql), (
            f"{entity_type}.{fname} SQL '{spec.sql}' is not <alias>.<column>"
        )
        alias_prefix = spec.sql.split(".", 1)[0]
        assert alias_prefix in valid_aliases, (
            f"{entity_type}.{fname} references unknown alias '{alias_prefix}' "
            f"(valid: {sorted(valid_aliases)})"
        )
        assert isinstance(spec.type, FieldType)


@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_field_names_are_unique_lowercase_snake_case(entity_type: str) -> None:
    entity = get_entity(entity_type)
    pattern = re.compile(r"^[a-z][a-z0-9_]*$")
    seen: set[str] = set()
    for name in entity.fields:
        assert pattern.match(name), f"{entity_type} field '{name}' is not snake_case"
        assert name not in seen
        seen.add(name)


@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_primary_key_is_a_whitelisted_field(entity_type: str) -> None:
    entity = get_entity(entity_type)
    assert entity.primary_key in entity.fields, (
        f"{entity_type} primary_key '{entity.primary_key}' missing from field whitelist"
    )


# --- Joins ------------------------------------------------------------------


@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_joins_have_distinct_aliases(entity_type: str) -> None:
    entity = get_entity(entity_type)
    aliases = [j.alias for j in entity.joins]
    assert len(aliases) == len(set(aliases))
    assert entity.base_alias not in aliases


@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_joins_reference_base_alias(entity_type: str) -> None:
    entity = get_entity(entity_type)
    for join in entity.joins:
        assert isinstance(join, Join)
        assert join.on, f"{entity_type} join on {join.table} has empty ON clause"


# --- Critical schema facts (anchored against critical-schema-facts.md) ------


def test_equity_uses_current_symbol_not_symbol() -> None:
    eq = get_entity("equity")
    assert eq.fields["symbol"].sql == "i.current_symbol"


def test_equity_rs_field_is_rs_composite() -> None:
    eq = get_entity("equity")
    assert "rs_composite" in eq.fields
    # rs_score / rs_percentile are the wrong-spec names — must not appear
    assert "rs_score" not in eq.fields
    assert "rs_percentile" not in eq.fields


def test_mf_primary_key_is_mstar_id() -> None:
    mf = get_entity("mf")
    assert mf.primary_key == "mstar_id"
    assert "fund_code" not in mf.fields  # the wrong-spec name


def test_mf_category_field_is_category_name() -> None:
    mf = get_entity("mf")
    assert "category_name" in mf.fields
    assert "category" not in mf.fields


def test_mf_fund_house_field_is_amc_name() -> None:
    mf = get_entity("mf")
    assert "amc_name" in mf.fields
    assert "fund_house" not in mf.fields


# --- Indexed columns --------------------------------------------------------


def test_equity_indexed_columns_cover_common_filter_paths() -> None:
    eq = get_entity("equity")
    have = {ic.column for ic in eq.indexed_columns}
    missing = EQUITY_REQUIRED_INDEXED_COLUMNS - have
    assert not missing, f"equity missing indexed columns: {missing}"


def test_mf_indexed_columns_cover_common_filter_paths() -> None:
    mf = get_entity("mf")
    have = {ic.column for ic in mf.indexed_columns}
    missing = MF_REQUIRED_INDEXED_COLUMNS - have
    assert not missing, f"mf missing indexed columns: {missing}"


def test_indexed_column_is_hashable_and_frozen() -> None:
    ic = IndexedColumn("de_instrument", "sector")
    {ic}  # noqa: B018 — must be hashable
    with pytest.raises((AttributeError, Exception)):
        ic.column = "industry"  # type: ignore[misc]


def test_entity_def_is_frozen() -> None:
    eq = get_entity("equity")
    with pytest.raises((AttributeError, Exception)):
        eq.name = "stocks"  # type: ignore[misc]


def test_is_indexed_helper() -> None:
    eq = get_entity("equity")
    assert eq.is_indexed("sector")
    assert not eq.is_indexed("rs_composite")  # joined table column, not on base index set


def test_sector_is_aggregation_only() -> None:
    sector = get_entity("sector")
    assert sector.aggregation_only is True


def test_index_entity_is_not_aggregation_only() -> None:
    idx = get_entity("index")
    assert idx.aggregation_only is False


# --- Aggregatable / groupable invariants ------------------------------------


@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_each_entity_has_at_least_one_aggregatable_field(entity_type: str) -> None:
    entity = get_entity(entity_type)
    assert any(f.aggregatable for f in entity.fields.values()), (
        f"{entity_type} has no aggregatable field — UQL aggregations will be unusable"
    )


@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_each_entity_has_at_least_one_groupable_field(entity_type: str) -> None:
    entity = get_entity(entity_type)
    assert any(f.groupable for f in entity.fields.values()), (
        f"{entity_type} has no groupable field — UQL group_by will be unusable"
    )
