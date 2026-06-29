# Member Self-Service — Design

**Date:** 2026-06-29
**Status:** Approved (brainstorming), pending implementation plan
**Phase:** Member self-service (extends Phase 4a/4b member auth + read-only portal)

## Summary

Members are **read-only** in v1 (see `app/modules/*` member contracts and the
Phase 4a/4b specs). This phase introduces a constrained set of **member-initiated
writes** plus a read-only progress view and a document download, delivered as one
cohesive "member self-service" capability and built incrementally:

1. **See loan application progress** — member-scoped read of their own applications.
2. **Apply for loans** — member submits an application that flows into the existing
   operator approval workflow.
3. **Complete KYC** — member submits KYC data into an operator review queue.
4. **Request full statement download** — member downloads a consolidated PDF on demand.

The member portal (a fourth audience inside `admin/apps/portal`) gains write surfaces
for the first time; the FastAPI backend gains a small, tightly-scoped member-write
layer.

## Decisions (from brainstorming)

- **Scope:** design all four as one phase; implement in dependency order.
- **KYC content:** structured fields only — **no document/photo uploads** (no file-storage
  subsystem is introduced). Document upload is explicitly out of scope and deferred to a
  future phase.
- **KYC review model:** a purpose-built **submission queue**. Member edits create a
  pending `kyc_submission`; an operator approves (fields are written to the member record)
  or rejects (with a reason). Members never directly overwrite identity fields.
- **Architecture:** dedicated member-write surfaces + a KYC review queue. Loan apply
  **reuses the existing operator approval** (`credit.approve_application` maker-checker)
  unchanged. KYC review does **not** ride on maker-checker (member-as-submitter does not
  fit the staff maker/checker model; KYC is single-reviewer).
- **Statement:** synchronous, consolidated PDF (savings + shares + loans + fees) rendered
  on demand via the existing WeasyPrint pipeline; optional date range.
- **KYC approve vs. activation:** two separate operator steps. KYC approval writes fields
  only; member **status** changes (e.g. `pending → active`) remain the existing
  maker-checker status-change flow (CLAUDE.md rule 7).

## Out of scope (v1 of this phase)

- KYC document / photo uploads and any object-storage subsystem.
- Member-side maker-checker / quorum.
- Guarantor nomination by members during loan apply (operators manage guarantors at review).
- Async statement generation + notification delivery (depends on Phase 3 notifications).
- Member-initiated edits to financial records, savings/shares transactions, or repayments.

## Backend design

### Data model

**New tenant-schema table `kyc_submissions`** (declares no schema; resolved at runtime via
`search_path`, per project conventions):

- `id` (PK)
- `member_id` (FK → `members.id`)
- `status` — `pending` | `approved` | `rejected`
- `submitted_at`, `reviewed_by` (tenant_user id, nullable), `reviewed_at` (nullable),
  `rejection_reason` (nullable)
- Proposed editable-field snapshot: `phone`, `email`, `physical_address`,
  `national_id_number`, `id_document_type`, `id_document_number`, `id_issued_date`,
  `id_expiry_date`, `next_of_kin_name`, `next_of_kin_phone`, `occupation`
- Partial unique index: at most one `pending` submission per `member_id` (resubmitting
  supersedes the open one). Rows are not deleted; review transitions are recorded in place.

**New nullable `members` columns:** `next_of_kin_name`, `next_of_kin_phone`, `occupation`
(KYC enrichment; nullable, backfill-free).

Migration: `alembic/tenant/`.

### Services

**`MemberSelfService` (members module, member-facing):**

- `get_kyc(member_id)` → current member KYC fields + latest submission status
  (`none`/`pending`/`approved`/`rejected` + reason).
- `submit_kyc(member_id, data)` → creates a `pending` submission, superseding any open one.
  Identity-field uniqueness (`national_id_number`) is **not** enforced here; it is surfaced
  at approval time. Members never write identity fields directly to the member row.

**`KycReviewService` (members module, operator-facing):**

- `list_pending()`, `get(id)`.
- `approve(id, reviewer)` → applies the proposed fields to the member row via the existing
  audited `MemberService` write path (diffs to `audit_log`). Raises a conflict if the
  proposed `national_id_number` now collides with another member (→ HTTP 409).
- `reject(id, reviewer, reason)` → marks the submission `rejected`, stores the reason.
- Activation is **not** performed here. After KYC approval the operator activates the
  member through the existing maker-checker status-change flow.

**Member loan apply (credit module):** a thin member-facing wrapper over the existing
`ApplicationService.create_application`:

- Sets `member_id = current_member.id`; derives `disbursement_destination` from the product
  (`member_savings` if allowed, else the first allowed destination); leaves
  `disbursement_account_id = NULL` for the operator to finalize at approval/disbursement.
- Guards: member must be `status='active'`; product must be active.
- Existing service validation (product min/max amount & term) is reused unchanged. The
  resulting `submitted` application flows into the **unchanged** operator approval
  (`credit.approve_application` maker-checker). No new approval path is added.

**Consolidated statement (reporting/credit):** renders one PDF scoped to `current_member`
covering savings (accounts, balances, transactions), shares, loans (with schedules), and
fees, with an optional `from`/`to` range, via the existing WeasyPrint pipeline. `format=html`
returns the same content for in-browser preview.

