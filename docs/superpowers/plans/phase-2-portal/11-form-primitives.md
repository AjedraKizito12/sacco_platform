# Portal v1 Sub-Plan 11: Form Primitives + Maker-Checker UX + Audit Bar

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/portal-v1/11-form-primitives` from `main` (or rebase on top of sub-plans 01-10).

**Goal:** Ship the form, dialog, and entity-detail primitives every screen in the portal will compose with. After this sub-plan merges, no feature module hand-rolls a label/input/error triad, no caller types `<input type="number">` for money, no operator-facing destructive action ships without `<ConfirmDialog>`, every approval-creating button uses `<MakerCheckerConfirmDialog>`, every entity-detail page can drop in `<AuditBar>` (graceful placeholder until the audit-log query endpoint ships), and every long form gets `useDraftAutoSave` for free.

**Architecture:**
- **FormField is a React Hook Form Controller wrapper.** Caller passes a `control` and `name`; FormField handles label / required-indicator / help / error / aria-describedby wiring. The render prop receives the field handlers — the field implementation (e.g., `<Input>`, `<MoneyInput>`, `<DateInput>`) stays a presentational uncontrolled component. RHF stays a peer-style dep of `@sacco/ui` so consumers ship one copy.
- **MoneyInput / PercentageInput / DateInput / DateRangeInput are presentational.** They accept `value` + `onValueChange` + `onBlur`. They never know about RHF — they integrate via FormField. This keeps them testable in isolation and reusable in non-RHF contexts (Storybook controls, simple search bars).
- **MoneyInput reads precision from the same `CURRENCIES` registry shipped in sub-plan 09.** The displayed string always carries the currency chip; the internal value is a Decimal-as-string (no float). On blur it canonicalises to the registry's precision. Negative values are disallowed unless the caller opts in.
- **DateInput uses `react-day-picker`** (the same library shadcn's Calendar wraps). Typed input accepts `DD/MM/YYYY` and `YYYY-MM-DD`; the calendar emits ISO `YYYY-MM-DD`. DateRangeInput is two DateInputs above a single two-month calendar popover.
- **ConfirmDialog is a primitive.** `<MakerCheckerConfirmDialog>` extends it with the literal copy from `docs/sacco-design-system-v2.md` line 1102 — "This will create an approval request, not execute the action." — and a confirm-button label of "Create Approval Request". The two dialogs share the same underlying `<Dialog>` from sub-plan 04 but the maker-checker variant intentionally cannot be talked out of its copy.
- **MakerCheckerBanner is a controlled banner.** Caller passes `approvalRequestId`, `operationLabel`, `requesterName`, `requestedAt`, `quorumRequired`, `quorumCurrent`. Renders the spec'd warning copy with a "View Approval Request" link. No fetching, no state — the consumer wires it.
- **AuditBar degrades.** Phase 1.7-F (audit-log query API) is still pending. The component renders a fixed placeholder ("Audit history coming soon — backend endpoint pending") plus the "View Full History" affordance disabled. The component's prop shape (`entityType`, `entityId`) matches the future API so feature modules can drop it in now and it lights up the day the backend ships.
- **useDraftAutoSave persists to `localStorage`** under a namespaced key (`sacco_draft:<formKey>`). Debounced 750ms after the last field change. Returns `{ restore, clear, lastSavedAt }`. The restore prompt's UI is the consumer's call (the hook only exposes the data).
- **Stepper is presentational.** Takes `steps: { id, label }[]` + `currentStepId`. Past steps are clickable (consumer wires the click); current is bold; future is greyed. No internal state.

**Tech Stack:** React 19, React Hook Form 7, Zod 3 (already on portal), `react-day-picker` 9, `date-fns` 4 (already in `@sacco/ui`), `@sacco/ui` primitives (Input, Label, Button, Dialog, Popover, Card).

**Portal v1 index reference:** `docs/superpowers/plans/2026-06-02-portal-v1-index.md` §Sub-plan 11.

**Required reading:**
- `docs/sacco-design-system-v2.md` §"Forms" (lines 510-654), §"Maker-Checker UX Patterns" (lines 1118-1175), §"Audit Bar" (lines 1176-1196), §"Maker-Checker Indicators" (lines 1088-1115)
- Sub-plan 09's `currency.ts` registry and `format.ts` helpers (the precision source-of-truth)
- Sub-plan 04's `Input`, `Label`, `Dialog`, `Popover`, `Card` primitives
- React Hook Form `Controller` docs
- `react-day-picker` v9 docs (the API differs from v8)

**Prerequisite:** **Sub-plans 04, 09 must be merged.** Sub-plan 04's base primitives and sub-plan 09's currency registry are direct dependencies.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `admin/packages/ui/package.json` | Modify | Add `react-day-picker`; declare `react-hook-form` peer dep |
| `admin/packages/ui/src/components/FormField/FormField.tsx` | Create | RHF Controller wrapper (label + help + error + aria) |
| `admin/packages/ui/src/components/FormField/FormField.test.tsx` | Create | Tests |
| `admin/packages/ui/src/components/FormField/FormField.stories.tsx` | Create | Stories |
| `admin/packages/ui/src/components/FormField/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/components/MoneyInput/MoneyInput.tsx` | Create | Currency-chip + thousands-separator input |
| `admin/packages/ui/src/components/MoneyInput/MoneyInput.test.tsx` | Create | Tests |
| `admin/packages/ui/src/components/MoneyInput/MoneyInput.stories.tsx` | Create | Stories |
| `admin/packages/ui/src/components/MoneyInput/format-helpers.ts` | Create | Parse/format helpers (separate so they can be unit-tested) |
| `admin/packages/ui/src/components/MoneyInput/format-helpers.test.ts` | Create | Helper tests |
| `admin/packages/ui/src/components/MoneyInput/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/components/PercentageInput/PercentageInput.tsx` | Create | `%`-suffix right-aligned input |
| `admin/packages/ui/src/components/PercentageInput/PercentageInput.test.tsx` | Create | Tests |
| `admin/packages/ui/src/components/PercentageInput/PercentageInput.stories.tsx` | Create | Stories |
| `admin/packages/ui/src/components/PercentageInput/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/components/DateInput/parse-date.ts` | Create | Lenient parser for DD/MM/YYYY + YYYY-MM-DD |
| `admin/packages/ui/src/components/DateInput/parse-date.test.ts` | Create | Parser tests |
| `admin/packages/ui/src/components/DateInput/DateInput.tsx` | Create | Single-date picker + typed input |
| `admin/packages/ui/src/components/DateInput/DateRangeInput.tsx` | Create | Two-input range with shared two-month calendar |
| `admin/packages/ui/src/components/DateInput/DateInput.test.tsx` | Create | Tests |
| `admin/packages/ui/src/components/DateInput/DateInput.stories.tsx` | Create | Stories |
| `admin/packages/ui/src/components/DateInput/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/components/ReadOnlyField/ReadOnlyField.tsx` | Create | Distinct-from-disabled informational field |
| `admin/packages/ui/src/components/ReadOnlyField/ReadOnlyField.test.tsx` | Create | Tests |
| `admin/packages/ui/src/components/ReadOnlyField/ReadOnlyField.stories.tsx` | Create | Stories |
| `admin/packages/ui/src/components/ReadOnlyField/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/components/Stepper/Stepper.tsx` | Create | Multi-step progress component |
| `admin/packages/ui/src/components/Stepper/Stepper.test.tsx` | Create | Tests |
| `admin/packages/ui/src/components/Stepper/Stepper.stories.tsx` | Create | Stories |
| `admin/packages/ui/src/components/Stepper/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/components/ConfirmDialog/ConfirmDialog.tsx` | Create | Base confirm dialog + MakerChecker variant |
| `admin/packages/ui/src/components/ConfirmDialog/ConfirmDialog.test.tsx` | Create | Tests |
| `admin/packages/ui/src/components/ConfirmDialog/ConfirmDialog.stories.tsx` | Create | Stories |
| `admin/packages/ui/src/components/ConfirmDialog/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/components/MakerCheckerBanner/MakerCheckerBanner.tsx` | Create | Pending-approval banner |
| `admin/packages/ui/src/components/MakerCheckerBanner/MakerCheckerBanner.test.tsx` | Create | Tests |
| `admin/packages/ui/src/components/MakerCheckerBanner/MakerCheckerBanner.stories.tsx` | Create | Stories |
| `admin/packages/ui/src/components/MakerCheckerBanner/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/components/AuditBar/AuditBar.tsx` | Create | Placeholder until P1.7-F ships |
| `admin/packages/ui/src/components/AuditBar/AuditBar.test.tsx` | Create | Tests |
| `admin/packages/ui/src/components/AuditBar/AuditBar.stories.tsx` | Create | Stories |
| `admin/packages/ui/src/components/AuditBar/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/hooks/use-draft-autosave.ts` | Create | localStorage-backed draft persistence hook |
| `admin/packages/ui/src/hooks/use-draft-autosave.test.ts` | Create | Hook tests |
| `admin/packages/ui/src/hooks/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/index.ts` | Modify | Re-export new components + hooks |
| `CLAUDE.md` | Modify | Append contract U (form primitives), V (maker-checker UX wiring), W (audit bar contract) |

---

## Task 1: Deps + FormField (RHF Controller wrapper)

**Files:**
- Modify: `admin/packages/ui/package.json`
- Create: `admin/packages/ui/src/components/FormField/{FormField.tsx,FormField.test.tsx,FormField.stories.tsx,index.ts}`

- [ ] **Step 1: Add deps**

In `admin/packages/ui/package.json` `dependencies` add:

```json
"react-day-picker": "^9.0.0"
```

In `peerDependencies` add:

```json
"react-hook-form": "^7.53.0"
```

In `devDependencies` add (for tests/stories that need RHF locally):

```json
"react-hook-form": "^7.53.0"
```

Install:

```bash
cd admin
pnpm install
```

- [ ] **Step 2: FormField implementation**

```tsx
// admin/packages/ui/src/components/FormField/FormField.tsx
"use client";

import { type ReactElement, useId } from "react";
import {
  Controller,
  type Control,
  type ControllerRenderProps,
  type FieldPath,
  type FieldValues,
} from "react-hook-form";
import { cn } from "../../utils/cn";
import { Label } from "../Label";

export interface FormFieldProps<
  TFieldValues extends FieldValues,
  TName extends FieldPath<TFieldValues>,
