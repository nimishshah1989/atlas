"use client";

import { useEffect, useState } from "react";
import { type SimulationListItem, type SimulationConfig, listSimulations, deleteSimulation } from "@/lib/api-simulate";

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const m = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${String(d.getDate()).padStart(2,"0")}-${m[d.getMonth()]}-${d.getFullYear()}`;
}

function sigBadge(s: string): string {
  const c: Record<string,string> = {
    breadth: "bg-blue-50 text-blue-700 border-blue-200",
    mcclellan: "bg-purple-50 text-purple-700 border-purple-200",
    rs: "bg-emerald-50 text-emerald-700 border-emerald-200",
    pe: "bg-amber-50 text-amber-700 border-amber-200",
    regime: "bg-rose-50 text-rose-700 border-rose-200",
    sector_rs: "bg-teal-50 text-teal-700 border-teal-200",
    mcclellan_summation: "bg-indigo-50 text-indigo-700 border-indigo-200",
    combined: "bg-gray-100 text-gray-700 border-gray-300",
  };
  return c[s] ?? "bg-gray-100 text-gray-700 border-gray-300";
}

interface Props { onLoad: (c: SimulationConfig) => void; refreshTrigger?: number }

export default function SavedSimulations({ onLoad, refreshTrigger }: Props) {
  const [sims, setSims] = useState<SimulationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = () => {
    setLoading(true); setError(null);
    listSimulations().then(r => setSims(r.simulations)).catch(e => setError(String(e))).finally(() => setLoading(false));
  };

  // load is intentionally not listed as a dependency — it's stable and we only want to re-run on refreshTrigger
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [refreshTrigger]);

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try { await deleteSimulation(id); setSims(p => p.filter(s => s.id !== id)); }
    catch (e: unknown) { setError(`Delete failed: ${e instanceof Error ? e.message : String(e)}`); }
    finally { setDeletingId(null); }
  };

  const Panel = ({ children }: { children: React.ReactNode }) => (
    <div className="bg-white border border-[#e4e4e8] rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b bg-[#f9f9f7] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-[#1a1a2e]">Saved Simulations</h2>
          <span className="text-xs text-[#9a9aad]">{sims.length} saved</span>
        </div>
        <button onClick={load} className="text-xs text-[#0d8a7a] hover:underline">Refresh</button>
      </div>
      {error && <div className="mx-4 mt-3 border border-red-200 bg-red-50 rounded p-2 text-sm text-red-700">{error}</div>}
      {children}
    </div>
  );

  if (loading) return (
    <Panel>
      <div className="p-4 animate-pulse space-y-2">{[...Array(3)].map((_, i) => <div key={i} className="h-12 bg-gray-100 rounded" />)}</div>
    </Panel>
  );

  if (!sims.length && !error) return (
    <Panel><div className="p-8 text-center text-sm text-[#9a9aad]">No saved simulations yet. Run a simulation and save the config.</div></Panel>
  );

  return (
    <Panel>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              {["Name / Instrument","Signal","Date Range","Flags","Saved","Actions"].map((h, i) => (
                <th key={h} className={`px-3 py-2 ${i >= 3 ? "text-right" : "text-left"} text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sims.map(sim => (
              <tr key={sim.id} className="hover:bg-[#f9f9f7]">
                <td className="px-3 py-2">
                  <div className="font-medium text-[#1a1a2e] text-xs">{sim.name ?? sim.config.instrument}</div>
                  {sim.name && <div className="text-xs text-[#9a9aad]">{sim.config.instrument}</div>}
                </td>
                <td className="px-3 py-2"><span className={`text-xs px-1.5 py-0.5 rounded border font-medium ${sigBadge(sim.config.signal)}`}>{sim.config.signal}</span></td>
                <td className="px-3 py-2 text-xs text-[#6b6b80] whitespace-nowrap">{sim.config.start_date} — {sim.config.end_date}</td>
                <td className="px-3 py-2">
                  {sim.is_auto_loop && <span className="text-xs px-1.5 py-0.5 rounded border bg-teal-50 text-teal-700 border-teal-200 font-medium">Auto-Loop</span>}
                </td>
                <td className="px-3 py-2 text-xs text-right text-[#9a9aad] whitespace-nowrap">{fmtDate(sim.created_at)}</td>
                <td className="px-3 py-2 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => onLoad(sim.config)} className="text-xs px-2 py-1 border border-[#0d8a7a] text-[#0d8a7a] rounded hover:bg-teal-50">Load</button>
                    <button onClick={() => handleDelete(sim.id)} disabled={deletingId === sim.id} className="text-xs px-2 py-1 border border-red-200 text-red-600 rounded hover:bg-red-50 disabled:opacity-40">{deletingId === sim.id ? "..." : "Delete"}</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
