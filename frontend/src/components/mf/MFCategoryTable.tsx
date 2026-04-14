"use client";

import { useEffect, useState } from "react";
import { getMfCategories, type MFCategoryRow, type MFStaleness } from "@/lib/api-mf";
import { formatDecimal, quadrantColor, quadrantBg, signColor } from "@/lib/format";

type SortKey = keyof Pick<
  MFCategoryRow,
  "category_name" | "fund_count" | "avg_rs_composite" | "total_aum_cr" | "net_flow_cr" | "sip_flow_cr" | "manager_alpha_p50"
>;

function StalenessTag({ staleness }: { staleness: MFStaleness }) {
  if (staleness.flag === "FRESH") return null;
  const cls = staleness.flag === "EXPIRED" ? "bg-red-50 text-red-700 border-red-200" : "bg-amber-50 text-amber-700 border-amber-200";
  return <span className={`text-xs px-1.5 py-0.5 rounded border ml-2 ${cls}`}>{staleness.flag} ({staleness.age_minutes}m)</span>;
}

function SortIcon({ sortKey, k, sortDir }: { sortKey: SortKey; k: SortKey; sortDir: "asc" | "desc" }) {
  if (k !== sortKey) return <span className="text-gray-300 ml-0.5">↕</span>;
  return <span className="text-[#1D9E75] ml-0.5">{sortDir === "desc" ? "↓" : "↑"}</span>;
}

const TH = "px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-800 select-none whitespace-nowrap";
const THL = "px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-800 select-none whitespace-nowrap";

export default function MFCategoryTable({ onSelectCategory }: { onSelectCategory: (cat: string, broad: string) => void }) {
  const [categories, setCategories] = useState<MFCategoryRow[]>([]);
  const [staleness, setStaleness] = useState<MFStaleness | null>(null);
  const [dataAsOf, setDataAsOf] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("avg_rs_composite");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    setLoading(true);
    getMfCategories().then((res) => { setCategories(res.categories); setStaleness(res.staleness); setDataAsOf(res.data_as_of); })
      .catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, []);

  const handleSort = (k: SortKey) => { if (k === sortKey) setSortDir((d) => d === "asc" ? "desc" : "asc"); else { setSortKey(k); setSortDir("desc"); } };
  const sorted = [...categories].sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    const na = typeof av === "string" ? parseFloat(av) : (av as number);
    const nb = typeof bv === "string" ? parseFloat(bv) : (bv as number);
    if (!isNaN(na) && !isNaN(nb)) return sortDir === "desc" ? nb - na : na - nb;
    return sortDir === "desc" ? String(bv).localeCompare(String(av)) : String(av).localeCompare(String(bv));
  });

  if (loading) return <div className="animate-pulse space-y-3">{[...Array(9)].map((_, i) => <div key={i} className="h-10 bg-gray-100 rounded" />)}</div>;
  if (error) return <div className="border rounded p-4 text-red-600 text-sm">Failed to load MF categories: {error}</div>;

  const SI = ({ k }: { k: SortKey }) => <SortIcon sortKey={sortKey} k={k} sortDir={sortDir} />;

  return (
    <div className="bg-white border rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-gray-700">MF Categories</h2>
          <span className="text-xs text-gray-400">{categories.length} categories</span>
          {staleness && <StalenessTag staleness={staleness} />}
        </div>
        {dataAsOf && <span className="text-xs text-gray-400">as of {dataAsOf}</span>}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className={THL} onClick={() => handleSort("category_name")}>Category <SI k="category_name" /></th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">Broad</th>
              <th className={TH} onClick={() => handleSort("fund_count")}>Funds <SI k="fund_count" /></th>
              <th className={TH} onClick={() => handleSort("avg_rs_composite")}>Avg RS <SI k="avg_rs_composite" /></th>
              <th className="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">Quadrants</th>
              <th className={TH} onClick={() => handleSort("total_aum_cr")}>AUM <SI k="total_aum_cr" /></th>
              <th className={TH} onClick={() => handleSort("net_flow_cr")}>Net Flow <SI k="net_flow_cr" /></th>
              <th className={TH} onClick={() => handleSort("sip_flow_cr")}>SIP Flow <SI k="sip_flow_cr" /></th>
              <th className={TH} onClick={() => handleSort("manager_alpha_p50")}>Alpha p50 <SI k="manager_alpha_p50" /></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, idx) => {
              const q = row.quadrant_distribution;
              const dominant = Object.entries(q).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
              return (
                <tr key={row.category_name} className={`border-b hover:bg-gray-50 cursor-pointer transition-colors ${idx % 2 === 0 ? "" : "bg-gray-50/30"}`} onClick={() => onSelectCategory(row.category_name, row.broad_category)}>
                  <td className="px-3 py-2.5 font-medium text-gray-900">{row.category_name}</td>
                  <td className="px-3 py-2.5 text-xs text-gray-500">{row.broad_category}</td>
                  <td className="px-3 py-2.5 text-right text-gray-700">{row.fund_count}</td>
                  <td className={`px-3 py-2.5 text-right font-medium ${quadrantColor(dominant)}`}>{formatDecimal(row.avg_rs_composite)}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center justify-center gap-1">
                      {(["LEADING","IMPROVING","WEAKENING","LAGGING"] as const).map((qn) =>
                        (q[qn] ?? 0) > 0 ? <span key={qn} className={`text-xs px-1 py-0.5 rounded border ${quadrantBg(qn)} ${quadrantColor(qn)}`}>{q[qn]}</span> : null
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right text-gray-700">{row.total_aum_cr ? `₹${formatDecimal(parseFloat(row.total_aum_cr))} Cr` : "—"}</td>
                  <td className={`px-3 py-2.5 text-right font-medium ${signColor(row.net_flow_cr)}`}>{row.net_flow_cr ? `₹${formatDecimal(parseFloat(row.net_flow_cr))} Cr` : "—"}</td>
                  <td className="px-3 py-2.5 text-right text-gray-700">{row.sip_flow_cr ? `₹${formatDecimal(parseFloat(row.sip_flow_cr))} Cr` : "—"}</td>
                  <td className={`px-3 py-2.5 text-right font-medium ${signColor(row.manager_alpha_p50)}`}>{row.manager_alpha_p50 ? `${parseFloat(row.manager_alpha_p50) > 0 ? "+" : ""}${formatDecimal(row.manager_alpha_p50)}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
