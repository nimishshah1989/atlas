"use client";

import { useState } from "react";
import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import EmptyState from "@/components/ui/EmptyState";

interface ZoneEvent {
  date: string;
  event_type: string;
  indicator: string;
  prior_zone?: string | null;
  prior_zone_duration_days?: number | null;
  value?: number | null;
  universe?: string | null;
  [key: string]: unknown;
}

interface ZoneEventsData {
  events?: ZoneEvent[];
  [key: string]: unknown;
}

interface SignalHistoryBlockProps {
  universe: string;
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  entered_ob: "Entered OB",
  exited_ob: "Exited OB",
  entered_os: "Entered OS",
  exited_os: "Exited OS",
  crossed_midline_up: "Crossed Midline \u2191",
  crossed_midline_dn: "Crossed Midline \u2193",
};

type SortColumn = "date" | "event_type" | "indicator" | "prior_zone" | "prior_zone_duration_days" | "value";
type SortDir = "asc" | "desc";

export default function SignalHistoryBlock({ universe }: SignalHistoryBlockProps) {
  const { data, meta, state, error } = useAtlasData<ZoneEventsData>(
    "/api/v1/stocks/breadth/zone-events",
    { universe, range: "5y" },
    { dataClass: "daily_regime" }
  );

  const [sortCol, setSortCol] = useState<SortColumn>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const events = data?.events ?? [];
  const effectiveState =
    state === "ready" && events.length === 0 ? "empty" : state;

  function handleSort(col: SortColumn) {
    if (col === sortCol) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(col);
      setSortDir("desc");
    }
  }

  const sorted = [...events].sort((a, b) => {
    const va = a[sortCol] ?? "";
    const vb = b[sortCol] ?? "";
    const cmp = String(va).localeCompare(String(vb), "en", { numeric: true });
    return sortDir === "asc" ? cmp : -cmp;
  });

  function SortIcon({ col }: { col: SortColumn }) {
    if (col !== sortCol) return <span className="ml-0.5 text-gray-300">↕</span>;
    return <span className="ml-0.5">{sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  return (
    <div data-block="signal-history" data-data-class="daily_regime">
      <DataBlock
        state={effectiveState}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No signal events"
        emptyBody="No zone transition events found for this universe and time range."
      >
        {data && events.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  {(
                    [
                      ["date", "Date"],
                      ["event_type", "Event"],
                      ["indicator", "Indicator"],
                      ["prior_zone", "Prior Zone"],
                      ["prior_zone_duration_days", "Days in Prior Zone"],
                      ["value", "Breadth Value"],
                    ] as [SortColumn, string][]
                  ).map(([col, label]) => (
                    <th
                      key={col}
                      onClick={() => handleSort(col)}
                      className="text-left px-3 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wide cursor-pointer select-none hover:text-gray-700"
                    >
                      {label}
                      <SortIcon col={col} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {sorted.map((ev, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="px-3 py-2 text-gray-700 font-mono text-xs">
                      {ev.date}
                    </td>
                    <td className="px-3 py-2 text-gray-800 font-medium">
                      {EVENT_TYPE_LABELS[ev.event_type] ?? ev.event_type}
                    </td>
                    <td className="px-3 py-2 text-gray-600 uppercase text-xs">
                      {ev.indicator}
                    </td>
                    <td className="px-3 py-2 text-gray-600 uppercase text-xs">
                      {ev.prior_zone ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-700">
                      {ev.prior_zone_duration_days !== null && ev.prior_zone_duration_days !== undefined
                        ? ev.prior_zone_duration_days
                        : "—"}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-700">
                      {ev.value !== null && ev.value !== undefined ? ev.value : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          data && events.length === 0 && (
            <EmptyState
              title="No signal events"
              body="No zone transition events found for this universe and time range."
            />
          )
        )}
      </DataBlock>
    </div>
  );
}
