# Notifications Call-Site Wiring (Increment 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every event code in the catalog publishes from its real trigger: password resets, maker-checker lifecycle, billing (invoice issued/overdue, subscription suspended), member activation, KYC decisions, and loan decisions.

**Architecture:** Two publication modes per the spec. **Direct** (same session/transaction as the business change): IAM reset services, `ApprovalService`, `KycReviewService`, credit executor/service. **Derived** (at-least-once consumers with `processed_events` guards + `dedupe_key`): `member_activated` from the existing tenant-outbox `MemberActivated` event, and the three billing codes from three NEW platform-outbox events (`BillingInvoiceIssued` / `BillingInvoiceOverdue` / `BillingSubscriptionSuspended`) — needed because billing runs in platform transactions while its recipients (tenant admins) read tenant-schema feeds; a consumer bridges the schemas.

**Tech Stack:** Existing `NotificationService.publish` / `EventPublisher` / Celery beat / pytest patterns. No new tables, no migrations, no portal changes.

Branch: `feat/notifications-callsites` (from `main`).

## Global Constraints

- Every publish goes through `NotificationService.publish()` in the caller's session. Direct call sites publish inside the same transaction as the business change (spec contract).
- Notifications never carry secrets or sensitive PII. The **password_reset notification is a NOTICE with empty context — the token never appears** (context `{}` matches the seeded empty allow-list).
- Anti-enumeration is untouched: `reset_request` still always returns `None`; the publish happens only inside the user-exists branch (invisible to the caller).
- Consumers use the module-consumer pattern (`app/modules/fees/consumer.py`): `processed_events` guard per `consumer_name`, at-least-once, and every consumer publish carries a `dedupe_key` so redelivery cannot double-notify. Consumer names: `notifications.member_consumer` (tenant outboxes), `notifications.billing_consumer` (platform outbox).
- Maker-checker recipients: `pending` → all eligible checkers except the maker (tenant scope: active `TenantUser` rows with `impersonation_id IS NULL`; platform scope: active `PlatformUser` with role `admin`/`superuser`); `approved`(final)/`rejected` → the maker. **If the maker id is not a staff row (e.g. a member-submitted loan application), skip silently** — the member is notified by the credit code paths instead.
- Credit publishes member notifications with `channels=["in_app"]` only — the credit module may not read member rows (cross-module rule), so it has no email; the in_app feed needs none. KYC/members-module publishes include the member's email (same-module access).
- A notification failure must never break the business operation beyond `ValueError`s that indicate call-site bugs (wrong code/kind/context key) — those are the tests' job to catch.
- Dedupe keys (fixed): `mc_pending:{request_id}:{user_id}`, `mc_approved:{request_id}`, `mc_rejected:{request_id}`, `member_activated:{outbox_event_id}`, `{billing_event_type}:{outbox_event_id}:{user_id}`, `kyc_approved:{submission_id}`, `kyc_rejected:{submission_id}`, `loan_approved:{application_id}`, `loan_rejected:{application_id}`.
- Context keys must match the seeded template `variables` exactly (publish rejects unknown keys): maker_checker_pending `{operation_type, requested_by_label}`, maker_checker_approved `{operation_type}`, maker_checker_rejected `{operation_type, reason}`, invoice_issued `{invoice_number, amount, currency, due_date}`, invoice_overdue `{invoice_number, amount, currency}`, subscription_suspended `{}`, member_activated `{full_name, member_number}`, kyc_submission_approved `{}`, kyc_submission_rejected `{reason}`, loan_application_approved `{amount}`, loan_application_rejected `{reason}`, password_reset `{}`.
- Tests that publish non-empty contexts must seed templates first (`seed_default_templates`); empty-context publishes pass without seeds.
- ruff + mypy (strict) clean; run `tests/modules/credit/` separately from `tests/core/` (known order flake).

## File Structure

