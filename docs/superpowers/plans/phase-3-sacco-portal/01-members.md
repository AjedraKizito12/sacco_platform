# SACCO Admin Portal — Members Module (Phase 3a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Environment note (2026-06-21):** background subagents can't get Edit approval; run **inline**. Pure client — no backend, no test DB. **Confirm typecheck PASSES before committing** (a pre-Read edit can silently fail — SP20 lesson).

**Goal:** The first SACCO-operator (tenant-authed) module — Members list / register / detail / change-status — as a pure client of the complete `members` backend. Establishes the tenant-operator pattern the rest of Phase 3 clones.

**Architecture:** Tenant-authed routes under `app/(tenant-authed)/members/*`, server-fetched via `getTenantPageContext()`. In-memory `<DataTable>` list, RHF/Zod registration form, and a maker-checker change-status action (202 → tenant approval). Reuses the existing api-client `resources.members.*`, the `@sacco/schemas` member Zod inputs, and the `member` StatusBadge entity. Adds only a `MemberOut` read type and the screens. Zero backend.

**Tech Stack:** Next.js 15 App Router, React 19, TS strict, `@sacco/ui` (DataTable, FormField, Input, Select, DateInput, Textarea, ConfirmDialog, MakerCheckerConfirmDialog, StatusBadge, FormattedDate, Card), `@sacco/schemas` (member Zod + new Out type), `@sacco/api-client` (`resources.members.*`), Vitest + Testing Library.

---

## Contract & scope notes (read before starting)

- **Zero new backend endpoints** (contract B); everything under `admin/` (contract N).
- **api-client (exists):** `resources.members.{list(query?), get(id), create(body), changeStatus(id, body)}`. All carry the `as never` wart → cast to `{ data?, error? }`.
- **Backend (gate `CurrentTenantUser`):** `MemberOut` fields per the spec; `POST /members` (201); `GET /members?status=`; `GET /members/{id}`; `POST /members/{id}/status-change` → **202** `{approval_request_id, status}` (maker-checker). `status-change` accepts only `new_status ∈ {active, suspended, exited}`.
- **@sacco/schemas (exist):** `memberRegistrationSchema`, `memberStatusChangeSchema`, `memberGenderSchema`, `idDocumentTypeSchema`, `memberStatusSchema`. Add only `MemberOut`.
- **Gating:** tenant auth only (no tenant RBAC keys) — pages call `getTenantPageContext()`, which redirects to `/login` when unauthenticated. No `requirePlatformPermission`.
- **Two drifts (locked):** (1) the change-status `<Select>` offers **only `active/suspended/exited`** (a local const), NOT the broader Zod `memberStatusSchema` enum, so it can't 422. (2) `memberStatusChangeSchema` carries `idempotency_key` the backend ignores — keep it (fresh UUID per form instance).
- **No `<AuditBar>`** on the member detail (tenant-schema record). **Checker side deferred** — approving a status-change needs a tenant approvals inbox (later Phase-3 module); this module only *creates* the approval.
- **Out of scope:** doc uploads, search, bulk import, draft-autosave, e2e + i18n.

## File structure

**`@sacco/schemas`** — modify `src/member.ts` (+ `MemberOut`).
**`@sacco/portal`**
- `app/(tenant-authed)/members/page.tsx` + `_components/MembersTable.tsx`.
- `app/(tenant-authed)/members/new/page.tsx` + `_components/CreateMemberForm.tsx`.
- `app/(tenant-authed)/members/[id]/page.tsx` + `_components/ChangeMemberStatusButton.tsx`.
- Tests under `apps/portal/src/__tests__/tenant-members/`.

---

## Task 1: `MemberOut` read type (`@sacco/schemas`)

**Files:**
- Modify: `admin/packages/schemas/src/member.ts`
- Test: `admin/packages/schemas/src/__tests__/member.test.ts` (create or extend)

- [ ] **Step 1: Failing test** (a light assertion that exercises the new export + a Zod schema)

