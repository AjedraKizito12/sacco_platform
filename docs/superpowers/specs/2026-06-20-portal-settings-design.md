# Portal — Platform Settings (SP20) Design

**Date:** 2026-06-20
**Phase:** 2 (Admin Portal), sub-plan 20
**Status:** Approved

## Goal

Fill the **Settings** nav group — the last of the 7 platform nav groups — as a
**read-only hub**: a settings index plus Security (real JWT signing-key view),
Billing (informational + links), and Notifications (Phase-3 placeholder). After
SP20 the portal's full screen inventory is complete.

## Contract posture (pure client — zero new endpoints)

SP20 is a **pure client** (contract B/N). The only real data source is the
existing `GET /platform/jwt-keys`; everything else is static informational
content or links. No backend files change. There is deliberately **no** editing
of any setting — billing-config values (grace period, finance email) and
session/password policy have no backend store, and surfacing them would require a
new endpoint (out of scope). All changes live under `admin/`.

Already in place (verified):

- **Backend:** `GET /platform/jwt-keys` → `list[JwtKeyOut]`, mounted with
  `dependencies=[Depends(get_current_superuser)]` (superuser-gated). `JwtKeyOut`
  fields: `id, kid, algorithm, audience, status, created_at, activated_at,
  retired_at, deleted_at`. `status ∈ {active, retiring, retired}` (DB CHECK).
- **permissions:** `platform.security.jwt_keys.read → superuser` already exists.
- **sidebar:** the platform "Settings" `<SidebarItem href="/platform/settings">`
  exists but is **ungated** (no `<PermissionGuard>`).
- **@sacco/ui:** `StatusBadge` (entity union in `status-maps.ts`, registry maps
  each entity → a `StatusMap`), `DataTable`, `Card`, `FormattedDate`.
- **@sacco/api-client:** `resources` builder pattern; `queryKeys` flat factory.

New in this sub-plan: a `settings.read` permission, a `JwtKeyOut` schema, a
`keys` api-client resource + `queryKeys.keys`, a `jwt_key` StatusBadge entity,
and the four Settings pages + a `JwtKeysTable`.

## Permission mapping (authoritative)

| Screen | Backend gate | Portal gate |
|--------|--------------|-------------|
| `/platform/settings` (hub) | — | `settings.read` (admin) |
| `/platform/settings/billing` | — | `settings.read` (admin) |
| `/platform/settings/notifications` | — | `settings.read` (admin) |
| `/platform/settings/security` | `GET /platform/jwt-keys` → superuser | `platform.security.jwt_keys.read` (superuser) |

Add `"settings.read": "admin"` to `permissions.ts`. Reuse the existing
`platform.security.jwt_keys.read` for the security page. Gate the sidebar
Settings link with `settings.read`. UI gating is UX-only; the API enforces
(contract D) — the keys endpoint is the real superuser boundary.

## Screens

### `/platform/settings` — hub

A page of cards, each linking to a sub-area with a one-line description:
- **Billing** → `/platform/settings/billing`
- **Notifications** → `/platform/settings/notifications`
- **Security** → `/platform/settings/security` — rendered **only** when the
  current user has `platform.security.jwt_keys.read` (superuser), via
  `userHasPermission`. Non-superuser admins don't see a card that would bounce
  them to permission-denied.

Gated `settings.read`. No data fetch.

### `/platform/settings/security` — JWT signing keys (real data)

- Server component, gated `requirePlatformPermission(user,
  "platform.security.jwt_keys.read")`.
- Fetches `resources.keys.listJwtKeys()` (cast `{ data?, error? }`), feeds a
  client `<JwtKeysTable rows={data ?? []} />`.
- `<JwtKeysTable>`: in-memory `<DataTable>` adapter (the endpoint is
  unpaginated → same pattern as SP12 UsersTable / SP16 InvoicesTable). `TData =
  JwtKeyOut` (has `id`, satisfies contract T). Columns: **Key ID** (`kid`,
  monospace), **Status** (`<StatusBadge entity="jwt_key" status={status} />`),
  **Algorithm**, **Audience**, **Created** (`<FormattedDate>`), **Activated**
  (`activated_at` or "—"), **Retired** (`retired_at` or "—"). No row actions —
  read-only.
