"use client";

import { useState, useEffect } from "react";
import { getGlobalBriefing, type BriefingDetail } from "@/lib/api-global";
import { formatIstDate, formatIstDateTime, SkeletonBlock, PanelError } from "./helpers";

export function BriefingPanel() {
  const [data, setData] = useState<BriefingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const resp = await getGlobalBriefing();
      setData(resp.data ?? resp.briefing ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load briefing");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const convictionColor = (c: string | null) => {
    if (!c) return "text-gray-500 bg-gray-50";
    const upper = c.toUpperCase();
    if (upper.includes("HIGH")) return "text-emerald-700 bg-emerald-50 border-emerald-200";
    if (upper.includes("LOW")) return "text-red-700 bg-red-50 border-red-200";
    return "text-amber-700 bg-amber-50 border-amber-200";
  };

  return (
    <div className="bg-white border border-[#e4e4e8] rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-gray-900 text-sm">Market Briefing</h2>
        {data && (
          <span className="text-xs text-gray-400">
            Data as of {formatIstDate(data.date ?? data.generated_at)}
          </span>
        )}
      </div>

      {loading && <SkeletonBlock lines={5} />}
      {error && <PanelError message={error} onRetry={load} />}

      {!loading && !error && data === null && (
        <p className="text-sm text-gray-400 text-center py-6">No briefing available.</p>
      )}

      {!loading && !error && data !== null && (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <h3 className="text-base font-semibold text-gray-900 leading-snug">{data.headline}</h3>
            {data.conviction && (
              <span className={`shrink-0 text-xs font-semibold px-2 py-0.5 rounded border ${convictionColor(data.conviction)}`}>
                {data.conviction}
              </span>
            )}
          </div>
          <p className="text-sm text-gray-700 leading-relaxed">{data.narrative}</p>
          {data.india_implication && (
            <div className="bg-teal-50 border border-teal-200 rounded p-3">
              <p className="text-xs font-semibold text-teal-700 mb-1">India Implication</p>
              <p className="text-sm text-teal-800">{data.india_implication}</p>
            </div>
          )}
          {data.risk_scenario && (
            <div className="bg-amber-50 border border-amber-200 rounded p-3">
              <p className="text-xs font-semibold text-amber-700 mb-1">Risk Scenario</p>
              <p className="text-sm text-amber-800">{data.risk_scenario}</p>
            </div>
          )}
          <div className="flex items-center justify-between text-xs text-gray-400 border-t border-[#e4e4e8] pt-2">
            {data.model_used && <span>Model: {data.model_used}</span>}
            <span>Generated: {formatIstDateTime(data.generated_at)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
