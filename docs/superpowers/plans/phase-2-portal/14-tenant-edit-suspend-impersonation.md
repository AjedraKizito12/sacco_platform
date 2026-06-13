# Tenant Edit / Suspend / Impersonation Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tenant lifecycle management (edit name, suspend via maker-checker, reactivate) and the cross-context impersonation entry flow (request → enter tenant session → persistent banner → end) to the admin portal, as a pure client of existing `/platform/tenants/*` and `/platform/impersonations/*` endpoints.

**Architecture:** Part A (lifecycle) reuses the SP12/SP13 server-page + form patterns: edit name is a direct `PATCH`; suspend routes through `<MakerCheckerConfirmDialog>` (202 + approval); reactivate is a direct `<ConfirmDialog>` (no maker-checker, per backend contract). Part B (impersonation) is novel: the impersonate screen submits an approval request, and lists the operator's *approved+active* impersonations for the tenant with an "Enter session" action. Entering mints a tenant token server-side via a Next route handler that bridges contexts — it refreshes the platform token, calls `mint-tenant-token`, and sets the tenant httpOnly refresh cookie + slug cookie + an impersonation marker cookie, keeping the tenant refresh token out of client JS (contract C). A full-page navigation to `/` then resolves into the tenant context, where the `(tenant-authed)` layout reads the marker cookie and renders a persistent `<ImpersonationBanner>` whose "End now" hits an end route handler (platform-token DELETE + clear tenant cookies).

**Tech Stack:** Next.js 15 App Router (`apps/portal/app/platform/(authed)/tenants/[id]/*` + `app/api/impersonation/*`), React 19, TS strict, `@sacco/ui` (forms, dialogs, Shell, new `ImpersonationBanner`), `@sacco/schemas` (Zod), `@sacco/api-client` (`resources.tenants.*`, `resources.impersonations.*`), Vitest + Testing Library.

---

## Contract & scope notes (read before starting)

- **Zero new backend endpoints** (contract B). All endpoints exist: `PATCH /platform/tenants/{id}` (name, direct, admin), `POST .../suspend` (202 maker-checker, admin), `POST .../reactivate` (direct, admin, 404/409), `POST /platform/impersonations` (202 + approval, any platform user), `GET /platform/impersonations/active`, `GET /platform/impersonations/{id}`, `POST .../{id}/mint-tenant-token` (impersonator only; 403/409/410/404), `DELETE /platform/impersonations/{id}` (impersonator only, 204). api-client methods exist: `resources.tenants.patch/suspend/reactivate`, `resources.impersonations.request/listActive/get/mintTenantToken/end`. The `Promise<never>` cast wart applies to all of them — cast to `{data?,error?}` with the standard comment at every call site (see SP13).
- **`assign-plan` is OUT of SP14** (deferred to SP15 Billing). The index lists the endpoint but there is no assign-plan screen in §669; assigning a subscription is a billing concern and `POST .../assign-plan` returns a `SubscriptionOut`. SP15 owns it.
- **Permissions** (already in `apps/portal/src/auth/permissions.ts`): `platform.tenants.write` (admin) gates edit/suspend/reactivate; `impersonation.start` (support) gates the impersonate request. Use them; do not invent keys. Gate before fetch on every server page.
- **Backend maker-checker facts (authoritative, do not reimplement):** `POST .../suspend` returns 202 `{status:"pending_approval", approval_request_id}` and submits a `tenant.suspend` approval; it does NOT suspend directly. `reactivate` is direct (operator intent is the authorizing signal — backend contract). `POST /platform/impersonations` returns 202 `{approval_request_id, status}` and submits a `platform.start_impersonation` approval (quorum 1, default); a **second** platform user must approve before the impersonation becomes active/mintable. Self-approval is rejected server-side.
- **Impersonation approval gap (documented):** approving the request needs the platform Approvals inbox UI (SP17, not built). In SP14 the impersonate screen submits the request and surfaces the operator's already-approved+active impersonations (via `GET /active`) with "Enter session". Until SP17, approval happens out of band (a second operator hits `POST /platform/approvals/{id}/approve`). `mint-tenant-token` returns 409 if not yet active — handled with a toast, never crashes.
- **Maker-checker / confirm UX = the established patterns:** suspend + impersonation-request use `<MakerCheckerConfirmDialog>` (locked copy) with the PR #26 feedback (button "Request X", `toast.success`/`toast.error` via `apiErrorMessage`, dialog closes on success only). Reactivate uses the base `<ConfirmDialog>` with `destructive={false}` (it's restorative, not destructive) — direct call, success/error toast.
- **Cross-context cookie rule (contract C):** the tenant refresh token returned by `mint-tenant-token` must be set as an httpOnly cookie **server-side** in a route handler — never stored in client JS. The platform refresh cookie persists alongside the tenant one (different names), so the end route handler can still act in platform context while the operator is in tenant context.
- **Out of scope:** assign-plan (SP15); the `/impersonations/all` admin view + revoke-other (a later ops sub-plan); editing tenant fields beyond name (backend only supports name); e2e (seeded-backend sub-plan); next-intl (portal-wide deferral — raw English strings).

## File Structure

**New files**
- `admin/packages/schemas/src/tenants.ts` — EXTEND with `tenantPatchSchema`, `tenantSuspendSchema`, `impersonationRequestSchema` (+ extend `__tests__/tenants.test.ts`).
- `admin/packages/ui/src/components/Shell/ImpersonationBanner.tsx` (+ `.stories.tsx`, + `.test.tsx`, + export from `Shell/index.ts` / package index) — full-width persistent banner.
- `admin/apps/portal/app/platform/(authed)/tenants/[id]/edit/page.tsx` + `_components/EditTenantForm.tsx`.
- `admin/apps/portal/app/platform/(authed)/tenants/[id]/suspend/page.tsx` + `_components/SuspendTenantForm.tsx`.
- `admin/apps/portal/app/platform/(authed)/tenants/[id]/impersonate/page.tsx` + `_components/ImpersonateTenantPanel.tsx`.
- `admin/apps/portal/app/api/impersonation/activate/route.ts`, `app/api/impersonation/end/route.ts`.
- Tests under `admin/apps/portal/src/__tests__/platform-tenants/`.

**Modified files**
- `admin/apps/portal/src/auth/cookies.ts` — add `IMPERSONATION_COOKIE`, `setImpersonationCookie`, `readImpersonationCookie`, `clearImpersonationCookie`, `clearTenantSlugCookie`.
- `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx` — add Edit / Suspend / Reactivate / Impersonate action buttons (gated).
- `admin/apps/portal/app/(tenant-authed)/layout.tsx` — read the impersonation cookie, render `<ImpersonationBanner>`.

---

# PART A — Tenant lifecycle

## Task 1: Lifecycle + impersonation Zod schemas (`@sacco/schemas`)

**Files:**
- Modify: `admin/packages/schemas/src/tenants.ts`
- Modify: `admin/packages/schemas/src/__tests__/tenants.test.ts`

- [ ] **Step 1: Write the failing test (append to the existing tenants.test.ts)**

```ts
import {
  impersonationRequestSchema,
  tenantPatchSchema,
  tenantSuspendSchema,
} from "../tenants";

describe("tenantPatchSchema", () => {
  it("accepts a non-empty name", () => {
    expect(tenantPatchSchema.safeParse({ name: "Renamed SACCO" }).success).toBe(true);
  });
  it("rejects a whitespace-only name", () => {
    expect(tenantPatchSchema.safeParse({ name: "   " }).success).toBe(false);
  });
  it("rejects a name over 200 chars", () => {
    expect(tenantPatchSchema.safeParse({ name: "a".repeat(201) }).success).toBe(false);
  });
});

describe("tenantSuspendSchema", () => {
  it("accepts a reason of at least 10 chars", () => {
    expect(tenantSuspendSchema.safeParse({ reason: "Non-payment for 90 days" }).success).toBe(true);
  });
  it("rejects a reason under 10 chars", () => {
    expect(tenantSuspendSchema.safeParse({ reason: "too short" }).success).toBe(false);
  });
  it("rejects a reason over 500 chars", () => {
    expect(tenantSuspendSchema.safeParse({ reason: "a".repeat(501) }).success).toBe(false);
  });
});

describe("impersonationRequestSchema", () => {
  it("accepts a reason of at least 10 chars", () => {
    expect(impersonationRequestSchema.safeParse({ reason: "Investigating a posting bug" }).success).toBe(true);
  });
  it("rejects a reason under 10 chars", () => {
    expect(impersonationRequestSchema.safeParse({ reason: "debug" }).success).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/schemas test -- tenants`
