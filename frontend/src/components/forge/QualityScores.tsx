"use client";

import type { QualityResponse, QualityDimension } from "@/lib/systemClient";

// ---------------------------------------------------------------------------
// Dimension ordering: 3 primary then 4 secondary
// ---------------------------------------------------------------------------

const PRIMARY_DIMS = ["architecture", "code", "security"];
const SECONDARY_DIMS = ["frontend", "devops", "docs", "api"];

function barColor(score: number): string {
  if (score >= 85) return "bg-emerald-500";
  if (score >= 70) return "bg-amber-500";
  return "bg-red-500";
}

function scoreColor(score: number): string {
  if (score >= 85) return "text-emerald-700";
  if (score >= 70) return "text-amber-600";
  return "text-red-600";
}

// ---------------------------------------------------------------------------
// PrimaryTile
// ---------------------------------------------------------------------------

function PrimaryTile({ dim }: { dim: QualityDimension }) {
  return (
    <div className="border border-gray-200 rounded-lg p-4 bg-white">
      <div className="flex items-start justify-between mb-3">
        <span className="text-[11px] font-mono uppercase tracking-wider text-gray-500 capitalize">
          {dim.dimension}
        </span>
        <span
          className={`text-3xl font-bold font-mono tabular-nums ${scoreColor(dim.score)}`}
        >
          {dim.score}
        </span>
      </div>
      <div className="w-full h-2 bg-gray-100 rounded overflow-hidden">
        <div
          className={`h-full rounded ${barColor(dim.score)} transition-all`}
          style={{ width: `${Math.min(dim.score, 100)}%` }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SecondaryTile
// ---------------------------------------------------------------------------

function SecondaryTile({ dim }: { dim: QualityDimension }) {
  return (
    <div className="border border-gray-100 rounded-lg p-3 bg-white">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] font-mono uppercase tracking-wider text-gray-500 capitalize">
          {dim.dimension}
        </span>
        <span
          className={`text-lg font-bold font-mono tabular-nums ${scoreColor(dim.score)}`}
        >
          {dim.score}
        </span>
      </div>
      <div className="w-full h-1 bg-gray-100 rounded overflow-hidden">
        <div
          className={`h-full rounded ${barColor(dim.score)} transition-all`}
          style={{ width: `${Math.min(dim.score, 100)}%` }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// QualityScores
// ---------------------------------------------------------------------------

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
  const allDims = scores.dimensions ?? [];

  const primary = PRIMARY_DIMS.map(
    (name) =>
      allDims.find((d) => d.dimension.toLowerCase() === name) ?? {
        dimension: name,
        score: 0,
        weight: 0,
      }
  );
  const secondary = SECONDARY_DIMS.map(
    (name) =>
      allDims.find((d) => d.dimension.toLowerCase() === name) ?? {
        dimension: name,
        score: 0,
        weight: 0,
      }
  );

  return (
    <div className="space-y-4">
      {/* Overall score + as_of */}
      <div className="flex items-baseline justify-between">
        <div>
          <span className="text-[10px] font-mono uppercase tracking-widest text-gray-500">
            Overall
          </span>
          <span className={`ml-2 text-2xl font-bold font-mono ${scoreColor(scores.overall)}`}>
            {scores.overall}
          </span>
        </div>
        {as_of && (
          <span className="text-[10px] font-mono text-gray-400">
            as of {as_of.slice(0, 19).replace("T", " ")}
          </span>
        )}
      </div>

      {/* 3 primary tiles */}
      <div className="grid grid-cols-3 gap-3">
        {primary.map((d) => (
          <PrimaryTile key={d.dimension} dim={d} />
        ))}
      </div>

      {/* 4 secondary tiles */}
      <div className="grid grid-cols-4 gap-2">
        {secondary.map((d) => (
          <SecondaryTile key={d.dimension} dim={d} />
        ))}
      </div>
    </div>
  );
}
