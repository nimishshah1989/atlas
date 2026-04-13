"use client";

export type QualityReport = {
  overall_score?: number;
  dimensions?: Array<{ dimension: string; score: number; weight: number }>;
  generated_at?: string;
};

function barColor(score: number): string {
  if (score >= 85) return "bg-emerald-500";
  if (score >= 70) return "bg-amber-500";
  return "bg-red-500";
}

export default function QualityScores({
  report,
}: {
  report: QualityReport | null;
}) {
  if (!report) {
    return (
      <p className="text-xs text-gray-500 font-mono">
        No quality report yet. Run <code>python .quality/checks.py --json</code>.
      </p>
    );
  }
  const overall = report.overall_score ?? 0;
  const dims = report.dimensions ?? [];
  return (
    <div className="space-y-3">
      <div>
        <div className="flex items-baseline justify-between">
          <span className="text-[10px] uppercase tracking-widest text-gray-500 font-mono">
            Overall
          </span>
          <span className="text-2xl font-bold font-mono">{overall}</span>
        </div>
        <div className="w-full h-2 bg-gray-200 rounded mt-1">
          <div
            className={`h-full rounded ${barColor(overall)}`}
            style={{ width: `${Math.min(overall, 100)}%` }}
          />
        </div>
      </div>
      <div className="space-y-1.5">
        {dims.map((d) => (
          <div key={d.dimension}>
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-600 capitalize">{d.dimension}</span>
              <span className="font-mono tabular-nums text-gray-800">
                {d.score}
              </span>
            </div>
            <div className="w-full h-1 bg-gray-100 rounded">
              <div
                className={`h-full rounded ${barColor(d.score)}`}
                style={{ width: `${Math.min(d.score, 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      {report.generated_at && (
        <p className="text-[10px] font-mono text-gray-400">
          {report.generated_at}
        </p>
      )}
    </div>
  );
}
