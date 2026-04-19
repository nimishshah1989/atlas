// S1-6 MF Rank page component tests
import "@testing-library/jest-dom";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";

// Mock SWR globally
jest.mock("swr", () => ({
  __esModule: true,
  default: jest.fn(),
}));

jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn() }) }));
jest.mock("next/link", () => {
  const r = jest.requireActual("react") as typeof import("react");
  return {
    __esModule: true,
    default: ({ href, children }: { href: string; children: r.ReactNode }) =>
      r.createElement("a", { href }, children),
  };
});

// Mock useAtlasData
jest.mock("@/hooks/useAtlasData", () => ({
  useAtlasData: jest.fn(),
}));

// Mock recharts
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
    ResponsiveContainer: ({ children }: { children: r.ReactNode }) =>
      r.createElement("div", { "data-testid": "responsive-container" }, children),
  };
});

global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: false,
    statusText: "mocked",
    json: () => Promise.resolve({}),
  })
) as jest.Mock;

// Import AFTER mocks
import useSWR from "swr";
import { useAtlasData } from "@/hooks/useAtlasData";
import MFRankPage from "../../../src/app/funds/rank/page";
import FilterRail from "../../../src/components/rank/FilterRail";
import RankTable from "../../../src/components/rank/RankTable";
import SparklineCell from "../../../src/components/rank/SparklineCell";

const mockUseSWR = useSWR as jest.Mock;
const mockUseAtlasData = useAtlasData as jest.Mock;

function loadingAtlasData() {
  return { state: "loading" as const, data: null, meta: null, error: null, isLoading: true, mutate: jest.fn() };
}

function makeFund(rank: number): Record<string, unknown> {
  return {
    rank,
    mstar_id: `fund-${rank}`,
    fund_name: `Test Fund ${rank}`,
    category: "Flexi Cap",
    aum_cr: 10000 + rank * 1000,
    returns_score: 70 + rank,
    risk_score: 65 + rank,
    resilience_score: 60 + rank,
    consistency_score: 75 + rank,
    composite_score: 67.5 + rank,
    ret_1y: 12.5 + rank,
    ret_3y: 15.2 + rank,
    ret_5y: 18.1 + rank,
    sparkline: null,
  };
}

