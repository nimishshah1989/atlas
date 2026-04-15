/**
 * Global Intelligence API client for ATLAS Pro shell.
 * Types mirror backend/models/global_intel.py Pydantic models.
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

// --- Types ---

export interface Meta {
  record_count: number;
  query_ms: number;
  stale?: boolean;
  data_as_of?: string | null;
}

// Briefing
export interface BriefingDetail {
  id: number;
  date: string;
  scope: string;
  scope_key: string | null;
  headline: string;
  narrative: string;
  key_signals: unknown;
  theses: unknown;
  patterns: unknown;
  india_implication: string | null;
  risk_scenario: string | null;
  conviction: string | null;
  model_used: string | null;
  staleness_flags: Record<string, unknown> | null;
  generated_at: string;
}

export interface BriefingResponse {
  briefing: BriefingDetail | null;
  data: BriefingDetail | null;
  meta: Meta;
  _meta: Meta;
}

// Macro Ratios
export interface MacroSparkItem {
  date: string;
  value: string | null;
}

export interface MacroRatioItem {
  ticker: string;
  name: string | null;
  unit: string | null;
  latest_value: string | null;
  latest_date: string | null;
  sparkline: MacroSparkItem[];
}

export interface MacroRatiosResponse {
  ratios: MacroRatioItem[];
  data: MacroRatioItem[];
  meta: Meta;
  _meta: Meta;
}

// RS Heatmap
export interface GlobalRSEntry {
  entity_id: string;
  name: string | null;
  instrument_type: string | null;
  country: string | null;
  rs_composite: string | null;
  rs_1m: string | null;
  rs_3m: string | null;
  rs_date: string | null;
  close: string | null;
  price_date: string | null;
}

export interface RSHeatmapResponse {
  heatmap: GlobalRSEntry[];
  data: GlobalRSEntry[];
  meta: Meta;
  _meta: Meta;
}

// Regime
export interface RegimeSummary {
  date: string | null;
  regime: string | null;
  confidence: string | null;
  breadth_score: string | null;
  momentum_score: string | null;
  volume_score: string | null;
  global_score: string | null;
  fii_score: string | null;
}

export interface BreadthSummary {
  date: string | null;
  advance: number | null;
  decline: number | null;
  unchanged: number | null;
  total_stocks: number | null;
  ad_ratio: string | null;
  pct_above_200dma: string | null;
  pct_above_50dma: string | null;
  new_52w_highs: number | null;
  new_52w_lows: number | null;
}

export interface GlobalRegimeResponse {
  regime: RegimeSummary | null;
  breadth: BreadthSummary | null;
  data: { regime: RegimeSummary | null; breadth: BreadthSummary | null };
  meta: Meta;
  _meta: Meta;
}

// Patterns
export interface PatternFinding {
  id: string;
  finding_type: string;
  title: string;
  content: string;
  entity: string | null;
  entity_type: string | null;
  confidence: string | null;
  tags: string[] | null;
  data_as_of: string;
  created_at: string;
}

export interface GlobalPatternsResponse {
  patterns: PatternFinding[];
  data: PatternFinding[];
  meta: Meta;
  _meta: Meta;
}

// --- API functions ---

export async function getGlobalBriefing(): Promise<BriefingResponse> {
  return fetchApi<BriefingResponse>("/api/v1/global/briefing");
}

export async function getMacroRatios(
  tickers?: string
): Promise<MacroRatiosResponse> {
  const p = new URLSearchParams();
  if (tickers) p.set("tickers", tickers);
  const qs = p.toString() ? `?${p.toString()}` : "";
  return fetchApi<MacroRatiosResponse>(`/api/v1/global/ratios${qs}`);
}

export async function getGlobalRSHeatmap(): Promise<RSHeatmapResponse> {
  return fetchApi<RSHeatmapResponse>("/api/v1/global/rs-heatmap");
}

export async function getGlobalRegime(): Promise<GlobalRegimeResponse> {
  return fetchApi<GlobalRegimeResponse>("/api/v1/global/regime");
}

export async function getGlobalPatterns(
  findingType?: string,
  limit?: number
): Promise<GlobalPatternsResponse> {
  const p = new URLSearchParams();
  if (findingType) p.set("finding_type", findingType);
  if (limit != null) p.set("limit", String(limit));
  const qs = p.toString() ? `?${p.toString()}` : "";
  return fetchApi<GlobalPatternsResponse>(`/api/v1/global/patterns${qs}`);
}
