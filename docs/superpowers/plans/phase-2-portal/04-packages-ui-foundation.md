# Portal v1 Sub-Plan 04: `packages/ui` Foundation + Storybook

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/portal-v1/04-packages-ui` from `main` (or rebase on top of sub-plans 01-03).

**Goal:** Stand up `@sacco/ui` — the shared component library that every portal app consumes. After this sub-plan merges, the design system's tokens live as a copy of `docs/tokens.css` inside `packages/ui/src/`, the portal app imports them through the package (not duplicated), seventeen base shadcn components ship with consistent token wiring, five components have Storybook coverage matching the design system spec, and Vitest + React Testing Library smoke tests pass for each shipped component.

**Architecture:**
- `admin/packages/ui/` is a workspace package with a flat ESM export surface (`@sacco/ui` resolves to `src/index.ts`). Next.js's `transpilePackages` (set in sub-plan 03) compiles the TypeScript and Tailwind directives at build time, so no `dist/` pre-build step is needed.
- **Tokens.css ownership policy (locked here):** `docs/tokens.css` at the repo root is the canonical source. `packages/ui/src/tokens.css` is a **byte-identical copy** that the portal consumes. A new CI guard script (`scripts/check-tokens-sync.sh`) compares the two and fails the build if they drift. Editing tokens means editing `docs/tokens.css` and re-copying.
- shadcn/ui components ship as source-controlled TypeScript files under `packages/ui/src/components/`. We don't pull from the shadcn registry at runtime — the components are forked once and live in the workspace. The forks consume the semantic tokens from `tokens.css` (e.g., `var(--color-surface-elevated)` rather than literal hex), so retheming is a tokens.css edit.
- Storybook 8 with the `@storybook/nextjs` framework gives us the executable design system reference per design system §"Living Documentation". The `@storybook/addon-a11y` plugin runs `axe-core` against every story and fails on violations.
- Vitest + React Testing Library smoke tests live alongside each component (`Button.test.tsx` next to `Button.tsx`). Tests assert: renders, accessible name, basic interaction.

**Tech Stack:** shadcn/ui, Radix UI primitives, Tailwind v4, Storybook 8, Vitest 2, React Testing Library 16, Lucide React.

**Portal v1 index reference:** `docs/superpowers/plans/2026-06-02-portal-v1-index.md` §Sub-plan 04.

**Required reading:**
- `docs/sacco-design-system-v2.md` (full — buttons, forms, cards, status badges, motion, focus, icons)
- `docs/tokens.css` (full)
- [shadcn/ui docs](https://ui.shadcn.com) for the v2 CLI

**Prerequisite:** **Sub-plan 03 must be merged** (or rebased onto). This sub-plan depends on `apps/portal` existing and on the placeholder `tokens` in its `globals.css` (which we replace).

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `admin/packages/ui/package.json` | Create | `@sacco/ui` manifest |
| `admin/packages/ui/tsconfig.json` | Create | Extends `@sacco/tsconfig/library.json` |
| `admin/packages/ui/eslint.config.mjs` | Create | Extends `@sacco/eslint-config` |
| `admin/packages/ui/src/tokens.css` | Create | Byte-identical copy of `docs/tokens.css` |
| `admin/packages/ui/src/globals.css` | Create | `@import "tailwindcss"` + tokens import + base resets |
| `admin/packages/ui/src/utils/cn.ts` | Create | shadcn's `cn()` helper (clsx + tailwind-merge) |
| `admin/packages/ui/src/components/Button/Button.tsx` | Create | Button component |
| `admin/packages/ui/src/components/Button/Button.test.tsx` | Create | RTL smoke test |
| `admin/packages/ui/src/components/Button/Button.stories.tsx` | Create | 5 variants × 3 sizes × 4 states |
| `admin/packages/ui/src/components/Input/...` | Create | Input + test + stories |
| `admin/packages/ui/src/components/Card/...` | Create | Card + test + stories (3 variants) |
| `admin/packages/ui/src/components/Badge/...` | Create | Badge + test + stories (8 variants) |
| `admin/packages/ui/src/components/Dialog/...` | Create | Dialog + test + stories |
| `admin/packages/ui/src/components/{Label,Textarea,Select,Checkbox,Radio,Sheet,Popover,DropdownMenu,Tabs,Tooltip,Separator,Toaster}/` | Create | shadcn-forked components + minimal smoke tests (no detailed stories — added when consumed) |
| `admin/packages/ui/src/index.ts` | Create | Re-exports |
| `admin/packages/ui/.storybook/main.ts` | Create | `@storybook/nextjs` framework config |
| `admin/packages/ui/.storybook/preview.ts` | Create | Global decorators + tokens.css import + a11y addon |
| `admin/packages/ui/vitest.config.ts` | Create | Vitest + jsdom |
| `admin/packages/ui/vitest.setup.ts` | Create | `@testing-library/jest-dom` matchers |
| `scripts/check-tokens-sync.sh` | Create | Byte-diff `docs/tokens.css` vs `admin/packages/ui/src/tokens.css` |
| `admin/apps/portal/app/globals.css` | Modify | Strip placeholder; import tokens from `@sacco/ui` |
| `admin/apps/portal/app/page.tsx` | Modify | Render the placeholder using `<Button>` and `<Card>` from `@sacco/ui` so the integration is exercised |
| `admin/apps/portal/package.json` | Modify | Add `@sacco/ui` as a workspace dependency |
| `CLAUDE.md` | Modify | Append the tokens.css ownership policy and the shadcn-fork-vs-registry contract to the Admin portal contracts subsection |

---

## Task 1: Package bootstrap

**Files:**
- Create: `admin/packages/ui/package.json`
- Create: `admin/packages/ui/tsconfig.json`
- Create: `admin/packages/ui/eslint.config.mjs`
- Create: `admin/packages/ui/src/index.ts` (empty stub)

- [ ] **Step 1: Create the package manifest**

```bash
mkdir -p admin/packages/ui/src/components admin/packages/ui/src/utils
```

```json
{
  "name": "@sacco/ui",
  "version": "0.0.0",
  "private": true,
  "license": "UNLICENSED",
  "type": "module",
  "exports": {
    ".": {
      "types": "./src/index.ts",
      "default": "./src/index.ts"
    },
    "./tokens.css": "./src/tokens.css",
    "./globals.css": "./src/globals.css",
    "./components/*": "./src/components/*"
  },
  "scripts": {
    "lint": "eslint . --max-warnings=0",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest",
    "storybook": "storybook dev -p 6006 --no-open",
    "storybook:build": "storybook build",
    "clean": "rm -rf .turbo coverage storybook-static"
  },
  "peerDependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "dependencies": {
    "@radix-ui/react-checkbox": "^1.1.1",
    "@radix-ui/react-dialog": "^1.1.1",
    "@radix-ui/react-dropdown-menu": "^2.1.1",
    "@radix-ui/react-label": "^2.1.0",
    "@radix-ui/react-popover": "^1.1.1",
    "@radix-ui/react-radio-group": "^1.2.0",
    "@radix-ui/react-select": "^2.1.1",
    "@radix-ui/react-separator": "^1.1.0",
    "@radix-ui/react-slot": "^1.1.0",
    "@radix-ui/react-tabs": "^1.1.0",
    "@radix-ui/react-tooltip": "^1.1.2",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.1",
    "lucide-react": "^0.445.0",
    "sonner": "^1.5.0",
    "tailwind-merge": "^2.5.2"
  },
  "devDependencies": {
    "@sacco/eslint-config": "workspace:*",
    "@sacco/tsconfig": "workspace:*",
    "@storybook/addon-a11y": "^8.3.0",
    "@storybook/addon-essentials": "^8.3.0",
    "@storybook/blocks": "^8.3.0",
    "@storybook/nextjs": "^8.3.0",
    "@storybook/react": "^8.3.0",
    "@storybook/test": "^8.3.0",
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.1",
    "eslint": "^9.10.0",
    "jsdom": "^25.0.0",
    "storybook": "^8.3.0",
    "typescript": "^5.6.2",
    "vitest": "^2.1.1"
  }
}
```

- [ ] **Step 2: TypeScript config**

```json
{
  "extends": "@sacco/tsconfig/library.json",
  "compilerOptions": {
    "rootDir": "./src",
    "outDir": "./dist",
    "jsx": "react-jsx",
    "lib": ["DOM", "DOM.Iterable", "ES2023"],
    "types": ["@testing-library/jest-dom"]
  },
  "include": ["src/**/*", "vitest.setup.ts", ".storybook/**/*"],
  "exclude": ["node_modules", "dist", "storybook-static", "coverage"]
}
```

- [ ] **Step 3: ESLint flat config**

```javascript
import baseConfig from "@sacco/eslint-config";

