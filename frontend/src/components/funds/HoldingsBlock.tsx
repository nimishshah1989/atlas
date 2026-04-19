"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDecimal } from "@/lib/format";

interface Holding {
  rank?: number | null;
  symbol?: string | null;
  name?: string | null;
  weight_pct?: number | string | null;
  market_cap_category?: string | null;
  [key: string]: unknown;
}

interface HoldingsData {
  holdings?: Holding[];
  records?: Holding[];
  [key: string]: unknown;
}

interface HoldingsBlockProps {
  id: string;
}

export default function HoldingsBlock({ id }: HoldingsBlockProps) {
  const { data, meta, state, error } = useAtlasData<HoldingsData>(
    `/api/v1/mf/${id}/holdings`,
    { limit: "20", include: "concentration" },
    { dataClass: "holdings" }
  );

  const rows: Holding[] = data?.holdings ?? data?.records ?? [];

  // Inline override for zero-row array
  const effectiveState =
    state === "ready" && rows.length === 0 ? "empty" : state;

  return (
    <div
      data-block="holdings"
      className="bg-white border border-gray-200 rounded-lg overflow-hidden"
    >
      <DataBlock
        state={effectiveState}
        dataClass="holdings"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No holdings data"
        emptyBody="Holdings data is not available for this fund."
      >
        {rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[500px]">
              <thead className="sticky top-0 bg-white z-10">
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide w-12">
                    #
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Symbol
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Name
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Weight %
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Market Cap
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr
                    key={i}
                    className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-4 py-2.5 text-right text-gray-400 tabular-nums text-xs">
                      {row.rank ?? i + 1}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-700">
                      {row.symbol ?? "—"}
                    </td>
                    <td className="px-4 py-2.5 text-gray-700">
                      {row.name ?? "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums font-medium text-gray-900">
                      {row.weight_pct != null
                        ? `${formatDecimal(row.weight_pct)}%`
                        : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-gray-500 text-xs">
                      {row.market_cap_category ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-gray-400 px-4 py-2 text-right">
              Top 20 holdings · as of {meta?.data_as_of ?? "—"}
            </p>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