> {
  control: Control<TFieldValues>;
  name: TName;
  label: string;
  /** Marks the field as required + appends the asterisk per spec line 542-546. */
  required?: boolean;
  helpText?: string;
  /** Renders the inner field. Receives the RHF field handlers + a stable id. */
  render(args: {
    field: ControllerRenderProps<TFieldValues, TName>;
    id: string;
    describedBy: string | undefined;
    invalid: boolean;
  }): ReactElement;
  className?: string;
}

export function FormField<
  TFieldValues extends FieldValues,
  TName extends FieldPath<TFieldValues>,
>({
  control,
  name,
  label,
  required = false,
  helpText,
  render,
  className,
}: FormFieldProps<TFieldValues, TName>) {
  const generatedId = useId();
  const id = `field-${generatedId}`;
  const helpId = helpText ? `${id}-help` : undefined;
  const errorId = `${id}-error`;
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => {
        const invalid = Boolean(fieldState.error);
        const describedBy = invalid
          ? errorId
          : helpId;
        return (
          <div className={cn("flex flex-col gap-1.5", className)}>
            <Label htmlFor={id}>
              {label}
              {required ? (
                <span
                  aria-hidden="true"
                  className="ml-0.5 text-[var(--text-danger)]"
                >
                  *
                </span>
              ) : null}
            </Label>
            {render({ field, id, describedBy, invalid })}
            {invalid ? (
              <p
                id={errorId}
                role="alert"
                className="text-[12px] text-[var(--text-danger)]"
              >
                {fieldState.error?.message ?? "Invalid value"}
              </p>
            ) : helpText ? (
              <p
                id={helpId}
                className="text-[12px] text-[var(--text-tertiary)]"
              >
                {helpText}
              </p>
            ) : null}
          </div>
        );
      }}
    />
  );
}
```

- [ ] **Step 3: Test harness + tests**

```tsx
// admin/packages/ui/src/components/FormField/FormField.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { FormField } from "./FormField";
import { Input } from "../Input";

interface Values {
  name: string;
}

function Harness({
  defaultValues = { name: "" },
  required = false,
  helpText,
}: {
  defaultValues?: Values;
  required?: boolean;
  helpText?: string;
}) {
  const { control, handleSubmit } = useForm<Values>({
    defaultValues,
    mode: "onBlur",
  });
  return (
    <form
      onSubmit={handleSubmit(() => {})}
      noValidate
    >
      <FormField
        control={control}
        name="name"
        label="Full name"
        required={required}
        helpText={helpText}
        render={({ field, id, describedBy, invalid }) => (
          <Input
            id={id}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            {...field}
          />
        )}
      />
      <button type="submit">Submit</button>
    </form>
  );
}

