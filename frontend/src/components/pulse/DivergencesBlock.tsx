"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import EmptyState from "@/components/ui/EmptyState";

interface DivergenceEntry {
  symbol?: string;
  factor?: string;
  description?: string;
  [key: string]: unknown;
}

// API returns { data: DivergenceEntry[] } or { data: { divergences: DivergenceEntry[] } }
type DivergenceData = DivergenceEntry[] | { divergences: DivergenceEntry[] };

function extractDivergences(data: DivergenceData | null): DivergenceEntry[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  return data.divergences ?? [];
}

export default function DivergencesBlock() {
  const { data, meta, state, error } = useAtlasData<DivergenceData>(
    "/api/v1/stocks/breadth/divergences",
    { universe: "nifty500" },
    { dataClass: "eod_breadth" }
  );

  return (
    <DataBlock
      state={state}
      dataClass="eod_breadth"
      dataAsOf={meta?.data_as_of ?? null}
      errorCode={error?.code}
      errorMessage={error?.message}
      emptyTitle="No divergences"
      emptyBody="No factor divergences detected in the current universe."
    >
      {data && (() => {
        const divs = extractDivergences(data);
        return divs.length === 0 ? (
            <EmptyState
              title="No divergences"
              body="No factor divergences detected in the current universe."
            />
          ) : (
            <ul
              className="divide-y divide-gray-100"
              data-block="divergences-block"
            >
              {divs.map((d, i) => (
                <li key={i} className="py-3 flex flex-col gap-0.5">
                  {d.symbol !== undefined && (
                    <span className="font-semibold text-gray-800 text-sm">
                      {d.symbol}
                    </span>
                  )}
                  {d.factor !== undefined && (
                    <span className="text-xs text-gray-500">{d.factor}</span>
                  )}
                  {d.description !== undefined && (
                    <span className="text-sm text-gray-700">{d.description}</span>
                  )}
                </li>
              ))}
            </ul>
          );
      })()}
    </DataBlock>
  );
}
