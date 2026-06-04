# Portal v1 Sub-Plan 03: Next.js 15 App Scaffold

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/portal-v1/03-nextjs-scaffold` from `main` (or rebase on top of sub-plans 01 + 02).

**Goal:** Land a working Next.js 15 + React 19 + Tailwind v4 app at `admin/apps/portal/` that boots, serves a placeholder home page, ships a strict CSP header, lints clean against `@sacco/eslint-config`, and type-checks clean against `@sacco/tsconfig`. Workspace-level Prettier + Husky + lint-staged block bad commits. CLAUDE.md is updated to reflect the real stack and the full set of Admin portal contracts.

**Architecture:**
- `admin/apps/portal/` is a Next.js 15 App Router project. `app/layout.tsx` is the only root layout (no auth shell yet — that's sub-plan 08). `app/page.tsx` renders a single placeholder card so the dev server has something to show.
- Tailwind v4 is configured **without a JS config file** for runtime — tokens live entirely in CSS via `@theme inline {}`. A minimal `tailwind.config.ts` exists ONLY so `eslint-plugin-tailwindcss` can locate it; runtime Tailwind ignores it.
- The placeholder tokens in `app/globals.css` use the design system's primitives but are intentionally a small subset. Sub-plan 04 copies `docs/tokens.css` into `packages/ui/src/tokens.css` and the portal switches to consuming it from there.
- `next.config.mjs` sets `output: "standalone"` and emits a strict default CSP via the `headers()` function. The CSP is `default-src 'self'` plus the minimal exceptions Next.js dev mode needs; production tightens further via the middleware in sub-plan 07.
- Prettier configuration lives at the workspace root (`admin/.prettierrc.json` + `.prettierignore`) so every package shares one source of truth. `prettier-plugin-tailwindcss` sorts class lists deterministically.
- Husky 9 hooks live at `admin/.husky/`. Git's `core.hooksPath` is set to `admin/.husky` so the hooks fire for all commits in the repo; Python-only commits exit 0 because lint-staged path globs don't match.

**Tech Stack:** Next.js 15, React 19, Tailwind v4, ESLint 9 flat config, Prettier 3, Husky 9, lint-staged 15.

**Portal v1 index reference:** `docs/superpowers/plans/2026-06-02-portal-v1-index.md` §Sub-plan 03.

**Required reading:** `docs/sacco-design-system-v2.md` §1–7 (typography, color, layout, spacing) and Portal v1 index §3 (hard contracts).

**Prerequisite:** **Sub-plans 01 and 02 must be merged** (or rebased onto). This sub-plan depends on the `@sacco/tsconfig`, `@sacco/eslint-config`, and the `admin-*` Makefile targets.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `admin/apps/portal/package.json` | Create | App manifest — Next.js 15, React 19, Tailwind v4, ESLint plugin |
| `admin/apps/portal/tsconfig.json` | Create | Extends `@sacco/tsconfig/nextjs.json` |
| `admin/apps/portal/next.config.mjs` | Create | `output: "standalone"`, strict CSP headers, transpilePackages |
| `admin/apps/portal/next-env.d.ts` | Create | Standard Next.js types shim |
| `admin/apps/portal/eslint.config.mjs` | Create | Extends `@sacco/eslint-config/next` |
| `admin/apps/portal/tailwind.config.ts` | Create | Minimal config — present only for `eslint-plugin-tailwindcss` |
| `admin/apps/portal/postcss.config.mjs` | Create | Tailwind v4 PostCSS plugin |
| `admin/apps/portal/app/layout.tsx` | Create | Root layout — `<html lang="en">`, font loading, CSS import |
| `admin/apps/portal/app/page.tsx` | Create | Placeholder home page |
| `admin/apps/portal/app/globals.css` | Create | Tailwind v4 import + `@theme inline` placeholder tokens |
| `admin/.prettierrc.json` | Create | Prettier config with `prettier-plugin-tailwindcss` |
| `admin/.prettierignore` | Create | Excludes build outputs |
| `admin/.husky/pre-commit` | Create | Runs `cd admin && pnpm exec lint-staged` |
| `admin/package.json` | Modify | Add `prepare`, `format`, lint-staged config |
| `CLAUDE.md` | Modify | Phase 2 stack (Next.js 14 → 15 + React 19); replace the Admin portal contracts subsection with the full A–O set |

---

## Task 1: Next.js app skeleton

**Files:**
- Create: `admin/apps/portal/package.json`
- Create: `admin/apps/portal/tsconfig.json`
- Create: `admin/apps/portal/next-env.d.ts`
- Create: `admin/apps/portal/next.config.mjs`
- Create: `admin/apps/portal/tailwind.config.ts`
- Create: `admin/apps/portal/postcss.config.mjs`
- Create: `admin/apps/portal/eslint.config.mjs`

- [ ] **Step 1: Create the directory and package manifest**

```bash
mkdir -p admin/apps/portal/app admin/apps/portal/public
```

```json
{
  "name": "@sacco/portal",
  "version": "0.0.0",
  "private": true,
  "license": "UNLICENSED",
  "type": "module",
  "scripts": {
    "dev": "next dev -p 3000",
    "build": "next build",
    "start": "next start -p 3000",
    "lint": "eslint . --max-warnings=0",
    "typecheck": "tsc --noEmit",
    "clean": "rm -rf .next .turbo"
  },
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@next/eslint-plugin-next": "^15.0.0",
    "@sacco/eslint-config": "workspace:*",
    "@sacco/tsconfig": "workspace:*",
    "@tailwindcss/postcss": "^4.0.0-beta.3",
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "eslint": "^9.10.0",
    "postcss": "^8.4.47",
    "tailwindcss": "^4.0.0-beta.3",
    "typescript": "^5.6.2"
  }
}
```

- [ ] **Step 2: Write the TypeScript config**

```json
{
  "extends": "@sacco/tsconfig/nextjs.json",
  "include": [
    "next-env.d.ts",
    "**/*.ts",
    "**/*.tsx",
    ".next/types/**/*.ts"
  ],
  "exclude": ["node_modules", ".next", ".turbo"]
}
```

- [ ] **Step 3: Write the Next.js types shim**

```typescript
/// <reference types="next" />
/// <reference types="next/image-types/global" />