describe("FormField", () => {
  it("renders the label and wires htmlFor → id", () => {
    render(<Harness />);
    const input = screen.getByLabelText("Full name");
    expect(input).toBeInTheDocument();
  });

  it("renders the required asterisk when required", () => {
    render(<Harness required />);
    expect(screen.getByText("*")).toBeInTheDocument();
  });

  it("renders help text linked via aria-describedby", () => {
    render(<Harness helpText="Use your government name." />);
    const input = screen.getByLabelText("Full name");
    const helpId = input.getAttribute("aria-describedby");
    expect(helpId).toBeTruthy();
    expect(document.getElementById(helpId!)?.textContent).toBe(
      "Use your government name.",
    );
  });

  it("surfaces RHF errors with role=alert + aria-describedby points at error", async () => {
    function ErrorHarness() {
      const { control, handleSubmit, setError } = useForm<Values>({
        defaultValues: { name: "" },
      });
      return (
        <form
          onSubmit={handleSubmit(() => {
            setError("name", { type: "manual", message: "Name is required" });
          })}
        >
          <FormField
            control={control}
            name="name"
            label="Full name"
            render={({ field, id, describedBy, invalid }) => (
              <Input
                id={id}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                {...field}
              />
            )}
          />
          <button type="submit">Submit</button>
        </form>
      );
    }
    render(<ErrorHarness />);
    await userEvent.click(screen.getByText("Submit"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Name is required");
    expect(screen.getByLabelText("Full name")).toHaveAttribute(
      "aria-describedby",
      alert.id,
    );
  });
});
```

- [ ] **Step 4: Stories + index**

```tsx
// admin/packages/ui/src/components/FormField/FormField.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { useForm } from "react-hook-form";
import { FormField } from "./FormField";
import { Input } from "../Input";

const meta: Meta<typeof FormField> = {
  title: "Forms/FormField",
  component: FormField,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj;

function Demo({
  required,
  helpText,
}: {
  required?: boolean;
  helpText?: string;
}) {
  const { control } = useForm<{ name: string }>({ defaultValues: { name: "" } });
  return (
    <div style={{ maxWidth: 360 }}>
      <FormField
        control={control}
        name="name"
        label="Member full name"
        required={required}
        helpText={helpText}
        render={({ field, id, describedBy, invalid }) => (
          <Input
            id={id}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            placeholder="Mary Akello"
            {...field}
          />
        )}
      />
    </div>
  );
}

export const Default: Story = { render: () => <Demo /> };
export const Required: Story = { render: () => <Demo required /> };
export const WithHelp: Story = {
  render: () => <Demo helpText="As it appears on national ID." />,
};
```

```typescript
// admin/packages/ui/src/components/FormField/index.ts
export { FormField, type FormFieldProps } from "./FormField";
```

- [ ] **Step 5: Re-export + verify + commit**

In `admin/packages/ui/src/index.ts` append:

```typescript
export * from "./components/FormField";
```

```bash
cd admin
pnpm --filter @sacco/ui typecheck
pnpm --filter @sacco/ui test
```
Expected: green.

```bash
git add admin/packages/ui/package.json admin/pnpm-lock.yaml \
        admin/packages/ui/src/components/FormField/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): FormField — RHF Controller wrapper with label/help/error/aria"
```

---

## Task 2: MoneyInput + PercentageInput

**Files:**
- Create: `admin/packages/ui/src/components/MoneyInput/{format-helpers.ts,format-helpers.test.ts,MoneyInput.tsx,MoneyInput.test.tsx,MoneyInput.stories.tsx,index.ts}`
- Create: `admin/packages/ui/src/components/PercentageInput/{PercentageInput.tsx,PercentageInput.test.tsx,PercentageInput.stories.tsx,index.ts}`

- [ ] **Step 1: Money format helpers (parse + format)**

```typescript
// admin/packages/ui/src/components/MoneyInput/format-helpers.ts
import { getCurrencyConfig } from "../../utils/currency";

/**
 * Strip everything except digits, decimal point, and leading minus.
 * Tolerates the user pasting "UGX 1,234.50" or typing as they go.
 */
export function stripFormatting(input: string): string {
  if (!input) return "";
  const leadingMinus = input.trimStart().startsWith("-") ? "-" : "";
  const digits = input.replace(/[^0-9.]/g, "");
  // Collapse multiple dots to the first one only.
  const firstDot = digits.indexOf(".");
  if (firstDot === -1) return `${leadingMinus}${digits}`;
  const integer = digits.slice(0, firstDot);
  const fraction = digits.slice(firstDot + 1).replace(/\./g, "");
  return `${leadingMinus}${integer}.${fraction}`;
}

/**
 * Add thousands separators while the user types. Preserves a trailing dot
 * and trailing zeros so "12." doesn't collapse to "12".
 */
export function formatTyping(stripped: string): string {
  if (!stripped) return "";
  const negative = stripped.startsWith("-");
  const body = negative ? stripped.slice(1) : stripped;
  const [intPart, fracPart] = body.split(".");
  const withThousands = (intPart ?? "").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const result =
    fracPart === undefined ? withThousands : `${withThousands}.${fracPart}`;
  return `${negative ? "-" : ""}${result}`;
}

/**
 * On blur, canonicalise to the currency's decimal precision.
 * "12" + UGX (0 decimals) → "12"
 * "12" + USD (2 decimals) → "12.00"
 * "12.5" + USD → "12.50"
 * "12.567" + USD → "12.57"  (banker's rounding NOT used; standard half-up)
 * "" → ""  (we leave empty values untouched so RHF can flag "required")
 */
export function canonicalise(
  stripped: string,
  currencyCode: string,
): string {
  if (!stripped || stripped === "-") return "";
  const config = getCurrencyConfig(currencyCode);
  const numeric = Number.parseFloat(stripped);
  if (!Number.isFinite(numeric)) return "";
  return numeric.toFixed(config.decimals);
}
```

- [ ] **Step 2: Helper tests**

```typescript
// admin/packages/ui/src/components/MoneyInput/format-helpers.test.ts
import { describe, expect, it } from "vitest";
import { canonicalise, formatTyping, stripFormatting } from "./format-helpers";

describe("stripFormatting", () => {
  it("strips commas and spaces", () => {
    expect(stripFormatting("1,234,567")).toBe("1234567");
    expect(stripFormatting("UGX 1 234")).toBe("1234");
  });
  it("preserves a leading minus", () => {
    expect(stripFormatting("-1,234")).toBe("-1234");
  });
  it("collapses multiple decimal points to the first", () => {
    expect(stripFormatting("1.2.3")).toBe("1.23");
  });
  it("returns empty for empty input", () => {
    expect(stripFormatting("")).toBe("");
  });
});

describe("formatTyping", () => {
  it("inserts thousands separators", () => {
    expect(formatTyping("1234567")).toBe("1,234,567");
  });
  it("preserves a trailing decimal point", () => {
    expect(formatTyping("12.")).toBe("12.");
  });
  it("preserves trailing zeros in the fractional part", () => {
    expect(formatTyping("12.50")).toBe("12.50");
  });
  it("handles negative", () => {
    expect(formatTyping("-1234")).toBe("-1,234");
  });
  it("returns empty for empty input", () => {
    expect(formatTyping("")).toBe("");
  });
});

describe("canonicalise", () => {
  it("UGX → 0 decimals", () => {
    expect(canonicalise("12", "UGX")).toBe("12");
    expect(canonicalise("12.5", "UGX")).toBe("13");
  });
  it("USD → 2 decimals", () => {
    expect(canonicalise("12", "USD")).toBe("12.00");
    expect(canonicalise("12.5", "USD")).toBe("12.50");
    expect(canonicalise("12.567", "USD")).toBe("12.57");
  });
  it("empty string stays empty (so 'required' can fire)", () => {
    expect(canonicalise("", "UGX")).toBe("");
    expect(canonicalise("-", "UGX")).toBe("");
  });
});
```

- [ ] **Step 3: MoneyInput component**

```tsx
// admin/packages/ui/src/components/MoneyInput/MoneyInput.tsx
"use client";

import {
  forwardRef,
  useCallback,
  useState,
  type ChangeEvent,
  type FocusEvent,
  type InputHTMLAttributes,
} from "react";
import { cn } from "../../utils/cn";
import { useTenantCurrency } from "../../context/TenantCurrency";
import { canonicalise, formatTyping, stripFormatting } from "./format-helpers";

export interface MoneyInputProps
  extends Omit<
    InputHTMLAttributes<HTMLInputElement>,
    "value" | "onChange" | "type"
  > {
  /** Decimal-as-string. Empty string means no value. */
  value: string;
  onValueChange(next: string): void;
  /** Override the provider's currency. */
  currency?: string;
  /** Permit a leading minus sign. Default false. */
  allowNegative?: boolean;
}

export const MoneyInput = forwardRef<HTMLInputElement, MoneyInputProps>(
  function MoneyInput(
    {
      value,
      onValueChange,
      currency,
      allowNegative = false,
      onBlur,
      className,
      ...rest
    },
    ref,
  ) {
    const provider = useTenantCurrency();
    const effectiveCurrency = currency ?? provider.currency;

    // The visible string includes thousands separators; the value prop
    // is the canonical Decimal-as-string. We re-derive the visible string
    // whenever value changes externally.
    const [display, setDisplay] = useState(() => formatTyping(value));
    // When the controlled value changes from the outside, re-sync.
    // Use a ref-style comparison to avoid loops.
    if (formatTyping(stripFormatting(display)) !== formatTyping(value)) {
      // External change — sync.
      setDisplay(formatTyping(value));
    }

    const onChange = useCallback(
      (e: ChangeEvent<HTMLInputElement>) => {
        let stripped = stripFormatting(e.target.value);
        if (!allowNegative && stripped.startsWith("-")) {
          stripped = stripped.slice(1);
        }
        setDisplay(formatTyping(stripped));
        onValueChange(stripped);
      },
      [allowNegative, onValueChange],
    );

    const handleBlur = useCallback(
      (e: FocusEvent<HTMLInputElement>) => {
        const stripped = stripFormatting(display);
        const canonical = canonicalise(stripped, effectiveCurrency);
        setDisplay(formatTyping(canonical));
        onValueChange(canonical);
        onBlur?.(e);
      },
      [display, effectiveCurrency, onBlur, onValueChange],
    );

    return (
      <div
        className={cn(
          "flex h-[var(--height-control-md)] items-center gap-2 rounded-[var(--radius-md)]",
          "border border-[var(--border-default)] bg-[var(--surface-elevated)]",
          "focus-within:border-[var(--border-focus)] focus-within:shadow-[var(--shadow-focus)]",
          "px-3",
          className,
        )}
      >
        <span
          aria-hidden="true"
          className="select-none rounded-[var(--radius-sm)] bg-[var(--surface-sunken)] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]"
        >
          {effectiveCurrency}
        </span>
        <input
          ref={ref}
          inputMode="decimal"
          autoComplete="off"
          className={cn(
            "h-full flex-1 bg-transparent text-right text-[14px] outline-none",
            "[font-feature-settings:'tnum'_1,'lnum'_1]",
            "[appearance:textfield] [-webkit-appearance:textfield]",
            "[&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none",
          )}
          value={display}
          onChange={onChange}
          onBlur={handleBlur}
          {...rest}
        />
      </div>
    );
  },
);
```

- [ ] **Step 4: MoneyInput tests**

```tsx
// admin/packages/ui/src/components/MoneyInput/MoneyInput.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MoneyInput } from "./MoneyInput";
import { TenantCurrencyProvider } from "../../context/TenantCurrency";

function Controlled({
  initial = "",
  currency,
  allowNegative,
}: {
  initial?: string;
  currency?: string;
  allowNegative?: boolean;
}) {
  const [value, setValue] = useState(initial);
  return (
    <div>
      <MoneyInput
        value={value}
        onValueChange={setValue}
        currency={currency}
        allowNegative={allowNegative}
        aria-label="amount"
      />
      <p data-testid="state">{value}</p>
    </div>
  );
}

describe("MoneyInput", () => {
  it("shows the currency chip from the provider when no prop", () => {
    render(
      <TenantCurrencyProvider currency="KES">
        <Controlled />
      </TenantCurrencyProvider>,
    );
    expect(screen.getByText("KES")).toBeInTheDocument();
  });

  it("formats with thousands separators as the user types", async () => {
    const user = userEvent.setup();
    render(<Controlled currency="UGX" />);
    const input = screen.getByLabelText("amount") as HTMLInputElement;
    await user.type(input, "1234567");
    expect(input.value).toBe("1,234,567");
    // Underlying state is the stripped value.
    expect(screen.getByTestId("state").textContent).toBe("1234567");
  });

  it("canonicalises on blur — UGX → no decimals", async () => {
    const user = userEvent.setup();
    render(<Controlled currency="UGX" />);
    const input = screen.getByLabelText("amount") as HTMLInputElement;
    await user.type(input, "12");
    await user.tab();
    expect(input.value).toBe("12");
    expect(screen.getByTestId("state").textContent).toBe("12");
  });

  it("canonicalises on blur — USD → 2 decimals", async () => {
    const user = userEvent.setup();
    render(<Controlled currency="USD" />);
    const input = screen.getByLabelText("amount") as HTMLInputElement;
    await user.type(input, "12");
    await user.tab();
    expect(input.value).toBe("12.00");
    expect(screen.getByTestId("state").textContent).toBe("12.00");
  });

  it("blocks the minus sign by default", async () => {
    const user = userEvent.setup();
    render(<Controlled currency="USD" />);
    const input = screen.getByLabelText("amount") as HTMLInputElement;
    await user.type(input, "-50");
    expect(input.value).toBe("50");
  });

  it("permits negative when allowNegative", async () => {
    const user = userEvent.setup();
    render(<Controlled currency="USD" allowNegative />);
    const input = screen.getByLabelText("amount") as HTMLInputElement;
    await user.type(input, "-50");
    expect(input.value).toBe("-50");
  });

  it("calls onBlur passthrough", async () => {
    const onBlur = vi.fn();
    const user = userEvent.setup();
    function H() {
      const [v, set] = useState("");
      return (
        <MoneyInput
          value={v}
          onValueChange={set}
          currency="USD"
          aria-label="amount"
          onBlur={onBlur}
        />
      );
    }
    render(<H />);
    await user.type(screen.getByLabelText("amount"), "1");
    await user.tab();
    expect(onBlur).toHaveBeenCalled();
  });
});
```

- [ ] **Step 5: MoneyInput stories**

```tsx
// admin/packages/ui/src/components/MoneyInput/MoneyInput.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { MoneyInput } from "./MoneyInput";
import { TenantCurrencyProvider } from "../../context/TenantCurrency";

const meta: Meta<typeof MoneyInput> = {
  title: "Forms/MoneyInput",
  component: MoneyInput,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

function Demo({
  currency,
  allowNegative,
}: {
  currency?: string;
  allowNegative?: boolean;
}) {
  const [value, setValue] = useState("");
  return (
    <div style={{ width: 280 }}>
      <MoneyInput
        value={value}
        onValueChange={setValue}
        currency={currency}
        allowNegative={allowNegative}
        aria-label="amount"
      />
      <p style={{ marginTop: 8, fontSize: 12 }}>state: {JSON.stringify(value)}</p>
    </div>
  );
}

export const UGX: Story = { render: () => <Demo currency="UGX" /> };
export const USD: Story = { render: () => <Demo currency="USD" /> };
export const AllowNegative: Story = {
  render: () => <Demo currency="USD" allowNegative />,
};
export const FromProvider: Story = {
  render: () => (
    <TenantCurrencyProvider currency="KES">
      <Demo />
    </TenantCurrencyProvider>
  ),
};
```

- [ ] **Step 6: MoneyInput index**

```typescript
// admin/packages/ui/src/components/MoneyInput/index.ts
export { MoneyInput, type MoneyInputProps } from "./MoneyInput";
```

- [ ] **Step 7: PercentageInput component**

```tsx
// admin/packages/ui/src/components/PercentageInput/PercentageInput.tsx
"use client";

import {
  forwardRef,
  useCallback,
  type ChangeEvent,
  type FocusEvent,
  type InputHTMLAttributes,
} from "react";
import { cn } from "../../utils/cn";

export interface PercentageInputProps
  extends Omit<
    InputHTMLAttributes<HTMLInputElement>,
    "value" | "onChange" | "type"
  > {
  /** Decimal-as-string. Empty string means no value. */
  value: string;
  onValueChange(next: string): void;
  /** Clamp to [min, max] on blur. Defaults to [0, 100]. */
  min?: number;
  max?: number;
}

/** Strip everything except digits + a single decimal point. */
function strip(input: string): string {
  const digits = input.replace(/[^0-9.]/g, "");
  const firstDot = digits.indexOf(".");
  if (firstDot === -1) return digits;
  return `${digits.slice(0, firstDot)}.${digits
    .slice(firstDot + 1)
    .replace(/\./g, "")}`;
}

/** Truncate the fractional part to 2 digits. */
function clampDecimals(s: string): string {
  const [a, b] = s.split(".");
  if (b === undefined) return a ?? "";
  return `${a}.${b.slice(0, 2)}`;
}

export const PercentageInput = forwardRef<HTMLInputElement, PercentageInputProps>(
  function PercentageInput(
    { value, onValueChange, min = 0, max = 100, onBlur, className, ...rest },
    ref,
  ) {
    const onChange = useCallback(
      (e: ChangeEvent<HTMLInputElement>) => {
        const next = clampDecimals(strip(e.target.value));
        onValueChange(next);
      },
      [onValueChange],
    );

    const handleBlur = useCallback(
      (e: FocusEvent<HTMLInputElement>) => {
        if (value === "") {
          onBlur?.(e);
          return;
        }
        const numeric = Number.parseFloat(value);
        if (!Number.isFinite(numeric)) {
          onValueChange("");
          onBlur?.(e);
          return;
        }
        const clamped = Math.min(max, Math.max(min, numeric));
        onValueChange(clamped.toFixed(2));
        onBlur?.(e);
      },
      [max, min, onBlur, onValueChange, value],
    );

    return (
      <div
        className={cn(
          "flex h-[var(--height-control-md)] items-center gap-2 rounded-[var(--radius-md)]",
          "border border-[var(--border-default)] bg-[var(--surface-elevated)]",
          "focus-within:border-[var(--border-focus)] focus-within:shadow-[var(--shadow-focus)]",
          "px-3",
          className,
        )}
      >
        <input
          ref={ref}
          inputMode="decimal"
          autoComplete="off"
          className={cn(
            "h-full flex-1 bg-transparent text-right text-[14px] outline-none",
            "[font-feature-settings:'tnum'_1,'lnum'_1]",
            "[appearance:textfield] [-webkit-appearance:textfield]",
            "[&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none",
          )}
          value={value}
          onChange={onChange}
          onBlur={handleBlur}
          {...rest}
        />
        <span
          aria-hidden="true"
          className="select-none text-[13px] text-[var(--text-tertiary)]"
        >
          %
        </span>
      </div>
    );
  },
);
```

- [ ] **Step 8: PercentageInput tests + stories + index**

```tsx
// admin/packages/ui/src/components/PercentageInput/PercentageInput.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { PercentageInput } from "./PercentageInput";

function Controlled({ min, max }: { min?: number; max?: number }) {
  const [v, set] = useState("");
  return (
    <div>
      <PercentageInput
        value={v}
        onValueChange={set}
        min={min}
        max={max}
        aria-label="rate"
      />
      <p data-testid="state">{v}</p>
    </div>
  );
}

describe("PercentageInput", () => {
  it("renders the % suffix", () => {
    render(<Controlled />);
    expect(screen.getByText("%")).toBeInTheDocument();
  });

  it("truncates beyond 2 decimal places", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const input = screen.getByLabelText("rate") as HTMLInputElement;
    await user.type(input, "12.345");
    expect(input.value).toBe("12.34");
  });

  it("canonicalises to 2 decimals on blur", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const input = screen.getByLabelText("rate") as HTMLInputElement;
    await user.type(input, "5");
    await user.tab();
    expect(input.value).toBe("5.00");
  });

  it("clamps to [min, max] on blur", async () => {
    const user = userEvent.setup();
    render(<Controlled min={0} max={100} />);
    const input = screen.getByLabelText("rate") as HTMLInputElement;
    await user.type(input, "150");
    await user.tab();
    expect(input.value).toBe("100.00");
  });
});
```

```tsx
// admin/packages/ui/src/components/PercentageInput/PercentageInput.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { PercentageInput } from "./PercentageInput";

const meta: Meta<typeof PercentageInput> = {
  title: "Forms/PercentageInput",
  component: PercentageInput,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

function Demo() {
  const [v, set] = useState("");
  return (
    <div style={{ width: 200 }}>
      <PercentageInput value={v} onValueChange={set} aria-label="rate" />
      <p style={{ marginTop: 8, fontSize: 12 }}>state: {JSON.stringify(v)}</p>
    </div>
  );
}

export const Default: Story = { render: () => <Demo /> };
```

```typescript
// admin/packages/ui/src/components/PercentageInput/index.ts
export {
  PercentageInput,
  type PercentageInputProps,
} from "./PercentageInput";
```

- [ ] **Step 9: Re-export + verify + commit**

In `admin/packages/ui/src/index.ts` append:

```typescript
export * from "./components/MoneyInput";
export * from "./components/PercentageInput";
```

```bash
cd admin
pnpm --filter @sacco/ui test
```

```bash
git add admin/packages/ui/src/components/MoneyInput/ \
        admin/packages/ui/src/components/PercentageInput/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): MoneyInput + PercentageInput"
```

---

## Task 3: DateInput + DateRangeInput

**Files:**
- Create: `admin/packages/ui/src/components/DateInput/{parse-date.ts,parse-date.test.ts,DateInput.tsx,DateRangeInput.tsx,DateInput.test.tsx,DateInput.stories.tsx,index.ts}`

- [ ] **Step 1: Lenient date parser**

```typescript
// admin/packages/ui/src/components/DateInput/parse-date.ts
import { isValid, parse } from "date-fns";

/**
 * Accept "DD/MM/YYYY" or "YYYY-MM-DD" (the design-system spec, line 603).
 * Returns the ISO date string ("YYYY-MM-DD") on success, null on failure.
 */
export function parseTypedDate(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  for (const fmt of ["yyyy-MM-dd", "dd/MM/yyyy"] as const) {
    const parsed = parse(trimmed, fmt, new Date());
    if (isValid(parsed)) {
      const yyyy = parsed.getFullYear().toString().padStart(4, "0");
      const mm = (parsed.getMonth() + 1).toString().padStart(2, "0");
      const dd = parsed.getDate().toString().padStart(2, "0");
      return `${yyyy}-${mm}-${dd}`;
    }
  }
  return null;
}

/** Format an ISO date as `28 May 2026` (display) or `DD/MM/YYYY` (typed). */
export function formatDateForInput(iso: string): string {
  if (!iso) return "";
  const [yyyy, mm, dd] = iso.split("-");
  if (!yyyy || !mm || !dd) return "";
  return `${dd}/${mm}/${yyyy}`;
}
```

- [ ] **Step 2: Parser tests**

```typescript
// admin/packages/ui/src/components/DateInput/parse-date.test.ts
import { describe, expect, it } from "vitest";
import { formatDateForInput, parseTypedDate } from "./parse-date";

describe("parseTypedDate", () => {
  it("accepts YYYY-MM-DD", () => {
    expect(parseTypedDate("2026-05-28")).toBe("2026-05-28");
  });
  it("accepts DD/MM/YYYY", () => {
    expect(parseTypedDate("28/05/2026")).toBe("2026-05-28");
  });
  it("returns null for nonsense", () => {
    expect(parseTypedDate("yesterday")).toBeNull();
    expect(parseTypedDate("32/13/2026")).toBeNull();
    expect(parseTypedDate("")).toBeNull();
  });
});

describe("formatDateForInput", () => {
  it("formats ISO as DD/MM/YYYY", () => {
    expect(formatDateForInput("2026-05-28")).toBe("28/05/2026");
  });
  it("returns empty for empty input", () => {
    expect(formatDateForInput("")).toBe("");
  });
});
```

- [ ] **Step 3: DateInput component**

```tsx
// admin/packages/ui/src/components/DateInput/DateInput.tsx
"use client";

import { CalendarDays } from "lucide-react";
import {
  forwardRef,
  useState,
  type ChangeEvent,
  type FocusEvent,
  type InputHTMLAttributes,
} from "react";
import { DayPicker } from "react-day-picker";
import "react-day-picker/style.css";
import { cn } from "../../utils/cn";
import { Popover, PopoverContent, PopoverTrigger } from "../Popover";
import { formatDateForInput, parseTypedDate } from "./parse-date";

export interface DateInputProps
  extends Omit<
    InputHTMLAttributes<HTMLInputElement>,
    "value" | "onChange" | "type"
  > {
  /** ISO date YYYY-MM-DD. Empty string = no date. */
  value: string;
  onValueChange(next: string): void;
}

export const DateInput = forwardRef<HTMLInputElement, DateInputProps>(
  function DateInput(
    { value, onValueChange, onBlur, className, ...rest },
    ref,
  ) {
    const [open, setOpen] = useState(false);
    const [typed, setTyped] = useState(() => formatDateForInput(value));

    // Re-sync when the controlled value changes externally.
    if (formatDateForInput(value) !== typed && !open) {
      setTyped(formatDateForInput(value));
    }

    const onTypedChange = (e: ChangeEvent<HTMLInputElement>) => {
      setTyped(e.target.value);
    };

    const handleBlur = (e: FocusEvent<HTMLInputElement>) => {
      const parsed = parseTypedDate(typed);
      if (parsed) {
        onValueChange(parsed);
        setTyped(formatDateForInput(parsed));
      } else if (typed.trim() === "") {
        onValueChange("");
      } else {
        // Invalid — revert to last known value.
        setTyped(formatDateForInput(value));
      }
      onBlur?.(e);
    };

    return (
      <div
        className={cn(
          "flex h-[var(--height-control-md)] items-center gap-2 rounded-[var(--radius-md)]",
          "border border-[var(--border-default)] bg-[var(--surface-elevated)]",
          "focus-within:border-[var(--border-focus)] focus-within:shadow-[var(--shadow-focus)]",
          "px-3",
          className,
        )}
      >
        <input
          ref={ref}
          className="h-full flex-1 bg-transparent text-[14px] outline-none [font-feature-settings:'tnum'_1,'lnum'_1]"
          placeholder="DD/MM/YYYY"
          value={typed}
          onChange={onTypedChange}
          onBlur={handleBlur}
          {...rest}
        />
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label="Open calendar"
              className="grid h-6 w-6 place-content-center rounded-[var(--radius-sm)] text-[var(--icon-default)] hover:bg-[var(--surface-hover)]"
            >
              <CalendarDays size={16} strokeWidth={1.75} />
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="p-2">
            <DayPicker
              mode="single"
              selected={value ? new Date(`${value}T00:00:00`) : undefined}
              onSelect={(date) => {
                if (!date) return;
                const yyyy = date.getFullYear().toString().padStart(4, "0");
                const mm = (date.getMonth() + 1).toString().padStart(2, "0");
                const dd = date.getDate().toString().padStart(2, "0");
                const iso = `${yyyy}-${mm}-${dd}`;
                onValueChange(iso);
                setTyped(formatDateForInput(iso));
                setOpen(false);
              }}
            />
          </PopoverContent>
        </Popover>
      </div>
    );
  },
);
```

- [ ] **Step 4: DateRangeInput component**

```tsx
// admin/packages/ui/src/components/DateInput/DateRangeInput.tsx
"use client";

import { CalendarDays } from "lucide-react";
import { useState } from "react";
import { DayPicker, type DateRange } from "react-day-picker";
import "react-day-picker/style.css";
import { cn } from "../../utils/cn";
import { Popover, PopoverContent, PopoverTrigger } from "../Popover";
import { formatDateForInput, parseTypedDate } from "./parse-date";

export interface DateRangeValue {
  from: string;
  to: string;
}

export interface DateRangeInputProps {
  value: DateRangeValue;
  onValueChange(next: DateRangeValue): void;
  className?: string;
  /** Aria label for the popover trigger. */
  triggerAriaLabel?: string;
}

export function DateRangeInput({
  value,
  onValueChange,
  className,
  triggerAriaLabel = "Open date range calendar",
}: DateRangeInputProps) {
  const [open, setOpen] = useState(false);
  const [fromTyped, setFromTyped] = useState(formatDateForInput(value.from));
  const [toTyped, setToTyped] = useState(formatDateForInput(value.to));

  const commit = (key: "from" | "to", typed: string) => {
    const parsed = parseTypedDate(typed);
    if (parsed) {
      onValueChange({ ...value, [key]: parsed });
    } else if (typed.trim() === "") {
      onValueChange({ ...value, [key]: "" });
    }
  };

  const selected: DateRange | undefined =
    value.from || value.to
      ? {
          from: value.from ? new Date(`${value.from}T00:00:00`) : undefined,
          to: value.to ? new Date(`${value.to}T00:00:00`) : undefined,
        }
      : undefined;

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <input
        aria-label="From"
        placeholder="DD/MM/YYYY"
        value={fromTyped}
        onChange={(e) => setFromTyped(e.target.value)}
        onBlur={() => commit("from", fromTyped)}
        className="h-[var(--height-control-md)] w-[140px] rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--surface-elevated)] px-3 text-[14px] outline-none focus:border-[var(--border-focus)]"
      />
      <span aria-hidden="true" className="text-[var(--text-tertiary)]">
        →
      </span>
      <input
        aria-label="To"
        placeholder="DD/MM/YYYY"
        value={toTyped}
        onChange={(e) => setToTyped(e.target.value)}
        onBlur={() => commit("to", toTyped)}
        className="h-[var(--height-control-md)] w-[140px] rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--surface-elevated)] px-3 text-[14px] outline-none focus:border-[var(--border-focus)]"
      />
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={triggerAriaLabel}
            className="grid h-[var(--height-control-md)] w-[var(--height-control-md)] place-content-center rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--surface-elevated)] text-[var(--icon-default)] hover:bg-[var(--surface-hover)]"
          >
            <CalendarDays size={16} strokeWidth={1.75} />
          </button>
        </PopoverTrigger>
        <PopoverContent align="end" className="p-2">
          <DayPicker
            mode="range"
            numberOfMonths={2}
            selected={selected}
            onSelect={(range) => {
              if (!range) return;
              const fmt = (d?: Date) => {
                if (!d) return "";
                const y = d.getFullYear().toString().padStart(4, "0");
                const m = (d.getMonth() + 1).toString().padStart(2, "0");
                const dd = d.getDate().toString().padStart(2, "0");
                return `${y}-${m}-${dd}`;
              };
              const next = { from: fmt(range.from), to: fmt(range.to) };
              onValueChange(next);
              setFromTyped(formatDateForInput(next.from));
              setToTyped(formatDateForInput(next.to));
            }}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
```

- [ ] **Step 5: DateInput tests**

```tsx
// admin/packages/ui/src/components/DateInput/DateInput.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { DateInput } from "./DateInput";

function Controlled({ initial = "" }: { initial?: string }) {
  const [v, set] = useState(initial);
  return (
    <div>
      <DateInput value={v} onValueChange={set} aria-label="date" />
      <p data-testid="state">{v}</p>
    </div>
  );
}

describe("DateInput", () => {
  it("hydrates from an ISO value", () => {
    render(<Controlled initial="2026-05-28" />);
    expect(screen.getByLabelText("date")).toHaveValue("28/05/2026");
  });

  it("accepts a typed DD/MM/YYYY and emits ISO", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const input = screen.getByLabelText("date") as HTMLInputElement;
    await user.type(input, "28/05/2026");
    await user.tab();
    expect(screen.getByTestId("state").textContent).toBe("2026-05-28");
  });

  it("accepts a typed YYYY-MM-DD and emits ISO", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const input = screen.getByLabelText("date") as HTMLInputElement;
    await user.type(input, "2026-05-28");
    await user.tab();
    expect(screen.getByTestId("state").textContent).toBe("2026-05-28");
  });

  it("reverts to the last known value on garbage input", async () => {
    const user = userEvent.setup();
    render(<Controlled initial="2026-05-28" />);
    const input = screen.getByLabelText("date") as HTMLInputElement;
    await user.clear(input);
    await user.type(input, "yesterday");
    await user.tab();
    expect(input.value).toBe("28/05/2026");
  });
});
```

- [ ] **Step 6: Stories + index**

```tsx
// admin/packages/ui/src/components/DateInput/DateInput.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { DateInput } from "./DateInput";
import { DateRangeInput, type DateRangeValue } from "./DateRangeInput";

