# Platform Approvals Inbox (SP17) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the platform Approvals inbox (list / detail / my-submissions) so a second operator can approve, reject, or cancel the maker-checker requests that SP14/SP15/SP16 can only *create* — plus a small additive backend enrichment (`current_approvals` count + an `actions` trail on detail) that the quorum badge and approver trail need.

**Architecture:** Two parts. **Part 1 (backend, separate commits)** is a Phase-1.7-style *additive* response enrichment on `app/modules/maker_checker/` — no new endpoints, no renamed/removed fields, no gate changes — landed first and not mixed with `admin/` commits. **Part 2 (portal, `admin/` only)** consumes it: hand-written `@sacco/schemas` Out types + operation-label map + action Zod inputs, then three server-fetched pages reusing the SP16 server-page-context + in-memory `<DataTable>` adapter + RHF/Zod + `useTypedMutation` patterns. The inbox is the **checker** side: approving **executes** the operation, so it uses the base form `<Dialog>`/`<ConfirmDialog>` — NOT `<MakerCheckerConfirmDialog>` (whose locked "creates an approval request" copy is the maker side).

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2.0 async / pytest (backend); Next.js 15 App Router, React 19, TS strict, `@sacco/ui` (DataTable, FormField, Textarea, ConfirmDialog, StatusBadge, Money, FormattedDate/FormattedDateTime, AuditBar, Card, Select), `@sacco/schemas` (Zod + new Out types), `@sacco/api-client` (`resources.makerChecker.*`, `resources.admin.*`), Vitest + Testing Library (portal).

---

## Contract & scope notes (read before starting)

- **SP17 is NOT pure-client.** Per CLAUDE.md contract B, a sub-plan that needs a backend change must surface it; this was surfaced during brainstorming and the resolution is an **additive** enrichment. Definition of additive: no endpoint added/removed, no field renamed/removed, no gate changed. `current_approvals` defaults to `0` (keeps the shared tenant router valid); `actions` appears only on the richer detail response.
- **Part 1 (backend) and Part 2 (`admin/`) ship in separate commits.** Backend lands first. This preserves the spirit of contracts B/N (portal commits stay `admin/`-only).
- **Everything else already exists — verified against the real code:**
  - api-client: `resources.makerChecker.listPlatform(query)` / `getPlatform(id)` / `approvePlatform(id, body)` / `rejectPlatform(id, body)` / `cancelPlatform(id, body)` (`admin/packages/api-client/src/resources/makerChecker.ts`). Every method is typed `Promise<never>` (`as never` wart) → cast to `{ data?, error? }` at each call site with the standard comment, exactly as SP15/16.
  - api-client: `resources.admin.listUsers(query?)` / `getUser(id)` (`admin/packages/api-client/src/resources/admin.ts`) for name resolution + the `update_sensitive` "before" fetch.
  - queryKeys (`admin/packages/api-client/src/query-keys.ts`): `approvals.root()`, `approvals.platform(filters)`, `approvals.detail(id)`.
  - StatusBadge: entity `"approval_request"` with `APPROVAL_REQUEST_STATUS` mapping all seven statuses (`admin/packages/ui/src/components/StatusBadge/status-maps.ts:76`).
  - permissions (`admin/apps/portal/src/auth/permissions.ts`): `"approvals.read" → "support"`, `"approvals.approve" → "admin"`.
  - server helpers (`admin/apps/portal/src/auth/server-page-context.ts`): `getPlatformPageContext()` + `requirePlatformPermission(user, perm)`.
  - The platform sidebar already links `/platform/approvals` gated `approvals.read` — these pages fill the current 404.
  - `@sacco/ui` exports `ConfirmDialog` (props `open / onOpenChange / title / description? / confirmLabel / destructive? / onConfirm / busy?`), `Dialog`/`DialogContent`/`DialogHeader`/`DialogTitle`/`DialogDescription`, `FormField`, `Textarea`, `Card`, `AuditBar`, `FormattedDateTime`.

- **Backend facts (authoritative — from `app/modules/maker_checker/`):**
  - Router `platform_api.py`, prefix `/platform/approvals`. `GET ""` (`CurrentSupport`, `?status=&operation_type=&requested_by=`) → `list[ApprovalRequestOut]`; `GET "/{request_id}"` (`CurrentSupport`) → `ApprovalRequestOut`; `POST "/{id}/approve"` (`CurrentAdmin`, `{comment?}`); `POST "/{id}/reject"` (`CurrentAdmin`, `{reason?}`); `POST "/{id}/cancel"` (`CurrentAdmin`).
  - `ApprovalRequestOut` (`schemas.py:33`) fields: `id, operation_type, payload, requested_by, requested_at, required_approvals, status, expires_at, executed_at, execution_result, rejection_reason`. `model_config = {"from_attributes": True}`.
  - `ApprovalActionOut` (`schemas.py:23`) fields: `id, actor_user_id, action, acted_at, comment`. Already exists.
  - **No ORM relationship** between request and actions. Actions are loaded via `select(PlatformApprovalAction).where(approval_request_id == id)`. The approve-count is `SELECT count(*) WHERE approval_request_id == id AND action == 'approve'` (`ApprovalService._approval_count`, `service.py:193` — private).
  - Service invariants: self-approval raises `ValueError` (`service.py:101`); `cancel()` only by the requester and only before any action exists; `required_approvals == 1` for all v1 platform ops (a pending request is "0 of 1", first approve executes it); statuses `pending / approved / rejected / cancelled / executed / execution_failed / expired`.
  - Operation payloads (drive the detail renderer; none store a "before" state):
    | Operation | Payload keys |
    |-----------|--------------|
    | `platform_user.update_sensitive` | `user_id`, `is_active`, `is_superuser` |
    | `billing.void_invoice` | `invoice_id`, `reason` |
    | `billing.cancel_subscription` | `subscription_id`, `reason` |
    | `billing.confirm_payment` | `payment_id` |
    | `tenant.suspend` | `tenant_id`, `reason` |
    | `tenant.retry_provisioning` | `tenant_id` |
    | `platform.start_impersonation` | `platform_user_id`, `tenant_id`, `reason` |

- **Deviation from spec wording — approve/reject dialog mechanism:** the spec says "Approve → confirm dialog with an optional comment field" / "Reject → ConfirmDialog with a required-reason field". The real `<ConfirmDialog>` has **no content/children slot** (props are title/description/confirmLabel only). The established precedent for an action-with-a-field is a **form `<Dialog>`** (FormField + Textarea + submit → mutation) — see SP16 `PendingPaymentsTable` reject. So: **Approve** and **Reject** use a form `<Dialog>` whose copy states the operation will run on approval; **Cancel** (no fields) uses the base `<ConfirmDialog destructive>`. Documented here, not a gap.

- **Out of scope (deferred, matching the spec):** `<MakerCheckerBanner>` wiring on invoice/subscription/tenant detail pages (its own follow-up — the `current_approvals` shipped here is what unblocks it); tenant-side approvals inbox (only the default-0 schema parity is touched); diff annotations for ops other than `update_sensitive` (no before-state in their payloads); e2e + next-intl (portal-wide deferrals, raw English); submit/create from the inbox (requests are created by feature flows).

