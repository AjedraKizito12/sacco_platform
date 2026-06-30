# KYC Fulfilment Tracking (SACCO + Member) — Design

**Date:** 2026-06-30
**Status:** Approved (brainstorming), pending implementation plan
**Phase:** Extends Phase 2 (admin portal), Phase 4a/4b (member auth + portal), and the
2026-06-29 Member Self-Service design.

## Summary

When a platform admin provisions a SACCO tenant, only the bare minimum (slug, name,
optional admin email) is captured. There is no place to record or track the SACCO's own
registration / regulatory KYC, and no measure of how complete it is. Members have KYC
columns today, but completeness is invisible and the configurable bar for "complete" does
not exist.

This effort introduces:

1. A **shared, reusable KYC completion tracker** that, given an entity's field values and
   an effective required-field set, computes a completion percentage, a missing-items
   checklist, and an `is_complete` flag.
2. **SACCO (tenant) organization KYC** — a singleton org profile the tenant admin fills in,
   self-attested, with a platform-settable `verified` flag (no full review queue).
3. **Member KYC** — a per-tenant configurable required set, the member submit → operator
   review write path (the 2026-06-29 spec's increment 3), and the tracker driving the
   member's "what's still missing" experience.

KYC completion is **informational only** in v1: it is computed, surfaced, and nudged, but
it gates nothing. Member activation (maker-checker) and tenant operation are unchanged.

## Decisions (from brainstorming)

- **Scope:** SACCO org KYC is net-new; the shared completion tracker is new and applied to
  both SACCO and members. Member submit/review follows the already-approved 2026-06-29
  Member Self-Service design (its increment 3) and is **built as part of this effort**.
- **SACCO review model — hybrid:** the tenant admin self-attests org KYC (direct write, no
  review queue). Completeness is derived from the required-field set. A platform-settable
  `verified` flag/timestamp records platform verification, which can happen later without a
  review-queue subsystem.
- **Requirements — fixed catalog with toggles:** there is a known catalog of KYC fields per
  entity type. Admins toggle which catalog fields are required for "complete". Some fields
  are **locked** (always required, not toggleable — the hard minimums). No arbitrary custom
  fields, no dynamic field definitions.
- **Config ownership:** the **platform** owns the SACCO required set (global, applies to all
  tenants). Each **tenant** owns its member required set (per-tenant).
- **Gating — none:** informational/nudge only. No new gates; existing subscription gate and
  maker-checker activation are untouched.

## Out of scope (v1)

- Any hard gate keyed off KYC completeness (activation, transacting, subscription).
- KYC document / photo uploads or any object-storage subsystem (consistent with the
  2026-06-29 spec).
- Arbitrary custom / dynamic KYC field definitions (only the fixed catalog + required
  toggles).
- A full platform-side SACCO review queue (the `verified` flag is the v1 mechanism).
- A platform tenants-list "incomplete KYC" badge and dashboard aggregate count. These need
  per-tenant cross-schema reads; v1 keeps platform oversight to the per-tenant detail view.
  Explicitly deferred, not forgotten.
- Member-side maker-checker / quorum for KYC (KYC review stays single-reviewer per the
  2026-06-29 spec).

## Architecture

Three layers, each independently understandable and testable:

1. **Core tracker (`app/core/kyc/`)** — pure computation, no DB, no I/O. Depends on nothing
   in `app/modules` or `app/platform_`. Consumed by both the members module and the
   platform SACCO surfaces.
2. **SACCO org KYC** — values in the tenant schema (`organization_profile` singleton);
   required-set config in the platform schema (`platform.sacco_kyc_requirements`).
3. **Member KYC** — required-set config in the tenant schema (`member_kyc_requirements`);
   submission/review per the 2026-06-29 spec.

### 1. Core tracker — `app/core/kyc/`

`catalog.py`:

```python
@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    locked: bool          # always required; toggles ignored
    default_required: bool # default when no override present
```

Two module-level catalogs: `SACCO_KYC_CATALOG` and `MEMBER_KYC_CATALOG` (see field lists
below). The catalog is the single source of truth for which keys exist and which are locked.

`completion.py`:

```python
def compute_completion(
    values: Mapping[str, object | None],
    catalog: Sequence[FieldSpec],
    required_overrides: Mapping[str, bool],
) -> KycCompletion: ...
```

- Effective-required for a field = `spec.locked or required_overrides.get(spec.key, spec.default_required)`.
- "Present" = value is not `None` and, for strings, `str(value).strip() != ""`.
- `required_overrides` only affects non-locked keys; unknown keys in the override map are
  ignored.

`KycCompletion` (frozen dataclass) returns:

- `items: list[FieldStatus]` where `FieldStatus = {key, label, required: bool, present: bool}`
  — the full catalog, for rendering a checklist.
- `required_total: int`, `required_present: int`
- `percent: int` — `round(required_present / required_total * 100)`; `100` when
  `required_total == 0`.
- `missing_required: list[str]` — required keys not present.
- `is_complete: bool` — `missing_required == []`.

Pure and synchronous. No imports from `app/modules` or `app/platform_`.

### 2. SACCO org KYC

**Catalog (`SACCO_KYC_CATALOG`):**

| key | locked | default_required |
|-----|--------|------------------|
| `legal_name` | yes | — |
| `registration_number` | yes | — |
| `registered_address` | yes | — |
| `primary_contact_name` | yes | — |
| `primary_contact_email` | yes | — |
| `registration_date` | no | yes |
| `regulator_name` | no | yes |
| `license_number` | no | yes |
| `tax_id` | no | yes |
| `primary_contact_phone` | no | yes |
| `postal_address` | no | yes |
| `district_region` | no | yes |
| `country` | no | yes |

**Tenant-schema model `organization_profile`** (declares no schema; resolved at runtime via
`search_path`, per project conventions). Singleton — at most one row per tenant schema.

- `id` (PK)
- one nullable column per catalog field key above (`legal_name`, … `country`)
- `verified` (bool, default false), `verified_at` (nullable), `verified_by_platform_user_id`
  (nullable UUID — references a `platform.platform_users` id; stored as a bare UUID, no
  cross-schema FK)
- `created_at`, `updated_at`
- `AuditableMixin` (writes before/after diffs to the tenant `audit_log`)
- Singleton enforcement: a `singleton` boolean column defaulting `true` with a unique
  constraint, so a second insert fails. The service uses get-or-create.

Lazily get-or-created on first read; no provisioning change, no backfill. Migration in
`alembic/tenant/`.

**Platform-schema config `platform.sacco_kyc_requirements`** (`__table_args__ = {"schema":
"platform"}`):

- `field_key` (PK, text), `is_required` (bool)
- Override rows only. Absent key → catalog default. Locked keys ignore any row.

**`OrganizationKycService`** (lives in a new `app/modules/organization/` module — tenant
context):

- `get(session)` → get-or-create the singleton; returns values + the latest computed
  completion (requirements read from `platform.sacco_kyc_requirements`).
- `upsert(session, data, actor)` → writes provided values via the audited path. If any
  catalog value materially changes, set `verified=false`, clear `verified_at` /
  `verified_by_platform_user_id` (changed data must be re-verified).
- `set_verified(session, verified, platform_user_id)` → flips the flag. **Verify is only
  permitted when the current completion `is_complete`** (raise a domain error → HTTP 409
  otherwise). Used by the platform endpoints via `get_session_for_tenant_schema`.

**`SaccoKycRequirementsService`** (platform context): `get()` → catalog + effective required
map; `replace(overrides)` → replaces the override rows in one transaction (locked keys
rejected/ignored).

### 3. Member KYC

**Catalog (`MEMBER_KYC_CATALOG`):**

| key | locked | default_required |
|-----|--------|------------------|
| `full_name` | yes | — |
| `date_of_birth` | yes | — |
| `gender` | yes | — |
| `phone` | no | yes |
| `email` | no | yes |
| `physical_address` | no | yes |
| `national_id_number` | no | yes |
| `id_document_type` | no | yes |
| `id_document_number` | no | yes |
| `id_issued_date` | no | no |
| `id_expiry_date` | no | no |
| `next_of_kin_name` | no | yes |
| `next_of_kin_phone` | no | yes |
| `occupation` | no | no |

Locked keys are the existing NOT NULL member columns. `next_of_kin_name`,
`next_of_kin_phone`, `occupation` are the new nullable columns added by the 2026-06-29 spec.

**Per-tenant config `member_kyc_requirements`** (tenant schema; override rows only, same
shape as the platform table). Operator-owned.

**Submission / review** — exactly as the 2026-06-29 Member Self-Service design specifies:
`kyc_submissions` table, the three new member columns, member submit endpoints, operator
review queue + approve/reject, `national_id` 409-on-approve. This design does not restate
those mechanics; it adds the tracker and the per-tenant required-set config on top, and the
member/operator KYC views render the completion checklist computed against the per-tenant
effective member requirements.

## API surface (new)

**Operator (tenant admin; `CurrentTenantUser`/`CurrentAdmin`, subscription-gated):**

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/organization/kyc` | SACCO org values + completion |
| `PUT` | `/organization/kyc` | Upsert org values (self-attested, audited); resets `verified` on material change; `Idempotency-Key` honored |
| `GET` | `/members/kyc-requirements` | Member catalog + effective required toggles |
| `PUT` | `/members/kyc-requirements` | Replace per-tenant member required overrides |
| `GET` | `/members/kyc-submissions[?status=pending]` | Member KYC review queue (2026-06-29 spec) |
| `GET` | `/members/kyc-submissions/{id}` | One submission, proposed-vs-current |
| `POST` | `/members/kyc-submissions/{id}/approve` | Apply fields (audited); 409 on national_id collision |
| `POST` | `/members/kyc-submissions/{id}/reject` | Reject with reason |
| `GET` | `/members/{id}/kyc` | One member's values + completion (operator member-detail card) |

**Platform (`CurrentAdmin`):**

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/platform/kyc/sacco-requirements` | SACCO catalog + global effective required |
| `PUT` | `/platform/kyc/sacco-requirements` | Replace global SACCO required overrides |
| `GET` | `/platform/tenants/{id}/kyc` | SACCO values + completion + verified (via `get_session_for_tenant_schema`) |
| `POST` | `/platform/tenants/{id}/kyc/verify` | Set `verified=true`; **409 if not `is_complete`**; tenant `audit_log` `actor_type='platform_user'` |
| `POST` | `/platform/tenants/{id}/kyc/unverify` | Set `verified=false` |

**Member (`CurrentMember`, subscription-gated; 2026-06-29 spec):**

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/member/me/kyc` | Current values + completion + latest submission status |
| `POST` | `/member/me/kyc` | Submit/resubmit KYC (creates/supersedes a `pending`) |

### Error / status semantics (fixed contracts)

- Verify a SACCO whose org KYC is not complete → **409** (names the missing requirement
  count).
- `PUT /organization/kyc` with any material value change while `verified=true` → succeeds,
  silently resets `verified=false` (re-verification required).
- Cross-tenant / cross-member access → **404** (never 403), consistent with existing
  contracts.
- KYC completion gates nothing → no new 402/403 paths.
- Member KYC submit/approve/reject semantics → per the 2026-06-29 spec (supersede on
  resubmit; 409 on national_id collision at approve).

### Cross-schema read note

Operator handlers computing SACCO completion read `platform.sacco_kyc_requirements` from a
tenant-context session. This reuses the established pattern in `get_tenant_session`, where
the subscription gate already issues a `platform.tenants ⋈ platform.subscriptions` query
within tenant request handling. Platform handlers reaching into a tenant's
`organization_profile` use the existing `get_session_for_tenant_schema(tenant_id)`
dependency (the same one `tenant_users_admin` uses).

## Portal design

### Operator portal
- **"Organization KYC" page** — a `FormField`/RHF/Zod form over the SACCO catalog, a
  completion progress indicator (percent + checklist of missing items), and a `verified`
  badge (read-only; set by the platform). Money/date primitives per the design system.
- **Settings → "Member KYC requirements"** — toggles for the non-locked member catalog
  fields (locked fields shown disabled/checked). Writes `PUT /members/kyc-requirements`.
- **Member detail** — a KYC completion card (progress + missing items) from
  `GET /members/{id}/kyc`.
- **Members → "KYC submissions"** review screen (2026-06-29 spec): `DataTable` of pending
  submissions; detail shows proposed-vs-current; Approve / Reject (`ConfirmDialog`).

### Member portal
- **Profile → KYC section** — completion banner + missing-items checklist + submission
  status (none / pending / rejected+reason / approved), and a "Complete/Edit KYC"
  `FormDialog` that submits to `POST /member/me/kyc`. Per the 2026-06-29 spec, enhanced with
  the tracker's checklist.

### Platform portal
- **Tenant detail → "KYC" section** — read-only SACCO values + completion + a Verify /
  Unverify action (`ConfirmDialog`; Verify disabled until complete).
- **Settings → "SACCO KYC requirements"** — global toggles for the non-locked SACCO catalog
  fields. Writes `PUT /platform/kyc/sacco-requirements`.

### Schemas
Backend Pydantic in each module's `schemas.py`; portal Zod in `@sacco/schemas`:
`OrganizationKycIn/Out`, `KycCompletionOut` (shared shape: `items`, `required_total`,
`required_present`, `percent`, `missing_required`, `is_complete`), `KycRequirementsOut/In`
(catalog + overrides), plus the 2026-06-29 `KycSubmissionIn/Out`.

## Audit
- Operator org-KYC upserts and member required-set changes → tenant `audit_log`,
  `actor_type='tenant_user'`.
- Platform verify/unverify of a tenant's org KYC → tenant `audit_log`,
  `actor_type='platform_user'` (the platform user acting in tenant context, per the
  platform_ contracts).
- Platform SACCO-requirements changes → platform `audit_log`.
- Member submissions and operator approve/reject → per the 2026-06-29 spec.

## Testing (TDD per conventions)

- **Core (`app/core/kyc`) unit tests:** locked-always-required; override on/off;
  present-vs-blank-string; `required_total == 0 → percent 100`; `missing_required` and
  `is_complete` correctness; unknown override keys ignored.
- **SACCO backend pytest:** org-profile get-or-create singleton; upsert audits diffs;
  material change resets `verified`; verify blocked when incomplete (409); verify/unverify
  via `get_session_for_tenant_schema`; SACCO requirements replace ignores locked keys.
- **Member backend pytest:** per-tenant requirements replace; completion surfaced on
  `GET /members/{id}/kyc` and `GET /member/me/kyc`; submission/review per the 2026-06-29
  spec (submit + supersede; approve applies + audits; reject; national_id 409;
  cross-member 404).
- **Portal vitest:** completion checklist + progress rendering; org-KYC form states;
  requirements-toggle save; platform verify gating (disabled until complete); member KYC
  section states; operator review approve/reject.

## Build sequence (each increment = its own implementation plan)

Tenant (SACCO) track first, per the build-order decision.

1. **Core tracker** — `app/core/kyc/` catalog + `compute_completion` + unit tests.
   Foundational; no API surface.
2. **SACCO org KYC backend** — tenant `organization_profile` model + migration +
   `OrganizationKycService`; platform `sacco_kyc_requirements` + `SaccoKycRequirementsService`;
   operator `/organization/kyc` endpoints; platform oversight + verify endpoints.
3. **SACCO org KYC portals** — operator Organization-KYC page; platform tenant-KYC
   view/verify + global SACCO-requirements settings.
4. **Member required-set config + tracker surfacing** — tenant `member_kyc_requirements` +
   operator settings endpoint/page; completion surfaced on the operator member detail and
   `GET /member/me/kyc`.
5. **Member KYC submission + review** (2026-06-29 spec, increment 3) — `kyc_submissions` +
   the three member columns, member submit endpoints, operator review queue + screens,
   member portal KYC section.

## Contract changes (append to `CLAUDE.md` on implementation)

- **Core KYC tracker:** `app/core/kyc/` is pure (no DB, no I/O) and imports nothing from
  `app/modules` or `app/platform_`. `compute_completion` is the only completion computation;
  do not hand-roll completeness checks elsewhere.
- **SACCO org KYC:** values live in the tenant-schema `organization_profile` singleton,
  self-attested by the tenant admin via `/organization/kyc`. The required set is
  platform-global (`platform.sacco_kyc_requirements`). The `verified` flag is set **only** by
  the platform verify/unverify endpoints (via `get_session_for_tenant_schema`) and **only**
  when completion `is_complete`; any material value change resets it to false.
- **Member KYC:** the required set is per-tenant (`member_kyc_requirements`, operator-owned).
  Member writes follow the 2026-06-29 contract changes (KYC submission + loan application are
  the only member writes; members never write identity fields directly; KYC review is
  single-reviewer, not maker-checker).
- **Gating:** KYC completion is informational only; it must not gate activation,
  transacting, or any request path in v1.
