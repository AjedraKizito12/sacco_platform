# SACCO Admin Portal — Members Module (Phase 3a) Design

**Date:** 2026-06-21
**Phase:** 3 (SACCO Admin / tenant-operator portal), sub-plan a — Members
**Status:** Approved

## Context: a new phase

Phase 2 (platform back-office) is functionally complete. Phase 3 builds the
**SACCO Admin Portal** — the tenant-operator UI a SACCO's own staff use to run
their cooperative. It is the **tenant-authed side of the existing portal app**
(the `(tenant-authed)` route group, tenant login, and tenant sidebar already
exist). Phase 3 ships module-by-module — **Members first** — and each module is a
**pure client** of the already-complete tenant backend (members, savings, shares,
credit, fees, reporting are all on `main`).

The **Members portal** (member self-service) is **Phase 4** — it needs a new
member-auth backend first and is out of scope here. The remaining **Phase 2
polish** (deployment, docs, deeper e2e, a11y, i18n, typography) is **deferred**.

This sub-plan establishes the tenant-operator pattern (server-fetch via
`getTenantPageContext()`, in-memory `<DataTable>`, RHF/Zod forms, maker-checker
action) that Savings/Shares/Credit/Fees/Reports will clone.

## Contract posture (pure client — zero backend)

All endpoints, api-client methods, Zod input schemas, the `member` StatusBadge
entity, and the tenant sidebar link already exist. New work: a hand-written
`MemberOut` read type in `@sacco/schemas`, and the four screens. All under
`admin/`.

Already in place (verified):

- **Backend** (`/members`, gate `CurrentTenantUser` — any authenticated tenant
  user; there is no fine-grained tenant RBAC):
  - `POST /members` → `MemberOut` (201).
  - `GET /members` (`?status=`) → `list[MemberOut]`.
  - `GET /members/{member_id}` → `MemberOut`.
  - `POST /members/{member_id}/status-change` → `StatusChangeOut` **(202)** —
    member status changes are **maker-checker** (CLAUDE.md rule 7). Body
    `{new_status, reason}`; response `{approval_request_id, status}`.
- **api-client** `resources.members.{list(query?), get(id), create(body),
  changeStatus(id, body)}` (carry the `as never` wart → cast to `{data?, error?}`).
- **@sacco/schemas** (`member.ts`): `memberRegistrationSchema`,
  `memberStatusChangeSchema`, `memberStatusSchema`, `memberGenderSchema`,
  `idDocumentTypeSchema`, `memberIdSchema` + inferred `*Input` types.
- **@sacco/ui**: `member` StatusBadge entity (`MEMBER_STATUS`), `DataTable`,
  `FormField`/`Input`/`Select`/`DateInput`, `ConfirmDialog`/
  `MakerCheckerConfirmDialog`, `StatusBadge`, `FormattedDate`.
- **portal**: `getTenantPageContext()` (the tenant server-fetch entrypoint, SP16),
  the `(tenant-authed)` layout + tenant sidebar (with a `/members` link, SP08).

## Backend facts (authoritative)

`MemberOut`: `id, member_number, full_name, date_of_birth, gender, phone, email,
physical_address, national_id_number, id_document_type, id_document_number,
id_issued_date, id_expiry_date, status, joined_at, created_at, updated_at`.
`MemberIn` == the fields `memberRegistrationSchema` already mirrors.
`status` ∈ `pending | active | suspended | exited` (DB CHECK; new members start
`pending`).
`StatusChangeIn.new_status` ∈ `Literal["active","suspended","exited"]` only.

### Two schema-vs-backend drifts to respect (locked decisions)