Expected: FAIL — the three new schemas aren't exported.

- [ ] **Step 3: Add the schemas to `tenants.ts`**

```ts
// Mirrors TenantPatchIn — only name is editable; slug/schema are immutable.
export const tenantPatchSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
});
export type TenantPatchInput = z.infer<typeof tenantPatchSchema>;

// Mirrors TenantSuspendIn — reason 10..500 chars.
export const tenantSuspendSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(10, "Give a reason of at least 10 characters")
    .max(500, "Reason must be 500 characters or fewer"),
});
export type TenantSuspendInput = z.infer<typeof tenantSuspendSchema>;

// Mirrors ImpersonationStartIn.reason — reason >= 10 chars. tenant_id is
// supplied by the screen, not the form.
export const impersonationRequestSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(10, "Give a reason of at least 10 characters")
    .max(500, "Reason must be 500 characters or fewer"),
});
export type ImpersonationRequestInput = z.infer<typeof impersonationRequestSchema>;
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd admin && pnpm --filter @sacco/schemas test -- tenants` → PASS. `pnpm --filter @sacco/schemas typecheck` → clean.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/schemas/src/tenants.ts admin/packages/schemas/src/__tests__/tenants.test.ts
git commit -m "feat(schemas): tenant patch/suspend + impersonation-request schemas"
```

---

## Task 2: Edit-tenant screen (`/[id]/edit`)

Name-only edit. `PATCH /platform/tenants/{id}` is a **direct** admin call (no maker-checker). Mirror the SP12 CreateUserForm/EditUserForm conventions (RHF + zodResolver, `noValidate`, cast + toast).

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/edit/_components/EditTenantForm.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/edit/page.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-tenants/EditTenantForm.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-tenants/EditTenantForm.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const patch = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { patch } } }),
}));

import { EditTenantForm } from "../../../app/platform/(authed)/tenants/[id]/edit/_components/EditTenantForm";

const tenant: TenantOut = {
  id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha SACCO",
  status: "active", is_active: true, provisioning_state: null,
  failed_step: null, failure_reason: null, provisioning_started_at: null,
  provisioning_completed_at: "2026-06-01T00:00:00Z", seed_version: 1,
  created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
};

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EditTenantForm tenant={tenant} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("EditTenantForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("rejects a blank name", async () => {
    renderForm();
    await userEvent.clear(screen.getByLabelText(/name/i));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/name is required/i)).toBeInTheDocument();
    expect(patch).not.toHaveBeenCalled();
  });

  it("submits the new name and redirects to detail with a toast", async () => {
    patch.mockResolvedValue({ data: { ...tenant, name: "Renamed" }, error: undefined });
    renderForm();
    await userEvent.clear(screen.getByLabelText(/name/i));
    await userEvent.type(screen.getByLabelText(/name/i), "Renamed");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith("t1", { name: "Renamed" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/platform/tenants/t1"));
    expect(await screen.findByText(/changes saved/i)).toBeInTheDocument();
  });

  it("surfaces an error and does not redirect", async () => {
    patch.mockResolvedValue({ data: undefined, error: { detail: "Tenant not found" } });
    renderForm();
    await userEvent.clear(screen.getByLabelText(/name/i));
    await userEvent.type(screen.getByLabelText(/name/i), "Renamed");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/tenant not found/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- EditTenantForm` → FAIL (module not found).