```
app/modules/iam/platform_auth/service.py       (modify: reset_request publish)
app/modules/iam/tenant_auth/service.py         (modify: reset_request publish)
app/modules/iam/member_auth/service.py         (modify: reset_request publish)
app/platform_/tenant_users_admin/service.py    (modify: initiate_password_reset publish)
tests/modules/iam/test_reset_notifications.py  (create)

app/modules/maker_checker/notifications.py     (create: recipient resolution + notify fns)
app/modules/maker_checker/service.py           (modify: 3 hook calls)
tests/modules/maker_checker/test_notifications.py (create)

app/platform_/billing/services/invoice_service.py      (modify: 2 outbox events)
app/platform_/billing/services/subscription_service.py (modify: 1 outbox event)
tests/platform_/billing/test_billing_domain_events.py  (create)

app/platform_/billing/consumer.py              (create: billing notifications consumer)
app/modules/members/consumer.py                (create: member_activated consumer)
app/workers/celery_app.py                      (modify: 2 includes + 2 beat entries)
tests/platform_/billing/test_notifications_consumer.py (create)
tests/modules/members/test_member_activated_consumer.py (create)

app/modules/members/kyc_submissions.py         (modify: approve/reject publish)
tests/modules/members/test_kyc_notifications.py (create)

app/modules/credit/executors.py                (modify: approve executor publish)
app/modules/credit/services/application.py     (modify: reject publish)
tests/modules/credit/test_loan_decision_notifications.py (create)

CLAUDE.md                                      (modify: Task 8)
```

---

### Task 1: password_reset notices (3 self-service flows + admin tenant-user reset)

**Files:**
- Modify: `app/modules/iam/platform_auth/service.py` (`reset_request`), `app/modules/iam/tenant_auth/service.py` (`reset_request`), `app/modules/iam/member_auth/service.py` (`reset_request`), `app/platform_/tenant_users_admin/service.py` (`initiate_password_reset`)
- Test: `tests/modules/iam/test_reset_notifications.py` (create)

**Interfaces:**
- Consumes: `NotificationService.publish` (existing). Each service already holds the right session (`self._db` platform / tenant).
- Produces: one `password_reset` notification per successful token issuance. Recipient kind matches the audience; `recipient_email=user.email` (member: `member.email`); `context={}`; default channels; no dedupe key (each request is a fresh notice).

- [ ] **Step 1: Write the failing tests** — `tests/modules/iam/test_reset_notifications.py`. Fixture pattern: session factory + `SET LOCAL search_path` (copy from an existing IAM service test, honoring the `feedback_test_patterns` memory: `async_sessionmaker` + commit + cleanup of `notification_events` both schemas, `platform_users`/`tenant_users`/`members` rows it seeds, and audit rows). Four tests:
  - platform reset_request with existing user → one `platform.notification_events` row (`event_code='password_reset'`, `recipient_kind='platform_user'`, `recipient_user_id=user.id`, `recipient_email=user.email`); unknown email → returns None, zero rows.
  - tenant reset_request → tenant-schema row, kind `tenant_user`.
  - member reset_request (eligible member) → tenant-schema row, kind `member`.
  - `TenantUsersAdminService.initiate_password_reset` → tenant-schema row for that user.
  Seed users the way each service's existing tests do (hash_password for credentials where the service requires them; member needs `portal_enabled=True, status='active', hashed_password` set).

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/modules/iam/test_reset_notifications.py -q` → rows missing (0 != 1).

- [ ] **Step 3: Implement** — in each user-exists branch, AFTER the token is made and audit written, add (adjusting the session attribute name per service):

```python
        from app.core.notifications.service import NotificationService  # noqa: PLC0415

        await NotificationService(self._db).publish(
            event_code="password_reset",
            recipient_kind="platform_user",  # tenant_user / member per service
            recipient_user_id=user.id,
            recipient_email=user.email,
            context={},
        )
