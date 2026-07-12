import { describe, expect, it } from "vitest";
import { applyThemeAttributes } from "@/theme/ThemeProvider";

describe("applyThemeAttributes", () => {
  it("stamps explicit dark", () => {
    const el = document.createElement("html");
    applyThemeAttributes(el, { mode: "dark", accent: "blue", fontSize: "large" }, false);
    expect(el.getAttribute("data-theme")).toBe("dark");
    expect(el.getAttribute("data-accent")).toBe("blue");
    expect(el.getAttribute("data-font-size")).toBe("large");
  });
  it("resolves system via the systemDark flag", () => {
    const el = document.createElement("html");
    applyThemeAttributes(el, { mode: "system", accent: "default", fontSize: "default" }, true);
    expect(el.getAttribute("data-theme")).toBe("dark");
  });
  it("omits data-accent/font-size when default", () => {
    const el = document.createElement("html");
    applyThemeAttributes(el, { mode: "light", accent: "default", fontSize: "default" }, false);
    expect(el.getAttribute("data-theme")).toBe("light");
    expect(el.hasAttribute("data-accent")).toBe(false);
    expect(el.hasAttribute("data-font-size")).toBe(false);
  });
});
