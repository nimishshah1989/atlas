"use client";

import { useState, useEffect } from "react";
import { getGlobalRegime, type RegimeSummary, type BreadthSummary } from "@/lib/api-global";
import { formatDecimal, formatPercent, regimeColor, signColor } from "@/lib/format";
import { formatIstDate, SkeletonBlock, PanelError } from "./helpers";

export function RegimePanel() {
  const [regime, setRegime] = useState<RegimeSummary | null>(null);
  const [breadth, setBreadth] = useState<BreadthSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const resp = await getGlobalRegime();
      const d = resp.data ?? { regime: resp.regime, breadth: resp.breadth };
      setRegime(d.regime ?? null);
      setBreadth(d.breadth ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load regime");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const dataDate = regime?.date ?? breadth?.date ?? null;

  return (
    <div className="bg-white border border-[#e4e4e8] rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-gray-900 text-sm">Market Regime</h2>
        {dataDate && (
          <span className="text-xs text-gray-400">Data as of {formatIstDate(dataDate)}</span>
        )}
      </div>

      {loading && <SkeletonBlock lines={6} />}
      {error && <PanelError message={error} onRetry={load} />}

      {!loading && !error && regime === null && breadth === null && (
        <p className="text-sm text-gray-400 text-center py-6">No regime data available.</p>
      )}

      {!loading && !error && (regime !== null || breadth !== null) && (
        <div className="space-y-4">
          {regime !== null && (
            <div className="flex items-center gap-3 flex-wrap">
              {regime.regime && (
                <span className={`text-sm font-bold px-3 py-1 rounded border ${regimeColor(regime.regime)}`}>
                  {regime.regime}
                </span>
              )}
              {regime.confidence != null && (
                <span className="text-xs text-gray-500">
                  Confidence: <span className="font-semibold text-gray-700">{formatPercent(regime.confidence)}</span>
                </span>
              )}
            </div>
          )}

          {regime !== null && (
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              {[
                { label: "Breadth", value: regime.breadth_score },
                { label: "Momentum", value: regime.momentum_score },
                { label: "Volume", value: regime.volume_score },
                { label: "Global", value: regime.global_score },
                { label: "FII", value: regime.fii_score },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-gray-500">{label}</span>
                  <span className={`font-medium tabular-nums ${signColor(value)}`}>{formatDecimal(value)}</span>
                </div>
              ))}
            </div>
          )}

          {breadth !== null && (
            <div className="border-t border-[#e4e4e8] pt-3">
              <p className="text-xs font-semibold text-gray-500 mb-2 uppercase tracking-wide">Breadth</p>
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Advance</span>
                  <span className="font-medium text-emerald-600 tabular-nums">{breadth.advance ?? "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Decline</span>
                  <span className="font-medium text-red-600 tabular-nums">{breadth.decline ?? "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">A/D Ratio</span>
                  <span className="font-medium tabular-nums">{formatDecimal(breadth.ad_ratio)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Above 200DMA</span>
                  <span className="font-medium tabular-nums">{formatPercent(breadth.pct_above_200dma, false)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Above 50DMA</span>
                  <span className="font-medium tabular-nums">{formatPercent(breadth.pct_above_50dma, false)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">52w Highs</span>
                  <span className="font-medium text-emerald-600 tabular-nums">{breadth.new_52w_highs ?? "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">52w Lows</span>
                  <span className="font-medium text-red-600 tabular-nums">{breadth.new_52w_lows ?? "—"}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
