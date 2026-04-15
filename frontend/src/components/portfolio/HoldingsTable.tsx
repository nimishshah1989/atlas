"use client";

import { useState, useMemo } from "react";
import type { HoldingAnalysis } from "@/lib/api-portfolio";
import {
  formatCurrency,
  formatPercent,
  formatDecimal,
  quadrantColor,
  quadrantBg,
  signColor,
} from "@/lib/format";
import { exportHoldingsCsv } from "./format-helpers";

export default function HoldingsTable({
  holdings,
  onDrillDown,
}: {
  holdings: HoldingAnalysis[];
  onDrillDown?: (holding: HoldingAnalysis) => void;
}) {
  const [sortKey, setSortKey] = useState<string>("weight_pct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const sorted = useMemo(() => {
    return [...holdings].sort((a, b) => {
      const numKeys = [
        "units",
        "nav",
        "current_value",
        "weight_pct",
        "return_1y",
        "rs_composite",
        "sharpe_ratio",
      ];
      const aRec = a as unknown as Record<string, string | null>;
      const bRec = b as unknown as Record<string, string | null>;
      let av: number | string = 0;
      let bv: number | string = 0;
      if (numKeys.includes(sortKey)) {
        av = parseFloat(aRec[sortKey] ?? "0") || 0;
        bv = parseFloat(bRec[sortKey] ?? "0") || 0;
      } else {
        av = aRec[sortKey] ?? "";
        bv = bRec[sortKey] ?? "";
      }
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [holdings, sortKey, sortDir]);

  function Th({
    label,
    k,
    right = false,
  }: {
    label: string;
    k: string;
    right?: boolean;
  }) {
    const active = sortKey === k;
    return (
      <th
        className={`px-3 py-2 text-xs font-semibold text-gray-500 cursor-pointer hover:text-gray-800 whitespace-nowrap ${
          right ? "text-right" : "text-left"
        } ${active ? "text-gray-900" : ""}`}
        onClick={() => handleSort(k)}
      >
        {label}
        {active ? (sortDir === "asc" ? " \u25B2" : " \u25BC") : ""}
      </th>
    );
  }

  return (
    <div className="overflow-auto">
      <div className="flex justify-end mb-2">
        <button
          onClick={() => exportHoldingsCsv(holdings)}
          className="text-xs text-[#1D9E75] border border-[#1D9E75] px-3 py-1 rounded hover:bg-[#1D9E75] hover:text-white transition-colors"
        >
          Export CSV
        </button>
      </div>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-[#e4e4e8]">
            <Th label="Scheme" k="scheme_name" />
            <Th label="Units" k="units" right />
            <Th label="NAV" k="nav" right />
            <Th label="Value" k="current_value" right />
            <Th label="Weight" k="weight_pct" right />
            <Th label="1Y Return" k="return_1y" right />
            <Th label="RS Score" k="rs_composite" right />
            <Th label="Quadrant" k="quadrant" />
            <Th label="Sharpe" k="sharpe_ratio" right />
          </tr>
        </thead>
        <tbody>
          {sorted.map((h) => (
            <tr
              key={h.holding_id}
              className="border-b border-[#f4f4f6] hover:bg-gray-50 cursor-pointer"
              onClick={() => onDrillDown?.(h)}
            >
              <td className="px-3 py-2 text-left max-w-[200px]">
                <div className="truncate text-gray-900 font-medium text-xs">
                  {h.scheme_name}
                </div>
                {h.mstar_id && (
                  <div className="text-[10px] text-gray-400">{h.mstar_id}</div>
                )}
              </td>
              <td className="px-3 py-2 text-right text-gray-700 tabular-nums">
                {formatDecimal(h.units, 3)}
              </td>
              <td className="px-3 py-2 text-right text-gray-700 tabular-nums">
                {formatCurrency(h.nav)}
              </td>
              <td className="px-3 py-2 text-right text-gray-700 tabular-nums font-medium">
                {formatCurrency(h.current_value)}
              </td>
              <td className="px-3 py-2 text-right text-gray-700 tabular-nums">
                {h.weight_pct
                  ? `${(parseFloat(h.weight_pct) * 100).toFixed(1)}%`
                  : "\u2014"}
              </td>
              <td
                className={`px-3 py-2 text-right tabular-nums ${signColor(h.return_1y)}`}
              >
                {formatPercent(h.return_1y)}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-gray-700">
                {formatDecimal(h.rs_composite)}
              </td>
              <td className="px-3 py-2">
                {h.quadrant ? (
                  <span
                    className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${quadrantBg(h.quadrant)} ${quadrantColor(h.quadrant)}`}
                  >
                    {h.quadrant}
                  </span>
                ) : (
                  <span className="text-gray-400 text-xs">{"\u2014"}</span>
                )}
              </td>
              <td
                className={`px-3 py-2 text-right tabular-nums ${signColor(h.sharpe_ratio)}`}
              >
                {formatDecimal(h.sharpe_ratio)}
              </td>
            </tr>
          ))}
          {sorted.length === 0 && (
            <tr>
              <td
                colSpan={9}
                className="px-3 py-8 text-center text-sm text-gray-400"
              >
                No holdings match the current filter.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
