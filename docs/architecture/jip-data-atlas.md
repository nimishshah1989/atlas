# JIP Data Atlas — Complete Data Point Reference

> **Purpose:** Single-source reference for all JIP (`de_*`) data available to ATLAS. Use this before designing any frontend screen or planning any enrichment. Do NOT scan de_* tables for each task — read this instead.
>
> **Last updated:** 2026-04-17  
> **Scope:** All 141 `de_*` tables across Stock, MF, ETF, Index, Global/Macro asset classes  
> **Data depth:** 25yr equity OHLCV, 18yr MF NAV, 10yr+ macro series  
> **Total size:** ~20 GB across de_* tables

---

## Table of Contents

1. [Stock / Equity](#1-stock--equity)
2. [Mutual Funds](#2-mutual-funds)
3. [ETF](#3-etf)
4. [Indices & Sectors](#4-indices--sectors)
5. [Global & Macro](#5-global--macro)
6. [Cross-Cutting: Market Intelligence](#6-cross-cutting-market-intelligence)
7. [Cross-Cutting: Institutional Flows & Sentiment](#7-cross-cutting-institutional-flows--sentiment)
8. [Enrichment Opportunities — V1–V5 Gaps](#8-enrichment-opportunities--v1v5-gaps)
9. [Quick Lookup: Table → Asset Class → Category](#9-quick-lookup-table--asset-class--category)

---

## 1. Stock / Equity

**Universe:** 2,000+ active NSE/BSE listed stocks. Master in `de_instrument`.

### 1.1 Identity & Classification
**Table:** `de_instrument`  
**Category:** Reference

| Column | Description |
|--------|-------------|
| `current_symbol` | NSE ticker |
| `isin` | ISIN (join key) |
| `company_name` | Full name |
| `sector` | Sector (13 categories) |
| `industry` | Sub-industry |
| `bse_scripcode` | BSE scrip code |
| `nifty_50` / `nifty_200` / `nifty_500` | Index membership flags |
| `listing_date` | IPO date |

**Table:** `de_market_cap_history`  
| Column | Description |
|--------|-------------|
| `cap_category` | large / mid / small / micro |
| `effective_from` / `effective_to` | Category validity window |

**Table:** `de_index_constituents`  
| Column | Description |
|--------|-------------|
| `index_code` | NIFTY50, BANKNIFTY, NIFTY_IT, etc. |
| `weight_pct` | Constituent weight |
| `effective_from` / `effective_to` | Membership history |

---

### 1.2 Price History (OHLCV)
**Table:** `de_equity_ohlcv` — 2.9 GB, partitioned by year (2000–2034)

| Column | Description |
|--------|-------------|
| `open` / `high` / `low` / `close` | Raw daily OHLCV |
| `close_adj` | Adjusted close (splits + dividends) |
| `volume` | Daily volume |

**Table:** `de_adjustment_factors_daily`  
| Column | Description |
|--------|-------------|
| `cumulative_factor` | Adjustment multiplier (splits, bonuses, dividends) |

---

### 1.3 Technical Indicators
**Table:** `de_equity_technical_daily` — **4.9 GB**, 80+ columns

#### Moving Averages
| Metric | Columns | V1–V5 Used? |
|--------|---------|-------------|
| Simple MA | `sma_5`, `sma_10`, `sma_20`, `sma_50`, `sma_100`, `sma_200` | `sma_50`, `sma_200` ✓ |
| Exponential MA | `ema_5`, `ema_10`, `ema_20`, `ema_50`, `ema_100`, `ema_200` | `ema_20` ✓ |
| Advanced MA | `dema_20`, `tema_20`, `wma_20`, `hma_20`, `kama_20`, `zlma_20`, `alma_20` | ✗ gap |
| VWAP | `vwap` | ✗ gap |

#### Momentum Oscillators
| Metric | Columns | V1–V5 Used? |
|--------|---------|-------------|
| RSI | `rsi_7`, `rsi_9`, `rsi_14`, `rsi_21` | `rsi_14` ✓ |
| MACD | `macd_line`, `macd_signal`, `macd_histogram` | all ✓ |
| Stochastic | `stochastic_k`, `stochastic_d` | ✗ gap |
| Williams %R | `williams_r_14` | ✗ gap |
| CCI | `cci_20` | ✗ gap |
| CMO | `cmo_14` | ✗ gap |
| Ultimate Oscillator | `ultosc` | ✗ gap |
| TRIX | `trix_15` | ✗ gap |
| TSI | `tsi_13_25` | ✗ gap |
| Rate of Change | `roc_5`, `roc_10`, `roc_21`, `roc_63`, `roc_252` | ✗ gap |

#### Trend & Volatility
| Metric | Columns | V1–V5 Used? |
|--------|---------|-------------|
| ADX | `adx_14`, `plus_di`, `minus_di` | `adx_14` ✓ |
| Aroon | `aroon_up`, `aroon_down`, `aroon_osc` | ✗ gap |
| Supertrend | `supertrend_10_3` | ✗ gap |
| Parabolic SAR | `psar` | ✗ gap |
| Bollinger Bands | `bollinger_upper`, `bollinger_middle`, `bollinger_lower`, `bollinger_width`, `bb_pct_b` | ✗ gap |

#### Risk Metrics (1y / 3y / 5y)
| Metric | Columns | V1–V5 Used? |
|--------|---------|-------------|
| Beta | `beta_nifty`, `beta_3y`, `beta_5y` | `beta_nifty` ✓ |
| Sharpe | `sharpe_1y`, `sharpe_3y`, `sharpe_5y` | `sharpe_1y` ✓ |
| Sortino | `sortino_1y`, `sortino_3y`, `sortino_5y` | `sortino_1y` ✓ |
| Calmar | `calmar_ratio`, `calmar_3y`, `calmar_5y` | `calmar_ratio` ✓ |
| Max Drawdown | `max_drawdown_1y`, `max_drawdown_3y`, `max_drawdown_5y` | `max_drawdown_1y` ✓ |
| Volatility | `volatility_20d`, `volatility_3y`, `volatility_5y` | `volatility_20d` ✓ |
| Treynor | `treynor_1y`, `treynor_3y`, `treynor_5y` | ✗ gap |
| Information Ratio | `information_ratio_3y`, `information_ratio_5y` | ✗ gap |
| Downside Risk | `downside_risk_1y`, `downside_risk_3y`, `downside_risk_5y` | ✗ gap |
| Alpha / Omega | `risk_alpha_nifty`, `risk_omega`, `risk_information_ratio` | ✗ gap |

#### Statistical / Advanced
| Metric | Columns | V1–V5 Used? |
|--------|---------|-------------|
| Z-Score | `zscore_20` | ✗ gap |
| Linear Regression | `linreg_slope_20`, `linreg_r2_20`, `linreg_angle_20` | ✗ gap |
| Distribution | `skew_20`, `kurt_20` | ✗ gap |

#### Computed Boolean Signals
| Signal | Column | V1–V5 Used? |
|--------|--------|-------------|
| Above 200 DMA | `above_200dma` | ✓ |
| Above 50 DMA | `above_50dma` | ✓ |
| Above 20 EMA | `above_20ema` | ✓ |
| Price > VWAP | `price_above_vwap` | ✗ gap |
| RSI Overbought (>70) | `rsi_overbought` | ✗ gap |
| RSI Oversold (<30) | `rsi_oversold` | ✗ gap |
| MACD Bullish | `macd_bullish` | ✗ gap |
| ADX Strong Trend | `adx_strong_trend` | ✗ gap |

---

### 1.4 Relative Strength (RS) & Momentum
**Table:** `de_rs_scores` — 5.5 GB  
**Table:** `de_rs_daily_summary` — 1.9 GB (denormalized, preferred for queries)

| Column | Description | V1–V5 Used? |
|--------|-------------|-------------|
| `rs_composite` | Composite RS score (vs NIFTY 500) | ✓ |
| `rs_1w` | 1-week RS | ✓ |
| `rs_1m` | 1-month RS | ✓ |
| `rs_3m` | 3-month RS | ✓ |
| `rs_6m` | 6-month RS | ✓ |
| `rs_12m` | 12-month RS | ✓ |

---

### 1.5 Fundamentals
**Table:** `de_equity_fundamentals` — **NOT used in V1–V5**  
**Sources:** Screener.in + BSE filings  
**Category:** Fundamentals

#### Valuation
| Column | Description |
|--------|-------------|
| `pe_ratio` | Price-to-earnings (TTM) |
| `pb_ratio` | Price-to-book |
| `peg_ratio` | PEG ratio |
| `ev_ebitda` | Enterprise value / EBITDA |
| `market_cap_cr` | Market cap (₹ crore) |
| `eps_ttm` | Earnings per share (TTM) |
| `book_value` | Book value per share |

#### Profitability
| Column | Description |
|--------|-------------|
| `roe_pct` | Return on equity |
| `roce_pct` | Return on capital employed |
| `operating_margin_pct` | Operating margin |
| `net_margin_pct` | Net profit margin |

#### Leverage & Liquidity
| Column | Description |
|--------|-------------|
| `debt_to_equity` | D/E ratio |
| `interest_coverage` | EBIT / interest expense |
| `current_ratio` | Current assets / current liabilities |

#### Shareholder Structure
| Column | Description |
|--------|-------------|
| `promoter_holding_pct` | Promoter stake % |
| `pledged_pct` | Pledged shares % |
| `fii_holding_pct` | FII stake % |
| `dii_holding_pct` | DII stake % |

#### Growth
| Column | Description |
|--------|-------------|
| `revenue_growth_yoy_pct` | Revenue YoY growth |
| `profit_growth_yoy_pct` | Net profit YoY growth |

#### Dividends & Price Range
| Column | Description |
|--------|-------------|
| `dividend_per_share` / `dividend_yield_pct` | Dividend data |
| `high_52w` / `low_52w` | 52-week price range |
| `face_value` | Share face value |

**Table:** `de_equity_fundamentals_history` — Historical snapshots of all above columns

---

### 1.6 Corporate Events & Filings
**Table:** `de_bse_announcements` — 33 MB — **NOT used in V1–V5**

| Column | Description |
|--------|-------------|
| `announcement_dt` | Announcement timestamp |
| `headline` | Short headline |
| `category` | Type (Board Meeting, Results, Dividend, AGM, etc.) |
| `subcategory` | Sub-type |
| `description` | Full text |
| `attachment_url` | Filing URL |

**Table:** `de_bse_result_calendar` — **NOT used in V1–V5**

| Column | Description |
|--------|-------------|
| `result_date` | Expected announcement date |
| `period` | Q1 / Q2 / Q3 / Q4 / FY |
| `announced_at` | Actual announcement timestamp |

**Table:** `de_bse_corp_actions` — **NOT used in V1–V5**

| Column | Description |
|--------|-------------|
| `action_type` | split / bonus / dividend / rights |
| `ex_date` / `record_date` | Key dates |
| `ratio` | Bonus/split ratio |
| `amount_per_share` | Dividend amount |

---

### 1.7 Advanced Technical Patterns
**Table:** `de_divergence_signals` — **NOT used in V1–V5**

| Column | Description |
|--------|-------------|
| `timeframe` | D / W / M |
| `divergence_type` | bullish / bearish |
| `indicator` | RSI / MACD / CCI / etc. |
| `strength` | Signal strength |

**Table:** `de_fib_levels` — **NOT used in V1–V5**

| Column | Description |
|--------|-------------|
| `swing_high` / `swing_low` | Swing extremes |
| `fib_236` / `fib_382` / `fib_500` / `fib_618` / `fib_786` | Fibonacci levels |

**Table:** `de_oscillator_weekly` / `de_oscillator_monthly` — **NOT used in V1–V5**

| Column | Description |
|--------|-------------|
| `stochastic_k` / `stochastic_d` | Weekly/monthly stochastic |
| `rsi_14` | Weekly/monthly RSI |
| `disparity_20` | Price disparity from MA |

---

## 2. Mutual Funds

**Universe:** 3,000+ funds. Master in `de_mf_master`.

### 2.1 Identity & Classification
**Table:** `de_mf_master`  

| Column | Description | V1–V5 Used? |
|--------|-------------|-------------|
| `mstar_id` | Primary key (Morningstar ID) | ✓ |
| `amfi_code` | AMFI scheme code | ✓ |
| `isin` | ISIN | ✓ |
| `fund_name` | Full fund name | ✓ |
| `amc_name` | AMC (fund house) | ✓ |
| `category_name` | SEBI category (Large Cap, ELSS, etc.) | ✓ |
| `broad_category` | Equity / Debt / Hybrid / Commodity | ✓ |
| `is_etf` / `is_index_fund` | ETF/index fund flags | ✓ |
| `is_active` | Active / wound-up | ✓ |
| `inception_date` | Fund launch date | ✓ |
| `expense_ratio` | Latest TER | ✓ |
| `primary_benchmark` | Benchmark index | partial |

---

### 2.2 NAV History
**Table:** `de_mf_nav_daily` — Partitioned by year (2006–2034)

| Column | Description | V1–V5 Used? |
|--------|-------------|-------------|
| `nav_date` | Date | ✓ |
| `nav` | Net asset value (₹) | ✓ |

---

### 2.3 Derived Analytics
**Table:** `de_mf_derived_daily` — 1.1 GB

| Category | Columns | V1–V5 Used? |
|----------|---------|-------------|
| RS | `derived_rs_composite`, `nav_rs_composite` | ✓ |
| Alpha | `manager_alpha` | ✓ |
| Coverage | `coverage_pct` | ✓ |
| Sharpe | `sharpe_1y`, `sharpe_3y`, `sharpe_5y` | `sharpe_1y` ✓; 3y/5y ✗ gap |
| Sortino | `sortino_1y`, `sortino_3y`, `sortino_5y` | `sortino_1y` ✓; 3y/5y ✗ gap |
| Max Drawdown | `max_drawdown_1y`, `max_drawdown_3y`, `max_drawdown_5y` | `max_drawdown_1y` ✓; 3y/5y ✗ gap |
| Volatility | `volatility_1y`, `volatility_3y` | `volatility_1y` ✓; 3y ✗ gap |
| StdDev | `stddev_1y`, `stddev_3y`, `stddev_5y` | ✗ gap |
| Beta | `beta_vs_nifty` | ✓ |
| Treynor | `treynor_ratio` | ✗ gap |
| Information Ratio | `information_ratio` | ✗ gap |

---

### 2.4 MF-Level Technicals (NEW)
**Table:** `de_mf_technical_daily` — 937 MB  
**Category:** Technicals (holdings-weighted or NAV-derived)

Same 46-column technical suite as equity (RSI, MACD, ADX, Bollinger, Stochastic, MAs, risk metrics) — applied to NAV series.  
**Currently exposed:** only via `de_mf_weighted_technicals` (3 columns). Full table largely unused.

**Table:** `de_mf_weighted_technicals` — Holdings-weighted stock technicals rolled up to fund level

| Column | Description | V1–V5 Used? |
|--------|-------------|-------------|
| `weighted_rsi` | Holdings-weighted RSI | ✓ |
| `weighted_breadth_pct_above_200dma` | % AUM in stocks above 200 DMA | ✓ |
| `weighted_macd_bullish_pct` | % AUM with bullish MACD | ✓ |

---

### 2.5 Holdings & Exposure
**Table:** `de_mf_holdings` — 119 MB

| Column | Description | V1–V5 Used? |
|--------|-------------|-------------|
| `holding_name` | Stock / bond name | ✓ |
| `isin` / `instrument_id` | Link to equity master | ✓ |
| `weight_pct` | Portfolio weight | ✓ |
| `market_value` | Value (₹ crore) | ✓ |
| `sector_code` | Holding sector | ✓ |
| `is_mapped` | Mapped to de_instrument? | ✓ |
| `shares_held` | Units held | partial |

**Table:** `de_mf_sector_exposure`

| Column | Description | V1–V5 Used? |
|--------|-------------|-------------|
| `sector` | Sector name | ✓ |
| `weight_pct` | % allocation | ✓ |
| `stock_count` | Number of stocks in sector | ✓ |

---

### 2.6 Flows
**Table:** `de_mf_category_flows` — Monthly category-level flows

| Column | Description | V1–V5 Used? |
|--------|-------------|-------------|
| `category` | SEBI category | ✓ |
| `month_date` | Month | ✓ |
| `net_flow_cr` | Net inflows (₹ crore) | ✓ |
| `gross_inflow_cr` / `gross_outflow_cr` | Gross flows | ✓ |
| `aum_cr` | AUM (₹ crore) | ✓ |
| `sip_flow_cr` | SIP contribution | ✓ |
| `sip_accounts` | Active SIP accounts | ✓ |
| `folios` | Total folio count | partial |

---

### 2.7 Lifecycle & Dividends
**Table:** `de_mf_lifecycle` — **underused**

| Column | Description |
|--------|-------------|
| `event_date` | Event date |
| `event_type` | inception / closure / merger / name_change |
| `description` | Details |

**Table:** `de_mf_dividends` — **NOT used in V1–V5**

| Column | Description |
|--------|-------------|
| `record_date` | Record date |
| `dividend_per_unit` | Dividend declared |
| `nav_before` / `nav_after` | NAV impact |
| `adj_factor` | Adjustment factor |

---

## 3. ETF

**Universe:** 500+ global ETFs. Master in `de_etf_master`.

### 3.1 Identity & Classification
**Table:** `de_etf_master`

| Column | Description |
|--------|-------------|
| `ticker` | Primary key |
| `name` | ETF name |
| `exchange` | NYSE / NASDAQ / BSE / NSE |
| `country` | Domicile country |
| `currency` | Trading currency |
| `sector` | Sector focus |
| `asset_class` | Equity / Fixed Income / Commodity / Currency |
| `category` | Sub-category (e.g., Large Cap, Emerging Markets) |
| `benchmark` | Tracked index |
| `expense_ratio` | TER |
| `inception_date` | Launch date |

---

### 3.2 Price History & Technicals
**Table:** `de_etf_ohlcv` — 56 MB  
Same OHLCV schema as equities.

**Table:** `de_etf_technical_daily` — **490 MB** — **NOT used in V1–V5**  
Full 46-column technical suite (identical structure to `de_equity_technical_daily`).

> **Gap:** ETF technicals exist but zero routes query this table. ETF rotation strategies, technical screening, and comparative analysis all blocked.

**Table:** `de_rs_scores` (entity_type filter)  
ETF RS scores available via same table as equities.

---

## 4. Indices & Sectors

**Universe:** 200+ indices (broad, sectoral, thematic, strategy). Master in `de_index_master`.

### 4.1 Identity & Structure
**Table:** `de_index_master`

| Column | Description |
|--------|-------------|
| `index_code` | NIFTY50, NIFTY_IT, BANKNIFTY, etc. |
| `index_name` | Full name |
| `category` | broad / sectoral / thematic / strategy |

**Table:** `de_sector_mapping`

| Column | Description |
|--------|-------------|
| `sector` | Sector name |
| `primary_nse_index` | Corresponding NSE index |
| `bse_sector_code` | BSE sector code |

---

### 4.2 Price History
**Table:** `de_index_prices` — 40 MB

| Column | Description | V1–V5 Used? |
|--------|-------------|-------------|
| `close` / `high` / `low` | Daily price | partial |
| `volume` | Volume | partial |

---

### 4.3 Index Technicals
**Table:** `de_index_technical_daily` — **292 MB** — **NOT fully used in V1–V5**  
48-column technical suite (same as equity, plus `bollinger_width`, `bb_pct_b`).

> **Gap:** Only market breadth endpoint queries this. No index technical screening, no regime-based scoring.

**Table:** `de_index_pivots` — **NOT used in V1–V5**

| Column | Description |
|--------|-------------|
| `pivot` | Daily pivot level |
| `s1` / `s2` / `s3` | Support levels |
| `r1` / `r2` / `r3` | Resistance levels |

---

### 4.4 Market Breadth
**Table:** `de_breadth_daily` — **Used in V1–V5**

| Category | Columns |
|----------|---------|
| Advance/Decline | `advance`, `decline`, `unchanged`, `total_stocks`, `ad_ratio` |
| DMA Breadth | `pct_above_200dma`, `pct_above_50dma` |
| Extremes | `new_52w_highs`, `new_52w_lows` |
| McClellan | `mcclellan_oscillator`, `mcclellan_summation` |

**Table:** `de_sector_breadth_daily` — 33 MB — **NOT fully used in V1–V5**

| Category | Columns |
|----------|---------|
| Stock count | `stocks_total` |
| DMA breadth | `stocks_above_50dma`, `stocks_above_200dma`, `pct_above_50dma`, `pct_above_200dma` |
| EMA breadth | `stocks_above_20ema` |
| Momentum | `stocks_rsi_overbought`, `stocks_rsi_oversold`, `stocks_macd_bullish` |
| Regime | `breadth_regime` |

---

### 4.5 Market Regime
**Table:** `de_market_regime` — **Used in V1–V5**

| Column | Description |
|--------|-------------|
| `regime` | bullish / bearish / sideways |
| `regime_strength` | Strength score |
| `trend_change_date` | Last regime transition |

---

## 5. Global & Macro

### 5.1 Global Assets
**Table:** `de_global_instrument_master`

| Column | Description |
|--------|-------------|
| `ticker` | Ticker |
| `instrument_type` | index / etf |
| `exchange` | Exchange |
| `currency` | Currency |
| `country` | Country |
| `category` | Asset category |
| `source` | Data source |

**Table:** `de_global_prices` — 36 MB — **Used partially in V1–V5**  
Same OHLCV schema.

**Table:** `de_global_technical_daily` — 330 MB — **Used partially in V1–V5**  
Full 46-column technical suite for global assets.

---

### 5.2 Macroeconomic Indicators
**Table:** `de_macro_master` — Master registry

| Ticker | Name | Source | Unit |
|--------|------|--------|------|
| `DGS10` | US 10yr Treasury Yield | FRED | % |
| `VIXCLS` | CBOE VIX | FRED | Index |
| `INDIAVIX` | India VIX | NSE | Index |
| `DXY` | US Dollar Index | FRED | Index |
| `BRENT` | Brent Crude | FRED | USD/barrel |
| `GOLD` | Gold spot | FRED | USD/troy oz |
| `SP500` | S&P 500 Index | FRED | Index |
| `USDINR` | USD/INR Exchange Rate | RBI | ₹/USD |
| 40+ others | Repo rate, CPI, IIP, M3, GST, credit, etc. | RBI/MOSPI/NSO/SEBI/BSE | Various |

**Table:** `de_macro_values` — 10+ years daily — **Partially used (8/50+ tickers)**

| Column | Description |
|--------|-------------|
| `date` | Date |
| `ticker` | Macro indicator ticker |
| `value` | Indicator value |

> **Gap:** Only 8 default tickers exposed via `get_macro_ratios`. 40+ RBI/MOSPI/NSO macro series (repo rate, CPI, IIP, GST collections, credit growth, M3 money supply, etc.) sitting unused.

---

### 5.3 Intermarket Analysis
**Table:** `de_intermarket_ratios` — **NOT used in V1–V5**

| Column | Description |
|--------|-------------|
| `ratio_name` | Ratio identifier (e.g., equity_bond_spread) |
| `value` | Ratio value |
| `sma_20` | 20-day moving average of ratio |
| `direction` | Trending up / down / sideways |

---

## 6. Cross-Cutting: Market Intelligence

### 6.1 Goldilocks Signals (Used in V1–V5)
**Table:** `de_goldilocks_stock_ideas`

| Column | Description |
|--------|-------------|
| `symbol` | Stock ticker |
| `idea_type` | BUY / SELL / HOLD |
| `entry_price` / `entry_zone_low` / `entry_zone_high` | Entry levels |
| `target_1` / `target_2` / `lt_target` | Targets |
| `stop_loss` | Stop level |
| `timeframe` | Trade horizon |
| `rationale` | Reasoning text |
| `technical_params` | JSONB — additional parameters |
| `status` | active / hit_target / stopped_out |
| `published_date` | Signal date |

**Table:** `de_goldilocks_market_view`

| Column | Description |
|--------|-------------|
| `nifty_close` | NIFTY close |
| `nifty_support_1` / `nifty_support_2` | NIFTY support levels |
| `nifty_resistance_1` / `nifty_resistance_2` | NIFTY resistance levels |
| `bank_nifty_close` | BANKNIFTY close |
| `bank_nifty_support` / `bank_nifty_resistance` | BANKNIFTY levels |
| `trend_direction` | Bullish / Bearish / Neutral |
| `trend_strength` | Strength |
| `headline` | Market view headline |
| `overall_view` | Detailed analysis |
| `global_impact` | Global factors text |

**Table:** `de_goldilocks_sector_view`

| Column | Description |
|--------|-------------|
| `sector` | Sector name |
| `trend` | Sector trend |
| `outlook` | Bullish / Bearish / Neutral |
| `rank` | Sector rank |
| `top_picks` | JSONB — top stock picks |

---

### 6.2 Derivatives Intelligence
**Table:** `de_fo_summary` — **Available but NOT fully exposed in UI**

| Column | Description |
|--------|-------------|
| `pcr_oi` | Put-call ratio (open interest) |
| `pcr_volume` | Put-call ratio (volume) |
| `fii_net_longs` / `fii_net_shorts` | FII derivative positioning |
| `max_pain` | Options max pain level |

---

## 7. Cross-Cutting: Institutional Flows & Sentiment

### 7.1 Institutional Flows
**Table:** `de_institutional_flows` — **NOT used in V1–V5**

| Column | Description |
|--------|-------------|
| `date` | Date |
| `category` | FII / DII / MF / Insurance / Banks / Corporates / Retail |
| `market_type` | equity / debt / hybrid / derivatives |
| `gross_buy` / `gross_sell` | Gross flows (₹ crore) |
| `net_flow` (computed) | Net flow |
| `source` | Data source |

> Distinct from `de_mf_category_flows` — this covers ALL institutional categories at market-type granularity.

---

### 7.2 Champion Trades
**Table:** `de_champion_trades` — **NOT used in V1–V5**  
Algorithmic/champion trade signals (potential insider activity proxy). Validate data quality before using.

---

## 8. Enrichment Opportunities — V1–V5 Gaps

Ranked by immediate product value. All data exists; only backend routes + frontend need to be added.

### Priority 1 — High Impact / Low Effort

| # | Enhancement | Tables | What to add |
|---|------------|--------|-------------|
| 1 | **Fundamental scoring on stock detail** | `de_equity_fundamentals` | PE/PB/PEG/EV-EBITDA, ROE/ROCE, margins, D/E, promoter/FII/DII holding, revenue+profit YoY growth |
| 2 | **Earnings calendar** | `de_bse_result_calendar` | Show upcoming + past results per stock; Q1–FY history |
| 3 | **Sector breadth per-sector** | `de_sector_breadth_daily` | % above 50/200DMA, overbought/oversold, MACD bullish per sector |
| 4 | **Extended MF risk metrics (3y/5y)** | `de_mf_derived_daily` | Add sharpe_3y/5y, sortino_3y/5y, max_drawdown_3y/5y, stddev_3y/5y to fund detail |
| 5 | **Extended stock risk metrics (3y/5y)** | `de_equity_technical_daily` | Add treynor, information_ratio, downside_risk, risk_alpha, risk_omega |

### Priority 2 — Medium Impact / Medium Effort

| # | Enhancement | Tables | What to add |
|---|------------|--------|-------------|
| 6 | **BSE corporate announcements** | `de_bse_announcements` | Board meeting, dividend, rights, restructuring feed per stock |
| 7 | **Corporate actions timeline** | `de_bse_corp_actions` | Splits, bonus, dividend history with ex-dates per stock |
| 8 | **Institutional flows dashboard** | `de_institutional_flows` | FII/DII/MF flows by equity/debt/derivatives — separate from MF flows |
| 9 | **MF full technical indicators** | `de_mf_technical_daily` | RSI, MACD, ADX, Bollinger on NAV series (not just weighted holdings) |
| 10 | **ETF technical screening** | `de_etf_technical_daily` | ETF screener with same technical filters as equity screener |
| 11 | **Derivatives intelligence** | `de_fo_summary` | PCR OI/volume, FII longs/shorts, max pain on market view |
| 12 | **Expanded macro tickers** | `de_macro_values`, `de_macro_master` | Expose repo rate, CPI, IIP, credit growth, GST, M3 (40+ series) |

### Priority 3 — Advanced / Niche

| # | Enhancement | Tables | What to add |
|---|------------|--------|-------------|
| 13 | **Index pivot levels** | `de_index_pivots` | Support/resistance pivots on index chart |
| 14 | **Intermarket ratios** | `de_intermarket_ratios` | Equity/bond spread, cross-asset technicals |
| 15 | **Divergence signals** | `de_divergence_signals` | RSI/MACD divergence alerts per stock |
| 16 | **Fibonacci levels** | `de_fib_levels` | Fib support/resistance on stock chart |
| 17 | **Weekly/monthly oscillators** | `de_oscillator_weekly`, `de_oscillator_monthly` | Higher-timeframe stochastic, RSI, disparity |
| 18 | **MF dividend history** | `de_mf_dividends` | Dividend track record, NAV impact per fund |
| 19 | **Advanced boolean signals** | `de_equity_technical_daily` | rsi_overbought/oversold, price_above_vwap, adx_strong_trend, macd_bullish |

---

## 9. Quick Lookup: Table → Asset Class → Category

| Table | Asset Class | Category | Size | V1–V5 Status |
|-------|-------------|----------|------|--------------|
| `de_instrument` | Stock | Reference | Small | ✓ Used |
| `de_equity_ohlcv` | Stock | Price | 2.9 GB | ✓ Used |
| `de_equity_technical_daily` | Stock | Technicals | 4.9 GB | Partial (35/80 cols) |
| `de_equity_fundamentals` | Stock | Fundamentals | Medium | ✗ Not used |
| `de_equity_fundamentals_history` | Stock | Fundamentals | Medium | ✗ Not used |
| `de_bse_announcements` | Stock | Corporate Events | 33 MB | ✗ Not used |
| `de_bse_result_calendar` | Stock | Corporate Events | Small | ✗ Not used |
| `de_bse_corp_actions` | Stock | Corporate Events | Small | ✗ Not used |
| `de_divergence_signals` | Stock | Technical Patterns | Small | ✗ Not used |
| `de_fib_levels` | Stock | Technical Patterns | Small | ✗ Not used |
| `de_oscillator_weekly` | Stock | Technicals | Small | ✗ Not used |
| `de_oscillator_monthly` | Stock | Technicals | Small | ✗ Not used |
| `de_adjustment_factors_daily` | Stock | Reference | Small | ✓ Used |
| `de_rs_scores` | Stock/MF/Global | RS/Momentum | 5.5 GB | ✓ Used |
| `de_rs_daily_summary` | Stock | RS/Momentum | 1.9 GB | ✓ Used |
| `de_market_cap_history` | Stock | Reference | Small | ✓ Used |
| `de_mf_master` | MF | Reference | Small | ✓ Used |
| `de_mf_nav_daily` | MF | Price | Large | ✓ Used |
| `de_mf_derived_daily` | MF | Analytics | 1.1 GB | Partial |
| `de_mf_technical_daily` | MF | Technicals | 937 MB | Partial (3 cols) |
| `de_mf_weighted_technicals` | MF | Technicals | Small | ✓ Used |
| `de_mf_holdings` | MF | Holdings | 119 MB | ✓ Used |
| `de_mf_sector_exposure` | MF | Holdings | Small | ✓ Used |
| `de_mf_category_flows` | MF | Flows | Small | ✓ Used |
| `de_mf_lifecycle` | MF | Reference | Small | Partial |
| `de_mf_dividends` | MF | Corporate Events | Small | ✗ Not used |
| `de_etf_master` | ETF | Reference | Small | Partial |
| `de_etf_ohlcv` | ETF | Price | 56 MB | Partial |
| `de_etf_technical_daily` | ETF | Technicals | 490 MB | ✗ Not used |
| `de_index_master` | Index | Reference | Small | ✓ Used |
| `de_index_prices` | Index | Price | 40 MB | Partial |
| `de_index_technical_daily` | Index | Technicals | 292 MB | Partial |
| `de_index_pivots` | Index | Technical Patterns | Small | ✗ Not used |
| `de_index_constituents` | Index | Reference | Small | ✓ Used |
| `de_breadth_daily` | Market | Breadth | Small | ✓ Used |
| `de_sector_breadth_daily` | Sector | Breadth | 33 MB | Partial |
| `de_market_regime` | Market | Regime | Small | ✓ Used |
| `de_macro_master` | Global | Reference | Small | ✓ Used |
| `de_macro_values` | Global | Macro | Medium | Partial (8/50+) |
| `de_intermarket_ratios` | Global | Macro | Small | ✗ Not used |
| `de_global_instrument_master` | Global | Reference | Small | ✓ Used |
| `de_global_prices` | Global | Price | 36 MB | ✓ Used |
| `de_global_technical_daily` | Global | Technicals | 330 MB | Partial |
| `de_institutional_flows` | Market | Flows | Small | ✗ Not used |
| `de_fo_summary` | Market | Derivatives | Small | Partial |
| `de_goldilocks_stock_ideas` | Market | Intelligence | Small | ✓ Used |
| `de_goldilocks_market_view` | Market | Intelligence | Small | ✓ Used |
| `de_goldilocks_sector_view` | Market | Intelligence | Small | ✓ Used |
| `de_sector_mapping` | Sector | Reference | Small | ✓ Used |
| `de_champion_trades` | Market | Intelligence | Small | ✗ Not used |

---

*This document is auto-generated from codebase analysis. Update after any new de_* table is added or V1-V5 routes are expanded.*
