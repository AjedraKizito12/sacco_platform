# Theme Preferences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let every portal user pick light/dark/system mode, one of five accent presets, and a font-size step — persisted in a `sacco_theme` cookie and applied with no flash of the wrong theme, uniformly across platform, operator, and member audiences.

**Architecture:** A cookie holds `{mode, accent, fontSize}`. The root server layout reads it, stamps `data-theme`/`data-accent`/`data-font-size` on `<html>`, and injects a pre-paint inline script that resolves `system` mode. The design-system token file gains a dark semantic layer, four accent-ramp overrides, and a `--font-scale` variable. A presentational `ThemeControls` (in `@sacco/ui`) is wired by a portal `ThemeProvider` that syncs the cookie to `documentElement` live. Appearance surfaces per audience plus a header quick-toggle consume the provider.

**Tech Stack:** Next.js 15 App Router, `@sacco/ui`/`@sacco/schemas`, CSS custom properties (design-system tokens), vitest. No backend, no migration, no new API.

**Spec:** `docs/superpowers/specs/2026-07-12-theme-preferences-design.md`

Branch: `feat/theme-preferences` (from `main`).

## Global Constraints

- **Cookie:** name `sacco_theme`, JSON `{mode,accent,fontSize}`, `Path=/`, `max-age` 1 year, `SameSite=Lax`, NOT httpOnly (client reads/writes it). Follows the existing `sacco_table_prefs` helper shape (`admin/packages/ui/src/components/DataTable/table-prefs.ts`).
- **Enums:** `mode ∈ {light, dark, system}` (default `system`); `accent ∈ {default, blue, green, amber, slate}` (default `default`, = current violet brand ramp, no override block); `fontSize ∈ {compact, default, large, xl}` (default `default`). Any invalid field → that field's default.
- **Contract P (tokens):** edit the canonical `docs/tokens.css`, then `cp docs/tokens.css admin/packages/ui/src/tokens.css`, then `bash scripts/check-tokens-sync.sh` must pass. Never edit the ui-package copy directly.
- **Contract Q (no literal hex in components):** accent/dark values live in tokens only. Do not add literal hex to component code. Audit touched components for pre-existing literal hex that would break dark mode; fix any found.
- **Contract E (CSP):** the pre-paint inline script is a static string constant with NO interpolated user data and NO `dangerouslySetInnerHTML` of user content. Attribute values come from a fixed allow-list.
- **Font scaling is type-only:** `--font-scale` multiplies the `--text-*` tokens; it must NOT scale spacing/layout tokens (deliberate — "font size", not zoom).
- **Both light and dark must be fully styled** (theme-aware requirement). Contrast: `--interactive-primary-text` on `--interactive-primary-bg` ≥ 4.5:1 for every accent in both modes.
- pnpm lint / typecheck / test clean across `@sacco/schemas`, `@sacco/ui`, `@sacco/portal`.

## File Structure

```
admin/packages/schemas/src/theme.ts                 (create: ThemePrefs + Zod + parse/serialize)
admin/packages/schemas/src/index.ts                 (modify: export)
admin/packages/schemas/src/__tests__/theme.test.ts  (create)

docs/tokens.css                                      (modify: dark layer, accent presets, --font-scale)
admin/packages/ui/src/tokens.css                     (modify: byte-copy of the above)

admin/packages/ui/src/components/ThemeControls/ThemeControls.tsx     (create)
admin/packages/ui/src/components/ThemeControls/ThemeModeToggle.tsx   (create)
admin/packages/ui/src/components/ThemeControls/ThemeControls.test.tsx (create)
admin/packages/ui/src/components/ThemeControls/ThemeControls.stories.tsx (create)
admin/packages/ui/src/components/ThemeControls/index.ts              (create)
admin/packages/ui/src/index.ts                                       (modify: export)

admin/apps/portal/src/theme/theme-cookie.ts          (create: server+client read/write)
admin/apps/portal/src/theme/ThemeProvider.tsx        (create: client context + live apply)
admin/apps/portal/src/theme/theme-script.ts          (create: pre-paint inline script string)
admin/apps/portal/src/theme/useTheme.ts              (create: context hook)
admin/apps/portal/app/layout.tsx                     (modify: stamp attrs, inline script, provider)
admin/apps/portal/src/__tests__/theme/ThemeProvider.test.tsx (create)

admin/apps/portal/app/platform/(authed)/settings/appearance/page.tsx (create)
admin/apps/portal/app/(tenant-authed)/settings/appearance/page.tsx   (create)
admin/apps/portal/src/components/theme/AppearanceSection.tsx          (create: shared client wrapper)
admin/apps/portal/app/member/(authed)/profile/_components/MemberAppearanceSection.tsx (create)
admin/apps/portal/app/member/(authed)/profile/page.tsx               (modify: render section)
admin/apps/portal/src/components/AppShellHeader.tsx                  (modify: header ThemeModeToggle)
admin/apps/portal/src/components/shell/nav-config.tsx               (modify: platform + tenant Settings)

CLAUDE.md                                            (modify: theming contract note)
```

