#!/usr/bin/env python3
"""Manifest-driven data health checker.

Reads `docs/specs/data-coverage.yaml` (the single source of truth for what
data Atlas requires) and scores every declared table on the 6-dimension
rubric: coverage, freshness, completeness, continuity, integrity, provenance.

Outputs `data-health.json` (machine-readable) + a markdown summary to stdout.

Design principles enforced here:
  - Zero hardcoded table names. Adding a table = edit YAML, not this script.
  - Every dimension is independently scored 0–100 so failures localise.
  - Fails loud: non-zero exit if any domain falls below the configured floor.

Usage:
    python scripts/check-data-coverage.py                        # all domains
    python scripts/check-data-coverage.py --domain equity_ohlcv  # one domain
    python scripts/check-data-coverage.py --json-only            # no markdown
    python scripts/check-data-coverage.py --strict               # exit 1 on any fail
    python scripts/check-data-coverage.py --mandatory-only       # skip non-mandatory domains
    python scripts/check-data-coverage.py --strict --mandatory-only  # CI mode

Wired into:
    - CI gate (block PRs that drop coverage below threshold)
    - /forge/routines page (consumes data-health.json)
    - post-chunk.sh (after every chunk DONE)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

try:
    import asyncpg
except ImportError:
    print("asyncpg required: pip install asyncpg", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "docs" / "specs" / "data-coverage.yaml"
OUTPUT_PATH = ROOT / "data-health.json"

IST = timezone(timedelta(hours=5, minutes=30))

# Regex to detect year-partitioned table names like de_equity_ohlcv_y2020
_YEAR_PART_RE = re.compile(r".*_y(\d{4})$")


# ─── Data model ──────────────────────────────────────────────────────────


@dataclass
class DimensionScore:
    name: str
    score: float  # 0–100
    detail: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TableHealth:
    table: str
    domain: str
    overall_score: float
    pass_: bool
    dimensions: list[DimensionScore]
    error: str | None = None


# ─── Manifest expansion ──────────────────────────────────────────────────


def expand_partitioned_tables(table_spec: dict[str, Any]) -> list[str]:
    """Resolve `de_equity_ohlcv_y{YEAR}` + `years: [2007, 2026]` → list of names."""
    name = table_spec["name"]
    if "{YEAR}" not in name:
        return [name]
    years = table_spec.get("years", [])
    if not years or len(years) != 2:
        return [name]
    start, end = years
    return [name.replace("{YEAR}", str(y)) for y in range(start, end + 1)]


def collect_tables(
    manifest: dict[str, Any],
    domain_filter: str | None,
    mandatory_only: bool = False,
) -> list[tuple[str, dict[str, Any], str]]:
    """Return list of (resolved_table_name, table_spec, domain_name).

    Args:
        manifest: Parsed YAML manifest dict.
        domain_filter: If set, only include tables from this domain.
        mandatory_only: If True, skip domains where mandatory != True.
    """
    out = []
    for domain_name, domain_spec in manifest.get("domains", {}).items():
        if domain_filter and domain_name != domain_filter:
            continue
        # Skip non-mandatory domains when --mandatory-only is set.
        # Default is True for existing domains (legacy compat).
        if mandatory_only and not domain_spec.get("mandatory", True):
            continue
        for tbl in domain_spec.get("tables", []):
            for resolved in expand_partitioned_tables(tbl):
                out.append((resolved, {**domain_spec, **tbl}, domain_name))
        for tbl in domain_spec.get("proposed_tables", []):
            for resolved in expand_partitioned_tables(tbl):
                spec = {**domain_spec, **tbl, "_proposed": True}
                out.append((resolved, spec, domain_name))
    return out


# ─── Scoring primitives ──────────────────────────────────────────────────


async def table_exists(conn: asyncpg.Connection, table: str) -> bool:
    val: Any = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)",
        table,
    )
    return bool(val)


async def row_count(conn: asyncpg.Connection, table: str) -> int:
    """Use pg_stat for big tables; exact count if pg_stat says small."""
    est: Any = await conn.fetchval(
        "SELECT n_live_tup FROM pg_stat_user_tables WHERE relname = $1", table
    )
    if est is None or int(est) < 10_000:
        exact: Any = await conn.fetchval(f'SELECT COUNT(*) FROM "{table}"')
        return int(exact)
    return int(est)


async def find_date_column(conn: asyncpg.Connection, table: str) -> str | None:
    candidates = [
        "trade_date",
        "nav_date",
        "asof_date",
        "as_of_date",
        "date",
        "filing_date",
        "txn_date",
        "ex_date",
        "effective_date",
        "period_end",
        "flow_date",
        "created_at",
        "updated_at",
    ]
    cols = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = $1",
        table,
    )
    col_names = {r["column_name"] for r in cols}
    for c in candidates:
        if c in col_names:
            return c
    return None


# ─── Dimension scorers ───────────────────────────────────────────────────


async def score_coverage(
    conn: asyncpg.Connection, table: str, spec: dict[str, Any]
) -> DimensionScore:
    rows = await row_count(conn, table)
    expected = spec.get("expected_universe")
    if expected is None:
        # No declared expectation — score by presence of any data.
        score = 100.0 if rows > 0 else 0.0
        detail = f"{rows:,} rows (no universe expectation)"
        return DimensionScore("coverage", score, detail, {"rows": rows})
    history_years = spec.get("history_years", 1)
    expected_rows = expected * history_years * 250  # ~250 trading days/yr
    # For partitioned tables, scale expected_rows down to per-year.
    if "{YEAR}" in spec.get("name", ""):
        expected_rows = expected * 250
    ratio = min(rows / max(expected_rows, 1), 1.0)
    return DimensionScore(
        "coverage",
        round(ratio * 100, 1),
        f"{rows:,} / {expected_rows:,} expected ({ratio * 100:.1f}%)",
        {"rows": rows, "expected": expected_rows},
    )


async def score_freshness(
    conn: asyncpg.Connection, table: str, spec: dict[str, Any]
) -> DimensionScore:
    # Partition-aware: archived year partitions score 100 (SLA not applicable).
    m = _YEAR_PART_RE.match(table)
    if m:
        table_year = int(m.group(1))
        current_year = datetime.now(IST).year
        if table_year < current_year - 1:
            return DimensionScore(
                "freshness",
                100.0,
                f"archived partition (year={table_year}) — SLA not applicable",
                {"table_year": table_year, "archived": True},
            )

    sla = spec.get("sla_freshness_days", 1)
    date_col = await find_date_column(conn, table)
    if date_col is None:
        return DimensionScore("freshness", 0.0, "no date column found", {})
    max_date = await conn.fetchval(f'SELECT MAX("{date_col}") FROM "{table}"')
    if max_date is None:
        return DimensionScore("freshness", 0.0, "table empty", {"date_col": date_col})
    if isinstance(max_date, datetime):
        max_date = max_date.date()
    today = datetime.now(IST).date()
    lag = (today - max_date).days
    score = max(0.0, 100.0 * (1 - max(lag - sla, 0) / max(sla * 5, 5)))
    return DimensionScore(
        "freshness",
        round(score, 1),
        f"max({date_col})={max_date}, lag={lag}d, sla={sla}d",
        {"max_date": str(max_date), "lag_days": lag, "sla_days": sla},
    )


async def score_completeness(
    conn: asyncpg.Connection, table: str, spec: dict[str, Any]
) -> DimensionScore:
    business_cols = spec.get("business_columns") or []
    if not business_cols:
        return DimensionScore("completeness", 100.0, "no business cols declared", {})
    rows = await row_count(conn, table)
    if rows == 0:
        return DimensionScore("completeness", 0.0, "table empty", {})
    sample = min(rows, 50_000)
    null_rates: dict[str, float] = {}
    actual_cols = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = $1",
        table,
    )
    actual = {r["column_name"] for r in actual_cols}
    for col in business_cols:
        if col not in actual:
            null_rates[col] = 1.0
            continue
        q = (
            f'SELECT AVG(CASE WHEN "{col}" IS NULL THEN 1.0 ELSE 0.0 END) '
            f'FROM (SELECT "{col}" FROM "{table}" LIMIT {sample}) s'
        )
        try:
            nr: Any = await conn.fetchval(q)
            null_rates[col] = float(nr or 0.0)
        except Exception as col_err:  # noqa: BLE001
            # asyncpg or type error — treat this column as fully null
            null_rates[col] = 1.0
            print(f"  warn: null-rate query failed for {col}: {col_err}", file=sys.stderr)
    avg_null = sum(null_rates.values()) / len(null_rates)
    return DimensionScore(
        "completeness",
        round((1 - avg_null) * 100, 1),
        f"avg null rate {avg_null * 100:.2f}% across {len(null_rates)} cols",
        {"null_rates": null_rates},
    )


async def score_continuity(
    conn: asyncpg.Connection, table: str, spec: dict[str, Any]
) -> DimensionScore:
    """Gap detection on date series. Skip if no daily cadence implied."""
    if spec.get("sla_freshness_days", 1) > 7:
        return DimensionScore("continuity", 100.0, "non-daily — skipped", {})
    date_col = await find_date_column(conn, table)
    if date_col is None:
        return DimensionScore("continuity", 100.0, "no date col — skipped", {})
    try:
        result = await conn.fetchrow(
            f'SELECT MIN("{date_col}") AS min_d, MAX("{date_col}") AS max_d, '
            f'COUNT(DISTINCT "{date_col}") AS n FROM "{table}"'
        )
    except Exception as e:
        return DimensionScore("continuity", 0.0, f"query failed: {e}", {})
    if not result or result["min_d"] is None:
        return DimensionScore("continuity", 0.0, "table empty", {})
    span_days = (result["max_d"] - result["min_d"]).days + 1
    expected_days = span_days * 5 / 7  # rough trading-day ratio
    ratio = min(result["n"] / max(expected_days, 1), 1.0)
    return DimensionScore(
        "continuity",
        round(ratio * 100, 1),
        (
            f"{result['n']} distinct dates over {span_days}d span "
            f"(expected ~{int(expected_days)} trading days)"
        ),
        {"distinct_dates": result["n"], "span_days": span_days},
    )


async def score_integrity(
    conn: asyncpg.Connection, table: str, spec: dict[str, Any]
) -> DimensionScore:
    """Dedupe check on declared natural key.

    Uses TABLESAMPLE SYSTEM(1) for tables with >500k estimated rows to
    bound execution time to <5s even on 10M-row tables.
    """
    nk = spec.get("natural_key")
    if not nk:
        return DimensionScore("integrity", 100.0, "no natural key declared", {})

    # Check estimated row count via pg_stat to decide sampling strategy.
    est_rows_raw: Any = await conn.fetchval(
        "SELECT n_live_tup FROM pg_stat_user_tables WHERE relname = $1", table
    )
    est_rows = int(est_rows_raw or 0)

    cols_quoted = ", ".join(f'"{c}"' for c in nk)

    if est_rows > 500_000:
        # Large table: use TABLESAMPLE SYSTEM(1) for ~1% random sample.
        try:
            _sample_sql = (
                f"SELECT COUNT(*) FROM ("
                f"SELECT {cols_quoted}, COUNT(*) c "
                f'FROM "{table}" TABLESAMPLE SYSTEM(1) '
                f"GROUP BY {cols_quoted} HAVING COUNT(*) > 1) s"
            )
            dupes: Any = await conn.fetchval(_sample_sql)
        except Exception as e:
            return DimensionScore("integrity", 0.0, f"sampled natural-key check failed: {e}", {})
        sample_rows_est = max(est_rows // 100, 1)
        dupe_rate = int(dupes or 0) / sample_rows_est
        return DimensionScore(
            "integrity",
            round((1 - min(dupe_rate, 1.0)) * 100, 1),
            (f"{dupes} duplicate {nk} groups in ~1% TABLESAMPLE of {est_rows:,} rows (sampled)"),
            {"duplicates": int(dupes or 0), "estimated_rows": est_rows, "sampled": True},
        )

    # Small table: exact count.
    try:
        dupes = await conn.fetchval(
            f"SELECT COUNT(*) FROM ("
            f"SELECT {cols_quoted}, COUNT(*) c "
            f'FROM "{table}" GROUP BY {cols_quoted} HAVING COUNT(*) > 1) s'
        )
    except Exception as e:
        return DimensionScore("integrity", 0.0, f"natural-key check failed: {e}", {})
    rows = await row_count(conn, table)
    if rows == 0:
        return DimensionScore("integrity", 0.0, "table empty", {})
    dupe_rate = dupes / rows
    return DimensionScore(
        "integrity",
        round((1 - min(dupe_rate, 1.0)) * 100, 1),
        f"{dupes} duplicate {nk} groups out of {rows} rows",
        {"duplicates": dupes, "rows": rows},
    )


async def score_provenance(
    conn: asyncpg.Connection, table: str, spec: dict[str, Any]
) -> DimensionScore:
    """Look for ingestion_run_id / source_id / created_at columns."""
    cols = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = $1",
        table,
    )
    col_names = {r["column_name"] for r in cols}
    markers = ["ingestion_run_id", "source_id", "source", "created_at", "updated_at"]
    present = [m for m in markers if m in col_names]
    score = (len(present) / len(markers)) * 100
    return DimensionScore(
        "provenance",
        round(score, 1),
        f"provenance markers present: {present}",
        {"present": present},
    )


# ─── Orchestrator ────────────────────────────────────────────────────────

SCORERS = [
    ("coverage", score_coverage),
    ("freshness", score_freshness),
    ("completeness", score_completeness),
    ("continuity", score_continuity),
    ("integrity", score_integrity),
    ("provenance", score_provenance),
]


async def score_table(
    conn: asyncpg.Connection, table: str, spec: dict[str, Any], domain: str
) -> TableHealth:
    if not await table_exists(conn, table):
        return TableHealth(
            table=table,
            domain=domain,
            overall_score=0.0,
            pass_=False,
            dimensions=[],
            error="table does not exist",
        )
    dims = []
    for _, scorer in SCORERS:
        try:
            dims.append(await scorer(conn, table, spec))
        except Exception as e:
            dim_name = scorer.__name__.replace("score_", "")
            dims.append(DimensionScore(dim_name, 0.0, f"error: {e}", {}))
    return TableHealth(
        table=table,
        domain=domain,
        overall_score=0.0,
        pass_=False,
        dimensions=dims,
    )


def compute_overall(
    table_health: TableHealth,
    weights: dict[str, int],
    pass_floor: float,
    overall_floor: float,
) -> None:
    total_w = sum(weights.values())
    raw = sum(d.score * weights.get(d.name, 0) for d in table_health.dimensions)
    weighted = raw / max(total_w, 1)
    table_health.overall_score = round(weighted, 1)
    per_dim_pass = all(d.score >= pass_floor for d in table_health.dimensions)
    table_health.pass_ = per_dim_pass and table_health.overall_score >= overall_floor


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", help="Limit to one domain")
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any fail")
    parser.add_argument(
        "--mandatory-only",
        action="store_true",
        help="Only check domains with mandatory: true in the manifest",
    )
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()

    if not args.db_url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2
    # Accept SQLAlchemy-style DSNs; asyncpg wants the bare postgresql:// form.
    args.db_url = args.db_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://"
    )

    manifest = yaml.safe_load(MANIFEST_PATH.read_text())
    rubric = manifest.get("rubric", {})
    weights = rubric.get("scoring", {}).get("weights", {})
    pass_floor = rubric.get("scoring", {}).get("pass_threshold", 80)
    overall_floor = rubric.get("scoring", {}).get("overall_threshold", 85)

    tables = collect_tables(manifest, args.domain, mandatory_only=args.mandatory_only)

    conn = await asyncpg.connect(args.db_url)
    try:
        results = []
        for table, spec, domain in tables:
            h = await score_table(conn, table, spec, domain)
            compute_overall(h, weights, pass_floor, overall_floor)
            results.append(h)
    finally:
        await conn.close()

    payload = {
        "generated_at": datetime.now(IST).isoformat(),
        "manifest_version": manifest.get("version"),
        "rubric": rubric,
        "tables": [
            {
                "table": r.table,
                "domain": r.domain,
                "overall_score": r.overall_score,
                "pass": r.pass_,
                "error": r.error,
                "dimensions": [asdict(d) for d in r.dimensions],
            }
            for r in results
        ],
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, default=str))

    if not args.json_only:
        print_markdown_summary(results, pass_floor, overall_floor)

    fail_count = sum(1 for r in results if not r.pass_)
    if args.strict and fail_count:
        return 1
    return 0


def print_markdown_summary(
    results: list[TableHealth], pass_floor: float, overall_floor: float
) -> None:
    by_domain: dict[str, list[TableHealth]] = {}
    for r in results:
        by_domain.setdefault(r.domain, []).append(r)

    print(f"# Atlas Data Health — {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}\n")
    print(f"**Pass thresholds:** per-dim ≥{pass_floor}, overall ≥{overall_floor}\n")
    pass_count = sum(1 for r in results if r.pass_)
    print(f"**Summary:** {pass_count}/{len(results)} tables passing\n\n")

    for domain, rows in sorted(by_domain.items()):
        domain_pass = sum(1 for r in rows if r.pass_)
        domain_status = "PASS" if domain_pass == len(rows) else "FAIL"
        print(f"## {domain} — {domain_status} ({domain_pass}/{len(rows)} tables pass)\n")
        header = (
            "| Table | Overall | Coverage | Freshness | Complete "
            "| Continuity | Integrity | Provenance | Status |"
        )
        print(header)
        print("|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            dim_scores = {d.name: d.score for d in r.dimensions}
            status = "✓" if r.pass_ else ("✗ " + (r.error or ""))
            cov = dim_scores.get("coverage", "-")
            fre = dim_scores.get("freshness", "-")
            com = dim_scores.get("completeness", "-")
            con = dim_scores.get("continuity", "-")
            intg = dim_scores.get("integrity", "-")
            prov = dim_scores.get("provenance", "-")
            row_line = (
                f"| `{r.table}` | **{r.overall_score}** | "
                f"{cov} | {fre} | {com} | {con} | {intg} | {prov} | {status} |"
            )
            print(row_line)
        print()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
