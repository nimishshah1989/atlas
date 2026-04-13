"use client";

import type { QualityResponse, QualityDimension } from "@/lib/systemClient";

// S1: 7 independent dims, no composite. Order is the registry order
// (security → product); non-gating dims get a muted "info" badge.
const DIM_ORDER = [
  "security",
  "code",
  "architecture",
  "api",
  "frontend",
  "backend",
  "product",
];
const FLOOR = 80;

function barColor(score: number, gating: boolean): string {
  if (!gating) return "bg-gray-300";
  if (score >= FLOOR) return "bg-emerald-500";
  if (score >= 60) return "bg-amber-500";
  return "bg-red-500";
}

function scoreColor(score: number, gating: boolean): string {
  if (!gating) return "text-gray-500";
  if (score >= FLOOR) return "text-emerald-700";
  if (score >= 60) return "text-amber-600";
  return "text-red-600";
}

function DimBar({ dim }: { dim: QualityDimension }) {
  const tag = dim.gating ? "GATE" : "info";
  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-white">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] font-mono uppercase tracking-wider text-gray-600 capitalize">
          {dim.dimension}
        </span>
        <span
          className={`text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded ${
            dim.gating
              ? "bg-gray-100 text-gray-700"
              : "bg-gray-50 text-gray-400"
          }`}
        >
          {tag}
        </span>
      </div>
      <div className="flex items-baseline justify-between mb-2">
        <span
          className={`text-2xl font-bold font-mono tabular-nums ${scoreColor(
            dim.score,
            dim.gating,
          )}`}
        >
          {dim.score}
        </span>
        <span className="text-[10px] font-mono text-gray-400 tabular-nums">
          {dim.passed}/{dim.eligible}
        </span>
      </div>
      <div className="w-full h-2 bg-gray-100 rounded overflow-hidden">
        <div
          className={`h-full rounded ${barColor(dim.score, dim.gating)} transition-all`}
          style={{ width: `${Math.min(dim.score, 100)}%` }}
        />
      </div>
    </div>
  );
}

export default function QualityScores({
  quality,
}: {
  quality: QualityResponse | null;
}) {
  if (!quality || quality.scores === null) {
    return (
      <p className="text-xs text-gray-500 font-mono py-4">
        No quality report yet. Run{" "}
        <code className="bg-gray-100 px-1 rounded">
          python .quality/checks.py --json
        </code>
        .
      </p>
    );
  }

  const { scores, as_of } = quality;
  const dimsMap = scores.dims ?? {};
  const ordered: QualityDimension[] = DIM_ORDER.map(
    (name) =>
      dimsMap[name] ?? {
        dimension: name,
        score: 0,
        gating: false,
        passed: 0,
        eligible: 0,
      },
  );

  const failedGating = ordered.filter(
    (d) => d.gating && d.score < FLOOR,
  );
  const verdict =
    failedGating.length === 0
      ? { text: "ALL GATING DIMS ≥ 80", cls: "text-emerald-700" }
      : {
          text: `BLOCKED: ${failedGating.map((d) => d.dimension).join(", ")} < 80`,
          cls: "text-red-600",
        };

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <span className={`text-xs font-mono font-semibold ${verdict.cls}`}>
          {verdict.text}
        </span>
        {as_of && (
          <span className="text-[10px] font-mono text-gray-400">
            as of {as_of.slice(0, 19).replace("T", " ")}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
        {ordered.map((d) => (
          <DimBar key={d.dimension} dim={d} />
        ))}
      </div>
    </div>
  );
}
