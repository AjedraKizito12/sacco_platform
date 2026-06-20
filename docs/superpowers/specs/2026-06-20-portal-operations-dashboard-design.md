# Portal — Operations Dashboard (SP18) Design

**Date:** 2026-06-20
**Phase:** 2 (Admin Portal), sub-plan 18
**Status:** Approved

## Goal

Build the platform **Operations Dashboard** at `/platform/operations` — a single
at-a-glance view of platform health (tenant counts, MRR, subscription mix,
outstanding invoices, pending approvals, active impersonations) backed by the
already-shipped `GET /platform/admin/dashboard-stats` aggregate endpoint. This
fills the "Operations" nav group, which currently 404s.

## Contract posture (pure client — zero new endpoints)

SP18 is a **pure client** of the existing API, matching SP12–SP16 (and unlike
SP17, which needed an additive backend change). The aggregate endpoint
`GET /platform/admin/dashboard-stats` shipped in Phase 1.7 (#9/#10). No backend
files are touched. All changes live under `admin/` (contracts B/N).

Everything already in place (verified against the real code):

- **api-client:** `resources.admin.dashboardStats()` (`resources/admin.ts`) —
  carries the `Promise<never>` wart, cast to `{ data?, error? }` per SP15/16.
- **queryKeys:** `admin.dashboardStats()` → `["admin", "dashboardStats"]`.
- **@sacco/ui:** `StatusBadge` (entities `tenant`, `subscription`), `Money`
  (currency registry, 7 codes), `Count` (tabular numerals), `RelativeTime`
  (exported from the FormattedDate module), `Card`. No chart primitives exist.
- **server helpers:** `getPlatformPageContext()` + `requirePlatformPermission()`.

New in this sub-plan: the `DashboardStatsOut` type in `@sacco/schemas` (none
exists yet), an `operations.read` permission key, two small single-use
presentational components, and the page itself.

## Backend facts (authoritative)

`GET /platform/admin/dashboard-stats` — gate **`CurrentAdmin`** (not support).
`DashboardStatsOut` (`app/platform_/admin/schemas.py`):

| Field | Type | Meaning |
|-------|------|---------|
| `tenants` | `dict[str, int]` | counts by `tenants.status` |
| `subscriptions` | `dict[str, int]` | counts by `subscriptions.status` |
| `mrr` | `dict[str, Decimal]` | normalised monthly revenue per currency (active+trialing × plan.base_price) |
| `invoices_outstanding` | `dict[str, int]` | unpaid-invoice counts by status (issued / partial / overdue) |
| `invoices_amount_outstanding` | `dict[str, Decimal]` | sum(amount_total − amount_paid) per currency for that set |
| `approvals_pending` | `int` | pending platform-scoped approval_requests |
| `active_impersonations` | `int` | non-ended/revoked/expired support_impersonations |
| `last_updated` | `datetime` | generation timestamp (freshness hint) |

Over the wire, `Decimal` fields arrive as JSON **strings** (FastAPI serialises
`Decimal` as a string). The hand-written TS type models `mrr` /
`invoices_amount_outstanding` values as `string` (same as `Money`'s `amount`
prop everywhere else in the portal).

The endpoint caches its response in Redis for **60 seconds** and **forbids any
cache-bypass query parameter** (CLAUDE.md platform_ contract). It deliberately
returns `last_updated` so the portal can show freshness. When Redis is down it
recomputes (documented degraded behaviour).

## Decision 1 — Permission gating: admin

The endpoint is `CurrentAdmin`. Add `operations.read → "admin"` to
`apps/portal/src/auth/permissions.ts` and call
`requirePlatformPermission(user, "operations.read")` in the page. The sidebar
"Operations" link is gated on the same key. A support user hitting the route
redirects to `/permission-denied` rather than rendering a screen the API would
403. UI gating is UX-only; the API enforces (contract D).

## Decision 2 — Refresh UX: static fetch + last-updated + manual refresh

Because the endpoint caches 60s and forbids cache-bypass, polling would just
re-serve the same cached payload. So:

- Server component fetches once on load.
- A header line renders `Last updated <RelativeTime value={last_updated} />`.
- A **Refresh** button (client component) calls `router.refresh()` to re-run the
  server fetch. Within the 60s window it returns the cached snapshot; after, a
  fresh one. No auto-polling. No `force_refresh` (the contract forbids it).

## Layout

```
Operations                                   Last updated 12s ago  [Refresh]

┌── Tenants ──┬── MRR ──────┬── Pending ──┬── Active ───┐
│   42        │ USh 4.2M    │ approvals   │ imperson.   │
│ 38 active   │ +KES 180k   │    3        │    1        │
└─────────────┴─────────────┴─────────────┴─────────────┘

┌── Tenants by status ──┐  ┌── Subscriptions by status ──┐
│ ● active        38    │  │ ● active      35            │
│ ● suspended      3    │  │ ● trialing     4            │
│ ● provisioning   1    │  │ ● past_due     2            │
└───────────────────────┘  └─────────────────────────────┘

┌── Outstanding invoices ───────────────────────────────┐
│ issued 12 · partial 3 · overdue 5    UGX 8.4M · KES 1M │  → /platform/billing/invoices
└───────────────────────────────────────────────────────┘
```

### Components (single-use, in the page's `_components/`, not `@sacco/ui`)

- **`<StatCard label value sub? href? />`** — one headline tile. `value` and
  `sub` are `ReactNode` so callers pass `<Count>` / `<Money>` directly. When
  `href` is set the whole card is a `next/link`.
- **`<StatusBreakdown title entity counts />`** — a `Card` titled `title`,
  rendering each `[status, count]` of the `counts` dict as
  `<StatusBadge entity={entity} status={status} />` + `<Count value={count} />`.
  `entity` is `"tenant"` or `"subscription"`. Rows sorted by count desc, then
  status asc, for stable ordering. Renders an empty hint ("No data") when the
  dict is empty.

These are single-use and presentational, so they live beside the page — not in
`@sacco/ui` (which is reserved for cross-screen primitives). They take plain
props and can be unit-tested in isolation.

### Top-row tiles (exact mapping)

1. **Tenants** — `value`: `<Count>` of `sum(tenants.values())`; `sub`:
   `<Count value={tenants.active ?? 0} /> active`.
2. **MRR** — `value`: one `<Money>` per currency in `mrr` (stacked; the first is
   the headline, the rest are smaller lines). Empty → "—".
3. **Pending approvals** — `value`: `<Count value={approvals_pending} />`;
   `href`: `/platform/approvals?status=pending`.
4. **Active impersonations** — `value`:
   `<Count value={active_impersonations} />`. No link (no impersonations-list
   screen yet — deferred).

### Money & counts (contracts H/R)

All amounts render through `<Money amount currency />`; all integers through
`<Count value />`. No raw `toLocaleString`, no `<input type=number>`. MRR and
invoice amounts iterate their per-currency dicts.

## Error & empty states

- **Fetch error** (`error` set or `data` undefined): render a simple error card
  ("Couldn't load operations stats") with the Refresh button. Do not `notFound()`
  — the route is valid; the data fetch failed.
- **Empty dicts** (e.g. no outstanding invoices): the outstanding-invoices card
  shows "No outstanding invoices"; `StatusBreakdown` shows "No data". Scalars
  default to `0`.

## File structure

**`@sacco/schemas`**
- Modify `packages/schemas/src/platform.ts` — add `DashboardStatsOut` interface
  (hand-written; `Decimal` dicts as `Record<string, string>`).
- Modify `packages/schemas/src/__tests__/platform.test.ts` — a light type/shape
  assertion if the file pattern warrants (Out types are interfaces; if existing
  Out types aren't unit-tested, skip — match the file's convention).

**`@sacco/portal`**
- Modify `apps/portal/src/auth/permissions.ts` — add `"operations.read": "admin"`.
- Create `app/platform/(authed)/operations/page.tsx` — server component.
- Create `app/platform/(authed)/operations/_components/StatCard.tsx`.
- Create `app/platform/(authed)/operations/_components/StatusBreakdown.tsx`.
- Create `app/platform/(authed)/operations/_components/RefreshButton.tsx` —
  `"use client"`, `router.refresh()`.
- Modify the sidebar component — gate/add the "Operations" nav link
  (verify the real sidebar file + whether the link already exists before editing).

**Tests** under `apps/portal/src/__tests__/platform-operations/`:
`StatCard`, `StatusBreakdown` (badge + count render, sort, empty), and a page
smoke if feasible without full server context (otherwise rely on the component
tests + typecheck/lint, as SP16/17 list pages do).

## Permission mapping (authoritative)

| Action | Backend gate | Portal gate |
|--------|--------------|-------------|
| View `/platform/operations` | `CurrentAdmin` | `operations.read` (admin) |

## Out of scope (deferred)

- **Charts / time-series** — no chart primitives exist in `@sacco/ui`; building
  them (forked, tokenised, Storybook'd) is its own sub-plan. v1 is tiles +
  breakdown lists.
- **Tenant-level operations**, **settings** — separate nav groups / sub-plans.
- **Active-impersonations drill-down** — no impersonations-list screen yet.
- **Auto-refresh / websockets** — the 60s server cache makes polling pointless.
- **e2e + next-intl** — portal-wide deferrals (raw English), matching SP12–17.

## Testing strategy

- **Portal:** Vitest + Testing Library. `StatCard` (label/value/sub render, link
  when `href` set). `StatusBreakdown` (renders a `StatusBadge` + `Count` per
  entry, sort order, empty-state). Per-package `test` + `typecheck` + `lint`
  green; all changes under `admin/`.
