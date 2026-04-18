#!/usr/bin/env python3
"""
ATLAS Fixture Seed Script — V1FE-2

Generates all 8 fixture JSON files deterministically from a given --as-of date.
Same --as-of date always produces byte-identical output.

Usage:
    python scripts/seed_fixtures.py --as-of 2026-04-17
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "frontend" / "mockups" / "fixtures"


def _seed_rng(as_of: str) -> None:
    """Seed random with the as-of date string for deterministic output."""
    random.seed(as_of)


def _jd(data: object) -> str:
    """Deterministic JSON serialization."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)


def _make_events(as_of: str) -> dict:  # type: ignore[type-arg]
    """India macro + global market events fixture."""
    return {
        "data_as_of": as_of,
        "source": "ATLAS hand-curated (India macro + global)",
        "events": [
            {
                "date": "2020-03-24",
                "category": "covid",
                "severity": "critical",
                "label": "COVID-19 National Lockdown",
                "affects": ["india", "global"],
            },
            {
                "date": "2020-03-27",
                "category": "rbi_policy",
                "severity": "high",
                "label": "RBI Emergency Rate Cut — 75 bps",
                "affects": ["india"],
            },
            {
                "date": "2016-11-08",
                "category": "demonetisation",
                "severity": "critical",
                "label": "Demonetisation Announcement",
                "affects": ["india"],
            },
            {
                "date": "2019-05-23",
                "category": "election",
                "severity": "high",
                "label": "General Election Result — NDA Majority",
                "affects": ["india"],
            },
            {
                "date": "2021-02-01",
                "category": "budget",
                "severity": "high",
                "label": "Union Budget 2021-22",
                "affects": ["india"],
            },
            {
                "date": "2022-05-04",
                "category": "rbi_policy",
                "severity": "high",
                "label": "RBI Emergency Rate Hike — 40 bps",
                "affects": ["india"],
            },
            {
                "date": "2024-04-19",
                "category": "global_macro",
                "severity": "medium",
                "label": "Middle East Escalation — Iran-Israel",
                "affects": ["global", "india"],
            },
            {
                "date": "2024-06-04",
                "category": "election",
                "severity": "high",
                "label": "General Election 2024 — Coalition",
                "affects": ["india"],
            },
        ],
    }


def _make_breadth_daily_5y(as_of: str) -> dict:  # type: ignore[type-arg]
    """Breadth daily 5-year fixture (nifty500 universe)."""
    # Generate 5 sample rows ending at as_of
    # Use multiples of 0.25 for index values to avoid float precision issues with multipleOf:0.0001
    from datetime import date, timedelta

    as_of_dt = date.fromisoformat(as_of)
    rows = []
    base_ema21 = 320
    base_dma50 = 290
    base_dma200 = 245
    base_close = 12500.0
    for i in range(5, 0, -1):
        d = as_of_dt - timedelta(days=i)
        delta = random.randint(-15, 15)
        # Use multiples of 0.25 for float-safe values
        idx_close = round(round((base_close + i * 10.0) * 4) / 4, 4)
        idx_tri = round(round((base_close * 1.12 + i * 12.0) * 4) / 4, 4)
        rows.append(
            {
                "date": d.isoformat(),
                "ema21_count": max(50, min(480, base_ema21 + delta)),
                "dma50_count": max(40, min(480, base_dma50 + delta - 5)),
                "dma200_count": max(30, min(480, base_dma200 + delta - 10)),
                "universe_size": 500,
                "index_close": idx_close,
                "index_tri": idx_tri,
            }
        )
    return {
        "data_as_of": as_of,
        "source": "ATLAS breadth engine — NSE Nifty 500 constituents via JIP",
        "universe": "nifty500",
        "universe_size": 500,
        "series": rows,
    }


