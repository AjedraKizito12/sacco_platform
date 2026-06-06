# Portal v1 Sub-Plan 09: Display Primitives

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/portal-v1/09-display-primitives` from `main` (or rebase on top of sub-plans 01-08).

**Goal:** Ship the typed display primitives the entire portal renders financial and temporal data through. After this sub-plan merges, NO call site in the codebase formats money, dates, percentages, or status labels by hand — they all go through `<Money>`, `<Percentage>`, `<Count>`, `<FormattedDate>`, `<FormattedDateTime>`, `<AuditTimestamp>`, `<RelativeTime>`, and `<StatusBadge>`. The design system's typography and color rules become enforceable: tabular numerals on every number, correct precision per currency, semantic colour per status.

**Architecture:**
- **Currency registry** (`@sacco/ui/src/utils/currency.ts`) is a small const map of ISO-3 code → `{ decimals, symbol?, locale }`. UGX → 0 decimals; KES/USD/EUR/GBP/TZS/RWF → 2 decimals. Money components read from this. Adding a new currency = adding a row.
- **TenantCurrencyProvider** is a React context that supplies the default currency for a subtree. `<Money>` without an explicit `currency` prop reads from the provider. Server components pass the tenant's default at layout level (sub-plan 08's `<AuthProvider>` will hand it in once tenant settings exist; until then, UGX is the default-default).
- **Number formatting uses `Intl.NumberFormat`.** Money / Percentage / Count all defer to the platform's number formatter, which respects locale and decimal precision. The portal's locale is `"en-UG"` by default (English Uganda — comma thousands, period decimal); a future i18n pass changes the locale, never the components.
- **Date formatting uses `date-fns`.** No `moment`, no `dayjs`. `format()` for absolute dates, `formatDistanceToNow()` for relative. Time-zone resolution is via `Intl.DateTimeFormat` with the tenant's timezone (default `Africa/Kampala` for UGX tenants; carried in the same provider as currency once tenant settings ship).
- **StatusBadge ships as a high-level wrapper around the existing `<Badge>` (sub-plan 04).** Consumers pass `entity` + `status` and the component looks up the right variant and label. The mappings live in one module so adding a new status is one place.
- **`PermissionGuard` and `requirePermission()` already shipped in sub-plan 08.** They're not re-implemented here. This sub-plan only ships the display primitives.

**Tech Stack:** React 19, `date-fns` 4, `Intl.NumberFormat`, `Intl.DateTimeFormat`.

**Portal v1 index reference:** `docs/superpowers/plans/2026-06-02-portal-v1-index.md` §Sub-plan 09.

**Required reading:**
- `docs/sacco-design-system-v2.md` §"Money & Number Display", §"Date & Time Display", §"Status Badges" (all eight domain tables)
- `app/core/audit/mixin.py` for the audit log timestamps the `<AuditTimestamp>` renders
- Sub-plan 04's `Badge` component (the lower-level primitive `<StatusBadge>` wraps)

**Prerequisite:** **Sub-plan 04 must be merged.** The `Badge` component is the foundation `StatusBadge` builds on.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `admin/packages/ui/package.json` | Modify | Add `date-fns` dependency |
| `admin/packages/ui/src/utils/currency.ts` | Create | Currency registry |
| `admin/packages/ui/src/utils/format.ts` | Create | Number + date formatter helpers |
| `admin/packages/ui/src/context/TenantCurrency.tsx` | Create | Context + provider + hook |
| `admin/packages/ui/src/components/Money/Money.tsx` | Create | Money component |
| `admin/packages/ui/src/components/Money/Money.test.tsx` | Create | Tests |
| `admin/packages/ui/src/components/Money/Money.stories.tsx` | Create | Stories |
| `admin/packages/ui/src/components/Money/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/components/Percentage/...` | Create | Percentage + tests + stories |
| `admin/packages/ui/src/components/Count/...` | Create | Count + tests + stories |
| `admin/packages/ui/src/components/FormattedDate/...` | Create | Date components (Date + DateTime + AuditTimestamp + RelativeTime) + tests + stories |
| `admin/packages/ui/src/components/StatusBadge/StatusBadge.tsx` | Create | StatusBadge with domain mappings |
| `admin/packages/ui/src/components/StatusBadge/status-maps.ts` | Create | Mapping tables (one per entity) |
| `admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx` | Create | Tests |
| `admin/packages/ui/src/components/StatusBadge/StatusBadge.stories.tsx` | Create | Stories — every entity × every status |
| `admin/packages/ui/src/components/StatusBadge/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/index.ts` | Modify | Re-export all new primitives |
| `admin/apps/portal/app/(tenant-authed)/layout.tsx` | Modify | Wrap children in `<TenantCurrencyProvider>` |
| `admin/apps/portal/app/platform/(authed)/page.tsx` | Modify | Use `<Money>` / `<StatusBadge>` / `<FormattedDateTime>` in placeholder dashboard |
| `admin/apps/portal/app/(tenant-authed)/page.tsx` | Modify | Same |
| `CLAUDE.md` | Modify | Append two contract bullets (R + S) noting tabular-nums + StatusBadge centralisation |

---

## Task 1: Currency registry + formatter helpers + TenantCurrencyProvider

**Files:**
- Modify: `admin/packages/ui/package.json` (add `date-fns`)
- Create: `admin/packages/ui/src/utils/currency.ts`
- Create: `admin/packages/ui/src/utils/format.ts`
- Create: `admin/packages/ui/src/context/TenantCurrency.tsx`

- [ ] **Step 1: Add `date-fns`**

In `admin/packages/ui/package.json`, append to `dependencies`:

```json
"date-fns": "^4.1.0"
```

Then install:

```bash
make admin-install
```

- [ ] **Step 2: Currency registry**

```typescript
// admin/packages/ui/src/utils/currency.ts
// Single source of truth for currency precision and display.
// Adding a new currency is one row; consumers do not branch on currency.

