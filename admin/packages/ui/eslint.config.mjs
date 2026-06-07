// admin/packages/ui/eslint.config.mjs
//
// ESLint v9 looks up `eslint.config.*` from the cwd. When `pnpm --filter
// @sacco/ui lint` runs, ESLint resolves this file from the package root.
// We import the shared config via a relative path (matching the workspace
// root convention in admin/eslint.config.mjs) rather than the package name,
// to keep resolution deterministic regardless of pnpm hoisting.

import baseConfig from "../eslint-config/index.js";

export default [
  ...baseConfig,
  {
    settings: {
      tailwindcss: {
        config: "../../apps/portal/tailwind.config.ts",
      },
    },
  },
  {
    ignores: ["node_modules", "dist", "storybook-static", "coverage"],
  },
];
