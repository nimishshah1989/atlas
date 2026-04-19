"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDecimal, signColor } from "@/lib/format";

interface AlphaRiskData {
  alpha?: number | string | null;
  beta?: number | string | null;
  sharpe_3y?: number | string | null;
  sortino_3y?: number | string | null;
  max_drawdown?: number | string | null;
  upside_capture?: number | string | null;
  downside_capture?: number | string | null;
  [key: string]: unknown;
}

interface AlphaRiskBlockProps {
  id: string;
}

interface MetricItem {
  label: string;
  value: string;
  colorClass?: string;
}

function MetricCell({ label, value, colorClass }: MetricItem) {
  return (
    <div className="bg-gray-50 rounded-lg p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-lg font-bold tabular-nums ${colorClass ?? "text-gray-900"}`}>
        {value}
      </div>
    </div>
  );
}

export default function AlphaRiskBlock({ id }: AlphaRiskBlockProps) {
  const { data, meta, state, error } = useAtlasData<AlphaRiskData>(
    `/api/v1/mf/${id}`,
    { include: "alpha,risk_metrics" },
    { dataClass: "daily_regime" }
  );

  const fmt = (v: number | string | null | undefined) =>
    formatDecimal(v ?? null);

  return (
    <div
      data-block="alpha"
      className="bg-white border border-gray-200 rounded-lg p-6"
    >
      <DataBlock
        state={state}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No risk metrics"
        emptyBody="Alpha and risk metrics are not available for this fund."
      >
        {data && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            <MetricCell
              label="Alpha"
              value={fmt(data.alpha)}
              colorClass={signColor(data.alpha ?? null)}
            />
            <MetricCell label="Beta" value={fmt(data.beta)} />
            <MetricCell label="Sharpe (3Y)" value={fmt(data.sharpe_3y)} />
            <MetricCell label="Sortino (3Y)" value={fmt(data.sortino_3y)} />
            <MetricCell
              label="Max Drawdown"
              value={
                data.max_drawdown != null
                  ? `${fmt(data.max_drawdown)}%`
                  : "—"
              }
              colorClass={
                data.max_drawdown != null
                  ? signColor(data.max_drawdown)
                  : undefined
              }
            />
            <MetricCell
              label="Upside Capture"
              value={
                data.upside_capture != null
                  ? `${fmt(data.upside_capture)}%`
                  : "—"
              }
            />
            <MetricCell
              label="Downside Capture"
              value={
                data.downside_capture != null
                  ? `${fmt(data.downside_capture)}%`
                  : "—"
              }
            />
          </div>
        )}
      </DataBlock>
    </div>
  );
}