def _make_zone_events(as_of: str) -> dict:  # type: ignore[type-arg]
    """Zone crossing events fixture."""
    return {
        "data_as_of": as_of,
        "source": "ATLAS zone detection engine — breadth_daily_5y derived",
        "universe": "nifty500",
        "events": [
            {
                "date": "2024-03-15",
                "universe": "nifty500",
                "indicator": "dma200",
                "event_type": "exited_os",
                "value": 272,
                "prior_zone": "os",
                "prior_zone_duration_days": 34,
            },
            {
                "date": "2024-06-10",
                "universe": "nifty500",
                "indicator": "ema21",
                "event_type": "entered_ob",
                "value": 388,
                "prior_zone": "neutral",
                "prior_zone_duration_days": 87,
            },
            {
                "date": "2025-01-20",
                "universe": "nifty500",
                "indicator": "dma200",
                "event_type": "entered_os",
                "value": 98,
                "prior_zone": "neutral",
                "prior_zone_duration_days": 12,
            },
            {
                "date": "2025-09-04",
                "universe": "nifty500",
                "indicator": "dma50",
                "event_type": "crossed_midline_up",
                "value": 252,
                "prior_zone": "neutral",
                "prior_zone_duration_days": 45,
            },
        ],
    }


def _make_search_index(as_of: str) -> dict:  # type: ignore[type-arg]
    """Search index fixture for fuzzy search."""
    return {
        "data_as_of": as_of,
        "source": "ATLAS search index (NSE + AMFI)",
        "entries": [
            {
                "id": "stock:reliance",
                "entity_type": "stock",
                "display_name": "Reliance Industries",
                "aliases": ["RIL", "Reliance", "RELIANCE"],
                "primary_url": "/mockups/stock-detail.html?symbol=RELIANCE",
                "ranking_weight": 1.0,
            },
            {
                "id": "stock:hdfcbank",
                "entity_type": "stock",
                "display_name": "HDFC Bank",
                "aliases": ["HDFC Bank", "HDB", "HDFCBANK"],
                "primary_url": "/mockups/stock-detail.html?symbol=HDFCBANK",
                "ranking_weight": 0.95,
            },
            {
                "id": "stock:infy",
                "entity_type": "stock",
                "display_name": "Infosys",
                "aliases": ["Infosys", "INFY", "Infy"],
                "primary_url": "/mockups/stock-detail.html?symbol=INFY",
                "ranking_weight": 0.92,
            },
            {
                "id": "mf:ppfas-flexi-cap-direct-growth",
                "entity_type": "mf",
                "display_name": "Parag Parikh Flexi Cap Fund - Direct Growth",
                "aliases": ["PPFAS", "Parag Parikh Flexi", "PPFCF"],
                "primary_url": "/mockups/mf-detail.html?id=ppfas-flexi-cap-direct-growth",
                "ranking_weight": 0.88,
            },
            {
                "id": "mf:mirae-large-cap-direct-growth",
                "entity_type": "mf",
                "display_name": "Mirae Asset Large Cap Fund - Direct Growth",
                "aliases": ["Mirae Large Cap", "MALCF"],
                "primary_url": "/mockups/mf-detail.html?id=mirae-large-cap-direct-growth",
                "ranking_weight": 0.82,
            },
            {
                "id": "sector:nifty_it",
                "entity_type": "sector",
                "display_name": "Nifty IT",
                "aliases": ["IT sector", "technology", "Nifty IT"],
                "primary_url": "/mockups/explore-sector.html?sector=nifty_it",
                "ranking_weight": 0.78,
            },
            {
                "id": "sector:nifty_bank",
                "entity_type": "sector",
                "display_name": "Nifty Bank",
                "aliases": ["Bank Nifty", "banking sector", "Nifty Bank"],
                "primary_url": "/mockups/explore-sector.html?sector=nifty_bank",
                "ranking_weight": 0.80,
            },
            {
                "id": "page:today",
                "entity_type": "page",
                "display_name": "Today — Market Pulse",
                "aliases": ["pulse", "today", "home", "dashboard"],
                "primary_url": "/mockups/today.html",
                "ranking_weight": 0.70,
            },
            {
                "id": "page:mf-rank",
                "entity_type": "page",
                "display_name": "MF Rank — 4-Factor Scoring",
                "aliases": ["MF rank", "mutual fund ranking", "fund screener"],
                "primary_url": "/mockups/mf-rank.html",
                "ranking_weight": 0.65,
            },
            {
                "id": "page:lab",
                "entity_type": "page",
                "display_name": "Lab — Breadth Playback",
                "aliases": ["lab", "simulator", "backtest", "playback"],
                "primary_url": "/mockups/lab.html",
                "ranking_weight": 0.60,
            },
            {
                "id": "stock:tcs",
                "entity_type": "stock",
                "display_name": "Tata Consultancy Services",
                "aliases": ["TCS", "Tata Consultancy", "tcs"],
                "primary_url": "/mockups/stock-detail.html?symbol=TCS",
                "ranking_weight": 0.90,
            },
            {
                "id": "stock:wipro",
                "entity_type": "stock",
                "display_name": "Wipro Limited",
                "aliases": ["Wipro", "WIPRO"],
                "primary_url": "/mockups/stock-detail.html?symbol=WIPRO",
                "ranking_weight": 0.75,
            },
        ],
    }


