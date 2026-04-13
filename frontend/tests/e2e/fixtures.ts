/**
 * TEST FIXTURES — not production data
 *
 * These fixtures are used by Playwright E2E tests to intercept
 * /api/v1/* backend calls without requiring a live ATLAS server.
 */

import type {
  StatusResponse,
  BreadthResponse,
  SectorListResponse,
  UniverseResponse,
  DeepDiveResponse,
  MoversResponse,
  RsHistoryResponse,
  DecisionListResponse,
} from "../../src/lib/api";

export const STATUS_FIXTURE: StatusResponse = {
  status: "ok",
  version: "0.1.0-test",
  freshness: {
    equity_ohlcv_as_of: "2026-04-11",
    rs_scores_as_of: "2026-04-11",
    technicals_as_of: "2026-04-11",
    breadth_as_of: "2026-04-11",
    regime_as_of: "2026-04-11",
    mf_holdings_as_of: "2026-04-11",
  },
  active_stocks: 2743,
  sectors: 31,
};

export const BREADTH_FIXTURE: BreadthResponse = {
  breadth: {
    date: "2026-04-11",
    advance: 1400,
    decline: 900,
    unchanged: 200,
    total_stocks: 2500,
    ad_ratio: "1.56",
    pct_above_200dma: "58.4",
    pct_above_50dma: "47.2",
    new_52w_highs: 34,
    new_52w_lows: 8,
  },
  regime: {
    date: "2026-04-11",
    regime: "BULL",
    confidence: "0.74",
    breadth_score: "0.68",
    momentum_score: "0.72",
    volume_score: "0.55",
    global_score: "0.61",
    fii_score: "0.58",
  },
  meta: { data_as_of: "2026-04-11", record_count: 1, query_ms: 12, stale: false },
};

export const SECTORS_FIXTURE: SectorListResponse = {
  sectors: [
    {
      sector: "Banks",
      stock_count: 25,
      avg_rs_composite: "6.2",
      avg_rs_momentum: "0.8",
      sector_quadrant: "LEADING",
      pct_above_200dma: "72.0",
      pct_above_50dma: "64.0",
      pct_above_ema21: "60.0",
      avg_rsi_14: "58.4",
      pct_rsi_overbought: "12.0",
      pct_rsi_oversold: "4.0",
      avg_adx: "28.5",
      pct_adx_trending: "48.0",
      pct_macd_bullish: "56.0",
      pct_roc5_positive: "60.0",
      avg_beta: "1.05",
      avg_sharpe: "1.2",
      avg_sortino: "1.6",
      avg_volatility_20d: "18.5",
      avg_max_dd: "-14.2",
      avg_calmar: "0.88",
      avg_mf_holders: "42.3",
      avg_disparity_20: "2.1",
    },
    {
      sector: "IT Services",
      stock_count: 30,
      avg_rs_composite: "5.1",
      avg_rs_momentum: "-0.3",
      sector_quadrant: "WEAKENING",
      pct_above_200dma: "55.0",
      pct_above_50dma: "40.0",
      pct_above_ema21: "38.0",
      avg_rsi_14: "48.7",
      pct_rsi_overbought: "6.0",
      pct_rsi_oversold: "10.0",
      avg_adx: "22.1",
      pct_adx_trending: "30.0",
      pct_macd_bullish: "38.0",
      pct_roc5_positive: "42.0",
      avg_beta: "0.92",
      avg_sharpe: "0.9",
      avg_sortino: "1.1",
      avg_volatility_20d: "21.3",
      avg_max_dd: "-18.5",
      avg_calmar: "0.55",
      avg_mf_holders: "38.7",
      avg_disparity_20: "-1.4",
    },
    {
      sector: "Pharma",
      stock_count: 22,
      avg_rs_composite: "4.8",
      avg_rs_momentum: "0.5",
      sector_quadrant: "IMPROVING",
      pct_above_200dma: "63.6",
      pct_above_50dma: "54.5",
      pct_above_ema21: "50.0",
      avg_rsi_14: "55.2",
      pct_rsi_overbought: "9.1",
      pct_rsi_oversold: "4.5",
      avg_adx: "25.8",
      pct_adx_trending: "40.9",
      pct_macd_bullish: "50.0",
      pct_roc5_positive: "54.5",
      avg_beta: "0.78",
      avg_sharpe: "1.1",
      avg_sortino: "1.4",
      avg_volatility_20d: "16.2",
      avg_max_dd: "-12.8",
      avg_calmar: "0.92",
      avg_mf_holders: "31.2",
      avg_disparity_20: "1.8",
    },
  ],
  meta: { data_as_of: "2026-04-11", record_count: 3, query_ms: 45, stale: false },
};

