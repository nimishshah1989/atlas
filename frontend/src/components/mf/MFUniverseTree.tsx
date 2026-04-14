"use client";

import { useEffect, useState } from "react";
import { getMfUniverse, type MFFund, type MFStaleness } from "@/lib/api-mf";
import { formatDecimal, formatCurrency, quadrantColor, quadrantBg, signColor } from "@/lib/format";

function StalenessTag({ staleness }: { staleness: MFStaleness }) {
  if (staleness.flag === "FRESH") return null;
  const cls = staleness.flag === "EXPIRED" ? "bg-red-50 text-red-700 border-red-200" : "bg-amber-50 text-amber-700 border-amber-200";
  return <span className={`text-xs px-1.5 py-0.5 rounded border ${cls}`}>{staleness.flag}</span>;
}

function FundRow({ fund, onSelect }: { fund: MFFund; onSelect: (id: string) => void }) {
  const q = fund.quadrant;
  return (
    <tr className="border-b hover:bg-gray-50 cursor-pointer transition-colors" onClick={() => onSelect(fund.mstar_id)}>
      <td className="px-3 py-2 text-sm font-medium text-gray-900 max-w-xs">
        <div className="truncate" title={fund.fund_name}>{fund.fund_name}</div>
        <div className="text-xs text-gray-400 truncate">{fund.amc_name}</div>
      </td>
      <td className="px-3 py-2 text-right text-sm text-gray-700">{formatCurrency(fund.nav)}</td>
      <td className={`px-3 py-2 text-right text-sm font-medium ${quadrantColor(q)}`}>{formatDecimal(fund.rs_composite)}</td>
      <td className="px-3 py-2 text-center">
        {q ? <span className={`text-xs px-1.5 py-0.5 rounded border ${quadrantBg(q)} ${quadrantColor(q)}`}>{q}</span> : <span className="text-gray-400">—</span>}
      </td>
      <td className={`px-3 py-2 text-right text-sm font-medium ${signColor(fund.manager_alpha)}`}>
        {fund.manager_alpha ? `${parseFloat(fund.manager_alpha) > 0 ? "+" : ""}${formatDecimal(fund.manager_alpha)}` : "—"}
      </td>
      <td className="px-3 py-2 text-right text-sm text-gray-600">{fund.expense_ratio ? `${formatDecimal(fund.expense_ratio)}%` : "—"}</td>
      <td className="px-3 py-2 text-center">
        {fund.is_index_fund ? <span className="text-xs px-1 py-0.5 bg-gray-100 text-gray-600 rounded">Index</span> : null}
      </td>
    </tr>
  );
}

export default function MFUniverseTree({ filterCategory, onSelectFund, onBack }: { filterCategory?: string; onSelectFund: (id: string, name: string) => void; onBack: () => void }) {
  const [allFunds, setAllFunds] = useState<MFFund[]>([]);
  const [staleness, setStaleness] = useState<MFStaleness | null>(null);
  const [dataAsOf, setDataAsOf] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    setLoading(true); setSearch("");
    getMfUniverse().then((res) => {
      const funds: MFFund[] = [];
      for (const broad of res.broad_categories)
        for (const cat of broad.categories)
          if (!filterCategory || cat.name === filterCategory) funds.push(...cat.funds);
      setAllFunds(funds); setStaleness(res.staleness); setDataAsOf(res.data_as_of);
    }).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, [filterCategory]);

  const filtered = allFunds.filter((f) => !search || f.fund_name.toLowerCase().includes(search.toLowerCase()) || f.amc_name.toLowerCase().includes(search.toLowerCase()));

  if (loading) return <div className="animate-pulse space-y-3">{[...Array(10)].map((_, i) => <div key={i} className="h-10 bg-gray-100 rounded" />)}</div>;
  if (error) return <div className="border rounded p-4 text-red-600 text-sm">Failed to load funds: {error}</div>;

  return (
    <div className="bg-white border rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="text-sm text-gray-500 hover:text-gray-800">← Back</button>
          <h2 className="text-sm font-semibold text-gray-700">{filterCategory ?? "All Funds"}</h2>
          <span className="text-xs text-gray-400">{filtered.length} fund{filtered.length !== 1 ? "s" : ""}</span>
          {staleness && <StalenessTag staleness={staleness} />}
        </div>
        <div className="flex items-center gap-3">
          {dataAsOf && <span className="text-xs text-gray-400">as of {dataAsOf}</span>}
          <input type="text" placeholder="Search funds..." value={search} onChange={(e) => setSearch(e.target.value)} className="text-sm border rounded px-2 py-1 w-48 focus:outline-none focus:border-[#1D9E75]" />
        </div>
      </div>
      {filtered.length === 0 ? (
        <div className="px-4 py-8 text-sm text-gray-400 text-center">No funds found{search ? ` for "${search}"` : " in this category"}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Fund</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">NAV</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">RS Score</th>
                <th className="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">Quadrant</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">Alpha</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">Exp Ratio</th>
                <th className="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">Type</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((fund) => <FundRow key={fund.mstar_id} fund={fund} onSelect={(id) => onSelectFund(id, fund.fund_name)} />)}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