def _make_ppfas_nav(as_of: str) -> dict:  # type: ignore[type-arg]
    """PPFAS Flexi Cap 5-year NAV series fixture."""
    from datetime import date, timedelta

    as_of_dt = date.fromisoformat(as_of)
    rows = []
    # Use multiples of 0.5 for IEEE 754 exact representation (passes multipleOf:0.0001)
    nav = 55.0
    for i in range(5, 0, -1):
        d = as_of_dt - timedelta(days=i)
        # Generate delta as multiple of 0.5 — always IEEE 754 exact
        delta = random.randint(-2, 3) * 0.5
        nav = nav + delta
        rows.append({"date": d.isoformat(), "nav": nav})
    return {
        "fund_id": "ppfas-flexi-cap-direct-growth",
        "scheme_code": "INF879O01027",
        "fund_name": "Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
        "category": "flexi_cap",
        "benchmark_id": "NIFTY_500_TRI",
        "data_as_of": as_of,
        "source": "AMFI NAV data via ATLAS MF pipeline",
        "series": rows,
    }


def _make_reliance_prices(as_of: str) -> dict:  # type: ignore[type-arg]
    """Reliance Industries 5-year price series fixture."""
    from datetime import date, timedelta

    as_of_dt = date.fromisoformat(as_of)
    rows = []
    # Use integer paise then divide by 100 for IEEE 754-safe 2dp prices
    close_paise = 280000  # 2800.00
    for i in range(5, 0, -1):
        d = as_of_dt - timedelta(days=i)
        delta_paise = random.randint(-2500, 3000)
        close_paise = close_paise + delta_paise
        close = round(close_paise / 100, 2)
        open_paise = close_paise + random.randint(-1000, 1000)
        open_p = round(open_paise / 100, 2)
        high = round(max(open_p, close) + random.randint(0, 2000) / 100, 2)
        low = round(min(open_p, close) - random.randint(0, 1500) / 100, 2)
        # Ensure low is positive
        low = max(low, round(min(open_p, close) * 0.99, 2))
        vol = random.randint(3_000_000, 8_000_000)
        rows.append(
            {
                "date": d.isoformat(),
                "open": open_p,
                "high": high,
                "low": low,
                "close": close,
                "adj_close": close,
                "volume": vol,
            }
        )
    return {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "isin": "INE002A01018",
        "company_name": "Reliance Industries Limited",
        "sector": "Energy",
        "data_as_of": as_of,
        "source": "NSE OHLCV data via JIP de_equity_ohlcv",
        "series": rows,
    }


