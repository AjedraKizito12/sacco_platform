# Portal — Tenant Users Management (SP23) Design

**Date:** 2026-06-20
**Phase:** 2 (Admin Portal), sub-plan 23
**Status:** Approved

## Goal

Fill the `/tenants/[id]/users` gap from the Phase 2 screen inventory — a platform
admin manages a tenant's users (list, create, edit, lock, assign role, reset
password). The backend (`tenant_users_admin`, P1.7-04) and the api-client
resource are already built and currently unused by any screen.

## Contract posture (pure client — zero new endpoints)

SP23 is a **pure client** (contracts B/N). All endpoints + api-client methods +
the queryKey already exist. New work: `@sacco/schemas` types, a `tenant_user`
StatusBadge entity, two permission keys, and four screens + a table. All under
`admin/`.

Already in place (verified):

- **Backend** `/platform/tenants/{tenant_id}/users` (gate `CurrentAdmin` for
  read AND write; uses `get_session_for_tenant_schema`; NOT subscription-gated):
  - `GET ""` → `list[TenantUserOut]` (filters `impersonation_id IS NULL` — shadows hidden).
  - `POST ""` → `TenantUserCreateOut` (201): `{ user, password_reset_token, password_reset_expires_in }`. Creates with no password; the token is one-time.
  - `GET "/{user_id}"` → `TenantUserOut` (404 for a shadow user).
  - `PATCH "/{user_id}"` → `TenantUserOut`. **Direct** (no maker-checker). Body `{ full_name?, is_active?, is_admin? }`. 404 for shadows.
  - `POST "/{user_id}/password-reset"` → `PasswordResetOut`: `{ user_id, password_reset_token, password_reset_expires_in }` (24h TTL). 404 for shadows.
- **api-client** `resources.tenants.{listUsers(id), getUser(id,userId), createUser(id,body), patchUser(id,userId,body), resetUserPassword(id,userId)}` (all carry the `as never` wart → cast to `{ data?, error? }`).
- **queryKeys** `tenants.users(id)`.
- **@sacco/ui** `OneTimeModal` (`apps/portal/src/components/OneTimeModal.tsx`,
  props `open / onAcknowledge / title / description / payload / payloadLabel? /
  warningCopy?`) — its docstring already names admin tenant-user reset as the use
  case. `DataTable`, `StatusBadge`, `FormField`, `Input`, shadcn `Select`/`Checkbox`,
  `ConfirmDialog`, `FormattedDate`/`RelativeTime`.
- The SP12 platform-users module is the structural template (list / new / [id] / [id]/edit).

## Backend facts (authoritative)

`TenantUserOut`: `id, email, full_name, is_active, is_admin, last_login_at,
created_at, updated_at, impersonation_id (always null here)`.
`TenantUserCreateIn`: `email, full_name, is_admin (default false)`.
`TenantUserPatchIn`: `full_name?, is_active?, is_admin?`.

## Permission mapping (authoritative)

Backend gates `CurrentAdmin` for every tenant-user route. Add to `permissions.ts`:

```ts
"platform.tenants.users.read": "admin",
"platform.tenants.users.write": "admin",
```

- List / detail pages: `platform.tenants.users.read`.
- New / edit / reset actions: `platform.tenants.users.write`.
- The "Users" entry point on `TenantDetail` is gated `platform.tenants.users.read`.

UI gating is UX-only; the API enforces (contract D).

## Screens (mirror SP12 platform-users)

All server-fetched via `getPlatformPageContext()` (the tenant id comes from the
route). Cast the `Promise<never>` resource results to `{ data?, error? }`.

### `/platform/tenants/[id]/users` — list

- Server: `resources.tenants.listUsers(id)` → `TenantUserOut[]`.
- `<TenantUsersTable rows tenantId />`: in-memory `<DataTable>` adapter (the
  endpoint is unpaginated → same pattern as SP12 UsersTable). Columns: **Email**
  (links to detail), **Name**, **Role** (`is_admin ? "Admin" : "Member"`),
  **Status** (`<StatusBadge entity="tenant_user" status={is_active ? "active" :
  "inactive"} />`), **Last login** (`<RelativeTime>` or "Never"). `TData =
  TenantUserOut` (has `id`, contract T).
- Header: an "Add user" `<Button asChild><Link href=".../users/new">` gated
  `platform.tenants.users.write`.
- Empty state: "No users yet."

### `/platform/tenants/[id]/users/new` — create

