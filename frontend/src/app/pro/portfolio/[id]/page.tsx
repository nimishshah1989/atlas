"use client";

import { useState, useEffect, useMemo } from "react";
import { use } from "react";
import {
  getPortfolioAnalysis,
  getPortfolioAttribution,
  getPortfolioOptimize,
  type PortfolioFullAnalysisResponse,
  type PortfolioAttributionResponse,
  type PortfolioOptimizationResponse,
} from "@/lib/api-portfolio";
import WeightedRsCard from "@/components/portfolio/WeightedRsCard";
import SectorChart from "@/components/portfolio/SectorChart";
import HoldingsTable from "@/components/portfolio/HoldingsTable";
import AttributionPanel from "@/components/portfolio/AttributionPanel";
import OptimizerPanel from "@/components/portfolio/OptimizerPanel";

// ─── Main Page ───────────────────────────────────────────────────────────────

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function PortfolioDetailPage({ params }: PageProps) {
  const { id } = use(params);

  const [analysis, setAnalysis] =
    useState<PortfolioFullAnalysisResponse | null>(null);
  const [attribution, setAttribution] =
    useState<PortfolioAttributionResponse | null>(null);
  const [optimization, setOptimization] =
    useState<PortfolioOptimizationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Sector filter for holdings table
  const [activeSector, setActiveSector] = useState<string | null>(null);

  // Active panel tab
  const [activePanel, setActivePanel] = useState<
    "holdings" | "attribution" | "optimizer"
  >("holdings");

  useEffect(() => {
    if (!id) return;
    loadData(id);
  }, [id]);

  async function loadData(portfolioId: string) {
    setLoading(true);
    setErrors({});

    const results = await Promise.allSettled([
      getPortfolioAnalysis(portfolioId),
      getPortfolioAttribution(portfolioId),
      getPortfolioOptimize(portfolioId),
    ]);

    const [analysisResult, attributionResult, optimizationResult] = results;

    if (analysisResult.status === "fulfilled") {
      setAnalysis(analysisResult.value);
    } else {
      setErrors((e) => ({
        ...e,
        analysis:
          analysisResult.reason instanceof Error
            ? analysisResult.reason.message
            : "Analysis failed",
      }));
    }

    if (attributionResult.status === "fulfilled") {
      setAttribution(attributionResult.value);
    } else {
      setErrors((e) => ({
        ...e,
        attribution:
          attributionResult.reason instanceof Error
            ? attributionResult.reason.message
            : "Attribution failed",
      }));
    }

    if (optimizationResult.status === "fulfilled") {
      setOptimization(optimizationResult.value);
    } else {
      setErrors((e) => ({
        ...e,
        optimization:
          optimizationResult.reason instanceof Error
            ? optimizationResult.reason.message
            : "Optimization failed",
      }));
    }

    setLoading(false);
  }

  // Filter holdings by sector
  const filteredHoldings = useMemo(() => {
    if (!analysis) return [];
    if (!activeSector) return analysis.holdings;
    return analysis.holdings.filter((h) =>
      h.top_sectors.some(
        (s) => (s as { sector_name?: string }).sector_name === activeSector
      )
    );
  }, [analysis, activeSector]);

  const portfolioName =
    analysis?.portfolio_name ??
    optimization?.portfolio_name ??
    `Portfolio ${id.slice(0, 8)}`;

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b bg-white sticky top-0 z-10">
        <div className="max-w-[1600px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a href="/" className="text-xl font-bold tracking-tight">
              <span className="text-[#1D9E75]">ATLAS</span>
              <span className="text-gray-400 text-sm font-normal ml-2">
                Pro
              </span>
            </a>
            <nav className="flex items-center gap-1 text-sm text-gray-500 ml-2">
              <a href="/" className="hover:text-gray-800">
                Home
              </a>
              <span>/</span>
              <a href="/pro/portfolio" className="hover:text-gray-800">
                Portfolios
              </a>
              <span>/</span>
              <span className="text-gray-800 font-medium truncate max-w-xs">
                {portfolioName}
              </span>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            {analysis && (
              <span className="text-xs text-gray-400">
                As of {analysis.data_as_of}
              </span>
            )}
            <div className="text-xs text-gray-400">
              Jhaveri Intelligence Platform
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-4 py-6">
        {loading && (
          <div className="space-y-4">
            <div className="h-32 bg-gray-100 rounded-lg animate-pulse" />
            <div className="h-64 bg-gray-100 rounded-lg animate-pulse" />
          </div>
        )}

        {!loading && (
          <>
            {/* Top row: RS card + Sector chart */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
              <div className="lg:col-span-1">
                {analysis ? (
                  <WeightedRsCard analysis={analysis} />
                ) : (
                  <div className="bg-white border border-[#e4e4e8] rounded-lg p-5">
                    <div className="text-sm text-red-600">
                      {errors.analysis ?? "Analysis unavailable"}
                    </div>
                  </div>
                )}
              </div>

              <div className="lg:col-span-2 bg-white border border-[#e4e4e8] rounded-lg p-5">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                  Sector Concentration
                  {activeSector && (
                    <span className="ml-2 text-[#1D9E75] normal-case font-normal">
                      — filtered: {activeSector}
                    </span>
                  )}
                </h3>
                {analysis ? (
                  <SectorChart
                    sectorWeights={analysis.portfolio.sector_weights}
                    onSectorClick={setActiveSector}
                    activeSector={activeSector}
                  />
                ) : (
                  <div className="h-48 flex items-center justify-center text-sm text-gray-400">
                    Sector data unavailable
                  </div>
                )}
              </div>
            </div>

            {/* Panel tabs */}
            <div className="bg-white border border-[#e4e4e8] rounded-lg overflow-hidden">
              <div className="border-b border-[#e4e4e8] flex">
                {(
                  [
                    { key: "holdings", label: "Holdings" },
                    { key: "attribution", label: "Attribution" },
                    { key: "optimizer", label: "Optimizer" },
                  ] as const
                ).map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => setActivePanel(key)}
                    className={`px-5 py-3 text-sm font-medium transition-colors border-b-2 ${
                      activePanel === key
                        ? "border-[#1D9E75] text-[#1D9E75]"
                        : "border-transparent text-gray-500 hover:text-gray-800"
                    }`}
                  >
                    {label}
                    {key === "holdings" && analysis && (
                      <span className="ml-1.5 text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                        {filteredHoldings.length}
                      </span>
                    )}
                    {key === "attribution" && errors.attribution && (
                      <span className="ml-1.5 text-xs text-red-500">!</span>
                    )}
                    {key === "optimizer" && errors.optimization && (
                      <span className="ml-1.5 text-xs text-red-500">!</span>
                    )}
                  </button>
                ))}
              </div>

              <div className="p-4">
                {activePanel === "holdings" && (
                  <>
                    {analysis ? (
                      <HoldingsTable
                        holdings={filteredHoldings}
                        onDrillDown={(h) => {
                          const topSector = h.top_sectors[0] as
                            | { sector_name?: string }
                            | undefined;
                          if (topSector?.sector_name) {
                            setActiveSector(topSector.sector_name);
                          }
                        }}
                      />
                    ) : (
                      <div className="text-sm text-red-600 py-4">
                        {errors.analysis ?? "Holdings unavailable"}
                      </div>
                    )}
                    {analysis && analysis.unavailable.length > 0 && (
                      <div className="mt-3 bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-700">
                        {analysis.unavailable.length} holding(s) could not be
                        enriched with JIP data and are excluded from analysis.
                      </div>
                    )}
                  </>
                )}

                {activePanel === "attribution" && (
                  <>
                    {attribution ? (
                      <AttributionPanel attribution={attribution} />
                    ) : (
                      <div className="text-sm text-red-600 py-4">
                        {errors.attribution ?? "Attribution unavailable"}
                      </div>
                    )}
                  </>
                )}

                {activePanel === "optimizer" && (
                  <>
                    {optimization ? (
                      <OptimizerPanel optimization={optimization} />
                    ) : (
                      <div className="text-sm text-red-600 py-4">
                        {errors.optimization ?? "Optimization unavailable"}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