const meta: Meta<typeof DateInput> = {
  title: "Forms/DateInput",
  component: DateInput,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

function Single() {
  const [v, set] = useState("");
  return (
    <div style={{ width: 260 }}>
      <DateInput value={v} onValueChange={set} aria-label="date" />
      <p style={{ marginTop: 8, fontSize: 12 }}>state: {JSON.stringify(v)}</p>
    </div>
  );
}

function Range() {
  const [v, set] = useState<DateRangeValue>({ from: "", to: "" });
  return (
    <div>
      <DateRangeInput value={v} onValueChange={set} />
      <p style={{ marginTop: 8, fontSize: 12 }}>state: {JSON.stringify(v)}</p>
    </div>
  );
}

export const Single_: Story = { name: "Single", render: () => <Single /> };
export const RangeTwoMonth: Story = { render: () => <Range /> };
```

```typescript
// admin/packages/ui/src/components/DateInput/index.ts
export { DateInput, type DateInputProps } from "./DateInput";
export {
  DateRangeInput,
  type DateRangeInputProps,
  type DateRangeValue,
} from "./DateRangeInput";
```

- [ ] **Step 7: Re-export + verify + commit**

In `admin/packages/ui/src/index.ts` append:

```typescript
export * from "./components/DateInput";
```

```bash
cd admin
pnpm --filter @sacco/ui test
```

```bash
git add admin/packages/ui/src/components/DateInput/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): DateInput + DateRangeInput (typed + calendar)"
```

---

## Task 4: ReadOnlyField + Stepper

**Files:**
- Create: `admin/packages/ui/src/components/ReadOnlyField/{ReadOnlyField.tsx,ReadOnlyField.test.tsx,ReadOnlyField.stories.tsx,index.ts}`
- Create: `admin/packages/ui/src/components/Stepper/{Stepper.tsx,Stepper.test.tsx,Stepper.stories.tsx,index.ts}`

- [ ] **Step 1: ReadOnlyField**

```tsx
// admin/packages/ui/src/components/ReadOnlyField/ReadOnlyField.tsx
import type { ReactNode } from "react";
import { cn } from "../../utils/cn";

