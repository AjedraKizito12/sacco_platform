# Portal v1 Sub-Plan 01: Admin Workspace Bootstrap

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/portal-v1/01-workspace-bootstrap` from `main` before starting.

**Goal:** Scaffold the empty `admin/` pnpm monorepo. After this sub-plan merges, `cd admin && pnpm install` succeeds against an empty workspace, `pnpm typecheck` and `pnpm lint` no-op cleanly, and Turborepo recognises the workspace. **No Next.js app yet, no shadcn, no Prettier, no Husky.** Those land in sub-plans 02 (compose + Makefile + .gitignore) and 03 (Next.js scaffold + Tailwind + tooling).

**Architecture:**
- `admin/` is a self-contained pnpm workspace with two top-level package roots: `apps/*` and `packages/*`. Future apps (`apps/portal` in sub-plan 03) and shared libraries (`packages/ui`, `packages/api-client`, `packages/schemas`) land in those directories.
- Two shared configuration packages ship here: `@sacco/tsconfig` (extended `tsconfig.json` with strict mode + `noUncheckedIndexedAccess` + `exactOptionalPropertyTypes`) and `@sacco/eslint-config` (flat config with React, Tailwind, jsx-a11y plugins). Every downstream package extends these.
- Turborepo orchestrates `build`, `test`, `lint`, `typecheck`, and `dev` pipelines across all packages. Cache lives under `admin/.turbo/`.
- Node 22 LTS is pinned via `admin/.nvmrc`. Auto-install peer deps; strict peer dependencies.

**Tech Stack:** pnpm 9, Turborepo 2, TypeScript 5.6, ESLint 9 (flat config), Node 22 LTS.

**Portal v1 index reference:** `docs/superpowers/plans/2026-06-02-portal-v1-index.md` §Sub-plan 01.

**Prerequisite:** None. This is the first portal sub-plan; the only thing required is that the repository is a git checkout.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `admin/package.json` | Create | Root workspace manifest (private, no dependencies of its own) |
| `admin/pnpm-workspace.yaml` | Create | Declares `apps/*` and `packages/*` as workspaces |
| `admin/turbo.json` | Create | Defines `build`, `test`, `lint`, `typecheck`, `dev` pipelines |
| `admin/.nvmrc` | Create | Pinned Node 22 LTS |
| `admin/.npmrc` | Create | pnpm settings: `auto-install-peers=true`, `strict-peer-dependencies=true` |
| `admin/.gitignore` | Create | `node_modules/`, `.turbo/`, `dist/`, build artefacts (root `.gitignore` updates land in sub-plan 02) |
| `admin/README.md` | Create | One-paragraph orientation: what lives here, how to install, how to run, link to portal v1 index |
| `admin/packages/tsconfig/package.json` | Create | `@sacco/tsconfig` manifest |
| `admin/packages/tsconfig/base.json` | Create | Strict TS base config |
| `admin/packages/tsconfig/nextjs.json` | Create | Next.js-flavoured extension (used by `apps/portal` in sub-plan 03) |
| `admin/packages/tsconfig/library.json` | Create | Library-flavoured extension (used by `packages/ui`, etc.) |
| `admin/packages/eslint-config/package.json` | Create | `@sacco/eslint-config` manifest |
| `admin/packages/eslint-config/index.js` | Create | Flat config with `react`, `tailwindcss`, `jsx-a11y`, TS ESLint |
| `admin/packages/eslint-config/next.js` | Create | Next.js-flavoured extension |

---

## Task 1: Top-level directory + Node pin + npmrc + .gitignore

**Files:**
- Create: `admin/.nvmrc`, `admin/.npmrc`, `admin/.gitignore`, `admin/README.md`

- [ ] **Step 1: Create the `admin/` directory and pin Node**

```bash
mkdir -p admin
echo "22" > admin/.nvmrc
```

- [ ] **Step 2: Write pnpm config**

```ini
# admin/.npmrc
# pnpm settings — applied to every pnpm command run inside admin/.

auto-install-peers=true
strict-peer-dependencies=true
shamefully-hoist=false
# Use the workspace protocol for cross-package deps so updates land via
# `pnpm -r update` without bumping versions explicitly.
prefer-workspace-packages=true
# Lockfile lives in admin/ — not the project root.
package-import-method=hardlink
```

- [ ] **Step 3: Write admin-local `.gitignore`**

The root `.gitignore` gets admin entries appended in sub-plan 02. This file covers admin-internal ignores so a fresh checkout doesn't accidentally commit local artefacts.

```
# admin/.gitignore
# pnpm + Turborepo + Next.js artefacts
node_modules/
.pnpm-store/
.turbo/
dist/
build/
*.log
*.tsbuildinfo

# Next.js (lands in sub-plan 03)
.next/
out/
.vercel/

# Storybook (lands in sub-plan 04)
storybook-static/

# Local env files (root-level .env stays; admin's are local-only)
.env*.local
```

- [ ] **Step 4: Write the README**

```markdown
# SACCO Admin Portal

This directory contains the Next.js 15 admin portal for the SACCO platform.
It's a self-contained pnpm + Turborepo monorepo; nothing here touches the
FastAPI backend code in `/app`.

## Layout

```
admin/
├── apps/
│   └── portal/        # Next.js 15 app (sub-plan 03)
└── packages/
    ├── tsconfig/       # Shared TS config
    ├── eslint-config/  # Shared ESLint config
    ├── ui/             # shadcn-based component library (sub-plan 04)
    ├── api-client/     # OpenAPI-generated client (sub-plan 05)
    └── schemas/        # Zod schemas mirrored from backend (sub-plan 06)
```

## Setup

```bash
nvm use     # picks up .nvmrc → Node 22
pnpm install
pnpm typecheck
pnpm lint
```

## Scripts

All Turborepo pipelines run from `admin/` and parallelise across packages:

- `pnpm dev` — start every dev server
- `pnpm build` — production build
- `pnpm typecheck` — TypeScript no-emit pass
- `pnpm lint` — ESLint across the workspace
- `pnpm test` — Vitest across the workspace

## Reference

- Portal v1 plan index: `../docs/superpowers/plans/2026-06-02-portal-v1-index.md`
- Design system spec: `../docs/sacco-design-system-v2.md`
- Design tokens (canonical): `../docs/tokens.css`
- Hard contracts: `../CLAUDE.md` § "Admin portal contracts"
```

- [ ] **Step 5: Commit**

```bash
git add admin/.nvmrc admin/.npmrc admin/.gitignore admin/README.md
git commit -m "feat(admin): bootstrap workspace directory + Node 22 pin"
```

---

## Task 2: pnpm workspace + root package.json

**Files:**
- Create: `admin/pnpm-workspace.yaml`
- Create: `admin/package.json`

- [ ] **Step 1: Declare workspaces**

```yaml
# admin/pnpm-workspace.yaml
packages:
  - "apps/*"
  - "packages/*"
```

- [ ] **Step 2: Write the root manifest**

```json
{
  "name": "sacco-admin",
  "version": "0.0.0",
  "private": true,
  "description": "SACCO platform admin portal (Next.js 15)",
  "license": "UNLICENSED",
  "engines": {
    "node": ">=22.0.0 <23.0.0",
    "pnpm": ">=9.0.0"
  },
  "packageManager": "pnpm@9.12.0",
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build",
    "test": "turbo run test",
    "lint": "turbo run lint",
    "typecheck": "turbo run typecheck",
    "format": "prettier --write \"**/*.{ts,tsx,js,jsx,json,md,css}\"",
    "clean": "turbo run clean && rm -rf node_modules .turbo"
  },
  "devDependencies": {
    "turbo": "^2.1.0",
    "typescript": "^5.6.2",
    "prettier": "^3.3.3"
  }
}
```

- [ ] **Step 3: Verify pnpm recognises the workspace**

```bash
cd admin
pnpm install
pnpm list -r --depth -1
```
Expected: `pnpm install` succeeds; the listing shows only the root manifest (no other packages exist yet).

- [ ] **Step 4: Commit**

```bash
git add admin/pnpm-workspace.yaml admin/package.json admin/pnpm-lock.yaml
git commit -m "feat(admin): pnpm workspace + root package.json"
```

---

## Task 3: Turborepo configuration

**Files:**
- Create: `admin/turbo.json`

- [ ] **Step 1: Write `turbo.json`**

```json
{
  "$schema": "https://turbo.build/schema.json",
  "ui": "stream",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": [".next/**", "!.next/cache/**", "dist/**", "storybook-static/**"],
      "env": ["NODE_ENV", "NEXT_PUBLIC_*"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    },
    "test": {
      "dependsOn": ["^build"],
      "outputs": ["coverage/**"]
    },
    "lint": {
      "outputs": []
    },
    "typecheck": {
      "dependsOn": ["^build"],
      "outputs": ["*.tsbuildinfo"]
    },
    "clean": {
      "cache": false
    }
  }
}
```

- [ ] **Step 2: Verify Turborepo runs**

```bash
cd admin
pnpm typecheck
```
Expected: Turborepo logs "No tasks were executed as part of this run." (no packages yet). Exit 0.

- [ ] **Step 3: Commit**

```bash
git add admin/turbo.json
git commit -m "feat(admin): turbo.json pipelines (build/test/lint/typecheck/dev)"
```

---

## Task 4: `@sacco/tsconfig` shared package

**Files:**
- Create: `admin/packages/tsconfig/package.json`
- Create: `admin/packages/tsconfig/base.json`
- Create: `admin/packages/tsconfig/nextjs.json`
- Create: `admin/packages/tsconfig/library.json`

- [ ] **Step 1: Create the package manifest**

```bash
mkdir -p admin/packages/tsconfig
```

```json
{
  "name": "@sacco/tsconfig",
  "version": "0.0.0",
  "private": true,
  "license": "UNLICENSED",
  "files": [
    "base.json",
    "nextjs.json",
    "library.json"
  ]
}
```

- [ ] **Step 2: Write the strict base config**

```json
{
  "$schema": "https://json.schemastore.org/tsconfig",
  "display": "Default",
  "compilerOptions": {
    "target": "ES2023",
    "lib": ["ES2023"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "moduleDetection": "force",
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "verbatimModuleSyntax": true,

    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "noImplicitReturns": true,
    "noPropertyAccessFromIndexSignature": true,

    "skipLibCheck": true,
    "incremental": true,

    "forceConsistentCasingInFileNames": true,
    "useDefineForClassFields": true
  },
  "exclude": ["node_modules", "dist", ".next", ".turbo", "build"]
}
```

- [ ] **Step 3: Write the Next.js extension**

```json
{
  "$schema": "https://json.schemastore.org/tsconfig",
  "display": "Next.js",
  "extends": "./base.json",
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["DOM", "DOM.Iterable", "ES2022"],
    "jsx": "preserve",
    "noEmit": true,
    "allowJs": true,
    "plugins": [{ "name": "next" }]
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"]
}
```

- [ ] **Step 4: Write the library extension**

```json
{
  "$schema": "https://json.schemastore.org/tsconfig",
  "display": "Library",
  "extends": "./base.json",
  "compilerOptions": {
    "lib": ["DOM", "DOM.Iterable", "ES2023"],
    "jsx": "react-jsx",
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "rootDir": "./src",
    "outDir": "./dist"
  },
  "include": ["src/**/*"]
}
```

- [ ] **Step 5: Verify**

```bash
cd admin
pnpm install
cat node_modules/@sacco/tsconfig/base.json | head -5
```
Expected: the file resolves via the workspace protocol — pnpm symlinks `packages/tsconfig/` into `node_modules/@sacco/tsconfig/`.

- [ ] **Step 6: Commit**

```bash
git add admin/packages/tsconfig/
git commit -m "feat(admin): @sacco/tsconfig (base / nextjs / library variants)"
```

---

## Task 5: `@sacco/eslint-config` shared package

**Files:**
- Create: `admin/packages/eslint-config/package.json`
- Create: `admin/packages/eslint-config/index.js`
- Create: `admin/packages/eslint-config/next.js`

- [ ] **Step 1: Create the package manifest**

```bash
mkdir -p admin/packages/eslint-config
```

```json
{
  "name": "@sacco/eslint-config",
  "version": "0.0.0",
  "private": true,
  "license": "UNLICENSED",
  "type": "module",
  "main": "./index.js",
  "exports": {
    ".": "./index.js",
    "./next": "./next.js"
  },
  "files": ["index.js", "next.js"],
  "peerDependencies": {
    "eslint": "^9.10.0"
  },
  "dependencies": {
    "@eslint/js": "^9.10.0",
    "@typescript-eslint/eslint-plugin": "^8.5.0",
    "@typescript-eslint/parser": "^8.5.0",
    "eslint-plugin-react": "^7.36.1",
    "eslint-plugin-react-hooks": "^4.6.2",
    "eslint-plugin-jsx-a11y": "^6.10.0",
    "eslint-plugin-tailwindcss": "^3.17.4",
    "globals": "^15.9.0"
  }
}
```

- [ ] **Step 2: Write the base flat config**

```javascript
// admin/packages/eslint-config/index.js
import js from "@eslint/js";
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import tailwind from "eslint-plugin-tailwindcss";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["**/*.{ts,tsx,js,jsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      react: reactPlugin,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y,
      tailwindcss: tailwind,
    },
    settings: {
      react: { version: "detect" },
      tailwindcss: {
        callees: ["clsx", "cn", "cva"],
        config: "apps/portal/tailwind.config.ts",
      },
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      ...reactPlugin.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,

      // React 19 / Next.js 15 — no need for React import in JSX.
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",

      // TypeScript handles unused imports better than the JS rule.
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],

      // Discourage `dangerouslySetInnerHTML` — CLAUDE.md hard contract.
      "react/no-danger": "error",

      // Tailwind: enforce class order + warn on unknown classes.
      "tailwindcss/classnames-order": "warn",
      "tailwindcss/no-custom-classname": "off",
    },
  },
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/.next/**",
      "**/.turbo/**",
      "**/storybook-static/**",
      "**/coverage/**",
    ],
  },
];
```

- [ ] **Step 3: Write the Next.js extension**

```javascript
// admin/packages/eslint-config/next.js
import base from "./index.js";

// Lazily imported only by apps/portal so libraries don't pull Next in.
import nextPlugin from "@next/eslint-plugin-next";

export default [
  ...base,
  {
    files: ["**/*.{ts,tsx,js,jsx}"],
    plugins: { "@next/next": nextPlugin },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs["core-web-vitals"].rules,
    },
  },
];
```

Note: `@next/eslint-plugin-next` is not declared as a dependency here — it's a peer of `@sacco/eslint-config/next`. `apps/portal` (sub-plan 03) will add it as a direct dependency.

- [ ] **Step 4: Install + verify it resolves**

```bash
cd admin
pnpm install
node -e "import('@sacco/eslint-config').then(m => console.log('config keys:', Object.keys(m.default[0])))"
```
Expected: prints `config keys: [ 'rules' ]` or similar — proves the export resolves via the workspace protocol.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/eslint-config/ admin/pnpm-lock.yaml
git commit -m "feat(admin): @sacco/eslint-config (base + Next.js variant)"
```

