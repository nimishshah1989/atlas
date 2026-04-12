"use client";

import { useEffect, useState } from "react";
import { getBreadth, type BreadthResponse } from "@/lib/api";
import { formatDecimal, regimeColor } from "@/lib/format";

export default function MarketOverview() {
  const [data, setData] = useState<BreadthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getBreadth()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 animate-pulse">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-24 bg-gray-100 rounded-lg" />
        ))}
      </div>
    );
  }

  if (!data) return null;

  const { breadth, regime } = data;
  const advDecl = breadth.advance - breadth.decline;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Market Overview</h2>
        <span className="text-xs text-gray-500">
          Data as of {data.meta.data_as_of}
        </span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {/* Regime */}
        <div className="rounded-lg border p-4">
          <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">
            Regime
          </div>
          <div
            className={`text-xl font-bold px-2 py-0.5 rounded inline-block ${regimeColor(regime.regime)}`}
          >
            {regime.regime}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            Confidence: {formatDecimal(regime.confidence)}%
          </div>
        </div>

        {/* Advance / Decline */}
        <div className="rounded-lg border p-4">
          <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">
            Adv / Dec
          </div>
          <div className="text-xl font-bold">
            <span className="text-emerald-600">{breadth.advance}</span>
            <span className="text-gray-400 mx-1">/</span>
            <span className="text-red-600">{breadth.decline}</span>
          </div>
          <div
            className={`text-xs mt-1 ${advDecl >= 0 ? "text-emerald-600" : "text-red-600"}`}
          >
            Net: {advDecl > 0 ? "+" : ""}
            {advDecl}
          </div>
        </div>

        {/* % Above 200 DMA */}
        <div className="rounded-lg border p-4">
          <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">
            Above 200 DMA
          </div>
          <div className="text-xl font-bold">
            {formatDecimal(breadth.pct_above_200dma)}%
          </div>
          <div className="w-full bg-gray-100 rounded-full h-1.5 mt-2">
            <div
              className="bg-[#1D9E75] h-1.5 rounded-full"
              style={{
                width: `${parseFloat(breadth.pct_above_200dma || "0")}%`,
              }}
            />
          </div>
        </div>

        {/* % Above 50 DMA */}
        <div className="rounded-lg border p-4">
          <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">
            Above 50 DMA
          </div>
          <div className="text-xl font-bold">
            {formatDecimal(breadth.pct_above_50dma)}%
          </div>
          <div className="w-full bg-gray-100 rounded-full h-1.5 mt-2">
            <div
              className="bg-blue-500 h-1.5 rounded-full"
              style={{
                width: `${parseFloat(breadth.pct_above_50dma || "0")}%`,
              }}
            />
          </div>
        </div>

        {/* 52W H/L */}
        <div className="rounded-lg border p-4">
          <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">
            52W High / Low
          </div>
          <div className="text-xl font-bold">
            <span className="text-emerald-600">{breadth.new_52w_highs}</span>
            <span className="text-gray-400 mx-1">/</span>
            <span className="text-red-600">{breadth.new_52w_lows}</span>
          </div>
        </div>
      </div>

      {/* Regime sub-scores */}
      <div className="flex gap-4 text-xs text-gray-600">
        <span>
          Breadth: <strong>{formatDecimal(regime.breadth_score)}</strong>
        </span>
        <span>
          Momentum: <strong>{formatDecimal(regime.momentum_score)}</strong>
        </span>
        <span>
          Volume: <strong>{formatDecimal(regime.volume_score)}</strong>
        </span>
        <span>
          Global: <strong>{formatDecimal(regime.global_score)}</strong>
        </span>
        <span>
          FII: <strong>{formatDecimal(regime.fii_score)}</strong>
        </span>
      </div>
    </div>
  );
}
