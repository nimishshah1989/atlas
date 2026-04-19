// S1-1 Pulse page component import tests
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

import PulsePage from "../../../src/app/pulse/page";
import RegimeBanner from "../../../src/components/pulse/RegimeBanner";
import GlanceStrip from "../../../src/components/pulse/GlanceStrip";
import SectorBoard from "../../../src/components/pulse/SectorBoard";
import MoverStrip from "../../../src/components/pulse/MoverStrip";
import FundStrip from "../../../src/components/pulse/FundStrip";
import SignalStrip from "../../../src/components/pulse/SignalStrip";
import DivergencesBlock from "../../../src/components/pulse/DivergencesBlock";
import EventsOverlay from "../../../src/components/pulse/EventsOverlay";

describe("S1-1 Pulse page components", () => {
  it("PulsePage is a function component", () => {
    expect(typeof PulsePage).toBe("function");
  });

  it("RegimeBanner is a function component", () => {
    expect(typeof RegimeBanner).toBe("function");
  });

  it("GlanceStrip is a function component", () => {
    expect(typeof GlanceStrip).toBe("function");
  });

  it("SectorBoard is a function component", () => {
    expect(typeof SectorBoard).toBe("function");
  });

  it("MoverStrip is a function component", () => {
    expect(typeof MoverStrip).toBe("function");
  });

  it("FundStrip is a function component", () => {
    expect(typeof FundStrip).toBe("function");
  });

  it("SignalStrip is a function component", () => {
    expect(typeof SignalStrip).toBe("function");
  });

  it("DivergencesBlock is a function component", () => {
    expect(typeof DivergencesBlock).toBe("function");
  });

  it("EventsOverlay is a function component", () => {
    expect(typeof EventsOverlay).toBe("function");
  });
});
