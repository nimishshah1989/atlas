# Critical Schema Facts (spec v2 was WRONG — these are correct)

> Moved out of `CLAUDE.md` in chunk S4. The rulebook points here; this file
> is the source of truth for every query you write against the data_engine
> database. **ALWAYS verify column names against this table before writing
> queries.**

| What | WRONG (spec v2) | CORRECT (actual DB) |
|------|-----------------|---------------------|
| Stock primary key | `instrument_id INTEGER` | `id UUID` |
| Stock symbol | `symbol` | `current_symbol` |
| Market cap | column on de_instrument | separate `de_market_cap_history`, column `cap_category` |
| RS columns | `rs_percentile, rs_score` | `rs_1w, rs_1m, rs_3m, rs_6m, rs_12m, rs_composite` |
| RS entity ref | `instrument_id` | `entity_id` |
| RS benchmark | `benchmark` | `vs_benchmark` |
| MF primary key | `fund_code` | `mstar_id` |
| MF category | `category` | `category_name` |
| MF fund house | `fund_house` | `amc_name` |
| MF NAV date | `date` | `nav_date` |
| Breadth columns | `advances, declines` | `advance, decline` (singular) |
| Regime composite | `composite_score` | `confidence` |

If you add a new discrepancy here, also grep-check the rest of the codebase
for the old name — stale references are how spec drift creeps back in.
