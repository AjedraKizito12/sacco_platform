# Portal v1 — Plan Index (Phase 2)

> **Status:** Drafted 2026-06-02. This is the **index** for Portal v1 (Phase 2 of the SaaS launch roadmap). Sub-plan documents are generated one at a time after the index is approved.
>
> **Scope:** Both contexts — platform admin back-office AND full tenant operator portal. One Next.js 15 app, two route trees.
>
> **For agentic workers:** Each sub-plan listed below will be a full plan document under `docs/superpowers/plans/phase-2-portal/`. Use `superpowers:subagent-driven-development` for execution.

---

## 1. Goal

Ship a production-grade Next.js 15 portal that operates the full SACCO platform — both the platform back-office (for Sacco-platform staff) and the tenant operator portal (for SACCO managers, finance, tellers). The portal is a true **client** of the existing FastAPI; it adds zero business logic and zero new endpoints. Backend gaps that block portal screens are shipped in a separate, parallel pre-phase (**Phase 1.7 — Backend Foundation for Portal**).

## 2. Architecture

- **Framework:** Next.js 15 (App Router), React 19, TypeScript strict (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`).
- **Workspace:** new top-level `admin/` directory, pnpm workspaces, Turborepo build cache. Layout: `admin/apps/portal/` + `admin/packages/{ui,api-client,schemas,eslint-config,tsconfig}/`.
- **Styling:** Tailwind v4 with `@theme inline` mapping from `tokens.css` (canonical source at `docs/tokens.css` copied into `admin/packages/ui/src/tokens.css` during sub-plan 04).
- **Components:** shadcn/ui owned in `packages/ui`. Storybook is the executable design system reference (`packages/ui/.storybook/`).
- **State:** TanStack Query (server), Zustand (small client slices), nuqs (URL-synced table/filter state).
- **Forms:** React Hook Form + Zod (schemas in `packages/schemas`, mirrored from backend Pydantic).
- **Tables:** TanStack Table via `@sacco/ui` DataTable wrapper — server-side everything.
- **API client:** `openapi-typescript` codegen from FastAPI OpenAPI spec → `packages/api-client/src/generated/`. Fetch wrapper auto-injects `Authorization`, `X-Tenant-Slug`, `Idempotency-Key`; handles 401-refresh; surfaces 402/403 subscription-gate as typed errors.
- **Auth:** Access token in memory; refresh token in httpOnly Secure SameSite=Strict cookie; CSRF protection via Next.js. Refresh on 401, redirect on refresh failure.
- **i18n:** next-intl, English-only v1, structure i18n-ready.
- **Testing:** Vitest + React Testing Library, Playwright (E2E), MSW.
- **Tooling:** ESLint (react, tailwindcss, jsx-a11y), Prettier, Husky, lint-staged, Node 22 LTS pinned via `admin/.nvmrc`.
- **Observability:** Sentry for frontend errors. Same JSON logs to the LGTM stack once Phase 5 lands.

## 3. Hard contracts (do not violate)

These mirror the "Admin portal contracts" subsection that will be appended to `CLAUDE.md` during sub-plan 03.

A. The portal is a CLIENT of the existing FastAPI. No business logic.
B. **Zero new API endpoints in Phase 2.** All backend additions ship in Phase 1.7. If a sub-plan thinks it needs a new endpoint, stop and surface.
C. Access token in memory. Refresh token in httpOnly Secure SameSite=Strict cookie. Never `localStorage`, never `sessionStorage`, never plain cookies.
D. UI permission gating is UX only. API enforces.
E. Strict CSP. No `dangerouslySetInnerHTML`. No user-controlled HTML rendering.
F. Password reset tokens displayed in one-time modal (until Phase 3 email is wired). Never in URLs, query strings, or logs.
G. Subscription-gate responses: 402 → "Subscription past due — payment required" screen with link to billing; 403 (from gate) → "Account suspended — contact platform admin". Platform admin context is NOT gated.
H. Money via `<Money amount currency />`. Dates via `<FormattedDate>` / `<FormattedDateTime>` / `<AuditTimestamp>` / `<RelativeTime>`. Never raw `toLocaleString`.
I. All tables: TanStack Table via `@sacco/ui` DataTable. Server-side pagination, sort, filter. URL state via nuqs.
J. All forms: React Hook Form + Zod. Schemas in `@sacco/schemas`.
K. Maker-checker UI patterns: action buttons labeled "Request X" not "X" when they create approval requests; confirm dialog explicitly states "This creates an approval request, not executes"; pending-approval banner on records with open approvals; approval inbox shows quorum ("1 of 2").
L. `Idempotency-Key` auto-injected on all POST/PUT/PATCH/DELETE by the API client (UUID per user intent — same UUID across retries of the same form submission).
M. No client-side data fetching for initial render. Server components fetch via the typed client; client components mutate via TanStack Query.
N. Do NOT modify anything outside `admin/` except: `docker-compose.yml` (add admin service), `Makefile` (add `admin-*` targets), `CLAUDE.md` (append portal subsection, update Phase 2 stack to "Next.js 15"), `.gitignore` (admin entries). Backend code, alembic, docker/, scripts/, tests/, app/ stay untouched.
O. Notification bell renders empty state ("Notifications coming soon") until Phase 3 ships. Bell component accepts the future Phase 3 event-feed shape but is fed null/empty in v1.

## 4. Prerequisites — Phase 1.7 (Backend Foundation for Portal)

Phase 1.7 is a separate, backend-only plan that ships in parallel with Portal v1 Part A. The Phase 1.7 sub-plans are listed here so Portal v1 sub-plans can declare specific dependencies. Phase 1.7 will get its own full plan document in a follow-up scoping session.

| ID | What it ships | Why it's needed |
|----|---------------|-----------------|
| **P1.7-A** | `/platform/approvals/*` router (list, get, approve, reject, cancel) operating against `PlatformApprovalRequest`. Mirrors the tenant `/approvals` API but uses `get_platform_session` and `PlatformApprovalRequest` model. | Without this, no platform-scoped maker-checker request can be approved via HTTP. Blocks billing payment confirmation in portal. |
| **P1.7-B** | `support_impersonations` table + impersonation lifecycle: `POST /platform/impersonations` (maker-checker), `DELETE /platform/impersonations/{id}` (end session), `GET /platform/impersonations/active`. Tenant JWT dependency accepts impersonation-minted tokens. `tenant.audit_log` gains `impersonation_id` FK. | Required by ADR-001 §7. Without this, platform admins cannot access tenant routes. Blocks "Open in tenant context" from platform tenant detail. |
| **P1.7-C** | Tenant management endpoints: `PATCH /platform/tenants/{id}` (name, contact), `POST /platform/tenants/{id}/suspend` (maker-checker), `POST /platform/tenants/{id}/reactivate`, `POST /platform/tenants/{id}/assign-plan` (or fold into PATCH). | Roadmap's tenant edit/suspend screens; portal cannot manage tenant lifecycle beyond create+retry today. |
| **P1.7-D** | Tenant-user CRUD from platform context: `GET /platform/tenants/{id}/users`, `POST .../users` (create + invite), `PATCH .../users/{user_id}` (lock/unlock/is_admin), `POST .../users/{user_id}/password-reset` (admin-initiated one-time-token returned in response body — replaces self-service email flow until Phase 3). | Roadmap's `/tenants/[id]/users` screen; portal cannot manage tenant users. |
| **P1.7-E** | Platform user roles: `platform_users.role` enum column (`superuser`, `admin`, `finance`, `support`). Migrate existing `is_superuser=true` rows to `role='superuser'`. Add `Annotated[PlatformUser, Depends(get_current_platform_user_with_role("admin"))]` helpers. Enforce 4-tier in all `/platform/*` routes. | CLAUDE.md mandates 4-tier RBAC enforced at API. Today only `is_superuser` exists. |
| **P1.7-F** | Audit log query API: `GET /platform/audit-log` (cross-tenant), `GET /audit-log` (tenant-scoped), with filters (actor, table, operation, date range, record_id) and `GET .../{id}` for detail with before/after JSON. | Roadmap's audit viewer screens; audit log is write-only today. |
| **P1.7-G** | `GET /platform/admin/dashboard-stats` aggregate endpoint: tenant counts by status, MRR, subscriptions by status, overdue invoice count, pending approval count, outbox queue depth. Single response, server-aggregated to avoid N+1 client calls. | Optional per CLAUDE.md; turns out to be needed because the dashboard otherwise fires ~12 parallel calls on mount and degrades on slow connections. |

Phase 1.7 effort estimate: ~3 weeks for one backend engineer. Sub-plans are roughly:
P1.7-01 platform approvals API · P1.7-02 impersonations table+endpoints · P1.7-03 tenant edit/suspend/plan-assign · P1.7-04 tenant-user CRUD + admin password reset · P1.7-05 platform user roles (4-tier) · P1.7-06 audit-log query API · P1.7-07 dashboard-stats.

## 5. API surface (authoritative inventory)

Every existing route, grouped. Sourced directly from the 14 api.py files mounted in `app/main.py:123-141`. Sub-plans cite this section for which routes they consume.

### Platform context — already exists

**Platform auth** (`app/modules/iam/platform_auth/api.py`)
- `POST /platform/auth/token` — login (email+password → access+refresh tokens)
- `POST /platform/auth/refresh` — refresh access token
- `POST /platform/auth/logout` — revoke session (Bearer required)
- `GET /platform/auth/me` — current platform user (Bearer required)
- `POST /platform/auth/password-reset/request` — request reset (always 204, anti-enumeration)
- `POST /platform/auth/password-reset/confirm` — confirm with token + new password

**JWT keys** (`app/modules/iam/keys/api.py`)
- `GET /.well-known/jwks.json` — public JWK set
- `GET /platform/jwt-keys/` — list signing keys (superuser)

**Platform tenants** (`app/platform_/tenants/api.py`)
- `POST /platform/tenants` — create tenant (202 + async provisioning)
- `GET /platform/tenants` — list (optional `status` filter)
- `GET /platform/tenants/{id}` — detail (poll target for provisioning status)
- `POST /platform/tenants/{id}/retry-provisioning` — retry (maker-checker)

**Platform users** (`app/platform_/users/api.py`)
- `GET /platform/users` — list
- `GET /platform/users/{id}` — detail
- `POST /platform/users` — create (superuser only)
- `PATCH /platform/users/{id}` — full_name immediate, is_active/is_superuser via maker-checker

**Platform billing** (`app/platform_/billing/api.py`)
- `GET /platform/billing/plans` — list (`only_active` filter)
- `POST /platform/billing/plans` — create plan
- `GET /platform/billing/plans/{id}` — detail
- `PATCH /platform/billing/plans/{id}` — update
- `GET /platform/billing/subscriptions` — list (filters: tenant_id, status)
- `POST /platform/billing/subscriptions` — assign plan to tenant
- `GET /platform/billing/subscriptions/{id}` — detail
- `POST /platform/billing/subscriptions/{id}/cancel?mode=at_period_end|immediate` — soft (direct) or hard (maker-checker)
- `POST /platform/billing/subscriptions/{id}/reactivate`
- `GET /platform/billing/invoices` — list (filters: tenant_id, status)
- `GET /platform/billing/invoices/{id}` — detail (with line items)
- `GET /platform/billing/invoices/{id}.pdf` — PDF
- `POST /platform/billing/invoices/{id}/payments` — record payment (maker action — creates Payment(pending) + ApprovalRequest)
- `POST /platform/billing/invoices/{id}/void` — submit void (maker-checker)
- `POST /platform/billing/payments/{id}/reject` — paired rejection (ApprovalService.reject + PaymentService.reject)
- `GET /platform/billing/payments/pending-confirmation` — checker's queue

### Platform context — Phase 1.7 dependencies

Marked **[P1.7-X]** where X is the Phase 1.7 sub-plan ID from section 4.

- **[P1.7-A]** `GET|POST /platform/approvals` (submit/list), `GET /platform/approvals/{id}`, `POST /platform/approvals/{id}/approve|reject|cancel`
- **[P1.7-B]** `POST|DELETE /platform/impersonations`, `GET /platform/impersonations/active`
- **[P1.7-C]** `PATCH /platform/tenants/{id}`, `POST .../suspend`, `POST .../reactivate`, `POST .../assign-plan`
- **[P1.7-D]** `GET|POST /platform/tenants/{id}/users`, `PATCH .../users/{uid}`, `POST .../users/{uid}/password-reset`
- **[P1.7-F]** `GET /platform/audit-log`, `GET /platform/audit-log/{id}`
- **[P1.7-G]** `GET /platform/admin/dashboard-stats`

### Tenant context — already exists

**Tenant auth** (`app/modules/iam/tenant_auth/api.py`)
- Same shape as platform: `/auth/token`, `/auth/refresh`, `/auth/logout`, `/auth/me`, `/auth/password-reset/request|confirm`. X-Tenant-Slug required (set by subdomain middleware in prod).

**Tenant billing** (`app/platform_/billing/api.py`)
- `GET /billing/me/subscription`, `GET /billing/me/invoices`, `GET /billing/me/invoices/{id}`, `GET /billing/me/invoices/{id}.pdf`

**Members** (`app/modules/members/api.py`)
- `POST /members`, `GET /members` (filter: status), `GET /members/{id}`, `POST /members/{id}/status-change` (maker-checker)

**Savings** (`app/modules/savings/api.py`)
- `POST|GET /savings/products`, `GET /savings/products/{id}`
- `POST /savings/accounts`, `GET /savings/accounts/{id}` (with balance), `GET /savings/accounts/{id}/transactions`
- `POST /savings/accounts/{id}/deposit` (direct), `POST /savings/accounts/{id}/withdraw` (maker-checker)

**Shares** (`app/modules/shares/api.py`)
- `POST|GET /shares/products`, `GET /shares/products/{id}`
- `POST /shares/accounts`, `GET /shares/accounts/{id}` (with balance), `GET /shares/accounts/{id}/transactions`
- `POST /shares/accounts/{id}/purchase` (direct), `POST /shares/accounts/{id}/redeem` (maker-checker)

**Credit** (`app/modules/credit/api.py`) — largest module
- Products: `POST|GET /credit/products`, `GET|PATCH /credit/products/{id}`
- Applications: `POST|GET /credit/applications`, `GET /credit/applications/{id}`, `POST .../withdraw|approve|reject`
- Disbursement: `POST /credit/loans/{application_id}/disburse` (direct, idempotency-keyed)
- Loans: `GET /credit/loans` (filters: member_id, status), `GET /credit/loans/{id}`
- Repayments: `POST /credit/loans/{id}/repayments`, `GET /credit/loans/{id}/repayments`
- Schedule: `GET /credit/loans/{id}/schedule`
- Write-off / recovery: `POST /credit/loans/{id}/write-off` (maker-checker if ≥ threshold), `POST .../recover`
- Restructure: `POST /credit/loans/{id}/restructure` (maker-checker quorum=2), `GET .../restructurings`
- Guarantors: `POST /credit/applications/{id}/guarantors` (nominate), `GET .../guarantors`, `POST /credit/guarantors/{id}/accept|decline`
- Payroll batches: `POST /credit/payroll-batches` (JSON), `POST /credit/payroll-batches/csv` (upload), `GET /credit/payroll-batches/{id}`, `POST .../reject`
- Query: `GET /credit/query/loans-eligible-for-fee`
- Statements: `GET /credit/loans/{id}/statement` (JSON), `GET /credit/loans/{id}/statement.pdf`

**Fees** (`app/modules/fees/api.py`)
- Fee types: `GET|POST /fees/types`, `GET|PATCH /fees/types/{id}`
- Assessments: `GET /fees/assessments` (filters), `GET /fees/assessments/{id}` (with collections), `POST /fees/assessments`
- Collections: `POST /fees/collections`

**Ledger** (`app/modules/ledger/api.py`)
- CoA: `POST|GET /ledger/accounts`, `GET /ledger/accounts/{id}` (with balance)
- Journal entries: `POST /ledger/journal-entries/submit` (maker-checker), `GET /ledger/journal-entries`, `GET /ledger/journal-entries/{id}`

**Reporting** (`app/modules/reporting/api.py`)
- `GET /reporting/trial-balance` (formats: json/pdf/csv)
- `GET /reporting/loan-portfolio` (status filter; formats: json/pdf/csv)
- `GET /reporting/income-statement` (from/to required; formats: json/pdf/csv)
- `GET /reporting/savings-statement` (member_id required; formats: json/pdf/csv)
- `GET /reporting/fee-collection` (from/to required; fee_type filter; formats: json/pdf/csv)
- `GET /reporting/runs` (filter: report_type)

**Approvals (Tenant)** (`app/modules/maker_checker/api.py`)
- `POST|GET /approvals`, `GET /approvals/{id}`
- `POST /approvals/{id}/approve|reject|cancel`

### Tenant context — Phase 1.7 dependencies

- **[P1.7-F]** `GET /audit-log` (tenant-scoped), `GET /audit-log/{id}`

## 6. Screen inventory (derived from API surface)

Two route trees in one app: `/platform/*` for platform staff, `/*` under tenant subdomain for SACCO operators. Login flows are separate. The cross-context entry point is the impersonation flow shipped in P1.7-B.

### Platform context (Platform Admin Portal)

```
PLATFORM NAVIGATION
├── /platform                       Dashboard (KPIs, recent activity, system health)         [P1.7-G]
├── /platform/login                 Login (POST /platform/auth/token)
├── /platform/forgot-password       Request reset                                            (existing)
├── /platform/reset-password        Confirm + one-time-modal pattern                         (existing)
│
├── Tenants
│   ├── /platform/tenants                   List + filters                                    (existing)
│   ├── /platform/tenants/new               Provisioning wizard + status polling              (existing)
│   ├── /platform/tenants/[id]              Detail (overview, embedded billing/users widgets) (existing)
│   ├── /platform/tenants/[id]/edit         Edit name/contact                                 [P1.7-C]
│   ├── /platform/tenants/[id]/suspend      Suspend confirmation (maker-checker)              [P1.7-C]
│   ├── /platform/tenants/[id]/billing      Tenant's subscription + invoices + payments       (existing)
│   ├── /platform/tenants/[id]/users        Tenant-user list/create/lock/reset                [P1.7-D]
│   ├── /platform/tenants/[id]/audit        Tenant-scoped audit log                           [P1.7-F]
│   ├── /platform/tenants/[id]/impersonate  Start impersonation session (maker-checker)       [P1.7-B]
│   └── (retry-provisioning surfaces inline on failed tenant detail)
│
├── Users (Platform)
│   ├── /platform/users                     List                                              (existing)
│   ├── /platform/users/new                 Create (superuser only)                           (existing)
│   ├── /platform/users/[id]                Detail (sessions, recent activity)                (existing /me + existing /users/{id})
│   ├── /platform/users/[id]/edit           Edit (immediate name; sensitive via MC)           (existing)
│   └── /platform/users/[id]/reset-password Admin-initiated, one-time-modal pattern           [P1.7-D]*
│
│   *Note: P1.7-D ships the admin-reset endpoint for tenant users; an equivalent for
│   platform users may already be the existing self-service flow, OR may need an
│   equivalent admin-initiated path. P1.7-04 will resolve.
│
├── Billing
│   ├── /platform/billing/plans                       List + create + edit                    (existing)
│   ├── /platform/billing/plans/[id]                  Detail                                  (existing)
│   ├── /platform/billing/subscriptions               List + filters                          (existing)
│   ├── /platform/billing/subscriptions/[id]          Detail (timeline of invoices+payments)  (existing)
│   ├── /platform/billing/subscriptions/[id]/cancel   Soft/hard cancel dialog                 (existing)
│   ├── /platform/billing/invoices                    List + filters                          (existing)
│   ├── /platform/billing/invoices/[id]               Detail + PDF download                   (existing)
│   ├── /platform/billing/invoices/[id]/record-payment  Maker form                            (existing)
│   ├── /platform/billing/invoices/[id]/void          Void confirmation (maker-checker)       (existing)
│   └── /platform/billing/payments/pending-confirmation  Checker queue + approve/reject       [P1.7-A]
│
├── Approvals (Platform)                                                                      [P1.7-A]
│   ├── /platform/approvals                           Pending (mine, all) + filters
│   ├── /platform/approvals/[id]                      Detail (payload, history, quorum)
│   └── /platform/approvals/my-submissions
│
├── Audit (Platform)                                                                          [P1.7-F]
│   ├── /platform/audit                               Search by actor/table/date
│   └── /platform/audit/[id]                          Entry detail with before/after JSON diff
│
├── Operations
│   ├── /platform/operations                          System health (degrades pre-Phase 5)
│   └── /platform/operations/jwt-keys                 Signing key list + rotation status      (existing)
│
└── Settings (Platform)                                                                       [partial P1.7]
    ├── /platform/settings/billing                    Defaults (grace period, plan, finance email)  [needs settings API — descope to read-only v1 if not ready]
    ├── /platform/settings/notifications              Provider config (Phase 3 read-only)
    └── /platform/settings/security                   Session TTL, password policy, JWT rotation    (existing /platform/jwt-keys)
```

### Tenant context (Tenant Operator Portal)

```
TENANT NAVIGATION
├── /                                Dashboard (KPI cards, charts, recent activity)
├── /login                           Tenant login (slug from subdomain)
├── /forgot-password                 Request reset
├── /reset-password                  Confirm + one-time-modal pattern
│
├── Dashboard
│   └── /                            Overview KPIs (members, savings, loans portfolio, fees collected)
│                                    — aggregates from list endpoints + reporting/* in v1
│                                    — no /me/dashboard endpoint
│
├── Members
│   ├── /members                              List + filters (status)
│   ├── /members/new                          Registration form
│   ├── /members/[id]                         Detail (Tabs: Overview, Savings, Shares, Loans, Guarantor For, Transactions, Audit)
│   ├── /members/[id]/status-change           Status change confirmation (maker-checker)
│   └── (sub-actions launch from member detail: open savings, new loan, record deposit)
│
├── Savings
│   ├── /savings/products                     List + create + edit
│   ├── /savings/products/[id]                Detail
│   ├── /savings/accounts                     List (cross-member)
│   ├── /savings/accounts/new                 Open account (member picker)
│   ├── /savings/accounts/[id]                Detail (Balance card + ledger table)
│   ├── /savings/accounts/[id]/deposit        Deposit form (direct)
│   └── /savings/accounts/[id]/withdraw       Withdrawal form (maker-checker)
│
├── Shares
│   ├── /shares/products                      List + create
│   ├── /shares/accounts                      List
│   ├── /shares/accounts/[id]                 Detail (shares held, total value, transactions)
│   ├── /shares/accounts/[id]/purchase        Purchase form (direct)
│   └── /shares/accounts/[id]/redeem          Redemption form (maker-checker)
│
├── Loans (Credit)
│   ├── /credit/products                      List + create + edit (CRUD)
│   ├── /credit/applications                  List + filters
│   ├── /credit/applications/new              Application wizard (Step 1 borrower, 2 terms, 3 guarantors, 4 review)
│   ├── /credit/applications/[id]             Detail (terms, guarantors, approval status)
│   ├── /credit/applications/[id]/guarantors  Nominate + per-guarantor accept/decline
│   ├── /credit/applications/[id]/approve     Approve (via approval inbox)
│   ├── /credit/applications/[id]/reject      Reject confirmation
│   ├── /credit/loans                         List + filters (member, status)
│   ├── /credit/loans/[id]                    Detail (Tabs: Overview, Schedule, Repayments, Guarantors, Audit)
│   ├── /credit/loans/[id]/disburse           Disburse (direct, idempotency-keyed)
│   ├── /credit/loans/[id]/repay              Post repayment
│   ├── /credit/loans/[id]/write-off          Write-off confirmation (maker-checker if ≥ threshold)
│   ├── /credit/loans/[id]/recover            Record recovery
│   ├── /credit/loans/[id]/restructure        Restructure form (maker-checker quorum=2)
│   ├── /credit/loans/[id]/statement          View + download PDF/CSV
│   └── /credit/payroll-batches
│       ├── /                                 List
│       ├── /new                              Submit JSON or CSV upload
│       └── /[id]                             Detail + reject
│
├── Fees
│   ├── /fees/types                           List + create + edit
│   ├── /fees/assessments                     List + filters (status, member, fee type)
│   ├── /fees/assessments/[id]                Detail (with collections)
│   ├── /fees/assessments/new                 Manual assessment
│   └── /fees/collections/new                 Cash or journal-voucher collection
│
├── Ledger
│   ├── /ledger/accounts                      Chart of accounts (tree)
│   ├── /ledger/accounts/new                  New account
│   ├── /ledger/accounts/[id]                 Account detail with balance + transactions
│   ├── /ledger/journal-entries               List
│   ├── /ledger/journal-entries/[id]          Detail
│   └── /ledger/journal-entries/submit        Manual GL entry form (maker-checker)
│
├── Reports
│   ├── /reports                              Index (5 reports listed)
│   ├── /reports/trial-balance                Date selector + JSON/PDF/CSV download
│   ├── /reports/loan-portfolio               Date + status filter
│   ├── /reports/income-statement             Date range
│   ├── /reports/savings-statement            Member picker + date range
│   ├── /reports/fee-collection               Date range + fee type filter
│   └── /reports/runs                         Materialization history
│
├── Approvals (Tenant)                        Approval inbox + detail (existing /approvals API)
│   ├── /approvals                            Pending (mine, all) + filters
│   ├── /approvals/[id]                       Detail (payload diff, quorum, approve/reject/cancel)
│   └── /approvals/my-submissions
│
├── Audit (Tenant)                                                                            [P1.7-F]
│   ├── /audit                                Search by actor/table/date/operation
│   └── /audit/[id]                           Entry detail with before/after JSON diff
│
├── Billing (Tenant — read-only)              Subscription summary + invoice history (existing /billing/me/*)
│   ├── /billing                              My subscription
│   ├── /billing/invoices                     List
│   └── /billing/invoices/[id]                Detail + PDF download
│
└── Settings (Tenant)                                                                         [P1.7-D]
    ├── /settings/users                       Tenant user mgmt (list/lock/reset/is_admin)
    └── /settings/profile                     My profile (current user; uses /auth/me)
```

### Comparison vs. roadmap's 28-screen reference

Roadmap counted 28 platform-only screens across 7 groups. This inventory has:
- **Platform context:** ~32 screens (added: edit/suspend/impersonate from P1.7, approval inbox, audit viewer split into search+detail, dashboard, ops index)
- **Tenant context:** ~50 screens (entirely additive — roadmap did not scope this)
- **Total:** ~82 screens

Differences from roadmap:
- **Larger because:** the prompt expanded scope to include the tenant operator portal (Members, Savings, Shares, Credit, Fees, Ledger, Reports, Audit, Settings).
- **Larger because:** I enumerated action surfaces (deposit, withdraw, restructure, write-off, suspend, impersonate) as distinct routes/screens; the roadmap counted these inside the detail screens.
- **Phase 1.7 unlocks 11 screens** that the roadmap implicitly assumed existed: platform-side approvals (3), audit viewer (2 × 2 contexts = 4), impersonation flow (1), tenant edit/suspend (2), tenant-user mgmt (1 platform + 1 tenant = 2), dashboard-stats (1).

## 7. Cross-cutting UI surfaces

These are not tied to a single endpoint group; they appear across modules.

1. **Login pages** — platform and tenant, separate paths, each with own forgot-password and reset-confirm flow.
2. **App shell** — header (tenant indicator chip, command palette trigger, notification bell stub, user menu) + sidebar (permission-conditional rendering) + main layout.
3. **Approval inboxes** — platform and tenant variants, cross-cuts every maker-checker operation; built after enough operations exist to validate.
4. **Audit log viewers** — platform and tenant variants (Phase 1.7-F).
5. **Permission-denied screen** — explicit, not a 404 or silent redirect.
6. **Subscription-gate error screens** — 402 (past-due grace expired) and 403 (suspended/cancelled).
7. **Account-suspended screen** — for tenant context only; platform admin context not gated.
8. **Command palette** (Cmd+K) — cmdk wired to a full action registry; first delivery is a stub, real wiring in Part C.
9. **One-time-modal** for password reset tokens — used by both self-service and admin-initiated reset flows.
10. **Pending-approval banner** — composable component shown above any record with an open approval request.
11. **Audit bar** — composable component shown on every entity detail page (last 3 changes + "View full history" link).
12. **Maker-checker confirm dialog** — variant of standard confirm dialog that explicitly states "This creates an approval request, not executes."

## 8. Operational model

- **Subagent-driven execution.** Each sub-plan dispatches one fresh subagent with focused context. Between subagents, the user reviews diff, runs `make -C admin test lint typecheck`, checks Storybook is updated, commits before the next dispatch.
- **No subagent modifies** `CLAUDE.md` (except sub-plan 03 which appends the portal subsection and flips "Next.js 14" → "Next.js 15"), `docs/sacco-design-system-v2.md`, `docs/tokens.css` (the canonical source — sub-plan 04 *copies* it into `admin/packages/ui/src/tokens.css`), or backend code without explicit approval.
- **No subagent touches outside `admin/`** except the four allowed root files: `docker-compose.yml`, `Makefile`, `CLAUDE.md`, `.gitignore`.
- **CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000.** Sub-plans that would exceed propose a split.
- **Each sub-plan reads** this index doc + the design system doc + the API files for the endpoints it consumes + the existing primitives from earlier sub-plans, before writing code.

---

## PART A — Foundation (parallel with Phase 1.7)

These eleven sub-plans only consume endpoints that already exist on `main` today. They can ship in parallel with Phase 1.7 backend work. Each sub-plan below specifies dependencies, complexity, required reading, endpoints consumed, screens implemented (where applicable), and verification.

### Sub-plan 01 — Admin workspace bootstrap

- **Dependencies:** none
- **Complexity:** S (1 day)
- **Required reading:** this index §2, §3, §8; root `package.json` does NOT exist (this is Python project) so this is greenfield
- **Endpoints consumed:** none
- **Screens implemented:** none (scaffolding only)
- **Deliverables:**
  - `admin/package.json` (root, private, workspace manifest)
  - `admin/pnpm-workspace.yaml` with packages: `apps/*`, `packages/*`
  - `admin/turbo.json` with `build`, `test`, `lint`, `typecheck`, `dev` pipelines
  - `admin/.nvmrc` pinned to Node 22 LTS
  - `admin/.npmrc` (`auto-install-peers=true`, `strict-peer-dependencies=true`)
  - `admin/packages/tsconfig/base.json` (TS strict, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`)
  - `admin/packages/eslint-config/index.js` (react, tailwindcss, jsx-a11y plugins)
  - `admin/packages/eslint-config/package.json`
  - `admin/packages/tsconfig/package.json`
- **Verification:** `cd admin && pnpm install` succeeds; `pnpm typecheck` runs (no packages yet so no-op); turbo recognizes the workspace.
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 02 — Docker Compose + Makefile integration

- **Dependencies:** 01
- **Complexity:** S (0.5 day)
- **Required reading:** `docker-compose.yml`, `Makefile`, `.gitignore`, `.env.example`
- **Endpoints consumed:** none
- **Deliverables:**
  - Append `admin` service to `docker-compose.yml` (Node 22, mounts `admin/`, runs `pnpm dev`)
  - Append `admin-dev`, `admin-build`, `admin-test`, `admin-lint`, `admin-typecheck`, `admin-storybook` targets to root `Makefile`
  - Append admin entries to `.gitignore` (`admin/node_modules/`, `admin/.next/`, `admin/**/dist/`, `admin/.turbo/`, `admin/storybook-static/`)
  - `admin/.env.example` (NEXT_PUBLIC_API_BASE_URL, NEXT_PUBLIC_SENTRY_DSN, COOKIE_SECRET, REFRESH_COOKIE_NAME)
- **Verification:** `make admin-dev` boots a Next.js dev server (placeholder); `docker compose up admin` builds.
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 03 — Next.js 15 app scaffold

- **Dependencies:** 01, 02
- **Complexity:** M (2 days)
- **Required reading:** this index §2, §3; `docs/sacco-design-system-v2.md` §1-7 (typography, color, layout, spacing)
- **Endpoints consumed:** none
- **Deliverables:**
  - `admin/apps/portal/` — Next.js 15 App Router scaffold, TypeScript strict
  - Tailwind v4 configured (no separate tailwind.config; uses `@theme inline` block in CSS)
  - `admin/apps/portal/app/layout.tsx` with `<html lang="en">`, font loading (Inter as General Sans fallback), CSS imports
  - `admin/apps/portal/app/page.tsx` — placeholder
  - `admin/apps/portal/package.json`
  - `admin/apps/portal/tsconfig.json` extending `packages/tsconfig/base.json`
  - `admin/apps/portal/.eslintrc.cjs` extending `packages/eslint-config`
  - `admin/apps/portal/next.config.mjs` (strict CSP, output `standalone` for Docker)
  - Prettier config at workspace root
  - Husky pre-commit hook running lint-staged (eslint --fix, prettier --write)
  - **CLAUDE.md update:** in §"Phase 2 — Admin Portal key decisions", change "Next.js 14" to "Next.js 15 + React 19"; in §"Admin portal contracts (do not violate)", append the items A–O from §3 of this index
- **Verification:** `make admin-dev` serves "/" with 200; `pnpm lint` and `pnpm typecheck` are clean; CSP header set; Husky blocks commits with lint errors.
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 04 — `packages/ui` foundation + Storybook

- **Dependencies:** 03
- **Complexity:** M (3 days)
- **Required reading:** `docs/sacco-design-system-v2.md` (full); `docs/tokens.css` (full); shadcn/ui CLI docs
- **Endpoints consumed:** none
- **Deliverables:**
  - Copy `docs/tokens.css` → `admin/packages/ui/src/tokens.css` (canonical → consumed). Sub-plan also writes the policy: tokens.css is editable in `docs/` ONLY; portal copies it. CI verifies the two are byte-identical.
  - `admin/packages/ui/package.json`
  - shadcn/ui init in this package; copy base components: Button, Input, Label, Textarea, Select, Checkbox, Radio, Card, Badge, Dialog, Sheet, Popover, DropdownMenu, Tabs, Tooltip, Toast (sonner), Separator
  - `admin/packages/ui/src/index.ts` re-exports all
  - `admin/packages/ui/.storybook/` configured with `@storybook/nextjs` (Next.js 15 compatible)
  - First stories: Button (5 variants × 3 sizes × 4 states), Input (states from design system), Card (3 variants), Badge (8 semantic variants), Dialog (modal example)
  - Tailwind v4 wired via the `@theme inline` block in tokens.css; consumed by both the portal app and Storybook
- **Verification:** `make admin-storybook` builds; all base-component stories render and pass `pnpm test` (Vitest + RTL smoke tests); accessibility addon runs clean; CI tokens-diff check passes.
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 05 — `packages/api-client` with OpenAPI codegen

- **Dependencies:** 01, 03
- **Complexity:** M (3 days)
- **Required reading:** this index §5; `app/main.py`; `app/core/db.py` (subscription-gate semantics); CLAUDE.md "Billing module contracts" subsection (gate HTTP codes 402/403)
- **Endpoints consumed:** none directly — generates TS types for ALL endpoints
- **Deliverables:**
  - OpenAPI capture script: `admin/scripts/capture-openapi.mjs` boots uvicorn, fetches `/openapi.json`, writes to `admin/packages/api-client/openapi.json`. Run via `pnpm openapi:capture`. The captured spec is committed.
  - `admin/packages/api-client/package.json`
  - `openapi-typescript` codegen → `admin/packages/api-client/src/generated/schema.d.ts`
  - `admin/packages/api-client/src/client.ts` — fetch wrapper:
    - Auto-injects `Authorization: Bearer <access_token>` from in-memory store
    - Auto-injects `X-Tenant-Slug` from current tenant context (set by app shell)
    - Auto-injects `Idempotency-Key` (UUID v7) on POST/PUT/PATCH/DELETE
    - On 401 once: try refresh via `/auth/refresh` or `/platform/auth/refresh`, retry original request once
    - On 402: throw typed `SubscriptionPastDueError`
    - On 403 from gate (detail starts with "Subscription status"): throw typed `SubscriptionSuspendedError`
    - On 5xx: throw typed `ServerError` with request_id for log correlation
  - Per-resource client functions: `platformAuth.login(...)`, `tenants.list(...)`, etc. generated wrappers around the typed paths
  - TanStack Query helpers: `queryKeys`, `useTypedQuery`, `useTypedMutation` (mutations auto-invalidate query keys)
- **Verification:** `pnpm test` covers the wrapper's auth-injection, refresh-on-401 (with MSW), idempotency-key generation, 402/403 typed errors. Generated types compile under strict mode.
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 06 — `packages/schemas` (Zod mirrors)

- **Dependencies:** 01, 05
- **Complexity:** S (1 day)
- **Required reading:** `app/modules/iam/platform_auth/schemas.py`, `app/modules/members/schemas.py`, `app/modules/savings/schemas.py`, `app/modules/credit/schemas.py` (for understanding the shapes; mirror what's needed for forms)
- **Endpoints consumed:** none directly
- **Deliverables:**
  - `admin/packages/schemas/src/auth.ts` — platform + tenant login, refresh, password reset request/confirm
  - `admin/packages/schemas/src/member.ts` — registration (full_name, dob, gender, optional contacts/ID), status-change
  - `admin/packages/schemas/src/savings.ts` — open account, deposit, withdraw
  - `admin/packages/schemas/src/credit.ts` — loan application, repayment, disburse, restructure, write-off
  - `admin/packages/schemas/src/billing.ts` — record-payment, plan create/edit
  - `admin/packages/schemas/src/common.ts` — money (Decimal-as-string with currency), pagination
  - Each schema co-located with TS inferred type
- **Verification:** `pnpm test` covers happy/sad cases per schema; types compile.
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 07 — Auth shell

- **Dependencies:** 03, 04, 05, 06
- **Complexity:** L (5 days)
- **Required reading:** this index §3.C, §3.F, §7.5, §7.9; `app/modules/iam/platform_auth/api.py`; `app/modules/iam/tenant_auth/api.py`; CLAUDE.md "IAM module contracts"
- **Endpoints consumed:**
  - `POST /platform/auth/token`, `/refresh`, `/logout`, `GET /platform/auth/me`
  - `POST /platform/auth/password-reset/request`, `/confirm`
  - `POST /auth/token`, `/refresh`, `/logout`, `GET /auth/me`
  - `POST /auth/password-reset/request`, `/confirm`
- **Screens implemented:**
  - `/platform/login`, `/platform/forgot-password`, `/platform/reset-password`
  - `/login`, `/forgot-password`, `/reset-password` (tenant context, slug from subdomain or selector in dev)
  - `/platform/logout` and `/logout` (POST handler routes)
- **Deliverables:**
  - Next.js middleware (`admin/apps/portal/middleware.ts`):
    - Resolves tenant context: subdomain in production, optional `?tenant=<slug>` query param + cookie in dev
    - Sets `X-Tenant-Slug` header on outgoing API requests (server components)
    - Redirects unauthenticated requests to the correct login page
  - HttpOnly Secure SameSite=Strict cookie for refresh token (set in route handler after login, cleared on logout)
  - In-memory access token store (server-only — passed through React Server Components context)
  - Login forms (RHF + Zod) for platform and tenant
  - Password reset request form (always 204 on success — no enumeration)
  - Password reset confirm form: on success, displays the new credentials (for admin-initiated case) or shows success state (for self-service)
  - One-time-modal pattern reusable component
- **Verification:**
  - Playwright E2E: login → access protected page → access expires → refresh succeeds → logout revokes session (next request 401)
  - Vitest + MSW: covers 401-refresh-retry, lockout response surfacing, anti-enumeration response
  - Manual: CSP header inspection, cookie flags verification (httpOnly, Secure, SameSite=Strict)
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 08 — App shell

- **Dependencies:** 04, 05, 07
- **Complexity:** L (5 days)
- **Required reading:** `docs/sacco-design-system-v2.md` §"Layout System", §"Navigation Structure"; this index §3.G, §7.2, §7.5–7.7
- **Endpoints consumed:** `GET /platform/auth/me`, `GET /auth/me` (already wired in 07)
- **Screens implemented:**
  - Header component (tenant indicator chip, Cmd+K trigger stub, notification bell stub, user menu)
  - Sidebar component (permission-conditional rendering — permissions derived from current user's `is_superuser` / `is_admin` until P1.7-E lands)
  - Main layout for `/platform/(authed)/*` and `/(authed)/*`
  - `/permission-denied` — explicit denial screen
  - `/subscription-past-due` — 402 screen with link to billing
  - `/account-suspended` — 403 (from gate) screen
- **Deliverables:**
  - `apps/portal/app/platform/(authed)/layout.tsx` — platform shell
  - `apps/portal/app/(authed)/layout.tsx` — tenant shell
  - `packages/ui/src/components/Shell/{Header,Sidebar,UserMenu,TenantIndicator,NotificationBellStub,CommandPaletteTrigger}.tsx`
  - Error boundary at the app shell level that catches `SubscriptionPastDueError` and `SubscriptionSuspendedError` from the API client and routes to the corresponding screens
  - Permission-denied page and util
  - Storybook stories for shell components
- **Verification:** Playwright covers: 402 surfaces, 403 surfaces, permission-denied surfaces; visual review against design system §"Layout System"; sidebar collapses below `lg` breakpoint.
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 09 — Display primitives

- **Dependencies:** 04
- **Complexity:** M (3 days)
- **Required reading:** `docs/sacco-design-system-v2.md` §"Money & Number Display", §"Date & Time Display", §"Status Badges", §"Permissions UX"
- **Endpoints consumed:** none
- **Deliverables (all in `packages/ui/src/components/`):**
  - `<Money amount currency />` — currency-prefixed, locale-aware, tabular-nums, decimal precision per currency registry, negative in danger-700
  - `<Percentage value />` — 2 decimals, % suffix, tabular-nums
  - `<Count value />` — thousands separator, no decimals, tabular-nums
  - `<FormattedDate value />` — "28 May 2026"
  - `<FormattedDateTime value />` — "28 May 2026, 14:32" in tenant tz
  - `<AuditTimestamp value />` — includes seconds + timezone abbreviation
  - `<RelativeTime value />` — "2 hours ago", falls back to absolute after 7 days
  - `<StatusBadge variant label />` with mapping helpers from the design system's domain status tables (loan, member, tenant provisioning, fee assessment, approval request, savings account)
  - `<PermissionGuard permission><children /></PermissionGuard>` — hides children if current user lacks permission
  - `requirePermission(permission)` — for server components; throws `PermissionDeniedError` caught by app shell
  - `<TenantCurrencyProvider>` — supplies the tenant's default currency to descendants (`<Money>` uses this if no `currency` prop)
  - Permission resolver (placeholder): maps permission strings → user attribute checks (`is_superuser`, `is_admin`); when P1.7-E ships, swap internals to call the role-based API helpers without touching call sites
- **Verification:**
  - Vitest covers every component with multiple values, edge cases (zero, negative, very large)
  - Storybook stories per component, including all StatusBadge variants
  - Accessibility scan clean
  - Visual review against design system specifications (exact px, weights, colors)
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 10 — DataTable wrapper

- **Dependencies:** 04, 09
- **Complexity:** L (5 days)
- **Required reading:** `docs/sacco-design-system-v2.md` §"Data Tables"; TanStack Table v8 docs; nuqs docs
- **Endpoints consumed:** none directly (consumes the standard list-endpoint shape from §5)
- **Deliverables:**
  - `<DataTable columns data state={...} />` in `packages/ui/src/components/DataTable/`
  - Server-side pagination, sort (single column), filter
  - URL-synced state via nuqs (filter values, sort column, page, density)
  - Column visibility toggle (persisted per-user via cookie)
  - Density toggle (default ↔ compact, persisted)
  - Sticky header on scroll; horizontal scroll for wide tables; first column may be sticky
  - Bulk selection (page-only checkbox + separate "select all matching" affordance)
  - States: empty, loading (skeleton rows — never spinner), error, permission-denied
  - CSV export: client-side from loaded data for v1 (small dataset). Server-rendered CSV is available only via reporting endpoints — sub-plan 29 wires those.
- **Verification:**
  - Vitest covers state synchronization, sort/filter/page changes, density toggle persistence
  - Playwright covers URL state restoration on reload
  - Storybook stories: small data, large data, empty, loading, error
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 11 — Form primitives

- **Dependencies:** 04, 06, 09
- **Complexity:** M (3 days)
- **Required reading:** `docs/sacco-design-system-v2.md` §"Forms", §"Maker-Checker UX Patterns", §"Audit Bar"
- **Endpoints consumed:** none directly
- **Deliverables (all in `packages/ui/src/components/`):**
  - `<FormField>` — wraps RHF Controller + label + help + error display
  - `<MoneyInput>` — right-aligned, currency chip prefix, thousands separators on type, decimal per currency, no spinner
  - `<PercentageInput>` — right-aligned, % suffix, max 2 decimals
  - `<DateInput>` — react-day-picker via shadcn Calendar+Popover; typed input accepts DD/MM/YYYY and YYYY-MM-DD
  - `<DateRangeInput>` — two inputs side-by-side, single calendar with two-month view
  - `<Stepper steps current />` — for multi-step forms (loan application, member onboarding)
  - `<ConfirmDialog />` and `<MakerCheckerConfirmDialog />` (variant explicitly stating "This creates an approval request, not executes")
  - `<AuditBar entityType entityId />` — last 3 changes + "View Full History" modal; degrades to placeholder until P1.7-F (audit query API) ships
  - `<ReadOnlyField value />` — distinct visual treatment from disabled per design system
  - `<MakerCheckerBanner approvalRequestId quorum />` — pending-approval banner for any record with an open approval
  - Draft auto-save hook (`useDraftAutoSave`) — persists form state to localStorage with a debounced save; full restore prompt
- **Verification:**
  - Vitest covers each primitive with valid/invalid inputs and edge cases
  - Storybook stories per primitive, including all states from the design system
  - Accessibility scan clean (labels associated, errors announced via aria-live)
- **No new backend endpoints needed:** ✓ confirmed.

---

## PART B — Feature modules

Each feature module sub-plan implements one nav group (or a coherent slice of a large one). Each declares its Phase 1.7 dependency (if any) and its prerequisite Part A sub-plans.

### Sub-plan 12 — Platform Users module (foundation validator)

- **Dependencies:** 01–11
- **Complexity:** M (3 days)
- **Required reading:** `app/platform_/users/api.py`, `app/platform_/users/service.py`; this index §6 (Platform Users)
- **Endpoints consumed:** `GET|POST /platform/users`, `GET|PATCH /platform/users/{id}`
- **Screens implemented:** `/platform/users` (list), `/platform/users/new`, `/platform/users/[id]`, `/platform/users/[id]/edit`
- **Why first:** smallest platform module, validates Part A foundation end-to-end (DataTable + form + permission + maker-checker pattern for sensitive fields).
- **Verification:** All listed Verification criteria below apply.
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 13 — Tenants list + provisioning wizard

- **Dependencies:** 12
- **Complexity:** L (5 days)
- **Required reading:** `app/platform_/tenants/api.py`, `app/platform_/provisioning/`; CLAUDE.md "Platform_ module contracts"
- **Endpoints consumed:** `GET|POST /platform/tenants`, `GET /platform/tenants/{id}`, `POST /platform/tenants/{id}/retry-provisioning`
- **Screens implemented:** `/platform/tenants` (list), `/platform/tenants/new` (wizard with async-202 + status polling), `/platform/tenants/[id]` (overview)
- **Notable patterns validated:** async 202 + status polling UX; maker-checker pattern for retry; status badges using the tenant provisioning palette
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 14 — Tenants edit/suspend + impersonation entry

- **Dependencies:** 13, **[P1.7-B, P1.7-C]**
- **Complexity:** M (3 days)
- **Required reading:** Phase 1.7 sub-plans 02 and 03 once written
- **Endpoints consumed:** **[P1.7-C]** `PATCH /platform/tenants/{id}`, `POST .../suspend|reactivate|assign-plan`; **[P1.7-B]** `POST /platform/impersonations`, `GET /platform/impersonations/active`
- **Screens implemented:** `/platform/tenants/[id]/edit`, `/platform/tenants/[id]/suspend`, `/platform/tenants/[id]/impersonate`
- **Cross-context UX:** when an impersonation session starts, the user is redirected to the tenant context (the tenant subdomain in prod, or a `/t/<slug>/...` path in dev) with a persistent banner: "Impersonating <Tenant Name> · ends at <time> · End now"
- **No new backend endpoints needed:** ✓ confirmed (consumes P1.7-B, P1.7-C only)

### Sub-plan 15 — Billing Plans + Subscriptions

- **Dependencies:** 12
- **Complexity:** M (4 days)
- **Required reading:** `app/platform_/billing/api.py`, `app/platform_/billing/services/`; CLAUDE.md "Billing module contracts"
- **Endpoints consumed:** `GET|POST /platform/billing/plans`, `GET|PATCH /platform/billing/plans/{id}`; `GET|POST /platform/billing/subscriptions`, `GET .../{id}`, `POST .../cancel`, `POST .../reactivate`
- **Screens implemented:** `/platform/billing/plans`, `/platform/billing/plans/[id]`, `/platform/billing/subscriptions`, `/platform/billing/subscriptions/[id]`, `/platform/billing/subscriptions/[id]/cancel`
- **Notable patterns:** soft vs hard cancel UX (the `mode=at_period_end|immediate` query param surfaces as two distinct buttons with different confirmation copy)
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 16 — Billing Invoices + Payments

- **Dependencies:** 15, **[P1.7-A]**
- **Complexity:** L (5 days)
- **Required reading:** `app/platform_/billing/api.py` (record_payment, reject_payment flows); CLAUDE.md "Billing module contracts" (payment rejection pairing, idempotency, no overpayment)
- **Endpoints consumed:** `GET /platform/billing/invoices`, `GET .../{id}`, `GET .../{id}.pdf`, `POST .../{id}/payments`, `POST .../{id}/void`, `POST /platform/billing/payments/{id}/reject`, `GET /platform/billing/payments/pending-confirmation`; **[P1.7-A]** `POST /platform/approvals/{id}/approve`
- **Screens implemented:** `/platform/billing/invoices`, `/platform/billing/invoices/[id]`, `/platform/billing/invoices/[id]/record-payment`, `/platform/billing/invoices/[id]/void`, `/platform/billing/payments/pending-confirmation`
- **Notable patterns:** payment confirmation flow (maker creates Payment(pending) + ApprovalRequest in one tx → checker approves via platform approvals API → executor confirms payment); paired rejection flow (separate endpoint, not the generic approval reject); inline PDF rendering via iframe
- **No new backend endpoints needed:** ✓ confirmed (consumes P1.7-A).

### Sub-plan 17 — Approval Inbox (Platform)

- **Dependencies:** 11, **[P1.7-A]**
- **Complexity:** M (4 days)
- **Required reading:** Phase 1.7 sub-plan 01 once written; `app/modules/maker_checker/service.py` for understanding payload shape; `docs/sacco-design-system-v2.md` §"Maker-Checker UX Patterns"
- **Endpoints consumed:** **[P1.7-A]** `GET|POST /platform/approvals`, `GET .../{id}`, `POST .../{id}/approve|reject|cancel`
- **Screens implemented:** `/platform/approvals`, `/platform/approvals/[id]`, `/platform/approvals/my-submissions`
- **Notable patterns:** quorum badge ("1 of 2 approvals"); payload-diff renderer (JSON tree with diff annotations); maker-cannot-approve enforcement reflected in UI (button hidden when current user is maker, with explanatory tooltip)
- **No new backend endpoints needed:** ✓ confirmed (consumes P1.7-A).

### Sub-plan 18 — JWT Keys & Operations widgets

- **Dependencies:** 12
- **Complexity:** S (1 day)
- **Required reading:** `app/modules/iam/keys/api.py`, `app/modules/iam/keys/service.py`
- **Endpoints consumed:** `GET /platform/jwt-keys/`
- **Screens implemented:** `/platform/operations`, `/platform/operations/jwt-keys`
- **Notable patterns:** read-only ops widgets that degrade gracefully (outbox depth, beat job timestamps surface "Not yet wired — Phase 5" placeholders)
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 19 — Platform Settings (partial)

- **Dependencies:** 12
- **Complexity:** S (1 day)
- **Required reading:** this index §6 (Settings (Platform))
- **Endpoints consumed:** `GET /platform/jwt-keys/` (for security settings page)
- **Screens implemented:** `/platform/settings/billing` (read-only placeholder until settings API ships), `/platform/settings/notifications` (read-only placeholder until Phase 3), `/platform/settings/security` (live — wraps the JWT keys list with policy callouts)
- **Notable patterns:** explicit "Configurable in next release" empty states with clear messaging
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 20 — Members module

- **Dependencies:** 01–11 (foundation), platform context sub-plans not required
- **Complexity:** M (4 days)
- **Required reading:** `app/modules/members/api.py`, `app/modules/members/service.py`, `app/modules/members/schemas.py`; `docs/sacco-design-system-v2.md` §"Member Profile"
- **Endpoints consumed:** `GET|POST /members`, `GET /members/{id}`, `POST /members/{id}/status-change`
- **Screens implemented:** `/members` (list + status filter), `/members/new` (registration), `/members/[id]` (detail with tabs), `/members/[id]/status-change` (maker-checker)
- **Notable patterns:** tabbed member profile per design system; status-change with reason field; tab "Audit Trail" degrades to placeholder until P1.7-F
- **Why first in tenant context:** smallest tenant module; validates tenant-context auth shell, header tenant indicator, and the MemberPicker pattern reused by Savings/Loans/Fees
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 21 — Savings module

- **Dependencies:** 20
- **Complexity:** M (4 days)
- **Required reading:** `app/modules/savings/api.py`, `app/modules/savings/service.py`; CLAUDE.md "Fees module contracts" (lien-aware available balance)
- **Endpoints consumed:** `GET|POST /savings/products`, `GET /savings/products/{id}`; `POST /savings/accounts`, `GET /savings/accounts/{id}`, `GET .../transactions`, `POST .../deposit|withdraw`
- **Screens implemented:** `/savings/products` (list/new/edit), `/savings/products/[id]`, `/savings/accounts` (list), `/savings/accounts/new`, `/savings/accounts/[id]`, `/savings/accounts/[id]/deposit`, `/savings/accounts/[id]/withdraw`
- **Notable patterns:** account detail uses design system's "Savings Account View" layout (header + KPI row + ledger table); deposit is direct, withdraw is maker-checker; balance shows current vs available (lien-aware)
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 22 — Shares module

- **Dependencies:** 21
- **Complexity:** S (2 days)
- **Required reading:** `app/modules/shares/api.py`, `app/modules/shares/service.py`
- **Endpoints consumed:** `GET|POST /shares/products`, `GET /shares/products/{id}`; `POST /shares/accounts`, `GET /shares/accounts/{id}`, `GET .../transactions`, `POST .../purchase|redeem`
- **Screens implemented:** `/shares/products`, `/shares/accounts`, `/shares/accounts/[id]`, purchase + redeem (maker-checker) sub-flows
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 23 — Credit (Products + Applications + Guarantors)

- **Dependencies:** 22
- **Complexity:** L (6 days)
- **Required reading:** `app/modules/credit/api.py` (products + applications + guarantors sections); `app/modules/credit/services/application.py`, `services/product.py`, `services/guarantor.py`; CLAUDE.md "Credit module contracts" and "Credit module v1b contracts"
- **Endpoints consumed:** `POST|GET|PATCH /credit/products`; `GET|POST /credit/applications`, `GET .../{id}`, `POST .../withdraw|approve|reject`; `POST /credit/applications/{id}/guarantors`, `GET .../guarantors`, `POST /credit/guarantors/{id}/accept|decline`
- **Screens implemented:** `/credit/products` (CRUD), `/credit/applications` (list + new wizard + detail), `/credit/applications/[id]/guarantors`
- **Notable patterns:** multi-step Stepper for the application wizard (borrower → terms → guarantors → review); guarantor lien display (forward reference — full lien column rendered in sub-plan 24 loan detail)
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 24 — Credit (Loans + Schedule + Repayments + Statements)

- **Dependencies:** 23
- **Complexity:** L (6 days)
- **Required reading:** `app/modules/credit/api.py` (loans, repayments, schedule, statements sections); `services/disbursement.py`, `services/repayment.py`, `services/statement.py`
- **Endpoints consumed:** `POST /credit/loans/{application_id}/disburse`; `GET /credit/loans`, `GET .../{id}`; `POST|GET /credit/loans/{id}/repayments`; `GET /credit/loans/{id}/schedule`; `GET /credit/loans/{id}/statement[.pdf]`
- **Screens implemented:** `/credit/loans` (list with filters), `/credit/loans/[id]` (detail with Overview/Schedule/Repayments/Guarantors/Audit tabs), `/credit/loans/[id]/disburse`, `/credit/loans/[id]/repay`, `/credit/loans/[id]/statement`
- **Notable patterns:** loan detail per design system "Loan Detail View"; in-arrears danger banner using design system inline alert pattern; statement PDF preview in iframe
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 25 — Credit (Write-off + Recovery + Restructure)

- **Dependencies:** 24
- **Complexity:** M (4 days)
- **Required reading:** `app/modules/credit/services/write_off.py`, `services/restructuring.py`; CLAUDE.md "Credit module v1b contracts"
- **Endpoints consumed:** `POST /credit/loans/{id}/write-off|recover|restructure`; `GET /credit/loans/{id}/restructurings`
- **Screens implemented:** `/credit/loans/[id]/write-off` (maker-checker if ≥ threshold), `/credit/loans/[id]/recover`, `/credit/loans/[id]/restructure` (maker-checker quorum=2)
- **Notable patterns:** quorum=2 explicitly surfaced in the confirm dialog and approval inbox; recovery is single-step (no MC) per contract; write-off threshold display reflects product configuration
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 26 — Credit (Payroll Batches)

- **Dependencies:** 24
- **Complexity:** M (3 days)
- **Required reading:** `app/modules/credit/services/payroll.py`
- **Endpoints consumed:** `POST /credit/payroll-batches` (JSON), `POST /credit/payroll-batches/csv` (upload), `GET .../{id}`, `POST .../reject`
- **Screens implemented:** `/credit/payroll-batches` (list), `/credit/payroll-batches/new` (JSON + CSV upload tabs), `/credit/payroll-batches/[id]` (detail with per-line status + reject)
- **Notable patterns:** react-dropzone for CSV upload; per-line error display
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 27 — Fees module

- **Dependencies:** 21 (savings dependency — collections can debit savings)
- **Complexity:** M (4 days)
- **Required reading:** `app/modules/fees/api.py`, `app/modules/fees/service.py`; CLAUDE.md "Fees module contracts"
- **Endpoints consumed:** `GET|POST|PATCH /fees/types`; `GET|POST /fees/assessments`, `GET .../{id}`; `POST /fees/collections`
- **Screens implemented:** `/fees/types`, `/fees/assessments` (list + new + detail with collections), `/fees/collections/new`
- **Notable patterns:** collection method picker enforces API contract (cash or journal_voucher only — savings_deduction is automatic)
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 28 — Ledger module

- **Dependencies:** 11 (forms primitive — Manual GL is a complex form)
- **Complexity:** M (4 days)
- **Required reading:** `app/modules/ledger/api.py`, `app/modules/ledger/service.py`
- **Endpoints consumed:** `POST|GET /ledger/accounts`, `GET /ledger/accounts/{id}`; `POST /ledger/journal-entries/submit`, `GET /ledger/journal-entries`, `GET .../{id}`
- **Screens implemented:** `/ledger/accounts` (tree view), `/ledger/accounts/new`, `/ledger/accounts/[id]` (with balance), `/ledger/journal-entries` (list), `/ledger/journal-entries/[id]`, `/ledger/journal-entries/submit` (manual GL form — multi-line with debit=credit validation, maker-checker)
- **Notable patterns:** double-entry form validation (sum debits = sum credits before submit allowed); CoA tree view with collapsible parents
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 29 — Reporting module

- **Dependencies:** 10 (DataTable)
- **Complexity:** L (5 days)
- **Required reading:** `app/modules/reporting/api.py`, `app/modules/reporting/services/`
- **Endpoints consumed:** `GET /reporting/{trial-balance,loan-portfolio,income-statement,savings-statement,fee-collection,runs}` (with JSON/PDF/CSV format support)
- **Screens implemented:** `/reports` (index), `/reports/trial-balance`, `/reports/loan-portfolio`, `/reports/income-statement`, `/reports/savings-statement`, `/reports/fee-collection`, `/reports/runs`
- **Notable patterns:** each report has a date selector (single date or range); JSON view rendered in DataTable; PDF preview in iframe; CSV download direct; "Materialized at: <ts>" indicator using `<AuditTimestamp>`; 404 handling shows last successful run timestamp from the API's error detail
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 30 — Approval Inbox (Tenant)

- **Dependencies:** 11
- **Complexity:** M (3 days)
- **Required reading:** `app/modules/maker_checker/api.py`, `app/modules/maker_checker/service.py`
- **Endpoints consumed:** `GET|POST /approvals`, `GET .../{id}`, `POST .../{id}/approve|reject|cancel`
- **Screens implemented:** `/approvals`, `/approvals/[id]`, `/approvals/my-submissions`
- **Notable patterns:** identical UX to platform approval inbox (sub-plan 17) but against tenant API; payload-diff renderer reused
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 31 — Audit Viewer (both contexts)

- **Dependencies:** 11, **[P1.7-F]**
- **Complexity:** M (4 days)
- **Required reading:** Phase 1.7 sub-plan 06 once written; `app/core/audit/` for audit log schema
- **Endpoints consumed:** **[P1.7-F]** `GET /platform/audit-log`, `GET /platform/audit-log/{id}`, `GET /audit-log`, `GET /audit-log/{id}`
- **Screens implemented:** `/platform/audit`, `/platform/audit/[id]`, `/audit`, `/audit/[id]`
- **Notable patterns:** before/after JSON diff renderer (same component as approval payload diff); filters: actor, table, operation, date range, record_id; `<AuditTimestamp>` everywhere; this unlocks the `<AuditBar>` primitive (sub-plan 11) to surface live data instead of placeholder
- **No new backend endpoints needed:** ✓ confirmed (consumes P1.7-F).

### Sub-plan 32 — Tenant Settings

- **Dependencies:** 20, **[P1.7-D]**
- **Complexity:** M (3 days)
- **Required reading:** Phase 1.7 sub-plan 04 once written
- **Endpoints consumed:** **[P1.7-D]** `GET|POST /platform/tenants/{id}/users`, `PATCH .../users/{uid}`, `POST .../users/{uid}/password-reset`; `GET /auth/me` (existing — for profile)
- **Screens implemented:** `/settings/users` (tenant user list + create + edit + admin-initiated password reset with one-time-modal), `/settings/profile`
- **Notable patterns:** the admin password-reset endpoint returns the token in response body — UI shows it in one-time-modal exactly like platform user reset
- **No new backend endpoints needed:** ✓ confirmed (consumes P1.7-D).

### Sub-plan 33 — Tenant Billing (read-only)

- **Dependencies:** 15 (shares billing PDF rendering)
- **Complexity:** S (1 day)
- **Required reading:** `app/platform_/billing/api.py` (tenant_router)
- **Endpoints consumed:** `GET /billing/me/subscription`, `GET /billing/me/invoices`, `GET .../{id}`, `GET .../{id}.pdf`
- **Screens implemented:** `/billing` (my subscription), `/billing/invoices` (list), `/billing/invoices/[id]` (detail + PDF download)
- **No new backend endpoints needed:** ✓ confirmed.

---

## PART C — Cross-cutting

These ship after enough modules exist to validate the cross-cutting surface.

### Sub-plan 34 — Platform Dashboard

- **Dependencies:** Most of Part B platform; **[P1.7-G]**
- **Complexity:** M (3 days)
- **Required reading:** Phase 1.7 sub-plan 07 once written; design system §"Dashboard Layout"
- **Endpoints consumed:** **[P1.7-G]** `GET /platform/admin/dashboard-stats`; falls back to parallel calls if endpoint unavailable
- **Screens implemented:** `/platform` (dashboard)
- **Notable patterns:** KPI row (tenants by status, MRR, overdue invoices, pending approvals), charts row (subscriptions trend, billing collections), operational data (recent activity, pending approvals widget)
- **No new backend endpoints needed:** ✓ confirmed (consumes P1.7-G).

### Sub-plan 35 — Tenant Dashboard

- **Dependencies:** Most of Part B tenant
- **Complexity:** M (3 days)
- **Required reading:** design system §"Dashboard Layout"
- **Endpoints consumed:** existing list/summary endpoints from members, savings, credit, fees, reporting
- **Screens implemented:** `/` (tenant dashboard)
- **Notable patterns:** aggregates from list endpoints + reporting summaries; KPI row (total members, total savings, outstanding loans, members in arrears); recent activity widget; degrades when reports haven't been materialized
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 36 — Command palette (real)

- **Dependencies:** Most of Part B
- **Complexity:** M (3 days)
- **Required reading:** cmdk docs; design system §"Command Palette"
- **Endpoints consumed:** existing search-friendly list endpoints
- **Deliverables:** action registry for every nav item + major action; recent-records list (last 10 viewed, persisted in localStorage); search-by-name across members, loans, transactions
- **Verification:** Playwright covers keyboard navigation flows
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 37 — Keyboard shortcuts + bulk operations

- **Dependencies:** 36
- **Complexity:** S (2 days)
- **Required reading:** design system §"Accessibility"
- **Deliverables:** registered shortcuts (Cmd+K palette, ? for shortcut cheatsheet, g+d for dashboard, g+m for members, etc.); table bulk-selection actions (export selected, bulk-status-change scaffold)
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 38 — Draft auto-save polish

- **Dependencies:** 11, several Part B sub-plans that ship long forms
- **Complexity:** S (1 day)
- **Required reading:** design system §"Multi-Step Forms"
- **Deliverables:** restore-prompt UX, draft expiration (24h), per-form clearance, draft inbox at `/drafts` (lists pending drafts across forms)
- **No new backend endpoints needed:** ✓ confirmed.

---

## PART D — Infrastructure & Quality

### Sub-plan 39 — GitHub Actions CI

- **Dependencies:** 01–11
- **Complexity:** M (2 days)
- **Required reading:** existing `.github/workflows/`
- **Deliverables:** `.github/workflows/portal.yml` (lint, typecheck, vitest, Playwright headless against built portal + MSW, Storybook build artifact, bundle analysis with size budget gates, tokens.css diff check vs `docs/tokens.css`)
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 40 — Sentry integration

- **Dependencies:** 03
- **Complexity:** S (1 day)
- **Deliverables:** `@sentry/nextjs` configured; release tagging tied to git SHA; user context excluded by default (only request_id, route, error)
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 41 — Env & secrets management

- **Dependencies:** 02
- **Complexity:** S (1 day)
- **Deliverables:** documented env var schema; runtime validation via Zod on app start; `.env.local.example`; secrets handling guidance in `docs/portal-secrets.md`
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 42 — Portal-specific custom skills

- **Dependencies:** Most of Part B
- **Complexity:** M (2 days)
- **Required reading:** `.claude/skills/new-module/SKILL.md` (existing pattern); `.claude/skills/impeccable/SKILL.md` (existing pattern)
- **Deliverables:** new skills at `.claude/skills/`:
  - `portal-new-page` — scaffolds a new route + page + loader pattern
  - `portal-form` — scaffolds RHF+Zod form aligned with primitives
  - `portal-permission-check` — checks a route for missing `PermissionGuard`/`requirePermission` calls
  - `portal-table` — scaffolds a DataTable with proper URL state + filters
  - `portal-audit-bar` — checks an entity detail page for missing `<AuditBar>`
  - `portal-money-display` — checks JSX for raw money formatting violations
- **Verification:** each skill works on an example route
- **No new backend endpoints needed:** ✓ confirmed.

### Sub-plan 43 — Pre-deploy security review

- **Dependencies:** Everything else
- **Complexity:** L (5 days, mostly external)
- **Required reading:** OWASP Top 10; CLAUDE.md §"Admin portal contracts"
- **Deliverables:** internal checklist run (CSP audit, cookie audit, auth flow audit, XSS audit, third-party-script audit); external pentest is Phase 9 of the roadmap
- **No new backend endpoints needed:** ✓ confirmed.

---

## 9. Standard verification criteria (every sub-plan)

Every sub-plan that ships code is considered complete only when ALL of the following pass:

1. **Lint clean:** `pnpm lint` no errors
2. **Type-check clean:** `pnpm typecheck` no errors under strict mode
3. **Tests pass:** `pnpm test` green; new components have Vitest unit tests with relevant edge cases
4. **Storybook updated:** new components have stories with all variants from the design system
5. **Accessibility scan clean:** Storybook a11y addon and per-component @axe-core/react checks pass
6. **Visual review against design system:** sub-plan reviewer (the user) opens Storybook and the live app, confirms specs (heights, radii, colors, spacing) match `docs/sacco-design-system-v2.md`
7. **No new backend endpoints introduced:** sub-plan diff shows zero changes outside `admin/` (with the four allowed root-file exceptions). CI enforces this.
8. **Playwright coverage:** every user-visible interaction has at least one E2E test that exercises the happy path against the running FastAPI (or MSW-mocked equivalent)
9. **PDF/CSV preview check:** sub-plans that touch report or invoice rendering test against a real WeasyPrint render and a CSV download

## 10. Effort estimate

Rough estimates assume one full-time frontend engineer per sub-plan, with the user as reviewer between sub-plans. Phase 1.7 runs in parallel with one backend engineer.

| Part | Sub-plans | Effort |
|------|-----------|--------|
| A — Foundation | 01–11 | ~3.5 weeks |
| B — Feature Modules | 12–33 | ~7 weeks |
| C — Cross-cutting | 34–38 | ~2 weeks |
| D — Infrastructure & Quality | 39–43 | ~1.5 weeks |
| **Total (Phase 2)** | 43 | **~14 weeks single-engineer; ~10 weeks with two engineers in parallel after Part A** |

Phase 1.7 ships in parallel with Part A and gates a subset of Part B sub-plans. Phase 1.7 is ~3 weeks of backend work.

End-to-end: **~14 weeks calendar time** with the suggested staffing (1 FE + 1 BE working in parallel during the first 3 weeks, then 2 FE working in parallel through Parts B/C/D, with BE returning to other roadmap phases).

---

## 11. Open items deferred to Phase 2 v2

Items deliberately out of v1 scope:

- **Notifications integration** — bell stubbed; real Phase 3 integration ships when Notifications framework is ready
- **Server-rendered CSV for large list exports** — v1 uses client-side from loaded data; large exports use the reporting endpoints already
- **Multi-currency** — currency registry exists; portal renders the tenant's default; multi-currency tenants are post-v1
- **Bulk-action mutation endpoints** — e.g., "suspend N tenants" — v1 does these one at a time; bulk-server endpoints are roadmap §5.2.2 "if needed"
- **Mobile/USSD member-facing app** — entirely separate phase, not on this roadmap
- **External pentest** — Phase 9 of the roadmap; this index's sub-plan 43 only ships the internal security review

---

## 12. What happens next

1. **You review this index.** Approve, request changes, or split it.
2. **Phase 1.7 gets its own index** — separate scoping session. The 7 Phase 1.7 sub-plans named in §4 are the starting list.
3. **Sub-plan 01 dispatches first** — one fresh subagent, focused context, producing the workspace bootstrap. You review the diff between subagents.
4. **Each sub-plan after that** is generated one at a time with your approval between each, exactly as `superpowers:subagent-driven-development` prescribes.

Stop. Awaiting your review.
