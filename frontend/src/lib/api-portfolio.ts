/**
 * Portfolio Management API client for ATLAS Pro shell.
 * Types mirror backend/models/portfolio.py Pydantic models.
 * Decimal fields are serialised as strings by FastAPI.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // ignore parse errors
    }
    throw new Error(detail);
  }
  return res.json();
}

// --- Enums ---

export type PortfolioType = "cams_import" | "manual" | "model";
export type OwnerType = "pms" | "ria_client" | "retail";
export type MappingStatus = "mapped" | "pending" | "manual_override";
export type OptimizationModel = "mean_variance" | "hrp";
export type RiskProfile = "conservative" | "moderate" | "aggressive";

// --- Holding types ---

export interface HoldingResponse {
  id: string;
  portfolio_id: string;
  scheme_name: string;
  folio_number: string | null;
  units: string;
  nav: string | null;
  mstar_id: string | null;
  mapping_confidence: string | null;
  mapping_status: MappingStatus;
  current_value: string | null;
  cost_value: string | null;
  created_at: string;
  updated_at: string;
}

// --- Portfolio types ---

export interface PortfolioResponse {
  id: string;
  name: string | null;
  portfolio_type: PortfolioType;
  owner_type: OwnerType;
  user_id: string | null;
  holdings: HoldingResponse[];
  analysis_cache: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface PortfolioListResponse {
  portfolios: PortfolioResponse[];
  count: number;
  data_as_of: string;
}

// --- Analysis provenance ---

export interface AnalysisProvenance {
  source_table: string;
  formula: string;
}

// --- Per-holding analysis ---

export interface HoldingAnalysis {
  holding_id: string;
  mstar_id: string;
  scheme_name: string;
  units: string;
  nav: string | null;
  current_value: string | null;
  weight_pct: string | null;

  // Returns
  return_1m: string | null;
  return_3m: string | null;
  return_6m: string | null;
  return_1y: string | null;
  return_3y: string | null;
  return_5y: string | null;

  // RS / momentum
  rs_composite: string | null;
  rs_momentum_28d: string | null;
  quadrant: string | null;

  // Derived metrics
  sharpe_ratio: string | null;
  sortino_ratio: string | null;
  alpha: string | null;
  beta: string | null;

  // Weighted technicals
  weighted_rsi: string | null;
  weighted_breadth_pct_above_200dma: string | null;
  weighted_macd_bullish_pct: string | null;

  // Sectors
  top_sectors: Array<Record<string, unknown>>;

  // Provenance
  provenance: Record<string, AnalysisProvenance>;
}

// --- Portfolio-level analysis ---

export interface PortfolioLevelAnalysis {
  total_value: string;
  total_cost: string | null;
  holdings_count: number;
  mapped_count: number;
  unmapped_count: number;

  weighted_rs: string | null;
  sector_weights: Record<string, string>;
  quadrant_distribution: Record<string, number>;

  weighted_sharpe: string | null;
  weighted_sortino: string | null;
  weighted_beta: string | null;

  overlap_pairs: Array<Record<string, unknown>>;
  provenance: Record<string, AnalysisProvenance>;
}

// --- Full analysis response ---

export interface PortfolioFullAnalysisResponse {
  portfolio_id: string;
  portfolio_name: string | null;
  data_as_of: string;
  computed_at: string;

  holdings: HoldingAnalysis[];
  portfolio: PortfolioLevelAnalysis;
  unavailable: Array<Record<string, unknown>>;
  rs_data_available: boolean;
}

// --- Brinson attribution types ---

export interface BrinsonCategoryEffect {
  category_name: string;
  portfolio_weight: string;
  benchmark_weight: string;
  portfolio_return: string | null;
  benchmark_return: string | null;
  allocation_effect: string | null;
  selection_effect: string | null;
  interaction_effect: string | null;
  total_effect: string | null;
  holding_count: number;
  provenance: AnalysisProvenance;
}

export interface BrinsonAttributionSummary {
  total_allocation_effect: string | null;
  total_selection_effect: string | null;
  total_interaction_effect: string | null;
  total_active_return: string | null;
  benchmark_total_return: string | null;
  formula: string;
  tolerance: string;
}

export interface PortfolioAttributionResponse {
  portfolio_id: string;
  portfolio_name: string | null;
  data_as_of: string;
  computed_at: string;
  categories: BrinsonCategoryEffect[];
  summary: BrinsonAttributionSummary;
  returns_available: boolean;
  benchmark_description: string;
  unavailable_holdings: Array<Record<string, unknown>>;
}

// --- Optimization types ---

export interface SEBIConstraint {
  constraint_id: string;
  constraint_type: string;
  description: string;
  value: string;
  is_binding: boolean;
  is_violated: boolean;
}

export interface OptimizedWeight {
  mstar_id: string;
  scheme_name: string;
  current_weight: string;
  optimized_weight: string;
  weight_change: string;
  provenance: AnalysisProvenance;
}

export interface OptimizationResult {
  model: OptimizationModel;
  weights: OptimizedWeight[];
  expected_return: string | null;
  expected_risk: string | null;
  sharpe_ratio: string | null;
  constraints_applied: SEBIConstraint[];
  solver_status: string;
  computation_time_ms: number | null;
}

export interface PortfolioOptimizationResponse {
  portfolio_id: string;
  portfolio_name: string | null;
  data_as_of: string;
  computed_at: string;
  models: OptimizationResult[];
  candidate_count: number;
  excluded_funds: Array<Record<string, unknown>>;
  provenance: Record<string, AnalysisProvenance>;
}

// --- Import result ---

export interface PortfolioImportResult {
  portfolio_id: string;
  portfolio_name: string | null;
  holdings: HoldingResponse[];
  needs_review: HoldingResponse[];
  mapped_count: number;
  pending_count: number;
  total_count: number;
  data_as_of: string;
}

// --- API functions ---

export async function listPortfolios(
  userId?: string
): Promise<PortfolioListResponse> {
  const params = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
  return fetchApi<PortfolioListResponse>(`/api/v1/portfolio/${params}`);
}

export async function getPortfolio(id: string): Promise<PortfolioResponse> {
  return fetchApi<PortfolioResponse>(`/api/v1/portfolio/${id}`);
}

export async function getPortfolioAnalysis(
  id: string,
  dataAsOf?: string
): Promise<PortfolioFullAnalysisResponse> {
  const params = dataAsOf
    ? `?data_as_of=${encodeURIComponent(dataAsOf)}`
    : "";
  return fetchApi<PortfolioFullAnalysisResponse>(
    `/api/v1/portfolio/${id}/analysis${params}`
  );
}

export async function getPortfolioAttribution(
  id: string,
  dataAsOf?: string
): Promise<PortfolioAttributionResponse> {
  const params = dataAsOf
    ? `?data_as_of=${encodeURIComponent(dataAsOf)}`
    : "";
  return fetchApi<PortfolioAttributionResponse>(
    `/api/v1/portfolio/${id}/attribution${params}`
  );
}

export async function getPortfolioOptimize(
  id: string,
  opts?: {
    riskProfile?: RiskProfile;
    dataAsOf?: string;
  }
): Promise<PortfolioOptimizationResponse> {
  const p = new URLSearchParams();
  if (opts?.riskProfile) p.set("risk_profile", opts.riskProfile);
  if (opts?.dataAsOf) p.set("data_as_of", opts.dataAsOf);
  const qs = p.toString() ? `?${p.toString()}` : "";
  return fetchApi<PortfolioOptimizationResponse>(
    `/api/v1/portfolio/${id}/optimize${qs}`
  );
}

export async function importCamsPdf(
  file: File,
  password?: string,
  name?: string
): Promise<PortfolioImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  if (password) formData.append("password", password);
  if (name) formData.append("portfolio_name", name);

  const res = await fetch(`${API_BASE}/api/v1/portfolio/import-cams`, {
    method: "POST",
    body: formData,
    // No Content-Type header — browser sets multipart/form-data with boundary
  });

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // ignore parse errors
    }
    throw new Error(detail);
  }
  return res.json();
}
