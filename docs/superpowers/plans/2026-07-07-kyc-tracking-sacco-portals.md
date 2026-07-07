# KYC Tracking Increment 3 — SACCO Org-KYC Portals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portal UI for the SACCO org-KYC backend shipped in increments 1–2: the operator "Organization KYC" self-attestation page, the platform tenant-detail KYC section with Verify/Unverify, and the platform Settings → SACCO KYC requirements toggles.

**Architecture:** Pure client of the existing API (zero new endpoints). Three new screens in `admin/apps/portal` share one app-local `KycCompletionCard` component. Types + Zod form schema live in `@sacco/schemas`; thin resource wrappers + query keys in `@sacco/api-client`. Server components fetch initial data; client components mutate via TanStack Query (`useTypedMutation`) and hold the latest `OrganizationKycOut` returned by each mutation in local state.

**Tech Stack:** Next.js 15 App Router, React 19, TypeScript strict, React Hook Form + Zod, TanStack Query, `@sacco/ui` primitives, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-06-30-kyc-fulfilment-tracking-design.md` (§Portal design → Operator + Platform portals; §API surface; §Schemas; §Testing).

## Global Constraints

- **Zero new API endpoints** (portal contract B). The five endpoints consumed here already exist on `main` (merged via PR #57): `GET/PUT /organization/kyc`, `GET/PUT /platform/kyc/sacco-requirements`, `GET /platform/tenants/{id}/kyc`, `POST .../kyc/verify`, `POST .../kyc/unverify`.
- Do NOT modify anything outside `admin/` except `CLAUDE.md` (Task 9 contract append) — portal contract N.
- Forms: React Hook Form + Zod; schemas in `@sacco/schemas` (contract J). Fields render through `<FormField control name label render />` (contract U).
- No `toLocaleString`; numbers through `@sacco/ui` primitives — the completion percent renders via `<Percentage value={string} />` (contract R; its `value` prop is a decimal-as-string 0–100).
- Confirmations through `<ConfirmDialog>`; verify/unverify are **direct** operations (no maker-checker), so NOT `<MakerCheckerConfirmDialog>` (contract V).
- Colors via `var(--...)` tokens only; no literal hex (contract Q).
- No client-side data fetching for initial render — server components fetch via the typed client (contract M).
- UI permission gating is UX-only; the API enforces (contract D). Backend gates: operator endpoints = any `CurrentTenantUser`; platform endpoints = `CurrentAdmin`.
- Verify-when-incomplete returns **409** from the API; the UI additionally disables the button (spec: "Verify disabled until complete").
- All commands below run from `/home/liam/projects/sacco-platform/admin` unless stated otherwise.

## Prerequisites (check before Task 1)

1. **The in-flight portal-UX refactor must be committed/landed first.** This plan modifies `admin/apps/portal/src/components/shell/nav-config.tsx`, which is currently an *untracked* file in the working tree (part of the uncommitted AppShell refactor, ~147 files). If you start this plan on a clean branch off `main` without that refactor, `nav-config.tsx` will not exist and Tasks 5–6 cannot apply. **Stop and surface to the user if `admin/apps/portal/src/components/shell/nav-config.tsx` does not exist.**
2. Work on a new branch off the branch containing the refactor: `git checkout -b feat/kyc-portals`.
3. `pnpm install` has already been run in `admin/` (node_modules present).

## File Structure

```
admin/packages/schemas/src/kyc.ts                                        (new — types, form schema, field config, payload helpers)
admin/packages/schemas/src/__tests__/kyc.test.ts                         (new)
admin/packages/schemas/src/index.ts                                      (modify — add export)
admin/packages/api-client/src/resources/organization.ts                  (new — operator /organization/kyc)
admin/packages/api-client/src/resources/kyc.ts                           (new — platform KYC endpoints)
admin/packages/api-client/src/resources/index.ts                         (modify — wire both)
admin/packages/api-client/src/query-keys.ts                              (modify — organization + kyc keys, tenants.kyc)
admin/packages/api-client/src/__tests__/query-keys-kyc.test.ts           (new)
admin/apps/portal/src/components/kyc/KycCompletionCard.tsx               (new — shared percent bar + checklist)
admin/apps/portal/src/components/kyc/__tests__/KycCompletionCard.test.tsx (new)
admin/apps/portal/app/(tenant-authed)/organization/kyc/page.tsx          (new — operator server page)
admin/apps/portal/app/(tenant-authed)/organization/kyc/_components/OrganizationKycScreen.tsx (new — client form + completion)
admin/apps/portal/app/(tenant-authed)/organization/kyc/__tests__/OrganizationKycScreen.test.tsx (new)
admin/apps/portal/app/platform/(authed)/settings/kyc/page.tsx            (new — platform settings server page)
admin/apps/portal/app/platform/(authed)/settings/kyc/_components/SaccoKycRequirementsForm.tsx (new)
admin/apps/portal/app/platform/(authed)/settings/kyc/__tests__/SaccoKycRequirementsForm.test.tsx (new)
admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantKycSection.tsx (new)
admin/apps/portal/app/platform/(authed)/tenants/[id]/__tests__/TenantKycSection.test.tsx (new)
admin/apps/portal/app/platform/(authed)/tenants/[id]/page.tsx            (modify — fetch KYC, pass section)
admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx (modify — kycSection prop)
admin/apps/portal/src/components/shell/nav-config.tsx                    (modify — operator nav group + platform settings child)
CLAUDE.md                                                                 (modify — Task 9, KYC contracts section)
```

---

### Task 1: `@sacco/schemas` — KYC types, form schema, field config, payload helpers

**Files:**
- Create: `admin/packages/schemas/src/kyc.ts`
- Create: `admin/packages/schemas/src/__tests__/kyc.test.ts`
- Modify: `admin/packages/schemas/src/index.ts`

**Interfaces:**
- Consumes: nothing (leaf package).
- Produces (imported by every later task): `KycFieldStatusOut`, `KycCompletionOut`, `OrganizationKycValuesOut`, `OrganizationKycValuesIn`, `OrganizationKycOut`, `SaccoKycRequirementItemOut`, `SaccoKycRequirementsOut`, `organizationKycFormSchema`, `OrganizationKycFormInput`, `OrganizationKycFieldKey`, `ORGANIZATION_KYC_FIELDS`, `organizationKycFormDefaults(values): OrganizationKycFormInput`, `toOrganizationKycPayload(input): OrganizationKycValuesIn`.

- [ ] **Step 1: Write the failing test**

Create `admin/packages/schemas/src/__tests__/kyc.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  ORGANIZATION_KYC_FIELDS,
  organizationKycFormDefaults,
  organizationKycFormSchema,
  toOrganizationKycPayload,
  type OrganizationKycValuesOut,
} from "../kyc";

const serverValues: OrganizationKycValuesOut = {
  legal_name: "Kampala Teachers SACCO",
  registration_number: null,
  registered_address: null,
  primary_contact_name: null,
  primary_contact_email: null,
  registration_date: null,
  regulator_name: null,
  license_number: null,
  tax_id: null,
  primary_contact_phone: null,
  postal_address: null,
  district_region: null,
  country: null,
};

