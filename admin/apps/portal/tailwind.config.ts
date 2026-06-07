import type { Config } from "tailwindcss";

// Tailwind v4 uses CSS-first config — see app/globals.css @theme block.
// This file exists ONLY so eslint-plugin-tailwindcss can resolve a path.
const config = {
  content: ["./app/**/*.{ts,tsx}", "../../packages/ui/src/**/*.{ts,tsx}"],
} satisfies Config;

export default config;
