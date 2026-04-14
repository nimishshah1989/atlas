"use client";

import { useEffect, useState } from "react";
import { getMfFlows, type MFFlowRow, type MFStaleness } from "@/lib/api";
import { formatDecimal, signColor } from "@/lib/format";

function StalenessTag({ staleness }: { staleness: MFStaleness }) {
  if (staleness.flag === "FRESH") return null;
  const color =
    staleness.flag === "EXPIRED"
      ? "bg-red-50 text-red-700 border-red-200"
      : "bg-amber-50 text-amber-700 border-amber-200";
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded border ${color}`}>
      {staleness.flag}
    </span>
  );
}

function FlowBar({
  value,
  max,
  isPositive,
}: {
  value: number;
  max: number;
  isPositive: boolean;
}) {
  const pct = max > 0 ? Math.min(100, (Math.abs(value) / max) * 100) : 0;
  return (
    <div className="h-1 rounded-full bg-gray-100 mt-1 w-full">
      <div
        className={`h-1 rounded-full ${isPositive ? "bg-emerald-400" : "bg-red-400"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function MFFlowsPanel() {
  const [flows, setFlows] = useState<MFFlowRow[]>([]);
  const [staleness, setStaleness] = useState<MFStaleness | null>(null);
  const [dataAsOf, setDataAsOf] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getMfFlows()
      .then((res) => {
        // Show latest 6 months, sorted most-recent first
        const sorted = [...res.flows].sort(
          (a, b) => b.month_date.localeCompare(a.month_date)
        );
        setFlows(sorted.slice(0, 6));
        setStaleness(res.staleness);
        setDataAsOf(res.data_as_of);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="animate-pulse space-y-2">
        <div className="h-5 bg-gray-100 rounded w-2/3" />
        {[...Array(6)].map((_, i) => (
          <div key={i} className="h-14 bg-gray-100 rounded" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="border rounded p-3 text-red-600 text-xs">
        Failed to load flows: {error}
      </div>
    );
  }

  const maxAbs = flows.reduce((m, f) => {
    const v = f.net_flow_cr ? Math.abs(parseFloat(f.net_flow_cr)) : 0;
    return Math.max(m, v);
  }, 0);

  return (
    <div className="bg-white border rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-gray-700">
            Industry Flows
          </h2>
          {staleness && <StalenessTag staleness={staleness} />}
        </div>
        {dataAsOf && (
          <span className="text-xs text-gray-400">as of {dataAsOf}</span>
        )}
      </div>

      {flows.length === 0 ? (
        <div className="px-4 py-6 text-sm text-gray-400 text-center">
          No flow data available
        </div>
      ) : (
        <div className="divide-y">
          {flows.map((row) => {
            const netFlow = row.net_flow_cr ? parseFloat(row.net_flow_cr) : null;
            const sipFlow = row.sip_flow_cr ? parseFloat(row.sip_flow_cr) : null;
            const aum = row.aum_cr ? parseFloat(row.aum_cr) : null;
            const isPos = netFlow !== null && netFlow >= 0;

            // Format month label: "2026-03" → "Mar 26"
            const [yr, mo] = row.month_date.split("-");
            const months = [
              "Jan","Feb","Mar","Apr","May","Jun",
              "Jul","Aug","Sep","Oct","Nov","Dec",
            ];
            const moLabel = months[parseInt(mo) - 1] ?? mo;
            const label = `${moLabel} ${yr.slice(2)}`;

            return (
              <div key={`${row.month_date}-${row.category}`} className="px-4 py-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-xs font-medium text-gray-700">
                      {label}
                    </span>
                    {row.category && row.category !== "All" && (
                      <span className="text-xs text-gray-400 ml-1">
                        · {row.category}
                      </span>
                    )}
                  </div>
                  <div className="text-right">
                    <span
                      className={`text-sm font-semibold ${signColor(netFlow)}`}
                    >
                      {netFlow !== null
                        ? `${isPos ? "+" : ""}₹${formatDecimal(Math.abs(netFlow))} Cr`
                        : "—"}
                    </span>
                  </div>
                </div>
                {netFlow !== null && (
                  <FlowBar value={netFlow} max={maxAbs} isPositive={isPos} />
                )}
                <div className="flex justify-between mt-1.5 text-xs text-gray-400">
                  <span>
                    SIP:{" "}
                    {sipFlow !== null ? `₹${formatDecimal(sipFlow)} Cr` : "—"}
                  </span>
                  <span>
                    AUM:{" "}
                    {aum !== null ? `₹${formatDecimal(aum)} Cr` : "—"}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
