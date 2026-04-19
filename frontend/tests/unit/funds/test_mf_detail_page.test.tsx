// S1-5 MF Detail page component tests
import "@testing-library/jest-dom";
import React from "react";
import { render, screen } from "@testing-library/react";

// Mock SWR globally — individual tests control state via useAtlasData mock
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: undefined,
    error: undefined,
    isValidating: true,
    mutate: jest.fn(),
  }),
}));

jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn() }) }));

// Mock React.use for Next.js App Router dynamic params
jest.mock("react", () => ({
  ...jest.requireActual("react"),
  use: (p: unknown) => {
    if (p && typeof p === "object" && "id" in (p as Record<string, unknown>)) return p;
    return { id: "ppfas-flexi-cap-direct-growth" };
  },
}));

// Mock useAtlasData — tests control return values per-test
jest.mock("@/hooks/useAtlasData", () => ({
  useAtlasData: jest.fn(),
}));

// Mock recharts to avoid SVG rendering issues in jsdom
jest.mock("recharts", () => {
  const r = jest.requireActual("react") as typeof import("react");
  return {
    LineChart: ({ children }: { children: r.ReactNode }) =>
      r.createElement("div", { "data-testid": "line-chart" }, children),
    Line: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    Legend: () => null,
    ReferenceLine: () => null,
    ResponsiveContainer: ({ children }: { children: r.ReactNode }) =>
      r.createElement("div", { "data-testid": "responsive-container" }, children),
    PieChart: ({ children }: { children: r.ReactNode }) =>
      r.createElement("div", { "data-testid": "pie-chart" }, children),
    Pie: () => null,
    Cell: () => null,
  };
});

global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: false,
    statusText: "mocked",
    json: () => Promise.resolve({}),
  })
) as jest.Mock;

// Import components AFTER all mocks are declared
import { useAtlasData } from "@/hooks/useAtlasData";
import FundDetailPage from "../../../src/app/funds/[id]/page";
import FundHeroBlock from "../../../src/components/funds/FundHeroBlock";
import ReturnsBlock from "../../../src/components/funds/ReturnsBlock";
import NavChartBlock from "../../../src/components/funds/NavChartBlock";
import HoldingsBlock from "../../../src/components/funds/HoldingsBlock";
import AlphaRiskBlock from "../../../src/components/funds/AlphaRiskBlock";
import SectorAllocationBlock from "../../../src/components/funds/SectorAllocationBlock";

const mockUseAtlasData = useAtlasData as jest.Mock;

function loadingState() {
  return {
    state: "loading" as const,
    data: null,
    meta: null,
    error: null,
    isLoading: true,
    mutate: jest.fn(),
  };
}

function readyState(data: Record<string, unknown>) {
  return {
    state: "ready" as const,
    data,
    meta: { data_as_of: "2026-04-19", staleness_seconds: 0 },
    error: null,
    isLoading: false,
    mutate: jest.fn(),
  };
}

