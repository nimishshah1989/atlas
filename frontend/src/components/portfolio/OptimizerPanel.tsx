"use client";

import { useState } from "react";
import type { PortfolioOptimizationResponse } from "@/lib/api-portfolio";
import { formatPercent, formatDecimal } from "@/lib/format";
import { fmtWeight } from "./format-helpers";

export default function OptimizerPanel({
  optimization,
}: {
  optimization: PortfolioOptimizationResponse;
}) {
  const [activeModel, setActiveModel] = useState(0);

  if (optimization.models.length === 0) {
    return (
      <div className="text-sm text-gray-400 text-center py-8">
        Optimization not available — insufficient mapped holdings.
      </div>
    );
  }

  const model = optimization.models[activeModel];

  return (
    <div>
      {/* Model tabs */}
      <div className="flex gap-2 mb-4">
        {optimization.models.map((m, i) => (
          <button
            key={m.model}
            onClick={() => setActiveModel(i)}
            className={`px-3 py-1 text-xs font-medium rounded border transition-colors ${
              activeModel === i
                ? "bg-[#1D9E75] text-white border-[#1D9E75]"
                : "bg-white text-gray-600 border-[#e4e4e8] hover:border-[#1D9E75]"
            }`}
          >
            {m.model === "mean_variance" ? "Mean-Variance" : "HRP"}
          </button>
        ))}
      </div>

      {/* Model stats */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gray-50 rounded p-3">
          <div className="text-xs text-gray-400">Exp. Return</div>
          <div className="text-sm font-semibold text-gray-900 mt-0.5">
            {model.expected_return
              ? formatPercent(parseFloat(model.expected_return) * 100)
              : "\u2014"}
          </div>
        </div>
        <div className="bg-gray-50 rounded p-3">
          <div className="text-xs text-gray-400">Exp. Risk</div>
          <div className="text-sm font-semibold text-gray-900 mt-0.5">
            {model.expected_risk
              ? formatPercent(parseFloat(model.expected_risk) * 100)
              : "\u2014"}
          </div>
        </div>
        <div className="bg-gray-50 rounded p-3">
          <div className="text-xs text-gray-400">Sharpe</div>
          <div className="text-sm font-semibold text-gray-900 mt-0.5">
            {model.sharpe_ratio ? formatDecimal(model.sharpe_ratio) : "\u2014"}
          </div>
        </div>
      </div>

      {/* Weights table */}
      <div className="overflow-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-[#e4e4e8]">
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500">
                Scheme
              </th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">
                Current
              </th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">
                Optimized
              </th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">
                Change
              </th>
            </tr>
          </thead>
          <tbody>
            {model.weights.map((w) => {
              const change = parseFloat(w.weight_change);
              return (
                <tr
                  key={w.mstar_id}
                  className="border-b border-[#f4f4f6] hover:bg-gray-50"
                >
                  <td className="px-3 py-2 text-xs text-gray-900 max-w-[180px]">
                    <div className="truncate">{w.scheme_name}</div>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-xs text-gray-700">
                    {fmtWeight(w.current_weight)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-xs text-gray-700">
                    {fmtWeight(w.optimized_weight)}
                  </td>
                  <td
                    className={`px-3 py-2 text-right tabular-nums text-xs font-semibold ${
                      isNaN(change)
                        ? ""
                        : change > 0
                        ? "text-emerald-600"
                        : change < 0
                        ? "text-red-600"
                        : "text-gray-500"
                    }`}
                  >
                    {isNaN(change)
                      ? "\u2014"
                      : `${change > 0 ? "+" : ""}${(change * 100).toFixed(1)}%`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* SEBI constraints */}
      {model.constraints_applied.length > 0 && (
        <div className="mt-4">
          <div className="text-xs font-semibold text-gray-500 mb-2">
            SEBI Constraints Applied
          </div>
          <div className="space-y-1">
            {model.constraints_applied.map((c) => (
              <div
                key={c.constraint_id}
                className={`flex items-center justify-between text-xs px-3 py-1.5 rounded ${
                  c.is_violated
                    ? "bg-red-50 border border-red-200"
                    : c.is_binding
                    ? "bg-amber-50 border border-amber-200"
                    : "bg-gray-50 border border-[#e4e4e8]"
                }`}
              >
                <span className="text-gray-700">{c.description}</span>
                <span className="tabular-nums text-gray-500">
                  {parseFloat(c.value) <= 1
                    ? fmtWeight(c.value)
                    : formatDecimal(c.value)}
                  {c.is_violated && (
                    <span className="ml-1 text-red-600 font-semibold">
                      VIOLATED
                    </span>
                  )}
                  {c.is_binding && !c.is_violated && (
                    <span className="ml-1 text-amber-600">binding</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
