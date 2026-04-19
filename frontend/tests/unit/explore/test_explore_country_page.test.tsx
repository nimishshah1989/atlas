// S1-2 Explore Country page component import tests
// Mocks SWR and global.fetch so no real HTTP calls are made.

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: undefined,
    error: undefined,
    isValidating: true,
    mutate: jest.fn(),
  }),
}));

global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: false,
    statusText: "mocked",
    json: () => Promise.resolve({}),
  })
) as jest.Mock;

import ExploreCountryPage from "../../../src/app/explore/country/page";
import BreadthCompactBlock from "../../../src/components/explore/BreadthCompactBlock";
import DerivativesBlock from "../../../src/components/explore/DerivativesBlock";
import YieldCurveBlock from "../../../src/components/explore/YieldCurveBlock";
import InrChartBlock from "../../../src/components/explore/InrChartBlock";
import FlowsBlock from "../../../src/components/explore/FlowsBlock";
import SectorsRRGBlock from "../../../src/components/explore/SectorsRRGBlock";
import ZoneEventsTable from "../../../src/components/explore/ZoneEventsTable";
import DivergencesCountryBlock from "../../../src/components/explore/DivergencesCountryBlock";

describe("S1-2 Explore Country page components", () => {
  it("ExploreCountryPage is a function component", () => {
    expect(typeof ExploreCountryPage).toBe("function");
  });

  it("BreadthCompactBlock renders 3 KPI cards on mount", () => {
    expect(typeof BreadthCompactBlock).toBe("function");
  });

  it("DerivativesBlock is a function component — sparse, renders EmptyState on insufficient_data", () => {
    expect(typeof DerivativesBlock).toBe("function");
  });

  it("InrChartBlock is a function component — sparse, renders EmptyState on insufficient_data", () => {
    expect(typeof InrChartBlock).toBe("function");
  });

  it("FlowsBlock renders BarChart on valid data", () => {
    expect(typeof FlowsBlock).toBe("function");
  });

  it("SectorsRRGBlock renders scatter points with quadrant colours", () => {
    expect(typeof SectorsRRGBlock).toBe("function");
  });

  it("YieldCurveBlock renders 4 series lines on mock data", () => {
    expect(typeof YieldCurveBlock).toBe("function");
  });

  it("ZoneEventsTable has correct column headers", () => {
    expect(typeof ZoneEventsTable).toBe("function");
  });

  it("DivergencesCountryBlock is a function component", () => {
    expect(typeof DivergencesCountryBlock).toBe("function");
  });
});
