"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

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
}

interface SignalApiData {
  breadth: BreadthFields;
  regime: RegimeFields;
}

/**
 * Convert pct string + total to count.
 * e.g. "49.0", 500 → 245
 */
function pctToCount(pct: string | null, total: number): number | null {
  if (pct === null) return null;
  const n = parseFloat(String(pct));
  if (isNaN(n)) return null;
  return Math.round((n / 100) * total);
}

function signalClass(count: number | null, total: number): "bull" | "bear" | "neut" {
  if (count === null) return "neut";
  const pct = count / total;
  if (pct >= 0.6) return "bull";
  if (pct >= 0.4) return "neut";
  return "bear";
}

function signalLabel(cls: "bull" | "bear" | "neut"): string {
  if (cls === "bull") return "Bullish";
  if (cls === "bear") return "Bearish";
  return "Neutral";
}

interface DmaCardProps {
  label: string;
  tooltip: string;
  count: number | null;
  total: number;
  pctStr: string | null;
}

function DmaCard({ label, tooltip, count, total, pctStr }: DmaCardProps) {
  const sig = signalClass(count, total);
  const pct = pctStr !== null ? parseFloat(String(pctStr)).toFixed(1) : null;

  return (
    <div className={`ss-card ss-card--${sig}`} title={tooltip}>
      <div className="ss-top">
        <div className="ss-lbl">{label}</div>
        <div className={`ss-sig ss-sig--${sig}`}>{signalLabel(sig)}</div>
      </div>
      <div className="ss-main">
        <div className="ss-val">{count !== null ? count : "—"}</div>
        {count !== null && <div className="ss-denom">/ {total}</div>}
      </div>
      <div className="ss-foot">
        {pct !== null ? `${pct}% of universe` : "—"}
      </div>
    </div>
  );
}

export default function SignalStrip() {
  const { data, meta, state, error } = useAtlasData<SignalApiData>(
    "/api/v1/stocks/breadth",
    { universe: "nifty500" },
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
      emptyBody="DMA breadth signals are unavailable."
    >
      {data && (() => {
        const total = (data.breadth.advance ?? 0) + (data.breadth.decline ?? 0);
        const universe = total > 0 ? total : 500;
        const above50Count = pctToCount(data.breadth.pct_above_50dma, universe);
        const above200Count = pctToCount(data.breadth.pct_above_200dma, universe);

        return (
          <div className="ss-strip" data-block="signal-strip">
            <DmaCard
              label="Above 50 DMA"
              tooltip="Medium-term trend breadth. Count of Nifty 500 stocks above their 50-day simple moving average."
              count={above50Count}
              total={universe}
              pctStr={data.breadth.pct_above_50dma}
            />
            <DmaCard
              label="Above 200 DMA"
              tooltip="Long-term structural breadth. Count of Nifty 500 stocks above their 200-day SMA. Below 50% = structural bear; above 70% = structural bull."
              count={above200Count}
              total={universe}
              pctStr={data.breadth.pct_above_200dma}
            />
            {/* 3rd card: 52-week highs vs lows */}
            <div
              className={`ss-card ss-card--${data.breadth.new_52w_highs >= data.breadth.new_52w_lows ? "bull" : "bear"}`}
              title="52-week new highs minus new lows. A positive net reading supports the bullish case."
            >
              <div className="ss-top">
                <div className="ss-lbl">52W High / Low</div>
                <div className={`ss-sig ss-sig--${data.breadth.new_52w_highs >= data.breadth.new_52w_lows ? "bull" : "bear"}`}>
                  {data.breadth.new_52w_highs >= data.breadth.new_52w_lows ? "Bullish" : "Bearish"}
                </div>
              </div>
              <div className="ss-main">
                <div className="ss-val">{data.breadth.new_52w_highs}</div>
                <div className="ss-denom">H</div>
              </div>
              <div className="ss-foot">
                <span className="neg">{data.breadth.new_52w_lows} new lows</span>
                {" · "}Net {data.breadth.new_52w_highs - data.breadth.new_52w_lows >= 0 ? "+" : ""}
                {data.breadth.new_52w_highs - data.breadth.new_52w_lows}
              </div>
            </div>
          </div>
        );
      })()}
    </DataBlock>
  );
}
