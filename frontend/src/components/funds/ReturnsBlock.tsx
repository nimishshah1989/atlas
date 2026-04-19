"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatPercent, signColor } from "@/lib/format";

interface ReturnRow {
  period?: string | null;
  fund?: number | string | null;
  benchmark?: number | string | null;
  alpha?: number | string | null;
  cat_rank?: string | null;
  [key: string]: unknown;
}

interface NavHistoryData {
  rolling_returns?: ReturnRow[];
  returns?: ReturnRow[];
  [key: string]: unknown;
}

const PERIOD_LABELS = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "10Y", "Since Inc."];

interface ReturnsBlockProps {
  id: string;
}

export default function ReturnsBlock({ id }: ReturnsBlockProps) {
  const { data, meta, state, error } = useAtlasData<NavHistoryData>(
    `/api/v1/mf/${id}/nav-history`,
    { range: "5y", include: "rolling_returns" },
    { dataClass: "daily_regime" }
  );

  const rows: ReturnRow[] = data?.rolling_returns ?? data?.returns ?? [];

  // Inline override for zero-row array (hasData() is key-presence only)
  const effectiveState =
    state === "ready" && rows.length === 0 ? "empty" : state;

  return (
    <div
      data-block="returns"
      className="bg-white border border-gray-200 rounded-lg overflow-hidden"
    >
      <DataBlock
        state={effectiveState}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No returns data"
        emptyBody="Rolling returns data is not available for this fund."
      >
        {rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Period
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Fund
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Benchmark
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Alpha (α)
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Cat. Rank
                  </th>
                </tr>
              </thead>
              <tbody>
                {/* Map provided rows */}
                {rows.map((row, i) => (
                  <tr
                    key={i}
                    className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-4 py-2.5 text-gray-700 font-medium">
                      {row.period ?? PERIOD_LABELS[i] ?? "—"}
                    </td>
                    <td
                      className={`px-4 py-2.5 text-right tabular-nums font-medium ${signColor(
                        row.fund ?? null
                      )}`}
                    >
                      {formatPercent(row.fund ?? null)}
                    </td>
                    <td
                      className={`px-4 py-2.5 text-right tabular-nums ${signColor(
                        row.benchmark ?? null
                      )}`}
                    >
                      {formatPercent(row.benchmark ?? null)}
                    </td>
                    <td
                      className={`px-4 py-2.5 text-right tabular-nums font-medium ${signColor(
                        row.alpha ?? null
                      )}`}
                    >
                      {formatPercent(row.alpha ?? null)}
                    </td>
                    <td className="px-4 py-2.5 text-right text-gray-600">
                      {row.cat_rank ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-gray-400 px-4 py-2 text-right">
              Source: ATLAS MF pipeline · as of {meta?.data_as_of ?? "—"}
            </p>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