- [ ] **Step 3: Write the form**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/edit/_components/EditTenantForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button, FormField, Input, toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  tenantPatchSchema,
  type TenantOut,
  type TenantPatchInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function EditTenantForm({ tenant }: { tenant: TenantOut }) {
  const router = useRouter();
  const { resources } = useAuth();
  const form = useForm<TenantPatchInput>({
    resolver: zodResolver(tenantPatchSchema),
    defaultValues: { name: tenant.name },
  });

  const mutation = useTypedMutation<unknown, TenantPatchInput>(
    async (vars) => {
      // resources.tenants.patch is typed Promise<never> (as-never paths in
      // tenants.ts); cast to the real { data, error } shape.
      const res = await (
        resources.tenants.patch(tenant.id, vars) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [
        queryKeys.tenants.root(),
        queryKeys.tenants.detail(tenant.id),
      ],
      onSuccess: () => {
        toast.success("Changes saved");
        router.push(`/platform/tenants/${tenant.id}`);
      },
      onError: (error) => {
        toast.error("The tenant was not updated", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <form
      noValidate
      className="flex max-w-xl flex-col gap-5"
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
    >
      <FormField
        control={form.control}
        name="name"
        label="Name"
        required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )}
      />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Save</Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => router.push(`/platform/tenants/${tenant.id}`)}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
```

> `resources.tenants.patch(id, { name })` signature confirmed in `packages/api-client/src/resources/tenants.ts`.

- [ ] **Step 4: Write the page**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/edit/page.tsx
import { notFound } from "next/navigation";
import type { TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { EditTenantForm } from "./_components/EditTenantForm";

export const metadata = { title: "Edit Tenant" };

export default async function EditTenantPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.write");

  // resources.tenants.get is typed Promise<never>; cast to { data, error }.
  const { data } = await (
    resources.tenants.get(id) as Promise<{ data?: TenantOut; error?: unknown }>
  );
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Edit tenant</h1>
      <EditTenantForm tenant={data} />
    </div>
  );
}
```

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- EditTenantForm` → PASS (3). `typecheck` + `lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/edit" admin/apps/portal/src/__tests__/platform-tenants/EditTenantForm.test.tsx
git commit -m "feat(portal): edit-tenant screen (direct name update)"
```

---

## Task 3: Suspend-tenant screen (`/[id]/suspend`) — maker-checker

Reason form (≥10 chars) → `<MakerCheckerConfirmDialog>` → `POST .../suspend` (202 + approval). PR #26 feedback pattern.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/suspend/_components/SuspendTenantForm.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/suspend/page.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-tenants/SuspendTenantForm.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-tenants/SuspendTenantForm.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const suspend = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { suspend } } }),
}));

import { SuspendTenantForm } from "../../../app/platform/(authed)/tenants/[id]/suspend/_components/SuspendTenantForm";

const tenant: TenantOut = {
  id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha SACCO",
  status: "active", is_active: true, provisioning_state: null,
  failed_step: null, failure_reason: null, provisioning_started_at: null,
  provisioning_completed_at: "2026-06-01T00:00:00Z", seed_version: 1,
  created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
};

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SuspendTenantForm tenant={tenant} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("SuspendTenantForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("rejects a reason under 10 characters", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText(/reason/i), "too short");
    await userEvent.click(screen.getByRole("button", { name: /request suspension/i }));
    expect(await screen.findByText(/at least 10 characters/i)).toBeInTheDocument();
    expect(suspend).not.toHaveBeenCalled();
  });

  it("opens the locked maker-checker dialog and submits on confirm", async () => {
    suspend.mockResolvedValue({
      data: { status: "pending_approval", approval_request_id: "ar1" },
      error: undefined,
    });
    renderForm();
    await userEvent.type(screen.getByLabelText(/reason/i), "Non-payment for 90 days");
    await userEvent.click(screen.getByRole("button", { name: /request suspension/i }));
    expect(await screen.findByText(/create an approval request, not execute/i)).toBeInTheDocument();
    expect(suspend).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /create approval request/i }));
    await waitFor(() =>
      expect(suspend).toHaveBeenCalledWith("t1", { reason: "Non-payment for 90 days" }),
    );
    expect(await screen.findByText(/approval request created/i)).toBeInTheDocument();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/platform/tenants/t1"));
  });

  it("keeps the dialog open and surfaces an error on failure", async () => {
    suspend.mockResolvedValue({
      data: undefined,
      error: { detail: "Tenant is already suspended" },
    });
    renderForm();
    await userEvent.type(screen.getByLabelText(/reason/i), "Non-payment for 90 days");
    await userEvent.click(screen.getByRole("button", { name: /request suspension/i }));
    await userEvent.click(
      await screen.findByRole("button", { name: /create approval request/i }),
    );
    expect(await screen.findByText(/already suspended/i)).toBeInTheDocument();
    expect(screen.getByText(/create an approval request, not execute/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- SuspendTenantForm` → FAIL.

- [ ] **Step 3: Write the form**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/suspend/_components/SuspendTenantForm.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  FormField,
  MakerCheckerConfirmDialog,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  tenantSuspendSchema,
  type TenantOut,
  type TenantSuspendInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function SuspendTenantForm({ tenant }: { tenant: TenantOut }) {
  const router = useRouter();
  const { resources } = useAuth();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, setPending] = useState<TenantSuspendInput | null>(null);

  const form = useForm<TenantSuspendInput>({
    resolver: zodResolver(tenantSuspendSchema),
    defaultValues: { reason: "" },
  });

  const mutation = useTypedMutation<unknown, TenantSuspendInput>(
    async (vars) => {
      // resources.tenants.suspend is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.tenants.suspend(tenant.id, vars) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.tenants.root(), queryKeys.tenants.detail(tenant.id)],
      onSuccess: () => {
        toast.success("Approval request created", {
          description: "The tenant will be suspended once another platform user approves it.",
        });
        setConfirmOpen(false);
        setPending(null);
        router.push(`/platform/tenants/${tenant.id}`);
      },
      onError: (error) => {
        toast.error("The suspension was not requested", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <form
        noValidate
        className="flex max-w-xl flex-col gap-5"
        onSubmit={form.handleSubmit((values) => {
          setPending(values);
          setConfirmOpen(true);
        })}
      >
        <FormField
          control={form.control}
          name="reason"
          label="Reason"
          required
          helpText="Recorded on the approval request and the audit log. Minimum 10 characters."
          render={({ field, id, describedBy, invalid }) => (
            <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
          )}
        />
        <div className="flex gap-3">
          <Button type="submit" variant="destructive" disabled={mutation.isPending}>
            Request Suspension
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => router.push(`/platform/tenants/${tenant.id}`)}
          >
            Cancel
          </Button>
        </div>
      </form>

      <MakerCheckerConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        operationLabel="tenant suspension"
        subjectLabel={tenant.name}
        busy={mutation.isPending}
        onConfirm={() => {
          if (pending) mutation.mutate(pending);
        }}
      />
    </>
  );
}
```

> Verify `Textarea` is exported from `@sacco/ui` (`grep -n "Textarea" packages/ui/src/index.ts`). If it is NOT, use `<Input>` as a single-line fallback OR check for a `<TextArea>` casing variant — match what exists; do not add a new component. Report which you used.

- [ ] **Step 4: Write the page**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/suspend/page.tsx
import { notFound, redirect } from "next/navigation";
import { Card } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { SuspendTenantForm } from "./_components/SuspendTenantForm";

export const metadata = { title: "Suspend Tenant" };

export default async function SuspendTenantPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.write");

  const { data } = await (
    resources.tenants.get(id) as Promise<{ data?: TenantOut; error?: unknown }>
  );
  if (!data) notFound();
  // Already-suspended tenants have nothing to suspend — send back to detail.
  if (data.status === "suspended") redirect(`/platform/tenants/${id}`);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Suspend {data.name}</h1>
      <Card className="p-6">
        <p className="mb-4 text-[var(--text-secondary)]">
          Suspending blocks all tenant access (402/403 on tenant requests). This
          creates an approval request — another platform user must approve before
          the tenant is suspended.
        </p>
        <SuspendTenantForm tenant={data} />
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- SuspendTenantForm` → PASS (3). `typecheck` + `lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/suspend" admin/apps/portal/src/__tests__/platform-tenants/SuspendTenantForm.test.tsx
git commit -m "feat(portal): suspend-tenant screen with maker-checker"
```

---

## Task 4: Reactivate action + lifecycle buttons on TenantDetail

Reactivate is **direct** (no maker-checker — backend contract). It uses the base `<ConfirmDialog>` (not destructive — it restores access). This task also wires the Edit / Suspend / Impersonate entry buttons onto the detail header, gated by status + permission.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantActions.tsx`
- Modify: `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-tenants/TenantActions.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-tenants/TenantActions.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const reactivate = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { reactivate } } }),
}));

import { TenantActions } from "../../../app/platform/(authed)/tenants/[id]/_components/TenantActions";

function tenant(over: Partial<TenantOut>): TenantOut {
  return {
    id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha SACCO",
    status: "active", is_active: true, provisioning_state: null,
    failed_step: null, failure_reason: null, provisioning_started_at: null,
    provisioning_completed_at: "2026-06-01T00:00:00Z", seed_version: 1,
    created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

function renderActions(t: TenantOut, caps: { canWrite?: boolean; canImpersonate?: boolean } = {}) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantActions tenant={t} canWrite={caps.canWrite ?? true} canImpersonate={caps.canImpersonate ?? true} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("TenantActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("shows Edit + Suspend + Impersonate for an active tenant with full perms", () => {
    renderActions(tenant({ status: "active" }));
    expect(screen.getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/platform/tenants/t1/edit");
    expect(screen.getByRole("link", { name: /suspend/i })).toHaveAttribute("href", "/platform/tenants/t1/suspend");
    expect(screen.getByRole("link", { name: /impersonate/i })).toHaveAttribute("href", "/platform/tenants/t1/impersonate");
    expect(screen.queryByRole("button", { name: /reactivate/i })).toBeNull();
  });

  it("shows Reactivate (not Suspend) for a suspended tenant", () => {
    renderActions(tenant({ status: "suspended" }));
    expect(screen.getByRole("button", { name: /reactivate/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /suspend/i })).toBeNull();
  });

  it("hides write actions without write permission but keeps impersonate", () => {
    renderActions(tenant({ status: "active" }), { canWrite: false, canImpersonate: true });
    expect(screen.queryByRole("link", { name: /edit/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /suspend/i })).toBeNull();
    expect(screen.getByRole("link", { name: /impersonate/i })).toBeInTheDocument();
  });

  it("reactivates via confirm dialog and toasts", async () => {
    reactivate.mockResolvedValue({ data: tenant({ status: "active" }), error: undefined });
    renderActions(tenant({ status: "suspended" }));
    await userEvent.click(screen.getByRole("button", { name: /reactivate/i }));
    await userEvent.click(screen.getByRole("button", { name: /^reactivate$/i }).closest("[role=dialog]") ? screen.getByRole("button", { name: /confirm|reactivate tenant/i }) : screen.getByRole("button", { name: /reactivate tenant/i }));
    await waitFor(() => expect(reactivate).toHaveBeenCalledWith("t1"));
    expect(await screen.findByText(/tenant reactivated/i)).toBeInTheDocument();
  });
});
```

> NOTE: the reactivate-confirm test's button lookup is fiddly because the trigger and the dialog confirm both say "Reactivate". Implement the dialog confirm label as **"Reactivate tenant"** (distinct from the trigger "Reactivate") so the test can target `getByRole("button", { name: /reactivate tenant/i })`. Simplify the test's final click to: open dialog via the trigger, then `await userEvent.click(screen.getByRole("button", { name: /reactivate tenant/i }))`. Adjust the test to that cleaner form when you write it.

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- TenantActions` → FAIL.