---

### Task 1: `@sacco/schemas` — ThemePrefs type, Zod, parse/serialize

**Files:**
- Create: `admin/packages/schemas/src/theme.ts`, `admin/packages/schemas/src/__tests__/theme.test.ts`
- Modify: `admin/packages/schemas/src/index.ts`

**Interfaces:**
- Produces: `ThemeMode`, `ThemeAccent`, `ThemeFontSize` union types; `ThemePrefs` interface `{mode: ThemeMode; accent: ThemeAccent; fontSize: ThemeFontSize}`; `THEME_DEFAULTS: ThemePrefs`; `THEME_ACCENTS: readonly ThemeAccent[]`; `themePrefsSchema` (Zod, each field `.catch(default)`); `parseThemeCookie(raw: string | undefined): ThemePrefs` (never throws); `serializeThemePrefs(p: ThemePrefs): string` (JSON).

- [ ] **Step 1: Write failing test**

`admin/packages/schemas/src/__tests__/theme.test.ts`:
```ts
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/schemas test -- theme`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

`admin/packages/schemas/src/theme.ts`:
```ts
import { z } from "zod";

export type ThemeMode = "light" | "dark" | "system";
export type ThemeAccent = "default" | "blue" | "green" | "amber" | "slate";
export type ThemeFontSize = "compact" | "default" | "large" | "xl";

export interface ThemePrefs {
  mode: ThemeMode;
  accent: ThemeAccent;
  fontSize: ThemeFontSize;
}

export const THEME_ACCENTS = ["default", "blue", "green", "amber", "slate"] as const;
export const THEME_FONT_SIZES = ["compact", "default", "large", "xl"] as const;

export const THEME_DEFAULTS: ThemePrefs = {
  mode: "system",
  accent: "default",
  fontSize: "default",
};

export const themePrefsSchema = z.object({
  mode: z.enum(["light", "dark", "system"]).catch(THEME_DEFAULTS.mode),
  accent: z.enum(THEME_ACCENTS).catch(THEME_DEFAULTS.accent),
  fontSize: z.enum(THEME_FONT_SIZES).catch(THEME_DEFAULTS.fontSize),
});

export function parseThemeCookie(raw: string | undefined): ThemePrefs {
  if (!raw) return { ...THEME_DEFAULTS };
  try {
    return themePrefsSchema.parse(JSON.parse(raw));
  } catch {
    return { ...THEME_DEFAULTS };
  }
}

export function serializeThemePrefs(p: ThemePrefs): string {
  return JSON.stringify(p);
}
```
Add `export * from "./theme";` to `index.ts`.
(Note: `z.object().parse` on a non-object throws → caught → defaults. Per-field `.catch` handles invalid enum values while keeping valid siblings. Verify the installed zod version supports `.catch`; it does in zod ≥3.20 — the repo already uses `.catch` elsewhere if present, else this is the first use and is standard.)

- [ ] **Step 4: Run test + lint + typecheck**

