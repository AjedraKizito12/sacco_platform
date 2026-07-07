import "@testing-library/jest-dom/vitest";

// Recharts' ResponsiveContainer relies on ResizeObserver, which jsdom does not
// implement. A no-op polyfill lets chart components mount in tests; the SVG
// geometry isn't asserted (we test the DOM legends/labels instead).
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
if (!("ResizeObserver" in globalThis)) {
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver = ResizeObserverStub;
}

// Recharts' ResponsiveContainer logs a width(0)/height(0) warning under jsdom
// because the DOM has no layout. We assert chart components via their DOM
// summaries (aria labels / legends), not SVG geometry, so this one specific
// message is noise — silence it while letting every other warning through.
const realWarn = console.warn.bind(console);
console.warn = (...args: unknown[]) => {
  if (typeof args[0] === "string" && args[0].includes("width(0) and height(0)")) {
    return;
  }
  realWarn(...args);
};