def _make_mf_rank_universe(as_of: str) -> dict:  # type: ignore[type-arg]
    """MF rank universe with 4-factor composite scores."""

    # Pre-seeded factor_inputs use only IEEE 754-exact values (multiples of 0.25 or powers of 2)
    # to satisfy jsonschema's multipleOf: 0.0001 check (which uses Decimal(float) internals).
    # All values are multiples of 1/16 (=0.0625) or 1/8 or 1/4, which are
    # always IEEE 754 exact binary fractions. This satisfies jsonschema's
    # multipleOf: 0.0001 check which uses Decimal(float) internally.
    _FACTOR_INPUTS_BY_FUND = {
        "ppfas-flexi-cap-direct-growth": {
            "excess_return_1y": 0.0625,  # 1/16
            "excess_return_3y": 0.0500,
            "excess_return_5y": 0.0400,
            "vol_3y": 0.1250,  # 1/8
            "max_dd_3y": 0.2000,
            "downside_dev_3y": 0.0800,  # safe
            "downside_capture": 0.8125,  # 13/16
            "worst_rolling_6m": -0.1250,
            "rolling_12m_alpha": 0.0500,
            "rolling_pct_beating_bench": 0.7500,  # 3/4
        },
        "mirae-large-cap-direct-growth": {
            "excess_return_1y": 0.0500,
            "excess_return_3y": 0.0400,
            "excess_return_5y": 0.0400,
            "vol_3y": 0.1375,  # safe
            "max_dd_3y": 0.2500,  # 1/4
            "downside_dev_3y": 0.1000,
            "downside_capture": 0.8750,  # 7/8
            "worst_rolling_6m": -0.1375,
            "rolling_12m_alpha": 0.0400,
            "rolling_pct_beating_bench": 0.7125,  # safe
        },
        "axis-bluechip-direct-growth": {
            "excess_return_1y": 0.0400,
            "excess_return_3y": 0.0300,
            "excess_return_5y": 0.0250,  # 1/40 (safe)
            "vol_3y": 0.1375,
            "max_dd_3y": 0.2250,  # safe
            "downside_dev_3y": 0.0800,
            "downside_capture": 0.9375,  # 15/16
            "worst_rolling_6m": -0.1375,
            "rolling_12m_alpha": 0.0300,
            "rolling_pct_beating_bench": 0.6250,  # 5/8
        },
        "sbi-small-cap-direct-growth": {
            "excess_return_1y": 0.0800,
            "excess_return_3y": 0.0625,
            "excess_return_5y": 0.0500,
            "vol_3y": 0.1875,  # 3/16
            "max_dd_3y": 0.2750,  # 11/40 (safe)
            "downside_dev_3y": 0.1125,  # safe
            "downside_capture": 1.0000,
            "worst_rolling_6m": -0.1875,
            "rolling_12m_alpha": 0.0500,
            "rolling_pct_beating_bench": 0.8125,  # 13/16
        },
        "hdfc-mid-cap-opportunities-direct": {
            "excess_return_1y": 0.0500,
            "excess_return_3y": 0.0400,
            "excess_return_5y": 0.0400,
            "vol_3y": 0.1625,  # 13/80 (safe)
            "max_dd_3y": 0.2625,  # safe
            "downside_dev_3y": 0.1000,
            "downside_capture": 0.9375,
            "worst_rolling_6m": -0.1625,
            "rolling_12m_alpha": 0.0400,
            "rolling_pct_beating_bench": 0.6875,  # 11/16
        },
    }

    def _make_fund(
        fund_id: str,
        scheme_code: str,
        name: str,
        category: str,
        aum: float,
        age: float,
        returns_score: float,
        risk_score: float,
        resilience_score: float,
        consistency_score: float,
        rank: int,
    ) -> dict:  # type: ignore[type-arg]
        composite = round(
            (returns_score + risk_score + resilience_score + consistency_score) / 4, 1
        )
        return {
            "fund_id": fund_id,
            "scheme_code": scheme_code,
            "scheme_name": name,
            "fund_name": name,
            "category": category,
            "aum_crore": aum,
            "age_years": age,
            "returns_score": returns_score,
            "risk_score": risk_score,
            "resilience_score": resilience_score,
            "consistency_score": consistency_score,
            "composite_score": composite,
            "rank": rank,
            "tie_break_rank": rank,
            "factor_inputs": _FACTOR_INPUTS_BY_FUND[fund_id],
        }

    # Use integer/100 for aum_crore (multipleOf:0.01) and age_years (multipleOf:0.01)
    # Use multiples of 0.25 for IEEE 754-exact score values (multipleOf:0.0001)
    # composite = round((r+k+s+c)/4, 1) — verified for each fund
    funds = [
        _make_fund(
            "ppfas-flexi-cap-direct-growth",
            "INF879O01027",
            "Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
            "flexi_cap",
            62340.25,  # aum_crore (multiple of 0.25 — IEEE 754 safe)
            12.25,  # age_years (multiple of 0.25 — IEEE 754 safe)
            82.5,  # returns  (sum=326.0 -> composite=81.5)
            78.5,  # risk
            80.0,  # resilience
            85.0,  # consistency
            # composite = round((82.5+78.5+80.0+85.0)/4, 1) = round(81.5, 1) = 81.5
            1,
        ),
        _make_fund(
            "mirae-large-cap-direct-growth",
            "INF769K01010",
            "Mirae Asset Large Cap Fund - Direct Plan - Growth",
            "large_cap",
            35120.5,  # aum_crore
            10.25,  # age_years
            75.5,  # returns  (sum=304.0 -> composite=76.0)
            73.0,  # risk
            76.5,  # resilience
            79.0,  # consistency
            # composite = round((75.5+73.0+76.5+79.0)/4, 1) = round(76.0, 1) = 76.0
            2,
        ),
        _make_fund(
            "axis-bluechip-direct-growth",
            "INF846K01EW2",
            "Axis Bluechip Fund - Direct Plan - Growth",
            "large_cap",
            28450.75,  # aum_crore
            9.75,  # age_years
            70.0,  # returns  (sum=294.0 -> composite=73.5)
            74.5,  # risk
            72.5,  # resilience
            77.0,  # consistency
            # composite = round((70.0+74.5+72.5+77.0)/4, 1) = round(73.5, 1) = 73.5
            3,
        ),
        _make_fund(
            "sbi-small-cap-direct-growth",
            "INF200K01RB2",
            "SBI Small Cap Fund - Direct Plan - Growth",
            "small_cap",
            18920.25,  # aum_crore
            8.5,  # age_years
            88.5,  # returns  (sum=286.0 -> composite=71.5)
            55.0,  # risk
            60.5,  # resilience
            82.0,  # consistency
            # composite = round((88.5+55.0+60.5+82.0)/4, 1) = round(71.5, 1) = 71.5
            4,
        ),
        _make_fund(
            "hdfc-mid-cap-opportunities-direct",
            "INF179K01VX1",
            "HDFC Mid-Cap Opportunities Fund - Direct Plan - Growth",
            "mid_cap",
            42380.5,  # aum_crore
            11.25,  # age_years
            79.5,  # returns  (sum=290.0 -> composite=72.5)
            66.0,  # risk
            69.0,  # resilience
            75.5,  # consistency
            # composite = round((79.5+66.0+69.0+75.5)/4, 1) = round(72.5, 1) = 72.5
            5,
        ),
    ]

    return {
        "data_as_of": as_of,
        "source": "ATLAS MF rank engine v1.1 — AMFI NAV + internal scoring",
        "universe_size": len(funds),
        "ranking_as_of": as_of,
        "tie_break_order": ["consistency", "risk", "returns", "resilience"],
        "funds": funds,
    }