export interface ReadOnlyFieldProps {
  label: string;
  /** Either a primitive value or a fully-rendered display primitive
   *  (e.g., `<Money>`, `<FormattedDate>`). */
  value: ReactNode;
  className?: string;
}

export function ReadOnlyField({ label, value, className }: ReadOnlyFieldProps) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <span className="text-[13px] font-medium text-[var(--text-secondary)]">
        {label}
      </span>
      <div
        className={cn(
          "flex min-h-[var(--height-control-md)] items-center rounded-[var(--radius-md)] px-3 text-[14px]",
          "bg-[var(--surface-sunken)] text-[var(--text-primary)]",
          "border border-[var(--border-subtle)]",
        )}
      >
        {value}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: ReadOnlyField tests + stories + index**

```tsx
// admin/packages/ui/src/components/ReadOnlyField/ReadOnlyField.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReadOnlyField } from "./ReadOnlyField";

describe("ReadOnlyField", () => {
  it("renders label + value", () => {
    render(<ReadOnlyField label="Member ID" value="M-2026-0042" />);
    expect(screen.getByText("Member ID")).toBeInTheDocument();
    expect(screen.getByText("M-2026-0042")).toBeInTheDocument();
  });

  it("accepts ReactNode values", () => {
    render(<ReadOnlyField label="Status" value={<strong>Active</strong>} />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });
});
```

```tsx
// admin/packages/ui/src/components/ReadOnlyField/ReadOnlyField.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { ReadOnlyField } from "./ReadOnlyField";

const meta: Meta<typeof ReadOnlyField> = {
  title: "Forms/ReadOnlyField",
  component: ReadOnlyField,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof ReadOnlyField>;

export const Default: Story = {
  args: { label: "Member ID", value: "M-2026-0042" },
};
export const NextToInput: Story = {
  render: () => (
    <div style={{ display: "grid", gap: 16, maxWidth: 320 }}>
      <ReadOnlyField label="Member ID" value="M-2026-0042" />
      <ReadOnlyField label="Joined" value="28 May 2026" />
    </div>
  ),
};
```

```typescript
// admin/packages/ui/src/components/ReadOnlyField/index.ts
export {
  ReadOnlyField,
  type ReadOnlyFieldProps,
} from "./ReadOnlyField";
```

- [ ] **Step 3: Stepper**

```tsx
// admin/packages/ui/src/components/Stepper/Stepper.tsx
"use client";

import { Check } from "lucide-react";
import { cn } from "../../utils/cn";

export interface StepperStep {
  id: string;
  label: string;
}

export interface StepperProps {
  steps: StepperStep[];
  currentStepId: string;
  /** Called when a completed step's label is clicked. Upcoming steps are not clickable. */
  onStepClick?(stepId: string): void;
  className?: string;
}

export function Stepper({
  steps,
  currentStepId,
  onStepClick,
  className,
}: StepperProps) {
  const currentIdx = steps.findIndex((s) => s.id === currentStepId);
  return (
    <ol
      aria-label="Progress"
      className={cn("flex w-full items-center gap-2", className)}
    >
      {steps.map((step, idx) => {
        const status =
          idx < currentIdx ? "done" : idx === currentIdx ? "current" : "upcoming";
        const clickable = status === "done" && onStepClick !== undefined;
        return (
          <li
            key={step.id}
            className="flex flex-1 items-center gap-2"
            aria-current={status === "current" ? "step" : undefined}
          >
            <button
              type="button"
              disabled={!clickable}
              onClick={clickable ? () => onStepClick(step.id) : undefined}
              className={cn(
                "flex items-center gap-2 rounded-[var(--radius-md)] px-2 py-1 text-[13px]",
                status === "done" &&
                  "text-[var(--text-success)] hover:bg-[var(--surface-hover)]",
                status === "current" &&
                  "font-semibold text-[var(--text-primary)]",
                status === "upcoming" && "text-[var(--text-tertiary)]",
                !clickable && "cursor-default",
              )}
            >
              <span
                className={cn(
                  "grid h-5 w-5 place-content-center rounded-full text-[11px]",
                  status === "done" &&
                    "bg-[var(--status-success-bg)] text-[var(--text-success)]",
                  status === "current" &&
                    "bg-[var(--interactive-primary-bg)] text-[var(--interactive-primary-text)]",
                  status === "upcoming" &&
                    "border border-[var(--border-default)] text-[var(--text-tertiary)]",
                )}
              >
                {status === "done" ? (
                  <Check size={12} strokeWidth={2.25} />
                ) : (
                  idx + 1
                )}
              </span>
              <span>{step.label}</span>
            </button>
            {idx < steps.length - 1 ? (
              <span
                aria-hidden="true"
                className={cn(
                  "h-px flex-1",
                  status === "done"
                    ? "bg-[var(--text-success)]"
                    : "bg-[var(--border-subtle)]",
                )}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
```

