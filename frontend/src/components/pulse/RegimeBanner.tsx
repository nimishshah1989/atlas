"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDecimal } from "@/lib/format";

interface BreadthFields {
  advance: number;
  decline: number;
  pct_above_200dma: string | null;
  pct_above_50dma: string | null;
  new_52w_highs: number;
  new_52w_lows: number;
}

interface RegimeFields {
  regime: string;
  confidence: string | null;
  days_in_regime?: number;
}

interface BreadthApiData {
  breadth: BreadthFields;
  regime: RegimeFields;
}

function regimeBannerClass(regime: string): string {
  const upper = regime.toUpperCase();
  if (upper.includes("BULL") || upper.includes("EXPANSION")) {
    return "bg-green-100 text-green-700 border-l-4 border-green-500";
  }
  if (upper.includes("BEAR") || upper.includes("CONTRACTION")) {
    return "bg-red-100 text-red-700 border-l-4 border-red-500";
  }
  // CORRECTION, NEUTRAL, SIDEWAYS, RECOVERY, etc.
  return "bg-amber-100 text-amber-700 border-l-4 border-amber-500";
}

export default function RegimeBanner() {
  const { data, meta, state, error } = useAtlasData<BreadthApiData>(
    "/api/v1/stocks/breadth",
    { universe: "nifty500" },
    { dataClass: "daily_regime" }
  );

  return (
    <DataBlock
      state={state}
      dataClass="daily_regime"
      dataAsOf={meta?.data_as_of ?? null}
      errorCode={error?.code}
      errorMessage={error?.message}
      emptyTitle="No regime data"
      emptyBody="Breadth data is unavailable for this universe."
    >
      {data && (
        <div
          className={`p-4 rounded ${regimeBannerClass(data.regime.regime)}`}
          data-block="regime-banner"
        >
          <div className="flex items-center gap-4">
            <span className="text-xl font-bold">{data.regime.regime}</span>
            {data.regime.confidence !== null && (
              <span className="text-sm">
                Confidence: {formatDecimal(data.regime.confidence)}%
              </span>
            )}
            {typeof data.regime.days_in_regime === "number" && (
              <span className="text-sm">
                {data.regime.days_in_regime}d in regime
              </span>
            )}
          </div>
          <div className="flex gap-6 mt-2 text-sm">
            <span>A/D: {data.breadth.advance}/{data.breadth.decline}</span>
            <span>
              &gt;200DMA:{" "}
              {data.breadth.pct_above_200dma !== null
                ? `${formatDecimal(data.breadth.pct_above_200dma)}%`
                : "—"}
            </span>
            <span>
              &gt;50DMA:{" "}
              {data.breadth.pct_above_50dma !== null
                ? `${formatDecimal(data.breadth.pct_above_50dma)}%`
                : "—"}
            </span>
            <span>
              52W H/L: {data.breadth.new_52w_highs}/{data.breadth.new_52w_lows}
            </span>
          </div>
        </div>
      )}
    </DataBlock>
  );
}
