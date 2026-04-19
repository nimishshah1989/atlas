"use client";

import { use, useState, useEffect } from "react";
import StockHeroBlock from "@/components/stocks/StockHeroBlock";
import StockChartBlock from "@/components/stocks/StockChartBlock";
import SignalStripBlock from "@/components/stocks/SignalStripBlock";
import DivergencesStockBlock from "@/components/stocks/DivergencesStockBlock";
import SignalHistoryStockBlock from "@/components/stocks/SignalHistoryStockBlock";
import PeersBlock from "@/components/stocks/PeersBlock";
import BenchmarkPanels from "@/components/stocks/BenchmarkPanels";
import InsiderBlock from "@/components/stocks/InsiderBlock";
import EmptyState from "@/components/ui/EmptyState";

interface PageProps {
  params: Promise<{ symbol: string }>;
}

export default function StockDetailPage({ params }: PageProps) {
  const { symbol } = use(params);
  const upperSymbol = symbol.toUpperCase();
  const [sector, setSector] = useState<string | null>(null);

  useEffect(() => {
    document.title = `ATLAS · ${upperSymbol}`;
  }, [upperSymbol]);

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Breadcrumb */}
      <nav className="px-6 pt-4" aria-label="Breadcrumb">
        <ol className="flex items-center gap-1 text-xs text-gray-400">
          <li><a href="/" className="text-gray-500 hover:text-teal-700">Global</a></li>
          <li aria-hidden="true" className="text-gray-300">›</li>
          <li><a href="/explore" className="text-gray-500 hover:text-teal-700">Explorer</a></li>
          <li aria-hidden="true" className="text-gray-300">›</li>
          <li className="text-gray-900 font-semibold">{upperSymbol}</li>
        </ol>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-4 space-y-6">
        {/* Hero — loads first; extracts sector on success */}
        <StockHeroBlock symbol={upperSymbol} onSectorLoaded={setSector} />

        {/* Signal strip */}
        <SignalStripBlock symbol={upperSymbol} />

        {/* Chart + overlays */}
        <section aria-label="Price Chart">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Price vs Benchmark (5Y)
          </h2>
          <StockChartBlock symbol={upperSymbol} />
        </section>

        {/* Benchmark panels */}
        <section aria-label="Benchmark Comparison">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Benchmark Comparison
          </h2>
          <BenchmarkPanels symbol={upperSymbol} />
        </section>

        {/* Peers — gated on hero sector */}
        <section aria-label="Peer Comparison">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Sector Peers
          </h2>
          <PeersBlock sector={sector} currentSymbol={upperSymbol} />
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Divergences */}
          <section aria-label="Divergences">
            <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
              Divergences
            </h2>
            <DivergencesStockBlock symbol={upperSymbol} />
          </section>

          {/* Signal History */}
          <section aria-label="Signal History">
            <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
              Signal History
            </h2>
            <SignalHistoryStockBlock symbol={upperSymbol} />
          </section>
        </div>

        {/* Insider Activity */}
        <section aria-label="Insider Activity">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Insider &amp; Bulk / Block Activity
          </h2>
          <InsiderBlock symbol={upperSymbol} />
        </section>

        {/* data-v2-deferred: rec-slots and signal playback */}
        <section aria-label="Recommendations" data-v2-deferred="true">
          <EmptyState title="Coming soon" body="AI-powered recommendations will be available in a future release." />
        </section>
      </div>
    </main>
  );
}
