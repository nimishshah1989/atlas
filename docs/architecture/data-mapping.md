# ATLAS — Data Mapping

*Last updated: 2026-04-17*

Complete mapping of every displayed data point across all ATLAS pages to its source table.column in the JIP data engine. Used by the API layer to build queries without ambiguity.

**Access pattern:** ATLAS never queries `de_*` tables directly. All reads go through the JIP Data Core `/internal/*` API (port 8000), abstracted by `backend/clients/jip_data_service.py` and `backend/clients/jip_equity_service.py`.

## Legend

- AVAILABLE — column exists, has data, directly usable as-is
- DERIVATION — data exists in one or more columns but requires computation (formula documented)
- EMPTY — table/column exists in the schema but contains 0–5 rows (pipeline gap, not an ATLAS problem)
- NOT YET COMPUTED — requires a new `atlas_*` table and a batch computation job

---

## 1. Market Regime Context (cross-page banner)

Appears on: pulse-breadth, pulse-sectors, pulse-sentiment, stock-detail

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Regime label (BULL/BEAR/CORRECTION/RECOVERY) | AVAILABLE | de_market_regime | regime | Latest row by date |
| Days in current regime | DERIVATION | de_market_regime | date, regime | `SELECT COUNT(*) FROM de_market_regime WHERE regime = :current_regime AND date >= (SELECT MIN(date) FROM de_market_regime WHERE regime != :current_regime ORDER BY date DESC LIMIT 1)` — count consecutive trailing rows with same regime |
| Regime confidence score | AVAILABLE | de_market_regime | confidence | Range 0–1; display as percentage |
| Breadth sub-score | AVAILABLE | de_market_regime | breadth_score | Used in regime narrative |
| Momentum sub-score | AVAILABLE | de_market_regime | momentum_score | Used in regime narrative |
| Volume sub-score | AVAILABLE | de_market_regime | volume_score | Used in regime narrative |
| Global sub-score | AVAILABLE | de_market_regime | global_score | Used in regime narrative |
| FII sub-score | AVAILABLE | de_market_regime | fii_score | Used in regime narrative |
| Indicator detail (JSONB) | AVAILABLE | de_market_regime | indicator_detail | Raw detail bag; parse per sub-indicator |
| Regime narrative text | DERIVATION | de_market_regime | regime, breadth_score, momentum_score, volume_score | Template: "Market in {regime} phase. Breadth at {breadth_score}%, Momentum {momentum_score}, Volume {volume_score}" — assembled in Python, not stored |

---

## 2. pulse-breadth.html — Market Breadth

### 2a. Signal Strip Cards (top 3 cards)

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| % stocks above 200 DMA (market-wide) | AVAILABLE | de_breadth_daily | pct_above_200dma | Latest date; multiply by 100 for display |
| % stocks above 50 DMA (market-wide) | AVAILABLE | de_breadth_daily | pct_above_50dma | Latest date |
| % stocks above 20 EMA (market-wide) | DERIVATION | de_equity_technical_daily | above_20ema | `SELECT AVG(above_20ema::int) * 100 FROM de_equity_technical_daily WHERE date = :latest_date` — de_breadth_daily lacks this column; compute from constituent flags |

### 2b. Dual-Axis Time-Series Chart

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Breadth % over time (left axis) | AVAILABLE | de_breadth_daily | pct_above_200dma | Daily series; last 252 trading days default |
| Market level over time (right axis) | AVAILABLE | de_index_price_daily | close_adj | index_code = 'NIFTY 50' |
| Chart date range | AVAILABLE | de_breadth_daily | date | Use as x-axis |

### 2c. Interpretation Rail

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Breadth zone (e.g. 28%) | AVAILABLE | de_breadth_daily | pct_above_200dma | Current value for zone card |
| Breadth reading label (e.g. CORRECTION) | DERIVATION | de_breadth_daily | pct_above_200dma | Rules: >=70% = STRONG BULL; 50–70% = BULL; 30–50% = NEUTRAL; 15–30% = CORRECTION; <15% = BEAR |
| Interpretation narrative | DERIVATION | de_breadth_daily, de_market_regime | pct_above_200dma, pct_above_50dma, advance, decline, regime | Template assembled in Python using current breadth values and regime label |

### 2d. Advance / Decline

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Advance count | AVAILABLE | de_breadth_daily | advance | Singular column (not "advances") |
| Decline count | AVAILABLE | de_breadth_daily | decline | Singular column |
| Unchanged count | AVAILABLE | de_breadth_daily | unchanged | |
| Total stocks | AVAILABLE | de_breadth_daily | total_stocks | |
| A/D ratio | AVAILABLE | de_breadth_daily | ad_ratio | Pre-computed; advance/decline |

### 2e. 52-Week Highs / Lows

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| New 52W highs count | AVAILABLE | de_breadth_daily | new_52w_highs | |
| New 52W lows count | AVAILABLE | de_breadth_daily | new_52w_lows | |

### 2f. McClellan Indicators

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| McClellan Oscillator | AVAILABLE | de_breadth_daily | mcclellan_oscillator | |
| McClellan Summation Index | AVAILABLE | de_breadth_daily | mcclellan_summation | |

### 2g. Signal History Table

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Date | AVAILABLE | de_breadth_daily | date | |
| Event label | DERIVATION | de_market_regime | regime | Regime transition = event; detect via LAG(regime) != regime |
| Regime at event | AVAILABLE | de_market_regime | regime | |
| Days in that regime | DERIVATION | de_market_regime | date, regime | Consecutive-same-regime count (see §1) |
| Breadth% at event date | AVAILABLE | de_breadth_daily | pct_above_200dma | JOIN on date |
| Advance/Decline at event date | AVAILABLE | de_breadth_daily | advance, decline | JOIN on date |

