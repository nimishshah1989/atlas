"use client";

import { useState, useEffect } from "react";
import { getMacroRatios, type MacroRatioItem } from "@/lib/api-global";
import { formatDecimal } from "@/lib/format";
import { formatIstDate, SkeletonBlock, PanelError } from "./helpers";

export function MacroRatiosPanel() {
  const [ratios, setRatios] = useState<MacroRatioItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const resp = await getMacroRatios();
      setRatios(resp.data ?? resp.ratios ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load macro ratios");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const latestDate =
    ratios && ratios.length > 0
      ? ratios.reduce((best, r) => {
          if (!r.latest_date) return best;
          return !best || r.latest_date > best ? r.latest_date : best;
        }, null as string | null)
      : null;

  return (
    <div className="bg-white border border-[#e4e4e8] rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-gray-900 text-sm">Macro Ratios</h2>
        {latestDate && (
          <span className="text-xs text-gray-400">Data as of {formatIstDate(latestDate)}</span>
        )}
      </div>

      {loading && <SkeletonBlock lines={6} />}
      {error && <PanelError message={error} onRetry={load} />}

      {!loading && !error && ratios !== null && ratios.length === 0 && (
        <p className="text-sm text-gray-400 text-center py-6">No macro ratio data available.</p>
      )}

      {!loading && !error && ratios !== null && ratios.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-[#e4e4e8]">
                <th className="text-left text-xs text-gray-500 font-semibold pb-2 pr-3">Ticker</th>
                <th className="text-left text-xs text-gray-500 font-semibold pb-2 pr-3">Name</th>
                <th className="text-right text-xs text-gray-500 font-semibold pb-2 pr-3">Latest Value</th>
                <th className="text-left text-xs text-gray-500 font-semibold pb-2">Unit</th>
                <th className="text-right text-xs text-gray-500 font-semibold pb-2">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e4e4e8]">
              {ratios.map((r) => (
                <tr key={r.ticker} className="hover:bg-gray-50">
                  <td className="py-2 pr-3 font-mono text-xs text-gray-700 font-semibold">{r.ticker}</td>
                  <td className="py-2 pr-3 text-gray-600 max-w-[160px] truncate">{r.name ?? "—"}</td>
                  <td className="py-2 pr-3 text-right tabular-nums font-medium text-gray-900">
                    {r.latest_value != null ? formatDecimal(r.latest_value, 4) : "—"}
                  </td>
                  <td className="py-2 text-gray-400 text-xs">{r.unit ?? "—"}</td>
                  <td className="py-2 text-right text-xs text-gray-400">{formatIstDate(r.latest_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
