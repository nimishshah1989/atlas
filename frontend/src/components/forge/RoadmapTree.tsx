"use client";

import { useState } from "react";
import type { RoadmapResponse } from "@/lib/systemClient";
import VersionCard from "./VersionCard";
import ChunkTable, { type ForgeChunk } from "./ChunkTable";

// ---------------------------------------------------------------------------
// RoadmapTree
// ---------------------------------------------------------------------------

export default function RoadmapTree({
  roadmap,
}: {
  roadmap: RoadmapResponse | null;
}) {
  const [view, setView] = useState<"roadmap" | "flat">("roadmap");

  // Build flat chunk list from roadmap data for the Flat view tab
  const flatChunks: ForgeChunk[] = roadmap
    ? roadmap.versions.flatMap((v) =>
        v.chunks.map((c) => ({
          id: c.id,
          title: c.title,
          status: c.status,
          attempts: c.attempts,
          last_error: c.last_error ?? null,
          started_at: null,
          finished_at: null,
          updated_at: c.updated_at ?? "",
        }))
      )
    : [];

  return (
    <div>
      {/* Tab toggle */}
      <div className="flex items-center gap-1 mb-3">
        <button
          onClick={() => setView("roadmap")}
          className={`text-xs font-mono px-3 py-1.5 rounded border transition-colors ${
            view === "roadmap"
              ? "bg-[#1D9E75] text-white border-[#1D9E75]"
              : "text-gray-600 border-gray-300 hover:border-gray-400"
          }`}
        >
          Roadmap
        </button>
        <button
          onClick={() => setView("flat")}
          className={`text-xs font-mono px-3 py-1.5 rounded border transition-colors ${
            view === "flat"
              ? "bg-[#1D9E75] text-white border-[#1D9E75]"
              : "text-gray-600 border-gray-300 hover:border-gray-400"
          }`}
        >
          Flat
        </button>
        {roadmap && (
          <span className="ml-2 text-[10px] font-mono text-gray-400">
            as of {roadmap.as_of.slice(0, 19).replace("T", " ")}
          </span>
        )}
      </div>

      {/* Roadmap view */}
      {view === "roadmap" && (
        <div className="space-y-2">
          {!roadmap && (
            <p className="text-xs text-gray-400 font-mono">
              Loading roadmap…
            </p>
          )}
          {roadmap?.versions.map((v) => (
            <VersionCard key={v.id} version={v} />
          ))}
        </div>
      )}

      {/* Flat view */}
      {view === "flat" && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <ChunkTable chunks={flatChunks} />
        </div>
      )}
    </div>
  );
}