---

## File Structure

**Part 1 — Backend (`app/`, separate commits)**
- Modify: `app/modules/maker_checker/schemas.py` — add `current_approvals: int = 0` to `ApprovalRequestOut`; add `ApprovalRequestDetailOut(ApprovalRequestOut)` with `actions: list[ApprovalActionOut]`.
- Modify: `app/modules/maker_checker/platform_api.py` — list handler sets `current_approvals` per row; detail handler returns `ApprovalRequestDetailOut` with `actions` + `current_approvals`.
- Modify: `app/modules/maker_checker/service.py` — make the approve-count reusable by handlers (rename `_approval_count` → public `approval_count`; add `list_actions(request_id)`).
- Test: `tests/modules/maker_checker/test_platform_api.py` — extend with `current_approvals` (list + detail), `actions` trail ordering, and a quorum-2 "1 of 2" case.

**Part 2 — `@sacco/schemas`**
- Create: `admin/packages/schemas/src/approvals.ts` — `ApprovalActionOut`, `ApprovalRequestOut`, `ApprovalRequestDetailOut`, `PLATFORM_OPERATION_LABELS` + `operationLabel()`, `approveActionSchema`, `rejectActionSchema` (+ inferred `*Input`).
- Modify: `admin/packages/schemas/src/index.ts` — `export * from "./approvals"`.
- Test: `admin/packages/schemas/src/__tests__/approvals.test.ts`.

**Part 2 — Portal (`admin/apps/portal/`)**
- Create: `app/platform/(authed)/approvals/_components/ApprovalsTable.tsx` — shared in-memory `<DataTable>` adapter.
- Create: `app/platform/(authed)/approvals/page.tsx` — inbox.
- Create: `app/platform/(authed)/approvals/my-submissions/page.tsx` — own queue.
- Create: `app/platform/(authed)/approvals/[id]/_components/PayloadView.tsx` — operation-aware payload + `update_sensitive` diff.
- Create: `app/platform/(authed)/approvals/[id]/_components/ApprovalActions.tsx` — approve/reject/cancel client component.
- Create: `app/platform/(authed)/approvals/[id]/page.tsx` — detail.
- Tests under `admin/apps/portal/src/__tests__/platform-approvals/`.

---

## Task 1: Backend — `current_approvals` on the list response

**Files:**
- Modify: `app/modules/maker_checker/schemas.py`
- Modify: `app/modules/maker_checker/service.py`
- Modify: `app/modules/maker_checker/platform_api.py`
- Test: `tests/modules/maker_checker/test_platform_api.py`

- [ ] **Step 1: Make the approve-count reusable (service.py)**

The handler needs the count the service already computes privately. Rename `_approval_count` to a public method and keep the internal callsite working.

In `app/modules/maker_checker/service.py`, change the method definition (line ~193) and its one internal caller (line ~114):

```python
    async def approval_count(self, request_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count()).where(
                self._act_cls.approval_request_id == request_id,
                self._act_cls.action == "approve",
            )
        )
        return result.scalar_one()
```

And update the caller inside `approve()`:

```python
        count = await self.approval_count(request.id)
```

> Note: `import uuid` is currently under `TYPE_CHECKING` in service.py. `approval_count`'s annotation `uuid.UUID` is fine because `from __future__ import annotations` is at the top (annotations are strings).

- [ ] **Step 2: Write the failing test (append to test_platform_api.py)**

Mirror the existing harness in the file (it already has `_make_platform_session_override`, `_create_platform_user`, `_cleanup`, and submits via the registered `platform.test.op` executor + `CurrentSupport`/`CurrentAdmin` overrides). Add a test asserting list rows carry `current_approvals`:

```python
async def test_list_returns_current_approvals(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    try:
        app.dependency_overrides[get_platform_session] = _make_platform_session_override(
            test_engine
        )
        _override_support_user(maker)  # helper already in this file; see existing tests
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Maker submits a request (required_approvals defaults to 1).
                created = await client.post(
                    "/platform/approvals",
                    json={"operation_type": "platform.test.op", "payload": {"x": 1}},
                )
                assert created.status_code == 201
                listed = await client.get("/platform/approvals")
                assert listed.status_code == 200
                body = listed.json()
                assert body[0]["current_approvals"] == 0
                assert body[0]["required_approvals"] == 1
    finally:
        app.dependency_overrides.clear()
        await _cleanup(factory)
```

> Match the *exact* override-helper names already present in the file (e.g. how existing tests swap `CurrentSupport` / `CurrentAdmin`). If the file uses a single `_override_user(user, role=...)` helper, use that; the snippet's `_override_support_user` is illustrative.

- [ ] **Step 3: Run to verify it fails**

Run: `cd /home/liam/projects/sacco-platform && python -m pytest tests/modules/maker_checker/test_platform_api.py::test_list_returns_current_approvals -v`
Expected: FAIL — response rows have no `current_approvals` key (KeyError in the assertion).

- [ ] **Step 4: Add the field + populate it (schemas.py + platform_api.py)**

In `schemas.py`, add the field to `ApprovalRequestOut` (default keeps the shared tenant router valid):

```python
class ApprovalRequestOut(BaseModel):
    id: uuid.UUID
    operation_type: str
    payload: dict[str, Any]
    requested_by: uuid.UUID
    requested_at: datetime
    required_approvals: int
    current_approvals: int = 0
    status: str
    expires_at: datetime | None
    executed_at: datetime | None
    execution_result: dict[str, Any] | None
    rejection_reason: str | None

    model_config = {"from_attributes": True}
```

> `current_approvals` is NOT an ORM attribute, so it can't arrive via `from_attributes`. Handlers set it explicitly.

In `platform_api.py`, update `list_approvals` to compute the count per row:

```python
@router.get("", response_model=list[ApprovalRequestOut])
async def list_approvals(
    session: Session,
    user: CurrentSupport,
    status: str | None = Query(None),
    operation_type: str | None = Query(None),
    requested_by: uuid.UUID | None = Query(None),
) -> list[ApprovalRequestOut]:
    q = select(PlatformApprovalRequest).order_by(PlatformApprovalRequest.requested_at.desc())
    if status:
        q = q.where(PlatformApprovalRequest.status == status)
    if operation_type:
        q = q.where(PlatformApprovalRequest.operation_type == operation_type)
    if requested_by is not None:
        q = q.where(PlatformApprovalRequest.requested_by == requested_by)
    rows = (await session.execute(q)).scalars().all()
    svc = ApprovalService(session)
    out: list[ApprovalRequestOut] = []
    for r in rows:
        dto = ApprovalRequestOut.model_validate(r)
        dto.current_approvals = await svc.approval_count(r.id)
        out.append(dto)
    return out
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd /home/liam/projects/sacco-platform && python -m pytest tests/modules/maker_checker/test_platform_api.py::test_list_returns_current_approvals -v`
Expected: PASS.