export default [
  ...baseConfig,
  {
    settings: {
      tailwindcss: {
        config: "../../apps/portal/tailwind.config.ts",
      },
    },
  },
  {
    ignores: ["node_modules", "dist", "storybook-static", "coverage"],
  },
];
```

- [ ] **Step 4: Empty re-export stub**

```typescript
// admin/packages/ui/src/index.ts
// Component re-exports land as each component is added in later tasks.
export {};
```

- [ ] **Step 5: Install + verify the package resolves**

```bash
make admin-install
cd admin
node -e "console.log(require.resolve('@sacco/ui/package.json'))"
```
Expected: prints the resolved path (`...packages/ui/package.json`). Proves the workspace protocol is wired.

- [ ] **Step 6: Commit**

```bash
git add admin/packages/ui/package.json \
        admin/packages/ui/tsconfig.json \
        admin/packages/ui/eslint.config.mjs \
        admin/packages/ui/src/index.ts \
        admin/pnpm-lock.yaml
git commit -m "feat(ui): @sacco/ui package skeleton"
```

---

## Task 2: tokens.css copy + sync CI script + ownership policy

**Files:**
- Create: `admin/packages/ui/src/tokens.css` (copy of `docs/tokens.css`)
- Create: `admin/packages/ui/src/globals.css`
- Create: `scripts/check-tokens-sync.sh`
- Modify: `CLAUDE.md` (Admin portal contracts subsection)

- [ ] **Step 1: Copy `docs/tokens.css` into the package**

```bash
cp docs/tokens.css admin/packages/ui/src/tokens.css
```

Do NOT modify the copy. The byte-identical guarantee is the contract.

- [ ] **Step 2: Write the package-level globals.css**

This file is what consuming apps import; it pulls in Tailwind v4 and the tokens.

```css
/* admin/packages/ui/src/globals.css
 * Entry point for tokens + Tailwind v4 base. Consuming apps import this
 * from their root CSS (e.g., admin/apps/portal/app/globals.css).
 */
@import "tailwindcss";
@import "./tokens.css";
```

- [ ] **Step 3: Write the sync check script**

```bash
#!/usr/bin/env bash
# scripts/check-tokens-sync.sh
# Verify admin/packages/ui/src/tokens.css is byte-identical to
# docs/tokens.css. Fails CI if they drift.

set -euo pipefail

CANONICAL="docs/tokens.css"
COPY="admin/packages/ui/src/tokens.css"

if ! [ -f "$CANONICAL" ]; then
  echo "FAIL: canonical tokens file missing: $CANONICAL"
  exit 1
fi
if ! [ -f "$COPY" ]; then
  echo "FAIL: portal copy missing: $COPY"
  exit 1
fi

if ! cmp -s "$CANONICAL" "$COPY"; then
  echo "FAIL: tokens.css is out of sync."
  echo "  Canonical: $CANONICAL"
  echo "  Copy:      $COPY"
  echo ""
  echo "Diff:"
  diff "$CANONICAL" "$COPY" || true
  echo ""
  echo "Fix: edit $CANONICAL only, then run:"
  echo "  cp $CANONICAL $COPY"
  exit 1
fi

echo "tokens.css in sync"
```

Make executable:

```bash
chmod +x scripts/check-tokens-sync.sh
```

Run it once to confirm the copy succeeded:

```bash
./scripts/check-tokens-sync.sh
```
Expected: `tokens.css in sync`.

- [ ] **Step 4: Add the tokens ownership policy to CLAUDE.md**

In `CLAUDE.md`, find the `### Admin portal contracts (do not violate)` subsection (added in sub-plan 03). Append two new bullets at the end:

```markdown
P. Design tokens are owned by `docs/tokens.css` (the canonical source).
   `admin/packages/ui/src/tokens.css` is a byte-identical copy consumed by the
   portal app and Storybook. Editing tokens means editing the canonical file
   and running `cp docs/tokens.css admin/packages/ui/src/tokens.css`. The
   `scripts/check-tokens-sync.sh` script enforces this in CI; PRs that drift
   are rejected.

Q. shadcn/ui components are **forked once** into
   `admin/packages/ui/src/components/`. They are not pulled from the shadcn
   registry at runtime. Forks consume semantic tokens via
   `var(--color-...)` references; literal hex values in component code
   are a contract violation. To add a new shadcn component, fork it from
   the latest registry, replace literal colours with token references,
   and submit as a PR.
```

- [ ] **Step 5: Commit**

```bash
git add docs/tokens.css \
        admin/packages/ui/src/tokens.css \
        admin/packages/ui/src/globals.css \
        scripts/check-tokens-sync.sh \
        CLAUDE.md
git commit -m "feat(ui): tokens.css copy + CI sync script + CLAUDE.md ownership policy"
```

---

## Task 3: `cn()` helper + Storybook bootstrap

**Files:**
- Create: `admin/packages/ui/src/utils/cn.ts`
- Create: `admin/packages/ui/.storybook/main.ts`
- Create: `admin/packages/ui/.storybook/preview.ts`

- [ ] **Step 1: Write the `cn()` helper**

```typescript
// admin/packages/ui/src/utils/cn.ts
// shadcn's standard helper — merges Tailwind classes with conflict resolution.
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 2: Storybook main config**

```typescript
// admin/packages/ui/.storybook/main.ts
import type { StorybookConfig } from "@storybook/nextjs";

const config: StorybookConfig = {
  stories: ["../src/**/*.stories.@(ts|tsx|mdx)"],
  addons: [
    "@storybook/addon-essentials",
    "@storybook/addon-a11y",
  ],
  framework: {
    name: "@storybook/nextjs",
    options: {
      nextConfigPath: "../../apps/portal/next.config.mjs",
    },
  },
  typescript: {
    check: false,
    reactDocgen: "react-docgen-typescript",
  },
  staticDirs: ["../public"],
};

