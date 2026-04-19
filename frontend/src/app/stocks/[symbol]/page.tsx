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
    <main style={{ background: "var(--bg-app)", minHeight: "100vh" }}>

      {/* Page header */}
      <div style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-default)", padding: "var(--space-4) var(--space-6)" }}>
        <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto" }}>
          <div className="crumb" style={{ padding: 0, marginBottom: 4 }}>
            <a href="/explore/country">India</a>
            <span className="crumb__sep">›</span>
            {sector && <><span>{sector}</span><span className="crumb__sep">›</span></>}
            <strong style={{ color: "var(--text-primary)" }}>{upperSymbol}</strong>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto", padding: "0 var(--space-6) var(--space-10)" }}>

        {/* Hero — loads first; extracts sector on success */}
        <div style={{ marginTop: "var(--space-5)" }}>
          <StockHeroBlock symbol={upperSymbol} onSectorLoaded={setSector} />
        </div>

        {/* Signal strip */}
        <SignalStripBlock symbol={upperSymbol} />

        {/* Price chart */}
        <div>
          <div className="sec-hd">
            <h3>Price vs Benchmark</h3>
            <span className="sec-sub">5-year daily</span>
          </div>
          <StockChartBlock symbol={upperSymbol} />
        </div>

        {/* Benchmark comparison */}
        <div>
          <div className="sec-hd">
            <h3>Benchmark Comparison</h3>
          </div>
          <BenchmarkPanels symbol={upperSymbol} />
        </div>

        {/* Sector peers */}
        <div>
          <div className="sec-hd">
            <h3>Sector Peers</h3>
            {sector && <span className="sec-sub">{sector}</span>}
          </div>
          <PeersBlock sector={sector} currentSymbol={upperSymbol} />
        </div>

        {/* Divergences + Signal History — 2 col */}
        <div>
          <div className="sec-hd"><h3>Divergences &amp; Signal History</h3></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
            <DivergencesStockBlock symbol={upperSymbol} />
            <SignalHistoryStockBlock symbol={upperSymbol} />
          </div>
        </div>

        {/* Insider activity */}
        <div>
          <div className="sec-hd">
            <h3>Insider &amp; Bulk / Block Activity</h3>
          </div>
          <InsiderBlock symbol={upperSymbol} />
        </div>

        {/* Deferred */}
        <div data-v2-deferred="true">
          <div className="sec-hd">
            <h3>AI Recommendations</h3>
            <span className="sec-badge">V2</span>
          </div>
          <EmptyState title="Coming soon" body="AI-powered recommendations will be available in a future release." />
        </div>

      </div>
    </main>
  );
}
