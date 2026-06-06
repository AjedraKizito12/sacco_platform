# Portal v1 Sub-Plan 06: `packages/schemas` (Zod Mirrors)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/portal-v1/06-schemas` from `main` (or rebase on top of sub-plans 01-05).

**Goal:** Ship the Zod schemas the portal's forms validate against. These schemas mirror the backend's Pydantic request bodies — same field names, same constraints, same error semantics. After this sub-plan merges, every React Hook Form `resolver` in later sub-plans is `zodResolver(<schema from @sacco/schemas>)`, so client-side validation matches server-side enforcement.

**Architecture:**
- `@sacco/schemas` is a small workspace package — one file per backend module (`auth.ts`, `member.ts`, `savings.ts`, `credit.ts`, `billing.ts`, `fees.ts`, `ledger.ts`), plus a `common.ts` for cross-domain primitives.
- The TypeScript types are inferred from the Zod schemas via `z.infer<typeof schemaName>` — never hand-written. This guarantees the type and the validator can't drift.
- **Money is `Decimal-as-string`.** Per CLAUDE.md rule #5, money is never `float`. The Zod helper `moneyString()` accepts a string matching `^-?\d+(\.\d{1,4})?$` (up to 4 decimal places, matches `Numeric(19,4)`); the form sends `"50000.00"` not `50000`. Components that parse the string for display use the design system's `<Money>` component (sub-plan 09).
- **Decimal precision per currency is enforced at the input layer**, not in the schema. UGX → 0 dp, KES/USD → 2 dp, etc. The schema's job is "is this a syntactically valid Decimal string?" The `<MoneyInput>` (sub-plan 11) enforces the per-currency precision.
- Pagination uses a generic `cursorPagination()` helper that produces a schema for any `{limit, cursor}` query — matches the audit log API (P1.7-06) cursor design.

**Tech Stack:** Zod 3, Vitest 2.

**Portal v1 index reference:** `docs/superpowers/plans/2026-06-02-portal-v1-index.md` §Sub-plan 06.

**Required reading:**
- `app/modules/iam/platform_auth/schemas.py` and `app/modules/iam/tenant_auth/schemas.py` (login + reset shapes)
- `app/modules/members/schemas.py` (`MemberIn`, `StatusChangeIn`)
- `app/modules/savings/schemas.py` (`OpenAccountIn`, `DepositIn`, `WithdrawIn`)
- `app/modules/credit/schemas.py` (`LoanApplicationCreateIn`, `LoanRepaymentCreateIn`, `DisburseIn`, `RestructureIn`, `WriteOffIn`)
- `app/platform_/billing/schemas.py` (`PaymentRecordIn`, `SubscriptionPlanIn`, `SubscriptionPlanPatch`)
- CLAUDE.md rule #5 (money precision)

**Prerequisite:** **Sub-plan 01 must be merged** (the `@sacco/tsconfig` + `@sacco/eslint-config` packages). Sub-plan 05 is a soft prerequisite — the generated `paths` types live there, but `@sacco/schemas` is independent and can be developed in parallel.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `admin/packages/schemas/package.json` | Create | `@sacco/schemas` manifest |
| `admin/packages/schemas/tsconfig.json` | Create | Extends `@sacco/tsconfig/library.json` |
| `admin/packages/schemas/eslint.config.mjs` | Create | Extends `@sacco/eslint-config` |
| `admin/packages/schemas/vitest.config.ts` | Create | Vitest config |
| `admin/packages/schemas/src/common.ts` | Create | `moneyString`, `percentageString`, `currencyCode`, `uuid`, `cursorPagination`, ISO date helpers |
| `admin/packages/schemas/src/auth.ts` | Create | Login (platform + tenant), refresh, password-reset request/confirm |
| `admin/packages/schemas/src/member.ts` | Create | Registration + status change |
| `admin/packages/schemas/src/savings.ts` | Create | Open account, deposit, withdraw |
| `admin/packages/schemas/src/credit.ts` | Create | Loan application, repayment, disburse, restructure, write-off |
| `admin/packages/schemas/src/billing.ts` | Create | Record payment, plan create/edit, subscription cancel |
| `admin/packages/schemas/src/fees.ts` | Create | Fee type create/edit, manual assessment, collection |
| `admin/packages/schemas/src/ledger.ts` | Create | Account create, manual GL entry |
| `admin/packages/schemas/src/index.ts` | Create | Re-export surface |
| `admin/packages/schemas/src/__tests__/*.test.ts` | Create | Vitest cases per domain |

---

## Task 1: Package bootstrap + `common.ts`

**Files:**
- Create: `admin/packages/schemas/package.json`
- Create: `admin/packages/schemas/tsconfig.json`
- Create: `admin/packages/schemas/eslint.config.mjs`
- Create: `admin/packages/schemas/vitest.config.ts`
- Create: `admin/packages/schemas/src/common.ts`
- Create: `admin/packages/schemas/src/index.ts` (stub)
- Create: `admin/packages/schemas/src/__tests__/common.test.ts`

- [ ] **Step 1: Package manifest**

```json
{
  "name": "@sacco/schemas",
  "version": "0.0.0",
  "private": true,
  "license": "UNLICENSED",
  "type": "module",
  "exports": {
    ".": {
      "types": "./src/index.ts",
      "default": "./src/index.ts"
    },
    "./common": "./src/common.ts",
    "./auth": "./src/auth.ts",
    "./member": "./src/member.ts",
    "./savings": "./src/savings.ts",
    "./credit": "./src/credit.ts",
    "./billing": "./src/billing.ts",
    "./fees": "./src/fees.ts",
    "./ledger": "./src/ledger.ts"
  },
  "scripts": {
    "lint": "eslint . --max-warnings=0",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest",
    "clean": "rm -rf .turbo coverage"
  },
  "dependencies": {
    "zod": "^3.23.8"
  },
  "devDependencies": {
    "@sacco/eslint-config": "workspace:*",
    "@sacco/tsconfig": "workspace:*",
    "eslint": "^9.10.0",
    "typescript": "^5.6.2",
    "vitest": "^2.1.1"
  }
}
```

- [ ] **Step 2: tsconfig + eslint + vitest configs**

```json
{
  "extends": "@sacco/tsconfig/library.json",
  "compilerOptions": {
    "rootDir": "./src",
    "outDir": "./dist",
    "jsx": "react-jsx",
    "lib": ["DOM", "ES2023"]
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "coverage"]
}
```

