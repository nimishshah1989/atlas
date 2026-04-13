/**
 * E2E smoke test: Market → Sector → Stock → DeepDive flow
 *
 * All backend calls are intercepted via page.route() so no live
 * ATLAS backend is needed. Fixtures are in ./fixtures.ts.
 */

import { test, expect } from "@playwright/test";
import {
  STATUS_FIXTURE,
  BREADTH_FIXTURE,
  SECTORS_FIXTURE,
  UNIVERSE_BANKS_FIXTURE,
  UNIVERSE_ALL_FIXTURE,
  UNIVERSE_IT_FIXTURE,
  DEEPDIVE_FIXTURE,
  RS_HISTORY_FIXTURE,
  MOVERS_FIXTURE,
  DECISIONS_FIXTURE,
} from "./fixtures";

/** Register all /api/v1/* mock routes before each test. */
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

  // Universe: sector-filtered vs full
  await page.route("**/api/v1/stocks/universe**", (route) => {
    const url = route.request().url();
    if (url.includes("sector=Banks")) {
      route.fulfill({ json: UNIVERSE_BANKS_FIXTURE });
    } else {
      route.fulfill({ json: UNIVERSE_ALL_FIXTURE });
    }
  });

  // Deep-dive and RS history for HDFCBANK
  await page.route("**/api/v1/stocks/HDFCBANK", (route) =>
    route.fulfill({ json: DEEPDIVE_FIXTURE })
  );
  await page.route("**/api/v1/stocks/HDFCBANK/rs-history**", (route) =>
    route.fulfill({ json: RS_HISTORY_FIXTURE })
  );
});

test("ATLAS header is visible on load", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("ATLAS")).toBeVisible();
});

test("Sector list renders all three fixture sectors", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Banks")).toBeVisible();
  await expect(page.getByText("IT Services")).toBeVisible();
  await expect(page.getByText("Pharma")).toBeVisible();
});

test("Market → Sector → Stock → DeepDive → Back navigation", async ({
  page,
}) => {
  // 1. Load home — sectors view
  await page.goto("/");
  await expect(page.getByText("ATLAS")).toBeVisible();

  // 2. Sector list renders
  await expect(page.getByText("Sector RS Rankings")).toBeVisible();
  await expect(page.getByText("Banks")).toBeVisible();

  // 3. Click Banks sector row → stock table
  await page.getByText("Banks").first().click();
  await expect(page.getByText("HDFCBANK")).toBeVisible();

  // 4. Click first stock → deep dive panel
  await page.getByText("HDFCBANK").first().click();
  await expect(page.getByText("HDFCBANK").first()).toBeVisible();
  await expect(page.getByText("HDFC Bank Limited").first()).toBeVisible();
  await expect(page.getByText("← Back")).toBeVisible();

  // 5. Back to stock list
  await page.getByText("← Back").click();
  await expect(page.getByText("HDFCBANK")).toBeVisible();

  // 6. Back to sector list
  await page.getByText("← Sectors").click();
  await expect(page.getByText("Sector RS Rankings")).toBeVisible();
});

test("IT Services sector click shows stock table with INFY", async ({
  page,
}) => {
  // Override universe route for this test to return IT Services stocks
  await page.route("**/api/v1/stocks/universe**", (route) =>
    route.fulfill({ json: UNIVERSE_IT_FIXTURE })
  );

  await page.goto("/");
  await page.getByText("IT Services").click();
  await expect(page.getByText("IT Services").first()).toBeVisible();
  await expect(page.getByText("INFY")).toBeVisible();
});