- [ ] **Step 6: Run the existing maker-checker suite (no regressions)**

Run: `cd /home/liam/projects/sacco-platform && python -m pytest tests/modules/maker_checker/ -q`
Expected: PASS (the renamed `approval_count` keeps `approve()` working; existing `test_service.py` that may reference `_approval_count` must be updated to `approval_count` — grep first: `rg "_approval_count" tests/ app/`).

- [ ] **Step 7: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add app/modules/maker_checker/schemas.py app/modules/maker_checker/service.py app/modules/maker_checker/platform_api.py tests/modules/maker_checker/test_platform_api.py
git commit -m "feat(maker-checker): expose current_approvals on platform approval list

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Backend — `ApprovalRequestDetailOut` with the actions trail

**Files:**
- Modify: `app/modules/maker_checker/schemas.py`
- Modify: `app/modules/maker_checker/service.py`
- Modify: `app/modules/maker_checker/platform_api.py`
- Test: `tests/modules/maker_checker/test_platform_api.py`

- [ ] **Step 1: Add a `list_actions` helper (service.py)**

Add to `ApprovalService` (the model class is already resolved as `self._act_cls`):

```python
    async def list_actions(self, request_id: uuid.UUID) -> list[Any]:
        result = await self._session.execute(
            select(self._act_cls)
            .where(self._act_cls.approval_request_id == request_id)
            .order_by(self._act_cls.acted_at.asc())
        )
        return list(result.scalars().all())
```

- [ ] **Step 2: Write the failing tests (append to test_platform_api.py)**

```python
async def test_detail_returns_actions_trail(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    checker = await _create_platform_user(factory, "checker")
    try:
        app.dependency_overrides[get_platform_session] = _make_platform_session_override(
            test_engine
        )
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                _override_user(maker, role="admin")
                created = await client.post(
                    "/platform/approvals",
                    json={"operation_type": "platform.test.op", "payload": {"x": 1}},
                )
                rid = created.json()["id"]

                # Checker approves -> with required_approvals=1 this executes.
                _override_user(checker, role="admin")
                approved = await client.post(f"/platform/approvals/{rid}/approve", json={})
                assert approved.status_code == 200

                _override_user(checker, role="support")
                detail = await client.get(f"/platform/approvals/{rid}")
                assert detail.status_code == 200
                body = detail.json()
                assert body["current_approvals"] == 1
                assert len(body["actions"]) == 1
                assert body["actions"][0]["action"] == "approve"
                assert body["actions"][0]["actor_user_id"] == str(checker.id)
    finally:
        app.dependency_overrides.clear()
        await _cleanup(factory)


async def test_detail_quorum_two_reports_one_of_two(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    checker = await _create_platform_user(factory, "checker")
    try:
        app.dependency_overrides[get_platform_session] = _make_platform_session_override(
            test_engine
        )
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                _override_user(maker, role="admin")
                created = await client.post(
                    "/platform/approvals",
                    json={
                        "operation_type": "platform.test.op",
                        "payload": {"x": 1},
                        "required_approvals": 2,
                    },
                )
                rid = created.json()["id"]

                _override_user(checker, role="admin")
                await client.post(f"/platform/approvals/{rid}/approve", json={})

                _override_user(checker, role="support")
                detail = (await client.get(f"/platform/approvals/{rid}")).json()
                assert detail["current_approvals"] == 1
                assert detail["required_approvals"] == 2
                assert detail["status"] == "pending"
    finally:
        app.dependency_overrides.clear()
        await _cleanup(factory)
```

> Use the file's real override helper. `role` switching matters: approve requires `CurrentAdmin`; the final detail GET only needs `CurrentSupport`.

- [ ] **Step 3: Run to verify they fail**

Run: `cd /home/liam/projects/sacco-platform && python -m pytest tests/modules/maker_checker/test_platform_api.py -k "actions_trail or one_of_two" -v`
Expected: FAIL — response has no `actions` key.

- [ ] **Step 4: Add `ApprovalRequestDetailOut` (schemas.py)**

Append after `ApprovalRequestOut`:

```python
class ApprovalRequestDetailOut(ApprovalRequestOut):
    actions: list[ApprovalActionOut] = []
```

- [ ] **Step 5: Return the detail DTO from the GET handler (platform_api.py)**

Add the import and rewrite `get_approval`:

```python
from app.modules.maker_checker.schemas import (
    ApprovalActionRequest,
    ApprovalRequestDetailOut,
    ApprovalRequestOut,
    RejectRequest,
    SubmitApprovalRequest,
)
```

```python
@router.get("/{request_id}", response_model=ApprovalRequestDetailOut)
async def get_approval(
    request_id: uuid.UUID,
    session: Session,
    user: CurrentSupport,
) -> ApprovalRequestDetailOut:
    row = await session.scalar(
        select(PlatformApprovalRequest).where(PlatformApprovalRequest.id == request_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    svc = ApprovalService(session)
    dto = ApprovalRequestDetailOut.model_validate(row)
    dto.current_approvals = await svc.approval_count(row.id)
    dto.actions = [ApprovalActionOut.model_validate(a) for a in await svc.list_actions(row.id)]
    return dto
```

> Add `ApprovalActionOut` to the schema import list too.

- [ ] **Step 6: Run to verify they pass**

Run: `cd /home/liam/projects/sacco-platform && python -m pytest tests/modules/maker_checker/test_platform_api.py -k "actions_trail or one_of_two" -v`
Expected: PASS.

- [ ] **Step 7: Full backend gate (ruff + mypy + suite)**

Run:
```bash
cd /home/liam/projects/sacco-platform
ruff check app/ tests/ && mypy app/ && python -m pytest tests/modules/maker_checker/ -q
```
Expected: clean + PASS.

- [ ] **Step 8: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add app/modules/maker_checker/schemas.py app/modules/maker_checker/service.py app/modules/maker_checker/platform_api.py tests/modules/maker_checker/test_platform_api.py
git commit -m "feat(maker-checker): add ApprovalRequestDetailOut actions trail to platform detail

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Portal schemas — approval Out types, operation labels, action Zod (`@sacco/schemas`)

**Files:**
- Create: `admin/packages/schemas/src/approvals.ts`
- Modify: `admin/packages/schemas/src/index.ts`
- Test: `admin/packages/schemas/src/__tests__/approvals.test.ts`

- [ ] **Step 1: Write the failing test**

