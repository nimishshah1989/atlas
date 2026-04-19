"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatPercent } from "@/lib/format";

interface BenchmarkPanel {
  benchmark?: string | null;
  label?: string | null;
  rs_1y?: number | string | null;
  alpha?: number | string | null;
  corr?: number | string | null;
  [key: string]: unknown;
}

interface BenchmarkData {
  panels?: BenchmarkPanel[];
  records?: BenchmarkPanel[];
  [key: string]: unknown;
}

interface BenchmarkPanelsProps {
  symbol: string;
}

function PanelCard({ panel }: { panel: BenchmarkPanel }) {
  const label = panel.label ?? panel.benchmark ?? "—";
  const rs1y = panel.rs_1y != null ? formatPercent(panel.rs_1y) : "—";
  const alpha = panel.alpha != null ? formatPercent(panel.alpha) : "—";
  const corr = panel.corr != null ? Number(panel.corr).toFixed(2) : "—";

  return (
    <div
      data-benchmark={panel.benchmark ?? undefined}
      className="bg-white border border-gray-200 rounded-lg p-4"
    >
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">{label}</div>
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">RS (1Y)</span>
          <span className="font-medium tabular-nums">{rs1y}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Alpha</span>
          <span className={`font-medium tabular-nums ${panel.alpha != null && Number(panel.alpha) >= 0 ? "text-emerald-600" : "text-red-600"}`}>{alpha}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Correlation</span>
          <span className="font-medium tabular-nums">{corr}</span>
        </div>
      </div>
    </div>
  );
}

export default function BenchmarkPanels({ symbol }: BenchmarkPanelsProps) {
  const { data, meta, state, error } = useAtlasData<BenchmarkData>(
    `/api/v1/stocks/${symbol}`,
    { include: "rs_panels" },
    { dataClass: "daily_regime" }
  );

  const panels = data?.panels ?? data?.records ?? [];
  const effectiveState = state === "ready" && panels.length === 0 ? "empty" : state;

  return (
    <div data-component="four-universal-benchmarks">
      <DataBlock
        state={effectiveState}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No benchmark data"
        emptyBody="Benchmark comparison data is not available."
      >
        {panels.length > 0 && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {panels.map((p, i) => (
              <PanelCard key={p.benchmark ?? i} panel={p} />
            ))}
          </div>
        )}
      </DataBlock>
    </div>
  );
}
