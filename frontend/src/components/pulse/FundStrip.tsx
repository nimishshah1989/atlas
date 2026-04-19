"use client";

import { useState, useEffect } from "react";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import LoadingSkeleton from "@/components/ui/LoadingSkeleton";
import { formatDecimal } from "@/lib/format";

type PostState = "loading" | "ready" | "empty" | "error";

interface FundRow {
  fund_name?: string;
  scheme_name?: string;
  rs_composite?: string | null;
  category?: string | null;
  [key: string]: unknown;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function FundStrip() {
  const [state, setState] = useState<PostState>("loading");
  const [data, setData] = useState<FundRow[]>([]);
  const [errorMsg, setErrorMsg] = useState<string>("");

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/query/template`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: "fund_1d_movers",
        params: { limit: 5 },
      }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((json: unknown) => {
        const j = json as Record<string, unknown>;
        const inner = (j?.data ?? j) as Record<string, unknown>;
        const records = (inner?.records as FundRow[] | undefined) ?? [];
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
        title="No fund movers"
        body="Fund daily movers data is unavailable."
      />
    );
  }

  return (
    <div className="flex gap-3 overflow-x-auto pb-2" data-block="fund-strip">
      {data.map((row, i) => {
        const name = row.fund_name ?? row.scheme_name ?? "—";
        return (
          <div
            key={String(row.fund_name ?? row.scheme_name ?? i)}
            className="min-w-48 border border-gray-200 rounded p-3 bg-white flex flex-col gap-1"
          >
            <span
              className="font-semibold text-gray-800 text-sm truncate"
              title={name}
            >
              {name}
            </span>
            <span className="text-xs text-gray-500">
              RS: {formatDecimal(row.rs_composite ?? null)}
            </span>
            {row.category !== null && row.category !== undefined && (
              <span className="text-xs text-gray-400 truncate">
                {String(row.category)}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
