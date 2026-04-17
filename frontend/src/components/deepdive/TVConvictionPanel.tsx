"use client";

import { classifyTvScore } from "@/lib/tv";

type TvTa = Record<string, number | string | null> | null | undefined;

export default function TVConvictionPanel({
  tvTa,
  explanation,
}: {
  tvTa: TvTa;
  explanation?: string;
}) {
  if (!tvTa) {
    return (
      <div className="border rounded-lg p-4 bg-white">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          External Confirmation (TradingView)
        </h3>
        <p className="text-sm text-gray-500 italic">TV data unavailable</p>
      </div>
    );
  }

  const rows: { key: string; label: string; raw: unknown }[] = [
    { key: "overall",     label: "Overall",     raw: tvTa["Recommend.All"] },
    { key: "ma",          label: "Moving Avgs", raw: tvTa["Recommend.MA"] },
    { key: "oscillators", label: "Oscillators", raw: tvTa["Recommend.Other"] },
  ];

  return (
    <div className="border rounded-lg p-4 bg-white">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        External Confirmation (TradingView)
      </h3>
      <div className="space-y-2">
        {rows.map((row) => {
          const chip = classifyTvScore(row.raw);
          return (
            <div
              key={row.key}
              data-testid={`tv-row-${row.key}`}
              className={`flex items-center justify-between border rounded px-3 py-2 text-sm ${chip.className}`}
            >
              <span className="font-medium">{row.label}</span>
              <span className="flex items-center gap-2">
                <span className="tabular-nums text-xs">{chip.display}</span>
                {chip.label && (
                  <span className="text-xs font-semibold tracking-wide">
                    {chip.label.replace("_", " ")}
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>
      {explanation && (
        <p className="text-xs text-gray-500 mt-2 italic">{explanation}</p>
      )}
    </div>
  );
}