```javascript
// admin/packages/schemas/eslint.config.mjs
import baseConfig from "@sacco/eslint-config";

export default [
  ...baseConfig,
  { ignores: ["node_modules", "dist", "coverage"] },
];
```

```typescript
// admin/packages/schemas/vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    globals: true,
  },
});
```

- [ ] **Step 3: Write `common.ts`**

```typescript
// admin/packages/schemas/src/common.ts
import { z } from "zod";

/**
 * Money is stored as Decimal-as-string on the wire (matches the backend's
 * Numeric(19,4) / DECIMAL(19,4) columns and CLAUDE.md rule #5). The portal
 * never sends a float.
 *
 * The schema accepts up to 4 decimal places. Per-currency precision (UGX → 0,
 * KES/USD → 2) is enforced at the <MoneyInput> layer (sub-plan 11), not here.
 */
export const moneyString = (opts?: {
  min?: string;
  max?: string;
  allowNegative?: boolean;
}) => {
  const pattern = opts?.allowNegative
    ? /^-?\d+(\.\d{1,4})?$/
    : /^\d+(\.\d{1,4})?$/;
  let schema = z
    .string()
    .trim()
    .regex(pattern, "Must be a decimal with up to 4 places");

  if (opts?.min !== undefined) {
    const minVal = opts.min;
    schema = schema.refine(
      (v) => Number.parseFloat(v) >= Number.parseFloat(minVal),
      `Must be ≥ ${minVal}`,
    );
  }
  if (opts?.max !== undefined) {
    const maxVal = opts.max;
    schema = schema.refine(
      (v) => Number.parseFloat(v) <= Number.parseFloat(maxVal),
      `Must be ≤ ${maxVal}`,
    );
  }
  return schema;
};

/**
 * Percentage is also Decimal-as-string with up to 2 decimal places.
 * Default range 0-100.
 */
export const percentageString = (opts?: { min?: number; max?: number }) => {
  const min = opts?.min ?? 0;
  const max = opts?.max ?? 100;
  return z
    .string()
    .trim()
    .regex(/^\d+(\.\d{1,2})?$/, "Must be a percentage with up to 2 places")
    .refine((v) => Number.parseFloat(v) >= min, `Must be ≥ ${min}`)
    .refine((v) => Number.parseFloat(v) <= max, `Must be ≤ ${max}`);
};

/** ISO-3 currency code, uppercase. UGX-only in v1 but kept flexible. */
export const currencyCode = z
  .string()
  .trim()
  .regex(/^[A-Z]{3}$/, "Must be a 3-letter currency code");

/** UUID v4 string from the backend (validates v1-5 patterns inclusively). */
export const uuid = z.string().uuid("Must be a valid UUID");

/** ISO-8601 date string (YYYY-MM-DD). */
export const isoDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, "Must be YYYY-MM-DD");

/** ISO-8601 datetime string. */
export const isoDateTime = z.string().datetime({
  message: "Must be an ISO-8601 datetime",
});

/**
 * Cursor pagination shape matching the audit log API (P1.7-06): opaque
 * base64 cursor, integer limit capped at 100.
 */
export const cursorPagination = () =>
  z.object({
    cursor: z.string().optional(),
    limit: z.coerce.number().int().min(1).max(100).optional(),
  });

/**
 * Idempotency key — UUID v4-ish; min length 8 enforced by the billing
 * PaymentRecordIn (backend Pydantic validator). We pass-through; the
 * api-client (sub-plan 05) injects a UUID v7 when none is provided.
 */
export const idempotencyKey = z.string().min(8);

export type Money = z.infer<ReturnType<typeof moneyString>>;
export type Percentage = z.infer<ReturnType<typeof percentageString>>;
export type CurrencyCode = z.infer<typeof currencyCode>;
export type UUID = z.infer<typeof uuid>;
export type ISODate = z.infer<typeof isoDate>;
export type ISODateTime = z.infer<typeof isoDateTime>;
```

- [ ] **Step 4: Empty index stub**

```typescript
// admin/packages/schemas/src/index.ts
export * from "./common";
```

- [ ] **Step 5: Tests for `common.ts`**

```typescript
// admin/packages/schemas/src/__tests__/common.test.ts
import { describe, expect, it } from "vitest";
import {
  cursorPagination,
  currencyCode,
  idempotencyKey,
  isoDate,
  isoDateTime,
  moneyString,
  percentageString,
  uuid,
} from "../common";

describe("moneyString", () => {
  it("accepts integer and decimal strings", () => {
    const m = moneyString();
    expect(m.parse("50000")).toBe("50000");
    expect(m.parse("50000.5")).toBe("50000.5");
    expect(m.parse("50000.1234")).toBe("50000.1234");
  });

  it("rejects more than 4 decimal places", () => {
    expect(() => moneyString().parse("50000.12345")).toThrow();
  });

  it("rejects negative when allowNegative is not set", () => {
    expect(() => moneyString().parse("-50000")).toThrow();
  });

  it("accepts negative when allowNegative=true", () => {
    expect(moneyString({ allowNegative: true }).parse("-50000")).toBe("-50000");
  });

  it("enforces min and max bounds", () => {
    const m = moneyString({ min: "100", max: "1000" });
    expect(m.parse("500")).toBe("500");
    expect(() => m.parse("50")).toThrow(/≥ 100/);
    expect(() => m.parse("5000")).toThrow(/≤ 1000/);
  });

  it("rejects non-numeric strings", () => {
    expect(() => moneyString().parse("fifty-thousand")).toThrow();
    expect(() => moneyString().parse("")).toThrow();
  });
});

describe("percentageString", () => {
  it("accepts 0..100 range by default", () => {
    expect(percentageString().parse("12.50")).toBe("12.50");
    expect(() => percentageString().parse("150")).toThrow();
  });
  it("honours custom range", () => {
    const annualRate = percentageString({ max: 50 });
    expect(annualRate.parse("12.5")).toBe("12.5");
    expect(() => annualRate.parse("60")).toThrow();
  });
});

describe("currencyCode", () => {
  it("requires three uppercase letters", () => {
    expect(currencyCode.parse("UGX")).toBe("UGX");
    expect(() => currencyCode.parse("ugx")).toThrow();
    expect(() => currencyCode.parse("UG")).toThrow();
  });
});

describe("uuid", () => {
  it("accepts a UUID v4 string", () => {
    expect(() =>
      uuid.parse("550e8400-e29b-41d4-a716-446655440000"),
    ).not.toThrow();
  });
  it("rejects garbage", () => {
    expect(() => uuid.parse("not-a-uuid")).toThrow();
  });
});

describe("isoDate / isoDateTime", () => {
  it("isoDate accepts YYYY-MM-DD", () => {
    expect(isoDate.parse("2026-06-04")).toBe("2026-06-04");
    expect(() => isoDate.parse("2026/06/04")).toThrow();
  });
  it("isoDateTime accepts ISO-8601", () => {
    expect(() =>
      isoDateTime.parse("2026-06-04T14:32:07Z"),
    ).not.toThrow();
  });
});

describe("cursorPagination", () => {
  it("accepts empty object", () => {
    expect(cursorPagination().parse({})).toEqual({});
  });
  it("coerces limit from string (URL params)", () => {
    expect(cursorPagination().parse({ limit: "50" })).toEqual({ limit: 50 });
  });
  it("caps limit at 100", () => {
    expect(() => cursorPagination().parse({ limit: 200 })).toThrow();
  });
});

describe("idempotencyKey", () => {
  it("requires at least 8 chars", () => {
    expect(idempotencyKey.parse("12345678")).toBe("12345678");
    expect(() => idempotencyKey.parse("short")).toThrow();
  });
});
```

