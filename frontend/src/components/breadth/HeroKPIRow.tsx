"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

interface BreadthCountData {
  ema21_count?: number | null;
  dma50_count?: number | null;
  dma200_count?: number | null;
  universe_size?: number | null;
  series?: Array<{
    ema21_count?: number | null;
    dma50_count?: number | null;
    dma200_count?: number | null;
    universe_size?: number | null;
    [key: string]: unknown;
  }>;
  [key: string]: unknown;
}

interface HeroKPIRowProps {
  universe: string;
}

function pctClass(pct: number | null): string {
  if (pct === null) return "text-gray-900";
  if (pct >= 60) return "text-green-600";
  if (pct >= 40) return "text-amber-600";
  return "text-red-600";
}

export default function HeroKPIRow({ universe }: HeroKPIRowProps) {
  const { data, meta, state, error } = useAtlasData<BreadthCountData>(
    "/api/v1/stocks/breadth",
    { universe, range: "1d", include: "counts" },
    { dataClass: "eod_breadth" }
  );

  // Latest row might be in series array or top-level
  const latest = data?.series?.[data.series.length - 1] ?? data;
  const universeSize = latest?.universe_size ?? 500;

  const ema21 = latest?.ema21_count ?? null;
  const dma50 = latest?.dma50_count ?? null;
  const dma200 = latest?.dma200_count ?? null;

  const ema21Pct = ema21 !== null && universeSize ? (ema21 / universeSize) * 100 : null;
  const dma50Pct = dma50 !== null && universeSize ? (dma50 / universeSize) * 100 : null;
  const dma200Pct = dma200 !== null && universeSize ? (dma200 / universeSize) * 100 : null;

  return (
    <div data-block="breadth-kpi" data-data-class="eod_breadth">
      <DataBlock
        state={state}
        dataClass="eod_breadth"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No breadth data"
        emptyBody="Breadth count data is not available for the selected universe."
      >
        {data && (
          <div className="grid grid-cols-3 gap-4">
            {/* 21-EMA card */}
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Above 21-EMA
              </p>
              <p className={`text-2xl font-bold ${pctClass(ema21Pct)}`}>
                {ema21 !== null ? ema21 : "—"}
              </p>
              <p className={`text-sm ${pctClass(ema21Pct)}`}>
                {ema21Pct !== null ? `${ema21Pct.toFixed(1)}%` : "—"}
              </p>
            </div>

            {/* 50-DMA card */}
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Above 50-DMA
              </p>
              <p className={`text-2xl font-bold ${pctClass(dma50Pct)}`}>
                {dma50 !== null ? dma50 : "—"}
              </p>
              <p className={`text-sm ${pctClass(dma50Pct)}`}>
                {dma50Pct !== null ? `${dma50Pct.toFixed(1)}%` : "—"}
              </p>
            </div>

            {/* 200-DMA card */}
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Above 200-DMA
              </p>
              <p className={`text-2xl font-bold ${pctClass(dma200Pct)}`}>
                {dma200 !== null ? dma200 : "—"}
              </p>
              <p className={`text-sm ${pctClass(dma200Pct)}`}>
                {dma200Pct !== null ? `${dma200Pct.toFixed(1)}%` : "—"}
              </p>
            </div>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
