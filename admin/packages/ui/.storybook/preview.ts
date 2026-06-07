// admin/packages/ui/.storybook/preview.ts
import type { Preview } from "@storybook/react";

import "../src/globals.css";

const preview: Preview = {
  parameters: {
    controls: {
      matchers: { color: /(background|color)$/i, date: /Date$/i },
    },
    a11y: {
      element: "#storybook-root",
      manual: false,
    },
    backgrounds: {
      default: "surface-base",
      values: [
        { name: "surface-base", value: "#f8f8f8" },
        { name: "surface-elevated", value: "#ffffff" },
        { name: "dark", value: "#1f1f1f" },
      ],
    },
    layout: "padded",
  },
};

export default preview;
