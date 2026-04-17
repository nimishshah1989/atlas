import { test, expect } from "@playwright/test";

test.describe("V6T-4 Market tab TV column", () => {
  test("TV column header and chip appear after drilling into a sector", async ({
    page,
  }) => {
    await page.goto("/fm");
    // Wait for sectors to load then click the first sector row
    const sectorRow = page.locator("table tbody tr").first();
    await sectorRow.waitFor({ timeout: 15000 });
    await sectorRow.click();

    // StockTable should now be visible with a TV column header
    await expect(page.locator("th").filter({ hasText: "TV" })).toBeVisible({
      timeout: 15000,
    });

    // At least one tv-chip should exist (may show dash if uncached - that is fine)
    await expect(
      page.locator('[data-testid="tv-chip"]').first()
    ).toBeVisible({ timeout: 15000 });
  });
});