describe("organizationKycFormSchema", () => {
  it("accepts a fully blank form (all fields optional client-side)", () => {
    const result = organizationKycFormSchema.safeParse(
      organizationKycFormDefaults(serverValues),
    );
    expect(result.success).toBe(true);
  });

  it("rejects a malformed contact email but accepts empty string", () => {
    const base = organizationKycFormDefaults(serverValues);
    expect(
      organizationKycFormSchema.safeParse({ ...base, primary_contact_email: "not-an-email" })
        .success,
    ).toBe(false);
    expect(
      organizationKycFormSchema.safeParse({ ...base, primary_contact_email: "" }).success,
    ).toBe(true);
  });

  it("rejects a malformed registration date but accepts empty string", () => {
    const base = organizationKycFormDefaults(serverValues);
    expect(
      organizationKycFormSchema.safeParse({ ...base, registration_date: "01/02/2026" }).success,
    ).toBe(false);
    expect(
      organizationKycFormSchema.safeParse({ ...base, registration_date: "2026-02-01" }).success,
    ).toBe(true);
  });
});

describe("organizationKycFormDefaults / toOrganizationKycPayload", () => {
  it("maps server nulls to empty strings for the form", () => {
    const defaults = organizationKycFormDefaults(serverValues);
    expect(defaults.legal_name).toBe("Kampala Teachers SACCO");
    expect(defaults.country).toBe("");
  });

  it("maps blank strings back to null on the wire (blank must not count as present)", () => {
    const payload = toOrganizationKycPayload({
      ...organizationKycFormDefaults(serverValues),
      country: "  ",
    });
    expect(payload.legal_name).toBe("Kampala Teachers SACCO");
    expect(payload.country).toBeNull();
    expect(payload.tax_id).toBeNull();
  });
});

