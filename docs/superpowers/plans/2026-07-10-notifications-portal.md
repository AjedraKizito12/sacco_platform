# Notifications Portal Surfaces (Increment 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The notification bell goes live for all three portal audiences (replacing the contract-O stub), each audience gets a preferences page, and platform admins get template + event screens — all under a "provider=null — real delivery disabled" banner.

**Architecture:** A presentational `NotificationBell` in `@sacco/ui` (popover, unread dot, item list, preferences link) fed by a portal client component that knows its audience and polls `GET .../notifications/me` via TanStack Query (60s refetch — the one sanctioned client-fetch widget, since the bell lives in the shell, not a page). Preferences render from a portal-side catalog mirror in `@sacco/schemas` (same pattern as StatusBadge status-maps): one toggle per (code × channel) relevant to the audience, `PUT` on change. Admin screens are standard server-component pages + DataTables over the platform admin API.

**Tech Stack:** Next.js 15 App Router, `@sacco/ui`/`api-client`/`schemas`, TanStack Query, vitest.

Branch: `feat/notifications-portal` (from `main`).

## Global Constraints

- Backend API is fixed (increment 1): self `GET ""` (`unread_only`, `limit`, `offset`), `POST /{id}/read` (204), `GET|PUT /preferences`; admin `GET/POST /templates`, `PATCH /templates/{id}`, `GET /events` (filters `recipient_user_id`, `event_code`, `status`), `POST /events/{id}/resend`. Audience prefixes: `/platform/notifications/me*`, `/notifications/me*`, `/member/notifications/me*`. **Zero new API endpoints.**
- Feed item wire shape: `{id, event_code, title, body, status, created_at, read_at}`. Preference: `{event_code, channel, enabled}`. Template: full row. Event admin row: `{id, event_code, recipient_kind, recipient_user_id, recipient_email, channels, context, scheduled_at, status, created_at}`.
- The portal catalog mirror lists the 13 event codes with a human label + audiences + toggleable channels (`email`, `in_app` — no code defaults to sms in v1). Adding a code = one row there (like status-maps, contract S's pattern).
- Preferences are default-enabled; the form treats a missing stored row as enabled and PUTs explicit rows only for codes the user has touched (send all currently-rendered toggles' states — the API upserts).
- Banner copy (fixed, roadmap): **"Notifications: provider=null — real delivery disabled"**, rendered on the platform templates, events, and settings/notifications pages.
- Bell: unread dot + count (from the fetched page, `unread_only=false`, limit 20), click item → mark read (204) + invalidate; footer link "Notification preferences" routes per audience (`/platform/settings/notifications`, `/notifications/preferences`, `/member/notifications/preferences`). Poll `refetchInterval: 60_000`.
- Contracts: dates via `<RelativeTime>`/`<FormattedDateTime>` (H); tables via `<DataTable>` (T); dialogs via `FormDialog`/`ConfirmDialog` (V); no maker-checker anywhere here (resend is a direct admin action → plain `ConfirmDialog`); statuses via `<StatusBadge>` — add a `notification_event` entity (`queued/sent/partial/failed/cancelled`) per contract S.
- `@sacco/ui` has **no Switch** — use the existing `Checkbox` for preference toggles.
- Platform pages gate with `requirePlatformPermission(user, "settings.read")` (same as the current settings stub); template edit / resend buttons are plain UI (API enforces admin — contract D).
- pnpm lint/typecheck/test clean; all list/table/form contracts per CLAUDE.md portal sections.

## File Structure

```
admin/packages/schemas/src/notifications.ts                (create: wire types + catalog + Zod)
admin/packages/schemas/src/__tests__/notifications.test.ts (create)
admin/packages/schemas/src/index.ts                        (modify: export)
admin/packages/api-client/src/resources/notifications.ts   (create)
admin/packages/api-client/src/resources/index.ts           (modify: register)
admin/packages/api-client/src/query-keys.ts                (modify: +notifications keys)
admin/packages/ui/src/components/NotificationBell/         (create: component + test + story + index)
admin/packages/ui/src/index.ts                             (modify: export)
admin/packages/ui/src/components/StatusBadge/status-maps.ts (modify: +notification_event)

admin/apps/portal/src/components/AppShellNotificationBell.tsx (create)
admin/apps/portal/src/components/AppShellHeader.tsx        (modify: swap stub)
admin/apps/portal/src/components/NotificationsProviderBanner.tsx (create)
admin/apps/portal/src/components/notifications/NotificationPreferencesForm.tsx (create)
admin/apps/portal/src/__tests__/notifications/*            (create: bell, preferences tests)

admin/apps/portal/app/platform/(authed)/settings/notifications/page.tsx (rewrite)
admin/apps/portal/app/(tenant-authed)/notifications/preferences/page.tsx (create)
admin/apps/portal/app/member/(authed)/notifications/preferences/page.tsx (create)
admin/apps/portal/app/platform/(authed)/notifications/templates/page.tsx (create + _components + tests)
admin/apps/portal/app/platform/(authed)/notifications/events/page.tsx    (create + _components + tests)
admin/apps/portal/src/components/shell/nav-config.tsx      (modify: platform Settings children)

CLAUDE.md                                                  (modify: Task 7)
```

---

### Task 1: `@sacco/schemas` — wire types, portal catalog, Zod

**Produces:** `NotificationFeedItemOut`, `NotificationPreferenceOut`, `NotificationTemplateOut`, `NotificationEventAdminOut` interfaces (mirror backend `app/core/notifications/schemas.py`); `NotificationAudience = "platform" | "tenant" | "member"`; `PORTAL_NOTIFICATION_CATALOG: readonly {code, label, audiences: NotificationAudience[], channels: ("email"|"in_app")[]}[]` (13 rows — audiences derived from the backend catalog: staff codes → platform+tenant, billing codes → tenant, member codes → member, password_reset/system_announcement → all); `catalogForAudience(audience)`; `notificationTemplatePatchSchema` (Zod: `subject_template/body_text/body_html/sms_body` optional strings, `is_active` optional boolean) + `NotificationTemplatePatchInput`.

- [ ] Failing test (`__tests__/notifications.test.ts`): catalog has exactly the 13 known codes, every row has a nonempty label + valid audiences/channels; `catalogForAudience("member")` returns exactly the member-visible codes (password_reset, system_announcement, member_activated, kyc ×2, loan ×2); patch schema accepts partial bodies and rejects `is_active: "yes"`.
- [ ] Implement per Produces; export from `index.ts`.
- [ ] `pnpm --filter @sacco/schemas test` green; lint/typecheck; commit `feat(schemas): notification wire types + portal catalog`.

---

### Task 2: api-client — notifications resource + query keys

**Produces:** `notifications(api)` registered in `buildResources` as `notifications`, with:

```ts
const SELF_PREFIX = {
  platform: "/platform/notifications/me",
  tenant: "/notifications/me",
  member: "/member/notifications/me",
} as const;

feed: (audience, query?) => GET(`${SELF_PREFIX[audience]}`)          // query: unread_only, limit, offset
markRead: (audience, id) => POST(`${SELF_PREFIX[audience]}/{id}/read` …)
getPreferences: (audience) / putPreferences: (audience, body: unknown[])
listTemplates: () / createTemplate: (body) / patchTemplate: (id, body)
searchEvents: (query?) / resendEvent: (id)
```

Query keys: `notifications.feed(audience)`, `notifications.preferences(audience)`, `notifications.templates()`, `notifications.events(filters?)`.

- [ ] Failing test (api-client `__tests__/query-keys-notifications.test.ts`): key shapes are stable arrays including the audience.
- [ ] Implement (same `as never` casting style as `member.ts`); register in `resources/index.ts`.
- [ ] `pnpm --filter @sacco/api-client test` green; lint/typecheck; commit `feat(api-client): notifications resource + query keys`.

---

### Task 3: `@sacco/ui` — presentational `NotificationBell` + StatusBadge entity

**Produces:** `NotificationBell` component:

```ts
interface NotificationBellItem { id: string; title: string; body: string; createdAt: string; readAt: string | null; }
interface NotificationBellProps {
  items: NotificationBellItem[];
  unreadCount: number;
  loading?: boolean;
  onItemClick?: (id: string) => void;      // consumer marks read
  onOpenPreferences?: () => void;
  emptyLabel?: string;                     // default "You're all caught up"
}
```

Popover (existing `Popover` primitives) triggered by the bell button; unread badge (small count chip when `unreadCount > 0`, `aria-label="Notifications (N unread)"`); item rows show title (bold when unread), body (line-clamped), `<RelativeTime>` timestamp; footer button "Notification preferences" when `onOpenPreferences` provided. Also: `status-maps.ts` gains `notification_event: {queued: neutral/info, sent: success, partial: warning, failed: destructive, cancelled: neutral}` (match the file's actual variant vocabulary).

- [ ] Failing vitest (`NotificationBell.test.tsx` beside the component, like `NotificationBellStub.test.tsx`): renders count badge; opening shows items; clicking an item fires `onItemClick(id)`; empty state shows `emptyLabel`; preferences button fires callback.
- [ ] Implement + Storybook story (default/unread/empty/loading variants, per portal-storybook-story conventions); export from `ui/src/index.ts` (keep the stub exported — Storybook still references it).
- [ ] `pnpm --filter @sacco/ui test` green; lint/typecheck; commit `feat(ui): NotificationBell + notification_event status badge`.

---

### Task 4: portal bell wiring (3 audiences)

**Produces:** `AppShellNotificationBell({ variant })` client component: `useAuth()` resources; `useTypedQuery(queryKeys.notifications.feed(variant), () => resources.notifications.feed(variant, { limit: 20 }), { refetchInterval: 60_000 })`; unwraps `{data}` results; `unreadCount = items.filter(i => !i.read_at).length`; `useTypedMutation` for `markRead` invalidating the feed key; `onOpenPreferences` → `router.push` per audience route (Global Constraints); renders `NotificationBell`. `AppShellHeader` replaces `<NotificationBellStub />` with `<AppShellNotificationBell variant={variant} />`.

- [ ] Failing vitest (`src/__tests__/notifications/AppShellNotificationBell.test.tsx`; mock `@/auth/use-auth` + `next/navigation`, QueryClientProvider wrapper): renders unread count from mocked feed; clicking an item calls `markRead` with the audience + id; preferences push per audience.
- [ ] Implement + header swap.
- [ ] `pnpm --filter @sacco/portal test -- AppShellNotificationBell` + existing header/shell tests green; lint/typecheck; commit `feat(portal): live notification bell for all three audiences`.

---

### Task 5: preferences form + three pages

**Produces:** `NotificationPreferencesForm({ audience, initial })` client component: rows = `catalogForAudience(audience)`; per row a `Checkbox` per channel (email / in-app), checked = stored row's `enabled` else `true`; any toggle change updates local state and a "Save preferences" button PUTs the **full rendered matrix** (`[{event_code, channel, enabled}, ...]`) via `useTypedMutation` (invalidates `notifications.preferences(audience)`), toast on success. Pages (server components fetching initial rows via the audience's page-context resources):
  - `platform/(authed)/settings/notifications/page.tsx` — rewrite: `NotificationsProviderBanner` + the form (`audience="platform"`). Keep `requirePlatformPermission(user, "settings.read")`.
  - `(tenant-authed)/notifications/preferences/page.tsx` — heading + form (`audience="tenant"`).
  - `member/(authed)/notifications/preferences/page.tsx` — heading + form (`audience="member"`).
  `NotificationsProviderBanner`: static informational strip with the fixed banner copy.

- [ ] Failing vitest (`src/__tests__/notifications/NotificationPreferencesForm.test.tsx`): member audience renders only member codes; unchecking email on one code and saving PUTs a matrix containing `{event_code, channel: "email", enabled: false}` for it and `enabled: true` elsewhere; stored `enabled: false` row renders unchecked.
- [ ] Implement; `pnpm --filter @sacco/portal test -- NotificationPreferencesForm`; lint/typecheck; commit `feat(portal): notification preferences pages (3 audiences) + provider banner`.

---

### Task 6: platform admin screens — templates + events

**Produces:**
- `/platform/notifications/templates`: server page (banner + DataTable via a client `TemplatesTable`: columns code, channel, locale, active `StatusBadge entity="notification_event"`? — no: active is boolean → render "Active"/"Inactive" text; updated `<FormattedDateTime>`). Row action "Edit" opens `FormDialog` (`react-hook-form` + `notificationTemplatePatchSchema`): textareas for subject/body_text/body_html/sms_body + active checkbox → `patchTemplate` mutation (invalidates `notifications.templates()`), toast, `router.refresh()`.
- `/platform/notifications/events`: server page (banner + client `EventsTable`): filters (status select, event_code select from catalog) via `useTableUrlState`-style URL params read in the server page and passed to `searchEvents`; columns event_code, recipient (kind + email), channels (joined), status `<StatusBadge entity="notification_event">`, created `<FormattedDateTime>`; row action "Resend" (disabled when status `queued`) → plain `ConfirmDialog` → `resendEvent` mutation + refresh.
- Nav: platform Settings children gain `{ label: "Notification templates", href: "/platform/notifications/templates" }` and `{ label: "Notification events", href: "/platform/notifications/events" }`.

- [ ] Failing vitests: `app/platform/(authed)/notifications/templates/__tests__/TemplatesTable.test.tsx` (edit dialog → patch called with changed body_text) and `.../events/__tests__/EventsTable.test.tsx` (resend confirm → resendEvent called; queued row's resend disabled).
- [ ] Implement pages/components/nav.
- [ ] `pnpm --filter @sacco/portal test -- "notifications"` green; lint/typecheck; commit `feat(portal): platform notification template + event admin screens`.

---

### Task 7: close-out

- [ ] Full admin suite: `pnpm lint && pnpm typecheck && pnpm test` (all packages green). Backend untouched — run `python -m pytest tests/core/notifications/ -q` as a sanity check only.
- [ ] CLAUDE.md:
  - Contract O rewrite: the bell is LIVE — `NotificationBell` (@sacco/ui) fed by `AppShellNotificationBell` polling the audience's `/…/notifications/me` feed every 60s; marking read via `POST .../{id}/read`; preferences at `/platform/settings/notifications`, `/notifications/preferences`, `/member/notifications/preferences`.
  - Notifications contracts section: append increment-3 bullet — portal catalog mirror lives in `admin/packages/schemas/src/notifications.ts` (adding an event code = backend catalog + template seed + one portal catalog row); banner copy fixed until real providers ship; admin template/event screens under `/platform/notifications/*` (settings.read to view; API enforces admin for writes); resend is a direct action (no maker-checker).
  - Roadmap table row 3 → **Done**; member portal section nav note (no new member nav item — preferences reached from the bell).
- [ ] Commit `docs(claude): notifications portal contracts (increment 3 — Phase 3 complete)`.

## Out of scope

- Real provider config UI (the settings page shows the banner + preferences only).
- Bulk announcements, template creation UI beyond the existing POST endpoint (list+edit only; create dialog omitted — seeds cover all codes; add when a real need appears).
- Per-user delivery history screen (`/users/[id]/notifications` from the roadmap) — the events search covers the support need for platform-scoped events; tenant-scoped event search is future work.
- WebSocket/live push — polling only.
