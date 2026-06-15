# Portal Billing — Invoices + Payments + Tenant Self-Service (SP16) Design

**Date:** 2026-06-15
**Phase:** 2 (Admin Portal), sub-plan 16
**Status:** Approved

## Goal

Complete the Billing nav group: the platform finance/admin **Invoices** and
**Payments** screens, plus the first **tenant self-service** billing views
(`/billing/me/*`). Pure client of existing endpoints — no new backend.

## Contract posture

Pure portal client work. **Zero new backend endpoints, api-client methods,
Zod schemas, permission keys, or StatusBadge maps** — all already exist:

- **api-client** (`resources.billing.*`): `listInvoices`, `getInvoice`,
  `getInvoicePdf`, `voidInvoice`, `recordPayment`, `listPendingPayments`,
  `rejectPayment`; and the tenant-context `mySubscription`, `myInvoices`,
  `myInvoice`, `myInvoicePdf`.
- **schemas** (`@sacco/schemas` `billing.ts`): `recordPaymentSchema`
  (+ `paymentMethodSchema`), `invoiceVoidSchema`, `paymentRejectSchema`
  (+ inferred `*Input` types). Out types `InvoiceOut`/`PaymentOut` etc. are
  added in this sub-plan (see below) — they do not yet exist in `@sacco/schemas`.
- **permissions** (`permissions.ts`): `billing.read` → finance, `billing.write` → admin.
- **StatusBadge**: `INVOICE_STATUS` (entity `"invoice"`) and `PAYMENT_STATUS`
  (entity `"payment"`) both exist.

Same posture as SP15 (Phase 2 contract B/N: no backend changes, everything under `admin/`).

## Permission mapping (authoritative — drives UI gating)

Backend gate tiers (from `app/platform_/billing/api.py`):

| Action | Backend dep | Portal gate |
|--------|-------------|-------------|
| List/get invoices, list pending payments, invoice PDF | `CurrentFinance` | `billing.read` |
| Record payment (maker) | `CurrentFinance` | `billing.read` |
| Void invoice (maker) | `CurrentAdmin` | `billing.write` |
| Reject payment (checker) | `CurrentAdmin` | `billing.write` |

Record-payment is a **finance** action, so it gates on `billing.read` (finance
tier), not `billing.write`. Void and reject gate on `billing.write` (admin).
UI gating is UX-only; the API enforces (contract D).

## Backend facts (authoritative)

- `GET /platform/billing/invoices` (finance) — unpaginated; `tenant_id` +
  `status_filter` query params. → in-memory DataTable adapter (SP15 pattern).
- `GET /platform/billing/invoices/{id}` (finance) → `InvoiceDetailOut`
  (`InvoiceOut` + `line_items: InvoiceLineItemOut[]`).
- `GET /platform/billing/invoices/{id}.pdf` (finance) → PDF stream.
- `POST /platform/billing/invoices/{id}/void` (admin) → submits a
  `billing.void_invoice` approval; returns `{status:"pending_approval",
  approval_request_id}`. Backend voids only when `amount_paid == 0`.
- `POST /platform/billing/invoices/{id}/payments` (finance) → creates
  `Payment(pending)` + `ApprovalRequest` in one tx; returns
  `{status, payment_id, approval_request_id}` (maker action). Body =
  `PaymentRecordIn` incl. a required `idempotency_key` (≥8 chars).
- `POST /platform/billing/payments/{id}/reject` (admin) → paired
  `ApprovalService.reject` + `PaymentService.reject`; returns
  `{status:"rejected", payment_id}`. 409 on conflict.
- `GET /platform/billing/payments/pending-confirmation` (finance) →
  `PaymentOut[]` of `status="pending"`.
- Tenant-context (`/billing/me/*`, require tenant auth + `X-Tenant-Slug`):
  `GET /billing/me/subscription` → `SubscriptionOut`; `GET /billing/me/invoices`
  → `InvoiceOut[]`; `GET /billing/me/invoices/{id}` → `InvoiceDetailOut`;
  `GET /billing/me/invoices/{id}.pdf` → PDF. Ownership enforced in-handler
  (cross-tenant → 404).
- `InvoiceOut`/`PaymentOut` carry `tenant_id`/`subscription_id` only — no
  embedded names (resolve client-side like SP15 subscriptions).

## Schema additions (`@sacco/schemas`)

Add hand-written read types mirroring the backend (the package has the `*In`
Zod schemas but no Out types for invoices/payments):
- `InvoiceLineItemOut`, `InvoiceOut`, `InvoiceDetailOut` (= `InvoiceOut` +
  `line_items: InvoiceLineItemOut[]`), `PaymentOut`. Money/`Decimal` fields as
  `string` (matches `<Money>`/`moneyString`).

## Confirm-payment / approval gap (documented)

Recording a payment creates an approval; **confirming (approving)** it requires
the platform Approvals inbox (SP17, not built). In SP16 the Payments queue lists
pending payments and offers **Reject** (admin); approval happens out of band via
`POST /platform/approvals/{id}/approve` until SP17. Same shape as SP14's
impersonation-approval gap. `<MakerCheckerBanner>` on records with open approvals
also waits on the approvals-list endpoint (SP17).

