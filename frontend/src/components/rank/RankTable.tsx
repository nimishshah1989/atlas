"use client";

import React, { useState, useMemo, useCallback } from "react";
import useSWR from "swr";
import Link from "next/link";
import SparklineCell, { type SparklinePoint } from "./SparklineCell";
import { formatPercent, formatDecimal, formatCurrency } from "@/lib/format";
import type { RankFilters } from "@/app/funds/rank/page";

export interface RankRecord {
  rank: number;
  mstar_id: string;
  fund_name: string;
  category: string;
  aum_cr: number | null;
  returns_score: number | null;
  risk_score: number | null;
  resilience_score: number | null;
  consistency_score: number | null;
  composite_score: number | null;
  ret_1y: number | null;
  ret_3y: number | null;
  ret_5y: number | null;
  sparkline: SparklinePoint[] | null;
}

interface RankApiResponse {
  records: RankRecord[];
}

type SortKey = keyof Pick<
  RankRecord,
  "rank" | "composite_score" | "returns_score" | "risk_score" | "resilience_score" | "consistency_score" | "ret_1y" | "ret_3y" | "ret_5y" | "aum_cr"
>;

type SortDir = "asc" | "desc";

interface RankTableProps {
  filters: RankFilters;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// SWR fetcher for GET /api/v1/mf/rank
interface RankApiEnvelope {
  records: RankRecord[];
  _meta: { data_as_of: string | null; staleness_seconds: number; source: string; total: number };
}

async function rankFetcher(url: string): Promise<RankApiEnvelope> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`rank fetch: ${res.status}`);
  return res.json() as Promise<RankApiEnvelope>;
}

function buildRankUrl(filters: RankFilters): string {
  const params = new URLSearchParams();
  params.set("limit", "100");
  if (filters.category) params.set("category", filters.category);
  if (filters.amc) params.set("aum_range", filters.amc);
  return `${API_BASE}/api/v1/mf/rank?${params.toString()}`;
}

