"use client";

import type { PortfolioFullAnalysisResponse } from "@/lib/api-portfolio";
import { formatCurrency, quadrantColor } from "@/lib/format";

export default function WeightedRsCard({
  analysis,
}: {
  analysis: PortfolioFullAnalysisResponse;
}) {
  const { portfolio } = analysis;
  const rs = portfolio.weighted_rs ? parseFloat(portfolio.weighted_rs) : null;
  const dist = portfolio.quadrant_distribution;
  const total =
    (dist.LEADING ?? 0) +
    (dist.IMPROVING ?? 0) +
    (dist.WEAKENING ?? 0) +
    (dist.LAGGING ?? 0) +
    (dist.UNKNOWN ?? 0);

  const quadrants: { key: string; label: string; color: string }[] = [
    { key: "LEADING", label: "Leading", color: "bg-emerald-500" },
    { key: "IMPROVING", label: "Improving", color: "bg-blue-500" },
    { key: "WEAKENING", label: "Weakening", color: "bg-amber-500" },
    { key: "LAGGING", label: "Lagging", color: "bg-red-500" },
  ];

  return (
    <div className="bg-white border border-[#e4e4e8] rounded-lg p-5">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
        Portfolio RS Score
      </h3>
      <div className="flex items-end gap-4 mb-4">
        <div
          className={`text-4xl font-bold ${
            rs !== null
              ? quadrantColor(
                  portfolio.weighted_rs
                    ? rs >= 60
                      ? "LEADING"
                      : rs >= 50
                      ? "IMPROVING"
                      : rs >= 40
                      ? "WEAKENING"
                      : "LAGGING"
                    : null
                )
              : "text-gray-400"
          }`}
        >
          {rs !== null ? rs.toFixed(1) : "\u2014"}
        </div>
        <div className="text-xs text-gray-400 mb-1">weighted RS</div>
      </div>

      {/* Quadrant distribution bar */}
      {total > 0 && (
        <div className="space-y-2">
          <div className="flex h-2 rounded overflow-hidden gap-px">
            {quadrants.map(({ key, color }) => {
              const count = dist[key] ?? 0;
              const pct = (count / total) * 100;
              if (pct === 0) return null;
              return (
                <div
                  key={key}
                  className={`${color} h-full`}
                  style={{ width: `${pct}%` }}
                />
              );
            })}
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {quadrants.map(({ key, label, color }) => {
              const count = dist[key] ?? 0;
              return (
                <div
                  key={key}
                  className="flex items-center gap-1 text-xs text-gray-600"
                >
                  <div className={`w-2 h-2 rounded-sm ${color}`} />
                  <span>
                    {label}: {count}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="mt-3 pt-3 border-t border-[#e4e4e8] grid grid-cols-3 gap-2 text-xs">
        <div>
          <div className="text-gray-400">Total Value</div>
          <div className="font-medium text-gray-900 mt-0.5">
            {formatCurrency(parseFloat(portfolio.total_value))}
          </div>
        </div>
        <div>
          <div className="text-gray-400">Holdings</div>
          <div className="font-medium text-gray-900 mt-0.5">
            {portfolio.holdings_count}
          </div>
        </div>
        <div>
          <div className="text-gray-400">Mapped</div>
          <div className="font-medium text-gray-900 mt-0.5">
            {portfolio.mapped_count}/{portfolio.holdings_count}
          </div>
        </div>
      </div>
    </div>
  );
}