### 2h. Sector Breadth Matrix (10 sectors × 5 columns)

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Sector name | AVAILABLE | de_sector_breadth_daily | sector | 31 distinct sectors; filter to top 10 by stocks_total |
| % above 50 DMA | AVAILABLE | de_sector_breadth_daily | pct_above_50dma | Latest date |
| % above 200 DMA | AVAILABLE | de_sector_breadth_daily | pct_above_200dma | Latest date |
| % above 20 EMA | AVAILABLE | de_sector_breadth_daily | pct_above_20ema | Latest date |
| RSI Overbought % | DERIVATION | de_sector_breadth_daily | stocks_rsi_overbought, stocks_total | `stocks_rsi_overbought / stocks_total * 100` |
| MACD Bullish % | DERIVATION | de_sector_breadth_daily | stocks_macd_bullish, stocks_total | `stocks_macd_bullish / stocks_total * 100` |
| Breadth regime label | AVAILABLE | de_sector_breadth_daily | breadth_regime | Per-sector enum |

---

## 3. pulse-sectors.html — Sector Compass (RRG)

### 3a. RRG Scatter Plot

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Sector name (label on plot) | AVAILABLE | de_rs_scores | entity_id | WHERE entity_type = 'sector' |
| RS Score (x-axis) | AVAILABLE | de_rs_scores | rs_composite | entity_type = 'sector', latest date. Normalize to 100-centered scale: `(rs_composite - mean) / stddev * 10 + 100` |
| RS Momentum (y-axis) | DERIVATION | de_rs_scores | rs_composite | `rs_composite(today) - rs_composite(28_days_ago)` per sector; JOIN on entity_id and lag by 28 calendar days |
| Quadrant assignment | DERIVATION | derived rs_score, rs_momentum | — | LEADING: rs>100 AND mom>0; WEAKENING: rs>100 AND mom<0; IMPROVING: rs<100 AND mom>0; LAGGING: rs<100 AND mom<0 |
| RS tail (trailing 4 weeks) | DERIVATION | de_rs_scores | date, rs_composite | `SELECT date, rs_composite FROM de_rs_scores WHERE entity_type='sector' AND entity_id=:sector AND date >= :today - 28 ORDER BY date` — 4 weekly points for RRG tail path |
| Period selector (1M/3M/6M/12M) | DERIVATION | de_rs_scores | rs_composite at period offsets | 1M = 21 trading days back; 3M = 63; 6M = 126; 12M = 252 |

**Critical gap:** `rs_1m` and `rs_3m` are NULL for entity_type='sector' in de_rs_scores. Only `rs_composite` is available. All period-based RS for sectors must be derived from rolling rs_composite snapshots, not from the dedicated period columns.

### 3b. Sector Comparison Table

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Sector name | AVAILABLE | de_rs_scores | entity_id | entity_type = 'sector' |
| RS score | AVAILABLE | de_rs_scores | rs_composite | Latest date, entity_type = 'sector' |
| RS momentum | DERIVATION | de_rs_scores | rs_composite | 28-day delta (see §3a) |
| Breadth% | AVAILABLE | de_sector_breadth_daily | pct_above_50dma | JOIN on sector name, latest date |
| 4-factor conviction | NOT YET COMPUTED | — | — | See §8 derivations; requires atlas_* store |
| Gold RS | DERIVATION | de_rs_scores + de_global_price_daily | rs_composite (sector), close (GLD) | Sector return vs GLD return over same period; ratio > 1 = outperforms gold |
| Action | NOT YET COMPUTED | — | — | BUY/WATCH/REDUCE derived from conviction + quadrant |

### 3c. 4-Factor Convergence Matrix

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| RS factor aligned | AVAILABLE | de_rs_scores | rs_composite | rs_composite > 100 threshold |
| Breadth factor aligned | AVAILABLE | de_sector_breadth_daily | pct_above_50dma | >50% threshold |
| Momentum factor aligned | DERIVATION | de_rs_scores | rs_composite | 28-day delta > 0 |
| Volume factor aligned | DERIVATION | de_equity_technical_daily | obv | Sector-aggregated OBV trend; positive slope = aligned |
| All-4 convergence flag | DERIVATION | all above | — | Boolean AND of 4 factor checks |

### 3d. Rotation Narrative

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Rotation narrative text | DERIVATION | de_rs_scores, de_sector_breadth_daily | rs_composite, breadth_regime | Template: strongest/weakest sectors by RS momentum, assembled in Python |

---

## 4. pulse-sentiment.html — Composite Sentiment

### 4a. Semicircle Gauge

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Composite sentiment score (0–100) | DERIVATION | multiple | see §4b | Weighted average: Price Breadth 40% + Options/PCR 20% + Institutional Flow 20% + Fundamental Revisions 20%. PCR and flow components are EMPTY (see gaps) |
| Zone label (Extreme Fear / Fear / Neutral / Greed / Extreme Greed) | DERIVATION | derived score | — | <20 = Extreme Fear; 20–40 = Fear; 40–60 = Neutral; 60–80 = Greed; >80 = Extreme Greed |

