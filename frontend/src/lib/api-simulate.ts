/**
 * Simulation Engine API client for ATLAS Pro shell.
 * Types mirror backend/models/simulation.py Pydantic models.
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

// --- Enums ---------------------------------------------------------------

export type SignalType =
  | "breadth"
  | "mcclellan"
  | "rs"
  | "pe"
  | "regime"
  | "sector_rs"
  | "mcclellan_summation"
  | "combined";

export type CombineLogic = "AND" | "OR";

export type TransactionAction = "sip_buy" | "lumpsum_buy" | "sell" | "redeploy";

// --- Config types --------------------------------------------------------

export interface SimulationParameters {
  sip_amount: string;
  lumpsum_amount: string;
  buy_level: string;
  sell_level: string;
  reentry_level?: string | null;
  sell_pct: string;
  redeploy_pct: string;
  cooldown_days: number;
}

export interface CombinedSignalConfig {
  signal_a: SignalType;
  signal_b: SignalType;
  logic: CombineLogic;
}

export interface SimulationConfig {
  signal: SignalType;
  instrument: string;
  instrument_type: string;
  parameters: SimulationParameters;
  start_date: string;
  end_date: string;
  combined_config?: CombinedSignalConfig | null;
}

// --- Result types --------------------------------------------------------

export interface SimulationSummary {
  total_invested: string;
  final_value: string;
  xirr: string;
  cagr: string;
  vs_plain_sip: string;
  vs_benchmark: string;
  alpha: string;
  max_drawdown: string;
  sharpe: string;
  sortino: string;
}

export interface TaxDetail {
  stcg_tax: string;
  ltcg_tax: string;
  cess: string;
  total_tax: string;
}

export interface TaxSummary {
  stcg: string;
  ltcg: string;
  total_tax: string;
  post_tax_xirr: string;
  unrealized: string;
}

export interface DailyValue {
  date: string;
  nav: string;
  units: string;
  fv: string;
  liquid: string;
  total: string;
}

export interface TransactionRecord {
  date: string;
  action: TransactionAction;
  amount: string;
  nav: string;
  units: string;
  tax_detail?: TaxDetail | null;
}

export interface SimulationResult {
  summary: SimulationSummary;
  daily_values: DailyValue[];
  transactions: TransactionRecord[];
  tax_summary: TaxSummary;
  tear_sheet_url?: string | null;
  data_as_of: string;
}

// --- Request/Response types ----------------------------------------------

export interface SimulationRunResponse {
  result: SimulationResult;
  data_as_of: string;
  staleness: string;
}

export interface SimulationSaveResponse {
  id: string;
  name?: string | null;
  created_at: string;
}

export interface SimulationListItem {
  id: string;
  name?: string | null;
  config: SimulationConfig;
  created_at: string;
  is_auto_loop: boolean;
}

export interface SimulationListResponse {
  simulations: SimulationListItem[];
  count: number;
  data_as_of: string;
}

export interface SimulationDetailResponse {
  id: string;
  name?: string | null;
  config: SimulationConfig;
  result: SimulationResult;
  created_at: string;
  is_auto_loop: boolean;
  auto_loop_cron?: string | null;
  last_auto_run?: string | null;
  data_as_of: string;
}

// --- API functions -------------------------------------------------------

export async function runSimulation(
  config: SimulationConfig
): Promise<SimulationRunResponse> {
  return fetchApi<SimulationRunResponse>("/api/v1/simulate/run", {
    method: "POST",
    body: JSON.stringify({ config }),
  });
}

export async function saveSimulation(
  name: string | null,
  config: SimulationConfig,
  is_auto_loop = false,
  auto_loop_cron?: string | null
): Promise<SimulationSaveResponse> {
  return fetchApi<SimulationSaveResponse>("/api/v1/simulate/save", {
    method: "POST",
    body: JSON.stringify({ name, config, is_auto_loop, auto_loop_cron }),
  });
}

export async function listSimulations(): Promise<SimulationListResponse> {
  return fetchApi<SimulationListResponse>("/api/v1/simulate/");
}

export async function getSimulation(
  id: string
): Promise<SimulationDetailResponse> {
  return fetchApi<SimulationDetailResponse>(`/api/v1/simulate/${id}`);
}

export async function deleteSimulation(id: string): Promise<void> {
  await fetchApi<Record<string, unknown>>(`/api/v1/simulate/${id}`, {
    method: "DELETE",
  });
}