Create `admin/packages/schemas/src/__tests__/approvals.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  PLATFORM_OPERATION_LABELS,
  approveActionSchema,
  operationLabel,
  rejectActionSchema,
} from "../approvals";

describe("PLATFORM_OPERATION_LABELS", () => {
  it("labels every known platform operation", () => {
    expect(PLATFORM_OPERATION_LABELS["billing.void_invoice"]).toBe("Void invoice");
    expect(PLATFORM_OPERATION_LABELS["platform_user.update_sensitive"]).toBe(
      "Update platform user",
    );
  });
});

describe("operationLabel", () => {
  it("returns the mapped label when known", () => {
    expect(operationLabel("tenant.suspend")).toBe("Suspend tenant");
  });
  it("humanizes an unknown operation instead of rendering the raw key", () => {
    expect(operationLabel("widget.frobnicate_thing")).toBe("Frobnicate thing");
  });
});

describe("approveActionSchema", () => {
  it("accepts an empty body (comment optional)", () => {
    expect(approveActionSchema.parse({})).toEqual({});
  });
  it("accepts an optional comment", () => {
    expect(approveActionSchema.parse({ comment: "looks good" }).comment).toBe("looks good");
  });
});

describe("rejectActionSchema", () => {
  it("requires a reason of at least 10 chars", () => {
    expect(rejectActionSchema.safeParse({ reason: "too short" }).success).toBe(false);
    expect(rejectActionSchema.safeParse({ reason: "this is a valid reason" }).success).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/schemas test -- approvals`
Expected: FAIL — `../approvals` does not exist.

- [ ] **Step 3: Create `approvals.ts`**

```ts
import { z } from "zod";

// ── Read models (hand-written, mirror app/modules/maker_checker/schemas.py) ──

export interface ApprovalActionOut {
  id: string;
  actor_user_id: string;
  action: string; // "approve" | "reject"
  acted_at: string;
  comment: string | null;
}

export interface ApprovalRequestOut {
  id: string;
  operation_type: string;
  payload: Record<string, unknown>;
  requested_by: string;
  requested_at: string;
  required_approvals: number;
  current_approvals: number;
  status: string;
  expires_at: string | null;
  executed_at: string | null;
  execution_result: Record<string, unknown> | null;
  rejection_reason: string | null;
}

export interface ApprovalRequestDetailOut extends ApprovalRequestOut {
  actions: ApprovalActionOut[];
}

// ── Operation labels ─────────────────────────────────────────────────────────

export const PLATFORM_OPERATION_LABELS: Record<string, string> = {
  "platform_user.update_sensitive": "Update platform user",
  "billing.void_invoice": "Void invoice",
  "billing.cancel_subscription": "Cancel subscription",
  "billing.confirm_payment": "Confirm payment",
  "tenant.suspend": "Suspend tenant",
  "tenant.retry_provisioning": "Retry provisioning",
  "platform.start_impersonation": "Start impersonation",
};

/**
 * Human label for an operation type. Falls back to humanizing the last
 * dot-segment so a new backend operation never renders a raw key badly
 * (mirrors StatusBadge unknown-status behavior, CLAUDE.md contract S).
 */
export function operationLabel(operationType: string): string {
  const known = PLATFORM_OPERATION_LABELS[operationType];
  if (known) return known;
  const tail = operationType.split(".").pop() ?? operationType;
  const words = tail.replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// ── Action inputs ────────────────────────────────────────────────────────────

export const approveActionSchema = z.object({
  comment: z.string().optional(),
});
export type ApproveActionInput = z.infer<typeof approveActionSchema>;

export const rejectActionSchema = z.object({
  reason: z.string().min(10, "Provide a reason of at least 10 characters."),
});
export type RejectActionInput = z.infer<typeof rejectActionSchema>;
```

- [ ] **Step 4: Export from the barrel (index.ts)**

Add to `admin/packages/schemas/src/index.ts`:

```ts
export * from "./approvals";
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/schemas test -- approvals`
Expected: PASS.

- [ ] **Step 6: Typecheck + lint the package**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add admin/packages/schemas/src/approvals.ts admin/packages/schemas/src/index.ts admin/packages/schemas/src/__tests__/approvals.test.ts
git commit -m "feat(portal): approval Out types + operation labels + action schemas

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `<ApprovalsTable>` — shared in-memory DataTable adapter

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/approvals/_components/ApprovalsTable.tsx`
- Test: `admin/apps/portal/src/__tests__/platform-approvals/ApprovalsTable.test.tsx`

- [ ] **Step 1: Write the failing test**

DataTable consumers mock `useTableUrlState` (nuqs has no resolvable test adapter under pnpm strict isolation — established SP16 pattern). Create `admin/apps/portal/src/__tests__/platform-approvals/ApprovalsTable.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@sacco/ui", async () => {
  const actual = await vi.importActual<typeof import("@sacco/ui")>("@sacco/ui");
  return {
    ...actual,
    useTableUrlState: () => ({
      page: 1,
      pageSize: 25,
      sortColumn: "requested_at",
      sortDirection: "desc" as const,
      filters: {} as Record<string, string | undefined>,
      setFilter: vi.fn(),
      setFilters: vi.fn(),
      density: "comfortable" as const,
    }),
  };
});

import { ApprovalsTable, type ApprovalRow } from "../../../app/platform/(authed)/approvals/_components/ApprovalsTable";

const rows: ApprovalRow[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    operation_type: "billing.void_invoice",
    operation_label: "Void invoice",
    status: "pending",
    current_approvals: 0,
    required_approvals: 1,
    requested_by_label: "maker@platform.test",
    requested_at: "2026-06-16T10:00:00Z",
  },
];