### 4b. Signal Strip Cards

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Price Breadth score | DERIVATION | de_breadth_daily | pct_above_200dma, pct_above_50dma, ad_ratio, mcclellan_oscillator, new_52w_highs, new_52w_lows | Normalize each sub-metric to 0–100 and average: `(pct_above_200dma + pct_above_50dma + ad_ratio_normalized + mcclellan_normalized + highs_lows_ratio_normalized) / 5 * 100` |
| Options/PCR score | EMPTY | de_fo_summary | pcr_oi, pcr_volume, fii_index_long, fii_index_short | Table has 0 rows — PIPELINE GAP. Display placeholder "N/A — data unavailable" until pipeline is repaired |
| Institutional Flow score | EMPTY | de_flow_daily / de_institutional_flows | net_flow (category = 'FII') | Tables have 5 rows total — effectively empty. Same treatment as PCR |
| Fundamental Revisions score | DERIVATION | de_equity_fundamentals | pe_ratio, roe_pct, revenue_growth_yoy_pct, profit_growth_yoy_pct | Aggregate over Nifty 500: median PE vs 52-week median PE; revenue/profit growth positive = bullish. Normalize to 0–100 |

### 4c. Sparkline Mini-Charts (per indicator)

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Price Breadth 30-day sparkline | AVAILABLE | de_breadth_daily | pct_above_200dma, date | Last 30 trading days |
| McClellan Oscillator sparkline | AVAILABLE | de_breadth_daily | mcclellan_oscillator, date | Last 30 trading days |
| PCR sparkline | EMPTY | de_fo_summary | pcr_oi, date | 0 rows — placeholder |
| FII flow sparkline | EMPTY | de_flow_daily | net_flow, date | 5 rows — placeholder |

### 4d. Sector Actionables Table

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Sector name | AVAILABLE | de_sector_breadth_daily | sector | |
| Breadth score | AVAILABLE | de_sector_breadth_daily | pct_above_50dma | |
| FII flow | EMPTY | de_flow_daily | net_flow | GROUP BY sector — data empty |
| Action | NOT YET COMPUTED | — | — | Derived from conviction engine |
| Gold RS | DERIVATION | de_global_price_daily + de_rs_scores | close (GLD/GC=F), rs_composite (sector) | See §3b Gold RS formula |

### 4e. Historical Extremes Table

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Prior fear episode dates | DERIVATION | de_market_regime | date, regime | WHERE regime IN ('BEAR', 'CORRECTION') — group consecutive matching rows into episodes |
| Breadth at episode | AVAILABLE | de_breadth_daily | pct_above_200dma | JOIN on date |
| Regime at episode | AVAILABLE | de_market_regime | regime | |
| Days in episode | DERIVATION | de_market_regime | date, regime | Consecutive-same-regime count |

---

## 5. stock-detail — Individual Stock Deep Dive

### 5a. Header

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Company name | AVAILABLE | de_instrument | company_name | JOIN on id = instrument_id |
| Symbol | AVAILABLE | de_instrument | current_symbol | Not "symbol" — see critical-schema-facts.md |
| Sector | AVAILABLE | de_instrument | sector | |
| Live price (bid/ask/LTP) | AVAILABLE | atlas_tv_cache | — | Sourced from TradingView MCP sidecar; not from de_* tables |
| Day change % | AVAILABLE | atlas_tv_cache | — | TradingView sidecar |

### 5b. Regime Banner

Same as §1. Regime label, days in regime from de_market_regime.

### 5c. Signal Strip — 4-Factor RS

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Returns RS | AVAILABLE | de_rs_scores | rs_composite | entity_type='equity', entity_id = instrument UUID, vs_benchmark = 'NIFTY 500' |
| Momentum RS (price momentum component) | AVAILABLE | de_equity_technical_daily | roc_21, roc_63 | 1-month and 3-month rate-of-change |
| Sector RS | AVAILABLE | de_rs_scores | rs_composite | entity_type='sector', entity_id = stock's sector name |
| Volume RS | DERIVATION | de_equity_technical_daily | obv, cmf_20, mfi_14 | Normalize each 0–100; average → volume RS sub-score |
| Conviction level (HIGH+/HIGH/MEDIUM/LOW/AVOID) | NOT YET COMPUTED | — | — | See §8; requires all 4 factors above + convergence logic |

### 5d. Combined Output Chip

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Conviction level | NOT YET COMPUTED | — | — | HIGH+/HIGH/MEDIUM/LOW/AVOID |
| Gold RS signal | DERIVATION | de_global_price_daily + de_rs_scores | close (GLD), rs_composite (equity) | AMPLIFIES_BULL: stock RS > gold RS; NEUTRAL: within ±5%; FRAGILE: underperforms slightly; AMPLIFIES_BEAR: significantly underperforms gold |
| Action signal | NOT YET COMPUTED | — | — | ACCUMULATE/BUY/WATCH/REDUCE/EXIT based on conviction + regime |
| Urgency | NOT YET COMPUTED | — | — | IMMEDIATE/DEVELOPING/PATIENT based on days since signal triggered |

### 5e. TradingView Chart

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Candlestick OHLCV chart | AVAILABLE | atlas_tv_cache / TradingView widget | — | Embedded TradingView widget (client-side) or TV MCP sidecar. No de_* query needed |

### 5f. Interpretation Rail

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| 52W high | AVAILABLE | de_equity_fundamentals | high_52w | Latest as_of_date for instrument |
| 52W low | AVAILABLE | de_equity_fundamentals | low_52w | Latest as_of_date for instrument |
| Support 1 / Support 2 | AVAILABLE | de_goldilocks_market_view | nifty_support_1, nifty_support_2 | Market-wide; per-stock levels not in any de_* table. Per-stock S/R requires atlas computation or TV sidecar |
| Resistance 1 / Resistance 2 | AVAILABLE | de_goldilocks_market_view | nifty_resistance_1, nifty_resistance_2 | Same caveat as support |
| Interpretation narrative | DERIVATION | de_equity_technical_daily, de_rs_scores | above_50dma, above_200dma, rsi_14, macd_bullish, rs_composite | Template assembled per §15 auto-interpretation spec |

