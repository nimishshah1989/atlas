"use client";

import useSWR, { type SWRConfiguration } from "swr";
import { apiFetch, AtlasMeta, AtlasApiError } from "@/lib/api";

export const STALENESS_THRESHOLDS: Record<string, number> = {
  intraday:     3600,
  eod_breadth:  21600,
  daily_regime: 86400,
  fundamentals: 604800,
  events:       604800,
  holdings:     604800,
  system:       21600,
};

type DataState = "loading" | "ready" | "stale" | "empty" | "error";

export interface UseAtlasDataResult<T> {
  data: T | null;
  meta: AtlasMeta | null;
  state: DataState;
  error: AtlasApiError | null;
  isLoading: boolean;
  mutate: () => void;
}

function hasData(json: unknown): boolean {
  if (!json || typeof json !== "object") return false;
  const wrapper = json as Record<string, unknown>;
  const inner = wrapper.data;

  // No data field at all
  if (inner === undefined || inner === null) return false;

  // Array-type data: non-empty means data
  if (Array.isArray(inner)) return inner.length > 0;

  // Object-type data: check well-known list fields first
  if (typeof inner === "object") {
    const d = inner as Record<string, unknown>;
    if (Array.isArray(d.records) && d.records.length > 0) return true;
    if (Array.isArray(d.series) && d.series.length > 0) return true;
    if (Array.isArray(d.divergences) && d.divergences.length > 0) return true;
    if (Array.isArray(d.events) && d.events.length > 0) return true;
    if (Array.isArray(d.sectors) && d.sectors.length > 0) return true;
    if (Array.isArray(d.gainers) && d.gainers.length > 0) return true;
    // Generic non-empty object with at least one real data key
    const keys = Object.keys(d).filter(k => k !== "_meta" && k !== "meta");
    return keys.length > 0;
  }

  return false;
}

function computeState<T>(
  swrData: { data: T; _meta: AtlasMeta } | undefined,
  swrError: unknown,
  isValidating: boolean,
  dataClass?: string
): DataState {
  if (swrError) return "error";
  if (!swrData && isValidating) return "loading";
  if (!swrData) return "loading";

  const meta = swrData._meta;

  // Known-sparse guard — null-safe
  if (meta && meta.insufficient_data === true) return "empty";

  // Check for data presence
  if (!hasData(swrData)) return "empty";

  // Staleness check — null-safe
  if (dataClass && meta && typeof meta.staleness_seconds === "number") {
    const threshold = STALENESS_THRESHOLDS[dataClass];
    if (typeof threshold === "number" && meta.staleness_seconds > threshold) {
      return "stale";
    }
  }

  return "ready";
}

export function useAtlasData<T>(
  endpoint: string | null,
  params?: Record<string, string | number | boolean | undefined>,
  options?: SWRConfiguration & { dataClass?: string }
): UseAtlasDataResult<T> {
  const { dataClass, ...swrOptions } = options ?? {};

  // Build SWR key — null suspends the fetch
  const key = endpoint
    ? [endpoint, JSON.stringify(params ?? {})]
    : null;

  const fetcher = async ([ep, p]: [string, string]) => {
    const parsedParams = p
      ? (JSON.parse(p) as Record<string, string | number | boolean | undefined>)
      : undefined;
    const raw = await apiFetch<Record<string, unknown>>(ep, parsedParams as never);
    const r = raw as Record<string, unknown>;
    // Normalize: if response has _meta but no `data` key, wrap the whole response.
    if (!("data" in r)) {
      const m = (r._meta ?? r.meta ?? { data_as_of: null, staleness_seconds: 0, source: "api" }) as AtlasMeta;
      return { data: raw as unknown as T, _meta: m };
    }
    return raw as unknown as { data: T; _meta: AtlasMeta };
  };

  const { data: swrData, error: swrError, isValidating, mutate } = useSWR<
    { data: T; _meta: AtlasMeta },
    unknown
  >(key, fetcher, swrOptions);

  const state = computeState<T>(swrData, swrError, isValidating, dataClass);

  const error = swrError instanceof AtlasApiError
    ? swrError
    : swrError instanceof Error
    ? new AtlasApiError("UNKNOWN", swrError.message)
    : swrError
    ? new AtlasApiError("UNKNOWN", String(swrError))
    : null;

  return {
    data: swrData?.data ?? null,
    meta: swrData?._meta ?? null,
    state,
    error,
    isLoading: state === "loading",
    mutate: () => { mutate(); },
  };
}
