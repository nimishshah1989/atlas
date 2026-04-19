"use client";

import { useState, useEffect } from "react";
import ErrorBanner from "@/components/ui/ErrorBanner";
import EmptyState from "@/components/ui/EmptyState";
import LoadingSkeleton from "@/components/ui/LoadingSkeleton";
import { formatDecimal } from "@/lib/format";

type PostState = "loading" | "ready" | "empty" | "error";

interface SectorRow {
  sector: string;
  rs_composite?: string | null;
  sector_quadrant?: string | null;
  pct_above_50dma?: string | null;
  [key: string]: unknown;
}

type SortDir = "asc" | "desc";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

function quadrantBadge(q: string | null | undefined): React.ReactNode {
  if (!q) return <span style={{ color: "var(--text-tertiary)" }}>—</span>;
  const s = String(q);
  let bg = "var(--bg-inset)";
  let col = "var(--text-secondary)";
  if (s.toLowerCase().includes("leading")) { bg = "var(--rag-green-100)"; col = "var(--rag-green-700)"; }
  else if (s.toLowerCase().includes("weakening")) { bg = "var(--rag-amber-100)"; col = "var(--rag-amber-700)"; }
  else if (s.toLowerCase().includes("lagging")) { bg = "var(--rag-red-100)"; col = "var(--rag-red-700)"; }
  else if (s.toLowerCase().includes("improving")) { bg = "var(--accent-100)"; col = "var(--accent-700)"; }
  return (
    <span style={{ background: bg, color: col, padding: "1px 7px", borderRadius: "var(--radius-full)", fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".04em" }}>
      {s}
    </span>
  );
}

function pctColor(pct: string | null | undefined): string {
  if (!pct) return "var(--text-tertiary)";
  const n = parseFloat(String(pct));
  if (isNaN(n)) return "var(--text-tertiary)";
  if (n >= 60) return "var(--rag-green-700)";
  if (n >= 40) return "var(--rag-amber-700)";
  return "var(--rag-red-700)";
}

export default function SectorBoard() {
  const [state, setState] = useState<PostState>("loading");
  const [data, setData] = useState<SectorRow[]>([]);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/stocks/sectors`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((json: unknown) => {
        const j = json as Record<string, unknown>;
        const sectors = (j?.sectors as SectorRow[] | undefined) ?? [];
        const rows = sectors.map((s) => ({
          ...s,
          rs_composite: (s.avg_rs_composite as string | null | undefined) ?? s.rs_composite ?? null,
        }));
        if (rows.length === 0) setState("empty");
        else { setData(rows); setState("ready"); }
      })
      .catch((e: unknown) => { setErrorMsg(String(e)); setState("error"); });
  }, []);

  const sorted = [...data].sort((a, b) => {
    const av = parseFloat(String(a.rs_composite ?? "0")) || 0;
    const bv = parseFloat(String(b.rs_composite ?? "0")) || 0;
    return sortDir === "desc" ? bv - av : av - bv;
  });

  if (state === "loading") return <LoadingSkeleton />;
  if (state === "error") return <ErrorBanner message={errorMsg} />;
  if (state === "empty") return <EmptyState title="No sector data" body="Sector rotation data is unavailable." />;

  return (
    <div
      data-block="sector-board"
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
          Sector Rotation
        </span>
        <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{data.length} sectors</span>
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr>
              {["Sector", "RS Score", ">50 DMA", "Quadrant"].map((col, i) => (
                <th
                  key={col}
                  onClick={col === "RS Score" ? () => setSortDir(d => d === "desc" ? "asc" : "desc") : undefined}
                  style={{
                    padding: "6px 10px",
                    fontSize: 9,
                    fontWeight: 600,
                    color: "var(--text-tertiary)",
                    textTransform: "uppercase",
                    letterSpacing: ".04em",
                    borderBottom: "2px solid var(--border-default)",
                    textAlign: i === 0 ? "left" : "right",
                    background: "var(--bg-surface)",
                    cursor: col === "RS Score" ? "pointer" : "default",
                    whiteSpace: "nowrap",
                    userSelect: "none",
                  }}
                >
                  {col}{col === "RS Score" ? (sortDir === "desc" ? " ▼" : " ▲") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <tr
                key={row.sector ?? i}
                style={{ borderBottom: "1px solid var(--border-subtle)" }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--bg-hover)"; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ""; }}
              >
                <td style={{ padding: "6px 10px", fontWeight: 500, color: "var(--text-primary)", textAlign: "left" }}>
                  {row.sector}
                </td>
                <td style={{ padding: "6px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 600, color: "var(--text-primary)" }}>
                  {formatDecimal(row.rs_composite ?? null)}
                </td>
                <td style={{ padding: "6px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 600, color: pctColor(row.pct_above_50dma) }}>
                  {row.pct_above_50dma != null
                    ? `${formatDecimal(String(row.pct_above_50dma))}%`
                    : "—"}
                </td>
                <td style={{ padding: "6px 10px", textAlign: "right" }}>
                  {quadrantBadge(row.sector_quadrant)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
