import { test, expect } from "@playwright/test";

test.describe("Auth shell", () => {
  test("redirects an unauthenticated GET of a protected page to /platform/login", async ({
    page,
  }) => {
    await page.goto("/platform");
    await expect(page).toHaveURL(/\/platform\/login\?next=%2Fplatform/);
  });

  test("login form renders with the right title", async ({ page }) => {
    await page.goto("/platform/login");
    await expect(
      page.getByRole("heading", { name: /platform sign in/i }),
    ).toBeVisible();
  });

  test("client-side validation rejects empty submission", async ({ page }) => {
    await page.goto("/platform/login");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText(/valid email/i)).toBeVisible();
  });

  // Note: a full login → me → logout round trip requires a seeded
  // platform user. That belongs in CI sub-plan 39 against a Docker compose
  // stack with the real backend. Document here as a follow-up.
});
