import { test, expect } from "@playwright/test";

// Authenticated project. Asserts the seeded rows render in their list screens.
test.describe("Seeded list data", () => {
  test("users list shows the seeded operator", async ({ page }) => {
    await page.goto("/platform/users");
    await expect(
      page.getByText(process.env["E2E_EMAIL"] ?? "e2e@platform.test"),
    ).toBeVisible();
  });

  test("tenants list shows the seeded tenant", async ({ page }) => {
    await page.goto("/platform/tenants");
    await expect(page.getByText("E2E SACCO")).toBeVisible();
  });
});