export interface CurrencyConfig {
  /** ISO-3 code (UPPERCASE). Used as the dictionary key. */
  code: string;
  /** Number of decimals used for display + parsing. */
  decimals: number;
  /** Locale tag for Intl.NumberFormat (BCP-47). */
  locale: string;
}

export const CURRENCIES: Record<string, CurrencyConfig> = {
  UGX: { code: "UGX", decimals: 0, locale: "en-UG" },
  KES: { code: "KES", decimals: 2, locale: "en-KE" },
  TZS: { code: "TZS", decimals: 2, locale: "en-TZ" },
  RWF: { code: "RWF", decimals: 0, locale: "en-RW" },
  USD: { code: "USD", decimals: 2, locale: "en-US" },
  EUR: { code: "EUR", decimals: 2, locale: "en-IE" },
  GBP: { code: "GBP", decimals: 2, locale: "en-GB" },
};

export function getCurrencyConfig(code: string): CurrencyConfig {
  const upper = code.toUpperCase();
  return CURRENCIES[upper] ?? { code: upper, decimals: 2, locale: "en-US" };
}

export const DEFAULT_CURRENCY = "UGX";
export const DEFAULT_TIMEZONE = "Africa/Kampala";
```

- [ ] **Step 3: Formatter helpers**

```typescript
// admin/packages/ui/src/utils/format.ts
import { format, formatDistanceToNow, parseISO } from "date-fns";
import { getCurrencyConfig } from "./currency";

/**
 * Format a Decimal-as-string money value for display.
 * Examples:
 *   formatMoney("1234567", "UGX") → "UGX 1,234,567"
 *   formatMoney("-50.5", "USD")   → "-USD 50.50"
 *   formatMoney("0", "UGX")        → "UGX 0"
 */
export function formatMoney(amount: string, currencyCode: string): string {
  const config = getCurrencyConfig(currencyCode);
  const numeric = Number.parseFloat(amount);
  if (!Number.isFinite(numeric)) {
    // Invalid input — render as-is rather than throwing.
    return `${config.code} ${amount}`;
  }
  const absolute = Math.abs(numeric);
  const formatter = new Intl.NumberFormat(config.locale, {
    minimumFractionDigits: config.decimals,
    maximumFractionDigits: config.decimals,
    useGrouping: true,
  });
  const formatted = formatter.format(absolute);
  return `${numeric < 0 ? "-" : ""}${config.code} ${formatted}`;
}

/**
 * Format a percentage from a Decimal-as-string value. Always 2 decimals.
 * Examples:
 *   formatPercentage("12.5")  → "12.50%"
 *   formatPercentage("100")   → "100.00%"
 */
export function formatPercentage(value: string): string {
  const numeric = Number.parseFloat(value);
  if (!Number.isFinite(numeric)) return `${value}%`;
  return `${numeric.toFixed(2)}%`;
}

/**
 * Format a non-decimal count with locale thousands separator.
 * Examples:
 *   formatCount(1234) → "1,234"
 */
export function formatCount(value: number, locale = "en-UG"): string {
  return new Intl.NumberFormat(locale, { useGrouping: true }).format(value);
}

// ── Dates ─────────────────────────────────────────────────────────────────────

/**
 * Render YYYY-MM-DD or ISO datetime as "28 May 2026".
 */
export function formatDate(value: string | Date): string {
  const date = typeof value === "string" ? parseISO(value) : value;
  return format(date, "d MMM yyyy");
}

/**
 * Render an ISO datetime as "28 May 2026, 14:32" in the given timezone.
 * Falls back to local timezone if none provided.
 */
export function formatDateTime(
  value: string | Date,
  timeZone?: string,
): string {
  const date = typeof value === "string" ? parseISO(value) : value;
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone,
  }).format(date);
}

/**
 * Render an audit timestamp: "28 May 2026, 14:32:07 EAT".
 */
export function formatAuditTimestamp(
  value: string | Date,
  timeZone?: string,
): string {
  const date = typeof value === "string" ? parseISO(value) : value;
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone,
    timeZoneName: "short",
  }).format(date);
}

/**
 * "2 hours ago" etc. Falls back to formatDate() after 7 days.
 */
export function formatRelativeTime(
  value: string | Date,
  now: Date = new Date(),
): string {
  const date = typeof value === "string" ? parseISO(value) : value;
  const ageMs = now.getTime() - date.getTime();
  const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;
  if (Math.abs(ageMs) > sevenDaysMs) {
    return formatDate(date);
  }
  return formatDistanceToNow(date, { addSuffix: true });
}
```

- [ ] **Step 4: TenantCurrencyProvider**

```tsx
// admin/packages/ui/src/context/TenantCurrency.tsx
"use client";

import { createContext, useContext, type ReactNode } from "react";
import { DEFAULT_CURRENCY, DEFAULT_TIMEZONE } from "../utils/currency";

export interface TenantCurrencyContextValue {
  currency: string;
  timeZone: string;
}

const TenantCurrencyContext = createContext<TenantCurrencyContextValue>({
  currency: DEFAULT_CURRENCY,
  timeZone: DEFAULT_TIMEZONE,
});

export interface TenantCurrencyProviderProps {
  currency?: string;
  timeZone?: string;
  children: ReactNode;
}

export function TenantCurrencyProvider({
  currency,
  timeZone,
  children,
}: TenantCurrencyProviderProps) {
  return (
    <TenantCurrencyContext.Provider
      value={{
        currency: currency ?? DEFAULT_CURRENCY,
        timeZone: timeZone ?? DEFAULT_TIMEZONE,
      }}
    >
      {children}
    </TenantCurrencyContext.Provider>
  );
}

export function useTenantCurrency(): TenantCurrencyContextValue {
  return useContext(TenantCurrencyContext);
}
```

- [ ] **Step 5: Re-export from package root**

In `admin/packages/ui/src/index.ts`, append:

```typescript
export * from "./context/TenantCurrency";
export * from "./utils/currency";
export * from "./utils/format";
```

- [ ] **Step 6: Smoke + commit**

```bash
cd admin
pnpm --filter @sacco/ui typecheck
```

```bash
git add admin/packages/ui/package.json \
        admin/packages/ui/src/utils/{currency,format}.ts \
        admin/packages/ui/src/context/TenantCurrency.tsx \
        admin/packages/ui/src/index.ts \
        admin/pnpm-lock.yaml