- [ ] **Step 6: Install + run tests**

```bash
make admin-install
cd admin
pnpm --filter @sacco/schemas test
```
Expected: all common tests pass.

- [ ] **Step 7: Commit**

```bash
git add admin/packages/schemas/ admin/pnpm-lock.yaml
git commit -m "feat(schemas): package bootstrap + common primitives (money/percentage/uuid/date/pagination)"
```

---

## Task 2: Auth + member schemas

**Files:**
- Create: `admin/packages/schemas/src/auth.ts`
- Create: `admin/packages/schemas/src/member.ts`
- Create: `admin/packages/schemas/src/__tests__/auth.test.ts`
- Create: `admin/packages/schemas/src/__tests__/member.test.ts`
- Modify: `admin/packages/schemas/src/index.ts`

- [ ] **Step 1: `auth.ts`**

The backend's `PlatformLoginRequest` and `TenantLoginRequest` shapes are identical structurally; we share one `loginSchema`.

```typescript
// admin/packages/schemas/src/auth.ts
import { z } from "zod";

// Backend-aligned: min length 12 (auth_password_min_length default in Settings).
// The IAM layer is authoritative; if config diverges, the API rejects with 401.
const passwordMinLength = 12;

export const loginSchema = z.object({
  email: z.string().trim().toLowerCase().email("Must be a valid email"),
  password: z.string().min(1, "Password is required"),
});

export const refreshSchema = z.object({
  refresh_token: z.string().min(10),
});

export const passwordResetRequestSchema = z.object({
  email: z.string().trim().toLowerCase().email("Must be a valid email"),
});

export const passwordResetConfirmSchema = z
  .object({
    token: z.string().min(10, "Reset token is required"),
    new_password: z
      .string()
      .min(
        passwordMinLength,
        `Password must be at least ${passwordMinLength} characters`,
      ),
    confirm_password: z.string(),
  })
  .refine(
    (data) => data.new_password === data.confirm_password,
    {
      message: "Passwords do not match",
      path: ["confirm_password"],
    },
  );

export type LoginInput = z.infer<typeof loginSchema>;
export type RefreshInput = z.infer<typeof refreshSchema>;
export type PasswordResetRequestInput = z.infer<typeof passwordResetRequestSchema>;
export type PasswordResetConfirmInput = z.infer<typeof passwordResetConfirmSchema>;
```

- [ ] **Step 2: `member.ts`**

The backend's `MemberIn` accepts: full_name, date_of_birth, gender, optional phone/email/physical_address/national_id_number/id_document_type/id_document_number/id_issued_date/id_expiry_date.

```typescript
// admin/packages/schemas/src/member.ts
import { z } from "zod";
import { isoDate, uuid } from "./common";

export const memberGenderSchema = z.enum(["M", "F", "X"]);

export const idDocumentTypeSchema = z.enum([
  "national_id",
  "passport",
  "driving_license",
  "voters_card",
]);

export const memberRegistrationSchema = z.object({
  full_name: z.string().trim().min(1, "Full name is required").max(200),
  date_of_birth: isoDate,
  gender: memberGenderSchema,
  phone: z
    .string()
    .trim()
    .regex(/^\+?[0-9\s-]{7,20}$/, "Must be a valid phone number")
    .optional()
    .or(z.literal("")),
  email: z
    .string()
    .trim()
    .toLowerCase()
    .email("Must be a valid email")
    .optional()
    .or(z.literal("")),
  physical_address: z.string().trim().max(500).optional().or(z.literal("")),
  national_id_number: z.string().trim().max(50).optional().or(z.literal("")),
  id_document_type: idDocumentTypeSchema.optional(),
  id_document_number: z.string().trim().max(50).optional().or(z.literal("")),
  id_issued_date: isoDate.optional(),
  id_expiry_date: isoDate.optional(),
});

export const memberStatusSchema = z.enum([
  "prospect",
  "active",
  "dormant",
  "suspended",
  "exited",
  "deceased",
]);

export const memberStatusChangeSchema = z.object({
  new_status: memberStatusSchema,
  reason: z
    .string()
    .trim()
    .min(10, "Reason must be at least 10 characters")
    .max(500),
  idempotency_key: z.string().min(8),
});

// Tenant id (UUID) helper used by other forms that target a specific member.
export const memberIdSchema = uuid;

export type MemberRegistrationInput = z.infer<typeof memberRegistrationSchema>;
export type MemberStatusChangeInput = z.infer<typeof memberStatusChangeSchema>;
export type MemberStatus = z.infer<typeof memberStatusSchema>;
export type MemberGender = z.infer<typeof memberGenderSchema>;
export type IdDocumentType = z.infer<typeof idDocumentTypeSchema>;
```

- [ ] **Step 3: Tests**

