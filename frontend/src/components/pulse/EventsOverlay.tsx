"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDate } from "@/lib/format";

interface EventEntry {
  // New-format fields (backend V2FE-1b)
  title?: string;
  event_type?: string;
  event_date?: string;
  // Legacy / current format from atlas_key_events
  label?: string;
  date?: string;
  scope?: string;
  type?: string;
  category?: string;
  affects?: string[];
  [key: string]: unknown;
}

interface EventsData {
  events?: EventEntry[];
  // API may return events at root when wrapped as `data`
  [key: string]: unknown;
}

function eventTitle(ev: EventEntry): string {
  return ev.title ?? ev.label ?? "—";
}

function eventDate(ev: EventEntry): string | undefined {
  return ev.event_date ?? ev.date;
}

function eventScope(ev: EventEntry): string | undefined {
  if (ev.scope !== undefined) return ev.scope;
  if (Array.isArray(ev.affects)) return ev.affects.join(", ");
  return undefined;
}

function eventType(ev: EventEntry): string | undefined {
  return ev.event_type ?? ev.type ?? ev.category;
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
      {data && (() => {
        // API wraps events at data.events; after apiFetch normalization data may be
        // the full response object (contains events key) or legacy { events: [...] }
        const evList: EventEntry[] = Array.isArray((data as Record<string, unknown>).events)
          ? ((data as Record<string, unknown>).events as EventEntry[])
          : [];
        return (
          <ul
            className="divide-y divide-gray-100"
            data-block="events-overlay"
          >
            {evList.map((ev, i) => (
              <li key={i} className="py-3 flex gap-4 items-start">
                <div className="flex flex-col items-center min-w-16 text-center">
                  <span className="text-xs text-gray-400">
                    {eventDate(ev) !== undefined ? formatDate(eventDate(ev)!) : "—"}
                  </span>
                  {eventScope(ev) !== undefined && (
                    <span className="mt-0.5 text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                      {eventScope(ev)}
                    </span>
                  )}
                </div>
                <div className="flex-1">
                  <p className="text-sm font-semibold text-gray-800">
                    {eventTitle(ev)}
                  </p>
                  {eventType(ev) !== undefined && (
                    <span className="text-xs text-gray-500">{eventType(ev)}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        );
      })()}
    </DataBlock>
  );
}
