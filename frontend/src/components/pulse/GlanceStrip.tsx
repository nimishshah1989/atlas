"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

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
  breadth_score: string | null;
  momentum_score: string | null;
}

interface GlanceApiData {
  breadth: GlanceBreadth;
  regime: GlanceRegime;
}

function ragClass(val: string | null): "g" | "a" | "r" | "" {
  if (val === null) return "";
  const n = parseFloat(String(val));
  if (isNaN(n)) return "";
  if (n >= 60) return "g";
  if (n >= 40) return "a";
  return "r";
}

function fmtPct(val: string | null): string {
  if (val === null) return "—";
  const n = parseFloat(String(val));
  if (isNaN(n)) return "—";
  return n.toFixed(1) + "%";
}

function fmtScore(val: string | null): string {
  if (val === null) return "—";
  const n = parseFloat(String(val));
  if (isNaN(n)) return "—";
  return (n * 100).toFixed(0);
}

function regimePillStyle(regime: string): React.CSSProperties {
  const u = regime.toUpperCase();
  if (u.includes("BULL") || u.includes("EXPANSION"))
    return { background: "var(--rag-green-100)", color: "var(--rag-green-700)" };
  if (u.includes("BEAR") || u.includes("CONTRACTION"))
    return { background: "var(--rag-red-100)", color: "var(--rag-red-700)" };
  return { background: "var(--rag-amber-100)", color: "var(--rag-amber-700)" };
}

export default function GlanceStrip() {
  const { data, meta, state, error } = useAtlasData<GlanceApiData>(
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
      emptyBody="At-a-glance metrics are unavailable for today."
    >
      {data && (() => {
        const adNet = data.breadth.advance - data.breadth.decline;
        const adSign = adNet >= 0 ? "+" : "";
        const bClass = ragClass(data.breadth.pct_above_200dma);
        const mClass = ragClass(data.regime.momentum_score !== null
          ? String(parseFloat(String(data.regime.momentum_score)) * 100) : null);

        return (
          <div className="mgrid mgrid--6" data-block="glance-strip">
            <div className="mbox">
              <div className="mbox__l">Advance / Decline</div>
              <div className="mbox__v">{data.breadth.advance} / {data.breadth.decline}</div>
              <div className={`mbox__d mbox__d--${adNet >= 0 ? "pos" : "neg"}`}>
                Net {adSign}{adNet}
              </div>
            </div>
            <div className={`mbox${bClass ? ` mbox--${bClass}` : ""}`}>
              <div className="mbox__l">Above 200 DMA</div>
              <div className="mbox__v">{fmtPct(data.breadth.pct_above_200dma)}</div>
              <div className="mbox__d" style={{ color: "var(--text-tertiary)" }}>structural breadth</div>
            </div>
            <div className="mbox">
              <div className="mbox__l">Above 50 DMA</div>
              <div className="mbox__v">{fmtPct(data.breadth.pct_above_50dma)}</div>
              <div className="mbox__d" style={{ color: "var(--text-tertiary)" }}>swing breadth</div>
            </div>
            <div className="mbox">
              <div className="mbox__l">52W High / Low</div>
              <div className="mbox__v">{data.breadth.new_52w_highs} / {data.breadth.new_52w_lows}</div>
              <div className={`mbox__d mbox__d--${data.breadth.new_52w_highs >= data.breadth.new_52w_lows ? "pos" : "neg"}`}>
                net {data.breadth.new_52w_highs - data.breadth.new_52w_lows >= 0 ? "+" : ""}
                {data.breadth.new_52w_highs - data.breadth.new_52w_lows}
              </div>
            </div>
            <div className={`mbox${mClass ? ` mbox--${mClass}` : ""}`}>
              <div className="mbox__l">Momentum Score</div>
              <div className="mbox__v">
                {data.regime.momentum_score !== null ? fmtScore(data.regime.momentum_score) : "—"}
              </div>
              <div className="mbox__d" style={{ color: "var(--text-tertiary)" }}>out of 100</div>
            </div>
            <div className="mbox">
              <div className="mbox__l">Regime</div>
              <div className="mbox__v">
                <span
                  style={{
                    ...regimePillStyle(data.regime.regime),
                    display: "inline-block",
                    padding: "2px 8px",
                    borderRadius: "var(--radius-full)",
                    fontSize: 11,
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: ".05em",
                  }}
                >
                  {data.regime.regime}
                </span>
              </div>
              {data.regime.confidence !== null && (
                <div className="mbox__d" style={{ color: "var(--text-tertiary)" }}>
                  {parseFloat(String(data.regime.confidence)).toFixed(0)}% confidence
                </div>
              )}
            </div>
          </div>
        );
      })()}
    </DataBlock>
  );
}