```typescript
// admin/packages/schemas/src/__tests__/auth.test.ts
import { describe, expect, it } from "vitest";
import {
  loginSchema,
  passwordResetConfirmSchema,
  passwordResetRequestSchema,
} from "../auth";

describe("loginSchema", () => {
  it("normalises email to lowercase", () => {
    const parsed = loginSchema.parse({
      email: "  Liam@SACCO.example  ",
      password: "AdminTest!2026",
    });
    expect(parsed.email).toBe("liam@sacco.example");
  });

  it("rejects empty password", () => {
    expect(() =>
      loginSchema.parse({ email: "x@y.test", password: "" }),
    ).toThrow();
  });
});

describe("passwordResetRequestSchema", () => {
  it("accepts a valid email", () => {
    expect(() =>
      passwordResetRequestSchema.parse({ email: "x@y.test" }),
    ).not.toThrow();
  });
});

describe("passwordResetConfirmSchema", () => {
  it("requires min length 12 password", () => {
    expect(() =>
      passwordResetConfirmSchema.parse({
        token: "abcdefghij",
        new_password: "short",
        confirm_password: "short",
      }),
    ).toThrow(/at least 12/);
  });

  it("enforces password match", () => {
    expect(() =>
      passwordResetConfirmSchema.parse({
        token: "abcdefghij",
        new_password: "longenoughpw1!",
        confirm_password: "different-pw-here",
      }),
    ).toThrow(/do not match/);
  });

  it("accepts matching strong password", () => {
    expect(() =>
      passwordResetConfirmSchema.parse({
        token: "abcdefghij",
        new_password: "Abcdefghijkl12!",
        confirm_password: "Abcdefghijkl12!",
      }),
    ).not.toThrow();
  });
});
```

```typescript
// admin/packages/schemas/src/__tests__/member.test.ts
import { describe, expect, it } from "vitest";
import {
  memberRegistrationSchema,
  memberStatusChangeSchema,
} from "../member";

describe("memberRegistrationSchema", () => {
  it("accepts a minimal valid member", () => {
    expect(() =>
      memberRegistrationSchema.parse({
        full_name: "Mary Akello",
        date_of_birth: "1990-05-12",
        gender: "F",
      }),
    ).not.toThrow();
  });

  it("rejects an invalid gender", () => {
    expect(() =>
      memberRegistrationSchema.parse({
        full_name: "Mary",
        date_of_birth: "1990-05-12",
        gender: "?",
      }),
    ).toThrow();
  });

  it("accepts an empty optional email", () => {
    expect(() =>
      memberRegistrationSchema.parse({
        full_name: "Mary",
        date_of_birth: "1990-05-12",
        gender: "F",
        email: "",
      }),
    ).not.toThrow();
  });

  it("rejects malformed phone", () => {
    expect(() =>
      memberRegistrationSchema.parse({
        full_name: "Mary",
        date_of_birth: "1990-05-12",
        gender: "F",
        phone: "phone???",
      }),
    ).toThrow();
  });
});

describe("memberStatusChangeSchema", () => {
  it("requires a reason ≥ 10 chars", () => {
    expect(() =>
      memberStatusChangeSchema.parse({
        new_status: "dormant",
        reason: "short",
        idempotency_key: "12345678",
      }),
    ).toThrow(/at least 10/);
  });

  it("accepts a valid status change", () => {
    expect(() =>
      memberStatusChangeSchema.parse({
        new_status: "suspended",
        reason: "Member missed three consecutive savings deposits",
        idempotency_key: "12345678",
      }),
    ).not.toThrow();
  });
});
```

- [ ] **Step 4: Update index re-exports**

```typescript
// admin/packages/schemas/src/index.ts
export * from "./common";
export * from "./auth";
export * from "./member";
```

- [ ] **Step 5: Run tests + typecheck**

```bash
cd admin
pnpm --filter @sacco/schemas test
pnpm --filter @sacco/schemas typecheck
```
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add admin/packages/schemas/src/{auth.ts,member.ts,__tests__,index.ts}
git commit -m "feat(schemas): auth + member schemas with tests"
```

---

## Task 3: Savings + credit schemas

**Files:**
- Create: `admin/packages/schemas/src/savings.ts`
- Create: `admin/packages/schemas/src/credit.ts`
- Create: `admin/packages/schemas/src/__tests__/savings.test.ts`
- Create: `admin/packages/schemas/src/__tests__/credit.test.ts`
- Modify: `admin/packages/schemas/src/index.ts`

- [ ] **Step 1: `savings.ts`**

Backend shapes:
- `OpenAccountIn` — `member_id`, `savings_product_id`
- `DepositIn` — `amount`, `payment_account_id`, `idempotency_key`, optional `narration`
- `WithdrawIn` — same as deposit (goes through maker-checker; service signs it as a withdrawal)

```typescript
// admin/packages/schemas/src/savings.ts
import { z } from "zod";
import { idempotencyKey, moneyString, uuid } from "./common";

export const openAccountSchema = z.object({
  member_id: uuid,
  savings_product_id: uuid,
});

const baseTransactionSchema = z.object({
  amount: moneyString({ min: "0.01" }),
  payment_account_id: uuid,
  idempotency_key: idempotencyKey,
  narration: z.string().trim().max(280).optional().or(z.literal("")),
});

export const depositSchema = baseTransactionSchema;
export const withdrawSchema = baseTransactionSchema;

export const savingsProductSchema = z.object({
  name: z.string().trim().min(1).max(200),
  interest_rate: moneyString({ min: "0", max: "100" }),
  liability_account_id: uuid,
  minimum_balance: moneyString({ min: "0" }),
});

export type OpenAccountInput = z.infer<typeof openAccountSchema>;
export type DepositInput = z.infer<typeof depositSchema>;
export type WithdrawInput = z.infer<typeof withdrawSchema>;
export type SavingsProductInput = z.infer<typeof savingsProductSchema>;
```

- [ ] **Step 2: `credit.ts`**

Backend shapes (from earlier conversation reads):
- `LoanApplicationCreateIn`: `loan_product_id`, `member_id`, `requested_amount`, `requested_term_periods`, `purpose`, `disbursement_destination`, `disbursement_account_id`, `idempotency_key`
- `LoanRepaymentCreateIn`: `amount`, `payment_account_id`, optional `narration`, optional `savings_account_id`, `idempotency_key`
- `DisburseIn`: `idempotency_key`
- `RestructureIn`: `restructuring_type`, `periods_added`, `reason`, `idempotency_key`
- `WriteOffIn`: `amount`, `reason`, optional `loan_loss_account_code`, `idempotency_key`

```typescript
// admin/packages/schemas/src/credit.ts
import { z } from "zod";
import { idempotencyKey, moneyString, percentageString, uuid } from "./common";

export const disbursementDestinationSchema = z.enum([
  "savings_account",
  "cash",
  "bank_transfer",
  "mobile_money",
]);

