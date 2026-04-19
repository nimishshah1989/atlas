"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDate } from "@/lib/format";

interface SignalEvent {
  date?: string | null;
  signal_type?: string | null;
  indicator?: string | null;
  description?: string | null;
  [key: string]: unknown;
}

interface SignalHistoryData {
  records?: SignalEvent[];
  series?: SignalEvent[];
  [key: string]: unknown;
}

interface SignalHistoryStockBlockProps {
  symbol: string;
}

function signalColor(type: string | null | undefined): string {
  const t = (type ?? "").toUpperCase();
  if (t === "ENTRY") return "bg-emerald-100 text-emerald-700";
  if (t === "EXIT") return "bg-red-100 text-red-700";
  if (t === "WARN") return "bg-amber-100 text-amber-700";
  if (t === "REGIME") return "bg-blue-100 text-blue-700";
  return "bg-gray-100 text-gray-600";
}

export default function SignalHistoryStockBlock({ symbol }: SignalHistoryStockBlockProps) {
  const { data, meta, state, error } = useAtlasData<SignalHistoryData>(
    `/api/v1/stocks/${symbol}`,
    { include: "signal_history" },
    { dataClass: "daily_regime" }
  );

  const events = data?.records ?? data?.series ?? [];
  const effectiveState = state === "ready" && events.length === 0 ? "empty" : state;

  return (
    <div data-component="signal-history-table" className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <DataBlock
        state={effectiveState}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No signal history"
        emptyBody="No historical signals found for this symbol."
      >
        {events.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Date</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Type</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Indicator</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Description</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e, i) => (
                  <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-2 text-gray-600 text-xs tabular-nums">{formatDate(e.date ?? null)}</td>
                    <td className="px-4 py-2">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${signalColor(e.signal_type)}`}>
                        {e.signal_type ?? "—"}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-gray-700">{e.indicator ?? "—"}</td>
                    <td className="px-4 py-2 text-gray-500 text-xs">{e.description ?? "—"}</td>
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