const HDFC_STOCK = {
  id: "aaa-111",
  symbol: "HDFCBANK",
  company_name: "HDFC Bank Limited",
  sector: "Banks",
  nifty_50: true as const,
  nifty_200: true as const,
  nifty_500: true as const,
  close: "1650.50",
  rs_composite: "7.1",
  rs_momentum: "0.9",
  quadrant: "LEADING",
  rsi_14: "62.3",
  adx_14: "32.5",
  above_200dma: true as const,
  above_50dma: true as const,
  macd_histogram: "5.2",
  beta_nifty: "1.02",
  sharpe_1y: "1.45",
  mf_holder_count: 58,
  cap_category: "Large Cap",
};

const ICICI_STOCK = {
  id: "bbb-222",
  symbol: "ICICIBANK",
  company_name: "ICICI Bank Limited",
  sector: "Banks",
  nifty_50: true as const,
  nifty_200: true as const,
  nifty_500: true as const,
  close: "1240.75",
  rs_composite: "6.8",
  rs_momentum: "0.7",
  quadrant: "LEADING",
  rsi_14: "59.8",
  adx_14: "29.1",
  above_200dma: true as const,
  above_50dma: true as const,
  macd_histogram: "3.8",
  beta_nifty: "1.08",
  sharpe_1y: "1.32",
  mf_holder_count: 52,
  cap_category: "Large Cap",
};

export const UNIVERSE_BANKS_FIXTURE: UniverseResponse = {
  sectors: [{ sector: "Banks", stock_count: 2, stocks: [HDFC_STOCK, ICICI_STOCK] }],
  meta: { data_as_of: "2026-04-11", record_count: 2, query_ms: 38, stale: false },
};

export const UNIVERSE_ALL_FIXTURE: UniverseResponse = {
  sectors: [{ sector: "Banks", stock_count: 2, stocks: [HDFC_STOCK, ICICI_STOCK] }],
  meta: { data_as_of: "2026-04-11", record_count: 2, query_ms: 38, stale: false },
};

export const UNIVERSE_IT_FIXTURE: UniverseResponse = {
  sectors: [
    {
      sector: "IT Services",
      stock_count: 1,
      stocks: [
        {
          id: "ccc-333",
          symbol: "INFY",
          company_name: "Infosys Limited",
          sector: "IT Services",
          nifty_50: true,
          nifty_200: true,
          nifty_500: true,
          close: "1820.00",
          rs_composite: "3.2",
          rs_momentum: "-0.8",
          quadrant: "LAGGING",
          rsi_14: "42.1",
          adx_14: "18.5",
          above_200dma: false,
          above_50dma: false,
          macd_histogram: "-2.1",
          beta_nifty: "0.88",
          sharpe_1y: "0.72",
          mf_holder_count: 45,
          cap_category: "Large Cap",
        },
      ],
    },
  ],
  meta: { data_as_of: "2026-04-11", record_count: 1, query_ms: 30, stale: false },
};