export const loanApplicationSchema = z.object({
  loan_product_id: uuid,
  member_id: uuid,
  requested_amount: moneyString({ min: "0.01" }),
  requested_term_periods: z
    .number()
    .int("Must be a whole number of periods")
    .min(1, "At least one period")
    .max(360, "Term cannot exceed 360 periods"),
  purpose: z.string().trim().min(10, "Purpose required").max(500),
  disbursement_destination: disbursementDestinationSchema,
  disbursement_account_id: uuid.optional(),
  idempotency_key: idempotencyKey,
});

export const loanRepaymentSchema = z.object({
  amount: moneyString({ min: "0.01" }),
  payment_account_id: uuid,
  narration: z.string().trim().max(280).optional().or(z.literal("")),
  savings_account_id: uuid.optional(),
  idempotency_key: idempotencyKey,
});

export const disburseSchema = z.object({
  idempotency_key: idempotencyKey,
});

export const restructuringTypeSchema = z.enum([
  "term_extension",
  "interest_only_period",
  "principal_holiday",
]);

export const loanRestructureSchema = z.object({
  restructuring_type: restructuringTypeSchema,
  periods_added: z
    .number()
    .int()
    .min(1, "Must add at least one period")
    .max(120, "Cannot add more than 120 periods"),
  reason: z.string().trim().min(20, "Reason must be at least 20 chars").max(1000),
  idempotency_key: idempotencyKey,
});

export const loanWriteOffSchema = z.object({
  amount: moneyString({ min: "0.01" }),
  reason: z.string().trim().min(20).max(1000),
  loan_loss_account_code: z
    .string()
    .trim()
    .max(20)
    .optional()
    .or(z.literal("")),
  idempotency_key: idempotencyKey,
});

export const loanRecoverySchema = z.object({
  amount: moneyString({ min: "0.01" }),
  reason: z.string().trim().min(10).max(500),
  idempotency_key: idempotencyKey,
});

export const loanProductSchema = z.object({
  name: z.string().trim().min(1).max(200),
  description: z.string().trim().max(1000).optional().or(z.literal("")),
  interest_method: z.enum(["flat", "reducing_balance"]),
  annual_interest_rate: percentageString({ max: 100 }),
  repayment_frequency: z.enum(["monthly", "quarterly", "annual"]),
  max_term_periods: z.number().int().min(1).max(360),
  min_amount: moneyString({ min: "0" }),
  max_amount: moneyString({ min: "0" }),
  required_approvals: z.number().int().min(1).max(5),
  // Detail fields (GL account codes, write_off_threshold) accept simple
  // string IDs from the backend's product service.
  gl_principal_receivable_code: z.string().trim().min(1).max(20),
  gl_interest_receivable_code: z.string().trim().min(1).max(20),
  gl_interest_income_code: z.string().trim().min(1).max(20),
  gl_loan_loss_expense_code: z.string().trim().min(1).max(20),
  penalty_fee_type_code: z.string().trim().max(40).optional().or(z.literal("")),
  write_off_threshold: moneyString({ min: "0" }).optional(),
  disbursement_destinations: z.array(disbursementDestinationSchema).min(1),
  repayment_allocation: z.enum(["principal_first", "interest_first", "fees_first"]),
});

export type LoanApplicationInput = z.infer<typeof loanApplicationSchema>;
export type LoanRepaymentInput = z.infer<typeof loanRepaymentSchema>;
export type DisburseInput = z.infer<typeof disburseSchema>;
export type LoanRestructureInput = z.infer<typeof loanRestructureSchema>;
export type LoanWriteOffInput = z.infer<typeof loanWriteOffSchema>;
export type LoanRecoveryInput = z.infer<typeof loanRecoverySchema>;
export type LoanProductInput = z.infer<typeof loanProductSchema>;
```

- [ ] **Step 3: Tests**

```typescript
// admin/packages/schemas/src/__tests__/savings.test.ts
import { describe, expect, it } from "vitest";
import { depositSchema, openAccountSchema, withdrawSchema } from "../savings";

describe("openAccountSchema", () => {
  it("requires both UUIDs", () => {
    expect(() =>
      openAccountSchema.parse({
        member_id: "550e8400-e29b-41d4-a716-446655440000",
        savings_product_id: "550e8400-e29b-41d4-a716-446655440001",
      }),
    ).not.toThrow();
  });
});

describe("depositSchema", () => {
  const ok = {
    amount: "50000.00",
    payment_account_id: "550e8400-e29b-41d4-a716-446655440002",
    idempotency_key: "1234567890ab",
  };
  it("accepts a valid deposit", () => {
    expect(() => depositSchema.parse(ok)).not.toThrow();
  });
  it("rejects zero amount", () => {
    expect(() =>
      depositSchema.parse({ ...ok, amount: "0" }),
    ).toThrow();
  });
  it("rejects float-precision overflow", () => {
    expect(() =>
      depositSchema.parse({ ...ok, amount: "50000.12345" }),
    ).toThrow();
  });
  it("rejects short idempotency key", () => {
    expect(() =>
      depositSchema.parse({ ...ok, idempotency_key: "short" }),
    ).toThrow();
  });
});

describe("withdrawSchema", () => {
  it("uses the same shape as deposit", () => {
    expect(withdrawSchema.shape.amount).toBe(depositSchema.shape.amount);
  });
});
```

```typescript
// admin/packages/schemas/src/__tests__/credit.test.ts
import { describe, expect, it } from "vitest";
import {
  loanApplicationSchema,
  loanRepaymentSchema,
  loanRestructureSchema,
  loanWriteOffSchema,
} from "../credit";

describe("loanApplicationSchema", () => {
  const ok = {
    loan_product_id: "550e8400-e29b-41d4-a716-446655440000",
    member_id: "550e8400-e29b-41d4-a716-446655440001",
    requested_amount: "1000000.00",
    requested_term_periods: 12,
    purpose: "Working capital for the family shop",
    disbursement_destination: "savings_account",
    disbursement_account_id: "550e8400-e29b-41d4-a716-446655440002",
    idempotency_key: "1234567890ab",
  };

  it("accepts a complete application", () => {
    expect(() => loanApplicationSchema.parse(ok)).not.toThrow();
  });

  it("rejects too-short purpose", () => {
    expect(() =>
      loanApplicationSchema.parse({ ...ok, purpose: "biz" }),
    ).toThrow();
  });

  it("rejects fractional term periods", () => {
    expect(() =>
      loanApplicationSchema.parse({ ...ok, requested_term_periods: 12.5 }),
    ).toThrow();
  });

  it("rejects out-of-range term", () => {
    expect(() =>
      loanApplicationSchema.parse({ ...ok, requested_term_periods: 0 }),
    ).toThrow();
    expect(() =>
      loanApplicationSchema.parse({ ...ok, requested_term_periods: 400 }),
    ).toThrow();
  });
});