- [ ] **Step 3: Write `TenantActions.tsx`**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantActions.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button, ConfirmDialog, toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import type { TenantOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function TenantActions({
  tenant,
  canWrite,
  canImpersonate,
}: {
  tenant: TenantOut;
  canWrite: boolean;
  canImpersonate: boolean;
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [reactivateOpen, setReactivateOpen] = useState(false);

  const reactivation = useTypedMutation<unknown, void>(
    async () => {
      // resources.tenants.reactivate is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.tenants.reactivate(tenant.id) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.tenants.root(), queryKeys.tenants.detail(tenant.id)],
      onSuccess: () => {
        toast.success("Tenant reactivated");
        setReactivateOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The tenant was not reactivated", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const isSuspended = tenant.status === "suspended";

  return (
    <div className="flex items-center gap-2">
      {canImpersonate ? (
        <Button asChild variant="secondary">
          <Link href={`/platform/tenants/${tenant.id}/impersonate`}>Impersonate</Link>
        </Button>
      ) : null}
      {canWrite && !isSuspended ? (
        <Button asChild variant="secondary">
          <Link href={`/platform/tenants/${tenant.id}/edit`}>Edit</Link>
        </Button>
      ) : null}
      {canWrite && !isSuspended ? (
        <Button asChild variant="destructive">
          <Link href={`/platform/tenants/${tenant.id}/suspend`}>Suspend</Link>
        </Button>
      ) : null}
      {canWrite && isSuspended ? (
        <Button variant="primary" onClick={() => setReactivateOpen(true)}>
          Reactivate
        </Button>
      ) : null}

      <ConfirmDialog
        open={reactivateOpen}
        onOpenChange={setReactivateOpen}
        title={`Reactivate ${tenant.name}?`}
        description="This restores tenant access immediately. No approval is required."
        confirmLabel="Reactivate tenant"
        busy={reactivation.isPending}
        onConfirm={() => reactivation.mutate()}
      />
    </div>
  );
}
```

> `ConfirmDialog` props (`open`, `onOpenChange`, `title`, `description`, `confirmLabel`, `busy`, `onConfirm`) confirmed in `packages/ui/src/components/ConfirmDialog/ConfirmDialog.tsx`. `Button variant="destructive"` used for Suspend (an `asChild` Link); confirm `asChild` + `destructive` compose (SP12 used both). `router.refresh()` re-runs the server component so the detail reflects the new status.

- [ ] **Step 4: Wire into TenantDetail**

In `TenantDetail.tsx`, replace the existing header-right slot (currently just the failed-only `RetryProvisioningButton`) so both actions coexist. Find the header `<div className="flex items-center justify-between">` block and update its right side to:

```tsx
        <div className="flex items-center gap-2">
          {canRetry && t.status === "failed" ? (
            <RetryProvisioningButton tenant={t} />
          ) : null}
          <TenantActions
            tenant={t}
            canWrite={canRetry}
            canImpersonate={canImpersonate}
          />
        </div>
```

`TenantDetail` currently receives `{ tenant, canRetry }`. Add `canImpersonate: boolean` to its props and thread it from the page. Import `TenantActions`. (`canRetry` is already `platform.tenants.write` — reuse it as `canWrite` for TenantActions; they're the same tier.) Update `[id]/page.tsx` to pass `canImpersonate={userHasPermission(user, "impersonation.start")}`:

```tsx
  return (
    <TenantDetail
      tenant={data}
      canRetry={userHasPermission(user, "platform.tenants.write")}
      canImpersonate={userHasPermission(user, "impersonation.start")}
    />
  );
```

Update the existing `TenantDetail.test.tsx` `renderDetail` helper to pass `canImpersonate` (default false) so existing tests still compile, and add one assertion that an active tenant with `canWrite` shows the Edit link.

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- "TenantActions|TenantDetail"` → PASS. `typecheck` + `lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantActions.tsx" "admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx" "admin/apps/portal/app/platform/(authed)/tenants/[id]/page.tsx" admin/apps/portal/src/__tests__/platform-tenants/TenantActions.test.tsx admin/apps/portal/src/__tests__/platform-tenants/TenantDetail.test.tsx
git commit -m "feat(portal): tenant lifecycle actions (reactivate + edit/suspend/impersonate entry)"
```

---

# PART B — Impersonation cross-context flow

## Task 5: `<ImpersonationBanner>` component (`@sacco/ui` Shell)

Full-width, persistent banner for the tenant context: "Impersonating <Tenant> · ends <time> · End now". `TenantIndicator` already shows a small "Impersonating" chip; this is the prominent top banner with the expiry and the end action.

**Files:**
- Create: `admin/packages/ui/src/components/Shell/ImpersonationBanner.tsx`
- Create: `admin/packages/ui/src/components/Shell/ImpersonationBanner.stories.tsx`
- Create: `admin/packages/ui/src/components/Shell/ImpersonationBanner.test.tsx`
- Modify: `admin/packages/ui/src/components/Shell/index.ts` (export) — confirm Shell has an index barrel; if exports flow through `packages/ui/src/index.ts` directly, add it there instead (match how `TenantIndicator` is exported).

- [ ] **Step 1: Write the failing test**

```tsx
// admin/packages/ui/src/components/Shell/ImpersonationBanner.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ImpersonationBanner } from "./ImpersonationBanner";

describe("ImpersonationBanner", () => {
  it("names the tenant and renders an End now action", () => {
    render(
      <ImpersonationBanner
        tenantName="Alpha SACCO"
        expiresAt="2026-06-13T12:30:00Z"
        onEnd={() => {}}
      />,
    );
    expect(screen.getByText(/impersonating/i)).toBeInTheDocument();
    expect(screen.getByText(/alpha sacco/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /end now/i })).toBeInTheDocument();
  });

  it("calls onEnd when End now is clicked", async () => {
    const onEnd = vi.fn();
    render(
      <ImpersonationBanner tenantName="Alpha SACCO" expiresAt="2026-06-13T12:30:00Z" onEnd={onEnd} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /end now/i }));
    expect(onEnd).toHaveBeenCalledOnce();
  });

  it("disables End now while busy", () => {
    render(
      <ImpersonationBanner tenantName="Alpha SACCO" expiresAt="2026-06-13T12:30:00Z" onEnd={() => {}} busy />,
    );
    expect(screen.getByRole("button", { name: /end now/i })).toBeDisabled();
  });

  it("exposes the banner as a status region for assistive tech", () => {
    render(
      <ImpersonationBanner tenantName="Alpha SACCO" expiresAt="2026-06-13T12:30:00Z" onEnd={() => {}} />,
    );
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/ui test -- ImpersonationBanner` → FAIL.

- [ ] **Step 3: Write the component**

```tsx
// admin/packages/ui/src/components/Shell/ImpersonationBanner.tsx
"use client";

import { Button } from "../Button";
import { FormattedDateTime } from "../FormattedDate";

export interface ImpersonationBannerProps {
  tenantName: string;
  /** ISO timestamp when the impersonation session auto-expires. */
  expiresAt: string;
  onEnd(): void;
  busy?: boolean;
}

/**
 * Persistent, high-visibility banner shown at the top of the tenant shell
 * while a platform operator is impersonating a tenant. The session also
 * expires server-side at `expiresAt`; "End now" terminates it early.
 */
export function ImpersonationBanner({
  tenantName,
  expiresAt,
  onEnd,
  busy = false,
}: ImpersonationBannerProps) {
  return (
    <div
      role="status"
      className="flex items-center justify-between gap-4 bg-[var(--surface-warning)] px-6 py-2 text-[13px] text-[var(--text-warning-strong)]"
    >
      <span>
        <strong className="font-semibold">Impersonating {tenantName}</strong>
        {" · ends "}
        <FormattedDateTime value={expiresAt} />
      </span>
      <Button variant="secondary" size="small" onClick={onEnd} disabled={busy}>
        End now
      </Button>
    </div>
  );
}
```

> Verify these tokens exist in `docs/tokens.css`: `--surface-warning`, `--text-warning-strong`. If the exact names differ (e.g. `--surface-warning-subtle`, `--text-warning`), use the closest existing warning tokens — grep `tokens.css` for `warning`. Verify `Button` accepts `size="small"` (the design-system button heights are 40/32/48 — `size="small"` = 32px; confirm the prop name/values in `Button.tsx`). Verify `FormattedDateTime` import path from the Shell folder (`../FormattedDate`).

- [ ] **Step 4: Story + export**

```tsx
// admin/packages/ui/src/components/Shell/ImpersonationBanner.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { ImpersonationBanner } from "./ImpersonationBanner";

const meta: Meta<typeof ImpersonationBanner> = {
  title: "Shell/ImpersonationBanner",
  component: ImpersonationBanner,
  args: {
    tenantName: "Kampala Teachers SACCO",
    expiresAt: "2026-06-13T12:30:00Z",
    onEnd: () => {},
  },
};
export default meta;
type Story = StoryObj<typeof ImpersonationBanner>;

export const Default: Story = {};
export const Busy: Story = { args: { busy: true } };
```

Export `ImpersonationBanner` the same way `TenantIndicator` is exported (find `TenantIndicator` in `packages/ui/src/index.ts` or `Shell/index.ts` and add `ImpersonationBanner` alongside it).

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/ui test -- ImpersonationBanner` → PASS (4). `pnpm --filter @sacco/ui typecheck` → clean.

- [ ] **Step 6: Commit**

```bash
git add admin/packages/ui/src/components/Shell/ImpersonationBanner.tsx admin/packages/ui/src/components/Shell/ImpersonationBanner.stories.tsx admin/packages/ui/src/components/Shell/ImpersonationBanner.test.tsx admin/packages/ui/src/index.ts admin/packages/ui/src/components/Shell/index.ts
git commit -m "feat(ui): ImpersonationBanner Shell component"
```

---

## Task 6: Impersonation cookie helpers

**Files:**
- Modify: `admin/apps/portal/src/auth/cookies.ts`
- Create: `admin/apps/portal/src/auth/__tests__/cookies-impersonation.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// admin/apps/portal/src/auth/__tests__/cookies-impersonation.test.ts
import { describe, expect, it, vi } from "vitest";

const store = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    set: (name: string, value: string) => store.set(name, value),
    get: (name: string) => (store.has(name) ? { value: store.get(name) } : undefined),
    delete: (name: string) => store.delete(name),
  })),
}));

