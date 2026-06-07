// admin/packages/eslint-config/next.js
import base from "./index.js";

// Lazily imported only by apps/portal so libraries don't pull Next in.
import nextPlugin from "@next/eslint-plugin-next";

export default [
  ...base,
  {
    files: ["**/*.{ts,tsx,js,jsx}"],
    plugins: { "@next/next": nextPlugin },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs["core-web-vitals"].rules,
    },
  },
];
