"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDecimal } from "@/lib/format";

interface SignalBreadth {
  advance: number;
  decline: number;
  pct_above_200dma: string | null;
  pct_above_50dma: string | null;
  new_52w_highs: number;
  new_52w_lows: number;
}

interface SignalRegime {
  regime: string;
  confidence: string | null;
  breadth_score: string | null;
  momentum_score: string | null;
  volume_score: string | null;
  global_score: string | null;
  fii_score: string | null;
}

interface SignalApiData {
  breadth: SignalBreadth;
  regime: SignalRegime;
}

interface SignalChipProps {
  label: string;
  value: string | null;
  colorClass?: string;
}

function SignalChip({ label, value, colorClass = "bg-gray-100 text-gray-700" }: SignalChipProps) {
  return (
    <div className={`flex flex-col items-center px-3 py-2 rounded ${colorClass}`}>
      <span className="text-xs font-medium opacity-75">{label}</span>
      <span className="text-sm font-bold">{value ?? "—"}</span>
    </div>
  );
}

function scoreClass(val: string | null): string {
  if (val === null) return "bg-gray-100 text-gray-700";
  const n = parseFloat(val);
  if (isNaN(n)) return "bg-gray-100 text-gray-700";
  if (n >= 0.6) return "bg-green-100 text-green-700";
  if (n >= 0.4) return "bg-amber-100 text-amber-700";
  return "bg-red-100 text-red-700";
}

export default function SignalStrip() {
  const { data, meta, state, error } = useAtlasData<SignalApiData>(
    "/api/v1/stocks/breadth",
    {},
    { dataClass: "eod_breadth" }
  );

  return (
    <DataBlock
      state={state}
      dataClass="eod_breadth"
      dataAsOf={meta?.data_as_of ?? null}
      errorCode={error?.code}
      errorMessage={error?.message}
      emptyTitle="No signal data"
      emptyBody="Signal scores are unavailable."
    >
      {data && (
        <div
          className="flex flex-wrap gap-2"
          data-block="signal-strip"
        >
          <SignalChip
            label="RS"
            value={formatDecimal(data.breadth.pct_above_200dma)}
            colorClass={scoreClass(data.breadth.pct_above_200dma !== null
              ? String(parseFloat(String(data.breadth.pct_above_200dma)) / 100)
              : null)}
          />
          <SignalChip
            label="Breadth"
            value={data.regime.breadth_score !== null
              ? formatDecimal(data.regime.breadth_score)
              : null}
            colorClass={scoreClass(data.regime.breadth_score)}
          />
          <SignalChip
            label="Momentum"
            value={data.regime.momentum_score !== null
              ? formatDecimal(data.regime.momentum_score)
              : null}
            colorClass={scoreClass(data.regime.momentum_score)}
          />
          <SignalChip
            label="Volume"
            value={data.regime.volume_score !== null
              ? formatDecimal(data.regime.volume_score)
              : null}
            colorClass={scoreClass(data.regime.volume_score)}
          />
          <SignalChip
            label="Global"
            value={data.regime.global_score !== null
              ? formatDecimal(data.regime.global_score)
              : null}
            colorClass={scoreClass(data.regime.global_score)}
          />
          <SignalChip
            label="FII"
            value={data.regime.fii_score !== null
              ? formatDecimal(data.regime.fii_score)
              : null}
            colorClass={scoreClass(data.regime.fii_score)}
          />
          <SignalChip
            label="52W H/L"
            value={`${data.breadth.new_52w_highs}/${data.breadth.new_52w_lows}`}
          />
        </div>
      )}
    </DataBlock>
  );
}
