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

interface DivergencesData {
  divergences?: DivergenceEntry[];
  [key: string]: unknown;
}

export default function DivergencesCountryBlock() {
  const { data, meta, state, error } = useAtlasData<DivergencesData>(
    "/api/v1/stocks/breadth/divergences",
    { universe: "nifty500" },
    { dataClass: "eod_breadth" }
  );

  const divergences = data?.divergences ?? [];
  const effectiveState =
    state === "ready" && divergences.length === 0 ? "empty" : state;

  return (
    <div data-block="divergences-country-block">
      <DataBlock
        state={effectiveState}
        dataClass="eod_breadth"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No divergences"
        emptyBody="No factor divergences detected in the current universe."
      >
        {data && divergences.length > 0 ? (
          <ul className="divide-y divide-gray-100">
            {divergences.map((d, i) => (
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
        ) : (
          data && divergences.length === 0 && (
            <EmptyState
              title="No divergences"
              body="No factor divergences detected in the current universe."
            />
          )
        )}
      </DataBlock>
    </div>
  );
}
