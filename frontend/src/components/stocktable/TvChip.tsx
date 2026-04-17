"use client";

import { classifyTvScore } from "@/lib/tv";

export default function TvChip({
  score,
  size = "md",
}: {
  score: number | null | undefined;
  size?: "sm" | "md";
}) {
  const chip = classifyTvScore(typeof score === "number" ? score : null);
  const sizeCls =
    size === "sm" ? "text-[10px] px-1 py-px" : "text-xs px-1.5 py-0.5";
  return (
    <span
      data-testid="tv-chip"
      data-tv-label={chip.label ?? "NONE"}
      className={`inline-flex items-center gap-1 rounded border font-medium ${sizeCls} ${chip.className}`}
    >
      {chip.label ? chip.label.replace("_", " ") : "\u2014"}
    </span>
  );
}