- [ ] **Step 4: Stepper tests + stories + index**

```tsx
// admin/packages/ui/src/components/Stepper/Stepper.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Stepper } from "./Stepper";

const steps = [
  { id: "personal", label: "Personal" },
  { id: "employment", label: "Employment" },
  { id: "documents", label: "Documents" },
];

describe("Stepper", () => {
  it("marks the current step with aria-current=step", () => {
    render(<Stepper steps={steps} currentStepId="employment" />);
    const current = screen.getByText("Employment").closest("li");
    expect(current).toHaveAttribute("aria-current", "step");
  });

  it("makes completed steps clickable + upcoming steps not", async () => {
    const onStepClick = vi.fn();
    const user = userEvent.setup();
    render(
      <Stepper
        steps={steps}
        currentStepId="employment"
        onStepClick={onStepClick}
      />,
    );
    await user.click(screen.getByText("Personal"));
    expect(onStepClick).toHaveBeenCalledWith("personal");

    await user.click(screen.getByText("Documents"));
    // Upcoming click should not fire the callback (button is disabled).
    expect(onStepClick).toHaveBeenCalledTimes(1);
  });
});
```

```tsx
// admin/packages/ui/src/components/Stepper/Stepper.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { Stepper } from "./Stepper";

const meta: Meta<typeof Stepper> = {
  title: "Forms/Stepper",
  component: Stepper,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof Stepper>;

const steps = [
  { id: "personal", label: "Personal" },
  { id: "employment", label: "Employment" },
  { id: "documents", label: "Documents" },
  { id: "review", label: "Review" },
];

export const Mid: Story = {
  args: { steps, currentStepId: "documents" },
};
export const Start: Story = {
  args: { steps, currentStepId: "personal" },
};
export const End: Story = {
  args: { steps, currentStepId: "review" },
};
```

```typescript
// admin/packages/ui/src/components/Stepper/index.ts
export { Stepper, type StepperProps, type StepperStep } from "./Stepper";
```

- [ ] **Step 5: Re-export + verify + commit**

In `admin/packages/ui/src/index.ts` append:

```typescript
export * from "./components/ReadOnlyField";
export * from "./components/Stepper";
```

```bash
cd admin
pnpm --filter @sacco/ui test
```

```bash
git add admin/packages/ui/src/components/ReadOnlyField/ \
        admin/packages/ui/src/components/Stepper/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): ReadOnlyField + Stepper"
```

---

## Task 5: ConfirmDialog + MakerCheckerConfirmDialog

**Files:**
- Create: `admin/packages/ui/src/components/ConfirmDialog/{ConfirmDialog.tsx,ConfirmDialog.test.tsx,ConfirmDialog.stories.tsx,index.ts}`

- [ ] **Step 1: Implementation**

```tsx
// admin/packages/ui/src/components/ConfirmDialog/ConfirmDialog.tsx
"use client";

import type { ReactNode } from "react";
import { Button } from "../Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../Dialog";

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange(next: boolean): void;
  title: string;
  description?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  /** Renders the confirm button as `destructive`. */
  destructive?: boolean;
  onConfirm(): void | Promise<void>;
  /** Disable both buttons while a mutation is in flight. */
  busy?: boolean;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  destructive = false,
  onConfirm,
  busy = false,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? (
            <DialogDescription>{description}</DialogDescription>
          ) : null}
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? "destructive" : "primary"}
            onClick={() => {
              void onConfirm();
            }}
            disabled={busy}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export interface MakerCheckerConfirmDialogProps
  extends Omit<
    ConfirmDialogProps,
    "title" | "description" | "confirmLabel" | "destructive"
  > {
  /** What the operator is requesting, e.g., "loan disbursement". */
  operationLabel: string;
  /** Subject the operator is acting on, e.g., "loan #L-2026-001234". */
  subjectLabel?: string;
}

/**
 * Locked copy per docs/sacco-design-system-v2.md line 1102 and CLAUDE.md
 * contract K. Do not customise — the maker-checker dialog says exactly
 * this so the dual-state outcome is unambiguous.
 */
export function MakerCheckerConfirmDialog({
  operationLabel,
  subjectLabel,
  ...rest
}: MakerCheckerConfirmDialogProps) {
  const title = subjectLabel
    ? `Request ${operationLabel} on ${subjectLabel}`
    : `Request ${operationLabel}`;
  const description = (
    <span>
      This will create an approval request, not execute the action.
      <br />
      Another authorised user must approve before {operationLabel} runs.
    </span>
  );
  return (
    <ConfirmDialog
      {...rest}
      title={title}
      description={description}
      confirmLabel="Create Approval Request"
    />
  );
}
```

- [ ] **Step 2: Tests**

```tsx
// admin/packages/ui/src/components/ConfirmDialog/ConfirmDialog.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ConfirmDialog,
  MakerCheckerConfirmDialog,
} from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("renders title + description + confirm/cancel", () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Delete member?"
        description="This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByText("Delete member?")).toBeInTheDocument();
    expect(screen.getByText("This cannot be undone.")).toBeInTheDocument();
    expect(screen.getByText("Delete")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("calls onConfirm when confirm clicked", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Proceed?"
        confirmLabel="Yes"
        onConfirm={onConfirm}
      />,
    );
    await user.click(screen.getByText("Yes"));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("disables both buttons when busy", () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Proceed?"
        confirmLabel="Yes"
        onConfirm={() => {}}
        busy
      />,
    );
    expect(screen.getByText("Yes")).toBeDisabled();
    expect(screen.getByText("Cancel")).toBeDisabled();
  });
});

describe("MakerCheckerConfirmDialog", () => {
  it("locks the spec copy (line 1102)", () => {
    render(
      <MakerCheckerConfirmDialog
        open
        onOpenChange={() => {}}
        operationLabel="loan disbursement"
        subjectLabel="loan #L-2026-001234"
        onConfirm={() => {}}
      />,
    );
    expect(
      screen.getByText(/This will create an approval request, not execute/),
    ).toBeInTheDocument();
    expect(screen.getByText("Create Approval Request")).toBeInTheDocument();
    expect(
      screen.getByText("Request loan disbursement on loan #L-2026-001234"),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Stories + index**

```tsx
// admin/packages/ui/src/components/ConfirmDialog/ConfirmDialog.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { Button } from "../Button";
import {
  ConfirmDialog,
  MakerCheckerConfirmDialog,
} from "./ConfirmDialog";

const meta: Meta = {
  title: "Forms/ConfirmDialog",
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

function Plain() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Delete member</Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Delete this member?"
        description="This is irreversible."
        confirmLabel="Delete"
        destructive
        onConfirm={() => setOpen(false)}
      />
    </>
  );
}

function MakerChecker() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Request disbursement</Button>
      <MakerCheckerConfirmDialog
        open={open}
        onOpenChange={setOpen}
        operationLabel="loan disbursement"
        subjectLabel="loan #L-2026-001234"
        onConfirm={() => setOpen(false)}
      />
    </>
  );
}

export const Destructive: Story = { render: () => <Plain /> };
export const MakerCheckerVariant: Story = { render: () => <MakerChecker /> };
```

```typescript
// admin/packages/ui/src/components/ConfirmDialog/index.ts
export {
  ConfirmDialog,
  MakerCheckerConfirmDialog,
  type ConfirmDialogProps,
  type MakerCheckerConfirmDialogProps,
} from "./ConfirmDialog";
```

- [ ] **Step 4: Re-export + verify + commit**

In `admin/packages/ui/src/index.ts` append:

```typescript
export * from "./components/ConfirmDialog";
```

```bash
cd admin
pnpm --filter @sacco/ui test
```

```bash
git add admin/packages/ui/src/components/ConfirmDialog/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): ConfirmDialog + MakerCheckerConfirmDialog (locked spec copy)"
```

---

## Task 6: MakerCheckerBanner + AuditBar (placeholder)

**Files:**
- Create: `admin/packages/ui/src/components/MakerCheckerBanner/{MakerCheckerBanner.tsx,MakerCheckerBanner.test.tsx,MakerCheckerBanner.stories.tsx,index.ts}`
- Create: `admin/packages/ui/src/components/AuditBar/{AuditBar.tsx,AuditBar.test.tsx,AuditBar.stories.tsx,index.ts}`

- [ ] **Step 1: MakerCheckerBanner**

```tsx
// admin/packages/ui/src/components/MakerCheckerBanner/MakerCheckerBanner.tsx
import { TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../utils/cn";

export interface MakerCheckerBannerProps {
  /** Approval request id used in the link. */
  approvalRequestId: string;
  /** Operation label, e.g., "Loan disbursement". */
  operationLabel: string;
  requesterName: string;
  /** ISO timestamp; consumers can pass a React node (e.g., `<FormattedDateTime>`). */
  requestedAt: string | ReactNode;
  quorumRequired: number;
  quorumCurrent: number;
  /** Action node (the consumer wires the link). */
  action: ReactNode;
  className?: string;
}

export function MakerCheckerBanner({
  operationLabel,
  requesterName,
  requestedAt,
  quorumRequired,
  quorumCurrent,
  action,
  className,
}: MakerCheckerBannerProps) {
  const remaining = Math.max(0, quorumRequired - quorumCurrent);
  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-3 rounded-[var(--radius-md)] border px-4 py-3",
        "border-[var(--text-warning)] bg-[var(--status-warning-bg)] text-[var(--text-warning)]",
        className,
      )}
    >
      <TriangleAlert size={20} strokeWidth={1.75} aria-hidden />
      <div className="flex-1 text-[13px] text-[var(--text-primary)]">
        <p className="font-semibold">Pending Approval</p>
        <p className="mt-1">
          {operationLabel} requested by{" "}
          <strong>{requesterName}</strong> on {requestedAt}.
        </p>
        <p>
          Requires {remaining} more {remaining === 1 ? "approval" : "approvals"} (
          {quorumCurrent} of {quorumRequired} so far).
        </p>
      </div>
      <div className="ml-auto">{action}</div>
    </div>
  );
}
```

- [ ] **Step 2: MakerCheckerBanner tests + stories + index**

```tsx
// admin/packages/ui/src/components/MakerCheckerBanner/MakerCheckerBanner.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MakerCheckerBanner } from "./MakerCheckerBanner";

