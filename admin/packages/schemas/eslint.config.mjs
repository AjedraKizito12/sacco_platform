import baseConfig from "@sacco/eslint-config";

export default [
  ...baseConfig,
  { ignores: ["node_modules", "dist", "coverage"] },
];