describe("S1-6 MF Rank page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Default: SWR returns loading
    mockUseSWR.mockReturnValue({ data: undefined, error: undefined, isValidating: true, mutate: jest.fn() });
    // Default: useAtlasData returns loading
    mockUseAtlasData.mockReturnValue(loadingAtlasData());
  });

  // ── Test 1: Page renders without crashing ─────────────────────────────────
  it("MFRankPage renders without crashing", () => {
    const { container } = render(React.createElement(MFRankPage));
    expect(container.querySelector("main")).toBeInTheDocument();
    // "MF Rank" appears in both breadcrumb and h1 — use getAllByText
    const headings = screen.getAllByText("MF Rank");
    expect(headings.length).toBeGreaterThanOrEqual(1);
  });

  // ── Test 2: FilterRail renders correct filter groups ──────────────────────
  it("FilterRail renders Category, AUM Range, and Time Period filter groups", () => {
    const filters = { category: null, sub_category: null, amc: null, period: null };
    render(React.createElement(FilterRail, { filters, onFiltersChange: jest.fn() }));

    expect(screen.getByText("Category")).toBeInTheDocument();
    expect(screen.getByText("AUM Range")).toBeInTheDocument();
    expect(screen.getByText("Time Period")).toBeInTheDocument();
  });

  // ── Test 3: FilterRail has fieldset elements for accessibility ─────────────
  it("FilterRail has fieldset elements for accessibility", () => {
    const filters = { category: null, sub_category: null, amc: null, period: null };
    const { container } = render(
      React.createElement(FilterRail, { filters, onFiltersChange: jest.fn() })
    );
    const fieldsets = container.querySelectorAll("fieldset");
    expect(fieldsets.length).toBeGreaterThanOrEqual(2);
  });

  // ── Test 4: Clicking a filter chip calls onFiltersChange ──────────────────
  it("Clicking a category filter calls onFiltersChange with updated value", () => {
    const onFiltersChange = jest.fn();
    const filters = { category: null, sub_category: null, amc: null, period: null };
    render(
      React.createElement(FilterRail, { filters, onFiltersChange })
    );

    // Click the "Flexi Cap" filter chip
    const flexiCapCheckbox = screen.getByRole("checkbox", { name: "Flexi Cap" });
    fireEvent.click(flexiCapCheckbox);

    expect(onFiltersChange).toHaveBeenCalledWith(
      expect.objectContaining({ category: "Flexi Cap" })
    );
  });

  // ── Test 5: RankTable renders ≥10 rows on mock data ──────────────────────
  it("RankTable renders ≥10 rows when backend returns ≥10 funds", () => {
    const funds = Array.from({ length: 12 }, (_, i) => makeFund(i + 1));
    mockUseSWR.mockReturnValue({
      data: { data: { records: funds }, _meta: { data_as_of: "2026-04-19", staleness_seconds: 0, source: "test" } },
      error: undefined,
      isValidating: false,
      mutate: jest.fn(),
    });

    const filters = { category: null, sub_category: null, amc: null, period: null };
    render(React.createElement(RankTable, { filters }));

    // Check that we have ≥10 fund name links in the DOM
    const fundLinks = screen.getAllByText(/Test Fund \d+/);
    expect(fundLinks.length).toBeGreaterThanOrEqual(10);
  });

  // ── Test 6: RankTable links fund names to /funds/${mstar_id} ──────────────
  it("RankTable links fund names to /funds/mstar_id", () => {
    const funds = [makeFund(1), makeFund(2)];
    mockUseSWR.mockReturnValue({
      data: { data: { records: funds }, _meta: { data_as_of: "2026-04-19", staleness_seconds: 0, source: "test" } },
      error: undefined,
      isValidating: false,
      mutate: jest.fn(),
    });

    const filters = { category: null, sub_category: null, amc: null, period: null };
    const { container } = render(React.createElement(RankTable, { filters }));

    const link = container.querySelector('a[href="/funds/fund-1"]');
    expect(link).toBeInTheDocument();
  });

  // ── Test 7: RankTable renders CSV export button ───────────────────────────
  it("RankTable renders CSV export button", () => {
    mockUseSWR.mockReturnValue({
      data: { data: { records: [] }, _meta: { data_as_of: null, staleness_seconds: 0, source: "test" } },
      error: undefined,
      isValidating: false,
      mutate: jest.fn(),
    });

    const filters = { category: null, sub_category: null, amc: null, period: null };
    render(React.createElement(RankTable, { filters }));

    const csvBtn = screen.getByTestId("csv-export-btn");
    expect(csvBtn).toBeInTheDocument();
    expect(csvBtn.textContent).toMatch(/Export CSV/i);
  });

  // ── Test 8: SparklineCell renders LineChart on mock sparkline data ─────────
  it("SparklineCell renders LineChart on mock sparkline data", () => {
    const data = [
      { date: "2026-01-01", nav: 100 },
      { date: "2026-02-01", nav: 105 },
      { date: "2026-03-01", nav: 110 },
    ];
    render(React.createElement(SparklineCell, { data }));
    expect(screen.getByTestId("sparkline-cell")).toBeInTheDocument();
    expect(screen.getByTestId("line-chart")).toBeInTheDocument();
  });

  // ── Test 9: SparklineCell renders "—" when data absent ───────────────────
  it("SparklineCell renders em-dash placeholder when data is null", () => {
    render(React.createElement(SparklineCell, { data: null }));
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  // ── Test 10: Changing filter changes SWR key ──────────────────────────────
  it("Changing category filter changes the SWR key passed to useSWR", () => {
    mockUseSWR.mockReturnValue({ data: undefined, error: undefined, isValidating: true, mutate: jest.fn() });

    const filters1 = { category: null, sub_category: null, amc: null, period: null };
    const { rerender } = render(React.createElement(RankTable, { filters: filters1 }));

    // Capture first SWR call key
    const firstCall = mockUseSWR.mock.calls[mockUseSWR.mock.calls.length - 1];
    const firstKey = JSON.stringify(firstCall[0]);

    const filters2 = { category: "Large Cap", sub_category: null, amc: null, period: null };
    rerender(React.createElement(RankTable, { filters: filters2 }));

    const secondCall = mockUseSWR.mock.calls[mockUseSWR.mock.calls.length - 1];
    const secondKey = JSON.stringify(secondCall[0]);

    expect(firstKey).not.toEqual(secondKey);
  });
});
