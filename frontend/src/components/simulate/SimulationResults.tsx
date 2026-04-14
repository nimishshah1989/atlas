"use client";

import { useState } from "react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { type SimulationRunResponse, type SimulationConfig, type DailyValue, type TransactionRecord, saveSimulation } from "@/lib/api-simulate";
import { formatCurrency, formatPercent } from "@/lib/format";

function kpiColor(val: string, invert = false): string {
  const n = parseFloat(val);
  if (isNaN(n)) return "text-[#1a1a2e]";
  const v = invert ? -n : n;
  return v > 0 ? "text-[#1a9a6c]" : v < 0 ? "text-[#d44040]" : "text-[#1a1a2e]";
}

function KPI({ label, value, pct, cur, inv }: { label: string; value: string; pct?: boolean; cur?: boolean; inv?: boolean }) {
  const n = parseFloat(value);
  const display = cur && !isNaN(n) ? formatCurrency(n) : pct && !isNaN(n) ? formatPercent(n) : value;
  return (
    <div className="bg-white border border-[#e4e4e8] rounded p-3">
      <div className="text-xs text-[#6b6b80] mb-1">{label}</div>
      <div className={`text-base font-bold ${(pct || cur) ? kpiColor(value, inv) : "text-[#1a1a2e]"}`}>{display}</div>
    </div>
  );
}

