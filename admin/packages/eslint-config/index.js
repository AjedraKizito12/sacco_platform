// admin/packages/eslint-config/index.js
import js from "@eslint/js";
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import tailwind from "eslint-plugin-tailwindcss";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["**/*.{ts,tsx,js,jsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      react: reactPlugin,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y,
      tailwindcss: tailwind,
    },
    settings: {
      react: { version: "detect" },
      tailwindcss: {
        callees: ["clsx", "cn", "cva"],
        config: "apps/portal/tailwind.config.ts",
      },
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      ...reactPlugin.configs.recommended.rules,
      // eslint-plugin-react-hooks v7 ships many React Compiler rules in
      // `recommended`. We only opt into the two classic rules for now;
      // the compiler rules require the React Compiler to be configured.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      ...jsxA11y.configs.recommended.rules,

      // React 19 / Next.js 15 — no need for React import in JSX.
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",

      // TypeScript handles unused imports better than the JS rule.
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],

      // Discourage `dangerouslySetInnerHTML` — CLAUDE.md hard contract.
      "react/no-danger": "error",

      // Tailwind: classnames-order disabled (handled by prettier-plugin-tailwindcss
      // at format time, and the v4 CSS-first config breaks the eslint plugin's
      // tailwindcss package resolution in workspace contexts).
      "tailwindcss/classnames-order": "off",
      "tailwindcss/no-custom-classname": "off",
    },
  },
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/.next/**",
      "**/.turbo/**",
      "**/storybook-static/**",
      "**/coverage/**",
    ],
  },
];
