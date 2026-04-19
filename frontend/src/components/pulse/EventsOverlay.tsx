"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDate } from "@/lib/format";

interface EventEntry {
  title?: string;
  date?: string;
  scope?: string;
  type?: string;
  [key: string]: unknown;
}

interface EventsData {
  events: EventEntry[];
}

export default function EventsOverlay() {
  const { data, meta, state, error } = useAtlasData<EventsData>(
    "/api/v1/global/events",
    { scope: "india,global" },
    { dataClass: "events" }
  );

  return (
    <DataBlock
      state={state}
      dataClass="events"
      dataAsOf={meta?.data_as_of ?? null}
      errorCode={error?.code}
      errorMessage={error?.message}
      emptyTitle="No events"
      emptyBody="No upcoming events found for the selected scope."
    >
      {data && (
        <ul
          className="divide-y divide-gray-100"
          data-block="events-overlay"
        >
          {data.events.map((ev, i) => (
            <li key={i} className="py-3 flex gap-4 items-start">
              <div className="flex flex-col items-center min-w-16 text-center">
                <span className="text-xs text-gray-400">
                  {ev.date !== undefined ? formatDate(ev.date) : "—"}
                </span>
                {ev.scope !== undefined && (
                  <span className="mt-0.5 text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                    {ev.scope}
                  </span>
                )}
              </div>
              <div className="flex-1">
                {ev.title !== undefined && (
                  <p className="text-sm font-semibold text-gray-800">
                    {ev.title}
                  </p>
                )}
                {ev.type !== undefined && (
                  <span className="text-xs text-gray-500">{ev.type}</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </DataBlock>
  );
}