describe("loanRepaymentSchema", () => {
  it("accepts savings_account_id as optional", () => {
    expect(() =>
      loanRepaymentSchema.parse({
        amount: "100000",
        payment_account_id: "550e8400-e29b-41d4-a716-446655440000",
        idempotency_key: "1234567890ab",
      }),
    ).not.toThrow();
  });
});

describe("loanRestructureSchema", () => {
  it("requires periods_added ≥ 1", () => {
    expect(() =>
      loanRestructureSchema.parse({
        restructuring_type: "term_extension",
        periods_added: 0,
        reason: "Borrower lost job, requesting term extension to recover",
        idempotency_key: "1234567890ab",
      }),
    ).toThrow();
  });
});

describe("loanWriteOffSchema", () => {
  it("rejects empty reason", () => {
    expect(() =>
      loanWriteOffSchema.parse({
        amount: "500000",
        reason: "too short",
        idempotency_key: "1234567890ab",
      }),
    ).toThrow();
  });
});
```

- [ ] **Step 4: Index re-exports**

```typescript
// admin/packages/schemas/src/index.ts
export * from "./common";
export * from "./auth";
export * from "./member";
export * from "./savings";
export * from "./credit";
```

- [ ] **Step 5: Run tests**

```bash
cd admin
pnpm --filter @sacco/schemas test
pnpm --filter @sacco/schemas typecheck
```
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add admin/packages/schemas/src/{savings.ts,credit.ts,__tests__,index.ts}
git commit -m "feat(schemas): savings + credit schemas with tests"
```

---

## Task 4: Billing + fees + ledger schemas

**Files:**
- Create: `admin/packages/schemas/src/billing.ts`
- Create: `admin/packages/schemas/src/fees.ts`
- Create: `admin/packages/schemas/src/ledger.ts`
- Create: `admin/packages/schemas/src/__tests__/billing.test.ts`
- Modify: `admin/packages/schemas/src/index.ts`

- [ ] **Step 1: `billing.ts`**

Backend shapes (`app/platform_/billing/schemas.py`):
- `PaymentRecordIn`: `amount`, `currency` (default UGX), `payment_method`, optional `external_reference`, optional `notes`, `idempotency_key` (min 8)
- `SubscriptionPlanIn`: `code`, `name`, optional `description`, `currency`, `base_price`, `per_user_price`, `per_member_price`, `billing_period`, optional `member_limit`, optional `user_limit`, `features`, `trial_period_days`, `grace_period_days`
- `SubscriptionPlanPatch`: subset of the above, all optional
- `SubscriptionCancelIn`: `reason`
- `InvoiceVoidIn`: `reason`
- `SubscriptionCreateIn`: `tenant_id`, `plan_id`, optional `start_date`

```typescript
// admin/packages/schemas/src/billing.ts
import { z } from "zod";
import {
  currencyCode,
  idempotencyKey,
  isoDate,
  moneyString,
  uuid,
} from "./common";

export const paymentMethodSchema = z.enum([
  "bank_transfer",
  "mobile_money",
  "cash",
  "cheque",
]);

export const recordPaymentSchema = z.object({
  amount: moneyString({ min: "0.01" }),
  currency: currencyCode.default("UGX"),
  payment_method: paymentMethodSchema,
  external_reference: z.string().trim().max(200).optional().or(z.literal("")),
  notes: z.string().trim().max(1000).optional().or(z.literal("")),
  idempotency_key: idempotencyKey,
});

export const billingPeriodSchema = z.enum(["monthly", "quarterly", "annual"]);

export const subscriptionPlanSchema = z.object({
  code: z
    .string()
    .trim()
    .min(1, "Code is required")
    .max(40)
    .regex(/^[a-z0-9_-]+$/, "Use lowercase, digits, _, or -"),
  name: z.string().trim().min(1).max(200),
  description: z.string().trim().max(1000).optional().or(z.literal("")),
  currency: currencyCode.default("UGX"),
  base_price: moneyString({ min: "0" }),
  per_user_price: moneyString({ min: "0" }).default("0"),
  per_member_price: moneyString({ min: "0" }).default("0"),
  billing_period: billingPeriodSchema,
  member_limit: z.number().int().min(0).optional(),
  user_limit: z.number().int().min(0).optional(),
  features: z.record(z.string(), z.unknown()).default({}),
  trial_period_days: z.number().int().min(0).max(365).default(0),
  grace_period_days: z.number().int().min(0).max(365).default(30),
});

// PATCH variant: all fields optional + code/billing_period are immutable.
export const subscriptionPlanPatchSchema = z
  .object({
    name: z.string().trim().min(1).max(200).optional(),
    description: z.string().trim().max(1000).optional().or(z.literal("")),
    base_price: moneyString({ min: "0" }).optional(),
    per_user_price: moneyString({ min: "0" }).optional(),
    per_member_price: moneyString({ min: "0" }).optional(),
    member_limit: z.number().int().min(0).optional(),
    user_limit: z.number().int().min(0).optional(),
    features: z.record(z.string(), z.unknown()).optional(),
    trial_period_days: z.number().int().min(0).max(365).optional(),
    grace_period_days: z.number().int().min(0).max(365).optional(),
    is_active: z.boolean().optional(),
  })
  .strict();

export const subscriptionCreateSchema = z.object({
  tenant_id: uuid,
  plan_id: uuid,
  start_date: isoDate.optional(),
});

export const subscriptionCancelSchema = z.object({
  reason: z.string().trim().min(10).max(500),
});

export const invoiceVoidSchema = z.object({
  reason: z.string().trim().min(10).max(500),
});

export const paymentRejectSchema = z.object({
  reason: z.string().trim().min(10).max(500),
});

export type RecordPaymentInput = z.infer<typeof recordPaymentSchema>;
export type SubscriptionPlanInput = z.infer<typeof subscriptionPlanSchema>;
export type SubscriptionPlanPatchInput = z.infer<typeof subscriptionPlanPatchSchema>;
export type SubscriptionCreateInput = z.infer<typeof subscriptionCreateSchema>;
export type SubscriptionCancelInput = z.infer<typeof subscriptionCancelSchema>;
export type InvoiceVoidInput = z.infer<typeof invoiceVoidSchema>;
export type PaymentRejectInput = z.infer<typeof paymentRejectSchema>;
```