export default config;
```

- [ ] **Step 3: Storybook preview (loads tokens.css globally)**

```typescript
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
```

- [ ] **Step 4: Verify Storybook boots**

```bash
make admin-install
cd admin
pnpm --filter @sacco/ui storybook &
SB_PID=$!
sleep 12
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:6006
kill $SB_PID 2>/dev/null || true
```
Expected: HTTP 200.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/ui/src/utils/cn.ts \
        admin/packages/ui/.storybook/
git commit -m "feat(ui): cn() helper + Storybook 8 with a11y addon"
```

---

## Task 4: Button — first end-to-end component (TDD pattern)

This task establishes the pattern every subsequent component follows. Read it carefully.

**Files:**
- Create: `admin/packages/ui/src/components/Button/Button.test.tsx`
- Create: `admin/packages/ui/src/components/Button/Button.tsx`
- Create: `admin/packages/ui/src/components/Button/Button.stories.tsx`
- Create: `admin/packages/ui/src/components/Button/index.ts`
- Create: `admin/packages/ui/vitest.config.ts`
- Create: `admin/packages/ui/vitest.setup.ts`
- Modify: `admin/packages/ui/src/index.ts` (export Button)

- [ ] **Step 1: Vitest setup**

```typescript
// admin/packages/ui/vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    css: false,
  },
});
```

```typescript
// admin/packages/ui/vitest.setup.ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 2: Write the failing test**

```typescript
// admin/packages/ui/src/components/Button/Button.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "./Button";

