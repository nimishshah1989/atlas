"use client";

import { useEffect, useState } from "react";
import {
  getStockDeepDive,
  getRsHistory,
  type StockDeepDive,
} from "@/lib/api";
import { formatCurrency, quadrantBg, quadrantColor } from "@/lib/format";
import RsChart, { type RsPoint } from "./deepdive/RsChart";
import ConvictionPillars from "./deepdive/ConvictionPillars";
import KeyTechnicalsGrid from "./deepdive/KeyTechnicalsGrid";

export default function DeepDivePanel({
  symbol,
  onBack,
}: {
  symbol: string;
  onBack: () => void;
}) {
  const [stock, setStock] = useState<StockDeepDive | null>(null);
  const [rsData, setRsData] = useState<RsPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([getStockDeepDive(symbol), getRsHistory(symbol, 12)])
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

  const q = stock.conviction.rs.quadrant;

  return (
    <div className="space-y-4">
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

      <RsChart data={rsData} />
      <ConvictionPillars conviction={stock.conviction} />
      <KeyTechnicalsGrid stock={stock} />
    </div>
  );
}
