// Workspace-root ESLint flat config.
//
// ESLint v9 looks for `eslint.config.*` in the cwd; it does not walk up to
// per-package configs the way ESLint v8 + .eslintrc did. So when lint-staged
// (and other workspace-root tooling) invoke `eslint <abs-path>`, ESLint
// needs this file at the workspace root.
//
// We re-export the Next.js shared config (the portal app's effective config)
// and scope it to files under `apps/portal/`. Add more entries here when new
// apps land — each app keeps its own `eslint.config.mjs` for direct
// `pnpm --filter <app> lint` invocations.

import nextConfig from "./packages/eslint-config/next.js";

export default [
  {
    ignores: [
      "**/node_modules/**",
      "**/.next/**",
      "**/.turbo/**",
      "**/dist/**",
      "**/build/**",
      "**/coverage/**",
      "**/next-env.d.ts",
    ],
  },
  ...nextConfig.map((config) => ({
    ...config,
    files: config.files ?? ["apps/portal/**/*.{ts,tsx,js,jsx}"],
  })),
  {
    // The Next.js plugin's `no-html-link-for-pages` rule scans for a `pages`
    // directory relative to the eslint cwd. At the workspace root we don't
    // have one (the App Router is in apps/portal/app). Disable here; the
    // per-app config in apps/portal/eslint.config.mjs also disables it.
    files: ["apps/portal/**/*.{ts,tsx,js,jsx}"],
    rules: {
      "@next/next/no-html-link-for-pages": "off",
      "tailwindcss/classnames-order": "off",
    },
  },
];
