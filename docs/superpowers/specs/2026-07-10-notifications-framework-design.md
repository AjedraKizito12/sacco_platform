# Notifications Framework — Design

**Date:** 2026-07-10
**Status:** Approved (brainstorming), pending implementation plan
**Phase:** SaaS launch Phase 3 (roadmap: `docs/superpowers/plans/saas-launch-roadmap.md` §Phase 3)

## Summary

A single in-app abstraction for "notify a user about X" so call sites exist today
(password reset, maker-checker alerts, billing reminders, KYC/loan decisions, system
events) and route to real email/SMS providers later without touching the call sites.
v1 ships `NullNotificationProvider` (default) and `LogNotificationProvider` only —
no real delivery. The `in_app` channel is first-class from day one: it powers the
portal notification bell (portal contract O) with no provider at all.

Built in three increments, each its own spec-checked PR:

1. **Core framework** — tables + migrations, `NotificationService.publish`,
   providers, dispatcher, beat jobs, template seeds, self + platform-admin HTTP APIs.
2. **Call-site wiring** — the 13 event codes published from IAM, maker-checker,
   billing, members, and credit.
3. **Portal surfaces** — bell feed for all three audiences, preferences page,
   platform template/event screens, "provider=null" banner.

## Decisions (from brainstorming)

- **Three increments, backend first** (mirrors the KYC / member-self-service cadence).
- **`in_app` is first-class in v1.** An in_app "delivery" is the `notification_events`
  row itself (with a `read_at` flag) served by `GET /notifications/me`. The feed IS
  the delivery; no provider involved.
- **Three recipient kinds:** `platform_user | tenant_user | member`. Members get
  four event codes of their own (KYC decision ×2, loan decision ×2) on top of the
  roadmap's nine.
