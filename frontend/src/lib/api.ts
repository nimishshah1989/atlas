const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function getHealth() {
  return fetchApi<{ status: string }>("/api/v1/health");
}

export async function getStatus() {
  return fetchApi<StatusResponse>("/api/v1/status");
}

export async function getBreadth() {
  return fetchApi<BreadthResponse>("/api/v1/stocks/breadth");
}

export async function getSectors() {
  return fetchApi<SectorListResponse>("/api/v1/stocks/sectors");
}

export async function getUniverse(params?: {
  benchmark?: string;
  sector?: string;
}) {
  const qs = new URLSearchParams();
  if (params?.benchmark) qs.set("benchmark", params.benchmark);
  if (params?.sector) qs.set("sector", params.sector);
  const q = qs.toString();
  return fetchApi<UniverseResponse>(`/api/v1/stocks/universe${q ? `?${q}` : ""}`);
}

export async function getStockDeepDive(symbol: string) {
  return fetchApi<DeepDiveResponse>(`/api/v1/stocks/${symbol}`);
}

export async function getMovers() {
  return fetchApi<MoversResponse>("/api/v1/stocks/movers");
}

export async function getRsHistory(symbol: string, months = 12) {
  return fetchApi<RsHistoryResponse>(
    `/api/v1/stocks/${symbol}/rs-history?months=${months}`
  );
}

export async function getDecisions() {
  return fetchApi<DecisionListResponse>("/api/v1/decisions");
}

export async function actionDecision(
  id: string,
  action: string,
  note?: string
) {
  return fetchApi(`/api/v1/decisions/${id}/action`, {
    method: "PUT",
    body: JSON.stringify({ action, note }),
  });
}

// --- Types ---

interface Meta {
  data_as_of: string | null;
  record_count: number;
  query_ms: number | null;
  stale: boolean;
}

export interface StatusResponse {
  status: string;
  version: string;
  freshness: {
    equity_ohlcv_as_of: string | null;
    rs_scores_as_of: string | null;
    technicals_as_of: string | null;
    breadth_as_of: string | null;
    regime_as_of: string | null;
    mf_holdings_as_of: string | null;
  };
  active_stocks: number;
  sectors: number;
}

export interface BreadthData {
  date: string;
  advance: number;
  decline: number;
  unchanged: number;
  total_stocks: number;
  ad_ratio: string | null;
  pct_above_200dma: string | null;
  pct_above_50dma: string | null;
  new_52w_highs: number;
  new_52w_lows: number;
}

export interface RegimeData {
  date: string;
  regime: string;
  confidence: string | null;
  breadth_score: string | null;
  momentum_score: string | null;
  volume_score: string | null;
  global_score: string | null;
  fii_score: string | null;
}

export interface BreadthResponse {
  breadth: BreadthData;
  regime: RegimeData;
  meta: Meta;
}

export interface SectorMetrics {
  sector: string;
  stock_count: number;
  avg_rs_composite: string | null;
  avg_rs_momentum: string | null;
  sector_quadrant: string | null;
  pct_above_200dma: string | null;
  pct_above_50dma: string | null;
  pct_above_ema21: string | null;
  avg_rsi_14: string | null;
  pct_rsi_overbought: string | null;
  pct_rsi_oversold: string | null;
  avg_adx: string | null;
  pct_adx_trending: string | null;
  pct_macd_bullish: string | null;
  pct_roc5_positive: string | null;
  avg_beta: string | null;
  avg_sharpe: string | null;
  avg_sortino: string | null;
  avg_volatility_20d: string | null;
  avg_max_dd: string | null;
  avg_calmar: string | null;
  avg_mf_holders: string | null;
  avg_disparity_20: string | null;
}

export interface SectorListResponse {
  sectors: SectorMetrics[];
  meta: Meta;
}

export interface StockSummary {
  id: string;
  symbol: string;
  company_name: string;
  sector: string | null;
  nifty_50: boolean;
  nifty_200: boolean;
  nifty_500: boolean;
  close: string | null;
  rs_composite: string | null;
  rs_momentum: string | null;
  quadrant: string | null;
  rsi_14: string | null;
  adx_14: string | null;
  above_200dma: boolean | null;
  above_50dma: boolean | null;
  macd_histogram: string | null;
  beta_nifty: string | null;
  sharpe_1y: string | null;
  mf_holder_count: number | null;
  cap_category: string | null;
}

export interface SectorGroup {
  sector: string;
  stock_count: number;
  stocks: StockSummary[];
}

