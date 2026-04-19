"use client";

import { useEffect } from "react";
import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatCurrency, formatDate } from "@/lib/format";

// API response shape: { stock: StockDetail, meta: {...}, _meta: {...} }
interface StockDetail {
  symbol?: string;
  company_name?: string;
  sector?: string | null;
  close?: number | string | null;
  cap_category?: string | null;
  nifty_50?: boolean;
  nifty_200?: boolean;
  nifty_500?: boolean;
  conviction?: {
    rs?: {
      rs_composite?: number | string | null;
      rs_momentum?: number | string | null;
      quadrant?: string | null;
    } | null;
    technical?: {
      checks_passing?: number;
      checks_total?: number;
    } | null;
    institutional?: {
      mf_holder_count?: number | null;
    } | null;
  } | null;
  gold_rs?: { gold_rs?: number | string | null } | null;
  [key: string]: unknown;
}

interface ApiShape {
  stock?: StockDetail;
  [key: string]: unknown;
}

interface StockHeroBlockProps {
  symbol: string;
  onSectorLoaded: (sector: string) => void;
}

function pctColor(n: number | null): string {
  if (n === null) return "var(--text-secondary)";
  if (n >= 0) return "var(--rag-green-700)";
  return "var(--rag-red-700)";
}

function quadrantBadge(q: string | null | undefined): { label: string; bg: string; fg: string } {
  if (!q) return { label: "—", bg: "var(--bg-inset)", fg: "var(--text-tertiary)" };
  const map: Record<string, { label: string; bg: string; fg: string }> = {
    LEADING:   { label: "Leading",   bg: "var(--rag-green-100)", fg: "var(--rag-green-700)" },
    IMPROVING: { label: "Improving", bg: "var(--rag-amber-100)", fg: "var(--rag-amber-700)" },
    LAGGING:   { label: "Lagging",   bg: "var(--rag-red-100)",   fg: "var(--rag-red-700)" },
    WEAKENING: { label: "Weakening", bg: "var(--rag-red-100)",   fg: "var(--rag-red-700)" },
  };
  return map[q.toUpperCase()] ?? { label: q, bg: "var(--bg-inset)", fg: "var(--text-secondary)" };
}