1. **The Zod `memberStatusSchema` enum is broader than the backend allows.** It
   lists `prospect/active/dormant/suspended/exited/deceased`, but the backend's
   `status-change` only accepts `active/suspended/exited`. The change-status form
   **offers only `active`, `suspended`, `exited`** (a local `const` option list),
   not the full Zod enum, so it can never submit a 422. (Do not "fix" the Zod
   enum — it is shared and out of this sub-plan's scope; just constrain the UI.)
2. **`memberStatusChangeSchema` carries an `idempotency_key`** the backend
   `StatusChangeIn` does not read. Pydantic v2 ignores the extra field, so
   sending it is harmless; keep it (one fresh UUID per form instance, per
   contract L), and rely on the auto-injected `Idempotency-Key` header.

## Permission / gating

The backend gates every member route on `CurrentTenantUser` (any authenticated
tenant user). The portal has **no tenant RBAC keys** (the permission registry is
platform-only). So these pages gate purely on tenant auth via
`getTenantPageContext()` (which redirects to `/login` when unauthenticated). No
new permission keys; no `requirePlatformPermission`.

## Screens (under `app/(tenant-authed)/members/*`)

All server-fetched via `getTenantPageContext()`; cast the `Promise<never>`
resource results to `{ data?, error? }`.

### `/members` — list

- Server: `resources.members.list({})` → `MemberOut[]`.
- `<MembersTable rows={…} />`: in-memory `<DataTable>` adapter (the endpoint is
  unpaginated → same pattern as SP12 UsersTable). Columns: **Member #**
  (`member_number`, links to detail), **Name**, **Gender**, **Phone**
  (or "—"), **Status** (`<StatusBadge entity="member" status={status} />`),
  **Joined** (`joined_at ? <FormattedDate> : "—"`). `TData = MemberOut`.
- Header: a "Register member" `<Button asChild><Link href="/members/new">`.
- Status filter `<Select>` (`pending/active/suspended/exited`) → in-memory filter.
- Empty state: "No members yet."

### `/members/new` — registration

- RHF + `zodResolver(memberRegistrationSchema)`. Fields: full_name (`<Input>`),
  date_of_birth (`<DateInput>`), gender (`<Select>` M/F/X), phone, email,
  physical_address, national_id_number (`<Input>`s), id_document_type
  (`<Select>`), id_document_number, id_issued_date / id_expiry_date
  (`<DateInput>`s). All via `<FormField>`.
- On submit → `members.create(values)` → `toast.success` + `router.push` to the
  new member's detail (`/members/${data.id}`).
- (Long KYC form — `useDraftAutoSave` from `@sacco/ui` is **optional**, deferred;
  not required for v1.)

### `/members/[id]` — detail

- Server: `members.get(id)` → `MemberOut`; `notFound()` if absent.
- Read-only `<Card>`s: identity (member #, name, DOB, gender, status badge,
  joined), contact (phone, email, address), KYC (national ID, ID doc
  type/number/issued/expiry — each "—" when null).
- Header action: **Change status** (`<ChangeMemberStatusButton>`).
- **No `<AuditBar>`** — member is a tenant-schema record and `AuditBarConnected`
  queries platform audit (same as the SP23 tenant-users decision). Tenant-record
  audit is a later item.

### Change status (maker-checker)

`<ChangeMemberStatusButton>` (client): a form `<Dialog>` with a **status
`<Select>` (active / suspended / exited only)** + a required **reason**
(`<Textarea>`, ≥10 chars) → on submit opens `<MakerCheckerConfirmDialog>`
(locked "creates an approval request, not executes" copy) → `changeStatus(id,
{new_status, reason, idempotency_key})`. Success toast: "Status change requested
— pending approval." Invalidate the member detail query; `router.refresh()`.

> **Checker side deferred:** approving a member status-change needs a
> **tenant approvals inbox**, which does not exist yet (Phase 2 built only the
> *platform* inbox). So the change is *created* here; approving is out of band
> until a tenant approvals inbox module ships (a later Phase-3 module mirroring
> SP17). The 202 `approval_request_id` is surfaced in the success toast.

## New supporting pieces

- **`@sacco/schemas`** (`member.ts`): add the `MemberOut` read interface (the Zod
  *inputs* exist; the read shape does not). Dates/timestamps as ISO strings.
- **portal**: `MembersTable`, `CreateMemberForm`, member detail page,
  `ChangeMemberStatusButton`. The tenant sidebar `/members` link already exists.

## File structure

**`@sacco/schemas`** — modify `src/member.ts` (+ `MemberOut`).
**`@sacco/portal`**
- `app/(tenant-authed)/members/page.tsx` + `_components/MembersTable.tsx`.
- `app/(tenant-authed)/members/new/page.tsx` + `_components/CreateMemberForm.tsx`.
- `app/(tenant-authed)/members/[id]/page.tsx` + `_components/ChangeMemberStatusButton.tsx`.
- Tests under `apps/portal/src/__tests__/tenant-members/`.

## Out of scope (deferred)

- **Member document/photo uploads**, full-text member search, bulk import.
- **`<AuditBar>` on tenant records** — needs a tenant audit-bar wiring.
- **Tenant approvals inbox** (the maker-checker checker side) — later Phase-3 module.
- **Members self-service portal** — Phase 4 (needs member-auth backend).
- **e2e + next-intl** — portal-wide deferrals (raw English).

## Testing strategy

- **Portal:** Vitest + Testing Library.
  - `MembersTable` (row render — member# link, status badge; empty state;
    `useTableUrlState` mocked).
  - `CreateMemberForm` (validation; successful create calls `members.create` +
    redirects — mocked resource).
  - `ChangeMemberStatusButton` (only active/suspended/exited offered; the
    maker-checker confirm copy appears; submit calls `changeStatus`).
  - `MemberOut` type compiles against the table/detail consumers.
- Per-package `test` + `typecheck` + `lint` green; all changes under `admin/`.