describe("ApprovalsTable", () => {
  it("renders the operation label as a link to the detail page", () => {
    render(<ApprovalsTable rows={rows} />);
    const link = screen.getByRole("link", { name: "Void invoice" });
    expect(link).toHaveAttribute(
      "href",
      "/platform/approvals/11111111-1111-1111-1111-111111111111",
    );
  });

  it("renders the quorum as '{current} of {required}'", () => {
    render(<ApprovalsTable rows={rows} />);
    expect(screen.getByText("0 of 1")).toBeInTheDocument();
  });

  it("shows the empty state when there are no rows", () => {
    render(<ApprovalsTable rows={[]} />);
    expect(screen.getByText("No approval requests")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal test -- ApprovalsTable`
Expected: FAIL — component does not exist.

- [ ] **Step 3: Implement `ApprovalsTable.tsx`**

Mirror SP16 `InvoicesTable` structure (in-memory filter/sort/paginate; `setFilter` resets page to 1 in the hook). The `requested_at` default sort is `desc`.

```tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import { PLATFORM_OPERATION_LABELS } from "@sacco/schemas";

export interface ApprovalRow {
  id: string;
  operation_type: string;
  operation_label: string;
  status: string;
  current_approvals: number;
  required_approvals: number;
  requested_by_label: string;
  requested_at: string;
}

const STATUS_FILTER_OPTIONS = [
  "pending",
  "approved",
  "rejected",
  "executed",
  "execution_failed",
  "expired",
  "cancelled",
] as const;

const columns: DataTableProps<ApprovalRow>["columns"] = [
  {
    id: "operation_label",
    accessorKey: "operation_label",
    header: "Operation",
    cell: ({ row }) => (
      <Link
        href={`/platform/approvals/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.operation_label}
      </Link>
    ),
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="approval_request" status={row.original.status} />,
  },
  {
    id: "quorum",
    accessorKey: "current_approvals",
    header: "Quorum",
    enableSorting: false,
    cell: ({ row }) => (
      <span className="tabular-nums">
        {row.original.current_approvals} of {row.original.required_approvals}
      </span>
    ),
  },
  { id: "requested_by_label", accessorKey: "requested_by_label", header: "Requested by" },
  {
    id: "requested_at",
    accessorKey: "requested_at",
    header: "Requested",
    cell: ({ row }) => <FormattedDate value={row.original.requested_at} />,
  },
];

export function filterApprovals(rows: ApprovalRow[], status: string | undefined): ApprovalRow[] {
  if (!status) return rows;
  return rows.filter((r) => r.status === status);
}

export function sortApprovals(
  rows: ApprovalRow[],
  column: string | null,
  dir: "asc" | "desc",
): ApprovalRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof ApprovalRow];
    const bv = b[column as keyof ApprovalRow];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/** Full (unpaginated) approvals list through DataTable; client-side filter/sort/paginate. */
export function ApprovalsTable({ rows }: { rows: ApprovalRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "requested_at", direction: "desc" },
    defaultPageSize: 25,
    filterKeys: ["status"],
  });

  const filtered = useMemo(
    () => filterApprovals(rows, urlState.filters["status"]),
    [rows, urlState.filters],
  );
  const sorted = useMemo(
    () => sortApprovals(filtered, urlState.sortColumn, urlState.sortDirection),
    [filtered, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<ApprovalRow>
      id="platform-approvals"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: filtered.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No approval requests",
        description: "Maker-checker requests created by billing, tenant, and user flows appear here.",
      }}
      filterSlot={
        <Select
          value={urlState.filters["status"] ?? "all"}
          onValueChange={(v) => urlState.setFilter("status", v === "all" ? null : v)}
        >
          <SelectTrigger className="w-48" aria-label="Filter by status">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUS_FILTER_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    />
  );
}
```

> `PLATFORM_OPERATION_LABELS` is imported to keep the symbol in this module's surface for downstream pages; the row's `operation_label` is precomputed server-side via `operationLabel()`. (If lint flags the import as unused, drop it — the pages do the labelling.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal test -- ApprovalsTable`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add "admin/apps/portal/app/platform/(authed)/approvals/_components/ApprovalsTable.tsx" admin/apps/portal/src/__tests__/platform-approvals/ApprovalsTable.test.tsx
git commit -m "feat(portal): ApprovalsTable in-memory DataTable adapter

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Inbox page + my-submissions page

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/approvals/page.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/approvals/my-submissions/page.tsx`

> These are server components doing real fetches — not unit-tested in isolation (consistent with SP16 list pages, whose coverage lives in the table component test). Verification is typecheck + lint + the suite staying green.

- [ ] **Step 1: Implement the inbox page**

Fetch the list + resolve requester names from `admin.listUsers()` (same Map pattern as SP15/16). Build `ApprovalRow[]` server-side, labelling via `operationLabel()`.

```tsx
// admin/apps/portal/app/platform/(authed)/approvals/page.tsx
import type { ApprovalRequestOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { ApprovalsTable, type ApprovalRow } from "./_components/ApprovalsTable";

export const metadata = { title: "Approvals" };

interface PlatformUserLite {
  id: string;
  email: string;
  full_name?: string | null;
}

function userLabel(u: PlatformUserLite | undefined, id: string): string {
  if (!u) return id;
  return u.full_name && u.full_name.length > 0 ? u.full_name : u.email;
}

export default async function ApprovalsInboxPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "approvals.read");

  const { data: requests } = await (
    resources.makerChecker.listPlatform({}) as Promise<{
      data?: ApprovalRequestOut[];
      error?: unknown;
    }>
  );
  const { data: users } = await (
    resources.admin.listUsers() as Promise<{ data?: PlatformUserLite[]; error?: unknown }>
  );

  const usersById = new Map((users ?? []).map((u) => [u.id, u]));
  const rows: ApprovalRow[] = (requests ?? []).map((r) => ({
    id: r.id,
    operation_type: r.operation_type,
    operation_label: operationLabel(r.operation_type),
    status: r.status,
    current_approvals: r.current_approvals,
    required_approvals: r.required_approvals,
    requested_by_label: userLabel(usersById.get(r.requested_by), r.requested_by),
    requested_at: r.requested_at,
  }));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Approvals</h1>
        <a
          href="/platform/approvals/my-submissions"
          className="text-[var(--text-link)] hover:underline"
        >
          My submissions
        </a>
      </div>
      <ApprovalsTable rows={rows} />
    </div>
  );
}
```

- [ ] **Step 2: Implement the my-submissions page**

Same shape, filtered by `requested_by: user.id`.

```tsx
// admin/apps/portal/app/platform/(authed)/approvals/my-submissions/page.tsx
import type { ApprovalRequestOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { ApprovalsTable, type ApprovalRow } from "../_components/ApprovalsTable";

export const metadata = { title: "My submissions" };

interface PlatformUserLite {
  id: string;
  email: string;
  full_name?: string | null;
}

export default async function MySubmissionsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "approvals.read");

  const { data: requests } = await (
    resources.makerChecker.listPlatform({ requested_by: user.id }) as Promise<{
      data?: ApprovalRequestOut[];
      error?: unknown;
    }>
  );
  const { data: users } = await (
    resources.admin.listUsers() as Promise<{ data?: PlatformUserLite[]; error?: unknown }>
  );
  const usersById = new Map((users ?? []).map((u) => [u.id, u]));

  const rows: ApprovalRow[] = (requests ?? []).map((r) => {
    const u = usersById.get(r.requested_by);
    return {
      id: r.id,
      operation_type: r.operation_type,
      operation_label: operationLabel(r.operation_type),
      status: r.status,
      current_approvals: r.current_approvals,
      required_approvals: r.required_approvals,
      requested_by_label: u ? (u.full_name ?? u.email) : r.requested_by,
      requested_at: r.requested_at,
    };
  });

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">My submissions</h1>
      <ApprovalsTable rows={rows} />
    </div>
  );
}
```

> `user.id` must exist on `CurrentUserShape`. Verify with `rg "id" admin/apps/portal/src/auth/permissions.ts` — if the shape names it differently (e.g. `sub`), use that. (SP12 detail self-checks already rely on the current-user id; reuse that field.)

- [ ] **Step 3: Typecheck + lint**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add "admin/apps/portal/app/platform/(authed)/approvals/page.tsx" "admin/apps/portal/app/platform/(authed)/approvals/my-submissions/page.tsx"
git commit -m "feat(portal): approvals inbox + my-submissions pages

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: `<PayloadView>` — operation-aware payload + update_sensitive diff

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/approvals/[id]/_components/PayloadView.tsx`
- Test: `admin/apps/portal/src/__tests__/platform-approvals/PayloadView.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PayloadView } from "../../../app/platform/(authed)/approvals/[id]/_components/PayloadView";

describe("PayloadView", () => {
  it("renders a generic structured tree for a non-diff operation", () => {
    render(
      <PayloadView
        operationType="tenant.suspend"
        payload={{ tenant_id: "abc", reason: "fraud review" }}
      />,
    );
    expect(screen.getByText("tenant_id")).toBeInTheDocument();
    expect(screen.getByText("fraud review")).toBeInTheDocument();
  });

  it("renders a before -> after diff for update_sensitive", () => {
    render(
      <PayloadView
        operationType="platform_user.update_sensitive"
        payload={{ user_id: "u1", is_active: false, is_superuser: true }}
        before={{ is_active: true, is_superuser: false }}
      />,
    );
    // is_active: true -> false ; is_superuser: false -> true
    expect(screen.getAllByText("Yes").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No").length).toBeGreaterThan(0);
    expect(screen.getByText("is_active")).toBeInTheDocument();
  });

  it("renders booleans as Yes/No in the generic tree", () => {
    render(<PayloadView operationType="billing.confirm_payment" payload={{ payment_id: "p1" }} />);
    expect(screen.getByText("payment_id")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal test -- PayloadView`
Expected: FAIL — component does not exist.

- [ ] **Step 3: Implement `PayloadView.tsx`**

Generic tree for any payload; a before→after diff branch for `update_sensitive` only. Includes a "view raw JSON" toggle (client component).

```tsx
"use client";

import { useState } from "react";

const DIFF_FIELDS = ["is_active", "is_superuser"] as const;

function renderValue(v: unknown): string {
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function isUuidish(v: unknown): boolean {
  return typeof v === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(v);
}

export interface PayloadViewProps {
  operationType: string;
  payload: Record<string, unknown>;
  /** Present only for platform_user.update_sensitive (fetched server-side). */
  before?: Record<string, unknown>;
}

export function PayloadView({ operationType, payload, before }: PayloadViewProps) {
  const [rawOpen, setRawOpen] = useState(false);
  const isDiff = operationType === "platform_user.update_sensitive" && before !== undefined;

  return (
    <div className="flex flex-col gap-3">
      {isDiff ? (
        <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
          <div className="flex justify-between py-2 text-[13px] text-[var(--text-tertiary)]">
            <span>Field</span>
            <span>Before → After</span>
          </div>
          {DIFF_FIELDS.map((f) => (
            <div key={f} className="flex justify-between py-2">
              <span className="text-[var(--text-secondary)]">{f}</span>
              <span className="text-[var(--text-primary)] tabular-nums">
                {renderValue(before?.[f])} → {renderValue(payload[f])}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {Object.entries(payload).map(([k, v]) => (
            <div key={k} className="flex justify-between gap-4 py-2">
              <span className="text-[var(--text-secondary)]">{k}</span>
              <span
                className={
                  isUuidish(v)
                    ? "font-mono text-[13px] text-[var(--text-primary)]"
                    : "text-[var(--text-primary)]"
                }
              >
                {renderValue(v)}
              </span>
            </div>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={() => setRawOpen((o) => !o)}
        className="self-start text-[13px] text-[var(--text-link)] hover:underline"
      >
        {rawOpen ? "Hide raw JSON" : "View raw JSON"}
      </button>
      {rawOpen ? (
        <pre className="overflow-auto rounded-md bg-[var(--surface-muted)] p-3 text-[12px] text-[var(--text-primary)]">
          {JSON.stringify(payload, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}
```

> `--surface-muted` is used by existing components; if typecheck/lint or visual review flags it, swap for `--surface-secondary` (grep `rg "surface-" admin/packages/ui/src/tokens.css` to confirm the available token).

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal test -- PayloadView`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add "admin/apps/portal/app/platform/(authed)/approvals/[id]/_components/PayloadView.tsx" admin/apps/portal/src/__tests__/platform-approvals/PayloadView.test.tsx
git commit -m "feat(portal): operation-aware approval PayloadView with update_sensitive diff

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: `<ApprovalActions>` — approve / reject / cancel client component

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/approvals/[id]/_components/ApprovalActions.tsx`
- Test: `admin/apps/portal/src/__tests__/platform-approvals/ApprovalActions.test.tsx`

> **Self-approval mirroring (the one place UI mirrors a service invariant):** approve/reject are shown only when `status === "pending"` AND `currentUserId !== requested_by` AND `canApprove`. When `currentUserId === requested_by`, hide approve/reject, show the explanatory tooltip text, and show **Cancel** (pending only).

- [ ] **Step 1: Write the failing test**

The component is fed primitives (no server context). Mock `useAuth` for `resources` and `useTypedMutation` passthrough is real; mock the resource calls via a stubbed `resources`.

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mutate = vi.fn();
vi.mock("@sacco/api-client", async () => {
  const actual =
    await vi.importActual<typeof import("@sacco/api-client")>("@sacco/api-client");
  return { ...actual, useTypedMutation: () => ({ mutate, isPending: false }) };
});
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { makerChecker: {} } }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

import { ApprovalActions } from "../../../app/platform/(authed)/approvals/[id]/_components/ApprovalActions";

const base = {
  requestId: "r1",
  status: "pending",
  requestedBy: "maker",
  subjectLabel: "Void invoice",
};

describe("ApprovalActions", () => {
  it("shows approve + reject for a different user with approve permission", () => {
    render(<ApprovalActions {...base} currentUserId="checker" canApprove />);
    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reject/i })).toBeInTheDocument();
  });

  it("hides approve/reject and shows the self-approval notice for the requester", () => {
    render(<ApprovalActions {...base} currentUserId="maker" canApprove />);
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/cannot approve your own request/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel request/i })).toBeInTheDocument();
  });

  it("renders no action buttons when the request is not pending", () => {
    render(
      <ApprovalActions {...base} status="executed" currentUserId="checker" canApprove />,
    );
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal test -- ApprovalActions`
Expected: FAIL — component does not exist.

- [ ] **Step 3: Implement `ApprovalActions.tsx`**

Approve/Reject use form `<Dialog>`s (the checker side — copy states the operation runs on approval, NOT MakerCheckerConfirmDialog). Cancel uses base `<ConfirmDialog destructive>`. All mutations cast the `Promise<never>` resource calls, invalidate `approvals.platform()` + `approvals.detail(id)`, toast, and `router.refresh()`.

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  FormField,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  approveActionSchema,
  rejectActionSchema,
  type ApproveActionInput,
  type RejectActionInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface ApprovalActionsProps {
  requestId: string;
  status: string;
  requestedBy: string;
  currentUserId: string;
  canApprove: boolean;
  subjectLabel: string;
}

export function ApprovalActions({
  requestId,
  status,
  requestedBy,
  currentUserId,
  canApprove,
  subjectLabel,
}: ApprovalActionsProps) {
  const router = useRouter();
  const { resources } = useAuth();

  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);

  const invalidates = [queryKeys.approvals.platform(), queryKeys.approvals.detail(requestId)];

  const approveForm = useForm<ApproveActionInput>({
    resolver: zodResolver(approveActionSchema),
    defaultValues: { comment: "" },
  });
  const rejectForm = useForm<RejectActionInput>({
    resolver: zodResolver(rejectActionSchema),
    defaultValues: { reason: "" },
  });

  const approveMutation = useTypedMutation<unknown, ApproveActionInput>(
    async (vars) => {
      // resources.makerChecker.approvePlatform is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.makerChecker.approvePlatform(
          requestId,
          vars as Record<string, unknown>,
        ) as Promise<{ data?: unknown; error?: unknown }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Request approved", {
          description: "The operation has been executed.",
        });
        setApproveOpen(false);
        approveForm.reset();
        router.refresh();
      },
      onError: (error) => {
        toast.error("The request was not approved", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const rejectMutation = useTypedMutation<unknown, RejectActionInput>(
    async (vars) => {
      const res = await (
        resources.makerChecker.rejectPlatform(
          requestId,
          vars as Record<string, unknown>,
        ) as Promise<{ data?: unknown; error?: unknown }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Request rejected");
        setRejectOpen(false);
        rejectForm.reset();
        router.refresh();
      },
      onError: (error) => {
        toast.error("The request was not rejected", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const cancelMutation = useTypedMutation<unknown, void>(
    async () => {
      const res = await (
        resources.makerChecker.cancelPlatform(requestId, {}) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Request cancelled");
        setCancelOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The request was not cancelled", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  if (status !== "pending") return null;

  const isOwnRequest = currentUserId === requestedBy;

  return (
    <div className="flex items-center gap-2">
      {isOwnRequest ? (
        <>
          <span className="text-[13px] text-[var(--text-tertiary)]">
            You submitted this request and cannot approve your own request.
          </span>
          <Button variant="destructive" onClick={() => setCancelOpen(true)}>
            Cancel request
          </Button>
        </>
      ) : canApprove ? (
        <>
          <Button variant="primary" onClick={() => { approveForm.reset(); setApproveOpen(true); }}>
            Approve
          </Button>
          <Button variant="destructive" onClick={() => { rejectForm.reset(); setRejectOpen(true); }}>
            Reject
          </Button>
        </>
      ) : null}

      {/* Approve — checker side: approving EXECUTES the operation. */}
      <Dialog open={approveOpen} onOpenChange={(o) => { if (!o) setApproveOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve {subjectLabel}</DialogTitle>
            <DialogDescription>
              Approving runs this operation now. With a single-approver quorum this executes
              immediately and cannot be undone here.
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={approveForm.handleSubmit((values) => approveMutation.mutate(values))}
          >
            <FormField
              control={approveForm.control}
              name="comment"
              label="Comment (optional)"
              render={({ field, id, describedBy, invalid }) => (
                <Textarea
                  id={id}
                  rows={2}
                  aria-describedby={describedBy}
                  aria-invalid={invalid}
                  {...field}
                />
              )}
            />
            <div className="flex gap-3">
              <Button type="submit" disabled={approveMutation.isPending}>
                Approve and execute
              </Button>
              <Button type="button" variant="ghost" onClick={() => setApproveOpen(false)}>
                Cancel
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Reject — required reason. */}
      <Dialog open={rejectOpen} onOpenChange={(o) => { if (!o) setRejectOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject {subjectLabel}</DialogTitle>
            <DialogDescription>
              Rejecting closes this request without running the operation.
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={rejectForm.handleSubmit((values) => rejectMutation.mutate(values))}
          >
            <FormField
              control={rejectForm.control}
              name="reason"
              label="Reason"
              required
              helpText="Recorded on the request and the audit log. Minimum 10 characters."
              render={({ field, id, describedBy, invalid }) => (
                <Textarea
                  id={id}
                  rows={3}
                  aria-describedby={describedBy}
                  aria-invalid={invalid}
                  {...field}
                />
              )}
            />
            <div className="flex gap-3">
              <Button type="submit" variant="destructive" disabled={rejectMutation.isPending}>
                Reject
              </Button>
              <Button type="button" variant="ghost" onClick={() => setRejectOpen(false)}>
                Cancel
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Cancel — requester withdraws (no fields → base ConfirmDialog). */}
      <ConfirmDialog
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        title={`Cancel ${subjectLabel}?`}
        description="This withdraws your pending request. You can re-submit from the originating screen."
        confirmLabel="Cancel request"
        destructive
        busy={cancelMutation.isPending}
        onConfirm={() => cancelMutation.mutate()}
      />
    </div>
  );
}
```

> Verify `useTypedMutation`'s second type param accepts `void` for the cancel mutation; if its signature requires a non-void variable type, use `Record<string, never>` and call `cancelMutation.mutate({})`. Grep the existing SP16 usages: `rg "useTypedMutation<" admin/apps/portal`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal test -- ApprovalActions`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add "admin/apps/portal/app/platform/(authed)/approvals/[id]/_components/ApprovalActions.tsx" admin/apps/portal/src/__tests__/platform-approvals/ApprovalActions.test.tsx
git commit -m "feat(portal): approval approve/reject/cancel actions (checker side)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Detail page — header, payload, actions trail, action buttons, AuditBar

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/approvals/[id]/page.tsx`

> Server component; resolves the request + requester + each action actor + (for `update_sensitive`) the "before" user. Not unit-tested in isolation (consistent with SP16 invoice detail page); typecheck/lint/suite green is the gate.

- [ ] **Step 1: Implement the detail page**

```tsx
// admin/apps/portal/app/platform/(authed)/approvals/[id]/page.tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import {
  AuditBar,
  Card,
  FormattedDateTime,
  StatusBadge,
} from "@sacco/ui";
import type { ApprovalRequestDetailOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { PayloadView } from "./_components/PayloadView";
import { ApprovalActions } from "./_components/ApprovalActions";

export const metadata = { title: "Approval request" };

interface PlatformUserLite {
  id: string;
  email: string;
  full_name?: string | null;
}

function label(u: PlatformUserLite | undefined, id: string): string {
  if (!u) return id;
  return u.full_name && u.full_name.length > 0 ? u.full_name : u.email;
}

export default async function ApprovalDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "approvals.read");

  const { data } = await (
    resources.makerChecker.getPlatform(id) as Promise<{
      data?: ApprovalRequestDetailOut;
      error?: unknown;
    }>
  );
  if (!data) notFound();

  const { data: users } = await (
    resources.admin.listUsers() as Promise<{ data?: PlatformUserLite[]; error?: unknown }>
  );
  const usersById = new Map((users ?? []).map((u) => [u.id, u]));

  // "Before" state for the update_sensitive diff only.
  let before: Record<string, unknown> | undefined;
  if (data.operation_type === "platform_user.update_sensitive") {
    const targetId = data.payload["user_id"];
    if (typeof targetId === "string") {
      const { data: target } = await (
        resources.admin.getUser(targetId) as Promise<{
          data?: { is_active?: boolean; is_superuser?: boolean };
          error?: unknown;
        }>
      );
      if (target) {
        before = { is_active: target.is_active, is_superuser: target.is_superuser };
      }
    }
  }

  const subjectLabel = operationLabel(data.operation_type);
  const canApprove = userHasPermission(user, "approvals.approve");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-[var(--text-h3)] font-semibold">{subjectLabel}</h1>
          <StatusBadge entity="approval_request" status={data.status} />
          <span className="text-[var(--text-tertiary)] tabular-nums">
            {data.current_approvals} of {data.required_approvals}
          </span>
        </div>
        <ApprovalActions
          requestId={data.id}
          status={data.status}
          requestedBy={data.requested_by}
          currentUserId={user.id}
          canApprove={canApprove}
          subjectLabel={subjectLabel}
        />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <Row
          label="Requested by"
          value={label(usersById.get(data.requested_by), data.requested_by)}
        />
        <Row label="Requested" value={<FormattedDateTime value={data.requested_at} />} />
        {data.rejection_reason ? <Row label="Rejection reason" value={data.rejection_reason} /> : null}
      </Card>

      <Card className="flex flex-col gap-2 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Details</h2>
        <PayloadView
          operationType={data.operation_type}
          payload={data.payload}
          {...(before !== undefined ? { before } : {})}
        />
      </Card>

      <Card className="flex flex-col gap-2 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Activity</h2>
        {data.actions.length === 0 ? (
          <p className="text-[var(--text-tertiary)]">No actions yet.</p>
        ) : (
          <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
            {data.actions.map((a) => (
              <div key={a.id} className="flex items-start justify-between gap-4 py-2">
                <div className="flex flex-col">
                  <span className="text-[var(--text-primary)]">
                    {label(usersById.get(a.actor_user_id), a.actor_user_id)}{" "}
                    {a.action === "approve" ? "approved" : "rejected"}
                  </span>
                  {a.comment ? (
                    <span className="text-[13px] text-[var(--text-tertiary)]">{a.comment}</span>
                  ) : null}
                </div>
                <FormattedDateTime value={a.acted_at} />
              </div>
            ))}
          </div>
        )}
      </Card>

      <AuditBar entityType="approval_request" entityId={data.id} />
    </div>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-[var(--text-primary)]">{value}</span>
    </div>
  );
}
```

> The `{...(before !== undefined ? { before } : {})}` spread satisfies `exactOptionalPropertyTypes` (the established portal pattern for optional props). `user.id` is the current-user id field — use whatever `CurrentUserShape` actually names it (confirmed in Task 5 Step 2).

- [ ] **Step 2: Typecheck + lint**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add "admin/apps/portal/app/platform/(authed)/approvals/[id]/page.tsx"
git commit -m "feat(portal): approval request detail page (payload, trail, actions, AuditBar)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Full verification + final review

**Files:** none (verification only).

- [ ] **Step 1: Backend gate**

Run:
```bash
cd /home/liam/projects/sacco-platform
ruff check app/ tests/ && mypy app/ && python -m pytest tests/modules/maker_checker/ -q
```
Expected: clean + PASS.

- [ ] **Step 2: Portal per-package gate**

Run:
```bash
cd /home/liam/projects/sacco-platform/admin
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Expected: all PASS / clean. Record the portal test count (it should rise by the ApprovalsTable + PayloadView + ApprovalActions cases over the SP16 baseline of 147).

- [ ] **Step 3: Contract spot-check**

- [ ] Confirm every new portal path is under `admin/` (`git diff --name-only main... | grep -v '^admin/' | grep -v '^app/modules/maker_checker/' | grep -v '^tests/modules/maker_checker/' | grep -v '^docs/'` returns nothing).
- [ ] Confirm no `<MakerCheckerConfirmDialog>` import in the approvals tree (checker side uses base Dialog/ConfirmDialog): `rg "MakerCheckerConfirmDialog" "admin/apps/portal/app/platform/(authed)/approvals"` returns nothing.
- [ ] Confirm the backend change is additive: `git diff main... -- app/modules/maker_checker/schemas.py` shows only added lines (no removed/renamed fields).

- [ ] **Step 4: Final holistic review**

Use superpowers:requesting-code-review against the branch. Confirm: self-approval UI rule mirrors the service invariant; approve copy says "executes" (checker), not "creates an approval request" (maker); quorum badge reads "{current} of {required}"; unknown operation types render a humanized label, not a raw key; AuditBar present on detail.

- [ ] **Step 5: Open the PR**

```bash
cd /home/liam/projects/sacco-platform
gh pr create --title "feat(portal): platform approvals inbox (SP17)" --body "$(cat <<'EOF'
## Summary
- Backend (additive, separate commits): `current_approvals` count on the platform approval list + an `ApprovalRequestDetailOut` actions trail on detail — no new endpoints, no renamed/removed fields, no gate changes.
- Portal: approvals inbox + my-submissions + detail (operation-aware payload with an `update_sensitive` before→after diff, actions trail, approve/reject/cancel as the checker side, AuditBar).
- Unblocks the approve half of every platform maker-checker flow (billing confirm-payment/void/cancel, platform_user update_sensitive, tenant suspend/retry, impersonation).

## Test plan
- Backend: `pytest tests/modules/maker_checker/` (current_approvals on list + detail, actions trail ordering, quorum-2 "1 of 2").
- Portal: `pnpm --filter @sacco/schemas test`, `pnpm --filter @sacco/portal test` (ApprovalsTable, PayloadView, ApprovalActions); typecheck + lint clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

> **CI note:** the Lint check fails environmentally on this repo (account billing lock, not code). Reproduce locally instead; it is not a required check. Merge with the red X like prior portal PRs.

---

## Self-review notes (author)

- **Spec coverage:** Part 1 backend enrichment → Tasks 1–2. `@sacco/schemas` Out types + operation labels + action Zod → Task 3. Inbox + my-submissions → Tasks 4–5. Operation-aware payload + update_sensitive diff → Task 6. Approve/reject/cancel with self-approval mirroring → Task 7. Detail page (header/quorum/payload/trail/AuditBar) → Task 8. Permission mapping enforced via `requirePlatformPermission` + `userHasPermission` throughout. Testing strategy → Tasks 4/6/7 (component) + 1/2 (pytest) + 9 (gate).
- **Deviations flagged:** (1) approve/reject use a form `<Dialog>` not `<ConfirmDialog>` because ConfirmDialog has no field slot (SP16 reject precedent); (2) `user.id` field name must be confirmed against `CurrentUserShape`; (3) `--surface-muted` / `useTypedMutation<…, void>` are the two spots to verify against real exports during execution (grep commands inline).
- **Type consistency:** `ApprovalRow` shape is identical in Task 4 (definition) and Tasks 5/8 (construction); `current_approvals`/`required_approvals`/`operation_label`/`requested_by_label` names match. `ApprovalActionsProps` in Task 7 matches the props passed in Task 8. `operationLabel`/`PLATFORM_OPERATION_LABELS`/`approveActionSchema`/`rejectActionSchema` from Task 3 are consumed exactly in Tasks 4/7/8.