describe("Button", () => {
  it("renders with an accessible name from children", () => {
    render(<Button>Save member</Button>);
    expect(
      screen.getByRole("button", { name: "Save member" }),
    ).toBeInTheDocument();
  });

  it("fires onClick when clicked", async () => {
    const user = userEvent.setup();
    let clicks = 0;
    render(<Button onClick={() => (clicks += 1)}>Click</Button>);
    await user.click(screen.getByRole("button"));
    expect(clicks).toBe(1);
  });

  it("respects the disabled prop", async () => {
    const user = userEvent.setup();
    let clicks = 0;
    render(
      <Button disabled onClick={() => (clicks += 1)}>
        Cannot click
      </Button>,
    );
    await user.click(screen.getByRole("button"));
    expect(clicks).toBe(0);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("renders as a child element when asChild is true", () => {
    render(
      <Button asChild>
        <a href="/members">Go to members</a>
      </Button>,
    );
    const link = screen.getByRole("link", { name: "Go to members" });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/members");
  });
});
```

- [ ] **Step 3: Run the test — expected to fail (no Button yet)**

```bash
cd admin
pnpm --filter @sacco/ui test
```
Expected: `Cannot find module './Button'`.

- [ ] **Step 4: Write the Button component**

The design system specifies four variants (Primary, Secondary, Ghost, Destructive) at three sizes (sm/md/lg). We collapse "Primary" into the default variant name `primary`. State styling (hover/active/disabled/focus) is per design system §"Buttons".

```tsx
// admin/packages/ui/src/components/Button/Button.tsx
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "../../utils/cn";

const buttonVariants = cva(
  // Base styles: 40px height, 12px radius, focus-visible ring per tokens
  [
    "inline-flex items-center justify-center gap-2",
    "rounded-[var(--radius-md)] font-medium",
    "transition-colors duration-150",
    "focus-visible:outline-2 focus-visible:outline-offset-2",
    "focus-visible:outline-[var(--border-focus)]",
    "disabled:cursor-not-allowed disabled:opacity-100",
    // Tabular numerals so any numeric label aligns in toolbars
    "[font-feature-settings:'tnum'_1,'lnum'_1]",
  ],
  {
    variants: {
      variant: {
        primary: [
          "bg-[var(--interactive-primary-bg)]",
          "text-[var(--interactive-primary-text)]",
          "hover:bg-[var(--interactive-primary-bg-hover)]",
          "active:bg-[var(--interactive-primary-bg-active)]",
          "disabled:bg-[var(--interactive-primary-bg-disabled)]",
        ],
        secondary: [
          "bg-[var(--interactive-secondary-bg)]",
          "text-[var(--interactive-secondary-text)]",
          "border border-[var(--interactive-secondary-border)]",
          "hover:bg-[var(--interactive-secondary-bg-hover)]",
          "active:bg-[var(--interactive-secondary-bg-active)]",
        ],
        ghost: [
          "bg-transparent",
          "text-[var(--interactive-ghost-text)]",
          "hover:bg-[var(--interactive-ghost-bg-hover)]",
          "hover:text-[var(--interactive-ghost-text-hover)]",
          "active:bg-[var(--interactive-ghost-bg-active)]",
        ],
        destructive: [
          "bg-[var(--interactive-destructive-bg)]",
          "text-[var(--interactive-destructive-text)]",
          "hover:bg-[var(--interactive-destructive-bg-hover)]",
        ],
      },
      size: {
        sm: "h-[var(--height-control-sm)] px-3 text-[13px]",
        md: "h-[var(--height-control)] px-4 text-[var(--text-body)]",
        lg: "h-[var(--height-control-lg)] px-5 text-[15px]",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /**
   * When true, renders as a Radix Slot — clones the single child and
   * applies the button classes to it. Useful for wrapping <Link>.
   */
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
```

```typescript
// admin/packages/ui/src/components/Button/index.ts
export { Button, buttonVariants, type ButtonProps } from "./Button";
```

Update the package root export:

```typescript
// admin/packages/ui/src/index.ts
export * from "./components/Button";
```

- [ ] **Step 5: Run tests — should pass**

```bash
cd admin
pnpm --filter @sacco/ui test
```
Expected: 4 tests pass.

- [ ] **Step 6: Write the stories — 5 variants × 3 sizes × 4 states**

```tsx
// admin/packages/ui/src/components/Button/Button.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { Button } from "./Button";

const meta: Meta<typeof Button> = {
  title: "Primitives/Button",
  component: Button,
  parameters: { layout: "centered" },
  argTypes: {
    variant: {
      control: "select",
      options: ["primary", "secondary", "ghost", "destructive"],
    },
    size: { control: "select", options: ["sm", "md", "lg"] },
    disabled: { control: "boolean" },
    asChild: { control: false },
  },
};
export default meta;

type Story = StoryObj<typeof Button>;

export const Primary: Story = { args: { variant: "primary", children: "Save member" } };
export const Secondary: Story = { args: { variant: "secondary", children: "Cancel" } };
export const Ghost: Story = { args: { variant: "ghost", children: "Filter" } };
export const Destructive: Story = {
  args: { variant: "destructive", children: "Write off loan" },
};

export const SizeSmall: Story = { args: { size: "sm", children: "Small" } };
export const SizeMedium: Story = { args: { size: "md", children: "Medium" } };
export const SizeLarge: Story = { args: { size: "lg", children: "Large" } };

export const StateDefault: Story = { args: { children: "Default" } };
export const StateHover: Story = {
  args: { children: "Hover", className: "hover:!bg-[var(--interactive-primary-bg-hover)]" },
};
export const StateDisabled: Story = { args: { disabled: true, children: "Disabled" } };
export const StateLoading: Story = {
  args: {
    disabled: true,
    children: (
      <>
        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" />
        Saving…
      </>
    ),
  },
};

export const Grid: Story = {
  render: () => (
    <div className="grid grid-cols-4 gap-4">
      {(["primary", "secondary", "ghost", "destructive"] as const).map((variant) => (
        <div key={variant} className="flex flex-col gap-2">
          <Button variant={variant} size="sm">{variant} sm</Button>
          <Button variant={variant} size="md">{variant} md</Button>
          <Button variant={variant} size="lg">{variant} lg</Button>
          <Button variant={variant} disabled>{variant} disabled</Button>
        </div>
      ))}
    </div>
  ),
};
```

- [ ] **Step 7: Verify in Storybook**

```bash
cd admin
pnpm --filter @sacco/ui storybook &
SB_PID=$!
sleep 12
curl -s "http://localhost:6006/index.json" | grep -c "Primitives/Button"
kill $SB_PID 2>/dev/null || true
```
Expected: prints a positive number — stories registered.

- [ ] **Step 8: Commit**

```bash
git add admin/packages/ui/src/components/Button/ \
        admin/packages/ui/src/index.ts \
        admin/packages/ui/vitest.config.ts \
        admin/packages/ui/vitest.setup.ts \
        admin/pnpm-lock.yaml
git commit -m "feat(ui): Button component + variants × sizes × states + stories + tests"
```

---

## Task 5: Input, Label, Textarea

Apply the Task 4 pattern. Each component lives in its own folder with `Component.tsx`, `Component.test.tsx`, `index.ts`, and (where called out by the index) a `Component.stories.tsx`.

**Files:**
- Create: `admin/packages/ui/src/components/{Input,Label,Textarea}/`
- Modify: `admin/packages/ui/src/index.ts`

- [ ] **Step 1: Input — full component + smoke test + design-system states stories**

`admin/packages/ui/src/components/Input/Input.tsx`:

```tsx
import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "../../utils/cn";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
  success?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, error, success, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "h-[var(--height-control)] w-full px-3",
        "rounded-[var(--radius-md)] border bg-[var(--surface-elevated)]",
        "text-[var(--text-body)] text-[var(--text-primary)]",
        "placeholder:text-[var(--text-disabled)]",
        "border-[var(--border-default)]",
        "transition-colors duration-150",
        "hover:border-[var(--border-strong)]",
        "focus-visible:border-[var(--border-focus)] focus-visible:outline-none",
        "focus-visible:shadow-[var(--shadow-focus)]",
        "disabled:cursor-not-allowed disabled:bg-[var(--surface-disabled)]",
        "disabled:text-[var(--text-disabled)]",
        "read-only:bg-[var(--surface-readonly)]",
        "read-only:border-[var(--border-subtle)]",
        error && [
          "border-[var(--border-danger)]",
          "focus-visible:shadow-[var(--shadow-focus-danger)]",
        ],
        success && "border-[var(--border-success)]",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
```

`Input.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Input } from "./Input";

describe("Input", () => {
  it("forwards value typing", async () => {
    const user = userEvent.setup();
    render(<Input aria-label="member-name" />);
    const input = screen.getByLabelText("member-name");
    await user.type(input, "Mary Akello");
    expect(input).toHaveValue("Mary Akello");
  });

  it("applies error styling when error=true", () => {
    render(<Input aria-label="amount" error />);
    expect(screen.getByLabelText("amount").className).toMatch(/border-/);
  });
});
```

`Input.stories.tsx` — cover the seven states from design system §"Forms — States":

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import { Input } from "./Input";

const meta: Meta<typeof Input> = {
  title: "Primitives/Input",
  component: Input,
  parameters: { layout: "padded" },
};
export default meta;

type Story = StoryObj<typeof Input>;

export const Default: Story = { args: { placeholder: "e.g. Mary Akello" } };
export const Hover: Story = { args: { placeholder: "hover state (via :hover)" } };
export const Focus: Story = {
  args: { placeholder: "tab to me", autoFocus: true },
};
export const Disabled: Story = { args: { disabled: true, value: "disabled" } };
export const ReadOnly: Story = {
  args: { readOnly: true, value: "read-only informational" },
};
export const Error: Story = {
  args: { error: true, value: "invalid amount" },
};
export const Success: Story = {
  args: { success: true, value: "available" },
};

export const Grid: Story = {
  render: () => (
    <div className="flex max-w-md flex-col gap-3">
      <Input placeholder="Default" />
      <Input placeholder="Disabled" disabled />
      <Input value="Read-only" readOnly />
      <Input value="Error" error onChange={() => {}} />
      <Input value="Success" success onChange={() => {}} />
    </div>
  ),
};
```

`index.ts`:

```typescript
export { Input, type InputProps } from "./Input";
```

- [ ] **Step 2: Label**

`admin/packages/ui/src/components/Label/Label.tsx`:

```tsx
import * as LabelPrimitive from "@radix-ui/react-label";
import { forwardRef, type ComponentPropsWithoutRef } from "react";
import { cn } from "../../utils/cn";

export interface LabelProps
  extends ComponentPropsWithoutRef<typeof LabelPrimitive.Root> {
  required?: boolean;
}

export const Label = forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  LabelProps
>(({ className, required, children, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(
      "mb-1.5 block text-[13px] font-medium text-[var(--text-tertiary)]",
      "peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
      className,
    )}
    {...props}
  >
    {children}
    {required ? (
      <span className="ml-0.5 text-[var(--text-danger)]" aria-hidden>
        *
      </span>
    ) : null}
  </LabelPrimitive.Root>
));
Label.displayName = "Label";
```

`Label.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Label } from "./Label";

describe("Label", () => {
  it("renders text", () => {
    render(<Label>Member name</Label>);
    expect(screen.getByText("Member name")).toBeInTheDocument();
  });
  it("renders the required asterisk when required", () => {
    render(<Label required>Email</Label>);
    expect(screen.getByText("*")).toBeInTheDocument();
  });
});
```

`index.ts`:

```typescript
export { Label, type LabelProps } from "./Label";
```

- [ ] **Step 3: Textarea** — mirror Input's structure with `<textarea>` element. Minimum height 96px per design system. Include resize-vertical only. Component, test, index.

```tsx
// admin/packages/ui/src/components/Textarea/Textarea.tsx
import { forwardRef, type TextareaHTMLAttributes } from "react";
import { cn } from "../../utils/cn";

export interface TextareaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, error, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "min-h-[96px] w-full resize-y p-3",
        "rounded-[var(--radius-md)] border bg-[var(--surface-elevated)]",
        "text-[var(--text-body)] text-[var(--text-primary)]",
        "border-[var(--border-default)]",
        "focus-visible:border-[var(--border-focus)] focus-visible:outline-none",
        "focus-visible:shadow-[var(--shadow-focus)]",
        "disabled:cursor-not-allowed disabled:bg-[var(--surface-disabled)]",
        error && "border-[var(--border-danger)]",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";
```

`Textarea.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Textarea } from "./Textarea";

describe("Textarea", () => {
  it("accepts multi-line text", async () => {
    const user = userEvent.setup();
    render(<Textarea aria-label="reason" />);
    const ta = screen.getByLabelText("reason");
    await user.type(ta, "Investigating reported balance issue");
    expect(ta).toHaveValue("Investigating reported balance issue");
  });
});
```

`index.ts`:

```typescript
export { Textarea, type TextareaProps } from "./Textarea";
```

- [ ] **Step 4: Re-export from `src/index.ts`**

```typescript
export * from "./components/Button";
export * from "./components/Input";
export * from "./components/Label";
export * from "./components/Textarea";
```

- [ ] **Step 5: Test + typecheck + lint**

```bash
cd admin
pnpm --filter @sacco/ui test
pnpm --filter @sacco/ui typecheck
pnpm --filter @sacco/ui lint
```
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add admin/packages/ui/src/components/{Input,Label,Textarea}/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): Input + Label + Textarea (with Input states stories)"
```

---

## Task 6: Card + Badge + Separator

**Files:**
- Create: `admin/packages/ui/src/components/{Card,Badge,Separator}/`
- Modify: `admin/packages/ui/src/index.ts`

- [ ] **Step 1: Card — standard, section, KPI sub-components**

Per design system §"Cards", three variants: Standard, Section (with header / body / footer slots), KPI.

```tsx
// admin/packages/ui/src/components/Card/Card.tsx
import {
  forwardRef,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { cn } from "../../utils/cn";

export const Card = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "rounded-[var(--radius-card)] border bg-[var(--surface-elevated)] p-6",
        "border-[var(--border-subtle)] shadow-[var(--shadow-sm)]",
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = "Card";

export const CardHeader = forwardRef<
  HTMLDivElement,
  HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "border-b border-[var(--border-subtle)] px-6 py-5",
      className,
    )}
    {...props}
  />
));
CardHeader.displayName = "CardHeader";

export const CardBody = forwardRef<
  HTMLDivElement,
  HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-6", className)} {...props} />
));
CardBody.displayName = "CardBody";

