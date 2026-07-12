# Theme Preferences (Design)

**Status:** Approved (brainstorming, 2026-07-12)
**Register:** product (admin/member portal) + design-system work.

## Goal

Let every portal user choose their appearance — light / dark / system mode, an
accent color from a curated set, and a font-size step — persisted per device
and applied without a flash of the wrong theme. Uniform across all three
audiences (platform, operator, member).

This is the first of two subsystems from the original request. **SACCO logo
upload and user profile pictures are a separate spec** (they need file storage,
which does not exist yet and arrives with Phase 4's MinIO). This spec covers
theme preferences only.

## Key decisions (resolved in brainstorming)

- **Persistence:** a single cookie `sacco_theme`, per device (mirrors the
  existing `sacco_table_prefs` cookie). No backend, no migration, no new API.
  Cross-device sync is explicitly out of scope.
- **Accent:** a curated set of five presets (not a free picker), each swapping
  only the `--color-brand-*` ramp and contrast-checked in light and dark.
- **Font size:** discrete steps (Compact / Default / Large / Extra-large), each
  overriding one root base-font-size variable the rem scale keys off.
- **Mode:** light / dark / system; `system` resolved client-side from
  `prefers-color-scheme`.

## Architecture

```
                cookie: sacco_theme {mode, accent, fontSize}
                          │                    ▲
   ┌──────────────────────▼──────────┐         │ write on change
   │ root layout.tsx (server)         │         │
   │  - read cookie                   │   ┌─────┴───────────────┐
   │  - stamp data-theme/-accent/     │   │ ThemeProvider        │
   │    -font-size on <html>          │   │ (client)             │
   │  - inject pre-paint inline script│   │  - live-updates      │
   └──────────────────────────────────┘   │    documentElement   │
                          │                │  - writes cookie     │
                          ▼                └─────▲───────────────┘
        <html data-theme data-accent data-font-size>
                          │                      │ onChange
   ┌──────────────────────▼──────────┐   ┌──────┴───────────────┐
   │ tokens.css semantic layer        │   │ ThemeControls (@ui)  │
   │  :root[data-theme="dark"]        │   │  mode / accent /     │
   │  :root[data-accent="blue"] …     │   │  fontSize controls   │
   │  :root[data-font-size="large"] … │   └──────────────────────┘
   └──────────────────────────────────┘   Appearance page (×3 audiences)
                                           + header quick light/dark toggle
```

### Component 1: Cookie contract + helpers

- Cookie name `sacco_theme`, JSON value `{mode, accent, fontSize}`. Non-httpOnly
  (the client reads/writes it), `SameSite=Lax`, `Path=/`, 1-year max-age.
- `ThemePrefs` type + a Zod schema in `@sacco/schemas` with safe defaults
  (`mode: "system"`, `accent: "slate"`, `fontSize: "default"`); an
  `parseThemeCookie(raw: string | undefined): ThemePrefs` that never throws
  (bad/absent cookie → defaults). Serialization helper for writing.
- Server read helper in the portal (`getThemePrefs()` over `next/headers`
  cookies) used by the root layout; client read/write via `document.cookie`.

### Component 2: Token layer (canonical `docs/tokens.css`, contract P)

The design system's semantic layer was authored for exactly this ("future dark
mode only needs to override the semantic layer"). Three additions:

- **Dark theme:** `:root[data-theme="dark"] { … }` overriding the semantic
  tokens (surface, text, border, interactive, status, chart) with dark values.
  Base ramp colors stay; only the semantic mappings flip. Every component that
  uses `var(--surface-*)` / `var(--text-*)` / etc. inherits dark automatically.
- **Accent presets:** `:root[data-accent="blue"]` (green/violet/amber likewise)
  overriding `--color-brand-50 … --color-brand-900`. `slate` is the default
  (current brand ramp) and needs no override block. Each preset must keep
  `--interactive-primary-text` contrast ≥ 4.5:1 on `--interactive-primary-bg`
  in BOTH light and dark (dark accent blocks live under
  `:root[data-theme="dark"][data-accent="blue"]` where the ramp needs adjusting
  for dark surfaces).
- **Font-size steps:** the type scale currently hardcodes absolute px
  (`--text-h1: 36px … --text-body: 14px`, no base variable). Introduce a root
  `--font-scale` (default `1`) and re-express each `--text-*` token as
  `calc(<original-px> * var(--font-scale))`, then set the scale per step:
  `:root[data-font-size="compact"]` → `0.9`, `default` → `1` (no block needed),
  `large` → `1.15`, `xl` → `1.3`. This scales *type only*, not spacing/layout
  (deliberate — "font size", not whole-UI zoom). The `@layer` aliases that
  re-map `--text-*` to themselves (lines ~472-478) are unaffected since they
  reference the now-calc'd values.
- Workflow per contract P: edit `docs/tokens.css`, then
  `cp docs/tokens.css admin/packages/ui/src/tokens.css`, then
  `scripts/check-tokens-sync.sh` passes.

### Component 3: `ThemeControls` + header toggle (`@sacco/ui`)

- `ThemeControls` — presentational, controlled: props `value: ThemePrefs`,
  `onChange(next: ThemePrefs)`. Renders a mode segmented control (Light / Dark /
  System), a row of accent swatches (five, showing the preset's brand color,
  selected state), and a font-size segmented control. Fully keyboard-accessible;
  swatches have `aria-label` + `aria-pressed`.
- `ThemeModeToggle` — a compact icon control (sun/moon/auto) for the header user
  menu; cycles light → dark → system, calls the same `onChange`.
- Both are presentational; the portal wires state.

### Component 4: Portal `ThemeProvider` + root-layout wiring

- `ThemeProvider` (client, in `admin/apps/portal`): holds the current
  `ThemePrefs` (seeded from a server-passed initial value), exposes it + a
  `setPrefs` via context. On change it (a) writes the cookie and (b) sets
  `data-theme` (resolving `system` → matched scheme), `data-accent`,
  `data-font-size` on `document.documentElement` live — no reload. Listens to
  `matchMedia("(prefers-color-scheme)")` changes while in `system` mode.
- Root `layout.tsx` (server): read the cookie, stamp the three `data-*`
  attributes on `<html>` for the initial paint (for `system`, stamp nothing for
  `data-theme` and let the inline script set it), wrap children in
  `ThemeProvider` with the parsed initial prefs, and inject a small **blocking
  inline `<script>`** in `<head>` that, before paint, reads the cookie and (for
  `system`) resolves `prefers-color-scheme` and sets `data-theme`. The script is
  a string constant (no user input interpolated — CSP-safe, contract E).
- `ThemeControls` consumers (the Appearance pages, the header toggle) read/write
  through the provider context.

### Component 5: Appearance surfaces

- **Platform:** `/platform/settings/appearance` (add to the platform Settings
  nav children).
- **Operator (tenant):** the tenant portal has **no settings area today**. Add
  a new route `/(tenant-authed)/settings/appearance/page.tsx` and a "Settings"
  entry to the tenant nav (a top-level nav item pointing at the appearance page
  is enough for v1; the group can grow later).
- **Member:** the member nav has **no Settings group**. Render the appearance
  controls as a section on the existing `/member/profile` page (simplest, no
  new nav item), consistent with how member preferences are reached.
- All three render the shared `ThemeControls` fed by the provider. Each is a
  thin page; no data fetching (prefs come from the cookie/provider).
- The header user menu (all audiences) gains the `ThemeModeToggle`.

## Contracts respected

- **P** — tokens edited canonically then copied; sync check green.
- **Q** — accent presets reference tokens; no literal hex added to component
  code. Part of this work is an audit for pre-existing literal hex in components
  that would break dark mode (should be clean; fix any found in the touched
  files).
- **E** — the pre-paint inline script is a static constant, no
  `dangerouslySetInnerHTML` of user data, no user-controlled HTML.
- Theme-aware: both light and dark are fully styled (the whole point).

## Out of scope

- SACCO logo upload and profile pictures (separate spec; needs file storage).
- Server-side / cross-device preference sync (cookie is per-device by design).
- Per-tenant enforced branding (this is a per-user preference, not an
  org-imposed theme).
- Custom/free accent colors (curated presets only).
- High-contrast / reduced-transparency accessibility modes beyond the standard
  reduced-motion the system already honors (could be a later accent to the set).

## Testing strategy

- **Schema/helpers:** `parseThemeCookie` returns defaults on missing/garbage
  input, round-trips valid prefs, rejects out-of-range enum values (→ default
  for that field).
- **`ThemeControls`:** renders all options, marks the current selection, fires
  `onChange` with the updated field for mode / accent / font-size changes;
  `ThemeModeToggle` cycles correctly.
- **Provider:** applies `data-*` attributes on mount from initial prefs; live
  toggling updates `documentElement`; `system` follows a mocked `matchMedia`.
- **Token sync:** `scripts/check-tokens-sync.sh` passes after the edits.
- **Visual (manual):** dark mode across dashboard, a data table, a form dialog,
  and a status-badge-heavy screen; one non-default accent; the `large` font
  size — confirm no clipped layouts and readable contrast.
- pnpm lint / typecheck / test clean across `@sacco/schemas`, `@sacco/ui`,
  `@sacco/portal`.