import {
  IMPERSONATION_COOKIE,
  clearImpersonationCookie,
  readImpersonationCookie,
  setImpersonationCookie,
} from "../cookies";

describe("impersonation cookie helpers", () => {
  it("round-trips the impersonation marker", async () => {
    await setImpersonationCookie({
      id: "imp1",
      tenantName: "Alpha SACCO",
      expiresAt: "2026-06-13T12:30:00Z",
      tenantId: "t1",
    });
    const read = await readImpersonationCookie();
    expect(read).toEqual({
      id: "imp1",
      tenantName: "Alpha SACCO",
      expiresAt: "2026-06-13T12:30:00Z",
      tenantId: "t1",
    });
    expect(store.get(IMPERSONATION_COOKIE)).toBeTruthy();
  });

  it("returns null when absent", async () => {
    store.delete(IMPERSONATION_COOKIE);
    expect(await readImpersonationCookie()).toBeNull();
  });

  it("returns null on malformed JSON", async () => {
    store.set(IMPERSONATION_COOKIE, "not-json");
    expect(await readImpersonationCookie()).toBeNull();
  });

  it("clears the cookie", async () => {
    await setImpersonationCookie({ id: "imp1", tenantName: "A", expiresAt: "x", tenantId: "t1" });
    await clearImpersonationCookie();
    expect(store.has(IMPERSONATION_COOKIE)).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- cookies-impersonation` → FAIL.

- [ ] **Step 3: Add the helpers to `cookies.ts`**

Read the existing `cookies.ts` first (it exports `setRefreshCookie`, `clearRefreshCookie`, `setTenantSlugCookie`, and the cookie-name/max-age consts). Append:

```ts
export const IMPERSONATION_COOKIE = "sacco_impersonation";

export interface ImpersonationMarker {
  id: string;
  tenantId: string;
  tenantName: string;
  expiresAt: string;
}

export async function setImpersonationCookie(
  marker: ImpersonationMarker,
): Promise<void> {
  const jar = await cookies();
  jar.set(IMPERSONATION_COOKIE, JSON.stringify(marker), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: TENANT_REFRESH_MAX_AGE,
  });
}

export async function readImpersonationCookie(): Promise<ImpersonationMarker | null> {
  const jar = await cookies();
  const raw = jar.get(IMPERSONATION_COOKIE)?.value;
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ImpersonationMarker;
  } catch {
    return null;
  }
}

export async function clearImpersonationCookie(): Promise<void> {
  const jar = await cookies();
  jar.delete(IMPERSONATION_COOKIE);
}

export async function clearTenantSlugCookie(): Promise<void> {
  const jar = await cookies();
  jar.delete(TENANT_SLUG_COOKIE);
}
```

> Match the exact cookie-attribute style the existing `setRefreshCookie` uses (it already encodes the httpOnly/secure/sameSite/path pattern — copy its options object shape so attributes stay consistent). Confirm `cookies()` is imported at the top of the file (it is — `setTenantSlugCookie` uses it). If `clearTenantSlugCookie` already exists, don't duplicate it.

- [ ] **Step 4: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- cookies-impersonation` → PASS (4). `typecheck` + `lint` → clean.

- [ ] **Step 5: Commit**

```bash
git add admin/apps/portal/src/auth/cookies.ts admin/apps/portal/src/auth/__tests__/cookies-impersonation.test.ts
git commit -m "feat(portal): impersonation marker cookie helpers"
```

---

## Task 7: Activate + End impersonation route handlers

Server-side route handlers that bridge platform→tenant context. **Activate**: refresh platform token → `mint-tenant-token` → set tenant refresh cookie + slug cookie + impersonation marker → return access token. **End**: refresh platform token → `DELETE /platform/impersonations/{id}` → clear tenant + impersonation cookies.

**Files:**
- Create: `admin/apps/portal/app/api/impersonation/activate/route.ts`
- Create: `admin/apps/portal/app/api/impersonation/end/route.ts`
- Create: `admin/apps/portal/src/__tests__/impersonation-routes.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// admin/apps/portal/src/__tests__/impersonation-routes.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getServerAccessToken = vi.fn();
vi.mock("@/auth/server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
}));

const setRefreshCookie = vi.fn();
const setTenantSlugCookie = vi.fn();
const setImpersonationCookie = vi.fn();
const clearRefreshCookie = vi.fn();
const clearTenantSlugCookie = vi.fn();
const clearImpersonationCookie = vi.fn();
vi.mock("@/auth/cookies", () => ({
  TENANT_REFRESH_COOKIE: "sacco_refresh_tenant",
  TENANT_REFRESH_MAX_AGE: 28800,
  setRefreshCookie: (...a: unknown[]) => setRefreshCookie(...a),
  setTenantSlugCookie: (...a: unknown[]) => setTenantSlugCookie(...a),
  setImpersonationCookie: (...a: unknown[]) => setImpersonationCookie(...a),
  clearRefreshCookie: (...a: unknown[]) => clearRefreshCookie(...a),
  clearTenantSlugCookie: (...a: unknown[]) => clearTenantSlugCookie(...a),
  clearImpersonationCookie: (...a: unknown[]) => clearImpersonationCookie(...a),
}));

const fetchMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function req(body: unknown): Request {
  return new Request("http://localhost/api/impersonation/activate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

describe("POST /api/impersonation/activate", () => {
  it("401s when there is no platform session", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    const { POST } = await import("../../app/api/impersonation/activate/route");
    const res = await POST(req({ impersonation_id: "imp1", tenant_id: "t1", tenant_name: "Alpha" }));
    expect(res.status).toBe(401);
    expect(setRefreshCookie).not.toHaveBeenCalled();
  });

  it("mints, sets tenant cookies, and returns the access token", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "plat-access" });
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: "tenant-access",
        refresh_token: "tenant-refresh",
        expires_in: 900,
        tenant_slug: "alpha",
        impersonation_id: "imp1",
        impersonation_expires_at: "2026-06-13T12:30:00Z",
      }),
    });
    const { POST } = await import("../../app/api/impersonation/activate/route");
    const res = await POST(req({ impersonation_id: "imp1", tenant_id: "t1", tenant_name: "Alpha SACCO" }));
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ access_token: "tenant-access", tenant_slug: "alpha" });
    // platform bearer used to mint
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain("/platform/impersonations/imp1/mint-tenant-token");
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer plat-access");
    // tenant cookies set
    expect(setRefreshCookie).toHaveBeenCalledWith(
      expect.objectContaining({ name: "sacco_refresh_tenant", value: "tenant-refresh" }),
    );
    expect(setTenantSlugCookie).toHaveBeenCalledWith("alpha");
    expect(setImpersonationCookie).toHaveBeenCalledWith(
      expect.objectContaining({ id: "imp1", tenantId: "t1", tenantName: "Alpha SACCO", expiresAt: "2026-06-13T12:30:00Z" }),
    );
  });

  it("propagates the mint error status (e.g. 409 not yet approved)", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "plat-access" });
    fetchMock.mockResolvedValue({
      ok: false, status: 409, json: async () => ({ detail: "not yet active" }),
    });
    const { POST } = await import("../../app/api/impersonation/activate/route");
    const res = await POST(req({ impersonation_id: "imp1", tenant_id: "t1", tenant_name: "Alpha" }));
    expect(res.status).toBe(409);
    expect(setRefreshCookie).not.toHaveBeenCalled();
  });
});

describe("POST /api/impersonation/end", () => {
  it("ends the impersonation and clears tenant cookies", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "plat-access" });
    fetchMock.mockResolvedValue({ ok: true, status: 204, json: async () => ({}) });
    const { POST } = await import("../../app/api/impersonation/end/route");
    const res = await POST(
      new Request("http://localhost/api/impersonation/end", {
        method: "POST",
        body: JSON.stringify({ impersonation_id: "imp1" }),
      }),
    );
    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain("/platform/impersonations/imp1");
    expect(init.method).toBe("DELETE");
    expect(clearRefreshCookie).toHaveBeenCalled();
    expect(clearTenantSlugCookie).toHaveBeenCalled();
    expect(clearImpersonationCookie).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- impersonation-routes` → FAIL (modules not found).

- [ ] **Step 3: Write the activate route**

```ts
// admin/apps/portal/app/api/impersonation/activate/route.ts
import { NextResponse } from "next/server";
import { getServerAccessToken } from "@/auth/server-helpers";
import {
  TENANT_REFRESH_COOKIE,
  TENANT_REFRESH_MAX_AGE,
  setImpersonationCookie,
  setRefreshCookie,
  setTenantSlugCookie,
} from "@/auth/cookies";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

interface ActivateBody {
  impersonation_id: string;
  tenant_id: string;
  tenant_name: string;
}

export async function POST(request: Request): Promise<NextResponse> {
  const body = (await request.json()) as Partial<ActivateBody>;
  if (!body.impersonation_id || !body.tenant_id || !body.tenant_name) {
    return NextResponse.json({ error: "Missing fields" }, { status: 400 });
  }

  const { accessToken } = await getServerAccessToken("platform");
  if (!accessToken) {
    return NextResponse.json({ error: "No platform session" }, { status: 401 });
  }

  const r = await fetch(
    `${API_BASE}/platform/impersonations/${body.impersonation_id}/mint-tenant-token`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
    },
  );
  if (!r.ok) {
    const detail = await safeJson(r);
    return NextResponse.json(detail ?? { error: "Mint failed" }, { status: r.status });
  }
  const data = (await r.json()) as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
    tenant_slug: string;
    impersonation_id: string;
    impersonation_expires_at: string;
  };

  // Set the tenant refresh token httpOnly server-side (never in client JS).
  await setRefreshCookie({
    name: TENANT_REFRESH_COOKIE,
    value: data.refresh_token,
    maxAgeSeconds: TENANT_REFRESH_MAX_AGE,
  });
  await setTenantSlugCookie(data.tenant_slug);
  await setImpersonationCookie({
    id: data.impersonation_id,
    tenantId: body.tenant_id,
    tenantName: body.tenant_name,
    expiresAt: data.impersonation_expires_at,
  });

  return NextResponse.json({
    access_token: data.access_token,
    expires_in: data.expires_in,
    tenant_slug: data.tenant_slug,
  });
}

async function safeJson(r: Response): Promise<unknown> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}
```

- [ ] **Step 4: Write the end route**

```ts
// admin/apps/portal/app/api/impersonation/end/route.ts
import { NextResponse } from "next/server";
import { getServerAccessToken } from "@/auth/server-helpers";
import {
  TENANT_REFRESH_COOKIE,
  clearImpersonationCookie,
  clearRefreshCookie,
  clearTenantSlugCookie,
} from "@/auth/cookies";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

export async function POST(request: Request): Promise<NextResponse> {
  const body = (await request.json()) as { impersonation_id?: string };
  if (!body.impersonation_id) {
    return NextResponse.json({ error: "Missing impersonation_id" }, { status: 400 });
  }

  const { accessToken } = await getServerAccessToken("platform");
  if (!accessToken) {
    return NextResponse.json({ error: "No platform session" }, { status: 401 });
  }

  // End the impersonation in platform context. Treat 404/410 (already
  // ended/expired) as success — the goal is to leave the tenant session.
  const r = await fetch(
    `${API_BASE}/platform/impersonations/${body.impersonation_id}`,
    {
      method: "DELETE",
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
    },
  );
  const ok = r.ok || r.status === 404 || r.status === 410;

  // Always clear the local tenant + impersonation cookies so the operator
  // returns to platform context regardless of the backend's terminal state.
  await clearRefreshCookie(TENANT_REFRESH_COOKIE);
  await clearTenantSlugCookie();
  await clearImpersonationCookie();

  if (!ok) {
    return NextResponse.json({ error: "End failed" }, { status: r.status });
  }
  return NextResponse.json({ ok: true });
}
```

> Confirm `clearRefreshCookie`'s signature: in `cookies.ts` it is `clearRefreshCookie(name)`. If it takes a different arg shape, adapt the call. Confirm `getServerAccessToken` is exported from `@/auth/server-helpers` (it is). The activate route does NOT need a slug header for the platform refresh (platform refresh has no tenant).

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- impersonation-routes` → PASS (5). `typecheck` + `lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add admin/apps/portal/app/api/impersonation admin/apps/portal/src/__tests__/impersonation-routes.test.ts
git commit -m "feat(portal): impersonation activate + end route handlers (context bridge)"
```

---

## Task 8: Impersonate screen (`/[id]/impersonate`)

Submit an impersonation request (maker-checker) AND list the operator's active+approved impersonations for this tenant with "Enter session" (→ activate route → full-page navigate to tenant context).

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/impersonate/_components/ImpersonateTenantPanel.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/impersonate/page.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-tenants/ImpersonateTenantPanel.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-tenants/ImpersonateTenantPanel.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const requestImp = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { impersonations: { request: requestImp } } }),
}));

const assign = vi.fn();
vi.stubGlobal("location", { assign: assign } as unknown as Location);
const fetchMock = vi.fn();

import { ImpersonateTenantPanel } from "../../../app/platform/(authed)/tenants/[id]/impersonate/_components/ImpersonateTenantPanel";

const tenant: TenantOut = {
  id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha SACCO",
  status: "active", is_active: true, provisioning_state: null,
  failed_step: null, failure_reason: null, provisioning_started_at: null,
  provisioning_completed_at: "2026-06-01T00:00:00Z", seed_version: 1,
  created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
};

function renderPanel(active: Array<{ id: string; expires_at: string }> = []) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ImpersonateTenantPanel tenant={tenant} activeForTenant={active} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("ImpersonateTenantPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("rejects a short reason and does not submit", async () => {
    renderPanel();
    await userEvent.type(screen.getByLabelText(/reason/i), "debug");
    await userEvent.click(screen.getByRole("button", { name: /request impersonation/i }));
    expect(await screen.findByText(/at least 10 characters/i)).toBeInTheDocument();
    expect(requestImp).not.toHaveBeenCalled();
  });

  it("submits an impersonation request via the locked dialog", async () => {
    requestImp.mockResolvedValue({ data: { approval_request_id: "ar1", status: "pending" }, error: undefined });
    renderPanel();
    await userEvent.type(screen.getByLabelText(/reason/i), "Investigating a posting discrepancy");
    await userEvent.click(screen.getByRole("button", { name: /request impersonation/i }));
    expect(await screen.findByText(/create an approval request, not execute/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /create approval request/i }));
    await waitFor(() =>
      expect(requestImp).toHaveBeenCalledWith({
        tenant_id: "t1",
        reason: "Investigating a posting discrepancy",
      }),
    );
    expect(await screen.findByText(/approval request created/i)).toBeInTheDocument();
  });

  it("enters an approved session: activates then navigates to tenant context", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: "ta", expires_in: 900, tenant_slug: "alpha" }),
    });
    renderPanel([{ id: "imp1", expires_at: "2026-06-13T12:30:00Z" }]);
    await userEvent.click(screen.getByRole("button", { name: /enter session/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/impersonation/activate",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
  });

  it("toasts when entering a session fails (e.g. expired)", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 410, json: async () => ({ detail: "session expired" }) });
    renderPanel([{ id: "imp1", expires_at: "2026-06-13T12:30:00Z" }]);
    await userEvent.click(screen.getByRole("button", { name: /enter session/i }));
    expect(await screen.findByText(/session expired/i)).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- ImpersonateTenantPanel` → FAIL.

- [ ] **Step 3: Write the panel**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/impersonate/_components/ImpersonateTenantPanel.tsx
"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Card,
  FormattedDateTime,
  FormField,
  MakerCheckerConfirmDialog,
  Textarea,
  toast,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  impersonationRequestSchema,
  type ImpersonationRequestInput,
  type TenantOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface ActiveImpersonation {
  id: string;
  expires_at: string;
}

export function ImpersonateTenantPanel({
  tenant,
  activeForTenant,
}: {
  tenant: TenantOut;
  activeForTenant: ActiveImpersonation[];
}) {
  const { resources } = useAuth();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, setPending] = useState<ImpersonationRequestInput | null>(null);
  const [entering, setEntering] = useState<string | null>(null);

  const form = useForm<ImpersonationRequestInput>({
    resolver: zodResolver(impersonationRequestSchema),
    defaultValues: { reason: "" },
  });

  const requestMutation = useTypedMutation<unknown, ImpersonationRequestInput>(
    async (vars) => {
      // resources.impersonations.request is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.impersonations.request({ tenant_id: tenant.id, reason: vars.reason }) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Approval request created", {
          description: "Another platform user must approve before you can enter the tenant session.",
        });
        setConfirmOpen(false);
        setPending(null);
        form.reset();
      },
      onError: (error) => {
        toast.error("The impersonation was not requested", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  async function enterSession(impersonationId: string) {
    setEntering(impersonationId);
    try {
      const res = await fetch("/api/impersonation/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          impersonation_id: impersonationId,
          tenant_id: tenant.id,
          tenant_name: tenant.name,
        }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: string } | null;
        toast.error("Couldn’t enter the tenant session", {
          description: apiErrorMessage(body, "The session may have expired. Request a new one."),
        });
        return;
      }
      // Full-page navigation so middleware re-resolves into the tenant context
      // (the tenant slug cookie is now set).
      window.location.assign("/");
    } finally {
      setEntering(null);
    }
  }

  return (
    <div className="flex max-w-xl flex-col gap-6">
      {activeForTenant.length > 0 ? (
        <Card className="flex flex-col gap-3 p-6">
          <h2 className="text-[var(--text-h5)] font-semibold">Approved sessions</h2>
          {activeForTenant.map((imp) => (
            <div key={imp.id} className="flex items-center justify-between gap-4">
              <span className="text-[var(--text-secondary)]">
                Expires <FormattedDateTime value={imp.expires_at} />
              </span>
              <Button
                variant="primary"
                disabled={entering !== null}
                onClick={() => void enterSession(imp.id)}
              >
                Enter session
              </Button>
            </div>
          ))}
        </Card>
      ) : null}

      <Card className="flex flex-col gap-4 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Request impersonation</h2>
        <p className="text-[var(--text-secondary)]">
          Impersonation requires approval from another platform user and is
          time-limited. All actions during the session are audited as yours.
        </p>
        <form
          noValidate
          className="flex flex-col gap-5"
          onSubmit={form.handleSubmit((values) => {
            setPending(values);
            setConfirmOpen(true);
          })}
        >
          <FormField
            control={form.control}
            name="reason"
            label="Reason"
            required
            helpText="Recorded on the approval request and the audit trail. Minimum 10 characters."
            render={({ field, id, describedBy, invalid }) => (
              <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
            )}
          />
          <div>
            <Button type="submit" disabled={requestMutation.isPending}>
              Request Impersonation
            </Button>
          </div>
        </form>
      </Card>

      <MakerCheckerConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        operationLabel="tenant impersonation"
        subjectLabel={tenant.name}
        busy={requestMutation.isPending}
        onConfirm={() => {
          if (pending) requestMutation.mutate(pending);
        }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Write the page (fetches active impersonations for this tenant server-side)**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/impersonate/page.tsx
import { notFound } from "next/navigation";
import type { TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import {
  ImpersonateTenantPanel,
  type ActiveImpersonation,
} from "./_components/ImpersonateTenantPanel";

export const metadata = { title: "Impersonate Tenant" };

interface ImpersonationOut {
  id: string;
  tenant_id: string;
  expires_at: string;
  ended_at: string | null;
  revoked_at: string | null;
}

export default async function ImpersonateTenantPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "impersonation.start");

  const { data: tenant } = await (
    resources.tenants.get(id) as Promise<{ data?: TenantOut; error?: unknown }>
  );
  if (!tenant) notFound();

  // The operator's active impersonations, filtered to this tenant and still live.
  const { data: active } = await (
    resources.impersonations.listActive() as Promise<{
      data?: ImpersonationOut[];
      error?: unknown;
    }>
  );
  const activeForTenant: ActiveImpersonation[] = (active ?? [])
    .filter((imp) => imp.tenant_id === id && !imp.ended_at && !imp.revoked_at)
    .map((imp) => ({ id: imp.id, expires_at: imp.expires_at }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Impersonate {tenant.name}</h1>
      <ImpersonateTenantPanel tenant={tenant} activeForTenant={activeForTenant} />
    </div>
  );
}
```

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- ImpersonateTenantPanel` → PASS (4). `typecheck` + `lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/impersonate" admin/apps/portal/src/__tests__/platform-tenants/ImpersonateTenantPanel.test.tsx
git commit -m "feat(portal): impersonate screen (request + enter approved session)"
```

---

## Task 9: Mount the banner in the tenant shell + "End now"

The `(tenant-authed)` layout reads the impersonation marker cookie and renders `<ImpersonationBanner>` above the shell. "End now" calls the end route handler then navigates back to platform.

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/_components/ImpersonationBannerClient.tsx`
- Modify: `admin/apps/portal/app/(tenant-authed)/layout.tsx`
- Create: `admin/apps/portal/src/__tests__/impersonation-banner-client.test.tsx`

- [ ] **Step 1: Write the failing test (the client wrapper that owns the End action)**

```tsx
// admin/apps/portal/src/__tests__/impersonation-banner-client.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const assign = vi.fn();
const fetchMock = vi.fn();

import { ImpersonationBannerClient } from "../../app/(tenant-authed)/_components/ImpersonationBannerClient";

describe("ImpersonationBannerClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("location", { assign } as unknown as Location);
  });

  it("ends the session and returns to the tenant detail in platform context", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) });
    render(
      <ImpersonationBannerClient
        impersonationId="imp1"
        tenantId="t1"
        tenantName="Alpha SACCO"
        expiresAt="2026-06-13T12:30:00Z"
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /end now/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/impersonation/end",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/platform/tenants/t1"));
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- impersonation-banner-client` → FAIL.

- [ ] **Step 3: Write the client wrapper**

```tsx
// admin/apps/portal/app/(tenant-authed)/_components/ImpersonationBannerClient.tsx
"use client";

