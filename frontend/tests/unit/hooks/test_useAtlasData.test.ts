import { STALENESS_THRESHOLDS } from "../../../src/hooks/useAtlasData";

// Test the exported constant directly
// Full hook testing with React/SWR requires a provider setup — threshold tests
// verify the state machine constants match atlas-states.js exactly.
describe("STALENESS_THRESHOLDS", () => {
  it("has intraday = 3600", () => {
    expect(STALENESS_THRESHOLDS.intraday).toBe(3600);
  });

  it("has eod_breadth = 21600", () => {
    expect(STALENESS_THRESHOLDS.eod_breadth).toBe(21600);
  });

  it("has daily_regime = 86400", () => {
    expect(STALENESS_THRESHOLDS.daily_regime).toBe(86400);
  });

  it("has fundamentals = 604800", () => {
    expect(STALENESS_THRESHOLDS.fundamentals).toBe(604800);
  });

  it("has events = 604800", () => {
    expect(STALENESS_THRESHOLDS.events).toBe(604800);
  });

  it("has holdings = 604800", () => {
    expect(STALENESS_THRESHOLDS.holdings).toBe(604800);
  });
});