export interface UniverseResponse {
  sectors: SectorGroup[];
  meta: Meta;
}

export interface ConvictionPillars {
  rs: {
    rs_composite: string | null;
    rs_momentum: string | null;
    quadrant: string | null;
    benchmark: string;
    explanation: string;
    rs_1w: string | null;
    rs_1m: string | null;
    rs_3m: string | null;
    rs_6m: string | null;
    rs_12m: string | null;
  };
  technical: {
    checks_passing: number;
    checks_total: number;
    checks: { name: string; passing: boolean; value: string | null; detail: string }[];
    explanation: string;
  };
  institutional: {
    mf_holder_count: number | null;
    delivery_vs_avg: string | null;
    explanation: string;
  };
}

export interface StockDeepDive {
  id: string;
  symbol: string;
  company_name: string;
  sector: string | null;
  industry: string | null;
  close: string | null;
  rsi_14: string | null;
  adx_14: string | null;
  above_200dma: boolean | null;
  above_50dma: boolean | null;
  macd_histogram: string | null;
  beta_nifty: string | null;
  sharpe_1y: string | null;
  sortino_1y: string | null;
  max_drawdown_1y: string | null;
  volatility_20d: string | null;
  sma_50: string | null;
  sma_200: string | null;
  cap_category: string | null;
  nifty_50: boolean;
  nifty_200: boolean;
  nifty_500: boolean;
  conviction: ConvictionPillars;
  mf_holder_count: number | null;
}

export interface DeepDiveResponse {
  stock: StockDeepDive;
  meta: Meta;
}

export interface MoverEntry {
  symbol: string;
  company_name: string;
  sector: string | null;
  rs_composite: string | null;
  rs_momentum: string | null;
  quadrant: string | null;
}

export interface MoversResponse {
  gainers: MoverEntry[];
  losers: MoverEntry[];
  meta: Meta;
}

export interface RsHistoryResponse {
  symbol: string;
  benchmark: string;
  data: { date: string; rs_composite: string | null }[];
  meta: Meta;
}

export interface DecisionSummary {
  id: string;
  entity: string;
  entity_type: string;
  decision_type: string;
  rationale: string;
  confidence: string;
  horizon: string;
  horizon_end_date: string;
  status: string;
  source_agent: string | null;
  created_at: string;
  user_action: string | null;
  user_action_at: string | null;
  user_notes: string | null;
}

export interface DecisionListResponse {
  decisions: DecisionSummary[];
  meta: Meta;
}

export interface FindingSummary {
  id: string;
  agent_id: string;
  agent_type: string;
  entity: string | null;
  entity_type: string | null;
  finding_type: string;
  title: string;
  content: string;
  confidence: string | null;
  tags: string[] | null;
  data_as_of: string;
  created_at: string;
}

export interface FindingsListResponse {
  findings: FindingSummary[];
  meta: Meta;
}

export async function getFindings(params?: {
  entity?: string;
  finding_type?: string;
  limit?: number;
}) {
  const qs = new URLSearchParams();
  if (params?.entity) qs.set("entity", params.entity);
  if (params?.finding_type) qs.set("finding_type", params.finding_type);
  if (params?.limit) qs.set("limit", String(params.limit));
  const q = qs.toString();
  return fetchApi<FindingsListResponse>(
    `/api/v1/intelligence/findings${q ? `?${q}` : ""}`
  );
}

// --- MF API (re-exported from api-mf.ts) ------------------------------------

export {
  getMfUniverse,
  getMfCategories,
  getMfFlows,
  getMfFundDeepDive,
  getMfHoldings,
  getMfSectors,
  getMfNavHistory,
  type MFStaleness,
  type MFFund,
  type MFCategoryGroup,
  type MFBroadCategoryGroup,
  type MFUniverseResponse,
  type MFCategoryRow,
  type MFCategoriesResponse,
  type MFFlowRow,
  type MFFlowsResponse,
  type MFFundIdentity,
  type MFFundDailyMetrics,
  type MFPillarPerformance,
  type MFPillarRSStrength,
  type MFPillarFlows,
  type MFPillarHoldingsQuality,
  type MFConvictionPillars,
  type MFSectorExposure,
  type MFTopHolding,
  type MFWeightedTechnicals,
  type MFFundDeepDiveResponse,
  type MFHolding,
  type MFHoldingsResponse,
  type MFFundSector,
  type MFFundSectorsResponse,
  type MFNAVPoint,
  type MFNAVHistoryResponse,
} from "./api-mf";
