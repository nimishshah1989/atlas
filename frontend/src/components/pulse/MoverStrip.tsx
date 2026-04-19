"use client";

import { useState, useEffect } from "react";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import LoadingSkeleton from "@/components/ui/LoadingSkeleton";
import { formatDecimal, formatPercent, signColor } from "@/lib/format";

type PostState = "loading" | "ready" | "empty" | "error";

interface MoverRow {
  symbol: string;
  rs_composite?: string | null;
  change_pct?: string | null;
  [key: string]: unknown;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function MoverStrip() {
  const [state, setState] = useState<PostState>("loading");
  const [data, setData] = useState<MoverRow[]>([]);
  const [errorMsg, setErrorMsg] = useState<string>("");

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/query/template`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: "top_gainers",
        params: { universe: "nifty500", limit: 5 },
      }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((json: unknown) => {
        const j = json as Record<string, unknown>;
        const inner = (j?.data ?? j) as Record<string, unknown>;
        const records = (inner?.records as MoverRow[] | undefined) ?? [];
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

  if (state === "loading") return <LoadingSkeleton />;
  if (state === "error") return <ErrorBanner message={errorMsg} />;
  if (state === "empty") {
    return (
      <EmptyState
        title="No movers today"
        body="Top gainers data is unavailable for this universe."
      />
    );
  }

  return (
    <div
      className="flex gap-3 overflow-x-auto pb-2"
      data-block="mover-strip"
    >
      {data.map((row, i) => (
        <div
          key={row.symbol ?? i}
          className="min-w-32 border border-gray-200 rounded p-3 bg-white flex flex-col gap-1"
        >
          <span className="font-bold text-gray-800 text-sm truncate">
            {row.symbol}
          </span>
          <span className="text-xs text-gray-500">
            RS: {formatDecimal(row.rs_composite ?? null)}
          </span>
          <span
            className={`text-sm font-semibold ${signColor(row.change_pct ?? null)}`}
          >
            {formatPercent(row.change_pct ?? null)}
          </span>
        </div>
      ))}
    </div>
  );
}
