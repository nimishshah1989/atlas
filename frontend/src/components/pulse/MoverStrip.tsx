"use client";

import { useState, useEffect } from "react";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import LoadingSkeleton from "@/components/ui/LoadingSkeleton";
import { formatDecimal } from "@/lib/format";

type PostState = "loading" | "ready" | "empty" | "error";

interface MoverRow {
  symbol: string;
  company_name?: string | null;
  sector?: string | null;
  rs_composite?: string | null;
  quadrant?: string | null;
  [key: string]: unknown;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

function quadrantColor(q: string | null | undefined): string {
  if (!q) return "var(--text-tertiary)";
  const s = String(q).toLowerCase();
  if (s.includes("leading")) return "var(--rag-green-700)";
  if (s.includes("improving")) return "var(--accent-700)";
  if (s.includes("weakening")) return "var(--rag-amber-700)";
  return "var(--rag-red-700)";
}

function rsColor(rs: string | null | undefined): string {
  if (!rs) return "var(--text-tertiary)";
  const n = parseFloat(String(rs));
  if (isNaN(n)) return "var(--text-tertiary)";
  if (n >= 70) return "var(--rag-green-700)";
  if (n >= 50) return "var(--rag-amber-700)";
  return "var(--rag-red-700)";
}

export default function MoverStrip() {
  const [state, setState] = useState<PostState>("loading");
  const [gainers, setGainers] = useState<MoverRow[]>([]);
  const [errorMsg, setErrorMsg] = useState<string>("");

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/stocks/movers?universe=nifty500&limit=6`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((json: unknown) => {
        const j = json as Record<string, unknown>;
        const rows = (j?.gainers as MoverRow[] | undefined) ?? [];
        if (rows.length === 0) setState("empty");
        else { setGainers(rows); setState("ready"); }
      })
      .catch((e: unknown) => { setErrorMsg(String(e)); setState("error"); });
  }, []);

  if (state === "loading") return <LoadingSkeleton />;
  if (state === "error") return <ErrorBanner message={errorMsg} />;
  if (state === "empty") return <EmptyState title="No movers today" body="Top gainers data is unavailable." />;

  return (
    <div
      data-block="mover-strip"
      style={{
        background: "var(--bg-surface)",
        border: "var(--border-card)",
        borderRadius: "var(--radius-lg)",
        overflow: "hidden",
      }}
    >
      {/* Card header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px var(--space-4)", borderBottom: "var(--border-inner)" }}>
        <span style={{ fontSize: "var(--fs-sm)", fontWeight: 600, color: "var(--text-primary)" }}>
          Top Movers
        </span>
        <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>Nifty 500 · by RS</span>
      </div>

      {/* Mover list */}
      <div style={{ padding: "var(--space-3) var(--space-4)", display: "flex", flexDirection: "column", gap: 1 }}>
        {gainers.map((row, i) => (
          <div
            key={row.symbol ?? i}
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto auto",
              gap: "var(--space-3)",
              alignItems: "center",
              padding: "8px 6px",
              borderRadius: "var(--radius-sm)",
              cursor: "pointer",
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--bg-hover)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ""; }}
          >
            {/* Symbol + sector */}
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)", fontVariantNumeric: "tabular-nums" }}>
                {row.symbol}
              </div>
              {row.sector && (
                <div style={{ fontSize: 10, color: "var(--text-tertiary)", marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {String(row.sector)}
                </div>
              )}
            </div>

            {/* Quadrant badge */}
            {row.quadrant && (
              <span style={{
                fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: "var(--radius-full)",
                background: "var(--bg-inset)", color: quadrantColor(row.quadrant),
                textTransform: "uppercase", letterSpacing: ".04em", whiteSpace: "nowrap",
              }}>
                {String(row.quadrant)}
              </span>
            )}

            {/* RS score */}
            <div style={{ textAlign: "right", minWidth: 40 }}>
              <div style={{ fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums", color: rsColor(row.rs_composite) }}>
                {formatDecimal(row.rs_composite ?? null)}
              </div>
              <div style={{ fontSize: 9, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: ".04em" }}>RS</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