```

  (member service: `recipient_kind="member"`, email from the member row; tenant_users_admin service: `recipient_kind="tenant_user"`.) The publish shares the caller's transaction — no commit here.

- [ ] **Step 4: Verify pass** — the new file + existing IAM suites: `python -m pytest tests/modules/iam/ -q` (green; existing reset tests unaffected — publishing adds rows nothing asserts against).

- [ ] **Step 5: Lint, typecheck, commit** — `feat(notifications): password_reset notices from all four reset flows`.

---

### Task 2: maker-checker lifecycle notifications

**Files:**
- Create: `app/modules/maker_checker/notifications.py`
- Modify: `app/modules/maker_checker/service.py` (3 hooks)
- Test: `tests/modules/maker_checker/test_notifications.py` (create)

**Interfaces:**
- Produces `app/modules/maker_checker/notifications.py`:
  - `async notify_pending(session, request) -> None` — resolve eligible checkers (per Global Constraints), publish `maker_checker_pending` to each with `dedupe_key=f"mc_pending:{request.id}:{user.id}"`, context `{"operation_type": request.operation_type, "requested_by_label": <maker email or str(requested_by)>}`.
  - `async notify_decided(session, request, *, approved: bool, reason: str | None) -> None` — resolve the maker among staff rows; if absent, return; else publish `maker_checker_approved` (context `{"operation_type": ...}`) or `maker_checker_rejected` (context adds `"reason": reason or ""`), dedupe `mc_approved:{id}` / `mc_rejected:{id}`.
  - Scope detection via `session.sync_session.info.get("is_platform", False)`; staff models: `TenantUser` (`app.modules.iam.tenant_users.models`) and `PlatformUser` (`app.platform_.models`).
- Hooks in `ApprovalService`: end of `submit()` (before return) → `notify_pending`; in `approve()` inside the `count >= request.required_approvals` branch after `_execute` → `notify_decided(approved=True, reason=None)`; in `reject()` after the status flip → `notify_decided(approved=False, reason=reason)`.

- [ ] **Step 1: Write the failing tests** — `tests/modules/maker_checker/test_notifications.py`. Register a no-op executor:

```python
from app.modules.maker_checker.registry import approval_executor

@approval_executor("test.notify_noop")
async def _noop(session, payload):  # noqa: ANN001, ANN202
    return {"ok": True}
