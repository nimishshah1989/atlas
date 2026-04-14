"use client";

import { useState } from "react";
import MarketOverview from "@/components/MarketOverview";
import SectorTable from "@/components/SectorTable";
import StockTable from "@/components/StockTable";
import DeepDivePanel from "@/components/DeepDivePanel";
import DecisionPanel from "@/components/DecisionPanel";
import MFCategoryTable from "@/components/mf/MFCategoryTable";
import MFUniverseTree from "@/components/mf/MFUniverseTree";
import MFDeepDive from "@/components/mf/MFDeepDive";
import MFFlowsPanel from "@/components/mf/MFFlowsPanel";

type Tab = "equity" | "mf";

type View =
  | { type: "sectors" }
  | { type: "stocks"; sector: string }
  | { type: "deep-dive"; symbol: string; sector: string }
  | { type: "mf-categories" }
  | { type: "mf-funds"; category: string; broadCategory: string }
  | { type: "mf-deep-dive"; mstarId: string; fundName: string; category: string };

export default function Home() {
  const [tab, setTab] = useState<Tab>("equity");
  const [view, setView] = useState<View>({ type: "sectors" });

  const handleTabSwitch = (t: Tab) => {
    setTab(t);
    if (t === "equity") {
      setView({ type: "sectors" });
    } else {
      setView({ type: "mf-categories" });
    }
  };

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b bg-white sticky top-0 z-10">
        <div className="max-w-[1600px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1
              className="text-xl font-bold tracking-tight cursor-pointer"
              onClick={() =>
                tab === "equity"
                  ? setView({ type: "sectors" })
                  : setView({ type: "mf-categories" })
              }
            >
              <span className="text-[#1D9E75]">ATLAS</span>
              <span className="text-gray-400 text-sm font-normal ml-2">
                Pro
              </span>
            </h1>

            {/* Tab switcher */}
            <div className="flex items-center border rounded-md overflow-hidden ml-2">
              <button
                onClick={() => handleTabSwitch("equity")}
                className={`px-3 py-1 text-xs font-medium transition-colors ${
                  tab === "equity"
                    ? "bg-[#1D9E75] text-white"
                    : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
                }`}
              >
                Market
              </button>
              <button
                onClick={() => handleTabSwitch("mf")}
                className={`px-3 py-1 text-xs font-medium transition-colors ${
                  tab === "mf"
                    ? "bg-[#1D9E75] text-white"
                    : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
                }`}
              >
                Mutual Funds
              </button>
            </div>

            {/* Breadcrumb */}
            <nav className="flex items-center gap-1 text-sm text-gray-500 ml-2">
              {tab === "equity" && (
                <>
                  <button
                    onClick={() => setView({ type: "sectors" })}
                    className="hover:text-gray-800"
                  >
                    Sectors
                  </button>
                  {(view.type === "stocks" || view.type === "deep-dive") && (
                    <>
                      <span>/</span>
                      <button
                        onClick={() =>
                          setView({
                            type: "stocks",
                            sector: (view as { sector: string }).sector,
                          })
                        }
                        className="hover:text-gray-800"
                      >
                        {(view as { sector: string }).sector}
                      </button>
                    </>
                  )}
                  {view.type === "deep-dive" && (
                    <>
                      <span>/</span>
                      <span className="text-gray-800 font-medium">
                        {view.symbol}
                      </span>
                    </>
                  )}
                </>
              )}

              {tab === "mf" && (
                <>
                  <button
                    onClick={() => setView({ type: "mf-categories" })}
                    className="hover:text-gray-800"
                  >
                    Categories
                  </button>
                  {(view.type === "mf-funds" ||
                    view.type === "mf-deep-dive") && (
                    <>
                      <span>/</span>
                      <button
                        onClick={() => {
                          if (
                            view.type === "mf-funds" ||
                            view.type === "mf-deep-dive"
                          ) {
                            setView({
                              type: "mf-funds",
                              category: view.category,
                              broadCategory:
                                view.type === "mf-funds"
                                  ? view.broadCategory
                                  : "",
                            });
                          }
                        }}
                        className="hover:text-gray-800"
                      >
                        {view.type === "mf-funds" || view.type === "mf-deep-dive"
                          ? view.category
                          : ""}
                      </button>
                    </>
                  )}
                  {view.type === "mf-deep-dive" && (
                    <>
                      <span>/</span>
                      <span className="text-gray-800 font-medium truncate max-w-xs">
                        {view.fundName}
                      </span>
                    </>
                  )}
                </>
              )}
            </nav>
          </div>
          <div className="text-xs text-gray-400">
            Jhaveri Intelligence Platform
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-[1600px] mx-auto px-4 py-4 space-y-6">
        {/* Market Overview — always visible */}
        <MarketOverview />

        {/* ── Equity views ── */}
        {tab === "equity" && (
          <>
            {view.type === "sectors" && (
              <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                <div className="lg:col-span-3">
                  <SectorTable
                    onSelectSector={(sector) =>
                      setView({ type: "stocks", sector })
                    }
                  />
                </div>
                <div className="lg:col-span-1">
                  <DecisionPanel />
                </div>
              </div>
            )}

            {view.type === "stocks" && (
              <StockTable
                sector={view.sector}
                onSelectStock={(symbol) =>
                  setView({ type: "deep-dive", symbol, sector: view.sector })
                }
                onBack={() => setView({ type: "sectors" })}
              />
            )}

            {view.type === "deep-dive" && (
              <DeepDivePanel
                symbol={view.symbol}
                onBack={() =>
                  setView({ type: "stocks", sector: view.sector })
                }
              />
            )}
          </>
        )}

        {/* ── MF views ── */}
        {tab === "mf" && (
          <>
            {view.type === "mf-categories" && (
              <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                <div className="lg:col-span-3">
                  <MFCategoryTable
                    onSelectCategory={(category, broadCategory) =>
                      setView({ type: "mf-funds", category, broadCategory })
                    }
                  />
                </div>
                <div className="lg:col-span-1">
                  <MFFlowsPanel />
                </div>
              </div>
            )}

            {view.type === "mf-funds" && (
              <MFUniverseTree
                filterCategory={view.category}
                onSelectFund={(mstarId, fundName) =>
                  setView({
                    type: "mf-deep-dive",
                    mstarId,
                    fundName,
                    category: view.category,
                  })
                }
                onBack={() => setView({ type: "mf-categories" })}
              />
            )}

            {view.type === "mf-deep-dive" && (
              <MFDeepDive
                mstarId={view.mstarId}
                onBack={() =>
                  setView({
                    type: "mf-funds",
                    category: view.category,
                    broadCategory: "",
                  })
                }
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}
