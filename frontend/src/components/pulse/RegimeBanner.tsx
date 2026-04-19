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
  confidence: string | null;
  days_in_regime?: number;
}

interface BreadthApiData {
  breadth: BreadthFields;
  regime: RegimeFields;
}

/** Returns lowercase slug for CSS modifier class */
function regimeSlug(regime: string): string {
  const u = regime.toUpperCase();
  if (u.includes("BULL") || u.includes("EXPANSION")) return "expansion";
  if (u.includes("BEAR") || u.includes("CONTRACTION")) return "contraction";
  if (u.includes("RECOVERY")) return "recovery";
  return "correction";
}

/** Short narrative text for each regime type */
function regimeNarrative(regime: string, breadth: BreadthFields): string {
  const slug = regimeSlug(regime);
  const above200 = breadth.pct_above_200dma !== null
    ? parseFloat(String(breadth.pct_above_200dma)).toFixed(0) + "%"
    : "—";
  const adNet = breadth.advance - breadth.decline;
  const adSign = adNet >= 0 ? "+" : "";

  switch (slug) {
    case "expansion":
      return `Breadth is expanding — ${above200} of universe above 200-DMA. A/D net ${adSign}${adNet}. Conditions favour new long positions and sector rotation into leaders.`;
    case "contraction":
      return `Structural breadth has weakened — only ${above200} of universe above 200-DMA. A/D net ${adSign}${adNet}. Reduce position sizing, tighten stops, and wait for breadth recovery before adding exposure.`;
    case "recovery":
      return `Breadth is recovering — ${above200} above 200-DMA and A/D net ${adSign}${adNet}. Early-stage improvement visible; wait for confirmation above 60% before adding new exposure.`;
    default: // correction
      return `Breadth is under pressure — ${above200} above 200-DMA. A/D net ${adSign}${adNet}. Many stocks in individual downtrends even as headline indices hold. Tighten stops and reduce new exposure.`;
  }
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
      {data && (() => {
        const slug = regimeSlug(data.regime.regime);
        const days = data.regime.days_in_regime;
        return (
          <div
            className={`regime-banner regime-banner--${slug}`}
            data-block="regime-banner"
          >
            {/* Left: label + serif regime name */}
            <div className="rb-left">
              <div className="rb-label">Market Regime</div>
              <div className="rb-name">{data.regime.regime}</div>
            </div>

            {/* Centre: narrative */}
            <div className="rb-text">
              {regimeNarrative(data.regime.regime, data.breadth)}
              {data.regime.confidence !== null && (
                <span style={{ marginLeft: 6, fontSize: 11, color: "var(--text-tertiary)" }}>
                  Confidence: {parseFloat(String(data.regime.confidence)).toFixed(0)}%
                </span>
              )}
            </div>

            {/* Right: days counter */}
            {typeof days === "number" && days > 0 ? (
              <div className="rb-days">
                <div className="rb-count">{days}</div>
                <div className="rb-unit">Days in Regime</div>
              </div>
            ) : (
              <div className="rb-days">
                <div className="rb-count" style={{ fontSize: 20, color: "var(--text-tertiary)" }}>—</div>
                <div className="rb-unit">Days in Regime</div>
              </div>
            )}
          </div>
        );
      })()}
    </DataBlock>
  );
}
