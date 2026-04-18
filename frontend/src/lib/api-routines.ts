/**
 * TypeScript client for GET /api/v1/system/routines (V11-0 routine visibility).
 * Matches RoutinesResponse Pydantic model exactly.
 */

// Resolve backend base URL — loopback on SSR, public proxy path in browser.
const BACKEND_BASE =
  typeof window === "undefined"
    ? "http://localhost:8010/api/v1/system"
    : "/api/v1/system";

// ---------------------------------------------------------------------------
// Response interfaces
// ---------------------------------------------------------------------------

export interface RoutineLastRun {
  run_id: string | null;
  status: string | null;        // "success" | "partial" | "failed" | null
  rows_fetched: number | null;
  rows_inserted: number | null;
  rows_updated: number | null;
  duration_ms: number | null;
  error_message: string | null;
  ran_at: string | null;        // ISO datetime string (IST-aware)
}

export interface RoutineEntry {
  id: string;
  tables: string[];
  cadence: string;
  schedule: string | null;
  source: string | null;
  manifest_status: string;      // "live" | "partial" | "missing" | "planned"
  is_new: boolean;
  priority: string | null;      // "P1" | "P2" | "P3" for new routines
  sla_freshness_hours: number | null;
  last_run: RoutineLastRun | null;
  sla_breached: boolean;
  display_status: string;       // "live" | "partial" | "sla_breached" | "missing" | "planned" | "unknown"
}

export interface RoutinesResponse {
  routines: RoutineEntry[];
  total: number;
  live_count: number;
  sla_breached_count: number;
  data_available: boolean;
  as_of: string;                // ISO datetime string
}

// ---------------------------------------------------------------------------
// Fetch wrapper
// ---------------------------------------------------------------------------

export async function getRoutines(): Promise<RoutinesResponse> {
  const res = await fetch(`${BACKEND_BASE}/routines`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`routines HTTP ${res.status}`);
  }
  return res.json() as Promise<RoutinesResponse>;
}