### 5g. Fundamentals Tab

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| PE ratio | AVAILABLE | de_equity_fundamentals | pe_ratio | Latest as_of_date |
| PB ratio | AVAILABLE | de_equity_fundamentals | pb_ratio | Latest as_of_date |
| EV/EBITDA | AVAILABLE | de_equity_fundamentals | ev_ebitda | |
| ROE | AVAILABLE | de_equity_fundamentals | roe_pct | |
| ROCE | AVAILABLE | de_equity_fundamentals | roce_pct | |
| Debt-to-Equity | AVAILABLE | de_equity_fundamentals | debt_to_equity | |
| Interest Coverage | AVAILABLE | de_equity_fundamentals | interest_coverage | |
| Net Margin | AVAILABLE | de_equity_fundamentals | net_margin_pct | |
| Operating Margin | AVAILABLE | de_equity_fundamentals | operating_margin_pct | |
| Promoter holding % | AVAILABLE | de_equity_fundamentals | promoter_holding_pct | |
| FII holding % | AVAILABLE | de_equity_fundamentals | fii_holding_pct | |
| DII holding % | AVAILABLE | de_equity_fundamentals | dii_holding_pct | |
| Pledged % | AVAILABLE | de_equity_fundamentals | pledged_pct | |
| Market cap (Cr) | AVAILABLE | de_equity_fundamentals | market_cap_cr | |
| EPS TTM | AVAILABLE | de_equity_fundamentals | eps_ttm | |
| Book value | AVAILABLE | de_equity_fundamentals | book_value | |
| Face value | AVAILABLE | de_equity_fundamentals | face_value | |
| Dividend yield | AVAILABLE | de_equity_fundamentals | dividend_yield_pct | |
| Dividend per share | AVAILABLE | de_equity_fundamentals | dividend_per_share | |
| PEG ratio | AVAILABLE | de_equity_fundamentals | peg_ratio | |
| Revenue growth YoY% | AVAILABLE | de_equity_fundamentals | revenue_growth_yoy_pct | |
| Profit growth YoY% | AVAILABLE | de_equity_fundamentals | profit_growth_yoy_pct | |
| Piotroski F-Score | DERIVATION | de_equity_fundamentals + de_equity_fundamentals_history | see formula | 9 binary checks (see §8). Score 0–9; display as integer |

### 5h. 8-Quarter Mini-Charts

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Revenue (8 quarters) | AVAILABLE | de_equity_fundamentals_history | revenue_cr, fiscal_period_end | WHERE period_type = 'quarterly' AND instrument_id = :id ORDER BY fiscal_period_end DESC LIMIT 8 |
| Operating Profit (8 quarters) | AVAILABLE | de_equity_fundamentals_history | operating_profit_cr, fiscal_period_end | Same filter |
| OPM% (8 quarters) | AVAILABLE | de_equity_fundamentals_history | opm_pct, fiscal_period_end | Same filter |
| Net Profit (8 quarters) | AVAILABLE | de_equity_fundamentals_history | net_profit_cr, fiscal_period_end | Same filter |
| EPS (8 quarters) | AVAILABLE | de_equity_fundamentals_history | eps, fiscal_period_end | Same filter |
| Interest expense (8 quarters) | AVAILABLE | de_equity_fundamentals_history | interest_cr, fiscal_period_end | Same filter |
| Depreciation (8 quarters) | AVAILABLE | de_equity_fundamentals_history | depreciation_cr, fiscal_period_end | Same filter |
| CFO (8 quarters) | AVAILABLE | de_equity_fundamentals_history | cfo_cr, fiscal_period_end | Same filter |

### 5i. Ownership History Chart

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Promoter holding trend (quarterly) | AVAILABLE | de_equity_fundamentals | promoter_holding_pct, as_of_date | Historical rows per instrument; JIP stores one row per quarter |
| FII holding trend (quarterly) | AVAILABLE | de_equity_fundamentals | fii_holding_pct, as_of_date | |
| DII holding trend (quarterly) | AVAILABLE | de_equity_fundamentals | dii_holding_pct, as_of_date | |

**VERIFIED:** de_equity_fundamentals has exactly 2,272 rows and 2,272 unique instruments — it is definitively **1 row per stock, point-in-time only**. There is no quarterly ownership history in this table. Promoter/FII/DII holding trends over time are **NOT available** in any de_* table — de_equity_fundamentals_history does not have promoter/FII columns. The ownership history chart on stock-detail must either: (a) be dropped from V7, (b) sourced via screener.in API for history (new pipeline), or (c) shown as point-in-time only (current quarter values).

---

## 6. explorer.html — Stock Screener

### 6a. Universe Filters

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Nifty 50 membership | AVAILABLE | de_instrument | nifty_50 | Boolean |
| Nifty 200 membership | AVAILABLE | de_instrument | nifty_200 | Boolean |
| Nifty 500 membership | AVAILABLE | de_instrument | nifty_500 | Boolean |
| Sector filter values | AVAILABLE | de_instrument | sector | DISTINCT sector values |
| Conviction filter values | NOT YET COMPUTED | — | — | Requires conviction computation (see §8) |

