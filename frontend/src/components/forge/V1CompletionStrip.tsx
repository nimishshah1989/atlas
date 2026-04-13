"use client";

import type { QualityResponse, QualityCheck } from "@/lib/systemClient";

// S3: render the product dim as a V1 completion progress bar + per-criterion
// badges. Product dim is informational (non-gating) until V1.6 R1, so this is
// a watch-it-climb view — not a gate. Criteria 7 and 12 are the two that
// need pipeline work to flip green.

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

export default function V1CompletionStrip({
  quality,
}: {
  quality: QualityResponse | null;
}) {
  const product = quality?.scores?.dims?.product;
  const checks = product?.checks ?? [];
  // Only render if the product dim has been wired to the v1-criteria YAML
  // (i.e. check IDs start with `v1-`). During the S1 stub era it was `p0`
  // and this strip should stay hidden.
  const v1Checks = checks.filter((c) => c.check_id.startsWith("v1-"));
  if (v1Checks.length === 0) return null;

  const total = v1Checks.length;
  const passed = v1Checks.filter((c) => c.score === c.max_score).length;
  const pct = Math.round((passed / total) * 100);

  return (
    <section className="border border-gray-200 rounded-lg p-4 bg-white">
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">V1 Completion</h3>
          <p className="text-[11px] font-mono text-gray-500">
            §24.3 — informational until V1.6 R1 flips product to gating
          </p>
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
        {v1Checks.map((c) => (
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