- **Dispatch flow:** `notification_events` itself is the notification outbox.
  `NotificationService.publish()` writes one row (status `queued`) inside the
  **caller's transaction** — atomic with the business change, same guarantee as
  `EventPublisher`. The Celery beat job `dispatch_pending_notifications` (every 30s)
  polls due queued rows and dispatches. There is **no RabbitMQ hop** for directly
  published notifications; this satisfies the CLAUDE.md Phase 3 note ("publish
  writes to outbox" — the event row is the outbox) without processing every
  notification twice. Derived events that react to existing domain events (e.g.
  `member_activated`) are created in increment 2 by a small consumer reading the
  real outbox with the established `processed_events` guard.
- **No bulk-send endpoint in v1.** `system_announcement` exists in the taxonomy and
  templates, but the operator-facing bulk-send (and its maker-checker requirement)
  is deferred until a real need; that also defers the spam threat.
- **Preferences enforced at dispatch time**, default enabled (no rows needed).
  Template versioning deferred (updated_at only). Rate limiting designed for
  (dedupe_key), enforced fully in v2.

## Event taxonomy (13 codes)

| Code | Recipient kind(s) | Increment-2 call site |
|---|---|---|
| `password_reset` | all three | IAM reset_request / admin reset (token delivery stays manual in v1 — the notification is the *notice*, never carries the token) |
| `maker_checker_pending` | platform_user, tenant_user | `ApprovalService.submit` |
| `maker_checker_approved` | platform_user, tenant_user | `ApprovalService.approve` (final approval) |
| `maker_checker_rejected` | platform_user, tenant_user | `ApprovalService.reject` |
| `invoice_issued` | tenant_user (admins) | `InvoiceService.generate_for_subscription` |
| `invoice_overdue` | tenant_user (admins) | billing dunning beat |
| `subscription_suspended` | tenant_user (admins) | `SubscriptionService.transition_to_suspended` |
| `system_announcement` | any | (no v1 call site — taxonomy + template only) |
| `member_activated` | member | outbox consumer on the member status-change event |
| `kyc_submission_approved` | member | `KycReviewService.approve` |
| `kyc_submission_rejected` | member | `KycReviewService.reject` |
| `loan_application_approved` | member | `credit.approve_application` executor |
| `loan_application_rejected` | member | `LoanApplicationService.reject` |

Security note: notification context/templates never contain secrets (reset tokens,
passwords) or sensitive PII (national IDs). The template `variables` JSON schema is
the allow-list; `publish()` rejects context keys not in it.

## Data model

`app/core/notifications/models.py`. Templates in the **platform schema only**;
events / deliveries / preferences exist in **both** schemas (platform-scoped rows for
platform users; tenant-scoped rows for tenant users and members, resolved via
`search_path` per project convention). Same dual-model pattern as outbox/maker-checker
(shared mixin, `Platform*` model with `{"schema": "platform"}`, tenant model without).

```
notification_templates            (platform schema only)
  id uuid pk
  code text not null              -- one of the 13 event codes
  channel text not null           -- 'email'|'sms'|'in_app'
  locale text not null default 'en'
  subject_template text           -- Jinja2; email + in_app title
  body_html text                  -- Jinja2; email only
  body_text text                  -- Jinja2; email fallback + in_app body
  sms_body text                   -- Jinja2; sms only
  variables jsonb not null        -- allow-listed context keys w/ descriptions
  is_active bool not null default true
  created_at, updated_at
  unique (code, channel, locale)

notification_events               (both schemas)
  id uuid pk
  event_code text not null
  recipient_kind text not null    -- 'platform_user'|'tenant_user'|'member'
  recipient_user_id uuid not null
  recipient_email text            -- denormalised snapshot
  recipient_phone text
  channels text[] not null        -- requested channels
  context jsonb not null
  dedupe_key text                 -- nullable; unique when present (idempotent publish)
  scheduled_at timestamptz not null default now()
  status text not null default 'queued'  -- queued|sent|partial|failed|cancelled
  read_at timestamptz             -- in_app: bell read marker
  created_at, updated_at
  unique (dedupe_key); index (status, scheduled_at); index (recipient_kind, recipient_user_id, created_at)

notification_deliveries           (both schemas)
  id uuid pk
  notification_event_id uuid not null fk
  channel text not null
  provider text not null          -- 'null'|'log'|future ids
  attempt int not null default 1
  status text not null            -- 'sent'|'failed'
  external_id text
  error_message text
  sent_at timestamptz not null default now()

notification_preferences          (both schemas)
  id uuid pk
  recipient_kind text not null
  user_id uuid not null
  event_code text not null
  channel text not null
  enabled bool not null default true
  unique (recipient_kind, user_id, event_code, channel)
```

Events are append-mostly: status/read_at update in place; deliveries are append-only
attempts. Purge job deletes terminal events older than 180 days.

## Components (`app/core/notifications/`)

- **`catalog.py`** — the 13 event codes + per-code default channels + allowed
  recipient kinds. Pure, no I/O (like `app/core/kyc/catalog.py`).
- **`service.py` — `NotificationService.publish(...)`** (async, takes the caller's
  session):
  ```python
  publish(
      *, event_code: str,
      recipient_kind: str, recipient_user_id: UUID,
      recipient_email: str | None, recipient_phone: str | None,
      context: dict[str, Any],
      channels: list[str] | None = None,   # None = catalog defaults
      scheduled_at: datetime | None = None,
      dedupe_key: str | None = None,
  ) -> NotificationEvent
  ```
  Validates code against the catalog and context keys against the template
  `variables` allow-list; idempotent on `dedupe_key` (returns the existing row).
  Never raises for "recipient has no email" — channel filtering happens at
  dispatch. Publish failures must never break the business transaction beyond
  validation errors (a bad call site is a bug; surfacing it in tests is the point).
- **`providers/base.py`** — `EmailProvider.send(to, subject, html, text) -> str|None`
  and `SMSProvider.send(to, body) -> str|None` (returns external id); raising =
  failure. **`providers/null.py`**, **`providers/log.py`** (structlog line; the
  delivery row records `provider='log'`). Selected via settings
  `NOTIFY_EMAIL_PROVIDER` / `NOTIFY_SMS_PROVIDER` (default `null`). Real providers
  (Brevo/SES/Africa's Talking) are future work; no stub classes needed in v1.
- **`renderer.py`** — sandboxed, autoescaped Jinja2 (`SandboxedEnvironment`)
  rendering DB template bodies with the event context. Missing template for a
  requested channel = that channel is skipped with a failed delivery row
  (`error_message='no active template'`), not a crash.
- **`dispatcher.py`** — per event: resolve channels = requested ∩ preference-enabled;
  `in_app` succeeds by definition and writes **no** delivery row (the event row is
  the feed item and the record); email/sms render + provider send, one delivery row
  per attempt. Event status: all resolved channels ok → `sent`, some → `partial`,
  none → `failed`; zero resolved channels (all preference-disabled) → `sent`
  (nothing owed). Preference-disabled channels produce no delivery row.
- **`beat.py`** — `dispatch_pending_notifications` (30s; platform schema + every
  active tenant schema, same iteration pattern as existing beats; row-locked
  `FOR UPDATE SKIP LOCKED` so overlapping runs never double-send),
  `retry_failed_notifications` (5 min; re-dispatch failed deliveries, max 3
  attempts, exponential backoff via `scheduled_at`), `purge_old_notification_events`
  (daily, 180 days).
- **`api.py`** — two routers:
  - Self (`/notifications/me*`), one set of handlers per audience dep
    (`CurrentPlatformUser` / `CurrentTenantUser` / `CurrentMember` — resolved by a
    small internal helper so paths stay identical): `GET /notifications/me`
    (paginated feed, `unread_only=`), `POST /notifications/me/{id}/read`,
    `GET|PATCH /notifications/me/preferences`. Cross-recipient access → 404.
  - Platform admin (`/platform/notifications/*`): templates list/create/patch
    (`CurrentAdmin`), events search by user/code/status (`CurrentSupport`),
    `POST /platform/notifications/events/{id}/resend` (`CurrentAdmin`, re-queues).
- **Template seeds** — migration-seeded rows for every (code, channel) pair the
  catalog declares, locale `en`. Editing is data, not code, thereafter.

## Error handling

- Provider raises → delivery row `failed` + error_message; event `partial`/`failed`;
  retry beat picks it up (≤3 attempts).
- Template render error → treated like provider failure (never crashes the beat run).
- Unknown event code / disallowed context key at publish → `ValueError` (bug at the
  call site; caught by tests, 500 in production rather than silent drop).
- Dispatcher is idempotent per event: an event is claimed by exactly one beat run
  (`SKIP LOCKED`) and moves out of `queued` in the same transaction as its
  delivery rows.

## Testing (TDD per conventions)

- Catalog completeness: every code has defaults + seeded templates for each channel.
- `publish`: validation, dedupe_key idempotency, snapshot fields, transactionality.
- Dispatcher: preference filtering, in_app success without provider, log provider
  writes delivery row, partial/failed statuses, missing-template skip.
- Beat: SKIP LOCKED single-claim, retry backoff and attempt cap, purge window.
- API: per-audience auth matrix (stub headers), cross-recipient 404, read marker,
  preferences round-trip, admin template CRUD + events search + resend.
- Increment 2: one test per call site asserting the event row (code, recipient,
  context) lands in the same transaction as the business change.

## Out of scope (v1)

- Real email/SMS providers and their config UI; delivery webhooks.
- Bulk `system_announcement` sending (and its maker-checker flow).
- Template versioning; per-tenant template overrides; locales beyond `en`.
- Per-user rate limiting beyond dedupe_key (designed, enforced v2).
- Notification digests, quiet hours, web push.

## Contract changes (CLAUDE.md, shipped with increment 1)

- `NotificationService.publish()` is the ONLY way to create `notification_events`
  rows; it writes in the caller's transaction (the event row is the notification
  outbox — no RabbitMQ hop for direct publishes).
- Notifications never carry secrets (reset tokens, passwords) or sensitive PII;
  the template `variables` allow-list is enforced at publish time.
- Providers are selected via settings; `null` is the default everywhere. Adding a
  real provider must not change any call site.
- The dispatcher/beat is the only code that flips event status; the self API only
  touches `read_at` and preferences.