### API surface

Member-scoped (gated by `CurrentMember` + subscription gate; `aud="member:<slug>"`; never
accept a client-supplied member_id; cross-member access → 404):

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/member/me/kyc` | Current KYC fields + latest submission status |
| `POST` | `/member/me/kyc` | Submit/resubmit KYC (creates/supersedes a `pending`); `Idempotency-Key` honored |
| `GET`  | `/member/loan-applications` | List the member's own applications (status + timeline) |
| `GET`  | `/member/loan-applications/{id}` | One application; cross-member → 404 |
| `POST` | `/member/loan-applications` | Submit an application (member must be `active`); `Idempotency-Key` honored |
| `GET`  | `/member/statement?from=&to=&format=pdf\|html` | Consolidated statement; streams `application/pdf` or HTML preview |

Operator-scoped (gated by `CurrentTenantUser` + `members.write`-level permission):

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/members/kyc-submissions?status=pending` | Review queue |
| `GET`  | `/members/kyc-submissions/{id}` | One submission (proposed vs. current) |
| `POST` | `/members/kyc-submissions/{id}/approve` | Apply fields to member (audited); 409 on national_id collision |
| `POST` | `/members/kyc-submissions/{id}/reject` | Reject with reason |

### Error / status semantics (fixed contracts)

- Member applying while not `active` → **409** ("Your membership must be active to apply").
- KYC submit while a `pending` submission exists → supersede it; **200/201**, not an error.
- Cross-member access anywhere → **404** (never 403), consistent with existing member contracts.
- KYC approve with a now-duplicate `national_id_number` → **409**, naming the conflict to the operator.
- Statement with no data in range → valid empty-state PDF, **200**.
- Loan apply outside product min/max amount or term → **422** from the existing application service.

### Audit

- Member submissions audit with `actor_type='member'` (member auth context, per existing
  member-auth contracts).
- Operator approve/reject and the field-application write audit as `actor_type='tenant_user'`.

## Portal design

### Member portal (write surfaces; forms via `FormDialog` + RHF + Zod, money via `MoneyInput`)

- **Profile → KYC section.** Shows current KYC fields and a status banner:
  - *none* → "Complete your KYC" CTA.
  - *pending* → "Under review" (form read-only).
  - *rejected* → reason + "Resubmit".
  - *approved* → confirmation.
  "Complete/Edit KYC" opens a `FormDialog`.
- **Loans page → "Apply for loan"** opens a `FormDialog` (product select shows that product's
  min/max amount & term as helper text; fields: amount, term, purpose). Submit → toast; the
  application appears in the Applications section.
- **Loans page → "Applications" section** — a `DataTable` of the member's applications with a
  `StatusBadge`. Each row opens a detail view rendering a **`Stepper`** for progress
  (`Submitted → Under review → Approved/Rejected → Disbursed`), showing decided amount/term or
  the rejection reason.
- **New nav item "Statements"** (member nav: Dashboard / Savings / Shares / Loans / Fees /
  **Statements** / Profile): a date-range form + "Download PDF" hitting `/member/statement`.

### Operator portal

- **Members → "KYC submissions"** review screen: a `DataTable` of pending submissions; the
  detail page shows the **proposed-vs-current diff**; **Approve** (`ConfirmDialog`, writes
  fields) and **Reject** (`ConfirmDialog` with a required reason). Activation remains the
  existing separate status-change action.

### Schemas

Backend Pydantic in each module's `schemas.py`; portal Zod in `@sacco/schemas`:
`KycSubmissionIn/Out`, `MemberLoanApplicationIn`, reuse `LoanApplicationOut`. The statement
response is binary (no schema).

## Testing (TDD per conventions)

- **Backend pytest:** KYC submit + supersede; approve applies fields + audits; reject;
  national_id 409 on approve; member apply happy path; active-guard 409; product min/max 422;
  cross-member 404 (applications + statement); statement renders including an empty range.
- **Portal vitest:** KYC form states (none/pending/rejected); apply-form validation and
  product min/max helper text; applications progress rendering; operator review approve/reject.

## Build sequence (incremental, dependency order)

1. **Application progress** — member read endpoints (`GET /member/loan-applications[/{id}]`)
   + portal Applications view. Lowest risk; mostly extends the read API.
2. **Loan apply** — `POST /member/loan-applications` + portal apply modal.
3. **KYC** — `kyc_submissions` table + migration, member submit endpoint, operator review
   service/endpoints, portal KYC section + operator review screen.
4. **Statement** — `GET /member/statement` + portal download.

## Contract changes

Update the member-contracts block in `CLAUDE.md` to permit exactly these writes and codify
the invariants:

- Members may write **only**: a KYC submission (`POST /member/me/kyc`) and a loan application
  (`POST /member/loan-applications`). No other member mutations.
- Members never write identity fields directly; KYC fields are applied to the member record
  only by an operator approving a `kyc_submission`.
- KYC review is single-reviewer and **not** maker-checker; member status changes remain
  maker-checker. Loan applications reuse the existing operator approval unchanged.
- Member loan apply requires `status='active'`; cross-member access returns 404; the member
  statement is always scoped to `current_member`.
- Document/photo upload and async statement generation remain out of scope.