def _make_sector_rrg(as_of: str) -> dict:  # type: ignore[type-arg]
    """Sector RRG fixture with tails of length >= 8."""

    def _make_tail(rs_ratio_end: float, rs_mom_end: float) -> list:  # type: ignore[type-arg]
        """Generate 9 tail points ending at the current position."""
        tail = []
        rs_r = rs_ratio_end - round(random.uniform(-3.0, 3.0), 4)
        rs_m = rs_mom_end - round(random.uniform(-2.0, 2.0), 4)
        for i in range(9):
            delta_r = round(random.uniform(-0.5, 0.8), 4)
            delta_m = round(random.uniform(-0.4, 0.6), 4)
            rs_r = round(rs_r + delta_r, 4)
            rs_m = round(rs_m + delta_m, 4)
            tail.append({"rs_ratio": rs_r, "rs_momentum": rs_m})
        return tail

    def _get_quadrant(rs_ratio: float, rs_momentum: float) -> str:
        if rs_ratio >= 100 and rs_momentum >= 100:
            return "leading"
        elif rs_ratio < 100 and rs_momentum >= 100:
            return "improving"
        elif rs_ratio >= 100 and rs_momentum < 100:
            return "weakening"
        else:
            return "lagging"

    # Note: avoid floats like 101.1, 102.8 etc that fail jsonschema multipleOf 0.0001
    # due to IEEE 754 precision (jsonschema uses Decimal internally — some float values
    # don't satisfy the Decimal comparison). Use 4dp values that are safe.
    sectors_data = [
        ("nifty_it", "Nifty IT", 103.2500, 101.4000, 10),
        ("nifty_bank", "Nifty Bank", 97.8100, 98.6200, 12),
        ("nifty_auto", "Nifty Auto", 105.1000, 97.3000, 15),
        ("nifty_pharma", "Nifty Pharma", 101.5500, 102.7500, 20),
        ("nifty_fmcg", "Nifty FMCG", 96.4000, 94.2000, 15),
        ("nifty_metal", "Nifty Metal", 98.7000, 103.5000, 15),
        ("nifty_energy", "Nifty Energy", 99.2000, 96.8000, 15),
        ("nifty_realty", "Nifty Realty", 94.5000, 101.0000, 10),
    ]

    sectors = []
    for slug, name, rs_ratio, rs_momentum, uni_size in sectors_data:
        quadrant = _get_quadrant(rs_ratio, rs_momentum)
        tail = _make_tail(rs_ratio, rs_momentum)
        sectors.append(
            {
                "sector_code": slug,
                "sector_slug": slug,
                "sector_name": name,
                "rs_ratio": rs_ratio,
                "rs_momentum": rs_momentum,
                "quadrant": quadrant,
                "universe_size": uni_size,
                "tail": tail,
            }
        )

    return {
        "data_as_of": as_of,
        "source": "ATLAS Sector RRG engine — NSE index data via JIP",
        "benchmark_id": "NIFTY_500_TRI",
        "lookback_weeks": 14,
        "sectors": sectors,
    }


