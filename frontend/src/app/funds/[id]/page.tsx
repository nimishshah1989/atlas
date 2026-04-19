"use client";

import { use, useState, useEffect } from "react";
import EmptyState from "@/components/ui/EmptyState";
import FundHeroBlock from "@/components/funds/FundHeroBlock";
import ReturnsBlock from "@/components/funds/ReturnsBlock";
import NavChartBlock from "@/components/funds/NavChartBlock";
import AlphaRiskBlock from "@/components/funds/AlphaRiskBlock";
import RollingAlphaBetaBlock from "@/components/funds/RollingAlphaBetaBlock";
import HoldingsBlock from "@/components/funds/HoldingsBlock";
import WeightedTechnicalsBlock from "@/components/funds/WeightedTechnicalsBlock";
import SectorAllocationBlock from "@/components/funds/SectorAllocationBlock";
import SuitabilityBlock from "@/components/funds/SuitabilityBlock";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function FundDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const [category, setCategory] = useState<string | null>(null);
  const [fundName, setFundName] = useState<string>(id);

  useEffect(() => {
    document.title = `ATLAS · ${fundName}`;
  }, [fundName]);

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Breadcrumb */}
      <nav className="px-6 pt-4" aria-label="Breadcrumb">
        <ol className="flex items-center gap-1 text-xs text-gray-400">
          <li>
            <a href="/" className="text-gray-500 hover:text-teal-700">
              India
            </a>
          </li>
          <li aria-hidden="true" className="text-gray-300">
            ›
          </li>
          <li>
            <a href="/funds" className="text-gray-500 hover:text-teal-700">
              Mutual Funds
            </a>
          </li>
          <li aria-hidden="true" className="text-gray-300">
            ›
          </li>
          <li className="text-gray-900 font-semibold truncate max-w-xs">
            {id}
          </li>
        </ol>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-4 space-y-6">
        {/* Hero — loads first; extracts category and name on success */}
        <FundHeroBlock
          id={id}
          onCategoryLoaded={setCategory}
          onNameLoaded={setFundName}
        />

        {/* Returns / NAV summary table */}
        <section aria-label="Rolling Returns">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Rolling Returns
          </h2>
          <ReturnsBlock id={id} />
        </section>

        {/* NAV Chart */}
        <section aria-label="NAV History">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            NAV vs Benchmark (5Y)
          </h2>
          <NavChartBlock id={id} />
        </section>

        {/* Alpha / Risk metrics */}
        <section aria-label="Alpha and Risk">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Alpha &amp; Risk Metrics
          </h2>
          <AlphaRiskBlock id={id} />
        </section>

        {/* Rolling Alpha / Beta chart */}
        <section aria-label="Rolling Alpha and Beta">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Rolling Alpha &amp; Beta (5Y)
          </h2>
          <RollingAlphaBetaBlock id={id} />
        </section>

        {/* Holdings table — top 20 */}
        <section aria-label="Top Holdings">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Top Holdings
          </h2>
          <HoldingsBlock id={id} />
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Weighted Technicals */}
          <section aria-label="Weighted Technicals">
            <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
              Weighted Technicals
            </h2>
            <WeightedTechnicalsBlock id={id} />
          </section>

          {/* Sector Allocation */}
          <section aria-label="Sector Allocation">
            <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
              Sector Allocation
            </h2>
            <SectorAllocationBlock id={id} />
          </section>
        </div>

        {/* Suitability */}
        <section aria-label="Suitability">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Suitability
          </h2>
          <SuitabilityBlock id={id} />
        </section>

        {/* Category info if available */}
        {category && (
          <p className="text-xs text-gray-400">
            Category: {category}
          </p>
        )}

        {/* data-v2-deferred slots */}
        <section
          aria-label="Recommendations"
          data-v2-deferred="true"
        >
          <EmptyState
            title="Coming soon"
            body="AI-powered recommendations will be available in a future release."
          />
        </section>
      </div>
    </main>
  );
}
