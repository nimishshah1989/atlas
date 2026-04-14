"use client";

import { useState } from "react";
import type {
  VersionResponse,
  VersionStatusEnum,
} from "@/lib/systemClient";
import ChunkRow from "./ChunkRow";

const STATUS_CHIP: Record<VersionStatusEnum | string, string> = {
  DONE: "text-emerald-700 bg-emerald-50 border-emerald-200",
  IN_PROGRESS: "text-teal-700 bg-teal-50 border-teal-200",
  PENDING: "text-gray-600 bg-gray-100 border-gray-200",
  PLANNED: "text-gray-500 bg-gray-50 border-gray-200",
  BLOCKED: "text-orange-700 bg-orange-50 border-orange-200",
  FAILED: "text-red-700 bg-red-50 border-red-200",
  EMPTY: "text-gray-400 bg-gray-50 border-gray-100",
};

export default function VersionCard({ version }: { version: VersionResponse }) {
  const [expanded, setExpanded] = useState(false);
  const statusClass =
    STATUS_CHIP[version.status] ?? "text-gray-500 bg-gray-50 border-gray-200";

  const rollupText =
    version.rollup.total === 0
      ? "0 chunks"
      : `${version.rollup.done}/${version.rollup.total} · ${version.rollup.pct}%`;

  return (
    <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
      <div
        className={`flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors ${
          expanded ? "border-b border-gray-100" : ""
        }`}
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="text-xs font-mono font-bold text-[#1D9E75] w-6 flex-shrink-0">
          {version.id}
        </span>
        <span className="text-sm font-medium text-gray-800 flex-1 min-w-0 truncate">
          {version.title}
        </span>
        <span className="text-xs font-mono text-gray-500 flex-shrink-0">
          {rollupText}
        </span>
        <span
          className={`text-[10px] font-mono uppercase px-1.5 py-0.5 rounded border flex-shrink-0 ${statusClass}`}
        >
          {version.status}
        </span>
        <span className="text-[10px] text-gray-400 font-mono flex-shrink-0 w-3 text-center">
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {expanded && (
        <div className="divide-y divide-gray-50">
          {version.chunks.length === 0 ? (
            <p className="px-4 py-3 text-xs text-gray-400 font-mono italic">
              No chunks yet — add them to roadmap.yaml
            </p>
          ) : (
            version.chunks.map((chunk) => (
              <ChunkRow key={chunk.id} chunk={chunk} />
            ))
          )}
        </div>
      )}
    </div>
  );
}