export const CardFooter = forwardRef<
  HTMLDivElement,
  HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "border-t border-[var(--border-subtle)] px-6 py-4",
      className,
    )}
    {...props}
  />
));
CardFooter.displayName = "CardFooter";

export interface KpiCardProps {
  label: string;
  value: ReactNode;
  trend?: { direction: "up" | "down" | "flat"; label: string };
  className?: string;
}

export function KpiCard({
  label,
  value,
  trend,
  className,
}: KpiCardProps): JSX.Element {
  return (
    <Card className={cn("flex flex-col gap-2 p-6", className)}>
      <p className="text-[13px] font-medium text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="text-[28px] font-semibold text-[var(--text-primary)] [font-feature-settings:'tnum'_1,'lnum'_1]">
        {value}
      </p>
      {trend ? (
        <p
          className={cn(
            "text-[12px]",
            trend.direction === "up" && "text-[var(--text-success)]",
            trend.direction === "down" && "text-[var(--text-danger)]",
            trend.direction === "flat" && "text-[var(--text-tertiary)]",
          )}
        >
          {trend.label}
        </p>
      ) : null}
    </Card>
  );
}
```

`Card.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Card, CardHeader, CardBody, KpiCard } from "./Card";

describe("Card", () => {
  it("renders children", () => {
    render(<Card>hello</Card>);
    expect(screen.getByText("hello")).toBeInTheDocument();
  });
  it("supports header + body composition", () => {
    render(
      <Card>
        <CardHeader>Header</CardHeader>
        <CardBody>Body</CardBody>
      </Card>,
    );
    expect(screen.getByText("Header")).toBeInTheDocument();
    expect(screen.getByText("Body")).toBeInTheDocument();
  });
});

describe("KpiCard", () => {
  it("renders label, value, trend", () => {
    render(
      <KpiCard
        label="Total Members"
        value="1,234"
        trend={{ direction: "up", label: "+5.2% MoM" }}
      />,
    );
    expect(screen.getByText("Total Members")).toBeInTheDocument();
    expect(screen.getByText("1,234")).toBeInTheDocument();
    expect(screen.getByText("+5.2% MoM")).toBeInTheDocument();
  });
});
```

`Card.stories.tsx` — 3 variants per the index requirement:

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import {
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  KpiCard,
} from "./Card";

const meta: Meta<typeof Card> = {
  title: "Surfaces/Card",
  component: Card,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof Card>;

export const Standard: Story = {
  render: () => (
    <Card className="max-w-md">
      <p className="mb-1 text-sm font-medium text-[var(--text-tertiary)]">
        Member ID
      </p>
      <p className="text-base text-[var(--text-primary)]">M-2026-0001</p>
    </Card>
  ),
};

export const Sectioned: Story = {
  render: () => (
    <Card className="max-w-lg p-0">
      <CardHeader>
        <h3 className="text-[18px] font-semibold">Savings account</h3>
      </CardHeader>
      <CardBody>Account #SA-2026-0042 · Current balance UGX 1,234,567</CardBody>
      <CardFooter>Last updated 2 hours ago</CardFooter>
    </Card>
  ),
};

export const KpiTriad: Story = {
  render: () => (
    <div className="grid max-w-3xl grid-cols-3 gap-4">
      <KpiCard
        label="Total Members"
        value="1,234"
        trend={{ direction: "up", label: "+5.2% MoM" }}
      />
      <KpiCard
        label="Outstanding Loans"
        value="UGX 12,345,000"
        trend={{ direction: "down", label: "-1.4% MoM" }}
      />
      <KpiCard
        label="Members in Arrears"
        value="14"
        trend={{ direction: "flat", label: "no change" }}
      />
    </div>
  ),
};
```

`index.ts`:

```typescript
export {
  Card,
  CardHeader,
  CardBody,
  CardFooter,
  KpiCard,
  type KpiCardProps,
} from "./Card";
```

- [ ] **Step 2: Badge — all 8 semantic variants**

```tsx
// admin/packages/ui/src/components/Badge/Badge.tsx
import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "../../utils/cn";

const badgeVariants = cva(
  [
    "inline-flex h-6 items-center gap-1 rounded-[var(--radius-sm)] px-2",
    "text-[12px] font-medium",
    "[font-feature-settings:'tnum'_1,'lnum'_1]",
  ],
  {
    variants: {
      variant: {
        success: "bg-[var(--status-success-bg)] text-[var(--text-success)]",
        warning: "bg-[var(--status-warning-bg)] text-[var(--text-warning)]",
        danger: "bg-[var(--status-danger-bg)] text-[var(--text-danger)]",
        "danger-solid":
          "bg-[var(--status-danger-solid-bg)] text-[var(--status-danger-solid-text)]",
        info: "bg-[var(--status-info-bg)] text-[var(--text-info)]",
        neutral:
          "bg-[var(--status-neutral-bg)] text-[var(--status-neutral-text)]",
        dark: "bg-[var(--status-dark-bg)] text-[var(--status-dark-text)]",
        accent: "bg-[var(--status-accent-bg)] text-[var(--text-accent)]",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  withDot?: boolean;
}

export function Badge({
  className,
  variant,
  withDot,
  children,
  ...props
}: BadgeProps): JSX.Element {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props}>
      {withDot ? (
        <span
          className="h-1.5 w-1.5 rounded-full bg-current"
          aria-hidden
        />
      ) : null}
      {children}
    </span>
  );
}

export { badgeVariants };
```

