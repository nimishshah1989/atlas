"use client";

import { useState, useEffect } from "react";
import { getGlobalRSHeatmap, type GlobalRSEntry } from "@/lib/api-global";
import { formatCurrency, formatDecimal } from "@/lib/format";
import { formatIstDate, SkeletonBlock, PanelError, rsScoreColor } from "./helpers";

export function RSHeatmapPanel() {
  const [rows, setRows] = useState<GlobalRSEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const resp = await getGlobalRSHeatmap();
      setRows(resp.data ?? resp.heatmap ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load RS heatmap");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const latestDate =
    rows && rows.length > 0
      ? rows.reduce((best, r) => {
          if (!r.rs_date) return best;
          return !best || r.rs_date > best ? r.rs_date : best;
        }, null as string | null)
      : null;

  return (
    <div className="bg-white border border-[#e4e4e8] rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-gray-900 text-sm">Global RS Heatmap</h2>
        {latestDate && (
          <span className="text-xs text-gray-400">Data as of {formatIstDate(latestDate)}</span>
        )}
      </div>

      {loading && <SkeletonBlock lines={7} />}
      {error && <PanelError message={error} onRetry={load} />}

      {!loading && !error && rows !== null && rows.length === 0 && (
        <p className="text-sm text-gray-400 text-center py-6">No RS heatmap data available.</p>
      )}

      {!loading && !error && rows !== null && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-[#e4e4e8]">
                <th className="text-left text-xs text-gray-500 font-semibold pb-2 pr-3">Entity</th>
                <th className="text-left text-xs text-gray-500 font-semibold pb-2 pr-3">Type</th>
                <th className="text-left text-xs text-gray-500 font-semibold pb-2 pr-3">Country</th>
                <th className="text-right text-xs text-gray-500 font-semibold pb-2 pr-2">RS Comp</th>
                <th className="text-right text-xs text-gray-500 font-semibold pb-2 pr-2">RS 1M</th>
                <th className="text-right text-xs text-gray-500 font-semibold pb-2 pr-2">RS 3M</th>
                <th className="text-right text-xs text-gray-500 font-semibold pb-2">Close</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e4e4e8]">
              {rows.map((r) => (
                <tr key={r.entity_id} className="hover:bg-gray-50">
                  <td className="py-2 pr-3">
                    <div className="font-mono text-xs text-gray-900 font-semibold">{r.entity_id}</div>
                    {r.name && <div className="text-xs text-gray-400 truncate max-w-[140px]">{r.name}</div>}
                  </td>
                  <td className="py-2 pr-3 text-xs text-gray-500">{r.instrument_type ?? "—"}</td>
                  <td className="py-2 pr-3 text-xs text-gray-500">{r.country ?? "—"}</td>
                  <td className={`py-2 pr-2 text-right tabular-nums text-sm ${rsScoreColor(r.rs_composite)}`}>
                    {formatDecimal(r.rs_composite)}
                  </td>
                  <td className={`py-2 pr-2 text-right tabular-nums text-sm ${rsScoreColor(r.rs_1m)}`}>
                    {formatDecimal(r.rs_1m)}
                  </td>
                  <td className={`py-2 pr-2 text-right tabular-nums text-sm ${rsScoreColor(r.rs_3m)}`}>
                    {formatDecimal(r.rs_3m)}
                  </td>
                  <td className="py-2 text-right tabular-nums text-sm text-gray-700">{formatCurrency(r.close)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
