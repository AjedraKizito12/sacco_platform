import baseConfig from "@sacco/eslint-config";

export default [
  ...baseConfig,
  {
    files: ["src/generated/**/*"],
    rules: {
      // Generated code has its own conventions.
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": "off",
    },
  },
  {
    ignores: ["node_modules", "dist", "coverage"],
  },
];