Run: `pnpm --filter @sacco/schemas test -- theme && pnpm --filter @sacco/schemas lint && pnpm --filter @sacco/schemas typecheck`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/schemas/src/theme.ts admin/packages/schemas/src/__tests__/theme.test.ts admin/packages/schemas/src/index.ts
git commit -m "feat(schemas): theme preferences type + cookie parse/serialize"
```

---

### Task 2: Token layer — dark theme, accent presets, font scale

**Files:**
- Modify: `docs/tokens.css` (canonical), then `admin/packages/ui/src/tokens.css` (byte copy)

**Interfaces:**
- Produces: `:root[data-theme="dark"]` semantic overrides; `:root[data-accent="{blue,green,amber,slate}"]` brand-ramp overrides (+ dark-mode variants where needed); `--font-scale` variable + `:root[data-font-size="{compact,large,xl}"]` overrides; `--text-*` tokens re-expressed as `calc(<px> * var(--font-scale))`.

- [ ] **Step 1: Add `--font-scale` and re-express the type scale**

In `docs/tokens.css`, in the `:root` block, add `--font-scale: 1;` and change the type tokens (lines ~214-220) to:
```css
  --font-scale:   1;
  --text-h1:      calc(36px * var(--font-scale));
  --text-h2:      calc(30px * var(--font-scale));
  --text-h3:      calc(24px * var(--font-scale));
  --text-h4:      calc(20px * var(--font-scale));
  --text-h5:      calc(18px * var(--font-scale));
  --text-body-lg: calc(16px * var(--font-scale));
  --text-body:    calc(14px * var(--font-scale));
```
(Apply to any other `--text-*` size tokens in that block — e.g. `--text-small`, `--text-caption` if present. Do NOT touch spacing/radius tokens.)

- [ ] **Step 2: Add the font-size step blocks**

After the `:root` block (near the end of the semantic layer):
```css
:root[data-font-size="compact"] { --font-scale: 0.9; }
:root[data-font-size="large"]   { --font-scale: 1.15; }
:root[data-font-size="xl"]      { --font-scale: 1.3; }
/* "default" needs no block (--font-scale: 1). */
```

- [ ] **Step 3: Add the dark semantic layer**

Add a `:root[data-theme="dark"]` block overriding the semantic tokens (base ramp untouched; only mappings flip). Concrete starting values (implementer verifies contrast with a checker):
```css
:root[data-theme="dark"] {
  --color-canvas:        #17161C;   /* dark violet-tinted page bg */
  --surface-base:        var(--color-canvas);
  --surface-elevated:    #201F27;
  --surface-overlay:     #262530;
  --surface-sunken:      #1B1A21;
  --surface-hover:       #2A2933;
  --surface-active:      #322F3D;
  --surface-selected:    #2C2540;
  --surface-disabled:    #201F27;
  --surface-readonly:    #1B1A21;

  --nav-item-active-bg:   #2C2540;
  --nav-item-active-text: var(--color-brand-200);
  --nav-item-active-icon: var(--color-brand-300);

  --text-primary:    #F4F3F9;
  --text-secondary:  #C9C7D4;
  --text-tertiary:   #9E9CAC;
  --text-disabled:   #6E6C7A;
  --text-inverse:    #17161C;
  --text-link:       var(--color-info-300);
  --text-link-hover: var(--color-info-200);
  --text-success:    var(--color-success-300);
  --text-warning:    var(--color-warning-300);
  --text-danger:     var(--color-danger-300);
  --text-info:       var(--color-info-300);
  --text-accent:     var(--color-accent-300);

  --border-subtle:   #2E2D38;
  --border-default:  #3A3947;
  --border-strong:   #4A4857;
  --border-focus:    var(--color-brand-400);
  --border-success:  var(--color-success-400);
  --border-warning:  var(--color-warning-400);
  --border-danger:   var(--color-danger-400);

  --icon-default:    #9E9CAC;
  --icon-strong:     #F4F3F9;
  --icon-disabled:   #5A5866;
  --icon-inverse:    #17161C;

  --interactive-primary-bg:          var(--color-brand-500);
  --interactive-primary-bg-hover:    var(--color-brand-400);
  --interactive-primary-bg-active:   var(--color-brand-300);
  --interactive-primary-bg-disabled: #3A3947;
  --interactive-primary-text:        #17161C;

  --interactive-secondary-bg:        #201F27;
  --interactive-secondary-bg-hover:  #2A2933;
  --interactive-secondary-bg-active: #322F3D;
  --interactive-secondary-border:    #3A3947;
  --interactive-secondary-text:      #F4F3F9;

  --interactive-ghost-bg-hover:      #2A2933;
  --interactive-ghost-bg-active:     #322F3D;
  --interactive-ghost-text:          #C9C7D4;
  --interactive-ghost-text-hover:    #F4F3F9;

  --interactive-destructive-bg:       var(--color-danger-500);
  --interactive-destructive-bg-hover: var(--color-danger-400);
  --interactive-destructive-text:     #17161C;

  --status-success-bg:  #16301F;
  --status-warning-bg:  #33280D;
  --status-danger-bg:   #3A1A1D;
  --status-info-bg:     #16273A;
  --status-accent-bg:   #241a3a;
  --status-neutral-bg:  #2A2933;
  --status-neutral-text:#C9C7D4;
  --status-dark-bg:     #0F0E13;
  --status-dark-text:   #F4F3F9;
  --status-danger-solid-bg:   var(--color-danger-500);
  --status-danger-solid-text: #17161C;

  --chart-tooltip-bg: #262530;
}
```
(These are a coherent starting set; the implementer runs a contrast check on text-on-surface and primary-text-on-primary-bg and nudges any pair below 4.5:1. Also override `--status-*-solid-text` / any semantic pairs the grep in Step 6 surfaces.)

- [ ] **Step 4: Add the four accent presets**

Each overrides the brand ramp. Provide light-mode blocks and, where the ramp needs different stops for dark surfaces, a `[data-theme="dark"][data-accent="x"]` block. Example for blue (repeat structure for green/amber/slate with their ramps):
```css
:root[data-accent="blue"] {
  --color-brand-50:  #EFF5FF; --color-brand-100: #DBE8FE; --color-brand-200: #BFD7FE;
  --color-brand-300: #93BBFD; --color-brand-400: #609AFA; --color-brand-500: #3B82F6;
  --color-brand-600: #2570EB; --color-brand-700: #1D5BD8; --color-brand-800: #1E4BAF;
  --color-brand-900: #1E408A;
}
/* green: emerald ramp; amber: amber ramp; slate: neutral slate ramp — same 50..900 shape. */
```
Use well-known accessible ramps (Tailwind blue/emerald/amber/slate are a safe source). `default` (violet) gets no block. Verify each preset's `--color-brand-600` (light primary bg) carries white text at ≥4.5:1, and its `--color-brand-500` (dark primary bg) carries the dark ink `#17161C` at ≥4.5:1.

