"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

interface ZoneSummaryEntry {
  zone?: string;
  threshold?: number | string;
  description?: string;
  pct_time?: number | null;
  [key: string]: unknown;
}

interface ZoneSummaryData {
  zone_summary?: ZoneSummaryEntry[];
  [key: string]: unknown;
}

interface ZoneLabelsBlockProps {
  universe: string;
}

const STATIC_ZONES = [
  {
    zone: "Overbought",
    threshold: "≥ 400",
    description: "Broad market participation — extended, watch for exhaustion",
  },
  {
    zone: "Midline",
    threshold: "250",
    description: "Neutral breadth — transition zone between bull and bear phases",
  },
  {
    zone: "Oversold",
    threshold: "≤ 100",
    description: "Narrow participation — potential capitulation or base-building",
  },
];

export default function ZoneLabelsBlock({ universe }: ZoneLabelsBlockProps) {
  const { data, meta, state, error } = useAtlasData<ZoneSummaryData>(
    "/api/v1/stocks/breadth",
    { universe, range: "5y", include: "zone_summary" },
    { dataClass: "eod_breadth" }
  );

  const zoneSummary = data?.zone_summary;

  return (
    <div data-block="zone-labels" data-data-class="eod_breadth">
      <DataBlock
        state={state}
        dataClass="eod_breadth"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="Zone reference"
        emptyBody="Historical zone distribution data not yet available."
      >
        <div className="grid grid-cols-3 gap-4">
          {(zoneSummary ?? STATIC_ZONES).map((z, i) => {
            // Access pct_time only from live ZoneSummaryEntry (not STATIC_ZONES)
            const pctTime = zoneSummary ? (z as ZoneSummaryEntry).pct_time : undefined;
            return (
              <div
                key={i}
                className="bg-white border border-gray-200 rounded-lg p-4"
              >
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  {z.zone ?? STATIC_ZONES[i]?.zone ?? "Zone"}
                </p>
                <p className="text-lg font-bold text-gray-900 mb-1">
                  {z.threshold ?? STATIC_ZONES[i]?.threshold ?? "—"}
                </p>
                <p className="text-xs text-gray-500">
                  {z.description ?? STATIC_ZONES[i]?.description ?? ""}
                </p>
                {pctTime !== null && pctTime !== undefined && (
                  <p className="text-xs text-gray-400 mt-1">
                    {typeof pctTime === "number" ? `${pctTime.toFixed(1)}% of time` : ""}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </DataBlock>
    </div>
  );
}
