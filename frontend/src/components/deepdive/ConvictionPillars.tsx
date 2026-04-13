"use client";

import type { StockDeepDive } from "@/lib/api";
import { formatDecimal, signColor } from "@/lib/format";

export default function ConvictionPillars({
  conviction,
}: {
  conviction: StockDeepDive["conviction"];
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div className="border rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Pillar 1: Relative Strength
        </h3>
        <div className="space-y-1.5 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">RS Composite</span>
            <span className={`font-medium ${signColor(conviction.rs.rs_composite)}`}>
              {formatDecimal(conviction.rs.rs_composite)}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Momentum</span>
            <span className={`font-medium ${signColor(conviction.rs.rs_momentum)}`}>
              {formatDecimal(conviction.rs.rs_momentum)}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">1W / 1M / 3M</span>
            <span className="text-xs tabular-nums">
              {formatDecimal(conviction.rs.rs_1w, 1)} /{" "}
              {formatDecimal(conviction.rs.rs_1m, 1)} /{" "}
              {formatDecimal(conviction.rs.rs_3m, 1)}
            </span>
          </div>
        </div>
        <p className="text-xs text-gray-500 mt-2 italic">
          {conviction.rs.explanation}
        </p>
      </div>

      <div className="border rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Pillar 2: Technical Health
        </h3>
        <div className="text-2xl font-bold text-center mb-2">
          <span
            className={
              conviction.technical.checks_passing >= 7
                ? "text-emerald-600"
                : conviction.technical.checks_passing >= 4
                  ? "text-amber-600"
                  : "text-red-600"
            }
          >
            {conviction.technical.checks_passing}
          </span>
          <span className="text-gray-400 text-lg">
            /{conviction.technical.checks_total}
          </span>
        </div>
        <div className="space-y-1">
          {conviction.technical.checks.map((c) => (
            <div key={c.name} className="flex items-center gap-1.5 text-xs">
              <span
                className={
                  c.value === "N/A"
                    ? "text-gray-400"
                    : c.passing
                      ? "text-emerald-500"
                      : "text-red-500"
                }
              >
                {c.value === "N/A" ? "○" : "●"}
              </span>
              <span className="text-gray-600">{c.name}</span>
              <span className="text-gray-400 ml-auto truncate max-w-[100px]">
                {c.value !== "N/A" ? c.value : "—"}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="border rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Pillar 3: Institutional
        </h3>
        <div className="space-y-3">
          <div>
            <div className="text-xs text-gray-500">MF Holders</div>
            <div className="text-2xl font-bold">
              {conviction.institutional.mf_holder_count ?? "—"}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Delivery vs Avg</div>
            <div className="text-lg font-medium">
              {conviction.institutional.delivery_vs_avg
                ? `${formatDecimal(conviction.institutional.delivery_vs_avg)}x`
                : "—"}
            </div>
          </div>
        </div>
        <p className="text-xs text-gray-500 mt-2 italic">
          {conviction.institutional.explanation}
        </p>
      </div>
    </div>
  );
}
