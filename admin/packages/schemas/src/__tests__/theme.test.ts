import { describe, expect, it } from "vitest";
import {
  THEME_DEFAULTS, THEME_ACCENTS, parseThemeCookie, serializeThemePrefs,
} from "../theme";

describe("theme prefs", () => {
  it("defaults are system/default/default", () => {
    expect(THEME_DEFAULTS).toEqual({ mode: "system", accent: "default", fontSize: "default" });
  });
  it("five accents including default", () => {
    expect(THEME_ACCENTS).toEqual(["default", "blue", "green", "amber", "slate"]);
  });
  it("missing cookie → defaults", () => {
    expect(parseThemeCookie(undefined)).toEqual(THEME_DEFAULTS);
  });
  it("garbage → defaults", () => {
    expect(parseThemeCookie("not json")).toEqual(THEME_DEFAULTS);
  });
  it("valid round-trips", () => {
    const p = { mode: "dark", accent: "blue", fontSize: "large" } as const;
    expect(parseThemeCookie(serializeThemePrefs(p))).toEqual(p);
  });
  it("invalid field falls back to that field's default", () => {
    expect(parseThemeCookie(JSON.stringify({ mode: "neon", accent: "blue", fontSize: "xl" })))
      .toEqual({ mode: "system", accent: "blue", fontSize: "xl" });
  });
});