### 6b. Screener Table Columns

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Symbol | AVAILABLE | de_instrument | current_symbol | |
| Company name | AVAILABLE | de_instrument | company_name | |
| Sector | AVAILABLE | de_instrument | sector | |
| RS Composite | AVAILABLE | de_rs_scores | rs_composite | entity_type='equity', latest date, vs_benchmark='NIFTY 500' |
| RSI 14 | AVAILABLE | de_equity_technical_daily | rsi_14 | Latest date per instrument |
| Above 50 DMA | AVAILABLE | de_equity_technical_daily | above_50dma | Boolean; latest date |
| Above 200 DMA | AVAILABLE | de_equity_technical_daily | above_200dma | Boolean; latest date |
| MACD Bullish | AVAILABLE | de_equity_technical_daily | macd_bullish | Boolean; latest date |
| Market Cap (Cr) | AVAILABLE | de_equity_fundamentals | market_cap_cr | Latest as_of_date |
| PE | AVAILABLE | de_equity_fundamentals | pe_ratio | Latest as_of_date |
| Conviction | NOT YET COMPUTED | — | — | HIGH+/HIGH/MEDIUM/LOW/AVOID; requires §8 computation |
| Action | NOT YET COMPUTED | — | — | BUY/ACCUMULATE/WATCH/REDUCE/EXIT |
| Urgency | NOT YET COMPUTED | — | — | IMMEDIATE/DEVELOPING/PATIENT |

**Performance note:** de_equity_technical_daily has 3.69M rows. The screener query MUST use WHERE date = :latest_date and JOIN on instrument_id with an index. Never `SELECT *` or load full history into Python.

---

## 7. mf-detail.html — Fund Deep Dive

### 7a. Fund Header

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Fund name | AVAILABLE | de_mf_derived_daily (join mf master) | — | MF master table not listed in audit; confirm table name via JIP `/internal/mf/` API |
| Category | AVAILABLE | MF master | category_name | Column is category_name not "category" per critical-schema-facts.md |
| Fund house | AVAILABLE | MF master | amc_name | Not "fund_house" per critical-schema-facts.md |
| AUM | AVAILABLE | MF master or derived | — | Check JIP MF master table; not visible in audit |
| NAV (current) | AVAILABLE | de_mf_derived_daily | nav_date + join to NAV table | Primary key is mstar_id; join to NAV series table |
| 1Y return | DERIVATION | NAV series | nav values | `(nav_today - nav_365d_ago) / nav_365d_ago * 100` |
| 3Y CAGR | DERIVATION | NAV series | nav values | `(nav_today / nav_3y_ago)^(365.25/1095) - 1` |
| 5Y CAGR | DERIVATION | NAV series | nav values | `(nav_today / nav_5y_ago)^(365.25/1825) - 1` |

### 7b. RS Metrics

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| RS vs benchmark | AVAILABLE | de_mf_derived_daily | derived_rs_composite | vs NIFTY 50 |
| RS vs NAV benchmark | AVAILABLE | de_mf_derived_daily | nav_rs_composite | vs category peers |
| Manager alpha | AVAILABLE | de_mf_derived_daily | manager_alpha | Pre-computed |

### 7c. Risk Metrics

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Sharpe 1Y | AVAILABLE | de_mf_derived_daily | sharpe_1y | |
| Sharpe 3Y | AVAILABLE | de_mf_derived_daily | sharpe_3y | |
| Sharpe 5Y | AVAILABLE | de_mf_derived_daily | sharpe_5y | |
| Sortino 1Y | AVAILABLE | de_mf_derived_daily | sortino_1y | |
| Sortino 3Y | AVAILABLE | de_mf_derived_daily | sortino_3y | |
| Sortino 5Y | AVAILABLE | de_mf_derived_daily | sortino_5y | |
| Max Drawdown 1Y | AVAILABLE | de_mf_derived_daily | max_drawdown_1y | |
| Max Drawdown 3Y | AVAILABLE | de_mf_derived_daily | max_drawdown_3y | |
| Max Drawdown 5Y | AVAILABLE | de_mf_derived_daily | max_drawdown_5y | |
| Volatility 1Y | AVAILABLE | de_mf_derived_daily | volatility_1y | |
| Volatility 3Y | AVAILABLE | de_mf_derived_daily | volatility_3y | |
| Volatility 5Y | AVAILABLE | de_mf_derived_daily | volatility_5y | |
| Beta vs Nifty | AVAILABLE | de_mf_derived_daily | beta_vs_nifty | |
| Information Ratio | AVAILABLE | de_mf_derived_daily | information_ratio | |
| Treynor Ratio | AVAILABLE | de_mf_derived_daily | treynor_ratio | |
| Std Dev 1Y | AVAILABLE | de_mf_derived_daily | stddev_1y | |
| Std Dev 3Y | AVAILABLE | de_mf_derived_daily | stddev_3y | |
| Std Dev 5Y | AVAILABLE | de_mf_derived_daily | stddev_5y | |
| Coverage % | AVAILABLE | de_mf_derived_daily | coverage_pct | % of AUM with underlying stock data |

### 7d. Sector Exposure Chart

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Sector name | AVAILABLE | de_mf_sector_exposure | sector | WHERE mstar_id = :fund_id AND as_of_date = :latest |
| Sector weight% | AVAILABLE | de_mf_sector_exposure | weight_pct | |
| Stock count in sector | AVAILABLE | de_mf_sector_exposure | stock_count | |

### 7e. Holdings Table

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Top stock holdings | AVAILABLE | MF holdings table | — | Not shown in audit; available via JIP `/internal/mf/holdings/` API |
| Weight per stock | AVAILABLE | MF holdings table | — | Same source |

### 7f. Portfolio-Weighted Fundamentals

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Weighted PE | DERIVATION | MF holdings + de_equity_fundamentals | weight_pct, pe_ratio | `SUM(holding_weight * pe_ratio) / SUM(holding_weight)` — weighted average over holdings |
| Weighted PB | DERIVATION | MF holdings + de_equity_fundamentals | weight_pct, pb_ratio | Same pattern |
| Weighted ROE | DERIVATION | MF holdings + de_equity_fundamentals | weight_pct, roe_pct | Same pattern |
| Weighted Debt/Equity | DERIVATION | MF holdings + de_equity_fundamentals | weight_pct, debt_to_equity | Same pattern |
| Weighted EV/EBITDA | DERIVATION | MF holdings + de_equity_fundamentals | weight_pct, ev_ebitda | Same pattern |