`Badge.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "./Badge";

describe("Badge", () => {
  it("renders children", () => {
    render(<Badge>Approved</Badge>);
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });
  it("renders the leading dot when withDot=true", () => {
    render(<Badge withDot>Pending</Badge>);
    const span = screen.getByText("Pending");
    expect(span.querySelector("[aria-hidden]")).toBeInTheDocument();
  });
});
```

`Badge.stories.tsx` — all 8 semantic variants:

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import { Badge } from "./Badge";

const meta: Meta<typeof Badge> = {
  title: "Primitives/Badge",
  component: Badge,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof Badge>;

const VARIANTS = [
  "success", "warning", "danger", "danger-solid",
  "info", "neutral", "dark", "accent",
] as const;

export const All: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      {VARIANTS.map((variant) => (
        <Badge key={variant} variant={variant}>
          {variant}
        </Badge>
      ))}
    </div>
  ),
};

export const WithDot: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      {VARIANTS.map((variant) => (
        <Badge key={variant} variant={variant} withDot>
          {variant}
        </Badge>
      ))}
    </div>
  ),
};

export const DomainLoanStatuses: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <Badge variant="neutral">Draft</Badge>
      <Badge variant="info">Submitted</Badge>
      <Badge variant="success">Approved</Badge>
      <Badge variant="warning">Disbursing</Badge>
      <Badge variant="danger-solid">In Arrears</Badge>
      <Badge variant="accent">Restructured</Badge>
      <Badge variant="dark">Closed</Badge>
    </div>
  ),
};
```

`index.ts`:

```typescript
export { Badge, badgeVariants, type BadgeProps } from "./Badge";
```

- [ ] **Step 3: Separator** — Radix-based primitive, no detailed stories (smoke only)

```tsx
// admin/packages/ui/src/components/Separator/Separator.tsx
import * as SeparatorPrimitive from "@radix-ui/react-separator";
import { forwardRef, type ComponentPropsWithoutRef } from "react";
import { cn } from "../../utils/cn";

export const Separator = forwardRef<
  React.ElementRef<typeof SeparatorPrimitive.Root>,
  ComponentPropsWithoutRef<typeof SeparatorPrimitive.Root>
>(
  (
    { className, orientation = "horizontal", decorative = true, ...props },
    ref,
  ) => (
    <SeparatorPrimitive.Root
      ref={ref}
      decorative={decorative}
      orientation={orientation}
      className={cn(
        "bg-[var(--border-subtle)]",
        orientation === "horizontal"
          ? "h-px w-full"
          : "h-full w-px",
        className,
      )}
      {...props}
    />
  ),
);
Separator.displayName = "Separator";
```

`Separator.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Separator } from "./Separator";

describe("Separator", () => {
  it("renders as a horizontal divider by default", () => {
    const { container } = render(<Separator />);
    expect(container.firstChild).toHaveAttribute(
      "data-orientation",
      "horizontal",
    );
  });
});
```

`index.ts`:

```typescript
export { Separator } from "./Separator";
```

- [ ] **Step 4: Update root re-exports + run all tests**

```typescript
// admin/packages/ui/src/index.ts
export * from "./components/Button";
export * from "./components/Input";
export * from "./components/Label";
export * from "./components/Textarea";
export * from "./components/Card";
export * from "./components/Badge";
export * from "./components/Separator";
```

```bash
cd admin
pnpm --filter @sacco/ui test
pnpm --filter @sacco/ui typecheck
```
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/ui/src/components/{Card,Badge,Separator}/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): Card + Badge (8 variants stories) + Separator"
```

---

## Task 7: Dialog (with stories) + Sheet, Popover, Tooltip (smoke only)

**Files:**
- Create: `admin/packages/ui/src/components/{Dialog,Sheet,Popover,Tooltip}/`
- Modify: `admin/packages/ui/src/index.ts`

- [ ] **Step 1: Dialog — Radix-based, with title/description/close**

```tsx
// admin/packages/ui/src/components/Dialog/Dialog.tsx
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import {
  forwardRef,
  type ComponentPropsWithoutRef,
  type HTMLAttributes,
} from "react";
import { cn } from "../../utils/cn";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogPortal = DialogPrimitive.Portal;
export const DialogClose = DialogPrimitive.Close;

export const DialogOverlay = forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-[var(--z-overlay)] bg-black/40",
      "data-[state=open]:animate-in data-[state=open]:fade-in-0",
      "data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
      className,
    )}
    {...props}
  />
));
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName;

export const DialogContent = forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed left-1/2 top-1/2 z-[var(--z-modal)] w-full max-w-lg",
        "-translate-x-1/2 -translate-y-1/2 p-0",
        "rounded-[var(--radius-xl)] bg-[var(--surface-elevated)]",
        "shadow-[var(--shadow-lg)]",
        "data-[state=open]:animate-in data-[state=closed]:animate-out",
        className,
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close
        aria-label="Close"
        className={cn(
          "absolute right-4 top-4 rounded p-1",
          "text-[var(--icon-default)] hover:text-[var(--icon-strong)]",
          "focus-visible:outline-2 focus-visible:outline-[var(--border-focus)]",
        )}
      >
        <X size={16} strokeWidth={1.75} />
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPortal>
));
DialogContent.displayName = DialogPrimitive.Content.displayName;

export function DialogHeader({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "border-b border-[var(--border-subtle)] p-6",
        className,
      )}
      {...props}
    />
  );
}

export function DialogBody({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-6", className)} {...props} />;
}

export function DialogFooter({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center justify-end gap-2",
        "border-t border-[var(--border-subtle)] p-4",
        className,
      )}
      {...props}
    />
  );
}

export const DialogTitle = forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn(
      "text-[var(--text-h4)] font-semibold text-[var(--text-primary)]",
      className,
    )}
    {...props}
  />
));
DialogTitle.displayName = DialogPrimitive.Title.displayName;

export const DialogDescription = forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn(
      "mt-1 text-[var(--text-body)] text-[var(--text-secondary)]",
      className,
    )}
    {...props}
  />
));
DialogDescription.displayName = DialogPrimitive.Description.displayName;
```

`Dialog.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./Dialog";
import { Button } from "../Button";

describe("Dialog", () => {
  it("opens on trigger click and shows title", async () => {
    const user = userEvent.setup();
    render(
      <Dialog>
        <DialogTrigger asChild>
          <Button>Open</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reverse transaction</DialogTitle>
          </DialogHeader>
        </DialogContent>
      </Dialog>,
    );
    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(
      await screen.findByRole("dialog", { name: "Reverse transaction" }),
    ).toBeInTheDocument();
  });
});
```

