"use client";

import type { PortfolioAttributionResponse } from "@/lib/api-portfolio";
import { fmtWeight, fmtEffect, effectColor } from "./format-helpers";

export default function AttributionPanel({
  attribution,
}: {
  attribution: PortfolioAttributionResponse;
}) {
  const { categories, summary } = attribution;

  return (
    <div>
      {!attribution.returns_available && (
        <div className="mb-3 bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-700">
          Insufficient NAV history to compute category returns. Effects shown as
          0.
        </div>
      )}
      <div className="overflow-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-[#e4e4e8]">
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500">
                Category
              </th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">
                Port. Wt
              </th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">
                Bench. Wt
              </th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">
                Alloc.
              </th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">
                Selection
              </th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">
                Interaction
              </th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">
                Total
              </th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">
                #
              </th>
            </tr>
          </thead>
          <tbody>
            {categories.map((cat) => (
              <tr
                key={cat.category_name}
                className="border-b border-[#f4f4f6] hover:bg-gray-50"
              >
                <td className="px-3 py-2 text-gray-900 text-xs font-medium">
                  {cat.category_name}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 text-xs">
                  {fmtWeight(cat.portfolio_weight)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 text-xs">
                  {fmtWeight(cat.benchmark_weight)}
                </td>
                <td
                  className={`px-3 py-2 text-right tabular-nums text-xs ${effectColor(cat.allocation_effect)}`}
                >
                  {fmtEffect(cat.allocation_effect)}
                </td>
                <td
                  className={`px-3 py-2 text-right tabular-nums text-xs ${effectColor(cat.selection_effect)}`}
                >
                  {fmtEffect(cat.selection_effect)}
                </td>
                <td
                  className={`px-3 py-2 text-right tabular-nums text-xs ${effectColor(cat.interaction_effect)}`}
                >
                  {fmtEffect(cat.interaction_effect)}
                </td>
                <td
                  className={`px-3 py-2 text-right tabular-nums text-xs font-semibold ${effectColor(cat.total_effect)}`}
                >
                  {fmtEffect(cat.total_effect)}
                </td>
                <td className="px-3 py-2 text-right text-xs text-gray-400">
                  {cat.holding_count}
                </td>
              </tr>
            ))}
          </tbody>
          {/* Summary row */}
          <tfoot>
            <tr className="border-t-2 border-[#e4e4e8] bg-gray-50">
              <td className="px-3 py-2 text-xs font-bold text-gray-900">
                Total
              </td>
              <td colSpan={2} />
              <td
                className={`px-3 py-2 text-right tabular-nums text-xs font-bold ${effectColor(summary.total_allocation_effect)}`}
              >
                {fmtEffect(summary.total_allocation_effect)}
              </td>
              <td
                className={`px-3 py-2 text-right tabular-nums text-xs font-bold ${effectColor(summary.total_selection_effect)}`}
              >
                {fmtEffect(summary.total_selection_effect)}
              </td>
              <td
                className={`px-3 py-2 text-right tabular-nums text-xs font-bold ${effectColor(summary.total_interaction_effect)}`}
              >
                {fmtEffect(summary.total_interaction_effect)}
              </td>
              <td
                className={`px-3 py-2 text-right tabular-nums text-xs font-bold ${effectColor(summary.total_active_return)}`}
              >
                {fmtEffect(summary.total_active_return)}
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
      <div className="mt-2 text-[10px] text-gray-400">{summary.formula}</div>
    </div>
  );
}
