import "@testing-library/jest-dom";
import React from "react";
import { render, screen } from "@testing-library/react";
import DataBlock from "../../../src/components/ui/DataBlock";
import ErrorBanner from "../../../src/components/ui/ErrorBanner";
import StaleWarning from "../../../src/components/ui/StaleWarning";
import { formatDate } from "../../../src/lib/format";

describe("DataBlock", () => {
  it("renders skeleton on state=loading", () => {
    const { container } = render(<DataBlock state="loading" />);
    expect(container.querySelector(".skeleton-block")).toBeInTheDocument();
  });

  it("renders children on state=ready", () => {
    render(
      <DataBlock state="ready">
        <span data-testid="child">hello</span>
      </DataBlock>
    );
    expect(screen.getByTestId("child")).toBeInTheDocument();
  });

  it("renders EmptyState on state=empty", () => {
    render(<DataBlock state="empty" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("No data available")).toBeInTheDocument();
  });

  it("renders StaleWarning + children on state=stale", () => {
    render(
      <DataBlock state="stale" dataAsOf="2026-04-19T00:00:00Z">
        <span data-testid="stale-child">content</span>
      </DataBlock>
    );
    expect(screen.getByTestId("stale-child")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("renders ErrorBanner on state=error", () => {
    render(
      <DataBlock state="error" errorCode="HTTP_500" errorMessage="Server error" />
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("HTTP_500")).toBeInTheDocument();
  });
});

describe("ErrorBanner", () => {
  it("has role=alert", () => {
    render(<ErrorBanner code="NET_ERR" message="Network failed" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});

describe("StaleWarning", () => {
  it("has data-staleness-banner attribute", () => {
    const { container } = render(
      <StaleWarning dataAsOf="2026-04-19T00:00:00Z" />
    );
    const el = container.querySelector("[data-staleness-banner]");
    expect(el).toBeInTheDocument();
  });
});

describe("formatDate", () => {
  it("formats IST date correctly", () => {
    // 2026-04-04T00:00:00Z is 04-Apr-2026 in IST (UTC+5:30 → still Apr 4)
    const result = formatDate("2026-04-04T00:00:00Z");
    expect(result).toBe("04-Apr-2026");
  });

  it("returns dash for null input", () => {
    expect(formatDate(null)).toBe("—");
  });

  it("returns dash for invalid date", () => {
    expect(formatDate("not-a-date")).toBe("—");
  });
});
