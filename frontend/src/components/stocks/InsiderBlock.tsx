"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatCurrency, formatDate } from "@/lib/format";

interface InsiderTransaction {
  date?: string | null;
  name?: string | null;
  designation?: string | null;
  transaction_type?: string | null;
  shares?: number | string | null;
  price?: number | string | null;
  value?: number | string | null;
  [key: string]: unknown;
}

interface InsiderData {
  records?: InsiderTransaction[];
  transactions?: InsiderTransaction[];
  [key: string]: unknown;
}

interface InsiderBlockProps {
  symbol: string;
}

export default function InsiderBlock({ symbol }: InsiderBlockProps) {
  const { data, meta, state, error } = useAtlasData<InsiderData>(
    `/api/v1/insider/${symbol}`,
    undefined,
    { dataClass: "daily_regime" }
  );

  const txns = data?.records ?? data?.transactions ?? [];
  const effectiveState = state === "ready" && txns.length === 0 ? "empty" : state;

  return (
    <div data-block="insider" className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <DataBlock
        state={effectiveState}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No insider activity"
        emptyBody="No insider or bulk/block transactions on record."
      >
        {txns.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Date</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Name</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Type</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Shares</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Price</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Value</th>
                </tr>
              </thead>
              <tbody>
                {txns.map((t, i) => (
                  <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-2 text-xs text-gray-500 tabular-nums">{formatDate(t.date ?? null)}</td>
                    <td className="px-4 py-2 text-gray-700">{t.name ?? "—"}</td>
                    <td className="px-4 py-2">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${(t.transaction_type ?? "").toLowerCase().includes("buy") ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                        {t.transaction_type ?? "—"}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{t.shares != null ? Number(t.shares).toLocaleString("en-IN") : "—"}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{formatCurrency(t.price ?? null)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{formatCurrency(t.value ?? null)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