describe("MakerCheckerBanner", () => {
  it("renders operation + requester + quorum copy", () => {
    render(
      <MakerCheckerBanner
        approvalRequestId="AR-1234"
        operationLabel="Loan disbursement"
        requesterName="Sarah Achieng"
        requestedAt="28 May 2026"
        quorumRequired={2}
        quorumCurrent={1}
        action={<a href="/approvals/AR-1234">View</a>}
      />,
    );
    expect(screen.getByText("Pending Approval")).toBeInTheDocument();
    expect(screen.getByText(/Loan disbursement requested by/)).toBeInTheDocument();
    expect(screen.getByText("Sarah Achieng")).toBeInTheDocument();
    expect(
      screen.getByText(/Requires 1 more approval \(1 of 2 so far\)\./),
    ).toBeInTheDocument();
  });

  it("pluralises remaining approvals", () => {
    render(
      <MakerCheckerBanner
        approvalRequestId="AR-1235"
        operationLabel="Reversal"
        requesterName="John Mukasa"
        requestedAt="28 May 2026"
        quorumRequired={3}
        quorumCurrent={1}
        action={<span>view</span>}
      />,
    );
    expect(
      screen.getByText(/Requires 2 more approvals \(1 of 3 so far\)\./),
    ).toBeInTheDocument();
  });
});
```

```tsx
// admin/packages/ui/src/components/MakerCheckerBanner/MakerCheckerBanner.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { MakerCheckerBanner } from "./MakerCheckerBanner";

