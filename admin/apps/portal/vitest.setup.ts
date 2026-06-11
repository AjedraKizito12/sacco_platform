import "@testing-library/jest-dom/vitest";

// Radix UI primitives (Select, Dialog, etc.) use pointer events and scroll APIs
// that jsdom does not implement. These no-op stubs prevent "not implemented"
// errors and allow the components to open/close in unit tests.
Object.defineProperty(window.Element.prototype, "scrollIntoView", {
  writable: true,
  value: () => {},
});
Object.defineProperty(window.Element.prototype, "hasPointerCapture", {
  writable: true,
  value: () => false,
});
Object.defineProperty(window.Element.prototype, "setPointerCapture", {
  writable: true,
  value: () => {},
});
Object.defineProperty(window.Element.prototype, "releasePointerCapture", {
  writable: true,
  value: () => {},
});

// Radix UI's floating layers (Popover, Select content) measure available height.
// jsdom has no layout engine, so ResizeObserver is not implemented.
if (typeof window.ResizeObserver === "undefined") {
  window.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