function exportCsv(records: RankRecord[]) {
  const header = [
    "Rank", "Fund Name", "Category", "AUM (₹ Cr)", "Returns Score", "Risk Score",
    "Resilience Score", "Consistency Score", "Composite Score", "1Y Return", "3Y Return", "5Y Return"
  ].join(",");
  const rows = records.map((r) =>
    [
      r.rank,
      `"${r.fund_name.replace(/"/g, '""')}"`,
      `"${r.category}"`,
      r.aum_cr ?? "",
      r.returns_score ?? "",
      r.risk_score ?? "",
      r.resilience_score ?? "",
      r.consistency_score ?? "",
      r.composite_score ?? "",
      r.ret_1y ?? "",
      r.ret_3y ?? "",
      r.ret_5y ?? "",
    ].join(",")
  );
  const csv = [header, ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "mf-rank.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function rankBadgeClass(rank: number): string {
  if (rank === 1) return "bg-green-100 text-green-700 border border-green-300";
  if (rank === 2) return "bg-teal-100 text-teal-700 border border-teal-300";
  if (rank === 3) return "bg-amber-100 text-amber-700 border border-amber-300";
  return "bg-gray-100 text-gray-500 border border-gray-200";
}

function compositeClass(score: number | null): string {
  if (score === null) return "";
  if (score >= 75) return "text-emerald-600";
  if (score >= 60) return "text-amber-600";
  return "text-red-600";
}

export default function RankTable({ filters }: RankTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("composite_score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const rankUrl = buildRankUrl(filters);

  const { data: swrData, error, isValidating } = useSWR<RankApiEnvelope>(
    rankUrl,
    rankFetcher,
    { revalidateOnFocus: false }
  );

  const records = swrData?.records ?? [];
  const dataAsOf = swrData?._meta?.data_as_of ?? null;
  const isLoading = !swrData && isValidating;

  const sorted = useMemo(() => {
    const copy = [...records];
    copy.sort((a, b) => {
      const av = a[sortKey] ?? -Infinity;
      const bv = b[sortKey] ?? -Infinity;
      if (typeof av === "number" && typeof bv === "number") {
        return sortDir === "asc" ? av - bv : bv - av;
      }
      return 0;
    });
    return copy;
  }, [records, sortKey, sortDir]);

  const toggleSort = useCallback(
    (key: SortKey) => {
      if (sortKey === key) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setSortDir("desc");
      }
    },
    [sortKey]
  );

  const sortArrow = (key: SortKey) =>
    sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : "";

  // Determine block state for data-state attribute
  const blockState = error ? "error" : isLoading ? "loading" : records.length > 0 ? "ready" : "empty";

  return (
    <div
      data-block="rank-table"
      data-endpoint="/api/v1/mf/rank"
      data-state={blockState}
      data-data-class="daily_regime"
      className="bg-white border border-gray-200 rounded-lg overflow-hidden"
    >
      {/* Table header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div>
          <div className="font-serif text-base font-semibold text-gray-900">Composite Rankings</div>
          <div className="text-xs text-gray-400 font-mono mt-0.5">
            {isLoading
              ? "Loading…"
              : error
              ? "Error loading data"
              : `${sorted.length} funds${dataAsOf ? ` · as of ${dataAsOf}` : ""}`}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="inline-flex items-center gap-1 text-xs font-medium px-3 py-1.5 bg-white text-gray-500 border border-gray-200 rounded hover:bg-gray-50 hover:text-gray-800 transition-colors"
            title="Export CSV"
            onClick={() => exportCsv(sorted)}
            data-testid="csv-export-btn"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-3 h-3">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Export CSV
          </button>
        </div>
      </div>

      {/* Loading skeleton */}
      {isLoading && (
        <div className="p-4 space-y-2 animate-pulse">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-10 bg-gray-100 rounded" />
          ))}
        </div>
      )}

      {/* Error */}
      {error && !isLoading && (
        <div className="p-4 text-sm text-red-600">
          Failed to load rankings. Please try again.
        </div>
      )}

      {/* Empty */}
      {!isLoading && !error && records.length === 0 && (
        <div className="p-8 text-center text-sm text-gray-400">
          No funds match the selected filters.
        </div>
      )}

      {/* Table */}
      {!isLoading && !error && sorted.length > 0 && (
        <div className="overflow-x-auto" data-mobile-scroll="true">
          <table className="w-full text-xs border-collapse" style={{ minWidth: 960 }} aria-label="MF Rank table">
            <thead>
              <tr className="bg-gray-50">
                {[
                  { key: "rank" as SortKey, label: "Rank", align: "left", w: "52px" },
                  { key: null, label: "Fund", align: "left" },
                  { key: null, label: "Category", align: "left" },
                  { key: "aum_cr" as SortKey, label: "AUM (₹ Cr)", align: "right" },
                  { key: null, label: "Sparkline", align: "center" },
                  { key: "ret_1y" as SortKey, label: "1Y Ret", align: "right" },
                  { key: "ret_3y" as SortKey, label: "3Y Ret", align: "right" },
                  { key: "ret_5y" as SortKey, label: "5Y Ret", align: "right" },
                  { key: "returns_score" as SortKey, label: "Returns", align: "right" },
                  { key: "risk_score" as SortKey, label: "Risk", align: "right" },
                  { key: "resilience_score" as SortKey, label: "Resilience", align: "right" },
                  { key: "consistency_score" as SortKey, label: "Consistency", align: "right" },
                  { key: "composite_score" as SortKey, label: "Composite", align: "right" },
                ].map((col) => (
                  <th
                    key={col.label}
                    className={`px-2.5 py-2 font-bold uppercase tracking-widest text-gray-400 border-b border-gray-200 whitespace-nowrap text-${col.align} ${col.key ? "cursor-pointer select-none hover:text-gray-700" : ""}`}
                    style={col.w ? { width: col.w } : undefined}
                    onClick={col.key ? () => toggleSort(col.key as SortKey) : undefined}
                    aria-sort={col.key && sortKey === col.key ? (sortDir === "asc" ? "ascending" : "descending") : undefined}
                  >
                    {col.label}{col.key ? sortArrow(col.key as SortKey) : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((row) => (
                <tr key={row.mstar_id} className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer">
                  <td className="px-2.5 py-2.5">
                    <span
                      className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold font-mono ${rankBadgeClass(row.rank)}`}
                    >
                      {row.rank}
                    </span>
                  </td>
                  <td className="px-2.5 py-2.5">
                    <Link href={`/funds/${row.mstar_id}`} className="flex flex-col gap-0.5 hover:text-teal-700">
                      <span className="text-xs font-semibold text-gray-900 max-w-[240px] leading-tight line-clamp-2">
                        {row.fund_name}
                      </span>
                      <span className="font-mono text-gray-400 text-[10px]">{row.mstar_id}</span>
                    </Link>
                  </td>
                  <td className="px-2.5 py-2.5">
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${
                      row.category === "Flexi Cap" ? "bg-teal-50 text-teal-700" :
                      row.category === "Large-Cap" ? "bg-emerald-50 text-emerald-700" :
                      row.category === "Large & Mid-Cap" ? "bg-emerald-50 text-emerald-700" :
                      row.category === "Mid-Cap" ? "bg-amber-50 text-amber-700" :
                      row.category === "Small-Cap" ? "bg-red-50 text-red-700" :
                      row.category?.includes("ELSS") ? "bg-purple-50 text-purple-700" :
                      "bg-gray-100 text-gray-600"
                    }`}>
                      {row.category}
                    </span>
                  </td>
                  <td className="px-2.5 py-2.5 text-right font-mono text-gray-700">
                    {row.aum_cr !== null ? formatCurrency(row.aum_cr) : "—"}
                  </td>
                  <td className="px-2.5 py-2.5">
                    <SparklineCell data={row.sparkline} />
                  </td>
                  <td className={`px-2.5 py-2.5 text-right font-semibold ${row.ret_1y !== null && row.ret_1y > 0 ? "text-emerald-600" : row.ret_1y !== null && row.ret_1y < 0 ? "text-red-600" : "text-gray-400"}`}>
                    {formatPercent(row.ret_1y)}
                  </td>
                  <td className={`px-2.5 py-2.5 text-right font-semibold ${row.ret_3y !== null && row.ret_3y > 0 ? "text-emerald-600" : row.ret_3y !== null && row.ret_3y < 0 ? "text-red-600" : "text-gray-400"}`}>
                    {formatPercent(row.ret_3y)}
                  </td>
                  <td className={`px-2.5 py-2.5 text-right font-semibold ${row.ret_5y !== null && row.ret_5y > 0 ? "text-emerald-600" : row.ret_5y !== null && row.ret_5y < 0 ? "text-red-600" : "text-gray-400"}`}>
                    {formatPercent(row.ret_5y)}
                  </td>
                  <td className="px-2.5 py-2.5 text-right">
                    <div className="flex flex-col items-end gap-0.5">
                      <span className="font-bold text-emerald-600 tabular-nums">{row.returns_score !== null ? formatDecimal(row.returns_score, 1) : "—"}</span>
                      {row.returns_score !== null && (
                        <div className="w-14 h-0.5 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${Math.min(100, row.returns_score)}%` }} />
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-2.5 py-2.5 text-right">
                    <div className="flex flex-col items-end gap-0.5">
                      <span className="font-bold text-amber-600 tabular-nums">{row.risk_score !== null ? formatDecimal(row.risk_score, 1) : "—"}</span>
                      {row.risk_score !== null && (
                        <div className="w-14 h-0.5 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-amber-500 rounded-full" style={{ width: `${Math.min(100, row.risk_score)}%` }} />
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-2.5 py-2.5 text-right">
                    <div className="flex flex-col items-end gap-0.5">
                      <span className="font-bold text-red-600 tabular-nums">{row.resilience_score !== null ? formatDecimal(row.resilience_score, 1) : "—"}</span>
                      {row.resilience_score !== null && (
                        <div className="w-14 h-0.5 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-red-500 rounded-full" style={{ width: `${Math.min(100, row.resilience_score)}%` }} />
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-2.5 py-2.5 text-right">
                    <div className="flex flex-col items-end gap-0.5">
                      <span className="font-bold text-teal-600 tabular-nums">{row.consistency_score !== null ? formatDecimal(row.consistency_score, 1) : "—"}</span>
                      {row.consistency_score !== null && (
                        <div className="w-14 h-0.5 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-teal-600 rounded-full" style={{ width: `${Math.min(100, row.consistency_score)}%` }} />
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-2.5 py-2.5 text-right">
                    <span className={`text-sm font-bold tabular-nums ${compositeClass(row.composite_score)}`}>
                      {row.composite_score !== null ? formatDecimal(row.composite_score, 2) : "—"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
