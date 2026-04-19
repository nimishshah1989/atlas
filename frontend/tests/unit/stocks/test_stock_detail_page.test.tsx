// S1-4 Stock Detail page component import tests
import "@testing-library/jest-dom";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: undefined,
    error: undefined,
    isValidating: true,
    mutate: jest.fn(),
  }),
}));

// Mock React.use for Next.js App Router params
jest.mock("react", () => ({
  ...jest.requireActual("react"),
  use: (val: unknown) => {
    if (val && typeof val === "object" && "symbol" in (val as Record<string, unknown>)) return val;
    return { symbol: "HDFCBANK" };
  },
}));

global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: false,
    statusText: "mocked",
    json: () => Promise.resolve({}),
  })
) as jest.Mock;

import StockDetailPage from "../../../src/app/stocks/[symbol]/page";
import StockHeroBlock from "../../../src/components/stocks/StockHeroBlock";
import StockChartBlock from "../../../src/components/stocks/StockChartBlock";
import SignalStripBlock from "../../../src/components/stocks/SignalStripBlock";
import DivergencesStockBlock from "../../../src/components/stocks/DivergencesStockBlock";
import SignalHistoryStockBlock from "../../../src/components/stocks/SignalHistoryStockBlock";
import PeersBlock from "../../../src/components/stocks/PeersBlock";
import BenchmarkPanels from "../../../src/components/stocks/BenchmarkPanels";
import InsiderBlock from "../../../src/components/stocks/InsiderBlock";

describe("S1-4 Stock Detail page components", () => {
  it("StockDetailPage is a function component", () => {
    expect(typeof StockDetailPage).toBe("function");
  });

  it("StockHeroBlock is a function component", () => {
    expect(typeof StockHeroBlock).toBe("function");
  });

  it("StockChartBlock is a function component", () => {
    expect(typeof StockChartBlock).toBe("function");
  });

  it("SignalStripBlock is a function component", () => {
    expect(typeof SignalStripBlock).toBe("function");
  });

  it("DivergencesStockBlock is a function component", () => {
    expect(typeof DivergencesStockBlock).toBe("function");
  });

  it("SignalHistoryStockBlock is a function component", () => {
    expect(typeof SignalHistoryStockBlock).toBe("function");
  });

  it("PeersBlock is a function component", () => {
    expect(typeof PeersBlock).toBe("function");
  });

  it("BenchmarkPanels is a function component", () => {
    expect(typeof BenchmarkPanels).toBe("function");
  });

  it("InsiderBlock is a function component", () => {
    expect(typeof InsiderBlock).toBe("function");
  });
});
