"use client";

import type { MFHolding, MFFundSector, MFTopHolding, MFWeightedTechnicals } from "@/lib/api";
import { formatDecimal } from "@/lib/format";

export function SectorExposureTable({ sectors }: { sectors: MFFundSector[] }) {
  if (sectors.length === 0) {
    return (
      <div className="px-4 py-4 text-sm text-gray-400 text-center">
        No sector data
      </div>
    );
  }
  return (
    <table className="w-full text-sm">
      <tbody>
        {sectors.map((s) => (
          <tr key={s.sector} className="border-b last:border-0 hover:bg-gray-50">
            <td className="px-3 py-2 text-gray-700">{s.sector}</td>
            <td className="px-3 py-2 text-right text-gray-500">
              {s.stock_count} stocks
            </td>
            <td className="px-3 py-2 text-right font-medium">
              {formatDecimal(s.weight_pct)}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

type HoldingItem = MFTopHolding | MFHolding;

function getSymbol(h: HoldingItem): string {
  return h.symbol;
}

function getHoldingName(h: HoldingItem): string {
  return "holding_name" in h ? h.holding_name : "";
}

export function TopHoldingsTable({
  topHoldings,
  holdings,
}: {
  topHoldings: MFTopHolding[];
  holdings: MFHolding[];
}) {
  const items: HoldingItem[] = topHoldings.length > 0 ? topHoldings : holdings;
  if (items.length === 0) {
    return (
      <div className="px-4 py-4 text-sm text-gray-400 text-center">
        No holdings data
      </div>
    );
  }
  return (
    <table className="w-full text-sm">
      <tbody>
        {items.map((h) => (
          <tr
            key={getSymbol(h)}
            className="border-b last:border-0 hover:bg-gray-50"
          >
            <td className="px-3 py-2">
              <div className="font-medium text-gray-900">{getSymbol(h)}</div>
              <div className="text-xs text-gray-400 truncate">
                {getHoldingName(h)}
              </div>
            </td>
            <td className="px-3 py-2 text-right font-medium">
              {formatDecimal(h.weight_pct)}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function WeightedTechnicalsBlock({
  wt,
}: {
  wt: MFWeightedTechnicals;
}) {
  if (!wt.weighted_rsi && !wt.weighted_breadth_pct_above_200dma && !wt.weighted_macd_bullish_pct) {
    return null;
  }
  return (
    <div className="border rounded-lg p-4">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
        Portfolio Technicals (weighted by holding weight)
      </h3>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <div className="text-xs text-gray-400">Weighted RSI</div>
          <div className="text-sm font-medium mt-0.5">
            {formatDecimal(wt.weighted_rsi)}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-400">% Above 200DMA</div>
          <div className="text-sm font-medium mt-0.5">
            {wt.weighted_breadth_pct_above_200dma
              ? `${formatDecimal(wt.weighted_breadth_pct_above_200dma)}%`
              : "—"}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-400">MACD Bullish %</div>
          <div className="text-sm font-medium mt-0.5">
            {wt.weighted_macd_bullish_pct
              ? `${formatDecimal(wt.weighted_macd_bullish_pct)}%`
              : "—"}
          </div>
        </div>
      </div>
      {wt.as_of_date && (
        <p className="text-xs text-gray-400 mt-2">as of {wt.as_of_date}</p>
      )}
    </div>
  );
}
