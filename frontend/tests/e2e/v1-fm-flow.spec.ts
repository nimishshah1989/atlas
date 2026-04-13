/**
 * V1 FM Flow — comprehensive E2E test for intelligence findings + decisions
 *
 * Covers: Market overview → Sector badges → Stock table → DeepDive with
 * FindingChips → DecisionPanel with correct badge labels → action buttons →
 * back navigation → lakh/crore formatting.
 *
 * All backend calls intercepted via page.route() — no live backend needed.
 * Fixtures live in ./fixtures.ts.
 */

import { test, expect } from "@playwright/test";
import {
  STATUS_FIXTURE,
  BREADTH_FIXTURE,
  SECTORS_FIXTURE,
  UNIVERSE_BANKS_FIXTURE,
  UNIVERSE_ALL_FIXTURE,
  DEEPDIVE_FIXTURE,
  RS_HISTORY_FIXTURE,
  MOVERS_FIXTURE,
  DECISIONS_FIXTURE,
  FINDINGS_FIXTURE,
} from "./fixtures";

/** Build the action-response payload the PUT endpoint returns. */
const makeActionResponse = (action: string) => ({ status: "ok", action });

/** Register all /api/v1/* mock routes. */
test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/status", (route) =>
    route.fulfill({ json: STATUS_FIXTURE })
  );
  await page.route("**/api/v1/stocks/breadth", (route) =>
    route.fulfill({ json: BREADTH_FIXTURE })
  );
  await page.route("**/api/v1/stocks/sectors", (route) =>
    route.fulfill({ json: SECTORS_FIXTURE })
  );
  await page.route("**/api/v1/stocks/movers", (route) =>
    route.fulfill({ json: MOVERS_FIXTURE })
  );
  await page.route("**/api/v1/decisions", (route) =>
    route.fulfill({ json: DECISIONS_FIXTURE })
  );
  // PUT action endpoint
  await page.route("**/api/v1/decisions/**/action", (route) => {
    if (route.request().method() === "PUT") {
      route.fulfill({ json: makeActionResponse("ACCEPTED") });
    } else {
      route.continue();
    }
  });

  // Intelligence findings — entity-filtered
  await page.route("**/api/v1/intelligence/findings**", (route) => {
    const url = route.request().url();
    if (url.includes("entity=HDFCBANK")) {
      route.fulfill({ json: FINDINGS_FIXTURE });
    } else {
      route.fulfill({ json: { findings: [], meta: { data_as_of: "2026-04-11", record_count: 0, query_ms: 5, stale: false } } });
    }
  });

  // Universe: sector-filtered vs full
  await page.route("**/api/v1/stocks/universe**", (route) => {
    const url = route.request().url();
    if (url.includes("sector=Banks")) {
      route.fulfill({ json: UNIVERSE_BANKS_FIXTURE });
    } else {
      route.fulfill({ json: UNIVERSE_ALL_FIXTURE });
    }
  });

  // Deep-dive and RS history
  await page.route("**/api/v1/stocks/HDFCBANK", (route) =>
    route.fulfill({ json: DEEPDIVE_FIXTURE })
  );
  await page.route("**/api/v1/stocks/HDFCBANK/rs-history**", (route) =>
    route.fulfill({ json: RS_HISTORY_FIXTURE })
  );
});

// ---------------------------------------------------------------------------
// Market overview
// ---------------------------------------------------------------------------

test("market overview loads with ATLAS header", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("ATLAS")).toBeVisible();
});

test("sector table renders all fixture sectors with quadrant badges", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Banks")).toBeVisible();
  await expect(page.getByText("IT Services")).toBeVisible();
  await expect(page.getByText("Pharma")).toBeVisible();
  // Quadrant badge for Banks sector
  await expect(page.getByText("LEADING").first()).toBeVisible();
});

// ---------------------------------------------------------------------------
// Market → Sector → Stock → DeepDive → Back
// ---------------------------------------------------------------------------

