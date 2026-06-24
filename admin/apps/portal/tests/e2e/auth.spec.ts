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

  // The tests below require the seeded backend (scripts/e2e_seed.py) running.

  const EMAIL = process.env["E2E_EMAIL"] ?? "e2e@platform.example.com";
  const PASSWORD = process.env["E2E_PASSWORD"] ?? "e2e-Password-123!";

  async function login(page: import("@playwright/test").Page): Promise<void> {
    await page.goto("/platform/login");
    await page.getByLabel(/email/i).fill(EMAIL);
    await page.getByLabel(/password/i).fill(PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\/platform(\/|$)/, { timeout: 15_000 });
  }

  test("logs in with seeded credentials and reaches the dashboard", async ({ page }) => {
    await login(page);
    await expect(page).toHaveURL(/\/platform(\/|$)/);
    await expect(
      page.getByRole("heading", { name: /platform dashboard/i }),
    ).toBeVisible();
  });

  test("logs out back to the login screen", async ({ page }) => {
    await login(page);
    await page.getByRole("button", { name: /user menu/i }).click();
    await page.getByRole("menuitem", { name: /sign out/i }).click();
    await expect(page).toHaveURL(/\/platform\/login/);
  });
});
