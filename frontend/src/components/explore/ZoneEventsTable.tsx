"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import EmptyState from "@/components/ui/EmptyState";
import { formatDate } from "@/lib/format";

interface ZoneEvent {
  date?: string | null;
  zone?: string | null;
  duration?: number | null;
  [key: string]: unknown;
}

interface ZoneEventsData {
  records?: ZoneEvent[];
  events?: ZoneEvent[];
  [key: string]: unknown;
}

export default function ZoneEventsTable() {
  const { data, meta, state, error } = useAtlasData<ZoneEventsData>(
    "/api/v1/stocks/breadth/zone-events",
    { universe: "nifty500", range: "5y" },
    { dataClass: "eod_breadth" }
  );

  const events = data?.records ?? data?.events ?? [];
  const effectiveState =
    state === "ready" && events.length === 0 ? "empty" : state;

  return (
    <div data-block="zone-events-table">
      <DataBlock
        state={effectiveState}
        dataClass="eod_breadth"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No zone events"
        emptyBody="No breadth zone events found for the selected universe and period."
      >
        {data && events.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="text-left py-2 px-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">
                    Date
                  </th>
                  <th className="text-left py-2 px-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">
                    Zone
                  </th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">
                    Duration (days)
                  </th>
                </tr>
              </thead>
              <tbody>
                {events.map((evt, i) => (
                  <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-2 px-3 text-gray-800">
                      {formatDate(evt.date ?? null)}
                    </td>
                    <td className="py-2 px-3 text-gray-700">
                      {evt.zone ?? "—"}
                    </td>
                    <td className="py-2 px-3 text-right text-gray-800 font-variant-numeric tabular-nums">
                      {evt.duration != null ? String(evt.duration) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          data && events.length === 0 && (
            <EmptyState
              title="No zone events"
              body="No breadth zone events found for the selected universe and period."
            />
          )
        )}
      </DataBlock>
    </div>
  );
}
