"use client";

import { useState, useEffect } from "react";
import DataBlock from "@/components/ui/DataBlock";
import ErrorBanner from "@/components/ui/ErrorBanner";
import EmptyState from "@/components/ui/EmptyState";
import LoadingSkeleton from "@/components/ui/LoadingSkeleton";
import { formatDecimal } from "@/lib/format";

type PostState = "loading" | "ready" | "empty" | "error";

interface SectorRow {
  sector: string;
  rs_composite?: string | null;
  rs_gold?: string | null;
  conviction?: string | null;
  [key: string]: unknown;
}

type SortDir = "asc" | "desc";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function SectorBoard() {
  const [state, setState] = useState<PostState>("loading");
  const [data, setData] = useState<SectorRow[]>([]);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/query/template`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: "sector_rotation",
        params: { include_gold_rs: true },
      }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((json: unknown) => {
        const j = json as Record<string, unknown>;
        const inner = (j?.data ?? j) as Record<string, unknown>;
        const records = (inner?.records as SectorRow[] | undefined) ?? [];
        if (records.length === 0) {
          setState("empty");
        } else {
          setData(records);
          setState("ready");
        }
      })
      .catch((e: unknown) => {
        setErrorMsg(String(e));
        setState("error");
      });
  }, []);

  const sorted = [...data].sort((a, b) => {
    const av = parseFloat(String(a.rs_composite ?? "0")) || 0;
    const bv = parseFloat(String(b.rs_composite ?? "0")) || 0;
    return sortDir === "desc" ? bv - av : av - bv;
  });

  function toggleSort() {
    setSortDir((d) => (d === "desc" ? "asc" : "desc"));
  }

  if (state === "loading") return <LoadingSkeleton />;
  if (state === "error") return <ErrorBanner message={errorMsg} />;
  if (state === "empty") {
    return (
      <EmptyState
        title="No sector data"
        body="Sector rotation data is unavailable."
      />
    );
  }

  return (
    <DataBlock state="ready" dataClass="daily_regime">
      <div data-role="sector-board" data-block="sector-board">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200 text-left">
              <th className="py-2 px-3 font-semibold text-gray-600">Sector</th>
              <th
                className="py-2 px-3 font-semibold text-gray-600 cursor-pointer select-none text-right"
                onClick={toggleSort}
                aria-sort={sortDir === "desc" ? "descending" : "ascending"}
              >
                RS {sortDir === "desc" ? "▼" : "▲"}
              </th>
              <th className="py-2 px-3 font-semibold text-gray-600 text-right">
                Gold RS
              </th>
              <th className="py-2 px-3 font-semibold text-gray-600 text-right">
                Conviction
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <tr
                key={row.sector ?? i}
                className="border-b border-gray-100 hover:bg-gray-50"
              >
                <td className="py-2 px-3 text-gray-800">{row.sector}</td>
                <td className="py-2 px-3 text-right text-gray-800">
                  {formatDecimal(row.rs_composite ?? null)}
                </td>
                <td className="py-2 px-3 text-right text-gray-800">
                  {formatDecimal(row.rs_gold ?? null)}
                </td>
                <td className="py-2 px-3 text-right text-gray-600">
                  {row.conviction !== null && row.conviction !== undefined
                    ? String(row.conviction)
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </DataBlock>
  );
}