def seed_all(as_of: str, output_dir: Path) -> None:
    """Generate all 8 fixture JSON files deterministically."""
    output_dir.mkdir(parents=True, exist_ok=True)

    _seed_rng(as_of)

    fixtures = {
        "events.json": _make_events(as_of),
        "breadth_daily_5y.json": _make_breadth_daily_5y(as_of),
        "zone_events.json": _make_zone_events(as_of),
        "search_index.json": _make_search_index(as_of),
        "ppfas_flexi_nav_5y.json": _make_ppfas_nav(as_of),
        "reliance_close_5y.json": _make_reliance_prices(as_of),
        "mf_rank_universe.json": _make_mf_rank_universe(as_of),
        "sector_rrg.json": _make_sector_rrg(as_of),
    }

    for filename, data in fixtures.items():
        out_path = output_dir / filename
        out_path.write_text(_jd(data), encoding="utf-8")
        try:
            rel = out_path.relative_to(ROOT)
        except ValueError:
            rel = out_path
        print(f"  wrote {rel}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ATLAS fixture seed script — generates deterministic fixture JSON files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--as-of",
        default="2026-04-17",
        metavar="DATE",
        help="Fixture data_as_of date (YYYY-MM-DD). Default: 2026-04-17",
    )
    parser.add_argument(
        "--output-dir",
        default=str(FIXTURES_DIR),
        metavar="DIR",
        help=f"Output directory. Default: {FIXTURES_DIR}",
    )
    args = parser.parse_args()

    # Validate date format
    import re

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.as_of):
        print(f"ERROR: --as-of must be YYYY-MM-DD, got {args.as_of!r}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    print(f"Seeding fixtures for data_as_of={args.as_of} into {output_dir}")
    seed_all(args.as_of, output_dir)
    print("Done.")


if __name__ == "__main__":
    main()
