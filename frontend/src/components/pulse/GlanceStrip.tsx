"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDecimal } from "@/lib/format";

interface GlanceBreadth {
  advance: number;
  decline: number;
  pct_above_200dma: string | null;
  pct_above_50dma: string | null;
  new_52w_highs: number;
  new_52w_lows: number;
}

interface GlanceRegime {
  regime: string;
  confidence: string | null;
}

interface GlanceApiData {
  breadth: GlanceBreadth;
  regime: GlanceRegime;
}

function regimePillClass(regime: string): string {
  const upper = regime.toUpperCase();
  if (upper.includes("BULL") || upper.includes("EXPANSION")) {
    return "inline-block px-2 py-0.5 rounded text-xs font-semibold bg-green-100 text-green-700";
  }
  if (upper.includes("BEAR") || upper.includes("CONTRACTION")) {
    return "inline-block px-2 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-700";
  }
  return "inline-block px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-700";
}

interface KpiCellProps {
  label: string;
  value: string;
  sub?: string;
}

function KpiCell({ label, value, sub }: KpiCellProps) {
  return (
    <div className="flex flex-col items-center border border-gray-200 rounded p-3 bg-white">
      <span className="text-xs text-gray-500 mb-1">{label}</span>
      <span className="text-lg font-bold text-gray-800">{value}</span>
      {sub !== undefined && (
        <span className="text-xs text-gray-400 mt-0.5">{sub}</span>
      )}
    </div>
  );
}

export default function GlanceStrip() {
  const { data, meta, state, error } = useAtlasData<GlanceApiData>(
    "/api/v1/stocks/breadth",
    { universe: "nifty500", range: "1d", include: "deltas" },
    { dataClass: "eod_breadth" }
  );

  return (
    <DataBlock
      state={state}
      dataClass="eod_breadth"
      dataAsOf={meta?.data_as_of ?? null}
      errorCode={error?.code}
      errorMessage={error?.message}
      emptyTitle="No breadth data"
      emptyBody="Breadth metrics are unavailable for today."
    >
      {data && (
        <div className="glance grid grid-cols-6 gap-px" data-block="glance-strip">
          <KpiCell
            label="Advance / Decline"
            value={`${data.breadth.advance} / ${data.breadth.decline}`}
            sub={`Net: ${data.breadth.advance - data.breadth.decline}`}
          />
          <KpiCell
            label="Above 200DMA"
            value={
              data.breadth.pct_above_200dma !== null
                ? `${formatDecimal(data.breadth.pct_above_200dma)}%`
                : "—"
            }
          />
          <KpiCell
            label="Above 50DMA"
            value={
              data.breadth.pct_above_50dma !== null
                ? `${formatDecimal(data.breadth.pct_above_50dma)}%`
                : "—"
            }
          />
          <KpiCell
            label="52W Highs / Lows"
            value={`${data.breadth.new_52w_highs} / ${data.breadth.new_52w_lows}`}
          />
          <div className="flex flex-col items-center border border-gray-200 rounded p-3 bg-white">
            <span className="text-xs text-gray-500 mb-1">Regime</span>
            <span className={regimePillClass(data.regime.regime)}>
              {data.regime.regime}
            </span>
          </div>
          <KpiCell
            label="Net A/D"
            value={String(data.breadth.advance - data.breadth.decline)}
          />
        </div>
      )}
    </DataBlock>
  );
}
