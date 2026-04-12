"use client";

import { useEffect, useState } from "react";
import { getSectors, type SectorMetrics } from "@/lib/api";
import {
  formatDecimal,
  formatPercent,
  quadrantColor,
  quadrantBg,
  signColor,
} from "@/lib/format";

type SortKey = keyof SectorMetrics;

export default function SectorTable({
  onSelectSector,
}: {
  onSelectSector: (sector: string) => void;
}) {
  const [sectors, setSectors] = useState<SectorMetrics[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>("avg_rs_composite");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [queryMs, setQueryMs] = useState<number | null>(null);

  useEffect(() => {
    getSectors()
      .then((res) => {
        setSectors(res.sectors);
        setQueryMs(res.meta.query_ms);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const sorted = [...sectors].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    const na = typeof av === "string" ? parseFloat(av) : (av as number);
    const nb = typeof bv === "string" ? parseFloat(bv) : (bv as number);
    if (isNaN(na)) return 1;
    if (isNaN(nb)) return -1;
    return sortDir === "desc" ? nb - na : na - nb;
  });

  const SortHeader = ({
    label,
    field,
    className = "",
  }: {
    label: string;
    field: SortKey;
    className?: string;
  }) => (
    <th
      className={`px-2 py-2 text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-800 whitespace-nowrap ${className}`}
      onClick={() => handleSort(field)}
    >
      {label}
      {sortKey === field && (
        <span className="ml-0.5">{sortDir === "desc" ? "↓" : "↑"}</span>
      )}
    </th>
  );

  if (loading) {
    return (
      <div className="animate-pulse space-y-2">
        {[...Array(10)].map((_, i) => (
          <div key={i} className="h-8 bg-gray-100 rounded" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">
          Sector RS Rankings
        </h2>
        <span className="text-xs text-gray-500">
          {sectors.length} sectors &middot;{" "}
          {queryMs !== null && `${(queryMs / 1000).toFixed(1)}s`}
        </span>
      </div>

      <div className="overflow-x-auto border rounded-lg">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50 sticky top-0">
            <tr>
              <SortHeader label="Sector" field="sector" className="text-left" />
              <SortHeader label="#" field="stock_count" />
              <SortHeader label="RS" field="avg_rs_composite" />
              <SortHeader label="Mom" field="avg_rs_momentum" />
              <SortHeader label="Quad" field="sector_quadrant" />
              <SortHeader label="%>200d" field="pct_above_200dma" />
              <SortHeader label="%>50d" field="pct_above_50dma" />
              <SortHeader label="RSI" field="avg_rsi_14" />
              <SortHeader label="%OB" field="pct_rsi_overbought" />
              <SortHeader label="%OS" field="pct_rsi_oversold" />
              <SortHeader label="ADX" field="avg_adx" />
              <SortHeader label="%Trend" field="pct_adx_trending" />
              <SortHeader label="%MACD+" field="pct_macd_bullish" />
              <SortHeader label="Beta" field="avg_beta" />
              <SortHeader label="Sharpe" field="avg_sharpe" />
              <SortHeader label="Vol" field="avg_volatility_20d" />
              <SortHeader label="MF" field="avg_mf_holders" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((s) => (
              <tr
                key={s.sector}
                className="hover:bg-gray-50 cursor-pointer"
                onClick={() => onSelectSector(s.sector)}
              >
                <td className="px-2 py-1.5 font-medium text-gray-900 whitespace-nowrap">
                  {s.sector}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {s.stock_count}
                </td>
                <td
                  className={`px-2 py-1.5 text-right tabular-nums font-medium ${signColor(s.avg_rs_composite)}`}
                >
                  {formatDecimal(s.avg_rs_composite)}
                </td>
                <td
                  className={`px-2 py-1.5 text-right tabular-nums ${signColor(s.avg_rs_momentum)}`}
                >
                  {formatDecimal(s.avg_rs_momentum)}
                </td>
                <td className="px-2 py-1.5 text-center">
                  <span
                    className={`text-xs px-1.5 py-0.5 rounded border ${quadrantBg(s.sector_quadrant)} ${quadrantColor(s.sector_quadrant)}`}
                  >
                    {s.sector_quadrant || "—"}
                  </span>
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatDecimal(s.pct_above_200dma, 1)}%
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatDecimal(s.pct_above_50dma, 1)}%
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatDecimal(s.avg_rsi_14, 1)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-red-500">
                  {formatDecimal(s.pct_rsi_overbought, 1)}%
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-emerald-500">
                  {formatDecimal(s.pct_rsi_oversold, 1)}%
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatDecimal(s.avg_adx, 1)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatDecimal(s.pct_adx_trending, 1)}%
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatDecimal(s.pct_macd_bullish, 1)}%
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatDecimal(s.avg_beta)}
                </td>
                <td
                  className={`px-2 py-1.5 text-right tabular-nums ${signColor(s.avg_sharpe)}`}
                >
                  {formatDecimal(s.avg_sharpe)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatDecimal(s.avg_volatility_20d, 1)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatDecimal(s.avg_mf_holders, 0)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
