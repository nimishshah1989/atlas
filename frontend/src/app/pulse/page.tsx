"use client";

// data-endpoint blocks from today.html:
// 1. /api/v1/stocks/breadth {universe:"nifty500"} → RegimeBanner
// 2. /api/v1/stocks/breadth {universe:"nifty500",range:"1d",include:"deltas"} → GlanceStrip
// 3. /api/v1/query/template POST {template:"sector_rotation",params:{include_gold_rs:true}} → SectorBoard
// 4. /api/v1/query/template POST {template:"top_gainers",params:{universe:"nifty500",limit:5}} → MoverStrip
// 5. /api/v1/query/template POST {template:"fund_1d_movers",params:{limit:5}} → FundStrip
// 6. /api/v1/stocks/breadth (fixture: fixtures/breadth_daily_5y.json) → SignalStrip
// 7. /api/v1/stocks/breadth/divergences {universe:"nifty500"} → DivergencesBlock
// 8. /api/v1/global/events {scope:"india,global"} → EventsOverlay
// deferred: four-decision-card (data-v2-deferred="true") → EmptyState

import { useEffect } from "react";
import RegimeBanner from "@/components/pulse/RegimeBanner";
import GlanceStrip from "@/components/pulse/GlanceStrip";
import SectorBoard from "@/components/pulse/SectorBoard";
import MoverStrip from "@/components/pulse/MoverStrip";
import FundStrip from "@/components/pulse/FundStrip";
import SignalStrip from "@/components/pulse/SignalStrip";
import DivergencesBlock from "@/components/pulse/DivergencesBlock";
import EventsOverlay from "@/components/pulse/EventsOverlay";
import EmptyState from "@/components/ui/EmptyState";

export default function PulsePage() {
  useEffect(() => {
    document.title = "ATLAS · Today";
  }, []);

  return (
    <main className="min-h-screen bg-gray-50">
      <title>ATLAS · Today</title>

      {/* Page header */}
      <header className="border-b border-gray-200 bg-white px-6 py-4">
        <h1 className="text-xl font-bold text-gray-900">Today</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Market pulse — regime, breadth, sectors, movers
        </p>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Regime Banner */}
        <section aria-label="Regime Banner">
          <RegimeBanner />
        </section>

        {/* Glance Strip — 6 KPI cells */}
        <section aria-label="At a Glance">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            At a Glance
          </h2>
          <GlanceStrip />
        </section>

        {/* Sector Board + Mover Strip side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <section aria-label="Sector Rotation">
            <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
              Sector Rotation
            </h2>
            <SectorBoard />
          </section>

          <section aria-label="Top Movers">
            <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
              Top Movers
            </h2>
            <MoverStrip />
          </section>
        </div>

        {/* Fund Strip */}
        <section aria-label="Fund Movers">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Fund Movers
          </h2>
          <FundStrip />
        </section>

        {/* Signal Strip */}
        <section aria-label="Signal Strip">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Signals
          </h2>
          <SignalStrip />
        </section>

        {/* Divergences + Events side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <section aria-label="Factor Divergences">
            <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
              Factor Divergences
            </h2>
            <DivergencesBlock />
          </section>

          <section aria-label="Events">
            <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
              Events
            </h2>
            <EventsOverlay />
          </section>
        </div>

        {/* Deferred: four-decision-card (data-v2-deferred="true") */}
        <section aria-label="Decision Cards" data-v2-deferred="true">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Decision Cards
          </h2>
          <EmptyState
            title="Coming soon"
            body="Decision cards will be available in a future release."
          />
        </section>
      </div>
    </main>
  );
}