import { useState } from "react";
import { ImpersonationBanner } from "@sacco/ui";

export function ImpersonationBannerClient({
  impersonationId,
  tenantId,
  tenantName,
  expiresAt,
}: {
  impersonationId: string;
  tenantId: string;
  tenantName: string;
  expiresAt: string;
}) {
  const [busy, setBusy] = useState(false);

  async function end() {
    setBusy(true);
    try {
      await fetch("/api/impersonation/end", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ impersonation_id: impersonationId }),
      });
    } finally {
      // Whether the call succeeded or not, the end route clears the tenant
      // cookies; return to the platform tenant detail.
      window.location.assign(`/platform/tenants/${tenantId}`);
    }
  }

  return (
    <ImpersonationBanner
      tenantName={tenantName}
      expiresAt={expiresAt}
      onEnd={() => void end()}
      busy={busy}
    />
  );
}
```

- [ ] **Step 4: Mount in the tenant-authed layout**

In `app/(tenant-authed)/layout.tsx`, read the marker cookie and render the banner above the shell. Add the import and the read; place the banner as the first child inside the outermost flex container (above the header). Read the existing layout first; insert:

```tsx
import { readImpersonationCookie } from "@/auth/cookies";
import { ImpersonationBannerClient } from "./_components/ImpersonationBannerClient";
```

After the auth resolution (where `slug`/`user` are known), before the return, add:

```tsx
  const impersonation = await readImpersonationCookie();