- Below the table, an informational `<Card>`: "Signing keys are rotated
  automatically by a scheduled job. Session TTL and password policy are managed
  via environment configuration." (Static — these values have no API.)
- Empty state: "No signing keys" (shouldn't happen in a configured env, but the
  table handles it).

### `/platform/settings/billing` — informational

Static `<Card>`s (no fetch), gated `settings.read`:
- **Invoice numbering** — "Invoices are numbered `INV-YYYY-NNNNNN` per year"
  (a fixed backend contract).
- **Default plan & pricing** — a sentence + a link to `/platform/billing/plans`
  ("Manage plans"). Default-plan assignment happens per-tenant on the tenant
  detail page; this is a pointer, not an editor.
- **Grace period** — "Past-due subscriptions retain access through their grace
  period before suspension" (behaviour note; the value is config, not editable
  here).

### `/platform/settings/notifications` — Phase-3 placeholder

A single `<Card>` (gated `settings.read`): "Notifications coming soon —
email/SMS providers wire up in Phase 3." Mirrors the notification-bell stub
(contract O). No fetch, no config.

## New supporting pieces

- **`@sacco/schemas`** — `JwtKeyOut` interface (mirror the Pydantic; dates as ISO
  strings, nullable `activated_at`/`retired_at`/`deleted_at`).
- **`@sacco/api-client`** — `resources/keys.ts`: `listJwtKeys() → GET
  /platform/jwt-keys`. Register in `resources/index.ts`. Add `queryKeys.keys`
  (`root()` + `list()` — for symmetry with other domains, even though the page
  is server-fetched).
- **`@sacco/ui`** — add `"jwt_key"` to the `StatusEntity` union, a
  `JWT_KEY_STATUS` map (`active → success`, `retiring → warning`, `retired →
  neutral`), and register it in the entity→map lookup. Unknown statuses already
  fall back to `neutral` with the raw value (contract S).

## File structure

**`@sacco/schemas`**
- Modify `packages/schemas/src/platform.ts` — add `JwtKeyOut`.

**`@sacco/api-client`**
- Create `packages/api-client/src/resources/keys.ts`.
- Modify `packages/api-client/src/resources/index.ts` — register `keys`.
- Modify `packages/api-client/src/query-keys.ts` — add `keys`.

**`@sacco/ui`**
- Modify `packages/ui/src/components/StatusBadge/status-maps.ts` — `jwt_key`
  entity + map + registry row.
- Modify the status-maps test (if present) to cover `jwt_key`.

**`@sacco/portal`**
- Modify `apps/portal/src/auth/permissions.ts` — `settings.read`.
- Modify `apps/portal/src/components/AppShellSidebar.tsx` — gate the Settings link.
- Create `app/platform/(authed)/settings/page.tsx` (hub).
- Create `app/platform/(authed)/settings/billing/page.tsx`.
- Create `app/platform/(authed)/settings/notifications/page.tsx`.
- Create `app/platform/(authed)/settings/security/page.tsx`.
- Create `app/platform/(authed)/settings/security/_components/JwtKeysTable.tsx`.
- Tests under `apps/portal/src/__tests__/platform-settings/`.

## Out of scope (deferred)

- **Editing any setting** — no backend store (contract B). Billing-config values
  and session/password policy stay informational.
- **Key rotation / create / delete actions** — rotation is a Celery beat job;
  CLAUDE.md forbids direct create/delete of signing-key rows.
- **Real notification provider config** — Phase 3.
- **Surfacing session-TTL / password-policy values from config** — would need a
  new endpoint.
- **e2e + next-intl** — portal-wide deferrals (raw English), matching SP12–19.

## Testing strategy

- **Portal:** Vitest + Testing Library. `JwtKeysTable` (row render — kid, status
  badge, algorithm; empty state; `useTableUrlState` mocked, per the established
  DataTable test pattern). StatusBadge `jwt_key` mapping (if the status-maps test
  file enumerates entities). Per-package `test` + `typecheck` + `lint` green; all
  changes under `admin/`.