### 7g. Gold RS

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Fund performance vs Gold | DERIVATION | NAV series + de_global_price_daily | nav values, close (GLD or GC=F) | Fund return over period / GLD return over same period. Signal: >1.1 = AMPLIFIES_BULL; 0.9–1.1 = NEUTRAL; 0.7–0.9 = FRAGILE; <0.7 = AMPLIFIES_BEAR |

---

## 8. pulse-global.html — Global Markets (planned)

### 8a. Global Index Dashboard

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| S&P 500 price + change | AVAILABLE | de_global_price_daily | close, date | ticker = '^GSPC' |
| Nasdaq price + change | AVAILABLE | de_global_price_daily | close, date | ticker = '^IXIC' |
| Nikkei price + change | AVAILABLE | de_global_price_daily | close, date | ticker = '^N225' |
| FTSE 100 price + change | AVAILABLE | de_global_price_daily | close, date | ticker = '^FTSE' |
| Hang Seng price + change | AVAILABLE | de_global_price_daily | close, date | ticker = '^HSI' |
| DAX price + change | AVAILABLE | de_global_price_daily | close, date | ticker = '^DAX' |
| CAC 40 price + change | AVAILABLE | de_global_price_daily | close, date | ticker = '^CAC' |
| ASX price + change | AVAILABLE | de_global_price_daily | close, date | ticker = '^AXJO' |
| Dow Jones price + change | AVAILABLE | de_global_price_daily | close, date | ticker = '^DJI' |

### 8b. Commodities

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Gold spot price | AVAILABLE | de_global_price_daily | close | ticker = 'GC=F' (futures) or 'GLD' (ETF proxy) |
| Crude oil price | AVAILABLE | de_global_price_daily | close | ticker = 'CL=F' |
| Brent crude | AVAILABLE | de_global_price_daily | close | ticker = 'BZ=F' |
| Natural gas | AVAILABLE | de_global_price_daily | close | ticker = 'NG=F' |
| Silver | AVAILABLE | de_global_price_daily | close | ticker = 'SI=F' |
| Copper | AVAILABLE | de_global_price_daily | close | ticker = 'HG=F' |
| Platinum | AVAILABLE | de_global_price_daily | close | ticker = 'PL=F' |

### 8c. Currencies / DXY

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| US Dollar Index | AVAILABLE | de_global_price_daily | close | ticker = 'DX-Y.NYB' |
| AUDUSD | AVAILABLE | de_global_price_daily | close | ticker = 'AUDUSD=X' |
| EURUSD | AVAILABLE | de_global_price_daily | close | ticker = 'EURUSD=X' |
| GBPUSD | AVAILABLE | de_global_price_daily | close | ticker = 'GBPUSD=X' |

### 8d. Bond / ETF Risk Proxies

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| TLT (20Y Treasury) | AVAILABLE | de_global_price_daily | close | ticker = 'TLT' |
| HYG (High Yield bonds) | AVAILABLE | de_global_price_daily | close | ticker = 'HYG' |
| LQD (Investment Grade) | AVAILABLE | de_global_price_daily | close | ticker = 'LQD' |
| AGG (US Aggregate) | AVAILABLE | de_global_price_daily | close | ticker = 'AGG' |
| EEM (Emerging Markets) | AVAILABLE | de_global_price_daily | close | ticker = 'EEM' |

### 8e. Crypto

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Bitcoin | AVAILABLE | de_global_price_daily | close | ticker = 'BTC-USD' |
| Ethereum | AVAILABLE | de_global_price_daily | close | ticker = 'ETH-USD' |

### 8f. Global Technicals

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| RSI 14 for any global ticker | AVAILABLE | de_global_technical_daily | rsi_14 | JOIN on ticker + date |
| MACD for any global ticker | AVAILABLE | de_global_technical_daily | macd_line, macd_signal, macd_histogram | |
| 200 DMA for any global ticker | AVAILABLE | de_global_technical_daily | sma_200 | |
| ADX for any global ticker | AVAILABLE | de_global_technical_daily | adx_14 | |

### 8g. Intermarket Ratios

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Bank Nifty / Nifty ratio | AVAILABLE | de_intermarket_ratios | value | ratio_name = 'BANKNIFTY_NIFTY' (20 rows — very limited history) |
| Smallcap / Nifty ratio | AVAILABLE | de_intermarket_ratios | value | ratio_name = 'SMALLCAP_NIFTY' |
| Metal / Nifty ratio | AVAILABLE | de_intermarket_ratios | value | ratio_name = 'METAL_NIFTY' |
| IT / Nifty ratio | AVAILABLE | de_intermarket_ratios | value | ratio_name = 'IT_NIFTY' |
| Other sector ratios | EMPTY | de_intermarket_ratios | — | Only 4 ratios available. Missing auto/pharma/realty/energy/fmcg/infra. Must derive from de_rs_scores sector data as workaround |

### 8h. Goldilocks Market View

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Nifty close (report date) | AVAILABLE | de_goldilocks_market_view | nifty_close, report_date | |
| Nifty support levels | AVAILABLE | de_goldilocks_market_view | nifty_support_1, nifty_support_2 | |
| Nifty resistance levels | AVAILABLE | de_goldilocks_market_view | nifty_resistance_1, nifty_resistance_2 | |
| Bank Nifty close | AVAILABLE | de_goldilocks_market_view | bank_nifty_close | |
| Bank Nifty support/resistance | AVAILABLE | de_goldilocks_market_view | bank_nifty_support_1/2, bank_nifty_resistance_1/2 | |
| Trend direction | AVAILABLE | de_goldilocks_market_view | trend_direction | |
| Trend strength (1-10) | AVAILABLE | de_goldilocks_market_view | trend_strength | |
| Headline | AVAILABLE | de_goldilocks_market_view | headline | |
| Overall view narrative | AVAILABLE | de_goldilocks_market_view | overall_view | |
| Global impact text | AVAILABLE | de_goldilocks_market_view | global_impact | |

