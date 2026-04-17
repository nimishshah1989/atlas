import { test, expect } from "@playwright/test";

test.describe("V6T-4 Watchlist Refresh TV signals", () => {
  test("Refresh TV signals button exists and Sync to TV is absent", async ({
    page,
  }) => {
    await page.goto("/pro/watchlists");
    // Wait for the page to settle (may show empty state or skeleton)
    await page.waitForTimeout(2000);

    // "Sync to TV" must not appear anywhere
    await expect(page.getByText("Sync to TV")).toHaveCount(0);

    // If any watchlist cards loaded, check for the new button
    const cards = page.locator('[data-testid="watchlist-card"]');
    const cardCount = await cards.count();
    if (cardCount > 0) {
      const firstCard = cards.first();
      await expect(
        firstCard.locator('[data-testid="refresh-tv-btn"]')
      ).toBeVisible();
      await expect(firstCard.getByText("Refresh TV signals")).toBeVisible();
    }
  });
});
