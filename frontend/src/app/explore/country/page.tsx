"use client";

// data-endpoint blocks from explore-country.html:
// 1. /api/v1/stocks/breadth {universe:"nifty500"} → Regime section (RegimeBanner-style)
// 2. /api/v1/stocks/breadth {universe:"nifty500",range:"5y"} → BreadthCompactBlock
// 3. /api/v1/derivatives/summary → DerivativesBlock (data-sparse="true")
// 4. /api/v1/macros/yield-curve {tenors:"2Y,10Y,30Y,real"} → YieldCurveBlock
// 5. /api/v1/query {entity_type:"timeseries"} → InrChartBlock (data-sparse="true")
// 6. /api/v1/global/flows {scope:"india",range:"5y"} → FlowsBlock
// 7. /api/v1/sectors/rrg {include:"gold_rs,conviction"} → SectorsRRGBlock
// 8. /api/v1/stocks/breadth/zone-events {universe:"nifty500",range:"5y"} → ZoneEventsTable
// 9. /api/v1/stocks/breadth/divergences {universe:"nifty500"} → DivergencesCountryBlock
// data-v2-derived="true" → EmptyState title="Coming soon"

import { useEffect } from "react";
import BreadthCompactBlock from "@/components/explore/BreadthCompactBlock";
import DerivativesBlock from "@/components/explore/DerivativesBlock";
import YieldCurveBlock from "@/components/explore/YieldCurveBlock";
import InrChartBlock from "@/components/explore/InrChartBlock";
import FlowsBlock from "@/components/explore/FlowsBlock";
import SectorsRRGBlock from "@/components/explore/SectorsRRGBlock";
import ZoneEventsTable from "@/components/explore/ZoneEventsTable";
import DivergencesCountryBlock from "@/components/explore/DivergencesCountryBlock";
import EmptyState from "@/components/ui/EmptyState";

export default function ExploreCountryPage() {
  useEffect(() => {
    document.title = "ATLAS · Explore India";
  }, []);

  return (
    <main className="min-h-screen bg-gray-50">
      <title>ATLAS · Explore India</title>

      {/* Breadcrumbs */}
      <nav className="px-6 pt-4" aria-label="Breadcrumb">
        <ol className="flex items-center gap-1 text-xs text-gray-400">
          <li>
            <a href="/" className="text-gray-500 font-medium hover:text-teal-700">
              Today
            </a>
          </li>
          <li aria-hidden="true" className="text-gray-300">›</li>
          <li>
            <a href="/explore" className="text-gray-500 font-medium hover:text-teal-700">
              Explore
            </a>
          </li>
          <li aria-hidden="true" className="text-gray-300">›</li>
          <li className="text-gray-900 font-semibold">India</li>
        </ol>
      </nav>

      {/* Page header */}
      <header className="border-b border-gray-200 bg-white px-6 py-4 mt-2">
        <h1 className="text-xl font-bold text-gray-900">India market landscape</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Regime, breadth, derivatives, macro, flows, and sector rotation
        </p>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Breadth Compact Section */}
        <section aria-label="Market Breadth">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Market Breadth
          </h2>
          <BreadthCompactBlock />
        </section>

        {/* Derivatives Section */}
        <section aria-label="Derivatives">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Derivatives
          </h2>
          <DerivativesBlock />
        </section>

        {/* G-Sec / Yield Curve Section */}
        <section aria-label="G-Sec / Yield Curve">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            G-Sec / Yield Curve
          </h2>
          <YieldCurveBlock />
        </section>

        {/* INR Section */}
        <section aria-label="INR">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            INR
          </h2>
          <InrChartBlock />
        </section>

        {/* FII/DII Flows Section */}
        <section aria-label="FII/DII Flows">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            FII / DII Flows
          </h2>
          <FlowsBlock />
        </section>

        {/* Sectors RRG + Zone Events + Divergences */}
        <section aria-label="Sector Rotation (RRG)">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Sectors RRG
          </h2>
          <SectorsRRGBlock />
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <section aria-label="Zone Events">
            <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
              Zone Events
            </h2>
            <ZoneEventsTable />
          </section>

          <section aria-label="Divergences">
            <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
              Factor Divergences
            </h2>
            <DivergencesCountryBlock />
          </section>
        </div>

        {/* data-v2-derived="true" block → EmptyState */}
        <section aria-label="Signal Playback" data-v2-derived="true">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Signal Playback (Compact)
          </h2>
          <EmptyState
            title="Coming soon"
            body="Signal playback will be available in a future release."
          />
        </section>
      </div>
    </main>
  );
}