git commit -m "feat(ui): currency registry + format helpers + TenantCurrencyProvider"
```

---

## Task 2: Money + Percentage + Count

**Files:**
- Create: `admin/packages/ui/src/components/Money/{Money.tsx,Money.test.tsx,Money.stories.tsx,index.ts}`
- Create: `admin/packages/ui/src/components/Percentage/{Percentage.tsx,Percentage.test.tsx,Percentage.stories.tsx,index.ts}`
- Create: `admin/packages/ui/src/components/Count/{Count.tsx,Count.test.tsx,Count.stories.tsx,index.ts}`
- Modify: `admin/packages/ui/src/index.ts`

- [ ] **Step 1: Money component**

```tsx
// admin/packages/ui/src/components/Money/Money.tsx
import type { HTMLAttributes } from "react";
import { cn } from "../../utils/cn";
import { formatMoney } from "../../utils/format";
import { useTenantCurrency } from "../../context/TenantCurrency";

export interface MoneyProps extends HTMLAttributes<HTMLSpanElement> {
  /** Decimal-as-string amount per CLAUDE.md rule #5. */
  amount: string;
  /** Override the provider's currency. */
  currency?: string;
  /** Render in a larger style for KPI cards. */
  size?: "default" | "large";
}

export function Money({
  amount,
  currency,
  size = "default",
  className,
  ...props
}: MoneyProps) {
  const provider = useTenantCurrency();
  const effectiveCurrency = currency ?? provider.currency;
  const formatted = formatMoney(amount, effectiveCurrency);
  const isNegative = formatted.startsWith("-");
  return (
    <span
      className={cn(
        "[font-feature-settings:'tnum'_1,'lnum'_1]",
        size === "large" && "text-[28px] font-semibold leading-tight",
        isNegative && "text-[var(--text-danger)]",
        className,
      )}
      data-currency={effectiveCurrency}
      data-amount={amount}
      {...props}
    >
      {formatted}
    </span>
  );
}
```

- [ ] **Step 2: Money tests**

```tsx
// admin/packages/ui/src/components/Money/Money.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Money } from "./Money";
import { TenantCurrencyProvider } from "../../context/TenantCurrency";

