"use client";

import { useState } from "react";
import { getMfOverlap, type MFOverlapHolding, type MFOverlapResponse } from "@/lib/api-mf";
import { formatDecimal } from "@/lib/format";

interface MFOverlapWidgetProps {
  mstarId: string;
}

function OverlapTable({ holdings }: { holdings: MFOverlapHolding[] }) {
  if (holdings.length === 0) {
    return (
      <div className="py-4 text-sm text-gray-400 text-center">
        No common holdings found
      </div>
    );
  }

  const sorted = [...holdings].sort((a, b) => {
    const minA = Math.min(parseFloat(a.weight_a) || 0, parseFloat(a.weight_b) || 0);
    const minB = Math.min(parseFloat(b.weight_a) || 0, parseFloat(b.weight_b) || 0);
    return minB - minA;
  });

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b bg-gray-50">
          <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500">Symbol</th>
          <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">Fund A %</th>
          <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">Fund B %</th>
          <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500">Min %</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((h) => {
          const wa = parseFloat(h.weight_a) || 0;
          const wb = parseFloat(h.weight_b) || 0;
          const minW = Math.min(wa, wb);
          return (
            <tr key={h.instrument_id || h.symbol} className="border-b last:border-0 hover:bg-gray-50">
              <td className="px-3 py-2 font-medium text-gray-900">{h.symbol}</td>
              <td className="px-3 py-2 text-right text-gray-600">{formatDecimal(h.weight_a)}%</td>
              <td className="px-3 py-2 text-right text-gray-600">{formatDecimal(h.weight_b)}%</td>
              <td className="px-3 py-2 text-right font-medium text-gray-900">{formatDecimal(String(minW))}%</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function MFOverlapWidget({ mstarId }: MFOverlapWidgetProps) {
  const [compareId, setCompareId] = useState("");
  const [result, setResult] = useState<MFOverlapResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleCompare() {
    const id = compareId.trim();
    if (!id) return;
    setLoading(true);
    setError(null);
    setResult(null);

    getMfOverlap(mstarId, id)
      .then((resp) => setResult(resp))
      .catch((e: Error) => setError(e.message ?? "Failed to load overlap data"))
      .finally(() => setLoading(false));
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") handleCompare();
  }

  return (
    <div className="border rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b bg-gray-50">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          Portfolio Overlap
        </h3>
        <p className="text-xs text-gray-400 mt-0.5">
          Compare this fund with another to find common holdings
        </p>
      </div>

      <div className="px-4 py-3">
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Enter fund ID (e.g. F0GBR04QJK)"
            value={compareId}
            onChange={(e) => setCompareId(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 text-sm border rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-teal-500 focus:border-teal-500"
          />
          <button
            onClick={handleCompare}
            disabled={loading || !compareId.trim()}
            className="text-sm px-4 py-1.5 bg-teal-600 text-white rounded hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Loading…" : "Compare"}
          </button>
        </div>
      </div>

      {error && (
        <div className="px-4 pb-3 text-sm text-red-600">{error}</div>
      )}

      {result && (
        <div>
          <div className="px-4 py-2 border-t bg-gray-50 flex items-center gap-4">
            <div>
              <span className="text-xs text-gray-500">Overlap</span>
              <span className="ml-2 text-lg font-bold text-gray-900">
                {formatDecimal(result.overlap_pct)}%
              </span>
            </div>
            <div className="text-xs text-gray-400">
              {result.common_holdings.length} common holding
              {result.common_holdings.length !== 1 ? "s" : ""}
            </div>
            <div className="text-xs text-gray-400 ml-auto">
              {result.fund_a} vs {result.fund_b}
            </div>
          </div>
          <OverlapTable holdings={result.common_holdings} />
        </div>
      )}
    </div>
  );
}