## PDF delivery (both contexts)

The access token lives in memory (contract C), so a plain `<a href>` to the
backend PDF URL can't carry auth. SP16 adds **server-side proxy route handlers**
that attach the bearer (and `X-Tenant-Slug` for the tenant route) and stream the
PDF back, mirroring the impersonation route-handler pattern:
- `app/api/billing/invoices/[id]/pdf/route.ts` (platform bearer).
- `app/api/billing/me/invoices/[id]/pdf/route.ts` (tenant bearer + slug).
"Download PDF" buttons link to these routes (open in a new tab).

## Screens / units

### Part A — Platform (`/platform/billing/*`, gated finance/admin)

1. **`<BillingTabs>` extended** → Plans | Subscriptions | Invoices | Payments.
2. **Invoices list** `/platform/billing/invoices` — in-memory `<DataTable>`;
   columns: invoice #, tenant (name-resolved from `tenants.list`), total
   (`<Money>`), paid (`<Money>`), status (`<StatusBadge entity="invoice">`),
   due date (`<FormattedDate>`); status + tenant filters. Gated `billing.read`.
3. **Invoice detail** `/platform/billing/invoices/[id]` — overview + line-items
   table + `<AuditBar entityType="invoice">` + actions:
   - **Record payment** (shown for `billing.read`): a form (amount
     `<MoneyInput>`, `payment_method` `<Select>`, `external_reference`, `notes`)
     → `<MakerCheckerConfirmDialog>` → `recordPayment` with a fresh
     `crypto.randomUUID()` `idempotency_key`. Toast "Payment recorded — pending
     approval". Shown only when the invoice is payable (status
     `issued`/`partial`/`overdue`).
   - **Void** (shown for `billing.write`, only when `Number(amount_paid) === 0` and
     status not `void`/`paid`): reason → `<MakerCheckerConfirmDialog>` →
     `voidInvoice`. Toast "Void requested — pending approval".
   - **Download PDF** → the platform PDF proxy route.
4. **Payments queue** `/platform/billing/payments` — `<DataTable>` over
   `listPendingPayments`; columns: invoice # (link to invoice detail), amount
   (`<Money>`), method, recorded (`<FormattedDate>`), status
   (`<StatusBadge entity="payment">`); **Reject** action (`billing.write`,
   reason → `<ConfirmDialog destructive>` → `rejectPayment`). An info note
   explains approval is via the Approvals inbox (SP17).
5. **Platform PDF proxy route** (unit 5 above).

### Part B — Tenant self-service (`(tenant-authed)`)

6. **`getTenantPageContext()`** in `server-page-context.ts` — tenant analog of
   `getPlatformPageContext()`: `getServerAccessToken("tenant")` +
   `getServerCurrentUser("tenant")` (redirect `/login` if absent) +
   `createApiClient({ tenantContext: new FixedTenantContext(slug) })` so
   `/billing/me/*` calls carry `X-Tenant-Slug`. Returns `{ user, slug, resources }`.
7. **Tenant billing page** `/billing` — current subscription summary
   (`mySubscription`, plan name resolved if needed) + own invoices list
   (`myInvoices`) via `<DataTable>` (invoice #, total, status, due); each row
   links to the tenant invoice detail.
8. **Tenant invoice detail** `/billing/invoices/[id]` — `myInvoice` + line
   items + Download PDF (tenant proxy route). 404 → notFound.
9. **Tenant PDF proxy route** (tenant bearer + slug).
10. **Tenant sidebar "Billing"** nav item → `/billing`.

## Money / dates / status / forms

`<Money amount currency />` for all amounts; `<FormattedDate>` for dates;
`<StatusBadge entity="invoice"|"payment">`; forms via `<FormField>` +
`<MoneyInput>`/`<Select>`; no raw `toLocaleString`, no literal hex (contracts
H/R/S/U/Q). Lists via `<DataTable>` (contract T). Maker-checker actions via
`<MakerCheckerConfirmDialog>` (contract V).

## Out of scope (documented)

- Confirm-payment approval UI → SP17 (approvals inbox).
- `<MakerCheckerBanner>` on records with open approvals → SP17 (needs approvals-list endpoint).
- e2e (seeded-backend sub-plan) and next-intl (portal-wide deferral) — raw English strings.

## Testing

Vitest + Testing Library per screen/form mirroring SP12–15: schema tests for the
new Out types are unnecessary (interfaces only) — but the record-payment form,
void flow, reject flow, invoice/payment table renders, and `getTenantPageContext`
are tested. PDF proxy routes get route-handler tests (bearer attached, slug for
tenant, stream/headers) like the impersonation routes. `typecheck` + `lint`
clean across `@sacco/schemas`/`@sacco/ui`/`@sacco/api-client`/`@sacco/portal`.
All changes confined to `admin/` (contracts B/N).
