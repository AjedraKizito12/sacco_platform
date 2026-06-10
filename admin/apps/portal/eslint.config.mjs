import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import nextConfig from "@sacco/eslint-config/next";

const here = dirname(fileURLToPath(import.meta.url));

export default [
  ...nextConfig,
  {
    settings: {
      tailwindcss: {
        // Tailwind v4 is CSS-first: eslint-plugin-tailwindcss 3.18+ loads the
        // CSS @theme block via tailwind-api-utils, which needs an absolute path
        // to resolve `tailwindcss` from a known location. The .ts file remains
        // for legacy tooling that still expects a JS Tailwind config path.
        config: resolve(here, "app/globals.css"),
      },
    },
    rules: {
      // Next.js 15 streams the root layout — we can opt out of the
      // explicit `metadata` export rule per page.
      "@next/next/no-html-link-for-pages": "off",
      // Class-name ordering is handled by `prettier-plugin-tailwindcss`
      // (sub-plan 03 Task 3). The Tailwind v4 + plugin-3.18 combo has
      // brittle config-loading paths in worker mode; rely on Prettier
      // sorting instead and skip the lint rule.
      "tailwindcss/classnames-order": "off",
    },
  },
  // Vitest test files: declare vitest globals so ESLint doesn't flag `vi`
  // as an undefined identifier. The `globals` package doesn't ship a
  // "vitest" entry, so we declare the commonly-used ones explicitly.
  {
    files: ["**/__tests__/**/*.{ts,tsx}", "**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}"],
    languageOptions: {
      globals: {
        vi: "readonly",
        describe: "readonly",
        it: "readonly",
        expect: "readonly",
        beforeAll: "readonly",
        afterAll: "readonly",
        beforeEach: "readonly",
        afterEach: "readonly",
        test: "readonly",
      },
    },
  },
  {
    ignores: ["node_modules", ".next", ".turbo", "next-env.d.ts"],
  },
];
