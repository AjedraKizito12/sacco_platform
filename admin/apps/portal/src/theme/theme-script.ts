// THEME_SCRIPT is a STATIC string constant — no user input is ever
// interpolated into it. It is injected into the root layout's <head> via
// `dangerouslySetInnerHTML` (contract E's one sanctioned exception: a
// literal constant with no user-controlled data qualifies as safe).
//
// It runs before React hydrates / before first paint, reads the
// `sacco_theme` cookie directly (defensive parsing — cookie content is
// still attacker-influenceable client storage, so nothing here is `eval`'d
// or trusted beyond simple property reads), resolves "system" via
// matchMedia, and stamps `data-theme` / `data-accent` / `data-font-size`
// on `document.documentElement`. This eliminates the flash of the wrong
// theme that would otherwise occur between first paint and React mount.
export const THEME_SCRIPT = `
(function () {
  try {
    var COOKIE = "sacco_theme";
    var match = document.cookie.match(new RegExp("(?:^|; )" + COOKIE + "=([^;]*)"));
    var prefs = { mode: "system", accent: "default", fontSize: "default" };
    if (match) {
      try {
        var parsed = JSON.parse(decodeURIComponent(match[1]));
        if (parsed && typeof parsed === "object") {
          if (parsed.mode === "light" || parsed.mode === "dark" || parsed.mode === "system") {
            prefs.mode = parsed.mode;
          }
          if (
            parsed.accent === "default" ||
            parsed.accent === "blue" ||
            parsed.accent === "green" ||
            parsed.accent === "amber" ||
            parsed.accent === "slate"
          ) {
            prefs.accent = parsed.accent;
          }
          if (
            parsed.fontSize === "compact" ||
            parsed.fontSize === "default" ||
            parsed.fontSize === "large" ||
            parsed.fontSize === "xl"
          ) {
            prefs.fontSize = parsed.fontSize;
          }
        }
      } catch (e) {}
    }
    var systemDark = false;
    try {
      systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    } catch (e) {}
    var resolvedTheme = prefs.mode === "system" ? (systemDark ? "dark" : "light") : prefs.mode;
    var el = document.documentElement;
    el.setAttribute("data-theme", resolvedTheme);
    if (prefs.accent && prefs.accent !== "default") {
      el.setAttribute("data-accent", prefs.accent);
    } else {
      el.removeAttribute("data-accent");
    }
    if (prefs.fontSize && prefs.fontSize !== "default") {
      el.setAttribute("data-font-size", prefs.fontSize);
    } else {
      el.removeAttribute("data-font-size");
    }
  } catch (e) {}
})();
`;
