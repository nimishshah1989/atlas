/**
 * Thin fetch wrappers for the 4 ATLAS system endpoints.
 * All interfaces match PRD §7 exactly.
 * Use cache: 'no-store' on all fetches.
 */

const BACKEND_BASE = "http://localhost:8010/api/v1/system";

// ---------------------------------------------------------------------------
// Response interfaces — match PRD §7 byte-for-byte
// ---------------------------------------------------------------------------

export interface HeartbeatResponse {
  memory_md_mtime: string | null;
  wiki_index_mtime: string | null;
  state_db_mtime: string | null;
  last_chunk_done_at: string | null;
  last_chunk_id: string | null;
  last_quality_run_at: string | null;
  last_quality_score: number | null;
  backend_uptime_seconds: number;
  as_of: string;
  last_smoke_run_at: string | null;
  last_smoke_result: string | null;
  last_smoke_summary: string | null;
}

export type CheckEnum = "ok" | "fail" | "slow-skipped" | "error";
export type VersionStatusEnum =
  | "DONE"
  | "IN_PROGRESS"
  | "PENDING"
  | "PLANNED"
  | "BLOCKED"
  | "FAILED"
  | "EMPTY";

export interface StepResponse {
  id: string;
  text: string;
  check: CheckEnum;
  detail: string;
}

export interface ChunkResponse {
  id: string;
  title: string;
  status: string;
  attempts: number;
  updated_at: string | null;
  steps: StepResponse[];
}

export interface RollupResponse {
  done: number;
  total: number;
  pct: number;
}

export interface DemoGateResponse {
  url: string;
  walkthrough: string[];
}

export interface VersionResponse {
  id: string;
  title: string;
  goal: string;
  status: VersionStatusEnum;
  rollup: RollupResponse;
  chunks: ChunkResponse[];
  demo_gate?: DemoGateResponse | null;
}

export interface RoadmapResponse {
  as_of: string;
  versions: VersionResponse[];
}

export interface QualityCheck {
  check_id: string;
  name: string;
  score: number;
  max_score: number;
  evidence: string;
  plain_english: string;
  fix: string;
  severity: string;
  status: string;
}

export interface QualityDimension {
  dimension: string;
  score: number;
  weight: number;
  checks?: QualityCheck[];
}

export interface QualityScoresData {
  overall: number;
  dimensions: QualityDimension[];
}

export interface QualityResponse {
  as_of: string | null;
  scores: QualityScoresData | null;
}

export interface LogsTailResponse {
  file: string;
  lines: string[];
  as_of: string;
}

// ---------------------------------------------------------------------------
// Fetch wrappers
// ---------------------------------------------------------------------------

export async function getHeartbeat(): Promise<HeartbeatResponse> {
  const res = await fetch(`${BACKEND_BASE}/heartbeat`, { cache: "no-store" });
  if (!res.ok) throw new Error(`heartbeat HTTP ${res.status}`);
  return res.json() as Promise<HeartbeatResponse>;
}

export async function getRoadmap(): Promise<RoadmapResponse> {
  const res = await fetch(`${BACKEND_BASE}/roadmap`, { cache: "no-store" });
  if (!res.ok) throw new Error(`roadmap HTTP ${res.status}`);
  return res.json() as Promise<RoadmapResponse>;
}

export async function getQuality(): Promise<QualityResponse> {
  const res = await fetch(`${BACKEND_BASE}/quality`, { cache: "no-store" });
  if (!res.ok) throw new Error(`quality HTTP ${res.status}`);
  return res.json() as Promise<QualityResponse>;
}

export async function getLogsTail(lines = 200): Promise<LogsTailResponse> {
  const res = await fetch(`${BACKEND_BASE}/logs/tail?lines=${lines}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`logs/tail HTTP ${res.status}`);
  return res.json() as Promise<LogsTailResponse>;
}
