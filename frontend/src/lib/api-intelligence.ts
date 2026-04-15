/**
 * Intelligence API client for ATLAS Pro shell.
 * Types mirror backend/models/intelligence.py Pydantic models.
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

export interface FindingSummary {
  id: string;
  agent_id: string;
  agent_type: string;
  entity: string | null;
  entity_type: string | null;
  finding_type: string;
  title: string;
  content: string;
  confidence: string | null; // Decimal serialized as string
  evidence: Record<string, unknown> | null;
  tags: string[] | null;
  data_as_of: string;
  expires_at: string | null;
  is_validated: boolean;
  created_at: string;
  updated_at: string;
}

export interface IntelligenceSearchResponse {
  findings: FindingSummary[];
  data: FindingSummary[];
  _meta: { record_count: number; query_ms: number };
}

export interface IntelligenceListResponse {
  findings: FindingSummary[];
  data: FindingSummary[];
  _meta: { record_count: number; query_ms: number };
}

// --- API functions ---

export async function searchIntelligence(params: {
  q: string;
  entity?: string;
  entity_type?: string;
  finding_type?: string;
  min_confidence?: string;
  max_age_hours?: number;
  top_k?: number;
}): Promise<IntelligenceSearchResponse> {
  const p = new URLSearchParams();
  p.set("q", params.q);
  if (params.entity) p.set("entity", params.entity);
  if (params.entity_type) p.set("entity_type", params.entity_type);
  if (params.finding_type) p.set("finding_type", params.finding_type);
  if (params.min_confidence != null)
    p.set("min_confidence", params.min_confidence);
  if (params.max_age_hours != null)
    p.set("max_age_hours", String(params.max_age_hours));
  if (params.top_k != null) p.set("top_k", String(params.top_k));
  return fetchApi<IntelligenceSearchResponse>(
    `/api/v1/intelligence/search?${p.toString()}`
  );
}

export async function listFindings(params?: {
  entity?: string;
  entity_type?: string;
  finding_type?: string;
  agent_id?: string;
  min_confidence?: string;
  limit?: number;
  offset?: number;
}): Promise<IntelligenceListResponse> {
  const p = new URLSearchParams();
  if (params?.entity) p.set("entity", params.entity);
  if (params?.entity_type) p.set("entity_type", params.entity_type);
  if (params?.finding_type) p.set("finding_type", params.finding_type);
  if (params?.agent_id) p.set("agent_id", params.agent_id);
  if (params?.min_confidence != null)
    p.set("min_confidence", params.min_confidence);
  if (params?.limit != null) p.set("limit", String(params.limit));
  if (params?.offset != null) p.set("offset", String(params.offset));
  const qs = p.toString() ? `?${p.toString()}` : "";
  return fetchApi<IntelligenceListResponse>(
    `/api/v1/intelligence/findings${qs}`
  );
}