// NOTE: This file should not be edited
// see https://nextjs.org/docs/app/api-reference/config/typescript for more information.
```

- [ ] **Step 4: Write `next.config.mjs` with strict CSP**

```javascript
/** @type {import('next').NextConfig} */
const cspDirectives = {
  "default-src": ["'self'"],
  // Next.js dev needs unsafe-eval for HMR; production drops it via the
  // middleware in sub-plan 07. unsafe-inline is required for streaming SSR
  // bootstrap until we wire nonces (also sub-plan 07).
  "script-src": ["'self'", "'unsafe-eval'", "'unsafe-inline'"],
  "style-src": ["'self'", "'unsafe-inline'"],
  "img-src": ["'self'", "data:", "blob:"],
  "font-src": ["'self'"],
  "connect-src": [
    "'self'",
    // Backend API. Sub-plan 05 reads this from NEXT_PUBLIC_API_BASE_URL and
    // we'd ideally template it in, but headers() runs at build time. Keep
    // permissive in dev; the production reverse-proxy enforces tighter
    // origin policy.
    "http://localhost:8001",
    "http://localhost:8000",
    "ws://localhost:3000",
  ],
  "frame-ancestors": ["'none'"],
  "form-action": ["'self'"],
  "base-uri": ["'self'"],
  "object-src": ["'none'"],
};

const cspString = Object.entries(cspDirectives)
  .map(([directive, values]) => `${directive} ${values.join(" ")}`)
  .join("; ");

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  // Library packages from the workspace must be transpiled by Next so
  // their TypeScript / ESM exports work without pre-built dist/ output.
  transpilePackages: ["@sacco/ui", "@sacco/api-client", "@sacco/schemas"],
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: cspString },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
```

- [ ] **Step 5: Write the minimal Tailwind config**

```typescript
import type { Config } from "tailwindcss";