### 8i. Goldilocks Stock Ideas

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Symbol | AVAILABLE | de_goldilocks_stock_ideas | symbol | |
| Company name | AVAILABLE | de_goldilocks_stock_ideas | company_name | |
| Idea type | AVAILABLE | de_goldilocks_stock_ideas | idea_type | |
| Entry price / zone | AVAILABLE | de_goldilocks_stock_ideas | entry_price, entry_zone_low, entry_zone_high | |
| Targets | AVAILABLE | de_goldilocks_stock_ideas | target_1, target_2, lt_target | |
| Stop loss | AVAILABLE | de_goldilocks_stock_ideas | stop_loss | |
| Timeframe | AVAILABLE | de_goldilocks_stock_ideas | timeframe | |
| Rationale | AVAILABLE | de_goldilocks_stock_ideas | rationale | |
| Status | AVAILABLE | de_goldilocks_stock_ideas | status, status_updated_at | |

### 8j. Goldilocks Sector View

| Data Point | Status | Table | Column(s) | Notes |
|---|---|---|---|---|
| Sector | AVAILABLE | de_goldilocks_sector_view | sector | |
| Trend | AVAILABLE | de_goldilocks_sector_view | trend | |
| Outlook | AVAILABLE | de_goldilocks_sector_view | outlook | |
| Rank | AVAILABLE | de_goldilocks_sector_view | rank | |
| Top picks | AVAILABLE | de_goldilocks_sector_view | top_picks | JSONB |

---

## 9. Derived Computations — Full Formulas

These computations do not exist in any `de_*` table and must be produced either as query-time derivations (fast, stateless) or stored in an `atlas_*` table (required when computation is expensive or used across pages).

### 9.1 Gold RS Signal

**Source tables:** `de_global_price_daily` (ticker='GLD' or 'GC=F') + `de_rs_scores` (for sectors) or NAV series (for MFs) or `de_equity_technical_daily` (for stocks)

**Formula (equity):**
```
period_return_stock = (close_today - close_N_days_ago) / close_N_days_ago
period_return_gold  = (gld_close_today - gld_close_N_days_ago) / gld_close_N_days_ago
gold_rs_ratio       = (1 + period_return_stock) / (1 + period_return_gold)

AMPLIFIES_BULL  if gold_rs_ratio > 1.05
NEUTRAL         if 0.95 <= gold_rs_ratio <= 1.05
FRAGILE         if 0.85 <= gold_rs_ratio < 0.95
AMPLIFIES_BEAR  if gold_rs_ratio < 0.85
```
Periods: 1M (21 trading days), 3M (63), 6M (126), 12M (252). Default display: 3M.

### 9.2 Piotroski F-Score (9 binary checks)

**Source tables:** `de_equity_fundamentals` + `de_equity_fundamentals_history`

Each check returns 1 (pass) or 0 (fail). Score = SUM of 9 checks.

```
Profitability (4 checks):
  F1: net_profit_cr > 0                                      (current year)
  F2: cfo_cr > 0                                             (current year)
  F3: roe_pct(current) > roe_pct(prior year)                 (improving)
  F4: cfo_cr > net_profit_cr                                 (quality earnings — accruals)

Leverage/Liquidity (3 checks):
  F5: debt_to_equity(current) < debt_to_equity(prior year)   (leverage falling)
  F6: current_ratio(current) > current_ratio(prior year)     (liquidity improving)
  F7: no new equity dilution (equity_capital_cr not rising)

Efficiency (2 checks):
  F8: opm_pct(current) > opm_pct(prior year)                 (margin expansion)
  F9: revenue_cr growth > total_assets_cr growth             (asset turnover improving)
```

All "prior year" values come from `de_equity_fundamentals_history` WHERE period_type = 'annual' ORDER BY fiscal_period_end DESC LIMIT 2.

Interpretation: 0–2 = WEAK; 3–5 = NEUTRAL; 6–7 = GOOD; 8–9 = STRONG.

### 9.3 4-Factor Conviction Score

**Source tables:** `de_rs_scores`, `de_equity_technical_daily`, `de_sector_breadth_daily`

**Four pillars:**

```
Pillar 1 — Returns RS:
  score_1 = 1 if rs_composite > 100 else 0
  (vs_benchmark = 'NIFTY 500')

Pillar 2 — Price Momentum RS:
  roc_score = normalize(roc_21) to 0-1 using sector peer distribution
  score_2    = 1 if roc_score > 0.6 else 0

Pillar 3 — Sector RS:
  sector_rs = rs_composite for entity_type='sector', entity_id = stock's sector
  score_3   = 1 if sector_rs > 100 else 0
  (sector must be in LEADING or IMPROVING quadrant)

Pillar 4 — Volume RS:
  obv_trend = linreg_slope of OBV over last 20 days (available as linreg_slope_20 in de_equity_technical_daily, computed on price not OBV — use cmf_20 > 0 as proxy)
  score_4   = 1 if cmf_20 > 0 AND mfi_14 > 50 else 0

Conviction = score_1 + score_2 + score_3 + score_4

HIGH+   if conviction == 4 (all factors aligned)
HIGH    if conviction == 3
MEDIUM  if conviction == 2
LOW     if conviction == 1
AVOID   if conviction == 0
```

