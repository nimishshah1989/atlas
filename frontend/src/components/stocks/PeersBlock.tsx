"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatPercent } from "@/lib/format";

interface PeerRecord {
  symbol?: string | null;
  name?: string | null;
  rs_composite?: number | string | null;
  gold_rs?: number | string | null;
  momentum?: number | string | null;
  volume?: number | string | null;
  breadth?: number | string | null;
  conviction?: number | string | null;
  [key: string]: unknown;
}

interface PeersData {
  records?: PeerRecord[];
  [key: string]: unknown;
}

interface PeersBlockProps {
  sector: string | null;
  currentSymbol: string;
}

export default function PeersBlock({ sector, currentSymbol }: PeersBlockProps) {
  const peerParams = sector
    ? {
        entity_type: "equity",
        "filters[0][field]": "sector",
        "filters[0][op]": "=",
        "filters[0][value]": sector,
        "fields": "symbol,rs_composite,gold_rs,momentum,volume,breadth,conviction",
        "sort[0][field]": "rs_composite",
        "sort[0][direction]": "desc",
        limit: 15,
      }
    : undefined;

  const { data, meta, state, error } = useAtlasData<PeersData>(
    sector ? "/api/v1/query" : null,
    peerParams,
    { dataClass: "daily_regime" }
  );

  const peers = data?.records ?? [];
  const effectiveState = state === "ready" && peers.length === 0 ? "empty" : state;

  if (!sector) {
    return (
      <div data-block="peers" className="bg-white border border-gray-200 rounded-lg p-4">
        <div className="text-sm text-gray-400 text-center py-4">Loading sector data…</div>
      </div>
    );
  }

  return (
    <div data-block="peers" className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <DataBlock
        state={effectiveState}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No peer data"
        emptyBody="No peer stocks found for this sector."
      >
        {peers.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Symbol</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">RS Composite</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Gold RS</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Momentum</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Conviction</th>
                </tr>
              </thead>
              <tbody>
                {peers.map((p, i) => (
                  <tr
                    key={i}
                    className={`border-b border-gray-100 hover:bg-gray-50 ${p.symbol === currentSymbol ? "bg-teal-50" : ""}`}
                  >
                    <td className="px-4 py-2 font-medium text-gray-900">
                      <a href={`/stocks/${p.symbol}`} className="hover:text-teal-700">
                        {p.symbol ?? "—"}
                      </a>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{p.rs_composite != null ? Number(p.rs_composite).toFixed(1) : "—"}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{p.gold_rs != null ? Number(p.gold_rs).toFixed(1) : "—"}</td>
                    <td className={`px-4 py-2 text-right tabular-nums ${p.momentum != null && Number(p.momentum) >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                      {p.momentum != null ? formatPercent(p.momentum) : "—"}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{p.conviction != null ? Number(p.conviction).toFixed(0) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
