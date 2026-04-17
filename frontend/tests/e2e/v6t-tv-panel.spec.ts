import { test, expect } from "@playwright/test";

test.describe("V6T-3 TVConvictionPanel", () => {
  test("renders TV panel or unavailable fallback on stock deep-dive", async ({ page }) => {
    await page.goto("/fm");
    await page.getByRole("button", { name: /reliance/i }).first().click().catch(() => {});
    // Fallback: click any stock row if name-based click missed.
    const row = page.locator("[data-testid^='stock-row-']").first();
    if (await row.count()) await row.click();

    const heading = page.getByRole("heading", { name: /external confirmation/i });
    await expect(heading).toBeVisible();

    const rowsLocator = page.locator("[data-testid^='tv-row-']");
    const unavailable = page.getByText(/tv data unavailable/i);
    const hasRows = (await rowsLocator.count()) === 3;
    const hasFallback = await unavailable.isVisible().catch(() => false);
    expect(hasRows || hasFallback).toBe(true);
  });
});