describe("ORGANIZATION_KYC_FIELDS", () => {
  it("covers all 13 catalog keys with the 5 locked minimums first", () => {
    expect(ORGANIZATION_KYC_FIELDS).toHaveLength(13);
    expect(ORGANIZATION_KYC_FIELDS.filter((f) => f.locked).map((f) => f.key)).toEqual([
      "legal_name",
      "registration_number",
      "registered_address",
      "primary_contact_name",
      "primary_contact_email",
    ]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter @sacco/schemas exec vitest run src/__tests__/kyc.test.ts`
Expected: FAIL — `Cannot find module '../kyc'` (or equivalent resolve error).

- [ ] **Step 3: Write the implementation**

Create `admin/packages/schemas/src/kyc.ts`:

```ts
// admin/packages/schemas/src/kyc.ts
import { z } from "zod";

// ---- Wire shapes (mirror app/modules/organization/schemas.py and
// app/platform_/kyc/schemas.py; dates are ISO strings over the wire). ----

export interface KycFieldStatusOut {
  key: string;
  label: string;
  required: boolean;
  present: boolean;
}

export interface KycCompletionOut {
  items: KycFieldStatusOut[];
  required_total: number;
  required_present: number;
  percent: number;
  missing_required: string[];
  is_complete: boolean;
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

// Mirrors OrganizationKycValuesIn: 13 catalog keys, each nullable. The form
// models "not provided" as "" and toOrganizationKycPayload converts back to
// null so a blank never gets stored as a present-looking empty string.
export const organizationKycFormSchema = z.object({
  legal_name: z.string().trim(),
  registration_number: z.string().trim(),
  registered_address: z.string().trim(),
  primary_contact_name: z.string().trim(),
  primary_contact_email: z
    .string()
    .trim()
    .toLowerCase()
    .email("Enter a valid email address")
    .or(z.literal("")),
  registration_date: z
    .string()
    .regex(ISO_DATE_RE, "Use the date picker (YYYY-MM-DD)")
    .or(z.literal("")),
  regulator_name: z.string().trim(),
  license_number: z.string().trim(),
  tax_id: z.string().trim(),
  primary_contact_phone: z.string().trim(),
  postal_address: z.string().trim(),
  district_region: z.string().trim(),
  country: z.string().trim(),
});
export type OrganizationKycFormInput = z.infer<typeof organizationKycFormSchema>;
export type OrganizationKycFieldKey = keyof OrganizationKycFormInput;

export type OrganizationKycValuesOut = { [K in OrganizationKycFieldKey]: string | null };
export type OrganizationKycValuesIn = { [K in OrganizationKycFieldKey]: string | null };

export interface OrganizationKycOut {
  values: OrganizationKycValuesOut;
  verified: boolean;
  verified_at: string | null;
  verified_by_platform_user_id: string | null;
  completion: KycCompletionOut;
}

export interface SaccoKycRequirementItemOut {
  key: string;
  label: string;
  locked: boolean;
  required: boolean;
}

export interface SaccoKycRequirementsOut {
  items: SaccoKycRequirementItemOut[];
}

// ---- Form-rendering config. Labels mirror SACCO_KYC_CATALOG in
// app/core/kyc/catalog.py verbatim. `required` is NOT here — it is
// config-dependent and read at runtime from completion.items. ----

export interface OrganizationKycFieldSpec {
  key: OrganizationKycFieldKey;
  label: string;
  kind: "text" | "email" | "date";
  locked: boolean;
}

export const ORGANIZATION_KYC_FIELDS: readonly OrganizationKycFieldSpec[] = [
  { key: "legal_name", label: "Registered legal name", kind: "text", locked: true },
  { key: "registration_number", label: "Registration number", kind: "text", locked: true },
  { key: "registered_address", label: "Registered physical address", kind: "text", locked: true },
  { key: "primary_contact_name", label: "Primary contact name", kind: "text", locked: true },
  { key: "primary_contact_email", label: "Primary contact email", kind: "email", locked: true },
  { key: "registration_date", label: "Date of registration", kind: "date", locked: false },
  { key: "regulator_name", label: "Regulator", kind: "text", locked: false },
  { key: "license_number", label: "License number", kind: "text", locked: false },
  { key: "tax_id", label: "Tax identification number", kind: "text", locked: false },
  { key: "primary_contact_phone", label: "Primary contact phone", kind: "text", locked: false },
  { key: "postal_address", label: "Postal address", kind: "text", locked: false },
  { key: "district_region", label: "District / region", kind: "text", locked: false },
  { key: "country", label: "Country", kind: "text", locked: false },
];

/** Server nulls → form empty strings. */
export function organizationKycFormDefaults(
  values: OrganizationKycValuesOut,
): OrganizationKycFormInput {
  const out = {} as Record<OrganizationKycFieldKey, string>;
  for (const field of ORGANIZATION_KYC_FIELDS) {
    out[field.key] = values[field.key] ?? "";
  }
  return out;
}

/** Form empty/blank strings → null on the wire. */
export function toOrganizationKycPayload(
  input: OrganizationKycFormInput,
): OrganizationKycValuesIn {
  const out = {} as Record<OrganizationKycFieldKey, string | null>;
  for (const field of ORGANIZATION_KYC_FIELDS) {
    const raw = input[field.key].trim();
    out[field.key] = raw === "" ? null : raw;
  }
  return out;
}
```

Modify `admin/packages/schemas/src/index.ts` — append one line:

```ts
export * from "./kyc";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter @sacco/schemas exec vitest run src/__tests__/kyc.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Package checks + commit**

Run: `pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint`
Expected: both exit 0.

```bash
git add admin/packages/schemas/src/kyc.ts admin/packages/schemas/src/__tests__/kyc.test.ts admin/packages/schemas/src/index.ts
git commit -m "feat(schemas): KYC wire types, org-KYC form schema + field config"
```

---

### Task 2: `@sacco/api-client` — organization + platform KYC resources, query keys

**Files:**
- Create: `admin/packages/api-client/src/resources/organization.ts`
- Create: `admin/packages/api-client/src/resources/kyc.ts`
- Modify: `admin/packages/api-client/src/resources/index.ts`
- Modify: `admin/packages/api-client/src/query-keys.ts`
- Create: `admin/packages/api-client/src/__tests__/query-keys-kyc.test.ts`

**Interfaces:**
- Consumes: `FetchClient` from `../client` (existing).
- Produces: `resources.organization.getKyc()`, `resources.organization.putKyc(body)`, `resources.kyc.getSaccoRequirements()`, `resources.kyc.putSaccoRequirements({ required })`, `resources.kyc.getTenantKyc(tenantId)`, `resources.kyc.verifyTenant(tenantId)`, `resources.kyc.unverifyTenant(tenantId)`; `queryKeys.organization.root()/.kyc()`, `queryKeys.kyc.root()/.saccoRequirements()`, `queryKeys.tenants.kyc(id)`. All resource methods return the client's `Promise<{ data?, error? }>` shape (typed `never` via the established `as never` cast pattern — callers cast, same as `resources.tenants.get`).

- [ ] **Step 1: Write the failing test**

Create `admin/packages/api-client/src/__tests__/query-keys-kyc.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { queryKeys } from "../query-keys";

describe("KYC query keys", () => {
  it("organization keys nest under a common root for invalidation", () => {
    expect(queryKeys.organization.root()).toEqual(["organization"]);
    expect(queryKeys.organization.kyc()).toEqual(["organization", "kyc"]);
  });

  it("platform kyc keys nest under a common root", () => {
    expect(queryKeys.kyc.root()).toEqual(["kyc"]);
    expect(queryKeys.kyc.saccoRequirements()).toEqual(["kyc", "saccoRequirements"]);
  });

  it("tenant kyc key is scoped by tenant id", () => {
    expect(queryKeys.tenants.kyc("t1")).toEqual(["tenants", "kyc", "t1"]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter @sacco/api-client exec vitest run src/__tests__/query-keys-kyc.test.ts`
Expected: FAIL — `queryKeys.organization` is undefined.

- [ ] **Step 3: Write the implementation**

Create `admin/packages/api-client/src/resources/organization.ts`:

```ts
import type { FetchClient } from "../client";

export function organization(api: FetchClient) {
  return {
    getKyc: () => api.GET("/organization/kyc" as never),
    putKyc: (body: Record<string, string | null>) =>
      api.PUT("/organization/kyc" as never, { body } as never),
  } as const;
}
```

Create `admin/packages/api-client/src/resources/kyc.ts`:

```ts
import type { FetchClient } from "../client";

export function kyc(api: FetchClient) {
  return {
    getSaccoRequirements: () =>
      api.GET("/platform/kyc/sacco-requirements" as never),
    putSaccoRequirements: (body: { required: Record<string, boolean> }) =>
      api.PUT("/platform/kyc/sacco-requirements" as never, { body } as never),
    getTenantKyc: (tenantId: string) =>
      api.GET("/platform/tenants/{tenant_id}/kyc" as never, {
        params: { path: { tenant_id: tenantId } },
      } as never),
    verifyTenant: (tenantId: string) =>
      api.POST("/platform/tenants/{tenant_id}/kyc/verify" as never, {
        params: { path: { tenant_id: tenantId } },
      } as never),
    unverifyTenant: (tenantId: string) =>
      api.POST("/platform/tenants/{tenant_id}/kyc/unverify" as never, {
        params: { path: { tenant_id: tenantId } },
      } as never),
  } as const;
}
```

Modify `admin/packages/api-client/src/resources/index.ts` — add the two imports and registry entries:

```ts
import { organization } from "./organization";
import { kyc } from "./kyc";
```

and inside `buildResources`'s returned object (after `memberAuth: memberAuth(api),`):

```ts
    organization: organization(api),
    kyc: kyc(api),
```

Modify `admin/packages/api-client/src/query-keys.ts`:

In the `tenants` block, add after `users: ...`:

```ts
    kyc: (id: string) => ["tenants", "kyc", id] as const,
```

After the `member` block (before the closing `} as const;`), add:

```ts
  organization: {
    root: () => ["organization"] as const,
    kyc: () => ["organization", "kyc"] as const,
  },
  kyc: {
    root: () => ["kyc"] as const,
    saccoRequirements: () => ["kyc", "saccoRequirements"] as const,
  },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter @sacco/api-client exec vitest run src/__tests__/query-keys-kyc.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Package checks + commit**

Run: `pnpm --filter @sacco/api-client test && pnpm --filter @sacco/api-client typecheck && pnpm --filter @sacco/api-client lint`
Expected: all exit 0 (existing suites still green).

```bash
git add admin/packages/api-client/src/resources/organization.ts admin/packages/api-client/src/resources/kyc.ts admin/packages/api-client/src/resources/index.ts admin/packages/api-client/src/query-keys.ts admin/packages/api-client/src/__tests__/query-keys-kyc.test.ts
git commit -m "feat(api-client): organization + platform KYC resources and query keys"
```

---

### Task 3: `KycCompletionCard` shared portal component

**Files:**
- Create: `admin/apps/portal/src/components/kyc/KycCompletionCard.tsx`
- Create: `admin/apps/portal/src/components/kyc/__tests__/KycCompletionCard.test.tsx`

**Interfaces:**
- Consumes: `KycCompletionOut` from `@sacco/schemas`; `Card`, `Percentage` from `@sacco/ui`.
- Produces: `KycCompletionCard({ completion, title? }: { completion: KycCompletionOut; title?: string })` — used by Tasks 4 and 7 (and by increments 4–5 later for member KYC).

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/src/components/kyc/__tests__/KycCompletionCard.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { KycCompletionOut } from "@sacco/schemas";
import { KycCompletionCard } from "../KycCompletionCard";

const incomplete: KycCompletionOut = {
  items: [
    { key: "legal_name", label: "Registered legal name", required: true, present: true },
    { key: "tax_id", label: "Tax identification number", required: true, present: false },
    { key: "postal_address", label: "Postal address", required: false, present: false },
  ],
  required_total: 2,
  required_present: 1,
  percent: 50,
  missing_required: ["tax_id"],
  is_complete: false,
};

describe("KycCompletionCard", () => {
  it("renders the percent, progress bar, and required-progress summary", () => {
    render(<KycCompletionCard completion={incomplete} />);
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
    expect(screen.getByText(/1 of 2 required items complete/i)).toBeInTheDocument();
  });

  it("lists every catalog item and marks optional ones", () => {
    render(<KycCompletionCard completion={incomplete} />);
    expect(screen.getByText("Registered legal name")).toBeInTheDocument();
    expect(screen.getByText("Tax identification number")).toBeInTheDocument();
    expect(screen.getByText("Postal address")).toBeInTheDocument();
    expect(screen.getByText("(optional)")).toBeInTheDocument();
  });

  it("shows the all-complete summary when complete", () => {
    render(
      <KycCompletionCard
        completion={{
          ...incomplete,
          required_present: 2,
          percent: 100,
          missing_required: [],
          is_complete: true,
          items: incomplete.items.map((i) => ({ ...i, present: true })),
        }}
      />,
    );
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText(/all required items are complete/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter @sacco/portal exec vitest run src/components/kyc/__tests__/KycCompletionCard.test.tsx`
Expected: FAIL — cannot resolve `../KycCompletionCard`.

- [ ] **Step 3: Write the implementation**

Create `admin/apps/portal/src/components/kyc/KycCompletionCard.tsx`:

```tsx
import { Check, Minus } from "lucide-react";
import { Card, Percentage } from "@sacco/ui";
import type { KycCompletionOut } from "@sacco/schemas";

/**
 * Shared completion tracker card: percent + progress bar + full-catalog
 * checklist. Server-computed (app/core/kyc); this component only renders —
 * it never re-derives completeness (CLAUDE.md core-tracker contract).
 */
export function KycCompletionCard({
  completion,
  title = "KYC completion",
}: {
  completion: KycCompletionOut;
  title?: string;
}) {
  return (
    <Card className="flex flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-[var(--text-h5)] font-semibold">{title}</h2>
        <Percentage
          value={String(completion.percent)}
          className="text-[var(--text-h5)] font-semibold"
        />
      </div>
      <div
        role="progressbar"
        aria-label={title}
        aria-valuenow={completion.percent}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-2 overflow-hidden rounded-full bg-[var(--status-neutral-bg)]"
      >
        <div
          className="h-full rounded-full bg-[var(--interactive-primary-bg)]"
          style={{ width: `${completion.percent}%` }}
        />
      </div>
      <p className="text-[13px] text-[var(--text-secondary)]">
        {completion.is_complete
          ? "All required items are complete."
          : `${completion.required_present} of ${completion.required_total} required items complete.`}
      </p>
      <ul className="flex flex-col gap-1.5">
        {completion.items.map((item) => (
          <li key={item.key} className="flex items-center gap-2 text-[13px]">
            {item.present ? (
              <Check size={14} className="shrink-0 text-[var(--text-success)]" aria-hidden />
            ) : (
              <Minus
                size={14}
                className={
                  item.required
                    ? "shrink-0 text-[var(--text-danger)]"
                    : "shrink-0 text-[var(--text-tertiary)]"
                }
                aria-hidden
              />
            )}
            <span
              className={
                item.present
                  ? "text-[var(--text-primary)]"
                  : item.required
                    ? "text-[var(--text-danger)]"
                    : "text-[var(--text-secondary)]"
              }
            >
              {item.label}
            </span>
            {item.required ? null : (
              <span className="text-[11px] text-[var(--text-tertiary)]">(optional)</span>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter @sacco/portal exec vitest run src/components/kyc/__tests__/KycCompletionCard.test.tsx`
Expected: PASS (3 tests). If the `50%`/`100%` exact-text assertions fail because `formatPercentage` emits a different string (e.g. `50.0%`), fix the *assertions* to match the primitive's real output — do not bypass `<Percentage>`.

- [ ] **Step 5: Commit**

```bash
git add admin/apps/portal/src/components/kyc/
git commit -m "feat(portal): shared KycCompletionCard (percent bar + checklist)"
```

---

### Task 4: Operator `OrganizationKycScreen` (client form + completion + verified badge)

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/organization/kyc/_components/OrganizationKycScreen.tsx`
- Create: `admin/apps/portal/app/(tenant-authed)/organization/kyc/__tests__/OrganizationKycScreen.test.tsx`

**Interfaces:**
- Consumes: Task 1 schema exports; Task 2 `resources.organization.putKyc` + `queryKeys.organization.root()`; Task 3 `KycCompletionCard`; `useAuth` from `@/auth/use-auth`; `apiErrorMessage` from `@/lib/api-error`.
- Produces: `OrganizationKycScreen({ initial }: { initial: OrganizationKycOut })` — mounted by Task 5's server page.

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/app/(tenant-authed)/organization/kyc/__tests__/OrganizationKycScreen.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { OrganizationKycOut } from "@sacco/schemas";

const putKyc = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { organization: { putKyc } } }),
}));

import { OrganizationKycScreen } from "../_components/OrganizationKycScreen";

function makeKyc(overrides: Partial<OrganizationKycOut> = {}): OrganizationKycOut {
  return {
    values: {
      legal_name: "Kampala Teachers SACCO",
      registration_number: null,
      registered_address: null,
      primary_contact_name: null,
      primary_contact_email: null,
      registration_date: null,
      regulator_name: null,
      license_number: null,
      tax_id: null,
      primary_contact_phone: null,
      postal_address: null,
      district_region: null,
      country: null,
    },
    verified: false,
    verified_at: null,
    verified_by_platform_user_id: null,
    completion: {
      items: [
        { key: "legal_name", label: "Registered legal name", required: true, present: true },
        { key: "registration_number", label: "Registration number", required: true, present: false },
      ],
      required_total: 2,
      required_present: 1,
      percent: 50,
      missing_required: ["registration_number"],
      is_complete: false,
    },
    ...overrides,
  };
}

function renderScreen(initial = makeKyc()) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <OrganizationKycScreen initial={initial} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("OrganizationKycScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("pre-fills values, shows the not-verified badge and completion card", () => {
    renderScreen();
    expect(screen.getByDisplayValue("Kampala Teachers SACCO")).toBeInTheDocument();
    expect(screen.getByText(/not verified/i)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
  });

  it("submits with blanks normalised to null and re-renders the returned completion", async () => {
    const next = makeKyc();
    next.values.registration_number = "REG-001";
    next.completion = {
      ...next.completion,
      required_present: 2,
      percent: 100,
      missing_required: [],
      is_complete: true,
      items: next.completion.items.map((i) => ({ ...i, present: true })),
    };
    putKyc.mockResolvedValue({ data: next, error: undefined });

    renderScreen();
    await userEvent.type(screen.getByLabelText(/registration number/i), "REG-001");
    await userEvent.click(screen.getByRole("button", { name: /save organization kyc/i }));

    await waitFor(() => expect(putKyc).toHaveBeenCalledTimes(1));
    const payload = putKyc.mock.calls[0]?.[0] as Record<string, string | null>;
    expect(payload["registration_number"]).toBe("REG-001");
    expect(payload["country"]).toBeNull(); // blank → null, never ""
    await waitFor(() =>
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100"),
    );
  });

  it("tells the operator when a save resets platform verification", async () => {
    const reset = makeKyc(); // server resets verified on material change
    putKyc.mockResolvedValue({ data: reset, error: undefined });
    renderScreen(makeKyc({ verified: true, verified_at: "2026-07-01T00:00:00Z" }));

    expect(screen.getByText(/verified by platform/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/regulator/i), "UMRA");
    await userEvent.click(screen.getByRole("button", { name: /save organization kyc/i }));
    await waitFor(() =>
      expect(screen.getByText(/reset platform verification/i)).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter @sacco/portal exec vitest run "app/(tenant-authed)/organization/kyc/__tests__/OrganizationKycScreen.test.tsx"`
Expected: FAIL — cannot resolve `../_components/OrganizationKycScreen`.

- [ ] **Step 3: Write the implementation**

Create `admin/apps/portal/app/(tenant-authed)/organization/kyc/_components/OrganizationKycScreen.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Badge,
  Button,
  DateInput,
  FormattedDateTime,
  FormField,
  Input,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  ORGANIZATION_KYC_FIELDS,
  organizationKycFormDefaults,
  organizationKycFormSchema,
  toOrganizationKycPayload,
  type OrganizationKycFormInput,
  type OrganizationKycOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { KycCompletionCard } from "@/components/kyc/KycCompletionCard";

export function OrganizationKycScreen({ initial }: { initial: OrganizationKycOut }) {
  const { resources } = useAuth();
  const [latest, setLatest] = useState(initial);

  const form = useForm<OrganizationKycFormInput>({
    resolver: zodResolver(organizationKycFormSchema),
    defaultValues: organizationKycFormDefaults(initial.values),
  });

  // Required-ness is config-driven (platform-owned required set), so it is
  // read from the server-computed completion, not hardcoded per field.
  const requiredByKey = new Map(
    latest.completion.items.map((item) => [item.key, item.required]),
  );

  const mutation = useTypedMutation<OrganizationKycOut, OrganizationKycFormInput>(
    async (vars) => {
      // putKyc is typed Promise<never> (as-never paths); cast to the real
      // { data, error } shape, same as every other resource call site.
      const res = await (resources.organization.putKyc(
        toOrganizationKycPayload(vars),
      ) as Promise<{ data?: OrganizationKycOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.organization.root()],
      onSuccess: (data) => {
        const verificationReset = latest.verified && !data.verified;
        setLatest(data);
        form.reset(organizationKycFormDefaults(data.values));
        toast.success(
          "Organization KYC saved",
          verificationReset
            ? {
                description:
                  "Your changes reset platform verification — the platform team must re-verify.",
              }
            : undefined,
        );
      },
      onError: (error) => {
        toast.error("Organization KYC was not saved", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <h1 className="text-[var(--text-h3)] font-semibold">Organization KYC</h1>
        {latest.verified ? (
          <Badge variant="success">Verified by platform</Badge>
        ) : (
          <Badge variant="neutral">Not verified</Badge>
        )}
        {latest.verified && latest.verified_at ? (
          <span className="text-[13px] text-[var(--text-secondary)]">
            since <FormattedDateTime value={latest.verified_at} />
          </span>
        ) : null}
      </div>
      <p className="max-w-2xl text-[13px] text-[var(--text-secondary)]">
        Self-attested registration and regulatory details for this SACCO. Completion is
        informational — it does not block any operation. Verification is set by the
        platform team once all required items are complete.
      </p>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <form
          noValidate
          className="flex flex-col gap-5"
          onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
        >
          {ORGANIZATION_KYC_FIELDS.map((spec) => (
            <FormField
              key={spec.key}
              control={form.control}
              name={spec.key}
              label={spec.label}
              required={requiredByKey.get(spec.key) ?? false}
              render={({ field, id, describedBy, invalid }) =>
                spec.kind === "date" ? (
                  <DateInput
                    id={id}
                    aria-describedby={describedBy}
                    aria-invalid={invalid}
                    value={field.value}
                    onValueChange={field.onChange}
                    onBlur={field.onBlur}
                  />
                ) : (
                  <Input
                    id={id}
                    type={spec.kind === "email" ? "email" : "text"}
                    aria-describedby={describedBy}
                    aria-invalid={invalid}
                    {...field}
                  />
                )
              }
            />
          ))}
          <div>
            <Button type="submit" disabled={mutation.isPending}>
              Save organization KYC
            </Button>
          </div>
        </form>

        <div className="lg:sticky lg:top-6 lg:self-start">
          <KycCompletionCard completion={latest.completion} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter @sacco/portal exec vitest run "app/(tenant-authed)/organization/kyc/__tests__/OrganizationKycScreen.test.tsx"`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/(tenant-authed)/organization/kyc/"
git commit -m "feat(portal): operator Organization KYC screen (form + completion + verified badge)"
```

---

### Task 5: Operator page route + nav entry

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/organization/kyc/page.tsx`
- Modify: `admin/apps/portal/src/components/shell/nav-config.tsx`

**Interfaces:**
- Consumes: `getTenantPageContext` from `@/auth/server-page-context`; Task 2 `resources.organization.getKyc`; Task 4 `OrganizationKycScreen`; `OrganizationKycOut` from `@sacco/schemas`.
- Produces: route `/organization/kyc` in the operator audience; "Organization" nav group.

- [ ] **Step 1: Create the server page**

Create `admin/apps/portal/app/(tenant-authed)/organization/kyc/page.tsx`:

```tsx
import type { OrganizationKycOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { OrganizationKycScreen } from "./_components/OrganizationKycScreen";

export const metadata = { title: "Organization KYC" };

export default async function OrganizationKycPage() {
  const { resources } = await getTenantPageContext();

  // getKyc is typed Promise<never> (as-never paths); cast to the real
  // { data, error } shape. GET lazily get-or-creates the singleton, so a
  // missing profile is not a 404 — any failure here is a real error.
  const { data, error } = await (resources.organization.getKyc() as Promise<{
    data?: OrganizationKycOut;
    error?: unknown;
  }>);
  if (!data) throw new Error(`Failed to load organization KYC: ${JSON.stringify(error)}`);

  return <OrganizationKycScreen initial={data} />;
}
```

- [ ] **Step 2: Add the nav group**

Modify `admin/apps/portal/src/components/shell/nav-config.tsx`:

Add `ShieldCheck` to the existing `lucide-react` import list (keep alphabetical order).

In `TENANT_NAV`, insert a new group between the `Billing` group and the `Approvals & Audit` group:

```ts
  {
    label: "Organization",
    items: [
      { label: "Organization KYC", href: "/organization/kyc", icon: ShieldCheck },
    ],
  },
```

- [ ] **Step 3: Verify**

Run: `pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint && pnpm --filter @sacco/portal test`
Expected: all exit 0 (nav-config has existing sidebar tests — if a snapshot/count assertion fails because of the new group, update that test to include the new "Organization KYC" entry; that is the only acceptable test edit here).

- [ ] **Step 4: Commit**

```bash
git add "admin/apps/portal/app/(tenant-authed)/organization/kyc/page.tsx" admin/apps/portal/src/components/shell/nav-config.tsx
git commit -m "feat(portal): /organization/kyc route + operator nav entry"
```

---

### Task 6: Platform Settings → SACCO KYC requirements page

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/settings/kyc/_components/SaccoKycRequirementsForm.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/settings/kyc/__tests__/SaccoKycRequirementsForm.test.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/settings/kyc/page.tsx`
- Modify: `admin/apps/portal/src/components/shell/nav-config.tsx`

**Interfaces:**
- Consumes: Task 1 `SaccoKycRequirementsOut` / `SaccoKycRequirementItemOut`; Task 2 `resources.kyc.getSaccoRequirements` / `putSaccoRequirements` + `queryKeys.kyc.root()`; `Checkbox`, `Label`, `Card`, `Button`, `toast` from `@sacco/ui`.
- Produces: route `/platform/settings/kyc`; `SaccoKycRequirementsForm({ initial }: { initial: SaccoKycRequirementsOut })`.

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/app/platform/(authed)/settings/kyc/__tests__/SaccoKycRequirementsForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { SaccoKycRequirementsOut } from "@sacco/schemas";

const putSaccoRequirements = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { kyc: { putSaccoRequirements } } }),
}));

import { SaccoKycRequirementsForm } from "../_components/SaccoKycRequirementsForm";

const initial: SaccoKycRequirementsOut = {
  items: [
    { key: "legal_name", label: "Registered legal name", locked: true, required: true },
    { key: "tax_id", label: "Tax identification number", locked: false, required: true },
    { key: "country", label: "Country", locked: false, required: false },
  ],
};

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <SaccoKycRequirementsForm initial={initial} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("SaccoKycRequirementsForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("renders locked minimums as checked and disabled", () => {
    renderForm();
    const locked = screen.getByRole("checkbox", { name: /registered legal name/i });
    expect(locked).toBeDisabled();
    expect(locked).toBeChecked();
    expect(screen.getByText(/always required/i)).toBeInTheDocument();
  });

  it("saves only the non-locked toggles", async () => {
    putSaccoRequirements.mockResolvedValue({ data: initial, error: undefined });
    renderForm();

    await userEvent.click(screen.getByRole("checkbox", { name: /tax identification/i }));
    await userEvent.click(screen.getByRole("checkbox", { name: /country/i }));
    await userEvent.click(screen.getByRole("button", { name: /save requirements/i }));

    await waitFor(() => expect(putSaccoRequirements).toHaveBeenCalledTimes(1));
    expect(putSaccoRequirements).toHaveBeenCalledWith({
      required: { tax_id: false, country: true },
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter @sacco/portal exec vitest run "app/platform/(authed)/settings/kyc/__tests__/SaccoKycRequirementsForm.test.tsx"`
Expected: FAIL — cannot resolve `../_components/SaccoKycRequirementsForm`.

- [ ] **Step 3: Write the implementation**

Create `admin/apps/portal/app/platform/(authed)/settings/kyc/_components/SaccoKycRequirementsForm.tsx`:

```tsx
"use client";

import { useState } from "react";
import { Button, Card, Checkbox, Label, toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import type { SaccoKycRequirementsOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function SaccoKycRequirementsForm({
  initial,
}: {
  initial: SaccoKycRequirementsOut;
}) {
  const { resources } = useAuth();
  const [items, setItems] = useState(initial.items);

  const mutation = useTypedMutation<SaccoKycRequirementsOut, Record<string, boolean>>(
    async (required) => {
      // putSaccoRequirements is typed Promise<never> (as-never paths); cast
      // to the real { data, error } shape.
      const res = await (resources.kyc.putSaccoRequirements({
        required,
      }) as Promise<{ data?: SaccoKycRequirementsOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.kyc.root()],
      onSuccess: (data) => {
        setItems(data.items);
        toast.success("SACCO KYC requirements saved");
      },
      onError: (error) => {
        toast.error("The requirements were not saved", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const toggle = (key: string, next: boolean) => {
    setItems((prev) =>
      prev.map((item) => (item.key === key ? { ...item, required: next } : item)),
    );
  };

  const save = () => {
    // Locked keys are ignored server-side; keep the payload to real toggles.
    mutation.mutate(
      Object.fromEntries(
        items.filter((item) => !item.locked).map((item) => [item.key, item.required]),
      ),
    );
  };

  return (
    <Card className="flex max-w-xl flex-col gap-4 p-6">
      <p className="text-[13px] text-[var(--text-secondary)]">
        Fields required for a SACCO&apos;s organization KYC to count as complete.
        Applies to all tenants. Locked minimums cannot be toggled off.
      </p>
      <ul className="flex flex-col">
        {items.map((item) => (
          <li key={item.key} className="flex items-center gap-3 py-2">
            <Checkbox
              id={`req-${item.key}`}
              checked={item.required}
              disabled={item.locked}
              onCheckedChange={(checked) => toggle(item.key, checked === true)}
            />
            <Label htmlFor={`req-${item.key}`}>{item.label}</Label>
            {item.locked ? (
              <span className="text-[11px] text-[var(--text-tertiary)]">
                Always required
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <div>
        <Button onClick={save} disabled={mutation.isPending}>
          Save requirements
        </Button>
      </div>
    </Card>
  );
}
```

Create `admin/apps/portal/app/platform/(authed)/settings/kyc/page.tsx`:

```tsx
import type { SaccoKycRequirementsOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { SaccoKycRequirementsForm } from "./_components/SaccoKycRequirementsForm";

export const metadata = { title: "SACCO KYC requirements" };

export default async function SaccoKycSettingsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "settings.read");

  // getSaccoRequirements is typed Promise<never> (as-never paths); cast to
  // the real { data, error } shape.
  const { data, error } = await (resources.kyc.getSaccoRequirements() as Promise<{
    data?: SaccoKycRequirementsOut;
    error?: unknown;
  }>);
  if (!data) {
    throw new Error(`Failed to load SACCO KYC requirements: ${JSON.stringify(error)}`);
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">SACCO KYC requirements</h1>
      <SaccoKycRequirementsForm initial={data} />
    </div>
  );
}
```

Modify `admin/apps/portal/src/components/shell/nav-config.tsx` — in `PLATFORM_NAV`'s `Settings` item, add a child between `Notifications` and `Security` (keep the list alphabetical-ish as it stands):

```ts
          { label: "SACCO KYC", href: "/platform/settings/kyc" },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter @sacco/portal exec vitest run "app/platform/(authed)/settings/kyc/__tests__/SaccoKycRequirementsForm.test.tsx"`
Expected: PASS (2 tests).

- [ ] **Step 5: Verify + commit**

Run: `pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: exit 0.

```bash
git add "admin/apps/portal/app/platform/(authed)/settings/kyc/" admin/apps/portal/src/components/shell/nav-config.tsx
git commit -m "feat(portal): platform Settings > SACCO KYC requirements toggles"
```

---

### Task 7: Platform `TenantKycSection` (read-only values + completion + Verify/Unverify)

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantKycSection.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/__tests__/TenantKycSection.test.tsx`

**Interfaces:**
- Consumes: Task 1 `OrganizationKycOut`; Task 2 `resources.kyc.verifyTenant` / `unverifyTenant` + `queryKeys.tenants.kyc(id)`; Task 3 `KycCompletionCard`; `ConfirmDialog`, `Badge`, `Card`, `Button`, `ReadOnlyField`, `FormattedDateTime`, `toast` from `@sacco/ui`.
- Produces: `TenantKycSection({ tenantId, initial, canVerify }: { tenantId: string; initial: OrganizationKycOut; canVerify: boolean })` — mounted by Task 8.

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/app/platform/(authed)/tenants/[id]/__tests__/TenantKycSection.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { OrganizationKycOut } from "@sacco/schemas";

const verifyTenant = vi.fn();
const unverifyTenant = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { kyc: { verifyTenant, unverifyTenant } } }),
}));

import { TenantKycSection } from "../_components/TenantKycSection";

function makeKyc(overrides: Partial<OrganizationKycOut> = {}): OrganizationKycOut {
  return {
    values: {
      legal_name: "Kampala Teachers SACCO",
      registration_number: "REG-001",
      registered_address: null,
      primary_contact_name: null,
      primary_contact_email: null,
      registration_date: null,
      regulator_name: null,
      license_number: null,
      tax_id: null,
      primary_contact_phone: null,
      postal_address: null,
      district_region: null,
      country: null,
    },
    verified: false,
    verified_at: null,
    verified_by_platform_user_id: null,
    completion: {
      items: [
        { key: "legal_name", label: "Registered legal name", required: true, present: true },
        { key: "registration_number", label: "Registration number", required: true, present: true },
      ],
      required_total: 2,
      required_present: 2,
      percent: 100,
      missing_required: [],
      is_complete: true,
    },
    ...overrides,
  };
}

function renderSection(initial: OrganizationKycOut, canVerify = true) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantKycSection tenantId="t1" initial={initial} canVerify={canVerify} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("TenantKycSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("disables Verify while incomplete and explains why", () => {
    const incomplete = makeKyc();
    incomplete.completion = {
      ...incomplete.completion,
      required_present: 1,
      percent: 50,
      missing_required: ["registration_number"],
      is_complete: false,
    };
    renderSection(incomplete);
    expect(screen.getByRole("button", { name: /^verify$/i })).toBeDisabled();
    expect(screen.getByText(/1 required item.* still missing/i)).toBeInTheDocument();
  });

  it("verifies via ConfirmDialog and flips to the verified state", async () => {
    const verified = makeKyc({
      verified: true,
      verified_at: "2026-07-07T08:00:00Z",
      verified_by_platform_user_id: "pu-1",
    });
    verifyTenant.mockResolvedValue({ data: verified, error: undefined });

    renderSection(makeKyc());
    await userEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    // Direct operation — plain ConfirmDialog, no maker-checker copy.
    expect(screen.queryByText(/approval request/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /verify organization kyc/i }));

    await waitFor(() => expect(verifyTenant).toHaveBeenCalledWith("t1"));
    await waitFor(() =>
      expect(screen.getByText(/verified by platform/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /remove verification/i })).toBeInTheDocument();
  });

  it("hides the actions entirely without the write permission", () => {
    renderSection(makeKyc(), false);
    expect(screen.queryByRole("button", { name: /^verify$/i })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter @sacco/portal exec vitest run "app/platform/(authed)/tenants/[id]/__tests__/TenantKycSection.test.tsx"`
Expected: FAIL — cannot resolve `../_components/TenantKycSection`.

- [ ] **Step 3: Write the implementation**

Create `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantKycSection.tsx`:

```tsx
"use client";

import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  FormattedDateTime,
  ReadOnlyField,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import type { OrganizationKycOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { KycCompletionCard } from "@/components/kyc/KycCompletionCard";

/**
 * Read-only SACCO org-KYC oversight card on the platform tenant detail.
 * Verify is a direct admin operation (no maker-checker) and the API returns
 * 409 when the profile is incomplete — the disabled state mirrors that.
 */
export function TenantKycSection({
  tenantId,
  initial,
  canVerify,
}: {
  tenantId: string;
  initial: OrganizationKycOut;
  canVerify: boolean;
}) {
  const { resources } = useAuth();
  const [latest, setLatest] = useState(initial);
  const [confirming, setConfirming] = useState<"verify" | "unverify" | null>(null);

  const mutation = useTypedMutation<OrganizationKycOut, "verify" | "unverify">(
    async (action) => {
      // verifyTenant/unverifyTenant are typed Promise<never> (as-never
      // paths); cast to the real { data, error } shape.
      const call =
        action === "verify"
          ? resources.kyc.verifyTenant(tenantId)
          : resources.kyc.unverifyTenant(tenantId);
      const res = await (call as Promise<{ data?: OrganizationKycOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.tenants.kyc(tenantId)],
      onSuccess: (data, action) => {
        setLatest(data);
        setConfirming(null);
        toast.success(
          action === "verify" ? "Organization KYC verified" : "Verification removed",
        );
      },
      onError: (error) => {
        setConfirming(null);
        toast.error("The verification change failed", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const missingCount = latest.completion.missing_required.length;
  const values = latest.values as Record<string, string | null>;

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4 p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-[var(--text-h5)] font-semibold">Organization KYC</h2>
            {latest.verified ? (
              <Badge variant="success">Verified by platform</Badge>
            ) : (
              <Badge variant="neutral">Not verified</Badge>
            )}
          </div>
          {canVerify ? (
            latest.verified ? (
              <Button variant="ghost" onClick={() => setConfirming("unverify")}>
                Remove verification
              </Button>
            ) : (
              <Button
                onClick={() => setConfirming("verify")}
                disabled={!latest.completion.is_complete}
              >
                Verify
              </Button>
            )
          ) : null}
        </div>
        {latest.verified && latest.verified_at ? (
          <p className="text-[13px] text-[var(--text-secondary)]">
            Verified <FormattedDateTime value={latest.verified_at} />
          </p>
        ) : null}
        {!latest.verified && !latest.completion.is_complete ? (
          <p className="text-[13px] text-[var(--text-secondary)]">
            {missingCount} required item{missingCount === 1 ? " is" : "s are"} still
            missing — verification unlocks when the SACCO completes them.
          </p>
        ) : null}
        <div className="grid grid-cols-2 gap-5">
          {latest.completion.items.map((item) => (
            <ReadOnlyField
              key={item.key}
              label={item.label}
              value={values[item.key] ?? "—"}
            />
          ))}
        </div>
      </Card>

      <KycCompletionCard completion={latest.completion} />

      <ConfirmDialog
        open={confirming === "verify"}
        onOpenChange={(next) => setConfirming(next ? "verify" : null)}
        title="Verify organization KYC?"
        description="This marks the SACCO's self-attested KYC as verified by the platform. Any later change to their KYC values resets it."
        confirmLabel="Verify organization KYC"
        busy={mutation.isPending}
        onConfirm={() => mutation.mutate("verify")}
      />
      <ConfirmDialog
        open={confirming === "unverify"}
        onOpenChange={(next) => setConfirming(next ? "unverify" : null)}
        title="Remove verification?"
        description="The SACCO's organization KYC will show as not verified until verified again."
        confirmLabel="Remove verification"
        destructive
        busy={mutation.isPending}
        onConfirm={() => mutation.mutate("unverify")}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter @sacco/portal exec vitest run "app/platform/(authed)/tenants/[id]/__tests__/TenantKycSection.test.tsx"`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantKycSection.tsx" "admin/apps/portal/app/platform/(authed)/tenants/[id]/__tests__/TenantKycSection.test.tsx"
git commit -m "feat(portal): platform TenantKycSection with verify/unverify"
```

---

### Task 8: Wire the KYC section into the tenant detail page

**Files:**
- Modify: `admin/apps/portal/app/platform/(authed)/tenants/[id]/page.tsx`
- Modify: `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx`

**Interfaces:**
- Consumes: Task 7 `TenantKycSection`; Task 2 `resources.kyc.getTenantKyc`; existing `userHasPermission(user, "platform.tenants.write")`.
- Produces: `TenantDetail` gains an optional `kycSection?: ReactNode` prop rendered between the Provisioning card and the audit bar.

- [ ] **Step 1: Add the prop to `TenantDetail`**

In `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx`:

Add `kycSection` to the destructured props and the prop type:

```tsx
  kycSection,
```
```tsx
  kycSection?: ReactNode;
```

Render it between the Provisioning `</Card>` and `{auditBar}`:

```tsx
      {kycSection}

      {auditBar}
```

- [ ] **Step 2: Fetch KYC in the server page and pass the section**

In `admin/apps/portal/app/platform/(authed)/tenants/[id]/page.tsx`:

Add imports:

```tsx
import type { OrganizationKycOut, TenantOut } from "@sacco/schemas";
import { TenantKycSection } from "./_components/TenantKycSection";
```

(replacing the existing `import type { TenantOut } ...` line), then after the existing tenant fetch + `notFound()` guard, add:

```tsx
  // Org KYC lives in the tenant schema; the read fails while a tenant is
  // still provisioning (schema/table absent) or failed. KYC is informational
  // (spec: no gating), so a failed read hides the section rather than
  // breaking the whole detail page.
  let kyc: OrganizationKycOut | null = null;
  if (data.status === "active") {
    try {
      const res = await (resources.kyc.getTenantKyc(id) as Promise<{
        data?: OrganizationKycOut;
        error?: unknown;
      }>);
      kyc = res.data ?? null;
    } catch {
      kyc = null;
    }
  }
```

and pass the new prop to `<TenantDetail ...>` alongside `auditBar`:

```tsx
      kycSection={
        kyc ? (
          <TenantKycSection
            tenantId={data.id}
            initial={kyc}
            canVerify={userHasPermission(user, "platform.tenants.write")}
          />
        ) : null
      }
```

- [ ] **Step 3: Verify**

Run: `pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint && pnpm --filter @sacco/portal test`
Expected: all exit 0.

- [ ] **Step 4: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/page.tsx" "admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx"
git commit -m "feat(portal): KYC oversight section on platform tenant detail"
```

---

### Task 9: Close-out — full suite, CLAUDE.md KYC contracts, wrap up

**Files:**
- Modify: `CLAUDE.md` (repo root)

- [ ] **Step 1: Run the full admin suite**

Run (from `admin/`): `pnpm lint && pnpm typecheck && pnpm test`
Expected: turbo runs all packages; everything exits 0.

- [ ] **Step 2: Append the KYC contracts to CLAUDE.md**

The spec's "Contract changes" section was deferred when increments 1–2 merged; append it now (increment 3 completes the SACCO-side surface). Add this section to `CLAUDE.md` after the "## Member portal (Phase 4b)" section:

```markdown
## KYC tracking contracts (do not violate)

- **Core KYC tracker:** `app/core/kyc/` is pure (no DB, no I/O) and imports nothing
  from `app/modules` or `app/platform_`. `compute_completion` is the only completion
  computation; do not hand-roll completeness checks anywhere (backend or portal —
  the portal renders server-computed `KycCompletionOut`, never re-derives it).
- **SACCO org KYC:** values live in the tenant-schema `organization_profile`
  singleton, self-attested by the tenant admin via `/organization/kyc`. The
  required set is platform-global (`platform.sacco_kyc_requirements`). The
  `verified` flag is set ONLY by the platform verify/unverify endpoints (via
  `get_session_for_tenant_schema`) and only when completion `is_complete`
  (409 otherwise); any material value change resets it to false.
- **Portal surfaces:** operator `/organization/kyc` page (self-attest + completion),
  platform tenant-detail KYC section (verify/unverify via plain `ConfirmDialog` —
  direct operation, no maker-checker), platform `/platform/settings/kyc`
  requirements toggles. The shared checklist renders through
  `admin/apps/portal/src/components/kyc/KycCompletionCard.tsx`.
- **Gating:** KYC completion is informational only; it must not gate activation,
  transacting, or any request path in v1.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): KYC tracking contracts (core tracker, SACCO org KYC, portals)"
```

- [ ] **Step 4: Manual smoke check (optional but recommended)**

With the local stack running (`docker compose up`), sign in to the operator portal, open **Organization → Organization KYC**, fill two fields, save, and watch the completion percent move. Then in the platform portal open a tenant detail and confirm the KYC section renders with Verify disabled/enabled per completeness, and **Settings → SACCO KYC** toggles save.

---

## Out of scope for this plan (later increments)

- Increment 4: tenant `member_kyc_requirements` config + operator settings page; member-detail completion card; `GET /members/{id}/kyc` (that endpoint does not exist yet — it ships with increment 4's backend).
- Increment 5: member KYC submission/review (`kyc_submissions`, member portal Profile → KYC section, operator review queue).
- AuditBar on the operator Organization KYC page: `OrganizationKycOut` exposes no row id, so `<AuditBar entityType entityId />` cannot be wired; revisit when the audit-log query endpoint (Phase 1.7-F) and an id field exist.
- Platform tenants-list "incomplete KYC" badge / dashboard aggregate (explicitly deferred in the spec).
```