describe("S1-5 MF Detail page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ── Test 1: Page renders without crashing ─────────────────────────────────
  // All child components use useAtlasData which is mocked to loading state
  // The page should render the layout skeleton without crashing
  it("FundDetailPage renders without crashing for ppfas-flexi-cap-direct-growth", () => {
    mockUseAtlasData.mockReturnValue(loadingState());

    const { container } = render(
      React.createElement(FundDetailPage, {
        params: Promise.resolve({ id: "ppfas-flexi-cap-direct-growth" }),
      })
    );

    // Page main layout must exist
    expect(container.querySelector("main")).toBeInTheDocument();
    // Breadcrumb
    expect(screen.getByText("Mutual Funds")).toBeInTheDocument();
    // Page id shown in breadcrumb
    expect(screen.getByText("ppfas-flexi-cap-direct-growth")).toBeInTheDocument();
  });

  // ── Test 2: FundHeroBlock renders AUM in lakh/crore format ────────────────
  it("FundHeroBlock renders AUM in lakh/crore format", () => {
    mockUseAtlasData.mockReturnValue(
      readyState({
        name: "PPFAS Flexi Cap",
        category: "Flexi Cap",
        aum: 75000000000, // 7,500 Cr
        nav: 84.25,
        rs_composite: 72.5,
        conviction: 65,
        conviction_band: "high",
      })
    );

    render(
      React.createElement(FundHeroBlock, {
        id: "ppfas-flexi-cap-direct-growth",
        onCategoryLoaded: jest.fn(),
        onNameLoaded: jest.fn(),
      })
    );

    // AUM should be formatted with Cr suffix and ₹ symbol
    const aumEl = screen.getByText(/Cr/);
    expect(aumEl).toBeInTheDocument();
    expect(aumEl.textContent).toMatch(/₹/);
  });

  // ── Test 3: FundHeroBlock calls onCategoryLoaded on success ───────────────
  it("FundHeroBlock calls onCategoryLoaded on success", () => {
    const onCategoryLoaded = jest.fn();

    mockUseAtlasData.mockReturnValue(
      readyState({
        name: "PPFAS Flexi Cap",
        category: "Flexi Cap",
        aum: 75000000000,
        nav: 84.25,
      })
    );

    render(
      React.createElement(FundHeroBlock, {
        id: "ppfas-flexi-cap-direct-growth",
        onCategoryLoaded,
        onNameLoaded: jest.fn(),
      })
    );

    expect(onCategoryLoaded).toHaveBeenCalledWith("Flexi Cap");
  });

  // ── Test 4: ReturnsBlock renders rolling returns table with correct columns
  it("ReturnsBlock renders rolling returns table with correct columns", () => {
    mockUseAtlasData.mockReturnValue(
      readyState({
        rolling_returns: [
          { period: "1Y", fund: 18.5, benchmark: 14.2, alpha: 4.3, cat_rank: "2/45" },
          { period: "3Y", fund: 22.1, benchmark: 16.8, alpha: 5.3, cat_rank: "1/42" },
        ],
      })
    );

    render(React.createElement(ReturnsBlock, { id: "ppfas-flexi-cap-direct-growth" }));

    expect(screen.getByText("Period")).toBeInTheDocument();
    expect(screen.getByText("Fund")).toBeInTheDocument();
    expect(screen.getByText("Benchmark")).toBeInTheDocument();
    expect(screen.getByText(/Alpha/)).toBeInTheDocument();
    expect(screen.getByText(/Cat\. Rank/)).toBeInTheDocument();
  });

  // ── Test 5: NavChartBlock renders LineChart container ─────────────────────
  it("NavChartBlock renders LineChart container", () => {
    mockUseAtlasData.mockReturnValue(
      readyState({
        series: [
          { date: "2021-04-01", nav_indexed: 100, benchmark_tri: 100 },
          { date: "2022-04-01", nav_indexed: 120, benchmark_tri: 110 },
        ],
      })
    );

    render(React.createElement(NavChartBlock, { id: "ppfas-flexi-cap-direct-growth" }));

    expect(screen.getByTestId("line-chart")).toBeInTheDocument();
  });

  // ── Test 6: HoldingsBlock renders rows from mock data ─────────────────────
  it("HoldingsBlock renders rows from mock data", () => {
    mockUseAtlasData.mockReturnValue(
      readyState({
        holdings: [
          {
            rank: 1,
            symbol: "HDFCBANK",
            name: "HDFC Bank Ltd",
            weight_pct: 8.5,
            market_cap_category: "Large Cap",
          },
          {
            rank: 2,
            symbol: "INFY",
            name: "Infosys Ltd",
            weight_pct: 6.2,
            market_cap_category: "Large Cap",
          },
        ],
      })
    );

    render(React.createElement(HoldingsBlock, { id: "ppfas-flexi-cap-direct-growth" }));

    expect(screen.getByText("HDFCBANK")).toBeInTheDocument();
    expect(screen.getByText("HDFC Bank Ltd")).toBeInTheDocument();
    expect(screen.getByText("INFY")).toBeInTheDocument();
  });

  // ── Test 7: AlphaRiskBlock renders metrics grid labels ────────────────────
  it("AlphaRiskBlock renders metrics grid labels", () => {
    mockUseAtlasData.mockReturnValue(
      readyState({
        alpha: 3.5,
        beta: 0.85,
        sharpe_3y: 1.2,
        sortino_3y: 1.8,
        max_drawdown: -18.5,
        upside_capture: 95.2,
        downside_capture: 72.3,
      })
    );

    render(React.createElement(AlphaRiskBlock, { id: "ppfas-flexi-cap-direct-growth" }));

    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("Sharpe (3Y)")).toBeInTheDocument();
    expect(screen.getByText("Sortino (3Y)")).toBeInTheDocument();
    expect(screen.getByText("Max Drawdown")).toBeInTheDocument();
  });

  // ── Test 8: "Atlas Verdict" text does NOT appear anywhere ─────────────────
  it("Atlas Verdict text does NOT appear in rendered output", () => {
    mockUseAtlasData.mockReturnValue(
      readyState({
        name: "PPFAS Flexi Cap",
        category: "Flexi Cap",
        aum: 75000000000,
        nav: 84.25,
        rs_composite: 72.5,
        conviction: 65,
        conviction_band: "high",
      })
    );

    const { container } = render(
      React.createElement(FundHeroBlock, {
        id: "ppfas-flexi-cap-direct-growth",
        onCategoryLoaded: jest.fn(),
      })
    );

    expect(container.textContent).not.toMatch(/Atlas Verdict/i);
    expect(container.textContent).not.toMatch(/STRONG BUY/i);
    expect(container.textContent).not.toMatch(/HOLD \/ ADD ON DIPS/i);
  });

  // ── Test 9: SectorAllocationBlock renders PieChart container ──────────────
  it("SectorAllocationBlock renders PieChart container", () => {
    mockUseAtlasData.mockReturnValue(
      readyState({
        sectors: [
          { sector: "Financial Services", weight_pct: 32.5 },
          { sector: "Technology", weight_pct: 18.2 },
          { sector: "Consumer", weight_pct: 12.1 },
        ],
      })
    );

    render(
      React.createElement(SectorAllocationBlock, {
        id: "ppfas-flexi-cap-direct-growth",
      })
    );

    expect(screen.getByTestId("pie-chart")).toBeInTheDocument();
  });
});
