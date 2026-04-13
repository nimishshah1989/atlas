"use client";

import { useEffect, useState } from "react";
import { getHeartbeat, type HeartbeatResponse } from "@/lib/systemClient";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 0) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

function ageColor(iso: string | null): "teal" | "amber" | "red" | "gray" {
  if (!iso) return "gray";
  const ageSeconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (ageSeconds > 6 * 3600) return "red";
  if (ageSeconds > 3600) return "amber";
  return "teal";
}

// ---------------------------------------------------------------------------
// Chip color classes
// ---------------------------------------------------------------------------

const CHIP_CLASSES: Record<"teal" | "amber" | "red" | "gray", string> = {
  teal: "border-[#1D9E75] bg-emerald-50 text-[#1D9E75]",
  amber: "border-amber-400 bg-amber-50 text-amber-700",
  red: "border-red-400 bg-red-50 text-red-700",
  gray: "border-gray-300 bg-gray-50 text-gray-500",
};

const DOT_CLASSES: Record<"teal" | "amber" | "red" | "gray", string> = {
  teal: "bg-[#1D9E75]",
  amber: "bg-amber-400",
  red: "bg-red-400",
  gray: "bg-gray-400",
};

// ---------------------------------------------------------------------------
// Individual chip
// ---------------------------------------------------------------------------

interface ChipProps {
  label: string;
  value: string;
  color: "teal" | "amber" | "red" | "gray";
  title?: string;
}

function Chip({ label, value, color, title }: ChipProps) {
  return (
    <div
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-mono whitespace-nowrap ${CHIP_CLASSES[color]}`}
      title={title}
    >
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${DOT_CLASSES[color]}`} />
      <span className="font-semibold">{label}</span>
      <span className="opacity-75">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Smoke chip helper
// ---------------------------------------------------------------------------

function smokeChip(hb: HeartbeatResponse): ChipProps {
  const { last_smoke_run_at, last_smoke_result, last_smoke_summary } = hb;

  if (!last_smoke_run_at && !last_smoke_summary) {
    return { label: "Smoke", value: "—", color: "gray" };
  }

  let color: "teal" | "amber" | "red" | "gray" = "gray";
  if (last_smoke_result === "red") {
    color = "red";
  } else if (last_smoke_result === "green") {
    // Even green can go amber/red if stale
    const ageColor_ = ageColor(last_smoke_run_at);
    color = ageColor_ === "teal" ? "teal" : ageColor_;
  }

  const summary = last_smoke_summary ?? "no summary";
  const ago = timeAgo(last_smoke_run_at);
  return {
    label: "Smoke",
    value: `${summary} · ${ago}`,
    color,
  };
}

// ---------------------------------------------------------------------------
// HeartbeatStrip
// ---------------------------------------------------------------------------

export default function HeartbeatStrip({
  initial,
}: {
  initial: HeartbeatResponse | null;
}) {
  const [hb, setHb] = useState<HeartbeatResponse | null>(initial);
  const [, setTick] = useState(0); // force re-render for time-ago updates

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const data = await getHeartbeat();
        if (alive) setHb(data);
      } catch {
        // keep stale data on error
      }
    };

    const pollId = setInterval(load, 30_000);
    const tickId = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => {
      alive = false;
      clearInterval(pollId);
      clearInterval(tickId);
    };
  }, []);

  if (!hb) {
    return (
      <div className="h-12 bg-white border-b border-gray-200 flex items-center px-4">
        <span className="text-xs text-gray-400 font-mono">Loading heartbeat…</span>
      </div>
    );
  }

  const chips: ChipProps[] = [
    {
      label: "MEMORY.md",
      value: timeAgo(hb.memory_md_mtime),
      color: ageColor(hb.memory_md_mtime),
      title: hb.memory_md_mtime ?? undefined,
    },
    {
      label: "Wiki",
      value: timeAgo(hb.wiki_index_mtime),
      color: ageColor(hb.wiki_index_mtime),
      title: hb.wiki_index_mtime ?? undefined,
    },
    {
      label: "state.db",
      value: timeAgo(hb.state_db_mtime),
      color: ageColor(hb.state_db_mtime),
      title: hb.state_db_mtime ?? undefined,
    },
    {
      label: "Quality",
      value:
        hb.last_quality_score !== null
          ? `${hb.last_quality_score} · ${timeAgo(hb.last_quality_run_at)}`
          : timeAgo(hb.last_quality_run_at),
      color: ageColor(hb.last_quality_run_at),
      title: hb.last_quality_run_at ?? undefined,
    },
    {
      label: "Backend",
      value:
        hb.backend_uptime_seconds < 60
          ? `${hb.backend_uptime_seconds}s up`
          : hb.backend_uptime_seconds < 3600
          ? `${Math.round(hb.backend_uptime_seconds / 60)}m up`
          : `${Math.round(hb.backend_uptime_seconds / 3600)}h up`,
      color: "teal",
    },
    smokeChip(hb),
  ];

  return (
    <div className="sticky top-0 z-40 h-auto min-h-12 bg-white border-b border-gray-200 flex flex-wrap items-center gap-2 px-4 py-2">
      {chips.map((chip) => (
        <Chip key={chip.label} {...chip} />
      ))}
    </div>
  );
}