### 9.4 Action Signal

**Inputs:** Conviction level + regime + rs_composite trend direction

```
if conviction in (HIGH+, HIGH) AND regime in (BULL, RECOVERY) → BUY
if conviction in (HIGH+, HIGH) AND regime in (CORRECTION)     → ACCUMULATE
if conviction == MEDIUM                                        → WATCH
if conviction == LOW AND rs_composite falling                  → REDUCE
if conviction == AVOID OR rs_composite < 80                   → EXIT
```

### 9.5 Urgency Signal

**Input:** Days since conviction level was first achieved (requires atlas_decisions table to track)

```
IMMEDIATE   if conviction changed upward within last 5 trading days
DEVELOPING  if 6–20 trading days
PATIENT     if > 20 trading days
```

Without atlas_decisions data, default all signals to PATIENT.

### 9.6 Sector RS Momentum (for RRG y-axis)

```
momentum = rs_composite(date=today) - rs_composite(date=today - 28 calendar days)

SELECT
  a.entity_id,
  a.rs_composite - b.rs_composite AS rs_momentum
FROM de_rs_scores a
JOIN de_rs_scores b
  ON a.entity_id = b.entity_id
  AND a.entity_type = b.entity_type
  AND a.vs_benchmark = b.vs_benchmark
WHERE a.entity_type = 'sector'
  AND a.date = :today
  AND b.date = (SELECT MAX(date) FROM de_rs_scores WHERE date <= :today - INTERVAL '28 days')
```

### 9.7 Days in Current Regime

```
WITH regime_today AS (
  SELECT regime FROM de_market_regime ORDER BY date DESC LIMIT 1
),
first_break AS (
  SELECT date FROM de_market_regime
  WHERE regime != (SELECT regime FROM regime_today)
  ORDER BY date DESC LIMIT 1
)
SELECT COUNT(*) AS days_in_regime
FROM de_market_regime
WHERE date > (SELECT date FROM first_break)
  AND regime = (SELECT regime FROM regime_today)
```

### 9.8 Sentiment Composite Score

```
component_breadth     = normalize(pct_above_200dma + pct_above_50dma + ad_ratio + mcclellan_norm + highs_lows_norm) to 0-100
component_pcr         = NULL (de_fo_summary empty)
component_flow        = NULL (de_flow_daily empty)
component_fundamental = normalize(median_revenue_growth + median_profit_growth - median_pe_deviation) to 0-100

# Available weights only:
composite = component_breadth * 0.60 + component_fundamental * 0.40
# (PCR and flow weights redistributed until pipeline fixed)
```

---

## 10. Summary of Gaps

| Gap | Severity | Affected Pages | Workaround |
|---|---|---|---|
| de_fo_summary: 0 rows | HIGH | pulse-sentiment (PCR score = missing) | Display "N/A — options data unavailable"; redistribute weight to breadth |
| de_flow_daily / de_institutional_flows: 5 rows | HIGH | pulse-sentiment (flow score), pulse-breadth (FII), sector actionables | Display "N/A — flow data unavailable" |
| de_intermarket_ratios: only 4 ratios | MEDIUM | pulse-global (sector ratios) | Derive additional ratios from de_rs_scores sector data |
| Sector RS 1M/3M NULLs | MEDIUM | pulse-sectors RRG period selector | Use rolling rs_composite snapshots for all period calculations |
| de_intermarket_ratios: only 20 rows total | MEDIUM | pulse-global (ratio history charts) | Chart will show only 20 data points; flag as limited history |
| Per-stock support/resistance levels | LOW | stock-detail interpretation rail | Use market-wide levels from de_goldilocks_market_view or TV sidecar |
| MF holdings table not named in audit | LOW | mf-detail holdings, weighted fundamentals | Confirm via JIP `/internal/mf/` API endpoint inspection |
| Ownership history via de_equity_fundamentals | LOW | stock-detail ownership chart | Verify row count per instrument; may only have 1 row (point-in-time, not series) |

---

## 11. Cleanup Chunk Scope (V6.5)

The following items are in scope for chunk V6.5 based on this mapping:

### Must fix (data gaps blocking UI)
1. **Confirm de_fo_summary pipeline status** with JIP team — no ATLAS fix needed, just visibility
2. **Confirm de_flow_daily pipeline status** with JIP team — same
3. **Add "data unavailable" graceful degradation** in sentiment API responses for empty components

### Derivations to implement in ATLAS backend
1. `GET /api/v1/market/regime` — adds `days_in_regime` field (§9.7 query)
2. `GET /api/v1/sectors/rrg` — RS momentum via §9.6 query; normalize to 100-center; return quadrant
3. `GET /api/v1/stocks/{symbol}/conviction` — 4-factor score (§9.3); Gold RS signal (§9.1); action + urgency (§9.4/§9.5)
4. `GET /api/v1/stocks/{symbol}/piotroski` — F-Score (§9.2)
5. `GET /api/v1/sentiment/composite` — composite score with graceful null handling (§9.8)
6. `GET /api/v1/screener` — bulk conviction scores for explorer table

### Schema verifications needed before building API
- Verify `de_equity_fundamentals` cardinality: 1-row-per-stock or time-series?
- Confirm MF holdings table name via JIP API inspection
- Verify `de_rs_daily_summary` vs `de_rs_scores` for equity RS (14.74M rows vs 10.5M — check which is correct source for equity entity_type)

### Do NOT implement in V6.5 (atlas_* writes required, deferred)
- `atlas_decisions` table for urgency tracking (requires new migration)
- Persistent conviction cache (use query-time computation for now)
- Piotroski batch pre-computation (compute on-demand per stock)