function dateTick(d: string): string {
  const p = d.split("-");
  if (p.length < 2) return d;
  const m = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${m[parseInt(p[1],10)-1] ?? ""} ${p[0].slice(2)}`;
}

function actionLabel(a: string): string {
  return a === "sip_buy" ? "SIP Buy" : a === "lumpsum_buy" ? "Lumpsum" : a === "sell" ? "Sell" : "Redeploy";
}

function actionColor(a: string): string {
  return a === "sip_buy" ? "text-[#1a9a6c] bg-emerald-50" : a === "lumpsum_buy" ? "text-[#0d8a7a] bg-teal-50" : a === "sell" ? "text-[#d44040] bg-red-50" : "text-[#8a7235] bg-amber-50";
}

type SortK = keyof Pick<TransactionRecord, "date" | "action" | "amount" | "nav" | "units">;

interface Props { response: SimulationRunResponse; config: SimulationConfig }

export default function SimulationResults({ response, config }: Props) {
  const { result } = response;
  const { summary, daily_values, transactions, tax_summary } = result;
  const [sortKey, setSortKey] = useState<SortK>("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [saveName, setSaveName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [txPage, setTxPage] = useState(0);
  const PAGE = 50;

  const handleSort = (k: SortK) => { if (k === sortKey) setSortDir(d => d === "asc" ? "desc" : "asc"); else { setSortKey(k); setSortDir("desc"); } };

  const sorted = [...transactions].sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    const na = parseFloat(String(av)), nb = parseFloat(String(bv));
    if (!isNaN(na) && !isNaN(nb)) return sortDir === "desc" ? nb - na : na - nb;
    return sortDir === "desc" ? String(bv).localeCompare(String(av)) : String(av).localeCompare(String(bv));
  });

  const pages = Math.ceil(sorted.length / PAGE);
  const paged = sorted.slice(txPage * PAGE, (txPage + 1) * PAGE);
  const chart = daily_values.map((d: DailyValue) => ({ date: d.date, total: parseFloat(d.total), fv: parseFloat(d.fv) }));

  const handleSave = async () => {
    setSaving(true); setSaveMsg(null);
    try { await saveSimulation(saveName || null, config); setSaveMsg("Saved"); }
    catch (e: unknown) { setSaveMsg(`Failed: ${e instanceof Error ? e.message : String(e)}`); }
    finally { setSaving(false); }
  };

  const SI = ({ k }: { k: SortK }) => k === sortKey
    ? <span className="text-[#0d8a7a] ml-0.5">{sortDir === "desc" ? "↓" : "↑"}</span>
    : <span className="text-gray-300 ml-0.5">↕</span>;
  const TH = "px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-800 select-none whitespace-nowrap";
  const THL = "px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-800 select-none whitespace-nowrap";

  return (
    <div className="space-y-4">
      <div className="bg-white border border-[#e4e4e8] rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b bg-[#f9f9f7] flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[#1a1a2e]">Simulation Results</h2>
          <span className="text-xs text-[#9a9aad]">data as of {result.data_as_of?.split("T")[0]}</span>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-5 gap-3">
            <KPI label="Total Invested" value={summary.total_invested} cur />
            <KPI label="Final Value" value={summary.final_value} cur />
            <KPI label="XIRR" value={summary.xirr} pct />
            <KPI label="CAGR" value={summary.cagr} pct />
            <KPI label="vs Plain SIP" value={summary.vs_plain_sip} pct />
          </div>
          <div className="grid grid-cols-5 gap-3">
            <KPI label="vs Benchmark" value={summary.vs_benchmark} pct />
            <KPI label="Alpha" value={summary.alpha} pct />
            <KPI label="Max Drawdown" value={summary.max_drawdown} pct inv />
            <KPI label="Sharpe" value={summary.sharpe} />
            <KPI label="Sortino" value={summary.sortino} />
          </div>
        </div>
      </div>

      {chart.length > 0 && (
        <div className="bg-white border border-[#e4e4e8] rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b bg-[#f9f9f7]"><h2 className="text-sm font-semibold text-[#1a1a2e]">Portfolio Value Over Time</h2></div>
          <div className="p-4">
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={chart} margin={{ top: 4, right: 8, bottom: 0, left: 16 }}>
                <defs>
                  <linearGradient id="totalGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0d8a7a" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#0d8a7a" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e8" />
                <XAxis dataKey="date" tickFormatter={dateTick} tick={{ fontSize: 11, fill: "#9a9aad" }} interval="preserveStartEnd" />
                <YAxis tickFormatter={(v: number) => formatCurrency(v)} tick={{ fontSize: 11, fill: "#9a9aad" }} width={90} />
                <Tooltip formatter={(v: unknown, n: unknown) => [formatCurrency(Number(v ?? 0)), n === "total" ? "Total Portfolio" : "Fund Value"]} labelFormatter={(l: unknown) => `Date: ${String(l ?? "")}`} contentStyle={{ fontSize: 12, border: "1px solid #e4e4e8", borderRadius: 4 }} />
                <Area type="monotone" dataKey="total" stroke="#0d8a7a" strokeWidth={2} fill="url(#totalGrad)" dot={false} name="total" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="bg-white border border-[#e4e4e8] rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b bg-[#f9f9f7]"><h2 className="text-sm font-semibold text-[#1a1a2e]">Tax Summary</h2></div>
        <div className="p-4 grid grid-cols-5 gap-3">
          <KPI label="STCG Tax" value={tax_summary.stcg} cur inv />
          <KPI label="LTCG Tax" value={tax_summary.ltcg} cur inv />
          <KPI label="Total Tax" value={tax_summary.total_tax} cur inv />
          <KPI label="Post-Tax XIRR" value={tax_summary.post_tax_xirr} pct />
          <KPI label="Unrealized" value={tax_summary.unrealized} cur />
        </div>
      </div>

      {transactions.length > 0 && (
        <div className="bg-white border border-[#e4e4e8] rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b bg-[#f9f9f7] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[#1a1a2e]">Transaction Log</h2>
            <span className="text-xs text-[#9a9aad]">{transactions.length} transactions</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className={THL} onClick={() => handleSort("date")}>Date <SI k="date" /></th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">Action</th>
                  <th className={TH} onClick={() => handleSort("amount")}>Amount <SI k="amount" /></th>
                  <th className={TH} onClick={() => handleSort("nav")}>NAV <SI k="nav" /></th>
                  <th className={TH} onClick={() => handleSort("units")}>Units <SI k="units" /></th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">Tax</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {paged.map((tx, i) => (
                  <tr key={i} className="hover:bg-[#f9f9f7]">
                    <td className="px-3 py-2 text-xs text-gray-700 whitespace-nowrap">{tx.date}</td>
                    <td className="px-3 py-2"><span className={`text-xs px-1.5 py-0.5 rounded font-medium ${actionColor(tx.action)}`}>{actionLabel(tx.action)}</span></td>
                    <td className="px-3 py-2 text-xs text-right text-gray-800 whitespace-nowrap">{formatCurrency(parseFloat(tx.amount))}</td>
                    <td className="px-3 py-2 text-xs text-right text-gray-700 whitespace-nowrap">{parseFloat(tx.nav).toFixed(2)}</td>
                    <td className="px-3 py-2 text-xs text-right text-gray-700 whitespace-nowrap">{parseFloat(tx.units).toFixed(4)}</td>
                    <td className="px-3 py-2 text-xs text-right text-gray-500 whitespace-nowrap">{tx.tax_detail ? formatCurrency(parseFloat(tx.tax_detail.total_tax)) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pages > 1 && (
            <div className="px-4 py-2 border-t flex items-center justify-between text-xs text-gray-500">
              <span>Page {txPage + 1} of {pages} ({transactions.length} total)</span>
              <div className="flex gap-2">
                <button disabled={txPage === 0} onClick={() => setTxPage(p => p - 1)} className="px-2 py-1 border rounded disabled:opacity-40 hover:bg-gray-50">Prev</button>
                <button disabled={txPage === pages - 1} onClick={() => setTxPage(p => p + 1)} className="px-2 py-1 border rounded disabled:opacity-40 hover:bg-gray-50">Next</button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="bg-white border border-[#e4e4e8] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-[#1a1a2e] mb-3">Save this simulation</h3>
        <div className="flex items-center gap-3">
          <input type="text" value={saveName} onChange={e => setSaveName(e.target.value)} placeholder="Name (optional)" className="border border-[#e4e4e8] rounded px-2 py-1.5 text-sm focus:outline-none focus:border-[#0d8a7a] bg-white flex-1 max-w-xs" />
          <button onClick={handleSave} disabled={saving} className="px-4 py-1.5 text-sm font-medium bg-[#8a7235] text-white rounded hover:bg-[#7a6230] transition-colors disabled:opacity-50">{saving ? "Saving..." : "Save Config"}</button>
          {saveMsg && <span className={`text-xs ${saveMsg.startsWith("Failed") ? "text-red-600" : "text-[#1a9a6c]"}`}>{saveMsg}</span>}
        </div>
      </div>
    </div>
  );
}