const meta: Meta<typeof MakerCheckerBanner> = {
  title: "Forms/MakerCheckerBanner",
  component: MakerCheckerBanner,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof MakerCheckerBanner>;

export const OneOfTwo: Story = {
  args: {
    approvalRequestId: "AR-1234",
    operationLabel: "Loan disbursement",
    requesterName: "Sarah Achieng",
    requestedAt: "28 May 2026",
    quorumRequired: 2,
    quorumCurrent: 1,
    action: (
      <a
        href="/approvals/AR-1234"
        className="text-[13px] underline"
      >
        View Approval Request
      </a>
    ),
  },
};

export const OneOfThree: Story = {
  args: { ...OneOfTwo.args!, quorumRequired: 3 },
};
```

```typescript
// admin/packages/ui/src/components/MakerCheckerBanner/index.ts
export {
  MakerCheckerBanner,
  type MakerCheckerBannerProps,
} from "./MakerCheckerBanner";
```

- [ ] **Step 3: AuditBar placeholder**

```tsx
// admin/packages/ui/src/components/AuditBar/AuditBar.tsx
import { History } from "lucide-react";

export interface AuditBarProps {
  /** Entity table or model name, e.g., "loan", "member". Matches the future
   *  audit-log query API's filter parameter. */
  entityType: string;
  /** Entity primary key (UUID or composite). */
  entityId: string;
}

/**
 * Placeholder for the entity activity panel. Phase 1.7-F (audit-log query
 * API) is still pending; until it ships this component renders a fixed
 * "coming soon" panel with a disabled "View Full History" affordance. The
 * `entityType` / `entityId` props match the future API parameters so
 * feature modules can drop this in today and it lights up when the
 * backend lands.
 */
export function AuditBar({ entityType, entityId }: AuditBarProps) {
  return (
    <section
      aria-label="Activity"
      data-entity-type={entityType}
      data-entity-id={entityId}
      className="rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-4"
    >
      <header className="mb-2 flex items-center gap-2 text-[var(--text-secondary)]">
        <History size={16} strokeWidth={1.75} aria-hidden />
        <h3 className="text-[13px] font-semibold uppercase tracking-wider">
          Activity
        </h3>
      </header>
      <p className="text-[13px] text-[var(--text-tertiary)]">
        Audit history coming soon — the audit-log query endpoint is pending.
      </p>
      <button
        type="button"
        disabled
        className="mt-3 text-[13px] text-[var(--text-tertiary)] underline-offset-2 hover:underline disabled:cursor-not-allowed disabled:opacity-60"
      >
        View Full History
      </button>
    </section>
  );
}
```

- [ ] **Step 4: AuditBar tests + stories + index**

```tsx
// admin/packages/ui/src/components/AuditBar/AuditBar.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AuditBar } from "./AuditBar";

describe("AuditBar", () => {
  it("renders the placeholder copy + disabled history button", () => {
    render(<AuditBar entityType="loan" entityId="L-001" />);
    expect(
      screen.getByText(/Audit history coming soon/),
    ).toBeInTheDocument();
    expect(screen.getByText("View Full History")).toBeDisabled();
  });

  it("exposes entity props via data attributes for future consumers", () => {
    const { container } = render(
      <AuditBar entityType="member" entityId="M-2026-0042" />,
    );
    const section = container.querySelector("section");
    expect(section).toHaveAttribute("data-entity-type", "member");
    expect(section).toHaveAttribute("data-entity-id", "M-2026-0042");
  });
});
```

```tsx
// admin/packages/ui/src/components/AuditBar/AuditBar.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { AuditBar } from "./AuditBar";

const meta: Meta<typeof AuditBar> = {
  title: "Forms/AuditBar",
  component: AuditBar,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof AuditBar>;

export const Placeholder: Story = {
  args: { entityType: "loan", entityId: "L-2026-001234" },
};
```

```typescript
// admin/packages/ui/src/components/AuditBar/index.ts
export { AuditBar, type AuditBarProps } from "./AuditBar";
```

- [ ] **Step 5: Re-export + verify + commit**

In `admin/packages/ui/src/index.ts` append:

```typescript
export * from "./components/MakerCheckerBanner";
export * from "./components/AuditBar";
```

```bash
cd admin
pnpm --filter @sacco/ui test
```

```bash
git add admin/packages/ui/src/components/MakerCheckerBanner/ \
        admin/packages/ui/src/components/AuditBar/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): MakerCheckerBanner + AuditBar placeholder (P1.7-F pending)"
```

---

## Task 7: useDraftAutoSave hook

**Files:**
- Create: `admin/packages/ui/src/hooks/{use-draft-autosave.ts,use-draft-autosave.test.ts,index.ts}`

- [ ] **Step 1: Hook**

```typescript
// admin/packages/ui/src/hooks/use-draft-autosave.ts
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_PREFIX = "sacco_draft:";

export interface UseDraftAutoSaveOptions<TValue> {
  /** Stable key for the draft, e.g., "loan-application:user-uuid". */
  formKey: string;
  /** Current form values to persist. */
  values: TValue;
  /** Debounce window for saves. Default 750ms. */
  debounceMs?: number;
  /** Skip writes (useful while the form is hydrating). */
  enabled?: boolean;
}

export interface UseDraftAutoSaveResult<TValue> {
  /** Read any previously-saved draft. Returns null when none exists. */
  restore(): TValue | null;
  /** Drop the saved draft (call after a successful submit). */
  clear(): void;
  /** ISO timestamp of the last successful save, or null. */
  lastSavedAt: string | null;
}

/**
 * Debounced localStorage persistence for in-progress forms. The hook does
 * NOT control the form — it just shadows `values` to storage and exposes a
 * `restore()` the consumer can call from a "You have unsaved changes…
 * Restore?" prompt.
 */
export function useDraftAutoSave<TValue>(
  options: UseDraftAutoSaveOptions<TValue>,
): UseDraftAutoSaveResult<TValue> {
  const { formKey, values, debounceMs = 750, enabled = true } = options;
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled) return;
    if (typeof window === "undefined") return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      try {
        const payload = {
          values,
          savedAt: new Date().toISOString(),
        };
        window.localStorage.setItem(
          `${STORAGE_PREFIX}${formKey}`,
          JSON.stringify(payload),
        );
        setLastSavedAt(payload.savedAt);
      } catch {
        // Quota or serialisation error — drop silently. The consumer can
        // surface "Couldn't save your draft" via a different signal if needed.
      }
    }, debounceMs);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [debounceMs, enabled, formKey, values]);

  const restore = useCallback((): TValue | null => {
    if (typeof window === "undefined") return null;
    try {
      const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${formKey}`);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as { values?: TValue };
      return parsed.values ?? null;
    } catch {
      return null;
    }
  }, [formKey]);

  const clear = useCallback(() => {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(`${STORAGE_PREFIX}${formKey}`);
    setLastSavedAt(null);
  }, [formKey]);

  return { restore, clear, lastSavedAt };
}
```

- [ ] **Step 2: Tests**

```typescript
// admin/packages/ui/src/hooks/use-draft-autosave.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useDraftAutoSave } from "./use-draft-autosave";

beforeEach(() => {
  vi.useFakeTimers();
  window.localStorage.clear();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("useDraftAutoSave", () => {
  it("persists after the debounce window", () => {
    const { result, rerender } = renderHook(
      ({ values }: { values: { name: string } }) =>
        useDraftAutoSave({ formKey: "loan-app", values }),
      { initialProps: { values: { name: "Mary" } } },
    );

    rerender({ values: { name: "Mary Akello" } });

    // Before the debounce fires, nothing is saved.
    expect(window.localStorage.getItem("sacco_draft:loan-app")).toBeNull();

    act(() => {
      vi.advanceTimersByTime(750);
    });

    const raw = window.localStorage.getItem("sacco_draft:loan-app");
    expect(raw).not.toBeNull();
    expect(JSON.parse(raw!).values).toEqual({ name: "Mary Akello" });
    expect(result.current.lastSavedAt).toBeTruthy();
  });

  it("restore() returns the persisted values", () => {
    window.localStorage.setItem(
      "sacco_draft:loan-app",
      JSON.stringify({ values: { name: "Sarah" }, savedAt: "x" }),
    );
    const { result } = renderHook(() =>
      useDraftAutoSave({ formKey: "loan-app", values: { name: "" } }),
    );
    expect(result.current.restore()).toEqual({ name: "Sarah" });
  });

  it("clear() removes the saved draft", () => {
    window.localStorage.setItem(
      "sacco_draft:loan-app",
      JSON.stringify({ values: { name: "Sarah" }, savedAt: "x" }),
    );
    const { result } = renderHook(() =>
      useDraftAutoSave({ formKey: "loan-app", values: { name: "" } }),
    );
    act(() => {
      result.current.clear();
    });
    expect(window.localStorage.getItem("sacco_draft:loan-app")).toBeNull();
  });

  it("respects enabled=false (no writes)", () => {
    const { rerender } = renderHook(
      ({ values, enabled }: { values: { name: string }; enabled: boolean }) =>
        useDraftAutoSave({ formKey: "loan-app", values, enabled }),
      { initialProps: { values: { name: "X" }, enabled: false } },
    );
    rerender({ values: { name: "Y" }, enabled: false });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(window.localStorage.getItem("sacco_draft:loan-app")).toBeNull();
  });
});
```

- [ ] **Step 3: Index + re-export + verify + commit**

```typescript
// admin/packages/ui/src/hooks/index.ts
export {
  useDraftAutoSave,
  type UseDraftAutoSaveOptions,
  type UseDraftAutoSaveResult,
} from "./use-draft-autosave";
```

In `admin/packages/ui/src/index.ts` append:

```typescript
export * from "./hooks";
```

```bash
cd admin
pnpm --filter @sacco/ui test
```

```bash
git add admin/packages/ui/src/hooks/ \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): useDraftAutoSave hook (debounced localStorage persistence)"
```

---

## Task 8: CLAUDE.md contracts + final verification + PR

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append contracts U, V, W**

In `CLAUDE.md` under `### Admin portal contracts (do not violate)`, after contract T, append:

```markdown
U. Form fields render through `<FormField control name label render />`
   from `@sacco/ui`. The render prop returns the inner field
   (`<Input>` / `<MoneyInput>` / `<PercentageInput>` / `<DateInput>` /
   `<DateRangeInput>` / `<ReadOnlyField>` / shadcn `<Select>` / etc.).
   FormField owns label / required-indicator / help / error /
   `aria-describedby` wiring; the field stays presentational. Hand-rolling
   the label-input-error triad is a contract violation. Money inputs use
   `<MoneyInput>` only (it reads precision from the currency registry);
   `<input type="number">` for currency amounts is forbidden.

V. Every action button that creates an approval request renders through
   `<MakerCheckerConfirmDialog>` from `@sacco/ui`. The dialog's copy
   ("This will create an approval request, not execute…" + the confirm
   button labelled "Create Approval Request") is intentionally locked.
   Records with open approvals render `<MakerCheckerBanner>` above the
   record body. Destructive confirmations use the base `<ConfirmDialog>`
   with `destructive`. Custom inline confirms or browser `confirm()`
   calls are contract violations.

W. Entity detail pages render `<AuditBar entityType entityId />` from
   `@sacco/ui`. Until the Phase 1.7-F audit-log query endpoint ships,
   the component renders a placeholder; the prop shape is the future
   API contract. Hand-rolling an activity panel is a contract violation
   even while the backend is pending — the placeholder is the single
   source of truth so the day the endpoint lands it lights up everywhere.

X. Long forms (loan applications, member onboarding) wire
   `useDraftAutoSave` from `@sacco/ui` against a stable per-user form
   key. On mount, the consumer calls `restore()` and prompts the user
   to resume if a draft exists; on successful submit, the consumer
   calls `clear()`. Drafts persist to `localStorage` keys prefixed
   `sacco_draft:`. Persistence is debounced 750ms — do not call
   `clear()` between keystrokes.
```

- [ ] **Step 2: Commit contracts**

```bash
git add CLAUDE.md
git commit -m "docs(claude): contracts U/V/W/X — form primitives + maker-checker + audit bar + draft autosave"
```

- [ ] **Step 3: Full pipeline**

```bash
cd admin
pnpm install
pnpm typecheck
pnpm lint
pnpm test
pnpm --filter @sacco/ui storybook:build
```
Expected: green; Storybook static output contains the `Forms/*` stories.

- [ ] **Step 4: Open the PR**

```bash
git push -u origin feat/portal-v1/11-form-primitives
gh pr create --title "feat(ui): form primitives + maker-checker UX + audit bar placeholder" --body "$(cat <<'EOF'
## Summary

- **FormField** — RHF `Controller` wrapper that owns label / required-asterisk / help / error / `aria-describedby` wiring. The render prop returns the inner field (presentational, RHF-unaware).
- **MoneyInput** — currency chip prefix, right-aligned, tabular-nums; live thousands separators; on-blur canonicalisation to the currency registry's precision (UGX → 0 decimals, USD → 2, etc.); negative blocked by default.
- **PercentageInput** — right-aligned, `%` suffix, max 2 decimals, on-blur clamp to `[min, max]` (default 0–100).
- **DateInput** + **DateRangeInput** — react-day-picker calendars; typed input accepts `DD/MM/YYYY` and `YYYY-MM-DD`; emits ISO `YYYY-MM-DD`; range variant uses a single two-month popover.
- **ReadOnlyField** — distinct-from-disabled informational field, accepts arbitrary ReactNode value (composes with `<Money>`, `<FormattedDate>`, etc.).
- **Stepper** — multi-step progress component; completed steps clickable, current bold, upcoming greyed; `aria-current="step"` on the active item.
- **ConfirmDialog** + **MakerCheckerConfirmDialog** — base destructive-confirm + the locked-copy variant from design system line 1102. The maker-checker dialog's title, body, and confirm-button label are intentionally not customisable.
- **MakerCheckerBanner** — pending-approval banner showing operation / requester / quorum-remaining; consumer wires the "View Approval Request" action node.
- **AuditBar** — placeholder until Phase 1.7-F (audit-log query API) ships; prop shape matches the future API so feature modules adopt it now.
- **useDraftAutoSave** — debounced localStorage persistence under `sacco_draft:<formKey>`; exposes `restore()`, `clear()`, `lastSavedAt`.

CLAUDE.md gains contracts **U** (form primitives), **V** (maker-checker UX), **W** (audit bar), **X** (draft autosave).

## Out of scope
- Feature-module forms — start landing from sub-plan 12.
- Real audit history rendering — lights up when Phase 1.7-F merges.
- E2E coverage against a seeded backend — sub-plan 39.

## Test plan
- [x] `pnpm --filter @sacco/ui test` — FormField, MoneyInput (+ helpers), PercentageInput, DateInput (+ parser), ReadOnlyField, Stepper, ConfirmDialog, MakerCheckerBanner, AuditBar, useDraftAutoSave
- [x] `pnpm --filter @sacco/ui storybook:build` — every primitive has a story under `Forms/*`
- [ ] Manual: open Storybook, drive every form story and the two dialog variants

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `react-day-picker` added; `react-hook-form` declared as peer + dev dep on `@sacco/ui`
- [ ] `<FormField>` wires label, required asterisk, help, error, `aria-describedby` correctly
- [ ] `<MoneyInput>` formats with thousands separators on type, canonicalises on blur per `CURRENCIES` precision, blocks negatives by default
- [ ] `<PercentageInput>` truncates to 2 decimals + clamps to `[min, max]` on blur
- [ ] `<DateInput>` accepts typed `DD/MM/YYYY` and `YYYY-MM-DD`; reverts on garbage input
- [ ] `<DateRangeInput>` renders two typed inputs + a two-month calendar popover
- [ ] `<ReadOnlyField>` is visually distinct from disabled
- [ ] `<Stepper>` marks the current step with `aria-current="step"` and disables upcoming-step clicks
- [ ] `<ConfirmDialog>` + `<MakerCheckerConfirmDialog>` render; maker-checker copy is locked
- [ ] `<MakerCheckerBanner>` renders operation + requester + quorum copy
- [ ] `<AuditBar>` renders placeholder + disabled "View Full History"
- [ ] `useDraftAutoSave` persists after debounce, restores, clears, respects `enabled=false`
- [ ] Storybook stories cover every primitive
- [ ] CLAUDE.md gains contracts U, V, W, X
- [ ] All new tests pass
- [ ] PR opened, CI green (Lint may stay environmentally red)

## Notes for the executing subagent

- **Do not** ship a `<NumberInput>`. Numbers without a currency or percentage context are rare in this domain; when they appear, plain `<Input type="text" inputMode="numeric">` is enough. Don't over-abstract.
- **Do not** add server-side validation hooks to `<FormField>`. Form-level Zod schemas live in `@sacco/schemas`; the field component stays presentational.
- **Do not** rewrite the maker-checker dialog copy. Line 1102 of `docs/sacco-design-system-v2.md` is the source; CLAUDE.md contract V locks it. If the copy needs to change, change it in the design system doc first, in the same PR.
- **Do not** wire the audit bar to a different endpoint than the eventual Phase 1.7-F shape. The placeholder takes `entityType` + `entityId` — that's the contract the backend will match. If the backend ships a different shape, this component changes; not before.
- **Do not** expose a "save now" affordance from `useDraftAutoSave`. Debouncing is the contract — adding a synchronous-save knob invites consumers to flush on every keystroke and trash localStorage perf.
- **The MoneyInput external-value sync** uses an inline value check inside the body of the component (not `useEffect`) so a programmatic `setValue` from RHF reflects immediately. This pattern is uncommon but correct for the controlled-with-display-copy idiom. Don't refactor it to a `useEffect` — that introduces a render-cycle gap where the input shows stale data.
- **Negative money values default to disallowed.** The only places `allowNegative` should flip true: account adjustment forms, manual GL entries, reversal forms. Default-deny is the safer behaviour because most consumers shouldn't even be able to type a minus.
- **`exactOptionalPropertyTypes` warning:** when threading optional props (e.g., `helpText`, `description`, `requestId`) through these components, conditionally spread them — `{...(helpText !== undefined ? { helpText } : {})}` — rather than passing `undefined`. Sub-plans 09 and 10 ran into this repeatedly; following the same pattern keeps strict mode quiet.
- **The `useDraftAutoSave` debounce timer is owned by a ref** so the cleanup effect can clear it on unmount without React reusing a stale timer reference across renders. Don't refactor it to `useState`.
- **React-day-picker v9's API differs from v8** — `selected` is a `Date` (not a string) and `onSelect` receives `Date | undefined`. The component code already handles this; if the install pulls v8 for some peer reason, bump explicitly to `^9.0.0` rather than downgrading the code.
- **MakerCheckerBanner takes the action node as a prop** rather than synthesising a `<Link>` inside, because the link's framework (Next.js's `<Link>` vs a plain `<a>`) is the consumer's concern. The banner has no opinion about routing.
- The four CLAUDE.md contracts (U/V/W/X) all reference `@sacco/ui` exports. After this PR merges, sub-plan 12 (Platform Users — the foundation validator) is the first place these contracts apply in earnest.
