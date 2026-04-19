// S1-7 TopNav + root redirect tests
import "@testing-library/jest-dom";
import React from "react";
import { render, screen } from "@testing-library/react";

// Mock next/navigation — usePathname and redirect must be controllable
jest.mock("next/navigation", () => ({
  usePathname: jest.fn().mockReturnValue("/"),
  redirect: jest.fn(),
}));

// Mock next/link — pass through all props (including style) so active-link assertions work.
// Uses jest.requireActual("react") inside factory (jest-mock-factory-no-outer-scope-refs pattern).
jest.mock("next/link", () => {
  const r = jest.requireActual("react") as typeof import("react");
  return {
    __esModule: true,
    default: (props: Record<string, unknown>) => {
      const { href, children, ...rest } = props;
      return r.createElement("a", { href, ...rest }, children as r.ReactNode);
    },
  };
});

// Import AFTER mocks
import { usePathname, redirect } from "next/navigation";
import TopNav from "../../../src/components/nav/TopNav";
import Home from "../../../src/app/page";

const mockUsePathname = usePathname as jest.Mock;
const mockRedirect = redirect as jest.Mock;

describe("S1-7 TopNav", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUsePathname.mockReturnValue("/");
  });

  // ── Test 1: All 6 nav link labels are rendered ────────────────────────────
  it("renders all 6 nav link labels", () => {
    render(React.createElement(TopNav));

    expect(screen.getByText("Pulse")).toBeInTheDocument();
    expect(screen.getByText("India")).toBeInTheDocument();
    expect(screen.getByText("Breadth")).toBeInTheDocument();
    expect(screen.getByText("Stocks")).toBeInTheDocument();
    expect(screen.getByText("Funds")).toBeInTheDocument();
    expect(screen.getByText("Fund Detail")).toBeInTheDocument();
  });

  // ── Test 2: /pulse link is active when pathname is "/pulse" ───────────────
  it("marks Pulse link active when pathname is /pulse", () => {
    mockUsePathname.mockReturnValue("/pulse");
    render(React.createElement(TopNav));

    const pulseLink = screen.getByRole("link", { name: "Pulse" });
    // Active style sets color to var(--accent-700)
    const style = pulseLink.getAttribute("style") ?? "";
    expect(style).toContain("var(--accent-700)");
  });

  // ── Test 3: /breadth link is active when pathname is "/breadth" ───────────
  it("marks Breadth link active when pathname is /breadth", () => {
    mockUsePathname.mockReturnValue("/breadth");
    render(React.createElement(TopNav));

    const breadthLink = screen.getByRole("link", { name: "Breadth" });
    const style = breadthLink.getAttribute("style") ?? "";
    expect(style).toContain("var(--accent-700)");
  });

  // ── Test 4: Mobile hamburger button is present ────────────────────────────
  it("has a hamburger button for mobile navigation", () => {
    render(React.createElement(TopNav));

    const hamburger = screen.getByRole("button", { name: /toggle navigation menu/i });
    expect(hamburger).toBeInTheDocument();
  });

  // ── Test 5: TopNav has sticky positioning ─────────────────────────────────
  it("renders a sticky header element", () => {
    const { container } = render(React.createElement(TopNav));

    const header = container.querySelector("header");
    expect(header).toBeInTheDocument();
    const style = header?.getAttribute("style") ?? "";
    expect(style).toContain("sticky");
  });

  // ── Test 6: /funds/rank active only on /funds/rank, not /funds/[id] ───────
  it("Funds link is active on /funds/rank but not on a fund detail page", () => {
    mockUsePathname.mockReturnValue("/funds/rank");
    const { rerender } = render(React.createElement(TopNav));

    const fundsLink = screen.getByRole("link", { name: "Funds" });
    expect(fundsLink.getAttribute("style") ?? "").toContain("var(--accent-700)");

    mockUsePathname.mockReturnValue("/funds/ppfas-flexi-cap-direct-growth");
    rerender(React.createElement(TopNav));

    // Funds link should NOT be active on a fund detail page
    const fundsLinkAfter = screen.getByRole("link", { name: "Funds" });
    const fundsStyle = fundsLinkAfter.getAttribute("style") ?? "";
    // The Funds (/funds/rank) link should NOT show accent color when on detail page
    // Fund Detail link should be active instead
    expect(fundsStyle).not.toContain("font-weight: 600");

    const fundDetailLink = screen.getByRole("link", { name: "Fund Detail" });
    expect(fundDetailLink.getAttribute("style") ?? "").toContain("var(--accent-700)");
  });
});

describe("S1-7 Home redirect", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ── Test 7: Home component calls redirect("/pulse") ───────────────────────
  it("Home page calls redirect to /pulse", () => {
    // redirect() in Next.js throws internally; mock it as a no-op
    mockRedirect.mockImplementation(() => {
      // no-op in test environment
    });

    try {
      render(React.createElement(Home));
    } catch {
      // redirect may throw; that is expected behaviour in Next.js
    }

    expect(mockRedirect).toHaveBeenCalledWith("/pulse");
  });
});
