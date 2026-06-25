# Phase 4b — Member Self-Service Portal (UI)

**Status:** Design approved 2026-06-25
**Scope:** Frontend only (`admin/`). Pure client of the Phase 4a `/member/*` API.
**Depends on:** Phase 4a (member auth + read-only self-service API), merged to `main` (PR #56).

## Problem

Phase 4a shipped member authentication and read-only `/member/*` endpoints, but
members have no UI. Phase 4b is the member-facing portal: members log in, see
their own financial picture (savings, shares, loans, fees, profile), and manage
their password. It is a **pure client** — no backend changes — mirroring how the
Phase 3 operator portal consumed already-shipped tenant endpoints.

## Decisions (locked during brainstorming)

1. **Same app, new audience.** Member screens live in the existing
   `apps/portal` Next.js app under a real `/member/` path segment with an
   `(authed)` group, mirroring how `platform/` is organized (NOT a parenthesized
   group at root, which would collide with operator routes `/login`, `/savings`).
   Not a separate deployable.
2. **Aggregating dashboard** is the authenticated landing — a summary home built
   by composing the existing `/member/*` list endpoints client-side. **No new
   backend endpoint.**
3. **Reuse the `@sacco/ui` `AppShell`** with a new `member` variant (alongside
   `platform`/`tenant`); operator-only chrome (command palette, notification
   bell beyond its empty stub, impersonation banner) is suppressed for this
   variant.
4. **Read-only v1.** The 4a backend has no member mutations, so the portal is
   strictly read-only except for auth (login / set-password / forgot / reset).
5. Tenant slug reuses the existing `resolveTenantSlug` (subdomain in prod,
   `?tenant=` in dev, cookie fallback).

## Architecture & placement

```
apps/portal/app/
  member/
    login/                      # email + password → POST /api/auth/member-login
    set-password/               # redeem operator token (?token=) → reset confirm
    forgot-password/            # self-service reset request
    reset-password/             # reset confirm (?token=)
    (authed)/
      layout.tsx                # member AppShell + getMemberPageContext()
      dashboard/                # aggregating home (landing)
      savings/
        page.tsx                # accounts list
        [id]/page.tsx           # account detail + transactions
      shares/page.tsx           # share accounts list
      loans/
        page.tsx                # loans list
        [id]/page.tsx           # loan detail + schedule + statement
      fees/page.tsx             # fee assessments list
      profile/page.tsx          # read-only profile
  api/auth/
    member-login/route.ts
    member-refresh/route.ts
    member-logout/route.ts
    member-forgot-password/route.ts
    member-reset-password/route.ts
```

Server-to-server calls use the same `API_INTERNAL_URL` / `NEXT_PUBLIC_API_BASE_URL`
resolution the operator handlers use. Member login posts to the backend
`/member/auth/token` with `X-Tenant-Slug` (slug from the middleware header /
`sacco_tenant_slug` cookie, identical to operator login).

## Auth & session (contract C)

- Access token in memory; refresh token in a **new** httpOnly Secure
  SameSite=Strict cookie `sacco_refresh_member` (distinct from the operator
  `sacco_refresh_tenant`).
- New route handlers clone the `tenant-*` handlers but target `/member/auth/*`:
  - `member-login` → `POST /member/auth/token`, sets `sacco_refresh_member` +
    persists `sacco_tenant_slug`.
  - `member-refresh` → `POST /member/auth/refresh` (no rotation).
  - `member-logout` → `POST /member/auth/logout`, clears the cookie.
  - `member-forgot-password` → `POST /member/auth/password-reset/request`
    (always 204, anti-enumeration — the UI shows a generic "check with your
    SACCO" message).
  - `member-reset-password` → `POST /member/auth/password-reset/confirm`.
- `getMemberPageContext()` server helper: cookie → `/member/auth/refresh` →
  `/member/auth/me`, returning `{ member, slug, resources }`. Mirrors
  `getTenantPageContext()`; wrapped in React `cache()` for request dedup.
- **Set-password**: `/member/set-password?token=…` posts the token +
  new password to `member-reset-password` (same confirm endpoint, 24h operator
  token vs 15min self-service — the backend validates either). The operator
  delivers the link out of band until Phase 3 email. The token is read from the
  query string only, never logged, never persisted (contract F).

### Middleware gating

Members and operators share a tenant subdomain, so the existing middleware is
extended to keep the two audiences apart:

- A request to `/member/*` with no valid member session → redirect
  `/member/login`.
- A request to operator root routes with only a member session, or to
  `/member/*` with only an operator session, is not authorized — the page
  context helper redirects to the correct login. The API enforces this
  regardless via the `aud` claim (`member:<slug>` vs `tenant:<slug>`); the
  middleware/redirect rule is defense-in-depth and correct UX.
- The member refresh cookie (`sacco_refresh_member`) and operator cookie
  (`sacco_refresh_tenant`) are independent, so a browser could hold both; route
  groups + the page-context audience check determine which one applies.

## Shell

Add a `member` variant to `@sacco/ui` `AppShell`:

- Nav group: Dashboard, Savings, Shares, Loans, Fees, Profile.
- Suppressed for this variant: command palette trigger, impersonation banner;
  the notification bell renders its existing "coming soon" empty stub only.
- User menu: member full name + Sign out (calls `member-logout`).
- A Storybook story covers the `member` variant.

## Screens (all read-only)

| Screen | Route | Source |
|---|---|---|
| Dashboard | `/member/dashboard` | composes `member.{listSavings,listShares,listLoans,listFees}` into tiles (total savings balance, shares held + value, active loans + next due, outstanding fees) — each links to its section |
| Savings list | `/member/savings` | `GET /member/savings` |
| Savings detail | `/member/savings/[id]` | account + `GET /member/savings/{id}/transactions` |
| Shares list | `/member/shares` | `GET /member/shares` |
| Loans list | `/member/loans` | `GET /member/loans` |
| Loan detail | `/member/loans/[id]` | `GET /member/loans/{id}` + `/schedule` + `/statement` (JSON; no PDF in v1) |
| Fees list | `/member/fees` | `GET /member/fees` |
| Profile | `/member/profile` | `GET /member/auth/me` (from page context) |

- Lists render through the `@sacco/ui` `DataTable`; the dashboard uses
  cards/`<StatCard>` tiles (a table is overkill there).
- Money via `<Money>`, counts via `<Count>`, domain statuses via `<StatusBadge>`,
  dates via the date primitives. No raw `toLocaleString`.
- Server components fetch via the typed client (contract M); any client-side
  refresh uses TanStack Query.
- Cross-member access is impossible — every `/member/*` endpoint is scoped to the
  token's member server-side.

## api-client & schemas

- New `@sacco/api-client` resources:
  - `resources.memberAuth`: `login`, `refresh`, `logout`, `me`, `resetRequest`,
    `resetConfirm`.
  - `resources.member`: `listSavings`, `getSavingsTransactions`, `listShares`,
    `listLoans`, `getLoan`, `getLoanSchedule`, `getLoanStatement`, `listFees`.
  - `queryKeys.member.*`.
- Read **types are reused** from `@sacco/schemas` where they already exist
  (`SavingsAccountOut`, `SavingsTransactionOut`, `ShareAccountListItemOut`,
  `LoanOut`, `LoanInstallmentOut`, `LoanStatementOut`, `FeeAssessmentOut`,
  `MemberOut`). Add only thin types where a `/member/*` response shape differs
  from the operator equivalent (none expected; verify at build time).
- Member login uses the existing `loginSchema` (email + password) from
  `@sacco/schemas`; set-password/reset reuse the existing reset Zod schemas.

## Testing

- Vitest unit tests per page/component, mirroring Phase 3 patterns: mock
  `useAuth` + `next/navigation`, wrap client components in
  `QueryClientProvider` + `TenantCurrencyProvider`, drive `DataTable` via the
  `useTableUrlState` mock used by every existing table test.
- Route-handler tests clone the `tenant-*` handler tests (cookie set/clear,
  slug fallback, upstream error pass-through).
- `AppShell` `member` variant Storybook story.
- Typecheck + lint clean; all changes confined to `admin/` (+ this `docs/` spec).
- e2e deferred (consistent with prior phases).

## Out of scope (YAGNI)

- Any member mutation: profile edit, contact update, loan application,
  withdrawal request, transfers, share purchase/redeem.
- Member loan statement **PDF** (4a ships JSON statement only).
- Notifications feed (Phase 3 NullProvider; bell stays an empty stub).
- next-intl / i18n (portal-wide deferral).
- e2e browser flows.
- A member dashboard-stats backend endpoint — the dashboard composes existing
  list endpoints client-side.

## Follow-ups

- Phase 3 email will later deliver set-password / reset links instead of the
  out-of-band interim.
- Member mutations (applications, withdrawal requests) would be a later phase
  needing new backend endpoints + maker-checker — explicitly out of 4b.