- [ ] **Step 5: Sync the ui-package copy + run the sync check**

Run:
```bash
cp docs/tokens.css admin/packages/ui/src/tokens.css
bash scripts/check-tokens-sync.sh
```
Expected: the sync script passes (files byte-identical).

- [ ] **Step 6: Audit for literal hex in components that would break dark mode**

Run: `grep -rnE "#[0-9a-fA-F]{6}\b" admin/packages/ui/src/components admin/apps/portal/src admin/apps/portal/app --include="*.tsx" | grep -v "tokens.css" | head -40`
Expected: ideally empty (contract Q). Record any hits in the task report; fix ones in files this branch already touches, list the rest for the final review (do not sprawl into unrelated files here).

- [ ] **Step 7: Commit**

```bash
git add docs/tokens.css admin/packages/ui/src/tokens.css
git commit -m "feat(ui): dark theme layer, accent presets, font-scale tokens"
```

---

### Task 3: `@sacco/ui` — ThemeControls + ThemeModeToggle

**Files:**
- Create: `admin/packages/ui/src/components/ThemeControls/{ThemeControls.tsx,ThemeModeToggle.tsx,ThemeControls.test.tsx,ThemeControls.stories.tsx,index.ts}`
- Modify: `admin/packages/ui/src/index.ts`

**Interfaces:**
- Consumes: `ThemePrefs`, `ThemeMode`, `ThemeAccent`, `ThemeFontSize`, `THEME_ACCENTS`, `THEME_FONT_SIZES` (Task 1).
- Produces:
  - `ThemeControls({ value: ThemePrefs; onChange: (next: ThemePrefs) => void })` — mode segmented control (Light/Dark/System), accent swatch row, font-size segmented control.
  - `ThemeModeToggle({ value: ThemeMode; onChange: (next: ThemeMode) => void })` — compact icon button cycling light→dark→system.

- [ ] **Step 1: Write failing tests**

