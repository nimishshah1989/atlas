"use client";

import type { QualityResponse, QualityCheck } from "@/lib/systemClient";

function barColor(pct: number): string {
  if (pct >= 95) return "bg-emerald-500";
  if (pct >= 80) return "bg-emerald-400";
  if (pct >= 60) return "bg-amber-500";
  return "bg-red-500";
}

function badgeColor(check: QualityCheck): string {
  if (check.score === check.max_score) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (check.status === "SKIP") return "bg-gray-50 text-gray-500 border-gray-200";
  return "bg-red-50 text-red-700 border-red-200";
}

export interface VersionCompletionStripProps {
  quality: QualityResponse | null;
  prefix: string;
  label: string;
  subtitle?: string;
}

export default function VersionCompletionStrip({
  quality,
  prefix,
  label,
  subtitle,
}: VersionCompletionStripProps) {
  const product = quality?.scores?.dims?.product;
  const checks = product?.checks ?? [];
  const versionChecks = checks.filter((c) => c.check_id.startsWith(`${prefix}-`));
  if (versionChecks.length === 0) return null;

  const total = versionChecks.length;
  const passed = versionChecks.filter((c) => c.score === c.max_score).length;
  const pct = Math.round((passed / total) * 100);

  return (
    <section className="border border-gray-200 rounded-lg p-4 bg-white">
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">{label}</h3>
          {subtitle ? (
            <p className="text-[11px] font-mono text-gray-500">{subtitle}</p>
          ) : null}
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold font-mono tabular-nums text-gray-900">
            {pct}%
          </div>
          <div className="text-[10px] font-mono text-gray-500 tabular-nums">
            {passed}/{total} criteria
          </div>
        </div>
      </div>

      <div className="w-full h-3 bg-gray-100 rounded overflow-hidden mb-4">
        <div
          className={`h-full rounded ${barColor(pct)} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
        {versionChecks.map((c) => (
          <div
            key={c.check_id}
            className={`border rounded px-2 py-1.5 ${badgeColor(c)}`}
            title={`${c.name} — ${c.evidence}`}
          >
            <div className="text-[10px] font-mono font-semibold uppercase tracking-wider">
              {c.check_id}
            </div>
            <div className="text-[10px] font-mono truncate" title={c.name}>
              {c.name}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
