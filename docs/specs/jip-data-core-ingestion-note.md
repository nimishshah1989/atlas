# JIP Data Core — Ingestion Work Note

**For:** JIP Data Core team
**From:** Atlas
**Date:** 2026-04-18
**Status:** Action required — blocks Atlas frontend work on derivatives, options, gold lens, insider/macro signals

---

## 1. Why this note exists

Atlas has audited what the database currently provides vs what Atlas needs to ship the planned frontend. Outcome: **7/12 wishlist domains fully covered, 3 partial, 2 missing**. The gaps below are blocking and need ingestion work in JIP Data Core before Atlas can ship the corresponding UI surfaces.

The full machine-readable contract is in:
- `docs/specs/data-coverage.yaml` — what Atlas requires (consumer view)
- `docs/specs/jip-source-manifest.yaml` — what JIP must produce (producer view, source URLs, schemas)

This note is the **human-readable companion** — read this first, then go to the YAML for exact column types / SLAs.

---

## 2. Existing — confirmation needed (no new build, just verify)

These routines exist and produce data. JIP team needs to **confirm SLA + close known gaps**, not build from scratch.

| Routine | Status | What we need from JIP |
|---|---|---|
| `equity_ohlcv_daily` (2007–2026) | ✓ live | Confirm bhavcopy backfill complete; confirm `de_equity_ohlcv` (unpartitioned) is intentionally empty (we use partitioned). |
| `mf_nav_daily` | ✓ live | Same — confirm `de_mf_nav_daily` unpartitioned is intentionally empty. |
| `equity_technicals_daily` (3.46M rows) | ✓ live | **Document which TA-Lib indicators are populated** — Atlas needs the column manifest. Send list. |
| `corporate_actions` | ✓ live | **Build downstream:** `de_adjustment_factors_daily` is empty. See §3.A. |
| `institutional_flows` | ⚠ partial | Only 5 rows. Need 10y backfill of FII/DII cash market flows. |
| `de_macro_values` | ✓ live | Confirm presence of: US 2Y yield, US 10Y yield, DXY, MOVE index, gold spot, silver, brent crude, copper, natgas. List which are missing. |

---

## 3. New ingestion work — by priority

### PRIORITY 1 (blocks Atlas frontend on derivatives, options, VIX, adjusted prices)

#### A. Adjustment factors daily — `de_adjustment_factors_daily`
**Why:** Without this, every chart in Atlas shows raw prices that have splits/bonus jumps. Charts will be wrong on day one.
**Source:** Already-ingested `de_corporate_actions` (no new external feed).
**Logic:** For each (symbol, trade_date), compute cumulative split factor × cumulative bonus factor × cumulative dividend factor.
**Cadence:** daily, after corporate_actions ingestion.
**Schema:** see `jip-source-manifest.yaml` → `adjustment_factors_daily`.
**Backfill:** full history (2007 onwards) for all 2k+ stocks.

#### B. F&O bhavcopy daily — `de_fo_bhavcopy_daily`
**Why:** Unlocks options chain analysis, PCR, max-pain, OI buildup signals — all Atlas frontend modules waiting on this.
**Source:** `https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip`
**Cadence:** daily 7:30pm IST, M–F only (no weekend).
**Schema:** 16 columns. See `jip-source-manifest.yaml` → `fo_bhavcopy_daily`.
**Backfill:** 10 years.
**Gotchas:**
- File-naming convention changed in **Feb 2024**. Pre-Feb-2024 use `fo{DDMMYYYY}bhav.csv.zip`. Backfill script must handle both.
- This is ONE table for futures + options (do not split). Filter by `instrument` column (FUTSTK / OPTSTK / FUTIDX / OPTIDX).
- Partition by year for query performance — same pattern as `de_equity_ohlcv_y{YEAR}`.

#### C. Participant-wise OI — `de_fo_participant_oi_daily`
**Why:** FII derivative positioning is the strongest sentiment signal Atlas can show. Long/short ratios drive market commentary.
**Source:** `https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{DDMMYYYY}.csv`
**Cadence:** daily 8pm IST.
**Backfill:** 5 years.

#### D. India VIX daily — `de_india_vix_daily`
**Why:** Foundational for fear/greed regime classification. Atlas commentary engine needs VIX history to calibrate.
**Source:** `https://www.nseindia.com/api/historical/vixhistory?from={DDMMYYYY}&to={DDMMYYYY}`
**Cadence:** daily 7:30pm IST.
**Backfill:** 10 years (VIX series goes back to 2008).

---

### PRIORITY 2 (unlocks insider/sentiment/macro layers)

#### E. Insider trades — `de_insider_trades`
**Source:** SEBI PIT disclosures via NSE — `https://www.nseindia.com/api/corporates-pit`
**Cadence:** daily.
**Backfill:** 3 years.

