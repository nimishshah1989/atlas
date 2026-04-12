"use client";

import { useEffect, useState } from "react";
import { getUniverse, type StockSummary, type SectorGroup } from "@/lib/api";
import {
  formatDecimal,
  formatCurrency,
  quadrantColor,
  quadrantBg,
  signColor,
} from "@/lib/format";

export default function StockTable({
  sector,
  onSelectStock,
  onBack,
}: {
  sector: string;
  onSelectStock: (symbol: string) => void;
  onBack: () => void;
}) {
  const [stocks, setStocks] = useState<StockSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<string>("rs_composite");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [search, setSearch] = useState("");

  useEffect(() => {
    setLoading(true);
    getUniverse({ sector })
      .then((res) => {
        const allStocks = res.sectors.flatMap((sg) => sg.stocks);
        setStocks(allStocks);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [sector]);

  const handleSort = (key: string) => {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const filtered = stocks.filter(
    (s) =>
      s.symbol.toLowerCase().includes(search.toLowerCase()) ||
      s.company_name.toLowerCase().includes(search.toLowerCase())
  );

  const sorted = [...filtered].sort((a, b) => {
    const av = (a as unknown as Record<string, unknown>)[sortKey];
    const bv = (b as unknown as Record<string, unknown>)[sortKey];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    const na = typeof av === "string" ? parseFloat(av) : (av as number);
    const nb = typeof bv === "string" ? parseFloat(bv) : (bv as number);
    if (isNaN(na)) return 1;
    if (isNaN(nb)) return -1;
    return sortDir === "desc" ? nb - na : na - nb;
  });

  const SH = ({
    label,
    field,
    className = "",
  }: {
    label: string;
    field: string;
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
        {[...Array(15)].map((_, i) => (
          <div key={i} className="h-8 bg-gray-100 rounded" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="text-sm text-gray-500 hover:text-gray-800 flex items-center gap-1"
        >
          ← Sectors
        </button>
        <h2 className="text-lg font-semibold text-gray-800">{sector}</h2>
        <span className="text-xs text-gray-500">{stocks.length} stocks</span>
      </div>

      <input
        type="text"
        placeholder="Search symbol or company..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full max-w-sm px-3 py-1.5 border rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-[#1D9E75]"
      />

      <div className="overflow-x-auto border rounded-lg">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50 sticky top-0">
            <tr>
              <SH label="Symbol" field="symbol" className="text-left" />
              <SH label="Company" field="company_name" className="text-left" />
              <SH label="Close" field="close" />
              <SH label="RS" field="rs_composite" />
              <SH label="Mom" field="rs_momentum" />
              <SH label="Quad" field="quadrant" />
              <SH label="RSI" field="rsi_14" />
              <SH label="ADX" field="adx_14" />
              <SH label=">200d" field="above_200dma" />
              <SH label=">50d" field="above_50dma" />
              <SH label="Beta" field="beta_nifty" />
              <SH label="Sharpe" field="sharpe_1y" />
              <SH label="MF#" field="mf_holder_count" />
              <SH label="Cap" field="cap_category" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((s) => (
              <tr
                key={s.id}
                className="hover:bg-gray-50 cursor-pointer"
                onClick={() => onSelectStock(s.symbol)}
              >
                <td className="px-2 py-1.5 font-medium text-[#1D9E75] whitespace-nowrap">
                  {s.symbol}
                </td>
                <td className="px-2 py-1.5 text-gray-700 max-w-[200px] truncate">
                  {s.company_name}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatCurrency(s.close)}
                </td>
                <td
                  className={`px-2 py-1.5 text-right tabular-nums font-medium ${signColor(s.rs_composite)}`}
                >
                  {formatDecimal(s.rs_composite)}
                </td>
                <td
                  className={`px-2 py-1.5 text-right tabular-nums ${signColor(s.rs_momentum)}`}
                >
                  {formatDecimal(s.rs_momentum)}
                </td>
                <td className="px-2 py-1.5 text-center">
                  <span
                    className={`text-xs px-1.5 py-0.5 rounded border ${quadrantBg(s.quadrant)} ${quadrantColor(s.quadrant)}`}
                  >
                    {s.quadrant || "—"}
                  </span>
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatDecimal(s.rsi_14, 1)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatDecimal(s.adx_14, 1)}
                </td>
                <td className="px-2 py-1.5 text-center">
                  {s.above_200dma === true ? (
                    <span className="text-emerald-500">●</span>
                  ) : s.above_200dma === false ? (
                    <span className="text-red-500">●</span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-2 py-1.5 text-center">
                  {s.above_50dma === true ? (
                    <span className="text-emerald-500">●</span>
                  ) : s.above_50dma === false ? (
                    <span className="text-red-500">●</span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {formatDecimal(s.beta_nifty)}
                </td>
                <td
                  className={`px-2 py-1.5 text-right tabular-nums ${signColor(s.sharpe_1y)}`}
                >
                  {formatDecimal(s.sharpe_1y)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {s.mf_holder_count ?? "—"}
                </td>
                <td className="px-2 py-1.5 text-center text-xs text-gray-500">
                  {s.cap_category || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