`Dialog.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from "./Dialog";
import { Button } from "../Button";

const meta: Meta<typeof Dialog> = {
  title: "Overlays/Dialog",
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof Dialog>;

export const ConfirmAction: Story = {
  render: () => (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="destructive">Request reversal</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reverse transaction TXN-2026-0042</DialogTitle>
          <DialogDescription>
            This creates an approval request, not executes. Another
            authorized user must approve before the reversal posts.
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          <p className="text-[var(--text-secondary)]">
            Provide a reason for the reversal so the checker has context.
          </p>
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary">Cancel</Button>
          </DialogClose>
          <Button variant="destructive">Create approval request</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  ),
};
```

`index.ts`:

```typescript
export {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
} from "./Dialog";
```

- [ ] **Step 2: Sheet, Popover, Tooltip — fork from shadcn registry**

These don't get detailed stories in this sub-plan (they're added as consumers appear in later sub-plans). Use the shadcn CLI to fork:

```bash
cd admin/packages/ui
pnpm dlx shadcn@latest add sheet popover tooltip --cwd .
```

For each generated file under `src/components/ui/`:
1. Move it to `src/components/{Sheet,Popover,Tooltip}/Component.tsx`
2. Replace literal hex colours with token references (see CLAUDE.md Q)
3. Add a minimal `Component.test.tsx` that renders + asserts presence
4. Add an `index.ts` that re-exports the named members

Smoke test pattern (e.g., for Sheet):

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Sheet, SheetContent, SheetTrigger } from "./Sheet";

describe("Sheet", () => {
  it("opens on trigger click", async () => {
    const user = userEvent.setup();
    render(
      <Sheet>
        <SheetTrigger>Open</SheetTrigger>
        <SheetContent aria-label="audit details">Audit log</SheetContent>
      </Sheet>,
    );
    await user.click(screen.getByText("Open"));
    expect(
      await screen.findByRole("dialog", { name: "audit details" }),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Update re-exports + verify**

```typescript
// admin/packages/ui/src/index.ts (append)
export * from "./components/Dialog";
export * from "./components/Sheet";
export * from "./components/Popover";
export * from "./components/Tooltip";
```

```bash
cd admin
pnpm --filter @sacco/ui test
pnpm --filter @sacco/ui typecheck
pnpm --filter @sacco/ui lint
```
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add admin/packages/ui/src/components/{Dialog,Sheet,Popover,Tooltip}/ \
        admin/packages/ui/src/index.ts \
        admin/pnpm-lock.yaml
git commit -m "feat(ui): Dialog (with stories) + Sheet + Popover + Tooltip"
```

---

## Task 8: Form primitives (Checkbox, Radio, Select, DropdownMenu, Tabs)

These ship as shadcn forks with consistent token wiring + smoke tests, no detailed stories yet.

**Files:**
- Create: `admin/packages/ui/src/components/{Checkbox,Radio,Select,DropdownMenu,Tabs}/`
- Modify: `admin/packages/ui/src/index.ts`

- [ ] **Step 1: Fork from shadcn**

```bash
cd admin/packages/ui
pnpm dlx shadcn@latest add checkbox radio-group select dropdown-menu tabs --cwd .
```

For each generated file:
1. Move to the right component folder
2. Replace literal hex colours with token references — every `bg-white`, `text-black`, `border-gray-200` etc. becomes a `var(--...)` reference. Cross-reference `docs/tokens.css` for the right semantic token.
3. Add `Component.test.tsx` smoke
4. Add `index.ts`

- [ ] **Step 2: Re-export and run tests**

```typescript
// admin/packages/ui/src/index.ts (append)
export * from "./components/Checkbox";
export * from "./components/Radio";
export * from "./components/Select";
export * from "./components/DropdownMenu";
export * from "./components/Tabs";
```

```bash
cd admin
pnpm --filter @sacco/ui test
pnpm --filter @sacco/ui typecheck
pnpm --filter @sacco/ui lint
```
Expected: green.

- [ ] **Step 3: Commit**

```bash
git add admin/packages/ui/src/components/{Checkbox,Radio,Select,DropdownMenu,Tabs}/ \
        admin/packages/ui/src/index.ts \
        admin/pnpm-lock.yaml
git commit -m "feat(ui): Checkbox + Radio + Select + DropdownMenu + Tabs"
```

---

## Task 9: Toast (sonner) integration

`sonner` is the design system's choice for toasts (bottom-right, success/info/warning/error variants). We wrap it once so consumers always get our defaults.

**Files:**
- Create: `admin/packages/ui/src/components/Toaster/Toaster.tsx`
- Create: `admin/packages/ui/src/components/Toaster/Toaster.test.tsx`
- Create: `admin/packages/ui/src/components/Toaster/index.ts`
- Modify: `admin/packages/ui/src/index.ts`

- [ ] **Step 1: Toaster wrapper**

```tsx
// admin/packages/ui/src/components/Toaster/Toaster.tsx
import { Toaster as SonnerToaster, toast } from "sonner";

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      richColors
      closeButton
      toastOptions={{
        className: "font-sans",
        style: {
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--border-subtle)",
        },
      }}
    />
  );
}

export { toast };
```

```tsx
// admin/packages/ui/src/components/Toaster/Toaster.test.tsx
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Toaster } from "./Toaster";

describe("Toaster", () => {
  it("renders without crashing", () => {
    const { container } = render(<Toaster />);
    expect(container).toBeTruthy();
  });
});
```

```typescript
// admin/packages/ui/src/components/Toaster/index.ts
export { Toaster, toast } from "./Toaster";
```

```typescript
// admin/packages/ui/src/index.ts (append)
export * from "./components/Toaster";
```

- [ ] **Step 2: Verify + commit**

```bash
cd admin
pnpm --filter @sacco/ui test
```

```bash
git add admin/packages/ui/src/components/Toaster/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): Toaster wrapper around sonner with token-styled defaults"
```

---

## Task 10: Portal app consumes `@sacco/ui` + globals refactor

**Files:**
- Modify: `admin/apps/portal/package.json` (add `@sacco/ui` workspace dep)
- Modify: `admin/apps/portal/app/globals.css`
- Modify: `admin/apps/portal/app/page.tsx` (use `<Card>` + `<Button>`)

- [ ] **Step 1: Add `@sacco/ui` as a portal dependency**

In `admin/apps/portal/package.json`, add to `dependencies`:

```json
"@sacco/ui": "workspace:*"
```

- [ ] **Step 2: Replace `app/globals.css` with a one-liner import**

The placeholder tokens written in sub-plan 03 are discarded. The portal now consumes tokens via `@sacco/ui`:

```css
@import "@sacco/ui/globals.css";
```

- [ ] **Step 3: Replace `app/page.tsx` with real component usage**

```tsx
import { Badge, Button, Card, KpiCard } from "@sacco/ui";