`ThemeControls.test.tsx`:
```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeControls, ThemeModeToggle } from "./ThemeControls";

const base = { mode: "system", accent: "default", fontSize: "default" } as const;

describe("ThemeControls", () => {
  it("marks the current mode/accent/size selected", () => {
    render(<ThemeControls value={{ ...base, mode: "dark", accent: "blue" }} onChange={() => {}} />);
    expect(screen.getByRole("button", { name: /dark/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /blue/i })).toHaveAttribute("aria-pressed", "true");
  });
  it("fires onChange with the updated mode", async () => {
    const onChange = vi.fn();
    render(<ThemeControls value={base} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /dark/i }));
    expect(onChange).toHaveBeenCalledWith({ ...base, mode: "dark" });
  });
  it("fires onChange with the updated accent", async () => {
    const onChange = vi.fn();
    render(<ThemeControls value={base} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /green/i }));
    expect(onChange).toHaveBeenCalledWith({ ...base, accent: "green" });
  });
  it("fires onChange with the updated font size", async () => {
    const onChange = vi.fn();
    render(<ThemeControls value={base} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /large/i }));
    expect(onChange).toHaveBeenCalledWith({ ...base, fontSize: "large" });
  });
});

describe("ThemeModeToggle", () => {
  it("cycles light → dark", async () => {
    const onChange = vi.fn();
    render(<ThemeModeToggle value="light" onChange={onChange} />);
    await userEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith("dark");
  });
});
```
(Every selectable control carries `aria-pressed`; the selected one is `"true"`. Accent swatch buttons expose their accent name via `aria-label` so `getByRole("button", { name: /blue/i })` resolves.)

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm --filter @sacco/ui test -- ThemeControls`
Expected: FAIL (component missing).

- [ ] **Step 3: Implement the components**

`ThemeControls.tsx` (client): three labelled groups of `aria-pressed` buttons built with the design tokens (`--surface-*`, `--text-*`, `--border-*`, `--interactive-*`). Mode buttons: Light/Dark/System (lucide `Sun`/`Moon`/`Monitor` icons + label). Accent swatches: one button per `THEME_ACCENTS`, each showing that accent's brand color — render a swatch whose background reads the preset via an inline `data-accent` scoped span OR a fixed swatch color map (a small `ACCENT_SWATCH: Record<ThemeAccent,string>` of representative hex is acceptable HERE because it's presentational chrome for the picker itself, not app UI — document that exception in a comment). Font-size buttons: Compact/Default/Large/Extra-large. Each group calls `onChange({ ...value, <field>: next })`. `ThemeModeToggle.tsx`: a single icon button; clicking advances `light→dark→system→light`.
Export both from `index.ts`; add `export * from "./components/ThemeControls";` to `ui/src/index.ts`.

- [ ] **Step 4: Storybook story**

`ThemeControls.stories.tsx`: a stateful wrapper showing all controls; variants for each mode. Per portal-storybook-story conventions.

- [ ] **Step 5: Run tests + lint + typecheck**

Run: `pnpm --filter @sacco/ui test -- ThemeControls && pnpm --filter @sacco/ui lint && pnpm --filter @sacco/ui typecheck`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add admin/packages/ui/src/components/ThemeControls admin/packages/ui/src/index.ts
git commit -m "feat(ui): ThemeControls + ThemeModeToggle components"
```

---

### Task 4: Portal cookie helpers + ThemeProvider + root-layout wiring

**Files:**
- Create: `admin/apps/portal/src/theme/{theme-cookie.ts,ThemeProvider.tsx,theme-script.ts,useTheme.ts}`
- Modify: `admin/apps/portal/app/layout.tsx`
- Test: `admin/apps/portal/src/__tests__/theme/ThemeProvider.test.tsx`

**Interfaces:**
- Consumes: `ThemePrefs`, `parseThemeCookie`, `serializeThemePrefs`, `THEME_DEFAULTS` (Task 1).
- Produces:
  - `getServerThemePrefs(): Promise<ThemePrefs>` (reads the cookie via `next/headers`).
  - `writeThemeCookieClient(p: ThemePrefs): void` (document.cookie).
  - `THEME_SCRIPT: string` — the pre-paint inline script (static).
  - `ThemeProvider({ initial: ThemePrefs; children })` + `useTheme()` returning `{ prefs, setPrefs }`. On `setPrefs`: write cookie + apply `data-theme`/`data-accent`/`data-font-size` to `document.documentElement` (resolving `system` via matchMedia); subscribe to scheme changes while `system`.
  - `applyThemeAttributes(el: HTMLElement, prefs: ThemePrefs, systemDark: boolean): void` (exported for tests).

