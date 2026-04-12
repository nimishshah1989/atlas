"use client";

import { useEffect, useState } from "react";
import {
  getStockDeepDive,
  getRsHistory,
  type StockDeepDive,
  type RsHistoryResponse,
} from "@/lib/api";
import {
  formatDecimal,
  formatCurrency,
  quadrantColor,
  quadrantBg,
  signColor,
} from "@/lib/format";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

export default function DeepDivePanel({
  symbol,
  onBack,
}: {
  symbol: string;
  onBack: () => void;
}) {
  const [stock, setStock] = useState<StockDeepDive | null>(null);
  const [rsData, setRsData] = useState<
    { date: string; rs: number | null }[]
  >([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getStockDeepDive(symbol),
      getRsHistory(symbol, 12),
    ])
      .then(([dive, hist]) => {
        setStock(dive.stock);
        setRsData(
          hist.data.map((d) => ({
            date: d.date,
            rs: d.rs_composite ? parseFloat(d.rs_composite) : null,
          }))
        );
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [symbol]);

  if (loading) {
    return (
      <div className="animate-pulse space-y-4">
        <div className="h-8 bg-gray-100 rounded w-1/3" />
        <div className="h-48 bg-gray-100 rounded" />
        <div className="grid grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-24 bg-gray-100 rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (!stock) return <div>Stock not found</div>;

  const { conviction } = stock;
  const q = conviction.rs.quadrant;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="text-sm text-gray-500 hover:text-gray-800"
            >
              ← Back
            </button>
            <h2 className="text-xl font-bold text-gray-900">{stock.symbol}</h2>
            <span
              className={`text-xs px-2 py-0.5 rounded border ${quadrantBg(q)} ${quadrantColor(q)}`}
            >
              {q || "—"}
            </span>
            {stock.nifty_50 && (
              <span className="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded">
                NIFTY 50
              </span>
            )}
            {stock.cap_category && (
              <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">
                {stock.cap_category}
              </span>
            )}
          </div>
          <p className="text-sm text-gray-600 mt-0.5">
            {stock.company_name} &middot; {stock.sector}
            {stock.industry ? ` / ${stock.industry}` : ""}
          </p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold">{formatCurrency(stock.close)}</div>
        </div>
      </div>

      {/* RS Chart */}
      <div className="border rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Relative Strength vs NIFTY 500 (12m)
        </h3>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={rsData}>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10 }}
              tickFormatter={(v) => v.slice(5)}
            />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip
              contentStyle={{ fontSize: 12 }}
              labelFormatter={(v) => `Date: ${v}`}
            />
            <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="3 3" />
            <Line
              type="monotone"
              dataKey="rs"
              stroke="#1D9E75"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Conviction Pillars */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Pillar 1: RS */}
        <div className="border rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Pillar 1: Relative Strength
          </h3>
          <div className="space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">RS Composite</span>
              <span className={`font-medium ${signColor(conviction.rs.rs_composite)}`}>
                {formatDecimal(conviction.rs.rs_composite)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Momentum</span>
              <span className={`font-medium ${signColor(conviction.rs.rs_momentum)}`}>
                {formatDecimal(conviction.rs.rs_momentum)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">1W / 1M / 3M</span>
              <span className="text-xs tabular-nums">
                {formatDecimal(conviction.rs.rs_1w, 1)} /{" "}
                {formatDecimal(conviction.rs.rs_1m, 1)} /{" "}
                {formatDecimal(conviction.rs.rs_3m, 1)}
              </span>
            </div>
          </div>
          <p className="text-xs text-gray-500 mt-2 italic">
            {conviction.rs.explanation}
          </p>
        </div>

        {/* Pillar 2: Technical */}
        <div className="border rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Pillar 2: Technical Health
          </h3>
          <div className="text-2xl font-bold text-center mb-2">
            <span
              className={
                conviction.technical.checks_passing >= 7
                  ? "text-emerald-600"
                  : conviction.technical.checks_passing >= 4
                    ? "text-amber-600"
                    : "text-red-600"
              }
            >
              {conviction.technical.checks_passing}
            </span>
            <span className="text-gray-400 text-lg">
              /{conviction.technical.checks_total}
            </span>
          </div>
          <div className="space-y-1">
            {conviction.technical.checks.map((c) => (
              <div
                key={c.name}
                className="flex items-center gap-1.5 text-xs"
              >
                <span
                  className={
                    c.value === "N/A"
                      ? "text-gray-400"
                      : c.passing
                        ? "text-emerald-500"
                        : "text-red-500"
                  }
                >
                  {c.value === "N/A" ? "○" : c.passing ? "●" : "●"}
                </span>
                <span className="text-gray-600">{c.name}</span>
                <span className="text-gray-400 ml-auto truncate max-w-[100px]">
                  {c.value !== "N/A" ? c.value : "—"}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Pillar 3: Institutional */}
        <div className="border rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Pillar 3: Institutional
          </h3>
          <div className="space-y-3">
            <div>
              <div className="text-xs text-gray-500">MF Holders</div>
              <div className="text-2xl font-bold">
                {conviction.institutional.mf_holder_count ?? "—"}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Delivery vs Avg</div>
              <div className="text-lg font-medium">
                {conviction.institutional.delivery_vs_avg
                  ? `${formatDecimal(conviction.institutional.delivery_vs_avg)}x`
                  : "—"}
              </div>
            </div>
          </div>
          <p className="text-xs text-gray-500 mt-2 italic">
            {conviction.institutional.explanation}
          </p>
        </div>
      </div>

      {/* Key Technicals Grid */}
      <div className="border rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">
          Key Technicals
        </h3>
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-sm">
          {[
            { label: "RSI", value: stock.rsi_14, fmt: (v: string) => formatDecimal(v, 1) },
            { label: "ADX", value: stock.adx_14, fmt: (v: string) => formatDecimal(v, 1) },
            { label: "MACD", value: stock.macd_histogram, fmt: (v: string) => formatDecimal(v, 4) },
            { label: "Beta", value: stock.beta_nifty, fmt: formatDecimal },
            { label: "Sharpe 1Y", value: stock.sharpe_1y, fmt: formatDecimal },
            { label: "Sortino 1Y", value: stock.sortino_1y, fmt: formatDecimal },
            { label: "Max DD 1Y", value: stock.max_drawdown_1y, fmt: (v: string) => `${formatDecimal(v)}%` },
            { label: "Vol 20d", value: stock.volatility_20d, fmt: (v: string) => `${formatDecimal(v)}%` },
            { label: "SMA 50", value: stock.sma_50, fmt: (v: string) => formatCurrency(v) },
            { label: "SMA 200", value: stock.sma_200, fmt: (v: string) => formatCurrency(v) },
            { label: "200 DMA", value: stock.above_200dma, fmt: (v: boolean) => v ? "Above" : "Below" },
            { label: "50 DMA", value: stock.above_50dma, fmt: (v: boolean) => v ? "Above" : "Below" },
          ].map((item) => (
            <div key={item.label}>
              <div className="text-xs text-gray-500">{item.label}</div>
              <div className={`font-medium ${item.value !== null && item.value !== undefined ? signColor(item.value as string) : ""}`}>
                {item.value !== null && item.value !== undefined
                  ? (item.fmt as (v: unknown) => string)(item.value)
                  : "—"}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
