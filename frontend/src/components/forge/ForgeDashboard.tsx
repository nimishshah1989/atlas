"use client";

import { useEffect, useState } from "react";
import ChunkTable, { type ForgeChunk } from "./ChunkTable";
import QualityScores, { type QualityReport } from "./QualityScores";
import LogTail, { type LogPayload } from "./LogTail";

type ForgeState = {
  now: string;
  chunks: ForgeChunk[];
  quality: QualityReport | null;
  log: LogPayload | null;
};

export default function ForgeDashboard() {
  const [data, setData] = useState<ForgeState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const res = await fetch("/forge/api", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as ForgeState;
        if (alive) {
          setData(json);
          setError(null);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "load failed");
      }
    };
    load();
    const id = setInterval(load, 10_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const chunks = data?.chunks ?? [];
  const done = chunks.filter((c) => c.status === "DONE").length;
  const failed = chunks.filter((c) => c.status === "FAILED").length;
  const inProgress = chunks.filter((c) =>
    ["PLANNING", "IMPLEMENTING", "TESTING", "QUALITY_CHECK"].includes(c.status)
  ).length;
  const total = chunks.length;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div className="min-h-screen bg-[#f9f9f7] text-gray-900 p-6">
      <div className="max-w-[1400px] mx-auto space-y-5">
        <header className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              <span className="text-[#1D9E75]">ATLAS</span>
              <span className="text-gray-500 font-normal ml-2 text-base">
                Forge Build Dashboard
              </span>
            </h1>
            <p className="text-xs text-gray-500 mt-1 font-mono">
              auto-refresh 10s ·{" "}
              {data ? new Date(data.now).toLocaleString("en-IN") : "loading…"}
            </p>
          </div>
          {error && (
            <span className="text-xs text-red-600 font-mono">{error}</span>
          )}
        </header>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Stat label="Chunks" value={total} />
          <Stat label="Done" value={done} color="text-emerald-600" />
          <Stat label="In progress" value={inProgress} color="text-teal-600" />
          <Stat label="Failed" value={failed} color="text-red-600" />
          <Stat label="Progress" value={`${pct}%`} color="text-[#1D9E75]" />
        </div>

        <div className="w-full h-2 bg-gray-200 rounded">
          <div
            className="h-full bg-[#1D9E75] rounded transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 bg-white border rounded-lg p-4">
            <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500 mb-3">
              Chunk Status
            </h2>
            <ChunkTable chunks={chunks} />
          </div>
          <div className="bg-white border rounded-lg p-4">
            <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500 mb-3">
              Quality Scores
            </h2>
            <QualityScores report={data?.quality ?? null} />
          </div>
        </div>

        <div className="bg-white border rounded-lg p-4">
          <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500 mb-3">
            Latest Log
          </h2>
          <LogTail log={data?.log ?? null} />
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  color = "text-gray-900",
}: {
  label: string;
  value: number | string;
  color?: string;
}) {
  return (
    <div className="bg-white border rounded-lg px-4 py-3">
      <div className="text-[10px] font-mono uppercase tracking-widest text-gray-500">
        {label}
      </div>
      <div className={`text-2xl font-mono font-bold ${color}`}>{value}</div>
    </div>
  );
}