```

  (Check the actual registry import path used by `app/modules/credit/executors.py` and match it.) Seed templates (`seed_default_templates`) + three tenant users (maker, checker, bystander) in `tenant_test`. Tests:
  - `submit` → `maker_checker_pending` rows for checker+bystander, none for the maker; dedupe rows carry the fixed keys.
  - `approve` to quorum (checker approves, required_approvals=1) → one `maker_checker_approved` row to the maker.
  - `reject` with reason → one `maker_checker_rejected` row to the maker, context includes the reason.
  - maker id that is no staff row (random UUID) → submit/approve/reject run clean, pending rows still go to all staff, no decided row, no exception.
  - platform scope: `is_platform` session + two `PlatformUser`s (roles admin + support): pending goes only to the admin (support tier is not an eligible checker).

- [ ] **Step 2: Run to verify failure** — module missing.

- [ ] **Step 3: Implement** `notifications.py`:

```python
"""Maker-checker lifecycle notifications (spec: notifications increment 2).

pending -> all eligible checkers except the maker; approved/rejected -> the
maker. A maker that is not a staff row (member-submitted operations) is
skipped silently — member-facing notices come from the owning module.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notifications.service import NotificationService


async def _staff(session: AsyncSession) -> tuple[str, list[Any]]:
    if session.sync_session.info.get("is_platform", False):
        from app.platform_.models import PlatformUser  # noqa: PLC0415

        rows = list(
            (
                await session.execute(
                    select(PlatformUser).where(
                        PlatformUser.is_active.is_(True),
                        PlatformUser.role.in_(("admin", "superuser")),
                    )
                )
            ).scalars()
        )
        return "platform_user", rows
    from app.modules.iam.tenant_users.models import TenantUser  # noqa: PLC0415

    rows = list(
        (
            await session.execute(
                select(TenantUser).where(
                    TenantUser.is_active.is_(True),
                    TenantUser.impersonation_id.is_(None),
                )
            )
        ).scalars()
    )
    return "tenant_user", rows


async def notify_pending(session: AsyncSession, request: Any) -> None:
    kind, staff = await _staff(session)
    maker = next((u for u in staff if u.id == request.requested_by), None)
    label = maker.email if maker is not None else str(request.requested_by)
    svc = NotificationService(session)
    for user in staff:
        if user.id == request.requested_by:
            continue
        await svc.publish(
            event_code="maker_checker_pending",
            recipient_kind=kind,
            recipient_user_id=user.id,
            recipient_email=user.email,
            context={"operation_type": request.operation_type, "requested_by_label": label},
            dedupe_key=f"mc_pending:{request.id}:{user.id}",
        )


async def notify_decided(
    session: AsyncSession, request: Any, *, approved: bool, reason: str | None
) -> None:
    kind, staff = await _staff(session)
    maker = next((u for u in staff if u.id == request.requested_by), None)
    if maker is None:
        return  # member-submitted (or departed) maker — owning module notifies
    if approved:
        code, context, key = (
            "maker_checker_approved",
            {"operation_type": request.operation_type},
            f"mc_approved:{request.id}",
        )
    else:
        code, context, key = (
            "maker_checker_rejected",
            {"operation_type": request.operation_type, "reason": reason or ""},
            f"mc_rejected:{request.id}",
        )
    await NotificationService(session).publish(
        event_code=code,
        recipient_kind=kind,
        recipient_user_id=maker.id,
        recipient_email=maker.email,
        context=context,
        dedupe_key=key,
    )
```

  Hooks in `service.py` (import at top of function to avoid cycles):

```python
        from app.modules.maker_checker.notifications import notify_pending  # noqa: PLC0415
        await notify_pending(self._session, request)
```

  and the two `notify_decided` calls per the Interfaces block.

- [ ] **Step 4: Verify pass** — `python -m pytest tests/modules/maker_checker/ -q` (whole module green — many suites exercise ApprovalService; the hooks must not break them. If a pre-existing suite lacks templates and a hook publishes a non-empty context, that's fine — publish only validates PROVIDED keys against the allow-list, and with no templates the allow-list is empty → non-empty contexts would raise. **Therefore: hooks must tolerate this**: wrap each notify call in `try/except ValueError` with a structlog warning? NO — instead, `_allowed_context_keys` returning an empty set means no templates exist; treat "no templates for the code at all" as allow-all: change `NotificationService._allowed_context_keys` to return `None` when NO active template rows exist for the code, and skip validation in that case. That keeps strict validation wherever templates are seeded (production, notification tests) without coupling every legacy test to template seeding. Update `tests/core/notifications/test_service.py::test_publish_validation_errors` accordingly — it seeds templates, so behavior there is unchanged; add one test that publish succeeds with arbitrary context when no template exists.)

- [ ] **Step 5: Lint, typecheck, commit** — `feat(notifications): maker-checker pending/approved/rejected notices`.

---

### Task 3: billing domain events (platform outbox)

**Files:**
- Modify: `app/platform_/billing/services/invoice_service.py`, `app/platform_/billing/services/subscription_service.py`
- Test: `tests/platform_/billing/test_billing_domain_events.py` (create)

**Interfaces (produces — consumed by Task 4's consumer):**
- `generate_for_subscription`: after the new invoice flush (NOT on the idempotent early-return), `EventPublisher.publish(session, aggregate_type="invoice", aggregate_id=invoice.id, event_type="BillingInvoiceIssued", payload={"invoice_id", "tenant_id", "invoice_number", "amount_total", "currency", "due_at"})` (all strings).
- `mark_overdue_batch`: change the bulk UPDATE to `RETURNING id, tenant_id, invoice_number, amount_total, amount_paid, currency`; per returned row publish `BillingInvoiceOverdue` with `payload={"invoice_id", "tenant_id", "invoice_number", "amount_outstanding", "currency"}`; return count unchanged.
- `transition_to_suspended`: publish `BillingSubscriptionSuspended` with `payload={"subscription_id", "tenant_id"}`.

- [ ] **Step 1: Write the failing tests** — platform-session factory fixture (copy from an existing billing service test); seed plan+subscription+invoice the way those tests do. Three tests asserting a `platform.outbox_events` row with the right `event_type` and payload keys after each call, plus: idempotent re-`generate_for_subscription` publishes NO second event.

- [ ] **Step 2: verify failure.**

- [ ] **Step 3: Implement** per Interfaces (import `EventPublisher` like `billing/beat.py` does).

- [ ] **Step 4: Verify pass** — `python -m pytest tests/platform_/billing/ -q` (whole billing suite green).

- [ ] **Step 5: Lint, typecheck, commit** — `feat(billing): domain events for invoice issued/overdue + subscription suspended`.

---

### Task 4: billing notifications consumer (platform outbox → tenant feeds)

**Files:**
- Create: `app/platform_/billing/consumer.py`
- Modify: `app/workers/celery_app.py` (include + beat 60s)
- Test: `tests/platform_/billing/test_notifications_consumer.py` (create)

**Interfaces:**
- `async _consume_batch(engine) -> int` (testable core) + Celery task `consume_billing_notification_events` (60s beat, `asyncio.run`).
- Flow per unprocessed event (`consumer_name="notifications.billing_consumer"`, platform `processed_events` guard, same SQL shape as `app/modules/credit/consumer.py`):
  1. Resolve `platform.tenants.schema_name` from `payload["tenant_id"]` (skip+mark processed if tenant missing/inactive).
  2. Open a session with `SET LOCAL search_path TO {schema}, platform`; select recipients: `TenantUser` active, `is_admin`, `impersonation_id IS NULL`.
  3. Per recipient: `NotificationService.publish(...)` with `dedupe_key=f"{event_type}:{event_id}:{user.id}"`; mapping: `BillingInvoiceIssued→invoice_issued` context `{invoice_number, amount: amount_total, currency, due_date: due_at}`, `BillingInvoiceOverdue→invoice_overdue` context `{invoice_number, amount: amount_outstanding, currency}`, `BillingSubscriptionSuspended→subscription_suspended` context `{}`. Commit tenant session.
  4. Insert the `processed_events` row (platform schema) and commit — after the tenant commit, so a crash between them is healed by dedupe on redelivery.

- [ ] **Step 1: failing tests** — seed: tenant row (slug/schema `tenant_test`… reuse the existing `test-tenant` row from conftest if present, else insert one pointing at `tenant_test`), one admin tenant user + one non-admin, seeded templates, one `PlatformOutboxEvent` per event type. Run `_consume_batch`: tenant-schema `notification_events` rows exist for the admin only, correct codes; `processed_events` rows written; second `_consume_batch` run → 0 new notifications (processed guard) and re-inserting the same outbox event id fails naturally (skip — instead assert dedupe: delete the processed rows, rerun, still no new notification rows thanks to dedupe_key).

- [ ] **Step 2: verify failure.**

- [ ] **Step 3: Implement** per Interfaces (structure copied from `app/modules/credit/consumer.py`: raw-SQL unprocessed query, `_SCHEMA_RE` guard on schema names).

- [ ] **Step 4: verify pass** — new file + `tests/platform_/billing/ -q`.

- [ ] **Step 5: Lint, typecheck, commit** — `feat(notifications): billing consumer bridges platform events to tenant feeds`.

---

### Task 5: member_activated consumer

**Files:**
- Create: `app/modules/members/consumer.py`
- Modify: `app/workers/celery_app.py` (include + beat 60s)
- Test: `tests/modules/members/test_member_activated_consumer.py` (create)

**Interfaces:**
- `async _consume_for_tenant(engine, schema) -> int` + task `consume_member_notification_events` (60s) iterating active tenant schemas (fees-consumer pattern), `consumer_name="notifications.member_consumer"`, filtering `event_type='MemberActivated'`.
- Per event: load the member row (same schema) for `email`/`full_name`/`member_number`; publish `member_activated` (kind `member`, `recipient_email=member.email`, context `{"full_name": ..., "member_number": ...}`, `dedupe_key=f"member_activated:{event_id}"`); mark processed.

- [ ] **Step 1: failing tests** — seed member + `TenantOutboxEvent(event_type="MemberActivated", payload={"member_id": ...})` + templates in `tenant_test`; run `_consume_for_tenant`; assert notification row (code, kind, email, context) + processed row; rerun → 0.

- [ ] **Step 2–5** — implement per pattern; verify `tests/modules/members/ -q` green; commit `feat(notifications): member_activated consumer`.

---

### Task 6: KYC decision notices

**Files:**
- Modify: `app/modules/members/kyc_submissions.py` (`KycReviewService.approve` / `.reject`)
- Test: `tests/modules/members/test_kyc_notifications.py` (create)

**Interfaces:** after the status flip + flush in each method: publish `kyc_submission_approved` (context `{}`) / `kyc_submission_rejected` (context `{"reason": reason}`), kind `member`, `recipient_user_id=member.id`, `recipient_email=member.email`, dedupe `kyc_approved:{submission.id}` / `kyc_rejected:{submission.id}`.

- [ ] Tests (seed templates; reuse the fixture pattern from `tests/modules/members/test_kyc_submissions_service.py`): approve → one row with empty context; reject → row whose context carries the reason; approve twice-idempotent not needed (approve raises `SubmissionNotPending` on reuse). Implement, verify `tests/modules/members/ -q`, commit `feat(notifications): KYC decision notices to members`.

---

### Task 7: loan decision notices

**Files:**
- Modify: `app/modules/credit/executors.py` (`execute_approve_application`), `app/modules/credit/services/application.py` (`reject`)
- Test: `tests/modules/credit/test_loan_decision_notifications.py` (create)

**Interfaces:** executor (after the application is marked approved): publish `loan_application_approved`, kind `member`, `recipient_user_id=application.member_id`, `recipient_email=None`, `channels=["in_app"]`, context `{"amount": payload["approved_amount"]}`, dedupe `loan_approved:{application_id}`. `LoanApplicationService.reject` (after status flip): `loan_application_rejected`, `channels=["in_app"]`, context `{"reason": reason or ""}`, dedupe `loan_rejected:{application_id}`.

- [ ] Tests (tenant-session factory + seeds per `tests/modules/credit/test_member_apply_api.py` helpers, service-level): call the executor function directly with a seeded submitted application payload → assert the notification row (code, kind, channels `["in_app"]`, context amount); `reject` via the service (needs an approval request? — `reject` guards status then calls ApprovalService only when `approval_request_id` set; seed application with `approval_request_id=None` to keep the test narrow) → assert row. Implement, verify `tests/modules/credit/ -q`, commit `feat(notifications): loan decision notices to members (in_app)`.

---

### Task 8: Close-out — suites + CLAUDE.md

- [ ] `python -m ruff check app/ tests/ && python -m mypy app/`; `python -m pytest tests/core/ tests/modules/ -q --ignore=tests/modules/credit` then `python -m pytest tests/modules/credit/ -q`; `python -m pytest tests/platform_/ -q`.
- [ ] CLAUDE.md — extend the "## Notifications contracts" section:

```markdown
- Increment 2 (call sites) is wired: password_reset notices from the four reset
  flows (platform/tenant/member self-service + admin tenant-user reset — notice
  only, token never in context); maker-checker pending (all eligible checkers,
  maker excluded) and approved/rejected (maker; skipped silently when the maker
  is not a staff row — member-submitted operations get their module's own codes);
  KYC decisions (members module, with email); loan decisions (credit, in_app-only —
  credit may not read member rows). Billing codes are DERIVED: the billing services
  publish BillingInvoiceIssued/BillingInvoiceOverdue/BillingSubscriptionSuspended
  to the platform outbox and `notifications.billing_consumer` bridges them to
  tenant-admin feeds; `notifications.member_consumer` derives member_activated
  from the existing MemberActivated event. All consumer publishes carry dedupe
  keys; publish treats a code with NO active templates as allow-all context
  (strict allow-list resumes the moment templates exist).
```

  Also update the roadmap table row 3 to "In progress — increments 1-2".
- [ ] Commit `docs(claude): notifications call-site contracts (increment 2)`.

## Out of scope

- Portal surfaces (increment 3), real providers, bulk announcements.
- Emails for credit member notices (needs a members read interface — future).
- Notifying on approval-request expiry/cancel (not in the taxonomy).
