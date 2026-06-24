import { chromium, type FullConfig } from "@playwright/test";

const EMAIL = process.env["E2E_EMAIL"] ?? "e2e@platform.example.com";
const PASSWORD = process.env["E2E_PASSWORD"] ?? "e2e-Password-123!";

/**
 * Logs in once with the seeded platform superuser and saves the browser
 * storage state (the httpOnly refresh cookie) so authenticated specs start
 * already signed in. Requires the seeded backend to be running.
 */
export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL ?? "http://localhost:3000";
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ baseURL });
    await page.goto("/platform/login");
    await page.getByLabel(/email/i).fill(EMAIL);
    await page.getByLabel(/password/i).fill(PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    // Wait for the authenticated dashboard, not just any /platform* URL: the
    // old /platform(\/|$) regex also matched /platform/login, so on a slow
    // (cold) first compile this could return before login completed and save
    // an EMPTY, unauthenticated storage state — failing every authed spec.
    await page.waitForURL((url) => url.pathname === "/platform", {
      timeout: 30_000,
    });
    await page
      .getByRole("heading", { name: /platform dashboard/i })
      .waitFor({ state: "visible", timeout: 15_000 });
    await page.context().storageState({ path: "tests/e2e/.auth/platform.json" });
  } finally {
    await browser.close();
  }
}
