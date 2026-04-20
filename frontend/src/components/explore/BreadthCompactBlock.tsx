"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

// API returns { breadth: { advance, decline, ad_ratio, pct_above_200dma, ... }, regime: {...}, meta: {...} }
interface BreadthApiData {
  breadth?: {
    advance?: number | null;
    decline?: number | null;
    unchanged?: number | null;
    total_stocks?: number | null;
    ad_ratio?: string | number | null;
    pct_above_50dma?: string | number | null;
    pct_above_200dma?: string | number | null;
    new_52w_highs?: number | null;
    new_52w_lows?: number | null;
    date?: string | null;
  } | null;
  regime?: {
    regime?: string | null;
    confidence?: string | number | null;
    breadth_score?: string | number | null;
    momentum_score?: string | number | null;
  } | null;
  [key: string]: unknown;
}

function fmt(v: string | number | null | undefined, dp = 1): string {
  if (v == null) return "—";
  const n = typeof v === "number" ? v : parseFloat(String(v));
  if (isNaN(n)) return "—";
  return n.toFixed(dp);
}

function ragColor(v: string | number | null | undefined, higherGood = true): string {
  if (v == null) return "var(--text-primary)";
  const n = typeof v === "number" ? v : parseFloat(String(v));
  if (isNaN(n)) return "var(--text-primary)";
  const good = higherGood ? n >= 0 : n <= 0;
  return good ? "var(--rag-green-700)" : "var(--rag-red-700)";
}

function KpiCard({ label, value, color, sub }: { label: string; value: string; color?: string; sub?: string }) {
  return (
    <div style={{ background: "var(--bg-surface)", border: "var(--border-card)", borderRadius: "var(--radius-md)", padding: "var(--space-3) var(--space-4)" }}>
      <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-tertiary)", marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--font-mono)", color: color ?? "var(--text-primary)", lineHeight: 1 }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 10, color: "var(--text-tertiary)", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

export default function BreadthCompactBlock() {
  const { data, meta, state, error } = useAtlasData<BreadthApiData>(
    "/api/v1/stocks/breadth",
    { universe: "nifty500", range: "5y" },
    { dataClass: "eod_breadth" }
  );

  const b = (data as BreadthApiData)?.breadth;
  const r = (data as BreadthApiData)?.regime;

  return (
    <div data-block="breadth-compact">
      <DataBlock
        state={state}
        dataClass="eod_breadth"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No breadth data"
        emptyBody="Breadth data is not available for the selected universe."
      >
        {data && b && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            {/* KPI row */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "var(--space-3)" }}>
              <KpiCard
                label="Advances"
                value={b.advance?.toLocaleString("en-IN") ?? "—"}
                color="var(--rag-green-700)"
                sub={b.total_stocks ? `of ${b.total_stocks.toLocaleString("en-IN")}` : undefined}
              />
              <KpiCard
                label="Declines"
                value={b.decline?.toLocaleString("en-IN") ?? "—"}
                color="var(--rag-red-700)"
              />
              <KpiCard
                label="A/D Ratio"
                value={fmt(b.ad_ratio, 2)}
                color={ragColor(b.ad_ratio)}
              />
              <KpiCard
                label="52W Highs"
                value={String(b.new_52w_highs ?? "—")}
                color={b.new_52w_highs ? "var(--rag-green-700)" : "var(--text-tertiary)"}
              />
              <KpiCard
                label="52W Lows"
                value={String(b.new_52w_lows ?? "—")}
                color={b.new_52w_lows ? "var(--rag-red-700)" : "var(--text-tertiary)"}
              />
            </div>

            {/* Regime + scores row */}
            {r && (
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-4)", padding: "var(--space-3)", background: "var(--bg-inset)", borderRadius: "var(--radius-md)" }}>
                <span style={{
                  padding: "3px 10px",
                  borderRadius: "var(--radius-full)",
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: ".05em",
                  ...((r.regime ?? "").toUpperCase().includes("BULL") ? { background: "var(--rag-green-100)", color: "var(--rag-green-700)" }
                    : (r.regime ?? "").toUpperCase().includes("BEAR") ? { background: "var(--rag-red-100)", color: "var(--rag-red-700)" }
                    : { background: "var(--rag-amber-100)", color: "var(--rag-amber-700)" }),
                }}>
                  {r.regime ?? "—"}
                </span>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  Confidence: <strong>{fmt(r.confidence, 1)}%</strong>
                </span>
                {r.breadth_score != null && (
                  <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                    Breadth score: <strong>{fmt(r.breadth_score, 1)}</strong>
                  </span>
                )}
                {r.momentum_score != null && (
                  <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                    Momentum score: <strong>{fmt(r.momentum_score, 1)}</strong>
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </DataBlock>
    </div>
  );
}
