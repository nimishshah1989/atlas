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
  const obj = json as Record<string, unknown>;
  return (
    (Array.isArray(obj.records) && obj.records.length > 0) ||
    (Array.isArray(obj.series) && obj.series.length > 0) ||
    (Array.isArray(obj.divergences) && obj.divergences.length > 0)
  );
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

  // Known-sparse guard
  if (meta.insufficient_data === true) return "empty";

  // Check for data presence
  if (!hasData(swrData)) return "empty";

  // Staleness check
  if (dataClass && typeof meta.staleness_seconds === "number") {
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
    return apiFetch<T>(ep, parsedParams);
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