export const DEEPDIVE_FIXTURE: DeepDiveResponse = {
  stock: {
    id: "aaa-111",
    symbol: "HDFCBANK",
    company_name: "HDFC Bank Limited",
    sector: "Banks",
    industry: "Private Sector Banks",
    close: "1650.50",
    rsi_14: "62.3",
    adx_14: "32.5",
    above_200dma: true,
    above_50dma: true,
    macd_histogram: "5.2",
    beta_nifty: "1.02",
    sharpe_1y: "1.45",
    sortino_1y: "1.88",
    max_drawdown_1y: "-11.2",
    volatility_20d: "16.8",
    sma_50: "1580.30",
    sma_200: "1495.70",
    cap_category: "Large Cap",
    nifty_50: true,
    nifty_200: true,
    nifty_500: true,
    conviction: {
      rs: {
        rs_composite: "7.1",
        rs_momentum: "0.9",
        quadrant: "LEADING",
        benchmark: "NIFTY 500",
        explanation: "Strong relative strength vs benchmark",
        rs_1w: "7.3",
        rs_1m: "6.9",
        rs_3m: "6.5",
        rs_6m: "6.1",
        rs_12m: "5.8",
      },
      technical: {
        checks_passing: 7,
        checks_total: 8,
        checks: [
          { name: "Above 200 DMA", passing: true, value: "Yes", detail: "Price > SMA200" },
          { name: "Above 50 DMA", passing: true, value: "Yes", detail: "Price > SMA50" },
          { name: "RSI healthy", passing: true, value: "62.3", detail: "30 < RSI < 70" },
          { name: "ADX trending", passing: true, value: "32.5", detail: "ADX > 25" },
          { name: "MACD bullish", passing: true, value: "5.2", detail: "Histogram > 0" },
          { name: "Beta reasonable", passing: true, value: "1.02", detail: "Beta < 1.5" },
          { name: "Sharpe > 1", passing: true, value: "1.45", detail: "Sharpe > 1.0" },
          { name: "Low drawdown", passing: false, value: "-11.2%", detail: "Max DD > -15%" },
        ],
        explanation: "7 of 8 technical checks passing",
      },
      institutional: {
        mf_holder_count: 58,
        delivery_vs_avg: "1.24",
        explanation: "58 MF holders — high institutional interest",
      },
    },
    mf_holder_count: 58,
  },
  meta: { data_as_of: "2026-04-11", record_count: 1, query_ms: 22, stale: false },
};

export const RS_HISTORY_FIXTURE: RsHistoryResponse = {
  symbol: "HDFCBANK",
  benchmark: "NIFTY 500",
  data: [
    { date: "2025-04-11", rs_composite: "5.8" },
    { date: "2025-07-11", rs_composite: "6.1" },
    { date: "2025-10-11", rs_composite: "6.4" },
    { date: "2026-01-11", rs_composite: "6.7" },
    { date: "2026-04-11", rs_composite: "7.1" },
  ],
  meta: { data_as_of: "2026-04-11", record_count: 5, query_ms: 15, stale: false },
};

export const MOVERS_FIXTURE: MoversResponse = {
  gainers: [
    {
      symbol: "HDFCBANK",
      company_name: "HDFC Bank Limited",
      sector: "Banks",
      rs_composite: "7.1",
      rs_momentum: "0.9",
      quadrant: "LEADING",
    },
  ],
  losers: [
    {
      symbol: "INFY",
      company_name: "Infosys Limited",
      sector: "IT Services",
      rs_composite: "3.2",
      rs_momentum: "-0.8",
      quadrant: "LAGGING",
    },
  ],
  meta: { data_as_of: "2026-04-11", record_count: 2, query_ms: 18, stale: false },
};

export const DECISIONS_FIXTURE: DecisionListResponse = {
  decisions: [
    {
      id: "dec-001",
      symbol: "HDFCBANK",
      signal: "ENTER",
      quadrant: "LEADING",
      reason: "RS composite crossed 7.0 threshold",
      created_at: "2026-04-11T09:15:00+05:30",
      action: "PENDING",
      action_at: null,
      action_note: null,
    },
  ],
  meta: { data_as_of: "2026-04-11", record_count: 1, query_ms: 8, stale: false },
};