// Tailwind v4 uses CSS-first config — see app/globals.css @theme block.
// This file exists ONLY so eslint-plugin-tailwindcss can resolve a path.
const config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
} satisfies Config;

export default config;
```

- [ ] **Step 6: PostCSS config (Tailwind v4 plugin)**

```javascript
/** @type {import('postcss-load-config').Config} */
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
```

- [ ] **Step 7: Flat ESLint config**

```javascript
import nextConfig from "@sacco/eslint-config/next";

export default [
  ...nextConfig,
  {
    settings: {
      tailwindcss: {
        config: "./tailwind.config.ts",
      },
    },
    rules: {
      // Next.js 15 streams the root layout — we can opt out of the
      // explicit `metadata` export rule per page.
      "@next/next/no-html-link-for-pages": "off",
    },
  },
  {
    ignores: ["node_modules", ".next", ".turbo", "next-env.d.ts"],
  },
];
```

- [ ] **Step 8: Commit**

```bash
git add admin/apps/portal/package.json \
        admin/apps/portal/tsconfig.json \
        admin/apps/portal/next-env.d.ts \
        admin/apps/portal/next.config.mjs \
        admin/apps/portal/tailwind.config.ts \
        admin/apps/portal/postcss.config.mjs \
        admin/apps/portal/eslint.config.mjs
git commit -m "feat(portal): Next.js 15 + React 19 app skeleton (configs)"
```

---

## Task 2: App Router pages + Tailwind v4 globals

**Files:**
- Create: `admin/apps/portal/app/layout.tsx`
- Create: `admin/apps/portal/app/page.tsx`
- Create: `admin/apps/portal/app/globals.css`

- [ ] **Step 1: Write `app/globals.css` with placeholder tokens**

The real tokens.css lands in sub-plan 04. This file declares the minimum tokens the placeholder layout uses; sub-plan 04 will replace it entirely.

```css
@import "tailwindcss";

/* Placeholder tokens. Full set lands in sub-plan 04 via the copy of
 * docs/tokens.css into packages/ui/src/tokens.css.
 * Naming follows the canonical token file so the eventual switch is a
 * find-and-replace, not a refactor. */
