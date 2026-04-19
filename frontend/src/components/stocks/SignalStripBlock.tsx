"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

interface ApiShape {
  stock?: {
    conviction?: {
      rs?: {
        rs_composite?: number | string | null;
        rs_1w?: number | string | null;
        rs_1m?: number | string | null;
        rs_3m?: number | string | null;
        rs_6m?: number | string | null;
        rs_12m?: number | string | null;
        quadrant?: string | null;
        benchmark?: string | null;
      } | null;
      technical?: {
        checks_passing?: number;
        checks_total?: number;
      } | null;
    } | null;
    above_200dma?: boolean | null;
    above_50dma?: boolean | null;
    rsi_14?: number | string | null;
  };
  [key: string]: unknown;
}

interface SignalStripBlockProps {
  symbol: string;
}

function chipStyle(isPositive: boolean | null): React.CSSProperties {
  if (isPositive === true)  return { background: "var(--rag-green-100)", color: "var(--rag-green-700)", border: "1px solid var(--rag-green-200)" };
  if (isPositive === false) return { background: "var(--rag-red-100)",   color: "var(--rag-red-700)",   border: "1px solid var(--rag-red-200)" };
  return { background: "var(--bg-inset)", color: "var(--text-secondary)", border: "1px solid var(--border-default)" };
}

function numColor(v: number | null): string {
  if (v === null) return "var(--text-secondary)";
  return v >= 0 ? "var(--rag-green-700)" : "var(--rag-red-700)";
}

export default function SignalStripBlock({ symbol }: SignalStripBlockProps) {
  const { data: rawData, meta, state, error } = useAtlasData<ApiShape>(
    `/api/v1/stocks/${symbol}`,
    {},
    { dataClass: "intraday" }
  );

  const stock = rawData?.stock;
  const rs = stock?.conviction?.rs;
  const tech = stock?.conviction?.technical;

  const rsComposite = rs?.rs_composite != null ? Number(rs.rs_composite) : null;
  const rs1m = rs?.rs_1m != null ? Number(rs.rs_1m) : null;
  const rs3m = rs?.rs_3m != null ? Number(rs.rs_3m) : null;
  const rsPositive = rsComposite !== null ? rsComposite >= 0 : null;

  const chips = [
    {
      label: `RS vs ${rs?.benchmark ?? "Nifty 500"}`,
      value: rsComposite != null ? rsComposite.toFixed(1) : "—",
      positive: rsPositive,
    },
    {
      label: "RS 1M",
      value: rs1m != null ? rs1m.toFixed(1) : "—",
      positive: rs1m !== null ? rs1m >= 0 : null,
    },
    {
      label: "RS 3M",
      value: rs3m != null ? rs3m.toFixed(1) : "—",
      positive: rs3m !== null ? rs3m >= 0 : null,
    },
    {
      label: "Quadrant",
      value: rs?.quadrant ?? "—",
      positive: rs?.quadrant === "LEADING" ? true : rs?.quadrant === "LAGGING" || rs?.quadrant === "WEAKENING" ? false : null,
    },
    {
      label: "Tech Checks",
      value: tech ? `${tech.checks_passing ?? 0}/${tech.checks_total ?? 10}` : "—",
      positive: tech?.checks_passing != null ? tech.checks_passing >= 5 : null,
    },
    {
      label: "200 DMA",
      value: stock?.above_200dma == null ? "—" : stock.above_200dma ? "Above" : "Below",
      positive: stock?.above_200dma ?? null,
    },
  ];

  const hasAnyData = chips.some(c => c.value !== "—");
  const effectiveState = state === "ready" && !hasAnyData ? "empty" : state;

  return (
    <div
      data-component="signal-strip"
      style={{ marginTop: "var(--space-4)", marginBottom: "var(--space-1)" }}
    >
      <DataBlock
        state={effectiveState}
        dataClass="intraday"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No signal data"
      >
        {(state === "ready" || state === "stale") && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
            {chips.map((chip) => (
              <span
                key={chip.label}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  padding: "4px 10px",
                  borderRadius: "var(--radius-full)",
                  fontSize: 11,
                  fontWeight: 600,
                  ...chipStyle(chip.positive),
                }}
              >
                <span style={{ fontWeight: 400, color: "var(--text-tertiary)" }}>{chip.label}</span>
                <span style={{ color: chip.value === "—" ? "var(--text-tertiary)" : numColor(
                  chip.value !== "—" && !isNaN(Number(chip.value.replace(/\//g, ""))) ? Number(chip.value) : null
                ) }}>
                  {chip.value}
                </span>
              </span>
            ))}
          </div>
        )}
      </DataBlock>
    </div>
  );
}
