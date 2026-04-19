"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import EmptyState from "@/components/ui/EmptyState";

interface DivergenceEntry {
  symbol?: string | null;
  factor?: string | null;
  description?: string | null;
  direction?: string | null;
  magnitude?: number | null;
  [key: string]: unknown;
}

interface DivergencesData {
  divergences?: DivergenceEntry[];
  [key: string]: unknown;
}

interface DivergencesBlockProps {
  universe: string;
}

export default function DivergencesBlock({ universe }: DivergencesBlockProps) {
  const { data, meta, state, error } = useAtlasData<DivergencesData>(
    "/api/v1/stocks/breadth/divergences",
    { universe },
    { dataClass: "daily_regime" }
  );

  const divergences = data?.divergences ?? [];
  const effectiveState =
    state === "ready" && divergences.length === 0 ? "empty" : state;

  return (
    <div data-block="divergences" data-data-class="daily_regime">
      <DataBlock
        state={effectiveState}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No divergences"
        emptyBody="No factor divergences detected in the current universe."
      >
        {data && divergences.length > 0 ? (
          <ul className="divide-y divide-gray-100 space-y-0">
            {divergences.map((d, i) => (
              <li key={i} className="py-3 flex flex-col gap-0.5">
                {d.symbol !== null && d.symbol !== undefined && (
                  <span className="font-semibold text-gray-800 text-sm">
                    {d.symbol}
                  </span>
                )}
                {d.factor !== null && d.factor !== undefined && (
                  <span className="text-xs text-gray-500">{d.factor}</span>
                )}
                {d.direction !== null && d.direction !== undefined && (
                  <span className="text-xs font-medium text-gray-600 uppercase">
                    {d.direction}
                  </span>
                )}
                {d.description !== null && d.description !== undefined && (
                  <span className="text-sm text-gray-700">{d.description}</span>
                )}
                {d.magnitude !== null && d.magnitude !== undefined && (
                  <span className="text-xs text-gray-400">
                    Magnitude: {typeof d.magnitude === "number" ? d.magnitude.toFixed(2) : d.magnitude}
                  </span>
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