```

Then in the JSX, change the outer structure so the banner renders at the very top (full width), e.g. wrap the existing `<div className="flex min-h-screen">` content:

```tsx
          <div className="flex min-h-screen flex-col">
            {impersonation ? (
              <ImpersonationBannerClient
                impersonationId={impersonation.id}
                tenantId={impersonation.tenantId}
                tenantName={impersonation.tenantName}
                expiresAt={impersonation.expiresAt}
              />
            ) : null}
            <div className="flex flex-1">
              {/* existing header+sidebar+main structure */}
            </div>
          </div>
```

Preserve the existing `AppShellHeader` / `AppShellSidebar` / `<main>` structure inside — only add the banner above it and adjust the flex wrapper to stack vertically. Keep all existing providers (`AuthProvider`, `PortalUserProvider`, `TenantCurrencyProvider`, `AppErrorBoundary`) unchanged.

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- impersonation-banner-client` → PASS. `typecheck` + `lint` → clean. Full portal suite → green.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/(tenant-authed)" admin/apps/portal/src/__tests__/impersonation-banner-client.test.tsx
git commit -m "feat(portal): mount impersonation banner in tenant shell with End now"
```

---

## Task 10: Full-module verification

**Files:** none (verification only, unless a fix is needed).

- [ ] **Step 1: Full verification**

```bash
cd admin
pnpm --filter @sacco/schemas test
pnpm --filter @sacco/ui test
pnpm --filter @sacco/portal test
pnpm --filter @sacco/portal typecheck
pnpm --filter @sacco/portal lint
pnpm --filter @sacco/ui typecheck
pnpm --filter @sacco/schemas typecheck
```

All green. The portal suite should be the pre-SP14 count plus the new EditTenantForm / SuspendTenantForm / TenantActions / ImpersonateTenantPanel / impersonation-routes / impersonation-banner-client / cookies-impersonation tests.

- [ ] **Step 2: Confirm no out-of-scope changes**

Run `git diff main..HEAD --stat` and confirm every path is under `admin/` or `docs/`. No `app/` (backend) changes (contract B/N).

- [ ] **Step 3: Manual smoke (recommended)**

Backend + portal up. As an admin: tenant detail → Edit (rename, immediate) → Suspend (reason → maker-checker dialog → approval request) → as a second operator approve the suspend → tenant shows suspended → Reactivate (confirm → active). Then Impersonate → submit reason → second operator approves the `platform.start_impersonation` request → return to the impersonate screen → "Enter session" → redirected into the tenant context with the banner → "End now" → back to platform detail. Confirm a `support`-only user sees Impersonate but not Edit/Suspend.

- [ ] **Step 4: Commit (only if a fix was needed)**

```bash
git add -A && git commit -m "fix(portal): SP14 verification fixes"
```

---

## Self-Review

**Spec coverage (index §663-671):** edit screen (Task 2) ✓; suspend screen, maker-checker (Task 3) ✓; reactivate (Task 4) ✓; impersonate screen (Task 8) ✓; cross-context redirect + persistent banner with tenant name / ends-at / End now (Tasks 5, 7, 9) ✓; consumes `PATCH/suspend/reactivate` + `POST /impersonations` + `GET /impersonations/active` + `mint-tenant-token` + `DELETE` — all existing, none added ✓. **assign-plan deliberately deferred to SP15** (documented; no SP14 screen, returns a subscription).

**Deliberate gaps (documented):** impersonation approval UI is SP17 (request is submitted here; approval out-of-band until then); `/impersonations/all` + revoke-other is a later ops sub-plan; e2e + i18n per portal-wide deferrals; the impersonation cookie marker is httpOnly + read server-side (no client storage, contract C).

**Type consistency:** `tenantPatchSchema`/`tenantSuspendSchema`/`impersonationRequestSchema` (Task 1) consumed in Tasks 2/3/8. `ImpersonationMarker` + cookie helpers (Task 6) consumed in Task 7. `ImpersonationBannerProps` (Task 5) consumed in Task 9 via `ImpersonationBannerClient`. `ActiveImpersonation` defined in Task 8's panel, consumed by its page. `TenantActions({tenant,canWrite,canImpersonate})` (Task 4) matches the TenantDetail wiring. Activate route body `{impersonation_id, tenant_id, tenant_name}` matches the panel's `enterSession` POST and the route test.

**Verify-before-wiring flags:** `Textarea` export from `@sacco/ui` (Task 3 — fall back to `Input` if absent); warning tokens `--surface-warning`/`--text-warning-strong` + `Button size="small"` (Task 5); `clearRefreshCookie` arg shape (Task 7); `ConfirmDialog` + `Button asChild variant="destructive"` compose (Task 4); the `(tenant-authed)` layout's exact JSX structure when inserting the banner (Task 9 — preserve all providers).