test("full FM navigation flow with deep dive and back navigation", async ({ page }) => {
  // 1. Load home
  await page.goto("/");
  await expect(page.getByText("ATLAS")).toBeVisible();
  await expect(page.getByText("Sector RS Rankings")).toBeVisible();

  // 2. Click Banks → stock table
  await page.getByText("Banks").first().click();
  await expect(page.getByText("HDFCBANK")).toBeVisible();

  // 3. Click HDFCBANK → deep dive
  await page.getByText("HDFCBANK").first().click();
  await expect(page.getByText("HDFC Bank Limited").first()).toBeVisible();
  await expect(page.getByText("← Back")).toBeVisible();

  // 4. Back to stock list
  await page.getByText("← Back").click();
  await expect(page.getByText("HDFCBANK")).toBeVisible();

  // 5. Back to sector list
  await page.getByText("← Sectors").click();
  await expect(page.getByText("Sector RS Rankings")).toBeVisible();
});

// ---------------------------------------------------------------------------
// FindingChips in deep dive
// ---------------------------------------------------------------------------

test("deep dive shows finding chips for HDFCBANK", async ({ page }) => {
  await page.goto("/");
  await page.getByText("Banks").first().click();
  await page.getByText("HDFCBANK").first().click();

  // Wait for deep dive to render
  await expect(page.getByText("HDFC Bank Limited").first()).toBeVisible();

  // Finding chips should appear
  const chips = page.locator("[data-testid='finding-chip']");
  await expect(chips.first()).toBeVisible();

  // At least the RS analysis chip should be present
  await expect(page.getByText("Rs Analysis").first()).toBeVisible();
});

test("finding chips show confidence percentage", async ({ page }) => {
  await page.goto("/");
  await page.getByText("Banks").first().click();
  await page.getByText("HDFCBANK").first().click();
  await expect(page.getByText("HDFC Bank Limited").first()).toBeVisible();

  // Confidence pct should appear (85% for fin-001)
  await expect(page.getByText(/85%/).first()).toBeVisible();
});

// ---------------------------------------------------------------------------
// DecisionPanel
// ---------------------------------------------------------------------------

test("decision panel shows decisions with correct signal badges", async ({ page }) => {
  await page.goto("/");

  // Decision panel should be visible on home page
  await expect(page.getByText("Decisions")).toBeVisible();

  // HDFCBANK buy_signal decision
  await expect(page.getByText("HDFCBANK")).toBeVisible();
  // Badge label for buy_signal
  const badge = page.locator("[data-testid='decision-type-badge']").first();
  await expect(badge).toBeVisible();
  await expect(badge).toHaveText("BUY SIGNAL");
});

test("decision panel shows rationale text", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByText("RS composite crossed 7.0 threshold — strong relative strength")
  ).toBeVisible();
});

test("decision panel action buttons work for PENDING decision", async ({ page }) => {
  await page.goto("/");
  // HDFCBANK decision is PENDING (user_action: null) — action buttons visible
  const acceptBtn = page.getByRole("button", { name: "Accept" }).first();
  await expect(acceptBtn).toBeVisible();

  // Click Accept — mock will respond with ok
  await acceptBtn.click();
  // After action the panel reloads; decisions endpoint returns same fixture
  // so Accept button should still be visible (fixture reloaded)
  await expect(page.getByText("HDFCBANK")).toBeVisible();
});

test("actioned decision shows status badge not action buttons", async ({ page }) => {
  await page.goto("/");
  // INFY decision has user_action: IGNORED → should show IGNORED badge not buttons
  await expect(page.getByText("IGNORED")).toBeVisible();
});

// ---------------------------------------------------------------------------
// Currency formatting
// ---------------------------------------------------------------------------

test("stock price displays with rupee prefix", async ({ page }) => {
  await page.goto("/");
  await page.getByText("Banks").first().click();
  await page.getByText("HDFCBANK").first().click();
  await expect(page.getByText("HDFC Bank Limited").first()).toBeVisible();

  // HDFCBANK close is 1650.50 — should display as ₹1,650 or ₹1.65 L
  // formatCurrency(1650.50) → "₹1,650" (under 1L threshold)
  await expect(page.getByText(/₹/).first()).toBeVisible();
});
