import nextConfig from "@sacco/eslint-config/next";

export default [
  ...nextConfig,
  {
    settings: {
      tailwindcss: {
        config: "./tailwind.config.ts",
      },
    },
    rules: {
      // Next.js 15 streams the root layout — we can opt out of the
      // explicit `metadata` export rule per page.
      "@next/next/no-html-link-for-pages": "off",
    },
  },
  {
    ignores: ["node_modules", ".next", ".turbo", "next-env.d.ts"],
  },
];
