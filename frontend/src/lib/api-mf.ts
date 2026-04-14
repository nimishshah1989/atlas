/**
 * MF (Mutual Fund) API client for ATLAS Pro shell.
 * Types mirror backend/models/mf.py Pydantic models.
 * Decimal fields are serialised as strings by FastAPI.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

// --- Functions ---------------------------------------------------------------

export async function getMfUniverse() {
  return fetchApi<MFUniverseResponse>("/api/v1/mf/universe");
}

export async function getMfCategories() {
  return fetchApi<MFCategoriesResponse>("/api/v1/mf/categories");
}

export async function getMfFlows(category?: string) {
  const q = category ? `?category=${encodeURIComponent(category)}` : "";
  return fetchApi<MFFlowsResponse>(`/api/v1/mf/flows${q}`);
}

export async function getMfFundDeepDive(mstarId: string) {
  return fetchApi<MFFundDeepDiveResponse>(`/api/v1/mf/${mstarId}`);
}

export async function getMfHoldings(mstarId: string) {
  return fetchApi<MFHoldingsResponse>(`/api/v1/mf/${mstarId}/holdings`);
}

export async function getMfSectors(mstarId: string) {
  return fetchApi<MFFundSectorsResponse>(`/api/v1/mf/${mstarId}/sectors`);
}

export async function getMfNavHistory(mstarId: string) {
  return fetchApi<MFNAVHistoryResponse>(`/api/v1/mf/${mstarId}/nav-history`);
}

export async function getMfOverlap(fundA: string, fundB: string) {
  return fetchApi<MFOverlapResponse>(
    `/api/v1/mf/overlap?funds=${encodeURIComponent(fundA)},${encodeURIComponent(fundB)}`
  );
}

// --- Types -------------------------------------------------------------------

export interface MFStaleness {
  source: string;
  age_minutes: number;
  flag: "FRESH" | "STALE" | "EXPIRED";
}

export interface MFFund {
  mstar_id: string;
  fund_name: string;
  amc_name: string;
  category_name: string;
  broad_category: string;
  nav: string | null;
  nav_date: string | null;
  rs_composite: string | null;
  rs_momentum_28d: string | null;
  quadrant: string | null;
  manager_alpha: string | null;
  expense_ratio: string | null;
  is_index_fund: boolean;
  primary_benchmark: string | null;
}

export interface MFCategoryGroup {
  name: string;
  funds: MFFund[];
}

export interface MFBroadCategoryGroup {
  name: string;
  categories: MFCategoryGroup[];
}

export interface MFUniverseResponse {
  broad_categories: MFBroadCategoryGroup[];
  data_as_of: string;
  staleness: MFStaleness;
}

export interface MFCategoryRow {
  category_name: string;
  broad_category: string;
  fund_count: number;
  avg_rs_composite: string | null;
  quadrant_distribution: Record<string, number>;
  net_flow_cr: string | null;
  sip_flow_cr: string | null;
  total_aum_cr: string | null;
  manager_alpha_p50: string | null;
  manager_alpha_p90: string | null;
}

export interface MFCategoriesResponse {
  categories: MFCategoryRow[];
  data_as_of: string;
  staleness: MFStaleness;
}

export interface MFFlowRow {
  month_date: string;
  category: string;
  net_flow_cr: string | null;
  gross_inflow_cr: string | null;
  gross_outflow_cr: string | null;
  aum_cr: string | null;
  sip_flow_cr: string | null;
  sip_accounts: number | null;
  folios: number | null;
}

export interface MFFlowsResponse {
  flows: MFFlowRow[];
  data_as_of: string;
  staleness: MFStaleness;
}

export interface MFFundIdentity {
  mstar_id: string;
  fund_name: string;
  amc_name: string;
  category_name: string;
  broad_category: string;
  primary_benchmark: string | null;
  inception_date: string | null;
  is_index_fund: boolean;
}

export interface MFFundDailyMetrics {
  nav: string | null;
  nav_date: string | null;
  aum_cr: string | null;
  expense_ratio: string | null;
  return_1m: string | null;
  return_3m: string | null;
  return_6m: string | null;
  return_1y: string | null;
  return_3y: string | null;
  return_5y: string | null;
}

export interface MFPillarPerformance {
  manager_alpha: string | null;
  information_ratio: string | null;
  capture_up: string | null;
  capture_down: string | null;
  explanation: string;
}

export interface MFPillarRSStrength {
  rs_composite: string | null;
  rs_momentum_28d: string | null;
  quadrant: string | null;
  explanation: string;
}

export interface MFPillarFlows {
  net_flow_cr_3m: string | null;
  sip_flow_cr_3m: string | null;
  folio_growth_pct: string | null;
  explanation: string;
}

export interface MFPillarHoldingsQuality {
  holdings_avg_rs: string | null;
  pct_above_200dma: string | null;
  concentration_top10_pct: string | null;
  explanation: string;
}

export interface MFConvictionPillars {
  performance: MFPillarPerformance;
  rs_strength: MFPillarRSStrength;
  flows: MFPillarFlows;
  holdings_quality: MFPillarHoldingsQuality;
}

export interface MFSectorExposure {
  top_sector: string | null;
  top_sector_weight_pct: string | null;
  sector_count: number;
}

export interface MFTopHolding {
  symbol: string;
  holding_name: string;
  weight_pct: string;
}

export interface MFWeightedTechnicals {
  weighted_rsi: string | null;
  weighted_breadth_pct_above_200dma: string | null;
  weighted_macd_bullish_pct: string | null;
  as_of_date: string | null;
}

export interface MFFundDeepDiveResponse {
  identity: MFFundIdentity;
  daily: MFFundDailyMetrics;
  pillars: MFConvictionPillars;
  sector_exposure: MFSectorExposure;
  top_holdings: MFTopHolding[];
  weighted_technicals: MFWeightedTechnicals;
  data_as_of: string;
  staleness: MFStaleness;
  inactive: boolean | null;
}

export interface MFHolding {
  instrument_id: string;
  symbol: string;
  holding_name: string;
  weight_pct: string;
  shares_held: string | null;
  market_value: string | null;
  sector: string | null;
  rs_composite: string | null;
  above_200dma: boolean | null;
}

export interface MFHoldingsResponse {
  holdings: MFHolding[];
  as_of_date: string;
  coverage_pct: string;
  warnings: string[];
}

export interface MFFundSector {
  sector: string;
  weight_pct: string;
  stock_count: number;
  sector_rs_composite: string | null;
}

export interface MFFundSectorsResponse {
  sectors: MFFundSector[];
  as_of_date: string;
}

export interface MFNAVPoint {
  nav_date: string;
  nav: string;
}

export interface MFNAVHistoryResponse {
  mstar_id: string;
  points: MFNAVPoint[];
  coverage_gap_days: number;
  data_as_of: string;
  staleness: MFStaleness;
}

export interface MFOverlapHolding {
  instrument_id: string;
  symbol: string;
  weight_a: string;
  weight_b: string;
}

export interface MFOverlapResponse {
  fund_a: string;
  fund_b: string;
  overlap_pct: string;
  common_holdings: MFOverlapHolding[];
  data_as_of: string;
  staleness: MFStaleness;
}