---

## Task 6: Final verification

- [ ] **Step 1: Fresh install + Turborepo pipelines**

```bash
cd admin
rm -rf node_modules
pnpm install
pnpm typecheck
pnpm lint
```
Expected:
- `pnpm install`: succeeds, generates `pnpm-lock.yaml`
- `pnpm typecheck`: "No tasks were executed as part of this run." (no packages with a typecheck script yet) — exit 0
- `pnpm lint`: same — exit 0

- [ ] **Step 2: Sanity-check directory shape**

```bash
tree admin -L 3 -I node_modules
```
Expected output (approx):

```
admin
├── .gitignore
├── .npmrc
├── .nvmrc
├── README.md
├── package.json
├── packages
│   ├── eslint-config
│   │   ├── index.js
│   │   ├── next.js
│   │   └── package.json
│   └── tsconfig
│       ├── base.json
│       ├── library.json
│       ├── nextjs.json
│       └── package.json
├── pnpm-lock.yaml
├── pnpm-workspace.yaml
└── turbo.json
```

- [ ] **Step 3: Confirm no untracked files**

```bash
cd ..  # back to repo root
git status admin/
```
Expected: clean (all admin files committed in earlier tasks).

- [ ] **Step 4: PR**

```bash
git push -u origin feat/portal-v1/01-workspace-bootstrap
gh pr create --title "feat(admin): bootstrap pnpm + Turborepo workspace" --body "$(cat <<'EOF'
## Summary
- New top-level `admin/` directory, self-contained from the backend
- pnpm 9 workspace with `apps/*` and `packages/*` package roots
- Turborepo 2 pipelines: build, dev, test, lint, typecheck
- Node 22 LTS pinned via `.nvmrc`
- Shared config packages:
  - `@sacco/tsconfig` (base, nextjs, library variants — strict mode, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`)
  - `@sacco/eslint-config` (flat config with React, Tailwind, jsx-a11y, TS ESLint; `react/no-danger` enforced per CLAUDE.md)
- `admin/README.md` orients newcomers and links to design system + plan index

## Out of scope
- Next.js app scaffold (sub-plan 03)
- Tailwind + tokens.css copy (sub-plan 03/04)
- Prettier + Husky + lint-staged (sub-plan 03)
- Root-level `docker-compose.yml` + `Makefile` integration (sub-plan 02)
- Root `.gitignore` admin entries (sub-plan 02)

## Test plan
- [ ] `cd admin && pnpm install` succeeds on a clean checkout
- [ ] `pnpm typecheck` exits 0 (no packages yet)
- [ ] `pnpm lint` exits 0 (no packages yet)
- [ ] Turborepo recognises the workspace
- [ ] `node -e "import('@sacco/eslint-config').then(m => console.log(Object.keys(m.default[0])))"` resolves via the workspace protocol

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `admin/.nvmrc` pins Node 22 LTS
- [ ] `admin/.npmrc` enables auto-install-peers and strict-peer-dependencies
- [ ] `admin/pnpm-workspace.yaml` declares `apps/*` and `packages/*`
- [ ] `admin/package.json` is private with Turborepo scripts
- [ ] `admin/turbo.json` defines five pipelines (build, dev, test, lint, typecheck)
- [ ] `@sacco/tsconfig` ships base + nextjs + library variants with strict mode
- [ ] `@sacco/eslint-config` ships base + next flat configs with React/Tailwind/jsx-a11y plugins and `react/no-danger` rule
- [ ] `pnpm install` succeeds
- [ ] `pnpm typecheck` and `pnpm lint` exit 0
- [ ] PR opened, CI green (CI for the admin workspace lands in sub-plan 39 — for now, a green local run is sufficient)

## Notes for the executing subagent

- **Do not** create `apps/portal/` here. That's sub-plan 03. The empty workspace is the entire deliverable.
- **Do not** add Prettier configuration or Husky hooks. Both land in sub-plan 03.
- **Do not** install React, Next.js, shadcn, Tailwind, or any other runtime dependency. The only top-level dev deps are `turbo`, `typescript`, `prettier` (declared but not configured yet).
- **Do not** modify the root `.gitignore`, `docker-compose.yml`, `Makefile`, or `CLAUDE.md` in this sub-plan. Those changes belong to sub-plans 02 and 03.
- pnpm version is pinned via `packageManager` in the root `package.json` (Corepack will install the right version on `pnpm install`). If the executor's machine doesn't have Corepack, run `corepack enable` first.
- The `eslint-plugin-tailwindcss` `config` setting references `apps/portal/tailwind.config.ts` even though that file doesn't exist yet. ESLint won't error on the missing file until Tailwind classes are linted (no JSX yet); the path is forward-looking for sub-plan 03 to consume.
- The `eslint-plugin-react-hooks` package may not yet have an ESM-only release compatible with ESLint 9 flat config. If `pnpm install` reports a peer warning, that's expected — the rules still apply at lint time. Do not pin to an older version to silence the warning.
- The library `tsconfig` sets `rootDir`/`outDir` — packages that use `dts-bundle-generator` or similar may need to override these. Sub-plan 04 (`packages/ui`) is the first consumer and will declare any necessary overrides.
- If `pnpm install` flags a workspace cycle, the most likely cause is a self-reference inside one of the new package manifests. Remove the offending dependency entry; cross-package references in the workspace use the `workspace:*` protocol, never the package's own name.
- If `make ci` runs the backend test suite and fails because of changes outside `admin/`, that's not in scope for this sub-plan. Stop and surface — sub-plan 01 should be a pure addition.