- RHF + Zod (`tenantUserCreateSchema`): email, full_name, is_admin (Checkbox).
- On submit → `createUser(id, values)`. Success returns `TenantUserCreateOut`;
  show the `password_reset_token` in `<OneTimeModal>` (title "User created",
  payloadLabel "Password reset token", warningCopy about out-of-band delivery
  until Phase 3, the TTL from `password_reset_expires_in`). `onAcknowledge` →
  `router.push(".../users")` + toast.
- Gated `platform.tenants.users.write`.

### `/platform/tenants/[id]/users/[userId]` — detail

- Server: `getUser(id, userId)` → `TenantUserOut`; `notFound()` if absent (also
  covers the shadow 404).
- Read-only `<Card>`: email, name, role, status badge, last login, created.
- Actions (gated write): **Edit** (link to `.../edit`), **Reset password**
  (`<ResetPasswordButton>` client component → `resetUserPassword(id, userId)` →
  `<OneTimeModal>` with the 24h token).
- `<AuditBarConnected>`? — the tenant-user record lives in the **tenant** schema,
  not platform; `AuditBarConnected` queries platform audit. So **no AuditBar**
  here (a tenant-schema audit bar would need the tenant audit endpoint wired to a
  record id — out of scope; documented). The per-tenant `/tenants/[id]/audit`
  viewer (SP19) already covers tenant-schema activity.

### `/platform/tenants/[id]/users/[userId]/edit` — patch

- RHF + Zod (`tenantUserPatchSchema`): full_name, **is_active** (the "lock"),
  **is_admin** (the "assign role"). Pre-filled from a server fetch of the user.
- On submit → `patchUser(id, userId, values)` (**direct**, no maker-checker) →
  toast + `router.push` back to detail. Gated `platform.tenants.users.write`.

## Entry point

Add a **"Users"** link on `TenantDetail` (next to the existing "Audit log"
link), gated `platform.tenants.users.read`, → `/platform/tenants/${t.id}/users`.
`TenantDetail` is a client component; pass a `canManageUsers: boolean` prop from
the tenant detail server page (like the existing `canViewAudit`).

## New supporting pieces

- **`@sacco/schemas`** (`src/tenants.ts` or a new `tenant-users.ts`):
  - `TenantUserOut` interface (mirror the Pydantic).
  - `tenantUserCreateSchema` (`email` valid email, `full_name` 1–200, `is_admin`
    boolean default false) + `TenantUserCreateInput`.
  - `tenantUserPatchSchema` (all optional: `full_name` 1–200, `is_active`,
    `is_admin`) + `TenantUserPatchInput`.
  - `tenantUserRoleLabel(isAdmin)` → "Admin" | "Member".
- **@sacco/ui** `status-maps.ts`: add `"tenant_user"` to `StatusEntity` + a
  `TENANT_USER_STATUS` map (`active → success`, `inactive → neutral`) +
  registry row.

## File structure

**`@sacco/schemas`** — add tenant-user types (+ barrel export if a new file).
**`@sacco/ui`** — `status-maps.ts` (+ `tenant_user`), `StatusBadge.test.tsx` (+ a case).
**`@sacco/portal`**
- `src/auth/permissions.ts` (+ 2 keys).
- `app/platform/(authed)/tenants/[id]/users/page.tsx` + `_components/TenantUsersTable.tsx`.
- `.../users/new/page.tsx` + `_components/CreateTenantUserForm.tsx`.
- `.../users/[userId]/page.tsx` + `_components/ResetPasswordButton.tsx`.
- `.../users/[userId]/edit/page.tsx` + `_components/EditTenantUserForm.tsx`.
- `app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx` + `tenants/[id]/page.tsx` (Users link + `canManageUsers`).
- Tests under `apps/portal/src/__tests__/platform-tenant-users/`.

## Out of scope (deferred)

- **Active sessions panel** on the detail page — no tenant-user session-list endpoint.
- **AuditBar on the tenant-user detail** — tenant-schema record; covered by `/tenants/[id]/audit`.
- **Shadow / impersonation users** — filtered out by the backend (404 on detail).
- **Tenant-side self-management** — separate tenant-operator surface.
- **e2e + next-intl** — portal-wide deferrals (raw English).

## Testing strategy

- **Portal:** Vitest + Testing Library.
  - `TenantUsersTable` (row render — email link, role label, status badge; empty
    state; `useTableUrlState` mocked).
  - `CreateTenantUserForm` (validation; on success the OneTimeModal shows the
    token — mock the resource).
  - `EditTenantUserForm` (pre-fill + patch submit; direct, no maker-checker dialog).
  - `tenantUserCreateSchema` / `tenantUserPatchSchema` (`@sacco/schemas`).
  - `tenant_user` StatusBadge mapping (`@sacco/ui`).
- Per-package `test` + `typecheck` + `lint` green; all changes under `admin/`.