- [ ] **Step 2: `fees.ts`**

```typescript
// admin/packages/schemas/src/fees.ts
import { z } from "zod";
import { currencyCode, idempotencyKey, isoDate, moneyString, uuid } from "./common";

export const feeApplicableToSchema = z.enum([
  "member",
  "loan",
  "savings_account",
  "share_account",
]);

export const feeAmountKindSchema = z.enum([
  "fixed",
  "percentage",
  "tiered",
]);

export const feeTriggerKindSchema = z.enum([
  "event",
  "scheduled",
  "manual",
]);

export const feeTypeSchema = z.object({
  code: z
    .string()
    .trim()
    .min(1)
    .max(40)
    .regex(/^[a-z0-9_]+$/, "Use lowercase, digits, or _"),
  name: z.string().trim().min(1).max(200),
  description: z.string().trim().max(1000).optional().or(z.literal("")),
  applicable_to: feeApplicableToSchema,
  amount_kind: feeAmountKindSchema,
  amount: moneyString({ min: "0" }),
  currency: currencyCode.default("UGX"),
  trigger_kind: feeTriggerKindSchema,
  event_name: z.string().trim().max(100).optional().or(z.literal("")),
  schedule_config: z.record(z.string(), z.unknown()).optional(),
  gl_income_account_code: z.string().trim().min(1).max(20),
  gl_receivable_account_code: z.string().trim().min(1).max(20),
  requires_collection: z.boolean().default(true),
});

export const feeTypePatchSchema = z
  .object({
    name: z.string().trim().min(1).max(200).optional(),
    description: z.string().trim().max(1000).optional().or(z.literal("")),
    amount: moneyString({ min: "0" }).optional(),
    is_active: z.boolean().optional(),
    requires_collection: z.boolean().optional(),
  })
  .strict();

export const feeAssessmentSchema = z.object({
  fee_type_id: uuid,
  target_type: z.enum(["member", "loan", "savings_account"]),
  target_id: uuid,
  period_start: isoDate,
  period_end: isoDate,
});

export const feeCollectionSchema = z
  .object({
    fee_assessment_id: uuid,
    amount: moneyString({ min: "0.01" }),
    method: z.enum(["cash", "journal_voucher"]),
    contra_account_id: uuid.optional(),
    idempotency_key: idempotencyKey,
  })
  .refine(
    (data) =>
      data.method !== "journal_voucher" || data.contra_account_id !== undefined,
    {
      message: "contra_account_id is required for journal_voucher",
      path: ["contra_account_id"],
    },
  );

export type FeeTypeInput = z.infer<typeof feeTypeSchema>;
export type FeeTypePatchInput = z.infer<typeof feeTypePatchSchema>;
export type FeeAssessmentInput = z.infer<typeof feeAssessmentSchema>;
export type FeeCollectionInput = z.infer<typeof feeCollectionSchema>;
```

- [ ] **Step 3: `ledger.ts`**

```typescript
// admin/packages/schemas/src/ledger.ts
import { z } from "zod";
import { idempotencyKey, moneyString, uuid } from "./common";

export const accountTypeSchema = z.enum([
  "asset",
  "liability",
  "equity",
  "income",
  "expense",
]);

export const accountSchema = z.object({
  code: z
    .string()
    .trim()
    .min(1)
    .max(20)
    .regex(/^[A-Z0-9.\-_]+$/, "Use uppercase letters, digits, ., -, or _"),
  name: z.string().trim().min(1).max(200),
  account_type: accountTypeSchema,
  parent_id: uuid.optional(),
  description: z.string().trim().max(1000).optional().or(z.literal("")),
});

// Manual GL entry — debits MUST equal credits.
export const journalLineSchema = z.object({
  account_id: uuid,
  debit_amount: moneyString({ min: "0" }).default("0"),
  credit_amount: moneyString({ min: "0" }).default("0"),
  description: z.string().trim().max(500).optional().or(z.literal("")),
});

export const manualJournalEntrySchema = z
  .object({
    reference: z.string().trim().min(1).max(50),
    description: z.string().trim().min(1).max(500),
    lines: z.array(journalLineSchema).min(2, "Need at least two lines"),
    idempotency_key: idempotencyKey,
  })
  .refine(
    (data) => {
      const totalDebit = data.lines.reduce(
        (s, l) => s + Number.parseFloat(l.debit_amount),
        0,
      );
      const totalCredit = data.lines.reduce(
        (s, l) => s + Number.parseFloat(l.credit_amount),
        0,
      );
      return Math.abs(totalDebit - totalCredit) < 0.0001;
    },
    { message: "Debits must equal credits", path: ["lines"] },
  )
  .refine(
    (data) =>
      data.lines.every(
        (l) =>
          (Number.parseFloat(l.debit_amount) > 0) !==
          (Number.parseFloat(l.credit_amount) > 0),
      ),
    {
      message: "Each line must be either a debit OR a credit, not both",
      path: ["lines"],
    },
  );

export type AccountInput = z.infer<typeof accountSchema>;
export type ManualJournalEntryInput = z.infer<typeof manualJournalEntrySchema>;
export type AccountType = z.infer<typeof accountTypeSchema>;
```

- [ ] **Step 4: Billing tests** (the largest of the three — covers the most surface)

```typescript
// admin/packages/schemas/src/__tests__/billing.test.ts
import { describe, expect, it } from "vitest";
import {
  recordPaymentSchema,
  subscriptionPlanPatchSchema,
  subscriptionPlanSchema,
} from "../billing";

describe("recordPaymentSchema", () => {
  const ok = {
    amount: "50000.00",
    currency: "UGX",
    payment_method: "bank_transfer" as const,
    idempotency_key: "12345678",
  };

  it("accepts a valid payment", () => {
    expect(() => recordPaymentSchema.parse(ok)).not.toThrow();
  });

  it("defaults currency to UGX when omitted", () => {
    const { currency, ...rest } = ok;
    void currency;
    const parsed = recordPaymentSchema.parse(rest);
    expect(parsed.currency).toBe("UGX");
  });

  it("rejects invalid payment_method", () => {
    expect(() =>
      recordPaymentSchema.parse({
        ...ok,
        payment_method: "crypto" as never,
      }),
    ).toThrow();
  });

  it("rejects too-short idempotency_key", () => {
    expect(() =>
      recordPaymentSchema.parse({ ...ok, idempotency_key: "short" }),
    ).toThrow();
  });
});

describe("subscriptionPlanSchema", () => {
  it("requires a code matching the slug pattern", () => {
    expect(() =>
      subscriptionPlanSchema.parse({
        code: "Starter Plan",
        name: "Starter",
        base_price: "0",
        billing_period: "monthly",
      }),
    ).toThrow();
  });

  it("applies defaults for per_user_price + grace_period_days", () => {
    const plan = subscriptionPlanSchema.parse({
      code: "starter",
      name: "Starter",
      base_price: "50000",
      billing_period: "monthly",
    });
    expect(plan.per_user_price).toBe("0");
    expect(plan.grace_period_days).toBe(30);
  });
});

describe("subscriptionPlanPatchSchema", () => {
  it("accepts a partial update", () => {
    expect(() =>
      subscriptionPlanPatchSchema.parse({ name: "Starter v2" }),
    ).not.toThrow();
  });

  it("rejects unknown keys (strict)", () => {
    expect(() =>
      subscriptionPlanPatchSchema.parse({ code: "cannot-change" }),
    ).toThrow();
  });
});
```

