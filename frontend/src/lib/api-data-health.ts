export interface DimensionScore {
  name: string;
  score: number;
  detail: string;
  raw?: Record<string, unknown>;
}

export interface TableHealth {
  table: string;
  domain: string;
  overall_score: number;
  pass: boolean;
  error: string | null;
  dimensions: DimensionScore[];
}

export interface DataHealthResponse {
  generated_at: string | null;
  manifest_version: number | null;
  rubric: Record<string, unknown> | null;
  tables: TableHealth[];
  available: boolean;
}

export async function getDataHealth(): Promise<DataHealthResponse> {
  const base =
    process.env.NEXT_PUBLIC_BACKEND_BASE ??
    process.env.BACKEND_BASE ??
    "http://127.0.0.1:8010";
  const res = await fetch(`${base}/api/v1/system/data-health`, {
    next: { revalidate: 60 },
  });
  if (!res.ok) {
    return {
      generated_at: null,
      manifest_version: null,
      rubric: null,
      tables: [],
      available: false,
    };
  }
  return res.json() as Promise<DataHealthResponse>;
}
