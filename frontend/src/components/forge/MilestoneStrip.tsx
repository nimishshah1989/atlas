"use client";

import type { MilestoneResponse } from "@/lib/systemClient";

const MILESTONE_DOT: Record<string, string> = {
  green: "bg-emerald-500",
  amber: "bg-amber-400",
  red: "bg-red-500",
  pending: "bg-gray-200",
};

const MILESTONE_SHORT: Record<string, string> = {
  planned: "PL",
  implemented: "IM",
  tests: "TS",
  quality_gate: "QG",
  post_chunk: "PC",
  wiki: "WK",
  memory: "MM",
};

export default function MilestoneStrip({
  milestones,
}: {
  milestones: MilestoneResponse[];
}) {
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
