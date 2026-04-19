// S1-3 Breadth Terminal page component import tests
// Mocks SWR and global.fetch so no real HTTP calls are made.

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

global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: false,
    statusText: "mocked",
    json: () => Promise.resolve({}),
  })
) as jest.Mock;

import BreadthPage from "../../../src/app/breadth/page";
import UniverseSelector from "../../../src/components/breadth/UniverseSelector";
import IndicatorSelector from "../../../src/components/breadth/IndicatorSelector";
import HeroKPIRow from "../../../src/components/breadth/HeroKPIRow";
import OscillatorPanel from "../../../src/components/breadth/OscillatorPanel";
import SignalHistoryBlock from "../../../src/components/breadth/SignalHistoryBlock";
import ZoneLabelsBlock from "../../../src/components/breadth/ZoneLabelsBlock";
import DivergencesBlock from "../../../src/components/breadth/DivergencesBlock";
import ConvictionHaloBlock from "../../../src/components/breadth/ConvictionHaloBlock";

describe("S1-3 Breadth Terminal page components", () => {
  it("BreadthPage is a function component", () => {
    expect(typeof BreadthPage).toBe("function");
  });

  it("UniverseSelector is a function component", () => {
    expect(typeof UniverseSelector).toBe("function");
  });

  it("IndicatorSelector is a function component", () => {
    expect(typeof IndicatorSelector).toBe("function");
  });

  it("HeroKPIRow is a function component", () => {
    expect(typeof HeroKPIRow).toBe("function");
  });

  it("OscillatorPanel is a function component", () => {
    expect(typeof OscillatorPanel).toBe("function");
  });

  it("SignalHistoryBlock is a function component", () => {
    expect(typeof SignalHistoryBlock).toBe("function");
  });

  it("ZoneLabelsBlock is a function component", () => {
    expect(typeof ZoneLabelsBlock).toBe("function");
  });

  it("DivergencesBlock is a function component", () => {
    expect(typeof DivergencesBlock).toBe("function");
  });

  it("ConvictionHaloBlock is a function component", () => {
    expect(typeof ConvictionHaloBlock).toBe("function");
  });
});