```ts
import { describe, expect, it } from "vitest";
import { memberRegistrationSchema, type MemberOut } from "../member";

describe("member schemas", () => {
  it("registration requires a full name and DOB", () => {
    expect(memberRegistrationSchema.safeParse({ full_name: "", date_of_birth: "2000-01-01", gender: "M" }).success).toBe(false);
    expect(
      memberRegistrationSchema.safeParse({ full_name: "Ada Loan", date_of_birth: "2000-01-01", gender: "F" }).success,
    ).toBe(true);
  });
  it("MemberOut is structurally usable", () => {
    const m: MemberOut = {
      id: "m1", member_number: "M-0001", full_name: "Ada", date_of_birth: "2000-01-01",
      gender: "F", phone: null, email: null, physical_address: null,
      national_id_number: null, id_document_type: null, id_document_number: null,
      id_issued_date: null, id_expiry_date: null, status: "active",
      joined_at: "2026-06-01", created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    };
    expect(m.member_number).toBe("M-0001");
  });
});
```

Run: `cd admin && pnpm --filter @sacco/schemas test -- member` → FAIL (no `MemberOut` export).

- [ ] **Step 2: Add `MemberOut` to `member.ts`** (after the inferred type exports)

```ts
// Mirrors app/modules/members/schemas.py MemberOut. Dates are ISO strings.
export interface MemberOut {
  id: string;
  member_number: string;
  full_name: string;
  date_of_birth: string;
  gender: string;
  phone: string | null;
  email: string | null;
  physical_address: string | null;
  national_id_number: string | null;
  id_document_type: string | null;
  id_document_number: string | null;
  id_issued_date: string | null;
  id_expiry_date: string | null;
  status: string;
  joined_at: string | null;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 3: Run → PASS; typecheck + lint the package; commit.**

```bash
cd admin && pnpm --filter @sacco/schemas test -- member && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
cd /home/liam/projects/sacco-platform
git add admin/packages/schemas/src/member.ts admin/packages/schemas/src/__tests__/member.test.ts
git commit -m "feat(portal): MemberOut read type

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `<MembersTable>` + list page

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/members/_components/MembersTable.tsx`
- Create: `admin/apps/portal/app/(tenant-authed)/members/page.tsx`
- Test: `admin/apps/portal/src/__tests__/tenant-members/MembersTable.test.tsx`

- [ ] **Step 1: Failing test** (mock `useTableUrlState`, per every DataTable test — copy the full mock from SP16 `InvoicesTable.test.tsx`)

```tsx
// vi.mock("@sacco/ui", ... useTableUrlState ...) with the standard fixed state
import { MembersTable } from "../../../app/(tenant-authed)/members/_components/MembersTable";
import type { MemberOut } from "@sacco/schemas";

const rows: MemberOut[] = [{
  id: "m1", member_number: "M-0001", full_name: "Ada Loan", date_of_birth: "2000-01-01",
  gender: "F", phone: "+256700000000", email: null, physical_address: null,
  national_id_number: null, id_document_type: null, id_document_number: null,
  id_issued_date: null, id_expiry_date: null, status: "active",
  joined_at: "2026-06-01", created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
}];