export default function Home() {
  return (
    <main className="mx-auto grid min-h-screen max-w-3xl place-items-center gap-6 p-8">
      <Card className="w-full">
        <p className="mb-2 text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
          Portal v1 — sub-plan 04
        </p>
        <h1 className="mb-3 text-3xl font-bold text-[var(--text-primary)]">
          @sacco/ui foundation
        </h1>
        <p className="mb-6 text-[var(--text-secondary)]">
          Tokens shared with Storybook. Components ready for the auth shell
          (sub-plan 07) and the app shell (sub-plan 08).
        </p>
        <div className="flex flex-wrap gap-2">
          <Button>Primary action</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Badge variant="success" withDot>Wired</Badge>
        </div>
      </Card>

      <div className="grid w-full grid-cols-3 gap-4">
        <KpiCard label="Total Members" value="—" />
        <KpiCard label="Outstanding Loans" value="—" />
        <KpiCard label="Members in Arrears" value="—" />
      </div>
    </main>
  );
}
```

- [ ] **Step 4: Install + verify the portal still builds**

```bash
make admin-install
cd admin
pnpm --filter @sacco/portal typecheck
pnpm --filter @sacco/portal lint
make admin-dev &
DEV_PID=$!
sleep 8
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000
kill $DEV_PID 2>/dev/null || true
```
Expected: typecheck + lint green; HTTP 200.

- [ ] **Step 5: Commit**

```bash
git add admin/apps/portal/package.json \
        admin/apps/portal/app/globals.css \
        admin/apps/portal/app/page.tsx \
        admin/pnpm-lock.yaml
git commit -m "feat(portal): consume tokens + components from @sacco/ui"
```

---

## Task 11: Final verification

- [ ] **Step 1: Full pipeline + tokens-sync check**

```bash
./scripts/check-tokens-sync.sh

cd admin
pnpm install
pnpm typecheck
pnpm lint
pnpm test
pnpm --filter @sacco/ui storybook:build
```
Expected:
- `check-tokens-sync.sh`: `tokens.css in sync`
- All pnpm pipelines: green
- Storybook builds to `admin/packages/ui/storybook-static/`

- [ ] **Step 2: Accessibility scan**

Boot Storybook and run the addon's "Accessibility" panel against every story. The addon fails the run if any story has serious or critical issues.

```bash
cd admin
pnpm --filter @sacco/ui storybook &
SB_PID=$!
sleep 12
# Manual inspection — open http://localhost:6006 and tab through stories.
# The a11y panel reports violations live.
kill $SB_PID 2>/dev/null || true
```

- [ ] **Step 3: PR**

```bash
git push -u origin feat/portal-v1/04-packages-ui
gh pr create --title "feat(ui): @sacco/ui foundation + 17 base components + Storybook 8" --body "$(cat <<'EOF'
## Summary
- New workspace package `@sacco/ui` ships seventeen shadcn-forked components
  (Button, Input, Label, Textarea, Select, Checkbox, Radio, Card, Badge,
  Dialog, Sheet, Popover, DropdownMenu, Tabs, Tooltip, Separator, Toaster)
- Detailed Storybook stories: Button (variants × sizes × states grid),
  Input (7 states), Card (3 variants), Badge (8 semantic + domain),
  Dialog (maker-checker confirm pattern). Other components: smoke stories
  only — added as consumers appear in later sub-plans.
- `docs/tokens.css` copied byte-identical to `packages/ui/src/tokens.css`
- `scripts/check-tokens-sync.sh` enforces the byte-identical contract in CI
- CLAUDE.md updates: token ownership policy (P), shadcn fork-vs-registry contract (Q)
- Portal app refactored to import tokens + components from `@sacco/ui`
- Vitest + React Testing Library smoke tests pass for every component
- Storybook 8 with `@storybook/addon-a11y` runs axe-core against every story

## Out of scope
- Display primitives (`<Money>`, `<FormattedDate>`, etc.) — sub-plan 09
- DataTable wrapper — sub-plan 10
- Form primitives (FormField + MoneyInput etc.) — sub-plan 11

## Test plan
- [ ] `./scripts/check-tokens-sync.sh` — tokens copy is in sync
- [ ] `make admin-install && pnpm -r typecheck && pnpm -r lint && pnpm -r test` — green
- [ ] `pnpm --filter @sacco/ui storybook:build` succeeds
- [ ] `make admin-dev` serves portal home with real components

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `@sacco/ui` package exists with the full export surface (`./tokens.css`, `./globals.css`, `./components/*`)
- [ ] `packages/ui/src/tokens.css` is byte-identical to `docs/tokens.css`
- [ ] `scripts/check-tokens-sync.sh` exists, is executable, and passes
- [ ] CLAUDE.md gains the token ownership (P) and shadcn fork (Q) contracts
- [ ] Seventeen components ship under `packages/ui/src/components/` with token-driven styling
- [ ] Storybook stories: Button (variants × sizes × states grid), Input (states), Card (3), Badge (8 + domain), Dialog
- [ ] Vitest smoke tests pass for every component
- [ ] Storybook builds cleanly via `storybook:build`
- [ ] Portal app's `globals.css` imports tokens from `@sacco/ui` (no duplication)
- [ ] Portal home page uses `<Card>`, `<Button>`, `<Badge>`, `<KpiCard>` from `@sacco/ui` so the wiring is exercised
- [ ] PR opened, CI green (admin CI workflow lands in sub-plan 39)

## Notes for the executing subagent

- **Do not** modify the byte-identical tokens copy by hand. If you find yourself editing `packages/ui/src/tokens.css`, stop. Edit `docs/tokens.css` and re-copy.
- **Do not** pull shadcn components from the registry at runtime. The forks are source-controlled. If a registry update is needed, fork the new version, replace literal colours with token references, and PR the diff.
- **Do not** use literal hex values inside component code. Every colour must reference a semantic token (`var(--...)`). This is enforced by code review; CI lint cannot catch all cases yet.
- **Do not** add detailed stories for every component. Only the five components named in the index (Button, Input, Card, Badge, Dialog) get full stories. The others get smoke stories that are upgraded when feature sub-plans (12+) consume them.
- The shadcn CLI may write components into `src/components/ui/` by default. Move them into the per-component folder structure (`src/components/Sheet/Sheet.tsx`, etc.) so the export surface stays organised.
- Tailwind v4 reads `@theme inline { ... }` blocks from any CSS file imported through PostCSS. The portal's `globals.css` imports `@sacco/ui/globals.css` which in turn imports `tokens.css` — the chain works because of `transpilePackages` in `next.config.mjs` (set in sub-plan 03).
- If Storybook can't find the tokens, verify `.storybook/preview.ts` imports `../src/globals.css` (not just `tokens.css`). The globals wrapper pulls in Tailwind v4 too — without it, utility classes don't render.
- The `@storybook/nextjs` framework reads the portal's `next.config.mjs`. If Storybook fails because of CSP or `transpilePackages`, double-check the path in `.storybook/main.ts` matches the actual location (`../../apps/portal/next.config.mjs`).
- The `prettier-plugin-tailwindcss` plugin (added in sub-plan 03) re-orders class lists on save. Trust it; if a class re-order breaks visual output, your tokens are wrong, not the order.
- If `pnpm --filter @sacco/ui test` hangs, check for missing `await` in user-event interactions. RTL 16 + user-event 14 require awaiting every interaction.
- The shadcn forks may emit React 19 deprecation warnings during install. Ignore them — the warnings come from third-party type definitions that haven't caught up yet. Don't pin to old versions of Radix to silence them.
- Total deliverable size is large but each component is small. If a single PR feels unreviewable, propose splitting Tasks 4–9 into two PRs (foundation + components, then components batch 2 + portal integration) — coordinate with the reviewer first.
