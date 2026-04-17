/**
 * Watchlists API client for ATLAS Pro shell (V6-8).
 * Types mirror backend/routes/watchlists.py Pydantic response models.
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
  // 204 No Content has no body
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json();
}

// --- Types ---

export interface WatchlistItem {
  id: string;
  name: string;
  symbols: string[];
  tv_synced: boolean;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface WatchlistListResponse {
  watchlists: WatchlistItem[];
  total: number;
}

// --- API functions ---

export async function getWatchlists(): Promise<WatchlistListResponse> {
  return fetchApi<WatchlistListResponse>("/api/v1/watchlists/");
}

export async function createWatchlist(
  name: string,
  symbols: string[]
): Promise<WatchlistItem> {
  return fetchApi<WatchlistItem>("/api/v1/watchlists/", {
    method: "POST",
    body: JSON.stringify({ name, symbols }),
  });
}

export async function deleteWatchlist(id: string): Promise<void> {
  await fetchApi<void>(`/api/v1/watchlists/${id}`, {
    method: "DELETE",
  });
}
