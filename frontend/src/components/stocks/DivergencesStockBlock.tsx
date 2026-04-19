"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDate } from "@/lib/format";

interface Divergence {
  indicator?: string | null;
  type?: string | null;
  date?: string | null;
  description?: string | null;
  [key: string]: unknown;
}

interface DivergencesData {
  divergences?: Divergence[];
  [key: string]: unknown;
}

interface DivergencesStockBlockProps {
  symbol: string;
}

export default function DivergencesStockBlock({ symbol }: DivergencesStockBlockProps) {
  const { data, meta, state, error } = useAtlasData<DivergencesData>(
    `/api/v1/stocks/${symbol}`,
    { include: "divergences" },
    { dataClass: "daily_regime" }
  );

  const divs = data?.divergences ?? [];
  const effectiveState = state === "ready" && divs.length === 0 ? "empty" : state;

  return (
    <div data-component="divergences-block" className="bg-white border border-gray-200 rounded-lg p-4">
      <DataBlock
        state={effectiveState}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No divergences"
        emptyBody="No active divergences detected for this symbol."
      >
        {divs.length > 0 && (
          <ul className="space-y-2">
            {divs.map((d, i) => (
              <li key={i} className="flex items-start gap-3 text-sm">
                <span className={`mt-0.5 inline-block w-2 h-2 rounded-full flex-shrink-0 ${d.type === "bullish" ? "bg-emerald-500" : d.type === "bearish" ? "bg-red-500" : "bg-amber-500"}`} />
                <div>
                  <span className="font-medium text-gray-800">{d.indicator ?? "—"}</span>
                  {d.description && <span className="text-gray-500 ml-2">{d.description}</span>}
                  {d.date && <span className="text-gray-400 ml-2 text-xs">{formatDate(d.date)}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </DataBlock>
    </div>
  );
}
