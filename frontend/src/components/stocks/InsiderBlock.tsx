"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatCurrency, formatDate } from "@/lib/format";

// Backend response shape from InsiderResponse.model_dump():
// { insider_trades: [...], meta: { symbol, from_date, to_date, data_as_of, point_count, limit } }
// Field names in each trade: txn_date, filing_date, person_name, person_category,
//   txn_type, qty, value_inr, post_holding_pct
interface InsiderTransaction {
  // Backend field names
  txn_date?: string | null;
  filing_date?: string | null;
  person_name?: string | null;
  person_category?: string | null;
  txn_type?: string | null;
  qty?: number | string | null;
  value_inr?: number | string | null;
  post_holding_pct?: number | string | null;
  [key: string]: unknown;
}

// InsiderResponse model_serializer wraps to { data: [...], _meta: {...} }
// useAtlasData returns data = the inner array directly.
// Fallback object shapes supported for forward-compat.
type InsiderData = InsiderTransaction[] | {
  insider_trades?: InsiderTransaction[];
  records?: InsiderTransaction[];
  transactions?: InsiderTransaction[];
  [key: string]: unknown;
};

interface InsiderBlockProps {
  symbol: string;
}

export default function InsiderBlock({ symbol }: InsiderBlockProps) {
  const { data, meta, state, error } = useAtlasData<InsiderData>(
    `/api/stocks/${symbol}/insider`,
    undefined,
    { dataClass: "daily_regime" }
  );

  // data is InsiderTransaction[] (array) when API returns standard { data:[...], _meta:{...} }
  const txns: InsiderTransaction[] = Array.isArray(data)
    ? (data as InsiderTransaction[])
    : (data as { insider_trades?: InsiderTransaction[]; records?: InsiderTransaction[]; transactions?: InsiderTransaction[] } | null)?.insider_trades
      ?? (data as { records?: InsiderTransaction[] } | null)?.records
      ?? (data as { transactions?: InsiderTransaction[] } | null)?.transactions
      ?? [];
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
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Quantity</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Category</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Value (₹)</th>
                </tr>
              </thead>
              <tbody>
                {txns.map((t, i) => (
                  <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-2 text-xs text-gray-500 tabular-nums">{formatDate(t.txn_date ?? null)}</td>
                    <td className="px-4 py-2 text-gray-700 max-w-[140px] truncate" title={String(t.person_name ?? "")}>{t.person_name ?? "—"}</td>
                    <td className="px-4 py-2">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${(String(t.txn_type ?? "")).toLowerCase().includes("buy") ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                        {t.txn_type ?? "—"}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{t.qty != null ? Number(t.qty).toLocaleString("en-IN") : "—"}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-xs text-gray-500">{t.person_category ?? "—"}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{formatCurrency(t.value_inr != null ? Number(t.value_inr) : null)}</td>
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