export default function StockHeroBlock({ symbol, onSectorLoaded }: StockHeroBlockProps) {
  const { data: rawData, meta, state, error } = useAtlasData<ApiShape>(
    `/api/v1/stocks/${symbol}`,
    { include: "rs,conviction" },
    { dataClass: "intraday" }
  );

  // The apiFetch hook returns the full JSON as `data`; the actual stock is under .stock
  const stock = rawData?.stock;

  useEffect(() => {
    if ((state === "ready" || state === "stale") && stock?.sector) {
      onSectorLoaded(stock.sector);
    }
  }, [state, stock, onSectorLoaded]);

  const close = stock?.close != null ? Number(stock.close) : null;
  const rsComposite = stock?.conviction?.rs?.rs_composite != null
    ? Number(stock.conviction.rs.rs_composite) : null;
  const rsMomentum = stock?.conviction?.rs?.rs_momentum != null
    ? Number(stock.conviction.rs.rs_momentum) : null;
  const quadrant = stock?.conviction?.rs?.quadrant ?? null;
  const techPassing = stock?.conviction?.technical?.checks_passing ?? null;
  const techTotal = stock?.conviction?.technical?.checks_total ?? 10;
  const mfCount = stock?.conviction?.institutional?.mf_holder_count ?? null;
  const badge = quadrantBadge(quadrant);

  return (
    <div
      data-block="hero"
      data-data-class="intraday"
      style={{
        background: "var(--bg-surface)",
        border: "var(--border-card)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--space-5)",
      }}
    >
      <DataBlock
        state={state}
        dataClass="intraday"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No stock data"
        emptyBody="Stock data is not available."
      >
        {stock && (
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "var(--space-5)" }}>
            {/* Left: identity + price */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginBottom: "var(--space-2)" }}>
                <h1 style={{
                  fontFamily: "var(--font-serif)",
                  fontSize: "var(--fs-xl)",
                  fontWeight: 500,
                  color: "var(--text-primary)",
                  margin: 0,
                  lineHeight: 1.2,
                }}>
                  {stock.company_name ?? symbol}
                </h1>
                <code style={{
                  fontSize: 11,
                  fontFamily: "var(--font-mono)",
                  background: "var(--bg-inset)",
                  border: "1px solid var(--border-default)",
                  borderRadius: "var(--radius-sm)",
                  padding: "2px 6px",
                  color: "var(--text-tertiary)",
                }}>
                  {stock.symbol ?? symbol}
                </code>
                {stock.sector && (
                  <span style={{
                    fontSize: 10,
                    fontWeight: 600,
                    padding: "2px 8px",
                    background: "var(--accent-50)",
                    border: "1px solid var(--accent-200)",
                    borderRadius: "var(--radius-full)",
                    color: "var(--accent-700)",
                    textTransform: "uppercase",
                    letterSpacing: ".04em",
                  }}>
                    {stock.sector}
                  </span>
                )}
                {stock.cap_category && (
                  <span style={{
                    fontSize: 10,
                    fontWeight: 600,
                    padding: "2px 8px",
                    background: "var(--bg-inset)",
                    border: "1px solid var(--border-default)",
                    borderRadius: "var(--radius-full)",
                    color: "var(--text-tertiary)",
                    textTransform: "capitalize",
                  }}>
                    {stock.cap_category}
                  </span>
                )}
              </div>

              <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-3)" }}>
                <span style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--fs-3xl)",
                  fontWeight: 700,
                  color: "var(--text-primary)",
                  letterSpacing: "-.01em",
                }}>
                  {close != null ? formatCurrency(close) : "—"}
                </span>
                {meta?.data_as_of && (
                  <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                    as of {formatDate(meta.data_as_of)}
                  </span>
                )}
              </div>
            </div>

            {/* Right: RS + conviction metrics grid */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 72px)",
              gap: "var(--space-3)",
              flexShrink: 0,
            }}>
              {/* RS Composite */}
              <div style={{
                background: "var(--bg-inset)",
                border: "1px solid var(--border-default)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-3)",
                textAlign: "center",
              }}>
                <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--text-tertiary)", marginBottom: 4 }}>
                  RS
                </div>
                <div style={{
                  fontSize: 18,
                  fontWeight: 700,
                  fontFamily: "var(--font-mono)",
                  color: pctColor(rsComposite),
                }}>
                  {rsComposite != null ? rsComposite.toFixed(1) : "—"}
                </div>
              </div>

              {/* RS Momentum */}
              <div style={{
                background: "var(--bg-inset)",
                border: "1px solid var(--border-default)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-3)",
                textAlign: "center",
              }}>
                <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--text-tertiary)", marginBottom: 4 }}>
                  Momentum
                </div>
                <div style={{
                  fontSize: 18,
                  fontWeight: 700,
                  fontFamily: "var(--font-mono)",
                  color: pctColor(rsMomentum),
                }}>
                  {rsMomentum != null ? rsMomentum.toFixed(2) : "—"}
                </div>
              </div>

              {/* Quadrant */}
              <div style={{
                background: "var(--bg-inset)",
                border: "1px solid var(--border-default)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-3)",
                textAlign: "center",
              }}>
                <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--text-tertiary)", marginBottom: 4 }}>
                  Quadrant
                </div>
                <div style={{
                  fontSize: 10,
                  fontWeight: 700,
                  padding: "2px 6px",
                  background: badge.bg,
                  color: badge.fg,
                  borderRadius: "var(--radius-sm)",
                  display: "inline-block",
                }}>
                  {badge.label}
                </div>
              </div>

              {/* Technical checks */}
              <div style={{
                background: "var(--bg-inset)",
                border: "1px solid var(--border-default)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-3)",
                textAlign: "center",
              }}>
                <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--text-tertiary)", marginBottom: 4 }}>
                  Checks
                </div>
                <div style={{
                  fontSize: 18,
                  fontWeight: 700,
                  fontFamily: "var(--font-mono)",
                  color: techPassing != null && techPassing >= 7 ? "var(--rag-green-700)"
                       : techPassing != null && techPassing >= 4 ? "var(--rag-amber-700)"
                       : "var(--rag-red-700)",
                }}>
                  {techPassing != null ? `${techPassing}/${techTotal}` : "—"}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* MF holder strip */}
        {stock && mfCount != null && (
          <div style={{
            marginTop: "var(--space-3)",
            paddingTop: "var(--space-3)",
            borderTop: "1px solid var(--border-subtle)",
            fontSize: 11,
            color: "var(--text-tertiary)",
          }}>
            Held by {mfCount.toLocaleString("en-IN")} mutual funds
          </div>
        )}
      </DataBlock>
    </div>
  );
}
