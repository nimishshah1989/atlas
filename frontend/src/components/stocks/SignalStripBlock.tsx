"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

interface SignalStripData {
  rs?: number | string | null;
  momentum?: number | string | null;
  volume?: number | string | null;
  breadth?: number | string | null;
  rs_label?: string | null;
  momentum_label?: string | null;
  volume_label?: string | null;
  breadth_label?: string | null;
  [key: string]: unknown;
}

interface SignalStripBlockProps {
  symbol: string;
}

function chipColor(label: string | null | undefined): string {
  const l = (label ?? "").toLowerCase();
  if (l.includes("bull") || l.includes("strong") || l.includes("high") || l.includes("above")) return "bg-emerald-100 text-emerald-700 border-emerald-200";
  if (l.includes("bear") || l.includes("weak") || l.includes("low") || l.includes("below")) return "bg-red-100 text-red-700 border-red-200";
  return "bg-amber-100 text-amber-700 border-amber-200";
}

export default function SignalStripBlock({ symbol }: SignalStripBlockProps) {
  const { data, meta, state, error } = useAtlasData<SignalStripData>(
    `/api/v1/stocks/${symbol}`,
    { include: "rs_strip" },
    { dataClass: "intraday" }
  );

  const chips = [
    { label: "RS", value: data?.rs_label ?? (data?.rs != null ? String(data.rs) : null) },
    { label: "Momentum", value: data?.momentum_label ?? (data?.momentum != null ? String(data.momentum) : null) },
    { label: "Volume", value: data?.volume_label ?? (data?.volume != null ? String(data.volume) : null) },
    { label: "Breadth", value: data?.breadth_label ?? (data?.breadth != null ? String(data.breadth) : null) },
  ];

  const effectiveState = state === "ready" && chips.every(c => c.value === null) ? "empty" : state;

  return (
    <div data-component="signal-strip" className="flex gap-3 flex-wrap">
      <DataBlock
        state={effectiveState}
        dataClass="intraday"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No signal data"
      >
        {(state === "ready" || state === "stale") && (
          <div className="flex gap-3 flex-wrap">
            {chips.map((chip) => (
              <span
                key={chip.label}
                data-chip={chip.label.toLowerCase()}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border ${chipColor(chip.value)}`}
              >
                <span className="text-gray-500 font-normal">{chip.label}</span>
                {chip.value ?? "—"}
              </span>
            ))}
          </div>
        )}
      </DataBlock>
    </div>
  );
}