#### F. Bulk + block deals — `de_bulk_deals`, `de_block_deals`
**Source:** `https://nsearchives.nseindia.com/content/equities/bulk.csv` and `.../block.csv`
**Cadence:** daily.
**Backfill:** 3 years.

#### G. India G-Sec yield curve — `de_in_gsec_yields_daily`
**Why:** Yield curve shape drives Atlas's macro-regime layer. Without it, macro commentary is noise.
**Source:** CCIL — `https://www.ccilindia.com/Research/Statistics/Pages/MarketStats.aspx`
**Tenors:** 3M, 6M, 1Y, 2Y, 5Y, 10Y, 15Y, 30Y.
**Backfill:** 10 years.

#### H. INR FX rates — `de_fx_rates_daily`
**Source:** RBI reference rates — `https://www.rbi.org.in/Scripts/ReferenceRateArchive.aspx`
**Currencies:** USD, EUR, GBP, JPY, CNY, AED.
**Backfill:** 10 years.

---

### PRIORITY 3 (nice-to-have but lifts analytical depth significantly)

#### I. Shareholding pattern quarterly — `de_shareholding_pattern`
**Source:** BSE corporate filings (XBRL).
**Backfill:** 5 years.
**Cadence:** quarterly.

#### J. RBI policy events — `de_rbi_policy_rates`
**Source:** RBI press releases, hand-curated initially.
**Cadence:** event-driven.

#### K. Securities-in-ban — `de_fo_securities_in_ban`
**Source:** `https://nsearchives.nseindia.com/content/fo/fo_secban_{DDMMYYYY}.csv`
**Cadence:** daily.

---

## 4. Cross-cutting: routine observability

Every routine — old and new — must emit a row to `de_routine_runs` on each execution:

```
run_id           uuid
routine_id       text         -- matches id in jip-source-manifest.yaml
source_url       text
started_at       timestamptz
ended_at         timestamptz
duration_ms      int
rows_fetched     int
rows_inserted    int
rows_updated    int
status           text         -- success | partial | failed
error_message    text         -- nullable
```

Atlas exposes this as `/api/system/routines` and renders it on the `/forge/routines` page (V8-0). This replaces invisible cron with a single dashboard the user can watch.

---

## 5. Cron → systemd (recommended migration)

Cron is a black box. Recommended migration: each routine becomes a `systemd` oneshot unit + timer. Benefits:
- `systemctl status jip-fo-bhavcopy.service` shows last run, exit code, next run
- `journalctl -u jip-fo-bhavcopy` gives full structured logs
- Failed units stay in failed state until acked (no silent skips)
- Atlas can poll `systemctl list-timers` to populate `/forge/routines`

Naming convention: `jip-<routine_id>.service` + `jip-<routine_id>.timer`.

---

## 6. Acceptance criteria (how Atlas will verify)

After JIP ships each routine, Atlas runs:

```bash
python scripts/check-data-coverage.py --domain <domain_name>
```

Pass = all 6 health dimensions (coverage, freshness, completeness, continuity, integrity, provenance) score ≥80, weighted overall ≥85. Failing routines block the matching Atlas frontend module from shipping.

---

## 7. Build order suggestion

If JIP team wants a single recommended sequence:

1. `de_adjustment_factors_daily` (1 day work, derived from existing data, unblocks all charting)
2. `de_india_vix_daily` (small table, unblocks regime engine)
3. `de_fo_bhavcopy_daily` (largest scope, biggest unlock)
4. `de_fo_participant_oi_daily` (small table, big sentiment signal)
5. `de_in_gsec_yields_daily` (macro layer)
6. `de_fx_rates_daily`
7. Backfill `de_institutional_flows` (10y FII/DII)
8. `de_insider_trades` + `de_bulk_deals` + `de_block_deals`
9. `de_shareholding_pattern` + `de_rbi_policy_rates` + `de_fo_securities_in_ban`

Estimated effort if a single engineer focuses: 3–4 weeks for P1+P2; P3 stretch for week 5.

---

## 8. Questions to confirm before starting

1. Confirm JIP Data Core has TA-Lib + empyrical wired (Atlas audit could not see your repo). Send `pip freeze | grep -iE "talib|empyrical|pandas-ta"` output.
2. Confirm `de_equity_ohlcv` and `de_mf_nav_daily` (unpartitioned) are intentionally empty.
3. Confirm `de_macro_values` has US2Y / US10Y / DXY / MOVE / gold / silver / crude / copper. Send list of currently-tracked macro_ids.
4. Agree on `de_routine_runs` table schema + start emitting from existing routines.
5. Agree to systemd migration plan or stay on cron.
