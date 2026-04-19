"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDecimal, signColor } from "@/lib/format";

interface WtData {
  aggregate_rs?: number | string | null;
  conviction?: number | string | null;
  momentum?: number | string | null;
  pct_above_200dma?: number | string | null;
  pct_above_50dma?: number | string | null;
  holdings_avg_rs?: number | string | null;
  [key: string]: unknown;
}

interface WeightedTechnicalsBlockProps {
  id: string;
}

function MetricRow({
  label,
  value,
  colorClass,
}: {
  label: string;
  value: string;
  colorClass?: string;
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
      <span className="text-sm text-gray-600">{label}</span>
      <span className={`text-sm font-medium tabular-nums ${colorClass ?? "text-gray-900"}`}>
        {value}
      </span>
    </div>
  );
}

export default function WeightedTechnicalsBlock({ id }: WeightedTechnicalsBlockProps) {
  const { data, meta, state, error } = useAtlasData<WtData>(
    `/api/v1/mf/${id}/weighted-technicals`,
    undefined,
    { dataClass: "daily_regime" }
  );

  const fmt = (v: number | string | null | undefined) =>
    formatDecimal(v ?? null);

  return (
    <div
      data-block="weighted-technicals"
      className="bg-white border border-gray-200 rounded-lg p-6 h-full"
    >
      <DataBlock
        state={state}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No technicals data"
        emptyBody="Weighted technicals data is not available for this fund."
      >
        {data && (
          <div>
            <MetricRow
              label="Aggregate RS"
              value={fmt(data.aggregate_rs)}
              colorClass={signColor(data.aggregate_rs ?? null)}
            />
            <MetricRow
              label="Conviction"
              value={fmt(data.conviction)}
            />
            <MetricRow
              label="Momentum"
              value={fmt(data.momentum)}
              colorClass={signColor(data.momentum ?? null)}
            />
            <MetricRow
              label="Holdings Avg RS"
              value={fmt(data.holdings_avg_rs)}
            />
            <MetricRow
              label="% Above 200DMA"
              value={
                data.pct_above_200dma != null
                  ? `${fmt(data.pct_above_200dma)}%`
                  : "—"
              }
            />
            <MetricRow
              label="% Above 50DMA"
              value={
                data.pct_above_50dma != null
                  ? `${fmt(data.pct_above_50dma)}%`
                  : "—"
              }
            />
          </div>
        )}
      </DataBlock>
    </div>
  );
}