describe("MembersTable", () => {
  it("links the member number to the detail page and shows the status badge", () => {
    render(<MembersTable rows={rows} />);
    expect(screen.getByRole("link", { name: "M-0001" })).toHaveAttribute("href", "/members/m1");
    expect(screen.getByText("Active")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    render(<MembersTable rows={[]} />);
    expect(screen.getByText("No members yet")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement `MembersTable.tsx`** — in-memory adapter (mirror SP16 `InvoicesTable` incl. the status `filterSlot`). Props `{ rows: MemberOut[] }`. Columns: Member # (`<Link href={/members/${id}}>`), Name, Gender, Phone (`?? "—"`), Status (`<StatusBadge entity="member" status>`), Joined (`joined_at ? <FormattedDate> : "—"`). `id="tenant-members"`, `data={pageRows}`, `state={{ totalRows: filtered.length, isError:false, isPermissionDenied:false }}`, empty `{ title: "No members yet", description: "Register a member to get started." }`. Status filter Select: `pending/active/suspended/exited`.

- [ ] **Step 3: Implement `page.tsx`** (server; tenant-authed)

```tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type { MemberOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { MembersTable } from "./_components/MembersTable";

export const metadata = { title: "Members" };

export default async function MembersPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (
    resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>
  );
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Members</h1>
        <Button asChild><Link href="/members/new">Register member</Link></Button>
      </div>
      <MembersTable rows={data ?? []} />
    </div>
  );
}
```

- [ ] **Step 4: Run test + typecheck + lint; commit.**

```bash
git add "admin/apps/portal/app/(tenant-authed)/members/page.tsx" "admin/apps/portal/app/(tenant-authed)/members/_components/MembersTable.tsx" admin/apps/portal/src/__tests__/tenant-members/MembersTable.test.tsx
git commit -m "feat(portal): SACCO members list + table

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `<CreateMemberForm>` + `/members/new`

**Files:**
- Create: `.../members/new/page.tsx` + `_components/CreateMemberForm.tsx`
- Test: `admin/apps/portal/src/__tests__/tenant-members/CreateMemberForm.test.tsx`

- [ ] **Step 1: Failing test** — validation + successful create calls `members.create` and redirects.

```tsx
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
const create = vi.fn();
vi.mock("@/auth/use-auth", () => ({ useAuth: () => ({ resources: { members: { create } } }) }));
import { CreateMemberForm } from "../../../app/(tenant-authed)/members/new/_components/CreateMemberForm";
// render in <QueryClientProvider>; fill full_name + dob + gender; submit;
// assert create called with the payload; on { data: { id: "m9" } } assert push("/members/m9").
```

- [ ] **Step 2: Implement `CreateMemberForm.tsx`** — RHF + `zodResolver(memberRegistrationSchema)`, mirror SP12 `CreateUserForm` structure. Fields via `<FormField>`: full_name (`<Input>`), date_of_birth (`<DateInput>`), gender (`<Select>` M/F/X — label them Male/Female/Other), phone, email, physical_address (`<Input>`/`<Textarea>`), national_id_number, id_document_type (`<Select>` national_id/passport/driving_license/voters_card), id_document_number, id_issued_date + id_expiry_date (`<DateInput>`). `useTypedMutation` → `members.create(values)` cast `{ data?: MemberOut; error? }`; on success `toast.success("Member registered")` + `router.push(/members/${data.id})`; on error `toast.error(apiErrorMessage(...))`. Cancel → `router.push("/members")`.

> Use `<DateInput>` for the date fields (it reads/writes ISO strings — matches `isoDate`). Confirm its prop shape against an existing consumer (SP14/15 forms) before wiring.

- [ ] **Step 3: Implement `new/page.tsx`** (server) — `getTenantPageContext()` (auth), `<h1>Register member</h1>`, render `<CreateMemberForm />`.

- [ ] **Step 4: Run + commit.**

```bash
git add "admin/apps/portal/app/(tenant-authed)/members/new/" admin/apps/portal/src/__tests__/tenant-members/CreateMemberForm.test.tsx
git commit -m "feat(portal): SACCO member registration form

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: member detail + change-status (maker-checker)

**Files:**
- Create: `.../members/[id]/page.tsx` + `_components/ChangeMemberStatusButton.tsx`
- Test: `admin/apps/portal/src/__tests__/tenant-members/ChangeMemberStatusButton.test.tsx`

- [ ] **Step 1: Detail `[id]/page.tsx`** (server)

`members.get(id)` → `MemberOut`; `notFound()` if absent. Read-only `<Card>`s (identity / contact / KYC) with a `Row` helper (`import type { ReactNode }`), `<StatusBadge entity="member">` for status, `<FormattedDate>` for dates (null → "—"). Header renders `<ChangeMemberStatusButton memberId={id} currentStatus={data.status} />`. No `<AuditBar>`.

- [ ] **Step 2: `ChangeMemberStatusButton.tsx`** (client)

A form `<Dialog>` (status `<Select>` + reason `<Textarea>`) → `<MakerCheckerConfirmDialog>` → mutation. The `<Select>` options are a **local const** `[{value:"active",label:"Active"},{value:"suspended",label:"Suspended"},{value:"exited",label:"Exited"}]` (NOT the Zod enum). RHF + `zodResolver(memberStatusChangeSchema)` with `defaultValues: { new_status: "active", reason: "", idempotency_key: crypto.randomUUID() }` (fresh key per instance). `useTypedMutation` → `members.changeStatus(memberId, values)` cast `{ data?, error? }`; on success `toast.success("Status change requested — pending approval")` + `router.refresh()`. Mirror SP16 `InvoiceActions` for the form-dialog → MakerCheckerConfirmDialog wiring.

- [ ] **Step 3: Test** — only active/suspended/exited offered; the maker-checker confirm copy ("create an approval request" / "Create Approval Request") appears; confirming calls `changeStatus` with the chosen status + a reason.

- [ ] **Step 4: Typecheck + lint + run; commit.**

```bash
git add "admin/apps/portal/app/(tenant-authed)/members/[id]/" admin/apps/portal/src/__tests__/tenant-members/ChangeMemberStatusButton.test.tsx
git commit -m "feat(portal): SACCO member detail + change-status (maker-checker)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Verification + PR

- [ ] **Step 1: Per-package gate**

```bash
cd /home/liam/projects/sacco-platform/admin
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test count (rises by the MembersTable + Create + ChangeStatus cases over the 182 baseline).

- [ ] **Step 2: Contract spot-checks**

- [ ] All changes under `admin/` + `docs/` (`git diff --name-only main...HEAD | grep -vE '^(admin/|docs/)'` empty).
- [ ] No backend files (`git diff --name-only main...HEAD | grep -E '^(app/|tests/)'` empty).
- [ ] Change-status offers only active/suspended/exited (`rg "prospect|dormant|deceased" "admin/apps/portal/app/(tenant-authed)/members"` returns nothing).

- [ ] **Step 3: Final holistic review** — list links to detail; registration validates + redirects; change-status is maker-checker (creates a tenant approval, not executes), copy is the locked maker-side text; no AuditBar; tenant-auth gating only.

- [ ] **Step 4: Push + PR**

```bash
cd /home/liam/projects/sacco-platform
git push -u origin feat/sacco-portal/01-members
gh pr create --title "feat(portal): SACCO admin — Members module (Phase 3a)" --body "$(cat <<'EOF'
## Summary
- First **SACCO-operator (tenant-authed)** module: Members list / register / detail / change-status — the tenant-operator side of the existing portal.
- **Pure client; zero backend.** Consumes the complete `members` backend via `resources.members.*` + the existing `@sacco/schemas` member Zod inputs + the `member` StatusBadge entity. Adds only a `MemberOut` read type.
- Establishes the tenant-operator pattern (getTenantPageContext + in-memory DataTable + RHF/Zod + maker-checker action) that Savings/Shares/Credit/Fees/Reports will clone.

## Notable points
- Change-status is **maker-checker** (202 → creates a tenant-scoped approval). The form offers only the backend-permitted `active/suspended/exited` (the shared Zod enum is broader). Approving needs a **tenant approvals inbox** (not built yet — a later Phase-3 module); this module only *creates* the approval.
- No `<AuditBar>` on the member detail (tenant-schema record).
- Gating is tenant-auth only (no tenant RBAC keys exist).

## Test plan
- `@sacco/schemas` + `@sacco/portal` test/typecheck/lint green (MemberOut, MembersTable, Create/ChangeStatus).
- All changes under `admin/` (contracts B/N).

> CI note: Lint fails environmentally on this repo (account billing lock); reproduced clean locally. Not a required check.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** MemberOut → T1; list → T2; registration → T3; detail + change-status → T4; verify/PR → T5.
- **Type consistency:** `MemberOut` (T1) used by MembersTable (T2) + detail (T4) + Create's success cast (T3). `memberRegistrationSchema`/`memberStatusChangeSchema` (existing) drive T3/T4 forms. Change-status options are a local const, not the Zod enum (the locked drift).
- **Verify-at-execution (grep inline):** `<DateInput>` prop shape (check an existing consumer); the `useTableUrlState` mock shape (copy from InvoicesTable.test.tsx); `getTenantPageContext()` return shape (`{ user, slug, resources }`); `MakerCheckerConfirmDialog` props (open/onOpenChange/operationLabel/subjectLabel/busy/onConfirm).
