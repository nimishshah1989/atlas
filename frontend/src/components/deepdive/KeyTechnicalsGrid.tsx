"use client";

import type { StockDeepDive } from "@/lib/api";
import { formatCurrency, formatDecimal, signColor } from "@/lib/format";

export default function KeyTechnicalsGrid({ stock }: { stock: StockDeepDive }) {
  const items: Array<{ label: string; value: unknown; fmt: (v: unknown) => string }> = [
    { label: "RSI", value: stock.rsi_14, fmt: (v) => formatDecimal(v as string, 1) },
    { label: "ADX", value: stock.adx_14, fmt: (v) => formatDecimal(v as string, 1) },
    { label: "MACD", value: stock.macd_histogram, fmt: (v) => formatDecimal(v as string, 4) },
    { label: "Beta", value: stock.beta_nifty, fmt: (v) => formatDecimal(v as string) },
    { label: "Sharpe 1Y", value: stock.sharpe_1y, fmt: (v) => formatDecimal(v as string) },
    { label: "Sortino 1Y", value: stock.sortino_1y, fmt: (v) => formatDecimal(v as string) },
    { label: "Max DD 1Y", value: stock.max_drawdown_1y, fmt: (v) => `${formatDecimal(v as string)}%` },
    { label: "Vol 20d", value: stock.volatility_20d, fmt: (v) => `${formatDecimal(v as string)}%` },
    { label: "SMA 50", value: stock.sma_50, fmt: (v) => formatCurrency(v as string) },
    { label: "SMA 200", value: stock.sma_200, fmt: (v) => formatCurrency(v as string) },
    { label: "200 DMA", value: stock.above_200dma, fmt: (v) => (v ? "Above" : "Below") },
    { label: "50 DMA", value: stock.above_50dma, fmt: (v) => (v ? "Above" : "Below") },
  ];

  return (
    <div className="border rounded-lg p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Key Technicals</h3>
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-sm">
        {items.map((item) => {
          const present = item.value !== null && item.value !== undefined;
          return (
            <div key={item.label}>
              <div className="text-xs text-gray-500">{item.label}</div>
              <div
                className={`font-medium ${present && typeof item.value === "string" ? signColor(item.value) : ""}`}
              >
                {present ? item.fmt(item.value) : "—"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
