"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

interface ApiShape {
  stock?: {
    conviction?: {
      rs?: {
        rs_composite?: number | string | null;
        rs_1w?: number | string | null;
        rs_1m?: number | string | null;
        rs_3m?: number | string | null;
        rs_6m?: number | string | null;
        rs_12m?: number | string | null;
        quadrant?: string | null;
        benchmark?: string | null;
        explanation?: string | null;
      } | null;
    } | null;
    sharpe_1y?: number | string | null;
    sortino_1y?: number | string | null;
    max_drawdown_1y?: number | string | null;
    beta_nifty?: number | string | null;
    volatility_20d?: number | string | null;
  };
  [key: string]: unknown;
}

interface BenchmarkPanelsProps {
  symbol: string;
}

function fmt(v: number | null, suffix = "", places = 2): string {
  if (v === null) return "—";
  const s = Math.abs(v).toFixed(places);
  const sign = v >= 0 ? "+" : "−";
  return `${sign}${s}${suffix}`;
}

function fmtPct(v: number | null, places = 1): string {
  if (v === null) return "—";
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(places)}%`;
}

function metricColor(v: number | null, higherIsBetter = true): string {
  if (v === null) return "var(--text-secondary)";
  const isGood = higherIsBetter ? v >= 0 : v <= 0;
  return isGood ? "var(--rag-green-700)" : "var(--rag-red-700)";
}

function MetricRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0", borderBottom: "1px solid var(--border-subtle)" }}>
      <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 700, fontFamily: "var(--font-mono)", color: color ?? "var(--text-primary)" }}>
        {value}
      </span>
    </div>
  );
}

export default function BenchmarkPanels({ symbol }: BenchmarkPanelsProps) {
  const { data: rawData, meta, state, error } = useAtlasData<ApiShape>(
    `/api/v1/stocks/${symbol}`,
    {},
    { dataClass: "daily_regime" }
  );

  const stock = rawData?.stock;
  const rs = stock?.conviction?.rs;

  const rsComposite = rs?.rs_composite != null ? Number(rs.rs_composite) : null;
  const rs1w = rs?.rs_1w != null ? Number(rs.rs_1w) : null;
  const rs1m = rs?.rs_1m != null ? Number(rs.rs_1m) : null;
  const rs3m = rs?.rs_3m != null ? Number(rs.rs_3m) : null;
  const rs6m = rs?.rs_6m != null ? Number(rs.rs_6m) : null;
  const rs12m = rs?.rs_12m != null ? Number(rs.rs_12m) : null;
  const sharpe = stock?.sharpe_1y != null ? Number(stock.sharpe_1y) : null;
  const sortino = stock?.sortino_1y != null ? Number(stock.sortino_1y) : null;
  const maxDD = stock?.max_drawdown_1y != null ? Number(stock.max_drawdown_1y) : null;
  const beta = stock?.beta_nifty != null ? Number(stock.beta_nifty) : null;

  const hasData = rsComposite !== null || sharpe !== null;
  const effectiveState = state === "ready" && !hasData ? "empty" : state;

  return (
    <div data-component="benchmark-panels">
      <DataBlock
        state={effectiveState}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No benchmark data"
        emptyBody="Benchmark comparison is not available for this stock."
      >
        {hasData && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)" }}>
            {/* RS Performance card */}
            <div style={{
              background: "var(--bg-surface)",
              border: "var(--border-card)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-4)",
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--text-tertiary)", marginBottom: "var(--space-3)" }}>
                Relative Strength vs {rs?.benchmark ?? "Benchmark"}
              </div>
              <MetricRow label="Composite RS" value={fmt(rsComposite)} color={metricColor(rsComposite)} />
              <MetricRow label="1 Week" value={fmt(rs1w)} color={metricColor(rs1w)} />
              <MetricRow label="1 Month" value={fmt(rs1m)} color={metricColor(rs1m)} />
              <MetricRow label="3 Months" value={fmt(rs3m)} color={metricColor(rs3m)} />
              <MetricRow label="6 Months" value={fmt(rs6m)} color={metricColor(rs6m)} />
              <MetricRow label="12 Months" value={fmt(rs12m)} color={metricColor(rs12m)} />
            </div>

            {/* Risk metrics card */}
            <div style={{
              background: "var(--bg-surface)",
              border: "var(--border-card)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-4)",
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--text-tertiary)", marginBottom: "var(--space-3)" }}>
                Risk Metrics (1 Year)
              </div>
              <MetricRow label="Sharpe Ratio" value={sharpe != null ? sharpe.toFixed(2) : "—"} color={metricColor(sharpe)} />
              <MetricRow label="Sortino Ratio" value={sortino != null ? sortino.toFixed(2) : "—"} color={metricColor(sortino)} />
              <MetricRow label="Max Drawdown" value={maxDD != null ? fmtPct(maxDD, 1) : "—"} color={maxDD != null ? (maxDD >= -0.10 ? "var(--rag-green-700)" : maxDD >= -0.20 ? "var(--rag-amber-700)" : "var(--rag-red-700)") : undefined} />
              <MetricRow label="Beta (Nifty)" value={beta != null ? beta.toFixed(2) : "—"} />
              <MetricRow label="Quadrant" value={rs?.quadrant ?? "—"} />
            </div>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
