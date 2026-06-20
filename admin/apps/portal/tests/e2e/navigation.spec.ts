import { test, expect } from "@playwright/test";

// Authenticated project (storageState from global-setup). Going directly to each
// path is more robust than clicking the sidebar; the assertion is the page's <h1>.
const NAV: Array<[string, RegExp]> = [
  ["/platform/tenants", /tenants/i],
  ["/platform/users", /users/i],
  ["/platform/operations", /operations/i],
  ["/platform/settings", /settings/i],
  ["/platform/approvals", /approvals/i],
  ["/platform/audit", /audit/i],
];

test.describe("Platform navigation", () => {
  for (const [path, heading] of NAV) {
    test(`navigates to ${path}`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    });
  }
});