@theme inline {
  --color-surface-base: #f8f8f8;
  --color-surface-elevated: #ffffff;
  --color-text-primary: #2b2b2b;
  --color-text-secondary: #5b5b5b;
  --color-border-subtle: #ededed;
  --color-primary-800: #1f1f1f;

  --font-sans:
    "Inter", system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue",
    Arial, sans-serif;

  --text-display: 48px;
  --text-h1: 36px;
  --text-h2: 30px;
  --text-h3: 24px;
  --text-h4: 20px;
  --text-h5: 18px;
  --text-body-lg: 16px;
  --text-body: 14px;
  --text-small: 12px;

  --radius-card: 18px;
  --radius-md: 12px;

  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

html {
  -webkit-text-size-adjust: 100%;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

body {
  font-family: var(--font-sans);
  font-size: var(--text-body);
  line-height: 1.5;
  color: var(--color-text-primary);
  background-color: var(--color-surface-base);
  margin: 0;
}

.font-tabular {
  font-feature-settings:
    "tnum" 1,
    "lnum" 1;
  font-variant-numeric: tabular-nums lining-nums;
}
```

- [ ] **Step 2: Write the root layout**

```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";

import "./globals.css";

// Inter is the fallback in the design system's font stack
// (General Sans → Inter → system-ui). Sub-plan 04 swaps to a real
// General Sans @font-face declaration via Fontshare or self-hosted files.
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SACCO Admin Portal",
  description: "Operational back-office for the SACCO platform",
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
  },
  robots: {
    index: false,
    follow: false,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 3: Write the placeholder home page**

```tsx
export default function Home() {
  return (
    <main className="mx-auto grid min-h-screen max-w-3xl place-items-center p-8">
      <div
        className="w-full rounded-[18px] border border-[var(--color-border-subtle)] bg-[var(--color-surface-elevated)] p-8 shadow-sm"
        style={{ boxShadow: "var(--shadow-sm)" }}
      >
        <p
          className="mb-2 text-xs font-medium uppercase tracking-wider"
          style={{ color: "var(--color-text-secondary)" }}
        >
          Portal v1 — sub-plan 03
        </p>
        <h1
          className="mb-3 text-3xl font-bold leading-tight"
          style={{ color: "var(--color-text-primary)" }}
        >
          SACCO Admin Portal
        </h1>
        <p
          className="mb-6 text-base"
          style={{ color: "var(--color-text-secondary)" }}
        >
          Next.js 15 + React 19 bootstrap successful. The auth shell, design
          system, and feature modules land in the sub-plans that follow.
        </p>
        <p className="font-tabular text-sm text-[var(--color-text-secondary)]">
          Bootstrap timestamp: <span suppressHydrationWarning>{new Date().toISOString()}</span>
        </p>
      </div>
    </main>
  );
}
```

- [ ] **Step 4: Install deps and verify dev server**

```bash
make admin-install
make admin-typecheck
make admin-lint
make admin-dev &
DEV_PID=$!
sleep 8
curl -sI http://localhost:3000 | head -5
curl -sI http://localhost:3000 | grep -i 'content-security-policy'
kill $DEV_PID 2>/dev/null || true
```
Expected: `HTTP/1.1 200 OK`; `Content-Security-Policy` header present.

- [ ] **Step 5: Commit**

```bash
git add admin/apps/portal/app/
git commit -m "feat(portal): root layout + placeholder home + Tailwind v4 globals"
```

---

## Task 3: Workspace-level Prettier

**Files:**
- Create: `admin/.prettierrc.json`
- Create: `admin/.prettierignore`
- Modify: `admin/package.json`

- [ ] **Step 1: Write the Prettier config**

```json
{
  "semi": true,
  "singleQuote": false,
  "trailingComma": "all",
  "tabWidth": 2,
  "printWidth": 100,
  "arrowParens": "always",
  "plugins": ["prettier-plugin-tailwindcss"],
  "tailwindFunctions": ["clsx", "cn", "cva"]
}
```

- [ ] **Step 2: Write `.prettierignore`**

```
node_modules/
.next/
.turbo/
dist/
build/
storybook-static/
coverage/
pnpm-lock.yaml
*.tsbuildinfo
```

- [ ] **Step 3: Add `prettier-plugin-tailwindcss` to the root manifest**

In `admin/package.json`, extend `devDependencies`:

```json
{
  "devDependencies": {
    "turbo": "^2.1.0",
    "typescript": "^5.6.2",
    "prettier": "^3.3.3",
    "prettier-plugin-tailwindcss": "^0.6.6"
  }
}
```

- [ ] **Step 4: Run Prettier across the workspace**

```bash
make admin-install
cd admin
pnpm format
git diff --stat
```
Expected: any formatting differences land in a single commit. If `pnpm format` rewrites your earlier files, that's normal — accept the changes.

- [ ] **Step 5: Commit**

```bash
git add admin/.prettierrc.json admin/.prettierignore admin/package.json admin/pnpm-lock.yaml
# Include any reformatted files from Step 4
git add -u admin/
git commit -m "feat(admin): workspace-level Prettier + prettier-plugin-tailwindcss"
```

---

## Task 4: Husky + lint-staged

**Files:**
- Modify: `admin/package.json` (add `prepare` script + lint-staged config + devDeps)
- Create: `admin/.husky/pre-commit`

- [ ] **Step 1: Add deps + scripts + lint-staged config to `admin/package.json`**

Extend `devDependencies`:

```json
"husky": "^9.1.5",
"lint-staged": "^15.2.10"
```

Add to the top-level object (alongside `scripts`):

```json
"lint-staged": {
  "*.{ts,tsx,js,jsx}": [
    "eslint --fix --max-warnings=0",
    "prettier --write"
  ],
  "*.{json,md,css}": [
    "prettier --write"
  ]
}
```

Extend `scripts`:

```json
"prepare": "husky || true"
```

- [ ] **Step 2: Install + run Husky init**

```bash
cd admin
pnpm install
pnpm exec husky init   # creates admin/.husky/pre-commit (default content)
```

- [ ] **Step 3: Overwrite the hook with the lint-staged invocation**

```bash
#!/usr/bin/env sh
# admin/.husky/pre-commit — runs on every commit.
# If no admin files are staged, lint-staged exits 0 (Python-only commits pass).
cd "$(dirname "$0")/.."
pnpm exec lint-staged
```

Make it executable:

```bash
chmod +x admin/.husky/pre-commit
```

- [ ] **Step 4: Point Git at the Husky directory**

```bash
git config core.hooksPath admin/.husky
```

NOTE: `core.hooksPath` is a per-clone setting (it lives in `.git/config`, which is gitignored). Document this in `admin/README.md` so other developers configure it after cloning:

Append to `admin/README.md`:

```markdown
## Git hooks

This workspace uses Husky 9 for pre-commit hooks. After cloning the
repo, point Git at the workspace's `.husky` directory once:

```bash
git config core.hooksPath admin/.husky
```

The `prepare` script (run automatically by `pnpm install`) takes care of
keeping the hooks executable.
```

- [ ] **Step 5: Verify the hook blocks bad commits**

```bash
cd admin/apps/portal
echo 'export const lint = "warn-me" // unused-var' > app/_lint-test.tsx
cd ../../../
git add admin/apps/portal/app/_lint-test.tsx
git commit -m "test: should be blocked"
```
Expected: the commit fails because lint-staged runs ESLint and the unused export triggers `@typescript-eslint/no-unused-vars`.

Clean up:

```bash
git restore --staged admin/apps/portal/app/_lint-test.tsx
rm admin/apps/portal/app/_lint-test.tsx
```

- [ ] **Step 6: Commit**

```bash
git add admin/package.json admin/.husky/pre-commit admin/README.md admin/pnpm-lock.yaml
git commit -m "feat(admin): Husky 9 + lint-staged pre-commit hook"
```

---

## Task 5: CLAUDE.md updates

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the Phase 2 stack line**

Find the line:

```markdown
- **Stack**: Next.js 14 App Router, TypeScript, Tailwind + shadcn/ui, Playwright e2e.
```

Replace with:

```markdown
- **Stack**: Next.js 15 App Router + React 19, TypeScript strict (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`), Tailwind v4 + shadcn/ui, Playwright e2e.
```

- [ ] **Step 2: Replace the Admin portal contracts subsection**

Find `### Admin portal contracts (do not violate — add to this section as P2 is built)`. Replace that subsection (the heading line + the five existing bullets) with the full A–O contracts from Portal v1 index §3:

```markdown
### Admin portal contracts (do not violate)

A. The portal is a CLIENT of the existing FastAPI. No business logic.
B. **Zero new API endpoints in Phase 2.** All backend additions ship in Phase 1.7. If a sub-plan thinks it needs a new endpoint, stop and surface.
C. Access token in memory. Refresh token in httpOnly Secure SameSite=Strict cookie. Never `localStorage`, never `sessionStorage`, never plain cookies.
D. UI permission gating is UX only. API enforces.
E. Strict CSP. No `dangerouslySetInnerHTML`. No user-controlled HTML rendering.
F. Password reset tokens displayed in one-time modal (until Phase 3 email is wired). Never in URLs, query strings, or logs.
G. Subscription-gate responses: 402 → "Subscription past due — payment required" screen with link to billing; 403 (from gate) → "Account suspended — contact platform admin". Platform admin context is NOT gated.
H. Money via `<Money amount currency />`. Dates via `<FormattedDate>` / `<FormattedDateTime>` / `<AuditTimestamp>` / `<RelativeTime>`. Never raw `toLocaleString`.
I. All tables: TanStack Table via `@sacco/ui` DataTable. Server-side pagination, sort, filter. URL state via nuqs.
J. All forms: React Hook Form + Zod. Schemas in `@sacco/schemas`.
K. Maker-checker UI patterns: action buttons labeled "Request X" not "X" when they create approval requests; confirm dialog explicitly states "This creates an approval request, not executes"; pending-approval banner on records with open approvals; approval inbox shows quorum ("1 of 2").
L. `Idempotency-Key` auto-injected on all POST/PUT/PATCH/DELETE by the API client (UUID per user intent — same UUID across retries of the same form submission).
M. No client-side data fetching for initial render. Server components fetch via the typed client; client components mutate via TanStack Query.
N. Do NOT modify anything outside `admin/` except: `docker-compose.yml` (add admin service), `Makefile` (add `admin-*` targets), `CLAUDE.md` (append portal subsection, update Phase 2 stack to "Next.js 15"), `.gitignore` (admin entries). Backend code, alembic, docker/, scripts/, tests/, app/ stay untouched.
O. Notification bell renders empty state ("Notifications coming soon") until Phase 3 ships. Bell component accepts the future Phase 3 event-feed shape but is fed null/empty in v1.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): Phase 2 stack (Next.js 15 + React 19); full Admin portal contracts (A–O)"
```

---

## Task 6: Final verification

- [ ] **Step 1: Clean install + every pipeline**

```bash
cd admin
rm -rf node_modules .turbo
pnpm install
pnpm typecheck
pnpm lint
pnpm build
```
Expected:
- `pnpm install`: succeeds, `pnpm-lock.yaml` updated
- `pnpm typecheck`: green
- `pnpm lint`: green, zero warnings
- `pnpm build`: produces `.next/standalone/` output

- [ ] **Step 2: Dev server + CSP header smoke**

```bash
make admin-dev &
DEV_PID=$!
sleep 8
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000
curl -sI http://localhost:3000 | grep -iE '(content-security-policy|x-frame-options|x-content-type-options|referrer-policy)'
kill $DEV_PID 2>/dev/null || true
```
Expected: status `200`; all four security headers present.

- [ ] **Step 3: Visual smoke**

Open `http://localhost:3000` in a browser. Expected: a centred card titled "SACCO Admin Portal" with a "Portal v1 — sub-plan 03" eyebrow tag. Typography uses Inter; the surface is `#ffffff` on a `#f8f8f8` page background.

- [ ] **Step 4: Husky smoke**

Already validated in Task 4 Step 5. Re-run if any commit since then bypassed the hook (e.g., `--no-verify`).

- [ ] **Step 5: PR**

```bash
git push -u origin feat/portal-v1/03-nextjs-scaffold
gh pr create --title "feat(portal): Next.js 15 + React 19 + Tailwind v4 scaffold" --body "$(cat <<'EOF'
## Summary
- New Next.js 15 app at `admin/apps/portal/` using React 19 and the App Router
- Tailwind v4 with CSS-first `@theme inline` config (placeholder tokens; sub-plan 04 copies `docs/tokens.css` into `packages/ui/src/tokens.css`)
- `next.config.mjs` with `output: "standalone"`, strict default CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`
- Inter via `next/font/google` (design system fallback chain; General Sans lands later)
- Workspace-level Prettier + `prettier-plugin-tailwindcss`
- Husky 9 + lint-staged pre-commit (`eslint --fix` + `prettier --write` on staged TS/TSX/JSON/MD/CSS files)
- CLAUDE.md updated: Phase 2 stack now "Next.js 15 + React 19"; Admin portal contracts expanded to the full A–O set from the Portal v1 index

## Out of scope
- `packages/ui` foundation + tokens.css copy (sub-plan 04)
- API client (sub-plan 05)
- Zod schemas (sub-plan 06)
- Auth shell (sub-plan 07)
- App shell (sub-plan 08)

## Test plan
- [ ] `make admin-install && make admin-typecheck && make admin-lint && make admin-build` all green
- [ ] `make admin-dev` serves `/` with 200 and a strict CSP header
- [ ] Husky hook blocks commits containing ESLint errors
- [ ] Browser visual: home page renders the placeholder card cleanly

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `admin/apps/portal/` Next.js 15 + React 19 app exists, builds, runs
- [ ] `next.config.mjs` sets `output: "standalone"` and emits strict CSP + 4 other security headers
- [ ] Tailwind v4 wired via `@tailwindcss/postcss` + `@theme inline` placeholder tokens in `app/globals.css`
- [ ] `apps/portal/tsconfig.json` extends `@sacco/tsconfig/nextjs.json`; `eslint.config.mjs` extends `@sacco/eslint-config/next`
- [ ] Workspace-level Prettier + `prettier-plugin-tailwindcss` in place
- [ ] Husky 9 pre-commit runs lint-staged; verified by attempting (and failing) to commit broken code
- [ ] CLAUDE.md Phase 2 stack flipped to Next.js 15 + React 19
- [ ] CLAUDE.md Admin portal contracts subsection replaced with the full A–O set
- [ ] `make admin-dev` serves `/` 200 with all expected security headers
- [ ] PR opened, CI green (the admin CI workflow lands in sub-plan 39 — for now, a clean local run suffices)

## Notes for the executing subagent

- **Do not** copy `docs/tokens.css` here. That's sub-plan 04. The placeholder tokens in `globals.css` are intentionally a subset and will be discarded in 04.
- **Do not** add shadcn/ui components, Radix primitives, or any UI library beyond the placeholder layout. Those land with `packages/ui` in sub-plan 04.
- **Do not** load General Sans yet. Inter alone is sufficient for the bootstrap; the design system's fallback chain is `General Sans → Inter → system-ui` and Inter is the second fallback. Sub-plan 04 self-hosts General Sans via `@font-face` if licensing allows.
- **Do not** add a middleware.ts file. Auth and tenant context handling land in sub-plan 07. The current CSP is a static header; sub-plan 07 swaps to a nonce-based CSP via middleware.
- **Do not** weaken the CSP. `'unsafe-eval'` is present because Next.js dev mode requires it (HMR). The production middleware (sub-plan 07) strips it and adds nonces. If you find yourself adding `'unsafe-inline'` to `script-src` for production, stop and surface — that's a contract violation (E).
- The `transpilePackages` array in `next.config.mjs` references `@sacco/ui`, `@sacco/api-client`, `@sacco/schemas` even though only `@sacco/ui` will exist after sub-plan 04. Next ignores entries that don't resolve; the list is forward-looking.
- The `connect-src` directive in CSP includes `http://localhost:8001` (the dev API port from sub-plan 02's Makefile default). If the executor's local API runs on a different port, override via a temporary CSP relax during development — do NOT permanently widen the production CSP.
- The `core.hooksPath` setting is per-clone. The `admin/README.md` snippet documents the one-time setup for fresh clones. Do not try to enforce it via a `post-checkout` hook — that's recursive.
- If `pnpm exec husky init` writes a different default hook than what's specified in Task 4 Step 3, OVERWRITE it. Husky 9's default is a no-op header that we replace with the lint-staged invocation.
- Tailwind v4 is currently in beta. If the `@tailwindcss/postcss` version pinned in this sub-plan is broken by the time you execute, bump to the latest beta and document the version in the PR description. Do NOT downgrade to Tailwind v3.
- The placeholder page uses inline `style={{ ... }}` for token-driven values. That's intentional for the bootstrap — `packages/ui` (sub-plan 04) introduces the `@apply`-based component classes that replace these inline styles. Don't refactor early.
