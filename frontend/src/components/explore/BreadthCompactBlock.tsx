"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatPercent } from "@/lib/format";

interface BreadthData {
  above_ema21_pct?: number | string | null;
  above_dma50_pct?: number | string | null;
  above_dma200_pct?: number | string | null;
  [key: string]: unknown;
}

export default function BreadthCompactBlock() {
  const { data, meta, state, error } = useAtlasData<BreadthData>(
    "/api/v1/stocks/breadth",
    { universe: "nifty500", range: "5y" },
    { dataClass: "eod_breadth" }
  );

  return (
    <div data-block="breadth-compact">
      <DataBlock
        state={state}
        dataClass="eod_breadth"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No breadth data"
        emptyBody="Breadth data is not available for the selected universe."
      >
        {data && (
          <div className="space-y-4">
            {/* 3 KPI cards */}
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  % Above 21-EMA
                </p>
                <p className="text-2xl font-bold text-gray-900">
                  {formatPercent(data.above_ema21_pct ?? null, false)}
                </p>
              </div>
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  % Above 50-DMA
                </p>
                <p className="text-2xl font-bold text-gray-900">
                  {formatPercent(data.above_dma50_pct ?? null, false)}
                </p>
              </div>
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  % Above 200-DMA
                </p>
                <p className="text-2xl font-bold text-gray-900">
                  {formatPercent(data.above_dma200_pct ?? null, false)}
                </p>
              </div>
            </div>

            {/* Dual-axis chart placeholder */}
            <div className="bg-gray-50 border border-dashed border-gray-300 rounded-lg p-6 flex items-center justify-center min-h-[120px]">
              <p className="text-sm text-gray-400">Breadth chart — coming in V2</p>
            </div>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