describe("Money", () => {
  it("formats UGX with no decimals", () => {
    render(<Money amount="1234567" currency="UGX" />);
    expect(screen.getByText("UGX 1,234,567")).toBeInTheDocument();
  });

  it("formats USD with 2 decimals", () => {
    render(<Money amount="50" currency="USD" />);
    expect(screen.getByText("USD 50.00")).toBeInTheDocument();
  });

  it("renders zero correctly", () => {
    render(<Money amount="0" currency="UGX" />);
    expect(screen.getByText("UGX 0")).toBeInTheDocument();
  });

  it("renders negative with danger colour", () => {
    render(<Money amount="-1234" currency="UGX" />);
    const span = screen.getByText("-UGX 1,234");
    expect(span.className).toMatch(/text-\[var\(--text-danger\)\]/);
  });

  it("uses the provider's currency when no prop", () => {
    render(
      <TenantCurrencyProvider currency="KES">
        <Money amount="50" />
      </TenantCurrencyProvider>,
    );
    expect(screen.getByText("KES 50.00")).toBeInTheDocument();
  });

  it("does not crash on invalid input", () => {
    render(<Money amount="not-a-number" currency="UGX" />);
    expect(screen.getByText(/UGX/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Money stories**

```tsx
// admin/packages/ui/src/components/Money/Money.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { Money } from "./Money";

const meta: Meta<typeof Money> = {
  title: "Display/Money",
  component: Money,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof Money>;

export const UGX: Story = { args: { amount: "1234567", currency: "UGX" } };
export const KES: Story = { args: { amount: "50000.50", currency: "KES" } };
export const USD: Story = { args: { amount: "12.34", currency: "USD" } };
export const Zero: Story = { args: { amount: "0", currency: "UGX" } };
export const Negative: Story = { args: { amount: "-1234567", currency: "UGX" } };
export const Large: Story = {
  args: { amount: "12345000", currency: "UGX", size: "large" },
};

export const TableAlignmentDemo: Story = {
  render: () => (
    <table className="border-collapse">
      <tbody>
        {["1234", "1234567", "1234567890", "12.34"].map((v) => (
          <tr key={v} className="border-b">
            <td className="px-4 py-2 text-right">
              <Money amount={v} currency="UGX" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  ),
};
```

- [ ] **Step 4: Percentage component**

```tsx
// admin/packages/ui/src/components/Percentage/Percentage.tsx
import type { HTMLAttributes } from "react";
import { cn } from "../../utils/cn";
import { formatPercentage } from "../../utils/format";

export interface PercentageProps extends HTMLAttributes<HTMLSpanElement> {
  /** Decimal-as-string value (0-100). */
  value: string;
}

export function Percentage({ value, className, ...props }: PercentageProps) {
  return (
    <span
      className={cn(
        "[font-feature-settings:'tnum'_1,'lnum'_1]",
        className,
      )}
      data-value={value}
      {...props}
    >
      {formatPercentage(value)}
    </span>
  );
}
```

```tsx
// admin/packages/ui/src/components/Percentage/Percentage.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Percentage } from "./Percentage";

describe("Percentage", () => {
  it("renders with two decimal places", () => {
    render(<Percentage value="12.5" />);
    expect(screen.getByText("12.50%")).toBeInTheDocument();
  });
  it("handles integers", () => {
    render(<Percentage value="100" />);
    expect(screen.getByText("100.00%")).toBeInTheDocument();
  });
});
```

```tsx
// admin/packages/ui/src/components/Percentage/Percentage.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { Percentage } from "./Percentage";

const meta: Meta<typeof Percentage> = {
  title: "Display/Percentage",
  component: Percentage,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof Percentage>;

export const Default: Story = { args: { value: "12.5" } };
export const Zero: Story = { args: { value: "0" } };
export const HighPrecision: Story = { args: { value: "12.345" } };
```

- [ ] **Step 5: Count component**

```tsx
// admin/packages/ui/src/components/Count/Count.tsx
import type { HTMLAttributes } from "react";
import { cn } from "../../utils/cn";
import { formatCount } from "../../utils/format";

export interface CountProps extends HTMLAttributes<HTMLSpanElement> {
  value: number;
}

export function Count({ value, className, ...props }: CountProps) {
  return (
    <span
      className={cn(
        "[font-feature-settings:'tnum'_1,'lnum'_1]",
        className,
      )}
      data-value={value}
      {...props}
    >
      {formatCount(value)}
    </span>
  );
}
```

```tsx
// admin/packages/ui/src/components/Count/Count.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Count } from "./Count";

describe("Count", () => {
  it("formats with thousands separator", () => {
    render(<Count value={1234567} />);
    expect(screen.getByText("1,234,567")).toBeInTheDocument();
  });
  it("renders zero", () => {
    render(<Count value={0} />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});
```

```tsx
// admin/packages/ui/src/components/Count/Count.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { Count } from "./Count";

const meta: Meta<typeof Count> = {
  title: "Display/Count",
  component: Count,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof Count>;

export const Default: Story = { args: { value: 1234 } };
export const Large: Story = { args: { value: 1234567890 } };
```

- [ ] **Step 6: Index files + re-exports + run tests**

Add `index.ts` for each component (e.g., `export { Money, type MoneyProps } from "./Money";`).

Update `admin/packages/ui/src/index.ts`:

```typescript
export * from "./components/Money";
export * from "./components/Percentage";
export * from "./components/Count";
```

```bash
cd admin
pnpm --filter @sacco/ui test
```
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add admin/packages/ui/src/components/{Money,Percentage,Count}/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): Money + Percentage + Count display primitives"
```

---

## Task 3: Date components

**Files:**
- Create: `admin/packages/ui/src/components/FormattedDate/{FormattedDate.tsx,FormattedDate.test.tsx,FormattedDate.stories.tsx,index.ts}`

(All four date components ship in the same folder since they share the same module concerns. The index file re-exports them all.)

- [ ] **Step 1: Implementation**

```tsx
// admin/packages/ui/src/components/FormattedDate/FormattedDate.tsx
import type { HTMLAttributes } from "react";
import { cn } from "../../utils/cn";
import {
  formatAuditTimestamp,
  formatDate,
  formatDateTime,
  formatRelativeTime,
} from "../../utils/format";
import { useTenantCurrency } from "../../context/TenantCurrency";

const numericClass = "[font-feature-settings:'tnum'_1,'lnum'_1]";

export interface FormattedDateProps extends HTMLAttributes<HTMLSpanElement> {
  /** ISO date (YYYY-MM-DD) or full ISO timestamp. */
  value: string | Date;
}

export function FormattedDate({ value, className, ...props }: FormattedDateProps) {
  return (
    <span className={cn(numericClass, className)} {...props}>
      {formatDate(value)}
    </span>
  );
}

export interface FormattedDateTimeProps extends HTMLAttributes<HTMLSpanElement> {
  value: string | Date;
  /** Override the tenant's default timezone. */
  timeZone?: string;
}

export function FormattedDateTime({
  value,
  timeZone,
  className,
  ...props
}: FormattedDateTimeProps) {
  const ctx = useTenantCurrency();
  return (
    <span className={cn(numericClass, className)} {...props}>
      {formatDateTime(value, timeZone ?? ctx.timeZone)}
    </span>
  );
}

export interface AuditTimestampProps extends HTMLAttributes<HTMLSpanElement> {
  value: string | Date;
  timeZone?: string;
}

export function AuditTimestamp({
  value,
  timeZone,
  className,
  ...props
}: AuditTimestampProps) {
  const ctx = useTenantCurrency();
  return (
    <span className={cn(numericClass, className)} {...props}>
      {formatAuditTimestamp(value, timeZone ?? ctx.timeZone)}
    </span>
  );
}

export interface RelativeTimeProps extends HTMLAttributes<HTMLSpanElement> {
  value: string | Date;
  /** Custom "now" for testing. */
  now?: Date;
}

export function RelativeTime({
  value,
  now,
  className,
  ...props
}: RelativeTimeProps) {
  return (
    <span
      className={cn(numericClass, className)}
      title={typeof value === "string" ? value : value.toISOString()}
      {...props}
    >
      {formatRelativeTime(value, now)}
    </span>
  );
}
```

- [ ] **Step 2: Tests**

```tsx
// admin/packages/ui/src/components/FormattedDate/FormattedDate.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  AuditTimestamp,
  FormattedDate,
  FormattedDateTime,
  RelativeTime,
} from "./FormattedDate";
import { TenantCurrencyProvider } from "../../context/TenantCurrency";

describe("FormattedDate", () => {
  it("renders YYYY-MM-DD as 'd MMM yyyy'", () => {
    render(<FormattedDate value="2026-05-28" />);
    expect(screen.getByText("28 May 2026")).toBeInTheDocument();
  });
  it("accepts a Date object", () => {
    render(<FormattedDate value={new Date(Date.UTC(2026, 4, 28))} />);
    expect(screen.getByText("28 May 2026")).toBeInTheDocument();
  });
});

describe("FormattedDateTime", () => {
  it("renders ISO datetime in the configured timezone", () => {
    render(
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <FormattedDateTime value="2026-05-28T11:32:00Z" />
      </TenantCurrencyProvider>,
    );
    // Africa/Kampala is UTC+3 → 14:32
    expect(screen.getByText(/14:32/)).toBeInTheDocument();
    expect(screen.getByText(/28 May 2026/)).toBeInTheDocument();
  });
});

describe("AuditTimestamp", () => {
  it("includes seconds + timezone abbreviation", () => {
    render(
      <TenantCurrencyProvider timeZone="Africa/Kampala">
        <AuditTimestamp value="2026-05-28T11:32:07Z" />
      </TenantCurrencyProvider>,
    );
    expect(screen.getByText(/14:32:07/)).toBeInTheDocument();
  });
});

describe("RelativeTime", () => {
  it("renders a relative phrase for recent timestamps", () => {
    const now = new Date("2026-05-28T14:32:00Z");
    const twoHoursAgo = new Date("2026-05-28T12:30:00Z");
    render(<RelativeTime value={twoHoursAgo} now={now} />);
    expect(screen.getByText(/hours? ago/)).toBeInTheDocument();
  });

  it("falls back to absolute date after 7 days", () => {
    const now = new Date("2026-05-28T14:32:00Z");
    const oneMonthAgo = new Date("2026-04-28T14:32:00Z");
    render(<RelativeTime value={oneMonthAgo} now={now} />);
    expect(screen.getByText("28 Apr 2026")).toBeInTheDocument();
  });

  it("exposes the raw timestamp via title for tooltip use", () => {
    render(<RelativeTime value="2026-05-28T14:32:00Z" />);
    const span = screen.getByText(/ago|2026/);
    expect(span).toHaveAttribute("title", "2026-05-28T14:32:00Z");
  });
});
```

- [ ] **Step 3: Stories**

```tsx
// admin/packages/ui/src/components/FormattedDate/FormattedDate.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import {
  AuditTimestamp,
  FormattedDate,
  FormattedDateTime,
  RelativeTime,
} from "./FormattedDate";

const meta: Meta = {
  title: "Display/Date",
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

export const FormattedDateExample: Story = {
  render: () => <FormattedDate value="2026-05-28" />,
};

export const FormattedDateTimeExample: Story = {
  render: () => <FormattedDateTime value="2026-05-28T14:32:00Z" />,
};

export const AuditTimestampExample: Story = {
  render: () => <AuditTimestamp value="2026-05-28T14:32:07Z" />,
};

export const RelativeTimeExample: Story = {
  render: () => (
    <div className="flex flex-col gap-2">
      <RelativeTime value={new Date(Date.now() - 2 * 60 * 60 * 1000)} />
      <RelativeTime value={new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)} />
    </div>
  ),
};
```

- [ ] **Step 4: Index + re-exports + commit**

```typescript
// admin/packages/ui/src/components/FormattedDate/index.ts
export {
  FormattedDate,
  FormattedDateTime,
  AuditTimestamp,
  RelativeTime,
  type FormattedDateProps,
  type FormattedDateTimeProps,
  type AuditTimestampProps,
  type RelativeTimeProps,
} from "./FormattedDate";
```

In `admin/packages/ui/src/index.ts`:

```typescript
export * from "./components/FormattedDate";
```

```bash
cd admin
pnpm --filter @sacco/ui test
```

```bash
git add admin/packages/ui/src/components/FormattedDate/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): FormattedDate + FormattedDateTime + AuditTimestamp + RelativeTime"
```

---

## Task 4: StatusBadge + domain status mappings

**Files:**
- Create: `admin/packages/ui/src/components/StatusBadge/status-maps.ts`
- Create: `admin/packages/ui/src/components/StatusBadge/StatusBadge.tsx`
- Create: `admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx`
- Create: `admin/packages/ui/src/components/StatusBadge/StatusBadge.stories.tsx`
- Create: `admin/packages/ui/src/components/StatusBadge/index.ts`

- [ ] **Step 1: Status maps**

The maps come straight from `docs/sacco-design-system-v2.md` §"Domain Status Mapping". Each entry is `{variant, label}`.

```typescript
// admin/packages/ui/src/components/StatusBadge/status-maps.ts
// Per docs/sacco-design-system-v2.md §"Domain Status Mapping". Adding a
// new status means adding a row in the relevant map.

import type { BadgeProps } from "../Badge";

export type StatusEntity =
  | "loan"
  | "member"
  | "tenant"
  | "savings_account"
  | "fee_assessment"
  | "approval_request"
  | "subscription"
  | "invoice"
  | "payment";

interface MapEntry {
  variant: NonNullable<BadgeProps["variant"]>;
  label: string;
}

type StatusMap = Record<string, MapEntry>;

export const LOAN_STATUS: StatusMap = {
  draft: { variant: "neutral", label: "Draft" },
  submitted: { variant: "info", label: "Submitted" },
  under_review: { variant: "info", label: "Under Review" },
  approved: { variant: "success", label: "Approved" },
  disbursing: { variant: "warning", label: "Disbursing" },
  disbursed: { variant: "success", label: "Disbursed" },
  in_arrears: { variant: "danger-solid", label: "In Arrears" },
  restructured: { variant: "accent", label: "Restructured" },
  written_off: { variant: "danger", label: "Written Off" },
  closed: { variant: "dark", label: "Closed" },
  rejected: { variant: "danger", label: "Rejected" },
  withdrawn: { variant: "neutral", label: "Withdrawn" },
  cancelled: { variant: "neutral", label: "Cancelled" },
};

export const MEMBER_STATUS: StatusMap = {
  prospect: { variant: "info", label: "Prospect" },
  active: { variant: "success", label: "Active" },
  dormant: { variant: "warning", label: "Dormant" },
  suspended: { variant: "danger-solid", label: "Suspended" },
  exited: { variant: "neutral", label: "Exited" },
  deceased: { variant: "dark", label: "Deceased" },
};

export const TENANT_STATUS: StatusMap = {
  pending: { variant: "info", label: "Pending" },
  provisioning: { variant: "warning", label: "Provisioning" },
  active: { variant: "success", label: "Active" },
  suspended: { variant: "danger-solid", label: "Suspended" },
  failed: { variant: "danger", label: "Failed" },
  deprovisioning: { variant: "warning", label: "Deprovisioning" },
  archived: { variant: "neutral", label: "Archived" },
};

export const SAVINGS_ACCOUNT_STATUS: StatusMap = {
  active: { variant: "success", label: "Active" },
  dormant: { variant: "warning", label: "Dormant" },
  frozen: { variant: "danger-solid", label: "Frozen" },
  closed: { variant: "neutral", label: "Closed" },
};

export const FEE_ASSESSMENT_STATUS: StatusMap = {
  assessed: { variant: "warning", label: "Assessed" },
  partially_paid: { variant: "info", label: "Partially Paid" },
  paid: { variant: "success", label: "Paid" },
  waived: { variant: "accent", label: "Waived" },
  cancelled: { variant: "neutral", label: "Cancelled" },
};

export const APPROVAL_REQUEST_STATUS: StatusMap = {
  pending: { variant: "warning", label: "Pending Approval" },
  approved: { variant: "info", label: "Approved" },
  rejected: { variant: "danger", label: "Rejected" },
  executed: { variant: "success", label: "Executed" },
  execution_failed: { variant: "danger-solid", label: "Execution Failed" },
  expired: { variant: "neutral", label: "Expired" },
  cancelled: { variant: "neutral", label: "Cancelled" },
};

// Subscription / invoice / payment maps cover the billing surface.
export const SUBSCRIPTION_STATUS: StatusMap = {
  pending: { variant: "info", label: "Pending" },
  trialing: { variant: "info", label: "Trialing" },
  active: { variant: "success", label: "Active" },
  past_due: { variant: "warning", label: "Past due" },
  suspended: { variant: "danger-solid", label: "Suspended" },
  cancelled: { variant: "neutral", label: "Cancelled" },
};

export const INVOICE_STATUS: StatusMap = {
  draft: { variant: "neutral", label: "Draft" },
  issued: { variant: "info", label: "Issued" },
  partial: { variant: "warning", label: "Partial" },
  paid: { variant: "success", label: "Paid" },
  overdue: { variant: "danger-solid", label: "Overdue" },
  void: { variant: "neutral", label: "Void" },
};

export const PAYMENT_STATUS: StatusMap = {
  pending: { variant: "warning", label: "Pending Confirmation" },
  confirmed: { variant: "success", label: "Confirmed" },
  rejected: { variant: "danger", label: "Rejected" },
};

const ENTITY_MAPS: Record<StatusEntity, StatusMap> = {
  loan: LOAN_STATUS,
  member: MEMBER_STATUS,
  tenant: TENANT_STATUS,
  savings_account: SAVINGS_ACCOUNT_STATUS,
  fee_assessment: FEE_ASSESSMENT_STATUS,
  approval_request: APPROVAL_REQUEST_STATUS,
  subscription: SUBSCRIPTION_STATUS,
  invoice: INVOICE_STATUS,
  payment: PAYMENT_STATUS,
};

export function resolveStatus(
  entity: StatusEntity,
  status: string,
): MapEntry | null {
  return ENTITY_MAPS[entity][status] ?? null;
}
```

- [ ] **Step 2: StatusBadge component**

```tsx
// admin/packages/ui/src/components/StatusBadge/StatusBadge.tsx
import { Badge } from "../Badge";
import { type StatusEntity, resolveStatus } from "./status-maps";

export interface StatusBadgeProps {
  entity: StatusEntity;
  status: string;
  /** Override the looked-up label (e.g., for localisation). */
  label?: string;
  withDot?: boolean;
  className?: string;
}

export function StatusBadge({
  entity,
  status,
  label,
  withDot,
  className,
}: StatusBadgeProps) {
  const entry = resolveStatus(entity, status);
  if (!entry) {
    // Unknown status — render the raw value in a neutral badge so the
    // operator can see what came through. Never crash.
    return (
      <Badge variant="neutral" withDot={withDot} className={className}>
        {label ?? status}
      </Badge>
    );
  }
  return (
    <Badge variant={entry.variant} withDot={withDot} className={className}>
      {label ?? entry.label}
    </Badge>
  );
}
```

- [ ] **Step 3: Tests**

```tsx
// admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders loan status with mapped label", () => {
    render(<StatusBadge entity="loan" status="in_arrears" />);
    expect(screen.getByText("In Arrears")).toBeInTheDocument();
  });

  it("renders tenant status", () => {
    render(<StatusBadge entity="tenant" status="suspended" />);
    expect(screen.getByText("Suspended")).toBeInTheDocument();
  });

  it("falls back to neutral with raw value for unknown status", () => {
    render(<StatusBadge entity="loan" status="quantum_state" />);
    expect(screen.getByText("quantum_state")).toBeInTheDocument();
  });

  it("respects label override", () => {
    render(<StatusBadge entity="loan" status="closed" label="Wrapped up" />);
    expect(screen.getByText("Wrapped up")).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Stories — coverage matrix per entity**

```tsx
// admin/packages/ui/src/components/StatusBadge/StatusBadge.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { StatusBadge } from "./StatusBadge";
import {
  APPROVAL_REQUEST_STATUS,
  FEE_ASSESSMENT_STATUS,
  INVOICE_STATUS,
  LOAN_STATUS,
  MEMBER_STATUS,
  PAYMENT_STATUS,
  SAVINGS_ACCOUNT_STATUS,
  SUBSCRIPTION_STATUS,
  TENANT_STATUS,
} from "./status-maps";

const meta: Meta<typeof StatusBadge> = {
  title: "Display/StatusBadge",
  component: StatusBadge,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof StatusBadge>;

function row(map: typeof LOAN_STATUS, entity: Parameters<typeof StatusBadge>[0]["entity"]) {
  return (
    <div className="flex flex-wrap gap-2">
      {Object.keys(map).map((status) => (
        <StatusBadge key={status} entity={entity} status={status} />
      ))}
    </div>
  );
}

export const Loan: Story = { render: () => row(LOAN_STATUS, "loan") };
export const Member: Story = { render: () => row(MEMBER_STATUS, "member") };
export const Tenant: Story = { render: () => row(TENANT_STATUS, "tenant") };
export const SavingsAccount: Story = {
  render: () => row(SAVINGS_ACCOUNT_STATUS, "savings_account"),
};
export const FeeAssessment: Story = {
  render: () => row(FEE_ASSESSMENT_STATUS, "fee_assessment"),
};
export const ApprovalRequest: Story = {
  render: () => row(APPROVAL_REQUEST_STATUS, "approval_request"),
};
export const Subscription: Story = {
  render: () => row(SUBSCRIPTION_STATUS, "subscription"),
};
export const Invoice: Story = { render: () => row(INVOICE_STATUS, "invoice") };
export const Payment: Story = { render: () => row(PAYMENT_STATUS, "payment") };
```

- [ ] **Step 5: Index + re-exports + run**

```typescript
// admin/packages/ui/src/components/StatusBadge/index.ts
export {
  StatusBadge,
  type StatusBadgeProps,
} from "./StatusBadge";
export {
  type StatusEntity,
  resolveStatus,
  LOAN_STATUS,
  MEMBER_STATUS,
  TENANT_STATUS,
  SAVINGS_ACCOUNT_STATUS,
  FEE_ASSESSMENT_STATUS,
  APPROVAL_REQUEST_STATUS,
  SUBSCRIPTION_STATUS,
  INVOICE_STATUS,
  PAYMENT_STATUS,
} from "./status-maps";
```

In `admin/packages/ui/src/index.ts`:

```typescript
export * from "./components/StatusBadge";
```

```bash
cd admin
pnpm --filter @sacco/ui test
pnpm --filter @sacco/ui storybook:build
```

```bash
git add admin/packages/ui/src/components/StatusBadge/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): StatusBadge with nine domain entity status maps"
```

---

## Task 5: Portal app consumes the primitives + tenant currency wiring

**Files:**
- Modify: `admin/apps/portal/app/(tenant-authed)/layout.tsx`
- Modify: `admin/apps/portal/app/platform/(authed)/page.tsx`
- Modify: `admin/apps/portal/app/(tenant-authed)/page.tsx`

- [ ] **Step 1: Wrap the tenant layout in `<TenantCurrencyProvider>`**

In `admin/apps/portal/app/(tenant-authed)/layout.tsx`, import `TenantCurrencyProvider` and wrap children. For v1 the currency stays at the `UGX` default; once tenant settings ship (post-v1) it's pulled from the user's tenant config.

```tsx
import { TenantCurrencyProvider } from "@sacco/ui";

// inside the JSX, around <AppErrorBoundary>:
<TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
  <AppErrorBoundary>
    {/* …existing shell… */}
  </AppErrorBoundary>
</TenantCurrencyProvider>
```

- [ ] **Step 2: Use primitives in the placeholder dashboards**

Update `admin/apps/portal/app/platform/(authed)/page.tsx`:

```tsx
import { Card, KpiCard, Money, StatusBadge, FormattedDateTime } from "@sacco/ui";

export default function PlatformDashboard() {
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          Platform dashboard
        </h1>
        <p className="text-[var(--text-secondary)]">
          Sub-plan 34 wires the real <code>GET /platform/admin/dashboard-stats</code> data.
        </p>
      </Card>

      <div className="grid grid-cols-3 gap-4">
        <KpiCard
          label="Total tenants"
          value="—"
          trend={{ direction: "flat", label: "no change" }}
        />
        <KpiCard
          label="Monthly recurring revenue"
          value={<Money amount="0" currency="UGX" size="large" />}
        />
        <KpiCard label="Outstanding invoices" value="—" />
      </div>

      <Card>
        <h2 className="mb-3 text-[18px] font-semibold">Sample status row</h2>
        <div className="flex flex-wrap gap-2">
          <StatusBadge entity="tenant" status="active" />
          <StatusBadge entity="tenant" status="provisioning" />
          <StatusBadge entity="invoice" status="overdue" />
          <StatusBadge entity="approval_request" status="pending" />
        </div>
        <p className="mt-3 text-[12px] text-[var(--text-tertiary)]">
          Last refreshed <FormattedDateTime value={new Date().toISOString()} />
        </p>
      </Card>
    </div>
  );
}
```

Same shape for `admin/apps/portal/app/(tenant-authed)/page.tsx`:

```tsx
import { Card, KpiCard, Money, StatusBadge, FormattedDate } from "@sacco/ui";

export default function TenantDashboard() {
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">Tenant dashboard</h1>
        <p className="text-[var(--text-secondary)]">
          Sub-plan 35 wires the real KPIs, charts, recent activity.
        </p>
      </Card>

      <div className="grid grid-cols-4 gap-4">
        <KpiCard label="Total members" value="—" />
        <KpiCard label="Total savings" value={<Money amount="0" size="large" />} />
        <KpiCard label="Outstanding loans" value={<Money amount="0" size="large" />} />
        <KpiCard label="Members in arrears" value="—" />
      </div>

      <Card>
        <h2 className="mb-3 text-[18px] font-semibold">Sample status row</h2>
        <div className="flex flex-wrap gap-2">
          <StatusBadge entity="member" status="active" />
          <StatusBadge entity="member" status="dormant" />
          <StatusBadge entity="loan" status="in_arrears" />
          <StatusBadge entity="savings_account" status="frozen" />
        </div>
        <p className="mt-3 text-[12px] text-[var(--text-tertiary)]">
          As of <FormattedDate value={new Date().toISOString()} />
        </p>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Smoke check**

```bash
cd admin
pnpm typecheck
pnpm lint
pnpm test
make admin-dev &
DEV_PID=$!
sleep 8
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/platform
kill $DEV_PID 2>/dev/null || true
```
Expected: 200; visual check shows the status row + Money formatting.

- [ ] **Step 4: Commit**

```bash
git add admin/apps/portal/app/\(tenant-authed\)/ \
        admin/apps/portal/app/platform/\(authed\)/page.tsx
git commit -m "feat(portal): dashboards consume Money/StatusBadge/Date primitives"
```

---

## Task 6: CLAUDE.md contracts

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append two bullets to the Admin portal contracts subsection**

Find `### Admin portal contracts (do not violate)` (extended in sub-plan 03). Append:

```markdown
R. Numbers and money are rendered through the typed primitives from
   `@sacco/ui` only: `<Money>`, `<Percentage>`, `<Count>`. Each enforces
   tabular numerals and the currency registry's precision rules. Inline
   `toLocaleString` calls are a contract violation and should be flagged
   in review.

S. Domain statuses (loan, member, tenant, savings account, fee assessment,
   approval request, subscription, invoice, payment) render through
   `<StatusBadge entity status />`. The mapping tables live in
   `@sacco/ui/components/StatusBadge/status-maps.ts`. Adding a new status
   means adding a row in that file; never hand-pick a `Badge` variant
   for a domain status.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): display primitives + StatusBadge centralisation contracts"
```

---

## Task 7: Final verification

- [ ] **Step 1: Full pipeline + Storybook**

```bash
cd admin
pnpm install
pnpm typecheck
pnpm lint
pnpm test
pnpm --filter @sacco/ui storybook:build
```
Expected: all green; the Storybook static build now contains the Money / Percentage / Count / Date / StatusBadge stories.

- [ ] **Step 2: Manual smoke**

```bash
make admin-dev &
DEV_PID=$!
sleep 8
# Visual: open the portal home, verify Money/StatusBadge renders.
kill $DEV_PID 2>/dev/null || true
```

- [ ] **Step 3: PR**

```bash
git push -u origin feat/portal-v1/09-display-primitives
gh pr create --title "feat(ui): display primitives (Money / Date / StatusBadge)" --body "$(cat <<'EOF'
## Summary
- Currency registry (7 ISO-3 codes, precision + locale) + `TenantCurrencyProvider` context
- `<Money>` (currency-prefixed, tabular-nums, negative-in-danger, large variant for KPIs)
- `<Percentage>` (2 decimals, tabular-nums)
- `<Count>` (locale thousands separator, tabular-nums)
- `<FormattedDate>` (28 May 2026), `<FormattedDateTime>` (in tenant tz), `<AuditTimestamp>` (with seconds + tz abbreviation), `<RelativeTime>` ("2 hours ago" → falls back to absolute after 7 days)
- `<StatusBadge entity status />` with 9 domain status maps covering loan / member / tenant / savings_account / fee_assessment / approval_request / subscription / invoice / payment
- Storybook stories cover every variant; Vitest covers the primitives end-to-end
- Portal dashboards refactored to consume the primitives
- CLAUDE.md gains contracts R (numbers via `<Money>`/`<Percentage>`/`<Count>`) and S (statuses via `<StatusBadge>`)

## Out of scope
- DataTable (sub-plan 10)
- Form primitives + MoneyInput (sub-plan 11)
- PermissionGuard / requirePermission (already shipped in sub-plan 08)

## Test plan
- [ ] `pnpm --filter @sacco/ui test` — Money / Percentage / Count / Date / StatusBadge cases
- [ ] `pnpm --filter @sacco/ui storybook:build`
- [ ] Manual: portal `/platform` and `/` render the placeholder dashboards with the primitives

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `CURRENCIES` registry + `formatMoney`/`formatPercentage`/`formatCount`/date helpers in `@sacco/ui/utils`
- [ ] `<TenantCurrencyProvider>` + `useTenantCurrency()` exported
- [ ] `<Money>`, `<Percentage>`, `<Count>` render with tabular-nums and the documented formatting
- [ ] `<FormattedDate>`, `<FormattedDateTime>`, `<AuditTimestamp>`, `<RelativeTime>` render per the design system spec
- [ ] `<StatusBadge entity status />` maps for all nine entities; unknown status falls back to neutral with the raw value
- [ ] Storybook stories cover every primitive + every status entity
- [ ] Portal dashboards consume the primitives
- [ ] CLAUDE.md gains contracts R and S
- [ ] All new tests pass
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** add a "no-currency" `<Money>` mode. Money without a currency is meaningless. If a caller has no currency context, they should ship a `<TenantCurrencyProvider>` or pass `currency` explicitly.
- **Do not** use `toLocaleString` directly anywhere in the portal. The primitives are the only acceptable path. CI sub-plan 39 will guard against this with a grep-based check.
- **Do not** introduce a custom date parser. `date-fns`'s `parseISO` handles every ISO-8601 form FastAPI emits.
- **Do not** drop the leading `"-"` on negative money or move it after the currency code. The design system spec is clear: minus sign first, then currency, then absolute value, rendered in `text-danger-700`. Accounting parentheses are explicitly forbidden.
- **Do not** branch on currency outside the registry. If a new currency needs different formatting (decimals, locale), add it to `CURRENCIES`. The consumers stay the same.
- The `formatMoney` function tolerates malformed strings rather than throwing. This is deliberate: at form-edit time, partial input ("12.") should render gracefully. The Zod schema rejects malformed values at submit time.
- The `<RelativeTime>` `now` prop is purely for testing — production calls omit it and use the system clock. Don't expose it as a "freeze time" hack in production code.
- The seven currencies cover East Africa + the major Western currencies. Adding more is a one-line PR; **do** add new ones as the platform expands. **Do NOT** "pre-populate" exotic currencies that aren't actively used.
- The `<StatusBadge>` status maps are the source of truth for domain status display. If a feature sub-plan needs a status that isn't in the map, add the row to the map first (with reviewer alignment) and only then write the consuming code.
- The `AuditTimestamp` uses `Intl.DateTimeFormat` with `timeZoneName: "short"`. The displayed string is locale-dependent — `"en-GB"` produces `EAT` for Africa/Kampala; other locales may produce different abbreviations. This is acceptable because audit timestamps are operator-facing.
- The tenant's actual timezone will come from the API's tenant settings once they exist. Until then the layout hardcodes `Africa/Kampala`. Don't add a per-user tz override here — that's a future setting.
- `getCurrencyConfig` returns a sensible default for unknown codes rather than throwing. The runtime path is permissive; the Zod schema's `currencyCode` is strict. Two layers of defense.
- The Storybook `TableAlignmentDemo` story exists to manually verify tabular-nums actually aligns columns. If the alignment looks off, the issue is almost always a missing font or that the surrounding container uses `text-align: left` instead of `right`. The component class adds `'tnum'_1`, not `text-align`; cells using `<Money>` in tables need `className="text-right"`.