- [ ] **Step 1: Write failing provider test**

`admin/apps/portal/src/__tests__/theme/ThemeProvider.test.tsx`:
```tsx
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
```
(Rationale: omitting `data-accent="default"` / `data-font-size="default"` keeps the DOM clean and lets the base `:root` values apply — the token blocks only exist for non-default values.)

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm --filter @sacco/portal test -- ThemeProvider`
Expected: FAIL.

- [ ] **Step 3: Implement the theme module**

- `theme-cookie.ts`: `COOKIE = "sacco_theme"`; `getServerThemePrefs()` uses `cookies()` from `next/headers` → `parseThemeCookie`; `writeThemeCookieClient(p)` sets `document.cookie` (`path=/;max-age=31536000;SameSite=Lax`, encodeURIComponent).
- `theme-script.ts`: `export const THEME_SCRIPT` — an IIFE string that reads the `sacco_theme` cookie, parses `{mode,accent,fontSize}` defensively, resolves `system` via `matchMedia("(prefers-color-scheme: dark)")`, and sets the three `data-*` attributes on `document.documentElement` (omitting default accent/font-size). No user input is interpolated — the string is a literal.
- `ThemeProvider.tsx`: React context holding `prefs`; `applyThemeAttributes(el, prefs, systemDark)` (pure, exported); on mount + on `setPrefs`, apply to `document.documentElement` and write the cookie; a `matchMedia` listener re-applies while `mode==="system"`.
- `useTheme.ts`: `useContext` wrapper throwing outside the provider.

- [ ] **Step 4: Wire the root layout**

In `admin/apps/portal/app/layout.tsx`:
```tsx
import { getServerThemePrefs } from "@/theme/theme-cookie";
import { ThemeProvider } from "@/theme/ThemeProvider";
import { THEME_SCRIPT } from "@/theme/theme-script";
...
  const themePrefs = await getServerThemePrefs();
  const dataTheme = themePrefs.mode === "system" ? undefined : themePrefs.mode;
  return (
    <html
      lang="en"
      className={inter.variable}
      {...(dataTheme ? { "data-theme": dataTheme } : {})}
      {...(themePrefs.accent !== "default" ? { "data-accent": themePrefs.accent } : {})}
      {...(themePrefs.fontSize !== "default" ? { "data-font-size": themePrefs.fontSize } : {})}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        ...
        <ThemeProvider initial={themePrefs}>
          {/* existing tree (NuqsAdapter/AuthProvider/...) */}
        </ThemeProvider>
        ...
```
(The `dangerouslySetInnerHTML` here is a STATIC constant — permitted by contract E because no user data is interpolated. Add a comment saying so. This is the one sanctioned use.)

- [ ] **Step 5: Run tests + lint + typecheck**

Run: `pnpm --filter @sacco/portal test -- ThemeProvider && pnpm --filter @sacco/portal lint && pnpm --filter @sacco/portal typecheck`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add admin/apps/portal/src/theme admin/apps/portal/app/layout.tsx admin/apps/portal/src/__tests__/theme
git commit -m "feat(portal): theme cookie, provider, no-flash root-layout wiring"
```

---

### Task 5: Appearance surfaces + header toggle

**Files:**
- Create: `admin/apps/portal/src/components/theme/AppearanceSection.tsx`; `app/platform/(authed)/settings/appearance/page.tsx`; `app/(tenant-authed)/settings/appearance/page.tsx`; `app/member/(authed)/profile/_components/MemberAppearanceSection.tsx`
- Modify: `app/member/(authed)/profile/page.tsx`; `admin/apps/portal/src/components/AppShellHeader.tsx`; `admin/apps/portal/src/components/shell/nav-config.tsx`

**Interfaces:**
- Consumes: `ThemeControls`, `ThemeModeToggle` (Task 3); `useTheme` (Task 4).
- Produces: an `AppearanceSection` client component (`<ThemeControls>` fed by `useTheme`); three audience surfaces; the header quick-toggle.

- [ ] **Step 1: Implement AppearanceSection + pages**

- `AppearanceSection.tsx` (client): `const { prefs, setPrefs } = useTheme(); return <Card><ThemeControls value={prefs} onChange={setPrefs} /></Card>` with a heading + one-line helper text.
- `platform/(authed)/settings/appearance/page.tsx` (server): `getPlatformPageContext()` + `requirePlatformPermission(user, "settings.read")`, render heading + `<AppearanceSection />`. Add `{ label: "Appearance", href: "/platform/settings/appearance" }` to the platform Settings children in `nav-config.tsx`.
- `(tenant-authed)/settings/appearance/page.tsx` (server): thin page rendering `<AppearanceSection />`. Add a top-level "Settings" nav item to the tenant nav in `nav-config.tsx` pointing at `/settings/appearance` (new group; operator portal had no settings area).
- `member/(authed)/profile/_components/MemberAppearanceSection.tsx` = re-export/thin wrapper of `AppearanceSection`; render it in `member/(authed)/profile/page.tsx` below the existing profile content.

- [ ] **Step 2: Header quick-toggle**

In `AppShellHeader.tsx`, add `<AppShellThemeToggle />` to the header `end` row before the user menu (create a tiny client `AppShellThemeToggle` that pulls `useTheme` and renders `<ThemeModeToggle value={prefs.mode} onChange={(mode) => setPrefs({ ...prefs, mode })} />`). Works for all three variants (the header is shared).

- [ ] **Step 3: Failing test for the wiring**

`admin/apps/portal/src/__tests__/theme/AppearanceSection.test.tsx`: render `AppearanceSection` inside a `ThemeProvider` with an initial value; assert `ThemeControls` shows the initial selection; simulate an accent click and assert the cookie write / provider update (mock `writeThemeCookieClient` or assert `document.documentElement` got `data-accent`). Keep it focused (one integration test).

- [ ] **Step 4: Run tests + lint + typecheck**

Run: `pnpm --filter @sacco/portal test -- theme && pnpm --filter @sacco/portal lint && pnpm --filter @sacco/portal typecheck`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/settings/appearance" "admin/apps/portal/app/(tenant-authed)/settings/appearance" "admin/apps/portal/app/member/(authed)/profile" admin/apps/portal/src/components/theme admin/apps/portal/src/components/AppShellHeader.tsx admin/apps/portal/src/components/shell/nav-config.tsx admin/apps/portal/src/__tests__/theme/AppearanceSection.test.tsx
git commit -m "feat(portal): appearance settings surfaces + header theme toggle"
```

---

### Task 6: Close-out — visual verification, audit, CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Full admin gates**

Run: `cd admin && pnpm lint && pnpm typecheck && pnpm test`
Expected: all green across schemas, ui, portal.

- [ ] **Step 2: Token sync re-check**

Run: `bash scripts/check-tokens-sync.sh`
Expected: pass.

- [ ] **Step 3: Visual verification (dev server serving the branch)**

Drive the running portal: switch to dark mode, a non-default accent (e.g. blue), and `large` font size, then eyeball: the dashboard, a `<DataTable>` screen, a form dialog (e.g. loan write-off), and a status-badge-heavy screen (approvals). Confirm readable contrast, no clipped layouts, and the no-flash behavior on reload (cookie set → correct theme on first paint). Record findings in the task report. Fix any contrast/clip issues in `docs/tokens.css` (re-`cp` + sync check) or the touched components.

- [ ] **Step 4: Update CLAUDE.md**

Add a short **Theming contract** note (near the design-system contracts P/Q):
- User theme prefs live in the `sacco_theme` cookie (`{mode,accent,fontSize}`), applied via `data-theme`/`data-accent`/`data-font-size` on `<html>`; the root layout stamps them and a static pre-paint inline script resolves `system` mode (the one sanctioned `dangerouslySetInnerHTML` — a constant, no user data, contract E).
- Dark mode + accent presets + font scaling live entirely in the token semantic layer (`docs/tokens.css`, copied per contract P); components never hardcode theme values (contract Q). Adding an accent = one ramp block + one `THEME_ACCENTS` entry.
- Font scaling (`--font-scale`) scales type only, not spacing.
- Note the scope: SACCO logo + profile-picture uploads are a separate future spec (need file storage).

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): theming contract (cookie prefs, dark/accent/font tokens)"
```

## Out of scope (reminder)

- SACCO logo upload + user profile pictures (separate spec; needs file storage).
- Cross-device / server-side preference sync (cookie is per-device).
- Free/custom accent colors; high-contrast mode.