- [ ] **Step 5: Index re-exports**

```typescript
// admin/packages/schemas/src/index.ts
export * from "./common";
export * from "./auth";
export * from "./member";
export * from "./savings";
export * from "./credit";
export * from "./billing";
export * from "./fees";
export * from "./ledger";
```

- [ ] **Step 6: Run + commit**

```bash
cd admin
pnpm --filter @sacco/schemas test
pnpm --filter @sacco/schemas typecheck
pnpm --filter @sacco/schemas lint
```

```bash
git add admin/packages/schemas/src/{billing.ts,fees.ts,ledger.ts,__tests__/billing.test.ts,index.ts}
git commit -m "feat(schemas): billing + fees + ledger schemas (with billing tests)"
```

---

## Task 5: Final verification

- [ ] **Step 1: Full pipeline**

```bash
cd admin
pnpm install
pnpm typecheck
pnpm lint
pnpm test
```
Expected: green.

- [ ] **Step 2: PR**

```bash
git push -u origin feat/portal-v1/06-schemas
gh pr create --title "feat(schemas): Zod mirrors for portal forms" --body "$(cat <<'EOF'
## Summary
- `@sacco/schemas` package shipping per-module Zod schemas matching the backend's Pydantic request bodies
- `common.ts` primitives: `moneyString` (Decimal-as-string, ≤4 dp, CLAUDE.md rule #5), `percentageString`, `currencyCode`, `uuid`, `isoDate`, `isoDateTime`, `cursorPagination` (matches P1.7-06 audit cursor), `idempotencyKey`
- `auth.ts`: login (platform + tenant share shape), refresh, password reset request + confirm (passwords match + ≥12 chars)
- `member.ts`: registration (full_name / dob / gender / optional contact + ID), status change (reason ≥10 chars)
- `savings.ts`: open account, deposit, withdraw
- `credit.ts`: loan application, repayment, disburse, restructure (periods ≥1, reason ≥20), write-off, recovery, loan product
- `billing.ts`: record payment, plan create + patch (PATCH is `.strict()` — rejects code/billing_period changes), subscription create + cancel, invoice void, payment reject
- `fees.ts`: fee type CRUD, manual assessment, collection (cross-field check: `journal_voucher` requires `contra_account_id`)
- `ledger.ts`: account create, manual GL entry (cross-line validators: debits = credits, each line is debit XOR credit)

## Out of scope
- Reporting query schemas (passed as URL params, not bodies — no Zod needed)
- Approval submit shape (`makerChecker`) — done in the resource client directly
- Tenant-user CRUD body (P1.7-04) — will land when that endpoint's portal screen is built

## Test plan
- [ ] `pnpm --filter @sacco/schemas test` — happy + sad cases per domain
- [ ] `pnpm typecheck` clean
- [ ] `pnpm lint` clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `@sacco/schemas` exports `common`, `auth`, `member`, `savings`, `credit`, `billing`, `fees`, `ledger`
- [ ] Every schema's TypeScript type is inferred via `z.infer<>` — no hand-written shapes
- [ ] `moneyString` enforces Decimal-as-string with ≤4 dp, optional min/max, optional negative
- [ ] Cross-field validation: password-reset-confirm matches, fee `journal_voucher` requires `contra_account_id`, manual journal debits = credits + each line is debit XOR credit, plan PATCH is `.strict()`
- [ ] All Vitest cases pass; typecheck + lint clean
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** use Zod numbers for money. Strings are the wire format. The backend's Pydantic `Decimal` accepts strings; the portal sends strings; the `<MoneyInput>` reformats but the value stored in the form is a string.
- **Do not** add server-only logic to these schemas. They validate the client side. The server still re-validates with Pydantic.
- **Do not** copy the backend's per-currency precision rules here. The schema accepts ≤4 dp; the input component enforces UGX → 0, KES/USD → 2 dp on user-facing display + submit-time formatting.
- **Do not** introduce a "DateInput-friendly" date type. `isoDate` is `YYYY-MM-DD` — the standard for `<input type="date">` and FastAPI date parameters.
- The `loanRestructureSchema.periods_added` lower bound is 1. The backend may accept 0 in principle (a no-op restructure) but the portal disallows it — there's no operational use case.
- The `manualJournalEntrySchema` cross-line validator uses `Math.abs(... < 0.0001)` because parseFloat can introduce floating-point fuzz. For perfect precision the right answer is BigDecimal — but the form's UX (user types numbers) means floats are good enough for client-side validation; the backend's exact-precision check is the authoritative one.
- The `subscriptionPlanPatchSchema` is `.strict()` — sending an unknown key (like `code`) errors. This is on purpose: the schema acts as a hard guard against forms accidentally PATCH-ing immutable fields.
- The `paymentMethodSchema`, `disbursementDestinationSchema`, and other enum variants are stable. If the backend adds a new variant, mirror it here in a follow-up PR — do NOT use a more permissive `z.string()`.
- For optional string fields with `.or(z.literal(""))`: this lets the form submit an empty string (the user cleared the field) while the schema still treats it as "absent". The backend's optional Pydantic fields accept `null` or omitted; the api-client serialises empty strings to omitted.
- The `idempotencyKey` schema requires ≥8 chars (matches the backend's `PaymentRecordIn` validator). Forms should not generate these manually — the `<MakerCheckerConfirmDialog>` from sub-plan 11 will mint one and pass it through.
- If a future sub-plan adds a form whose schema isn't here yet, add the schema before the form. Do not co-locate Zod schemas inside the consuming sub-plan; centralisation is the contract.
