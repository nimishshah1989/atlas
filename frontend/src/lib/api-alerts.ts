/**
 * Alerts API client for ATLAS Pro shell (V6-8).
 * Types mirror backend/routes/alerts.py Pydantic response models.
 * Decimal fields serialised as strings by FastAPI.
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

export interface AlertItem {
  id: number;
  source: string;
  symbol: string | null;
  instrument_id: string | null;
  alert_type: string | null;
  message: string | null;
  metadata: Record<string, unknown> | null;
  rs_at_alert: string | null;
  quadrant_at_alert: string | null;
  is_read: boolean;
  created_at: string;
}

export interface AlertsMeta {
  returned: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface AlertsResponse {
  data: AlertItem[];
  _meta: AlertsMeta;
}

export interface AlertReadResponse {
  id: number;
  is_read: boolean;
  message: string;
}

// --- API functions ---

export interface GetAlertsParams {
  source?: string;
  unread?: boolean;
  limit?: number;
  offset?: number;
}

export async function getAlerts(
  params?: GetAlertsParams
): Promise<AlertsResponse> {
  const p = new URLSearchParams();
  if (params?.source) p.set("source", params.source);
  if (params?.unread != null) p.set("unread", String(params.unread));
  if (params?.limit != null) p.set("limit", String(params.limit));
  if (params?.offset != null) p.set("offset", String(params.offset));
  const qs = p.toString() ? `?${p.toString()}` : "";
  return fetchApi<AlertsResponse>(`/api/alerts${qs}`);
}

export async function markAlertRead(id: number): Promise<AlertReadResponse> {
  return fetchApi<AlertReadResponse>(`/api/alerts/${id}/read`, {
    method: "POST",
  });
}
