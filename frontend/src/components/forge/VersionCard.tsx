"use client";

import { useState } from "react";
import type {
  VersionResponse,
  VersionStatusEnum,
  ChunkResponse,
  MilestoneResponse,
} from "@/lib/systemClient";
import StepCheckRow from "./StepCheckRow";

// ---------------------------------------------------------------------------
// Status colors
// ---------------------------------------------------------------------------

const STATUS_CHIP: Record<VersionStatusEnum | string, string> = {
  DONE: "text-emerald-700 bg-emerald-50 border-emerald-200",
  IN_PROGRESS: "text-teal-700 bg-teal-50 border-teal-200",
  PENDING: "text-gray-600 bg-gray-100 border-gray-200",
  PLANNED: "text-gray-500 bg-gray-50 border-gray-200",
  BLOCKED: "text-orange-700 bg-orange-50 border-orange-200",
  FAILED: "text-red-700 bg-red-50 border-red-200",
  EMPTY: "text-gray-400 bg-gray-50 border-gray-100",
};

const CHUNK_STATUS_DOT: Record<string, string> = {
  DONE: "bg-emerald-500",
  IN_PROGRESS: "bg-teal-500",
  PENDING: "bg-gray-300",
  PLANNED: "bg-gray-300",
  BLOCKED: "bg-orange-400",
  FAILED: "bg-red-500",
};

// Process-strip milestone colors (R/A/G + neutral pending).
const MILESTONE_DOT: Record<string, string> = {
  green: "bg-emerald-500",
  amber: "bg-amber-400",
  red: "bg-red-500",
  pending: "bg-gray-200",
};

// Short two-letter labels stacked above each dot. Keep in sync with the
// backend `milestones` order in backend/routes/system_roadmap.py.
const MILESTONE_SHORT: Record<string, string> = {
  planned: "PL",
  implemented: "IM",
  tests: "TS",
  quality_gate: "QG",
  post_chunk: "PC",
  wiki: "WK",
  memory: "MM",
};

function MilestoneStrip({ milestones }: { milestones: MilestoneResponse[] }) {
  if (!milestones || milestones.length === 0) return null;
  const greens = milestones.filter((m) => m.status === "green").length;
  return (
    <span
      className="inline-flex items-center gap-0.5 ml-1 flex-shrink-0"
      title={`${greens}/${milestones.length} milestones green`}
    >
      {milestones.map((m) => (
        <span
          key={m.name}
          className={`w-1.5 h-1.5 rounded-full ${
            MILESTONE_DOT[m.status] ?? "bg-gray-200"
          }`}
          title={`${MILESTONE_SHORT[m.name] ?? m.name} (${m.name}): ${m.status}${
            m.detail ? ` — ${m.detail}` : ""
          }`}
        />
      ))}
      <span className="text-[9px] font-mono text-gray-400 ml-0.5">
        {greens}/{milestones.length}
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

// ---------------------------------------------------------------------------
// ChunkRow (expandable)
// ---------------------------------------------------------------------------

function ChunkRow({ chunk }: { chunk: ChunkResponse }) {
  const [expanded, setExpanded] = useState(false);
  const dotColor = CHUNK_STATUS_DOT[chunk.status] ?? "bg-gray-300";
  const hasError = Boolean(chunk.last_error);
  const canExpand = chunk.steps.length > 0 || hasError;

  return (
    <div>
      <div
        className="flex items-center gap-2 py-1.5 pl-4 pr-3 rounded hover:bg-gray-50 cursor-pointer group"
        onClick={() => setExpanded((v) => !v)}
      >
        <span
          className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotColor}`}
        />
        <span className="text-[10px] font-mono text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded flex-shrink-0">
          {chunk.id}
        </span>
        <span className="text-xs text-gray-700 flex-1 truncate">
          {chunk.title || <span className="italic text-gray-400">untitled</span>}
        </span>
        {chunk.attempts > 0 && (
          <span
            className={`text-[10px] font-mono px-1 rounded flex-shrink-0 ${
              hasError
                ? "text-red-700 bg-red-50"
                : "text-gray-500 bg-gray-100"
            }`}
            title={`${chunk.attempts} attempt${chunk.attempts === 1 ? "" : "s"}`}
          >
            ×{chunk.attempts}
          </span>
        )}
        {hasError && (
          <span
            className="text-[10px] font-mono text-red-600 bg-red-50 px-1 rounded flex-shrink-0"
            title="last_error present — click to expand"
          >
            ERR
          </span>
        )}
        {chunk.last_shipped_at && (
          <span
            className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
              chunk.last_ship_ok ? "bg-emerald-500" : "bg-red-500"
            }`}
            title={`last forge-ship: ${chunk.last_shipped_at}${
              chunk.last_ship_ok
                ? " — tests + gate + memory all ✓"
                : " — FAILED, re-run scripts/forge-ship.sh"
            }`}
          />
        )}
        {chunk.milestones && chunk.milestones.length > 0 && (
          <MilestoneStrip milestones={chunk.milestones} />
        )}
        <span className="text-[10px] font-mono text-gray-400 flex-shrink-0">
          {timeAgo(chunk.updated_at)}
        </span>
        {canExpand && (
          <span className="text-[10px] text-gray-400 font-mono ml-1 flex-shrink-0">
            {expanded ? "▲" : "▼"}
          </span>
        )}
      </div>
      {expanded && (
        <div className="pb-1 space-y-0.5">
          {hasError && (
            <pre className="ml-6 mr-3 my-1 text-[10px] font-mono text-red-700 bg-red-50 border border-red-100 rounded px-2 py-1 whitespace-pre-wrap break-words">
              {chunk.last_error}
            </pre>
          )}
          {chunk.steps.map((step) => (
            <StepCheckRow key={step.id} step={step} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// VersionCard
// ---------------------------------------------------------------------------

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
      {/* Version header */}
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

      {/* Chunk list */}
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
