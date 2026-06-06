"""HTTP API for the billing module.

platform_router (mounted at /platform/billing): admin-only CRUD + maker-checker
tenant_router   (mounted at /billing/me):       read-only tenant-facing views
"""
from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_platform_session
from app.modules.iam.dependencies import CurrentTenantUser, get_current_tenant_user
from app.modules.maker_checker.service import ApprovalService
from app.platform_.auth import CurrentPlatformUser, get_current_platform_user
from app.platform_.billing.exceptions import (
    InvalidTransition,
    PaymentConflict,
    PlanInactive,
    SubscriptionConflict,
)
from app.platform_.billing.schemas import (
    InvoiceDetailOut,
    InvoiceOut,
    InvoiceVoidIn,
    PaymentOut,
    PaymentRecordIn,
    SubscriptionCancelIn,
    SubscriptionCreateIn,
    SubscriptionOut,
    SubscriptionPlanIn,
    SubscriptionPlanOut,
    SubscriptionPlanPatch,
)
from app.platform_.billing.services import (
    InvoiceService,
    PaymentService,
    PlanCodeConflict,
    PlanService,
    SubscriptionService,
)
from app.platform_.models import PlatformUser, Tenant


class PaymentRejectIn(BaseModel):
    reason: str

_log = structlog.get_logger(__name__)

platform_router = APIRouter(prefix="/platform/billing", tags=["billing-platform"])
tenant_router = APIRouter(prefix="/billing/me", tags=["billing-tenant"])


# ── Plans ─────────────────────────────────────────────────────────────────────


@platform_router.get(
    "/plans",
    response_model=list[SubscriptionPlanOut],
)
async def list_plans(
    _user: CurrentPlatformUser,
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    only_active: bool = False,
) -> list[SubscriptionPlanOut]:
    plans = await PlanService(session).list_plans(only_active=only_active)
    return [SubscriptionPlanOut.model_validate(p) for p in plans]


@platform_router.post(
    "/plans",
    response_model=SubscriptionPlanOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan(
    payload: SubscriptionPlanIn,
    _user: CurrentPlatformUser,
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionPlanOut:
    try:
        plan = await PlanService(session).create(**payload.model_dump())
    except PlanCodeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SubscriptionPlanOut.model_validate(plan)


@platform_router.get(
    "/plans/{plan_id}",
    response_model=SubscriptionPlanOut,
)
async def get_plan(
    plan_id: uuid.UUID,
    _user: CurrentPlatformUser,
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionPlanOut:
    plan = await PlanService(session).get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return SubscriptionPlanOut.model_validate(plan)


@platform_router.patch(
    "/plans/{plan_id}",
    response_model=SubscriptionPlanOut,
)
async def update_plan(
    plan_id: uuid.UUID,
    payload: SubscriptionPlanPatch,
    _user: CurrentPlatformUser,
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionPlanOut:
    try:
        plan = await PlanService(session).update(
            plan_id=plan_id,
            **payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlanCodeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SubscriptionPlanOut.model_validate(plan)


# ── Subscriptions ─────────────────────────────────────────────────────────────


@platform_router.get(
    "/subscriptions",
    response_model=list[SubscriptionOut],
)
async def list_subscriptions(
    _user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    tenant_id: uuid.UUID | None = None,
    status_filter: str | None = None,
) -> list[SubscriptionOut]:
    from sqlalchemy import select

    from app.platform_.billing.models import Subscription

    q = select(Subscription).order_by(Subscription.created_at.desc())
    if tenant_id is not None:
        q = q.where(Subscription.tenant_id == tenant_id)
    if status_filter is not None:
        q = q.where(Subscription.status == status_filter)
    result = await session.execute(q)
    return [SubscriptionOut.model_validate(s) for s in result.scalars().all()]


@platform_router.post(
    "/subscriptions",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
)
async def assign_subscription(
    payload: SubscriptionCreateIn,
    _user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionOut:
    try:
        sub = await SubscriptionService(session).assign(
            tenant_id=payload.tenant_id,
            plan_id=payload.plan_id,
            start_date=payload.start_date,
        )
    except PlanInactive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SubscriptionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SubscriptionOut.model_validate(sub)


@platform_router.get(
    "/subscriptions/{subscription_id}",
    response_model=SubscriptionOut,
)
async def get_subscription(
    subscription_id: uuid.UUID,
    _user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionOut:
    sub = await SubscriptionService(session).get(subscription_id)
    if sub is None:
        raise HTTPException(
            status_code=404, detail=f"Subscription {subscription_id} not found"
        )
    return SubscriptionOut.model_validate(sub)


@platform_router.post("/subscriptions/{subscription_id}/cancel")
async def cancel_subscription(
    subscription_id: uuid.UUID,
    payload: SubscriptionCancelIn,
    user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    mode: str = "at_period_end",
) -> dict[str, str]:
    """Cancel a subscription. Two modes:

    - mode=at_period_end (default): graceful — sets cancelled_at + reason,
      status changes at period end (beat job). No maker-checker.
    - mode=immediate: hard cancel — creates an ApprovalRequest. The checker
      must approve, then the billing.cancel_subscription executor flips status.
    """
    if mode not in {"at_period_end", "immediate"}:
        raise HTTPException(
            status_code=400, detail="mode must be 'at_period_end' or 'immediate'"
        )

    if mode == "at_period_end":
        try:
            sub = await SubscriptionService(session).cancel(
                subscription_id=subscription_id,
                reason=payload.reason,
                cancel_at_period_end=True,
            )
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "status": "cancellation_scheduled",
            "subscription_id": str(sub.id),
        }

    # mode == "immediate" — go through maker-checker
    existing = await SubscriptionService(session).get(subscription_id)
    if existing is None:
        raise HTTPException(
            status_code=404, detail=f"Subscription {subscription_id} not found"
        )

    approval_request = await ApprovalService(session).submit(
        operation_type="billing.cancel_subscription",
        payload={
            "subscription_id": str(subscription_id),
            "reason": payload.reason,
        },
        requested_by=user.id,
    )
    return {
        "status": "pending_approval",
        "approval_request_id": str(approval_request.id),
    }


@platform_router.post(
    "/subscriptions/{subscription_id}/reactivate",
    response_model=SubscriptionOut,
)
async def reactivate_subscription(
    subscription_id: uuid.UUID,
    _user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionOut:
    try:
        sub = await SubscriptionService(session).reactivate(
            subscription_id=subscription_id
        )
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SubscriptionOut.model_validate(sub)


# ── Invoices ──────────────────────────────────────────────────────────────────


@platform_router.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(
    _user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    tenant_id: uuid.UUID | None = None,
    status_filter: str | None = None,
) -> list[InvoiceOut]:
    from sqlalchemy import select

    from app.platform_.billing.models import Invoice

    q = select(Invoice).order_by(Invoice.created_at.desc())
    if tenant_id is not None:
        q = q.where(Invoice.tenant_id == tenant_id)
    if status_filter is not None:
        q = q.where(Invoice.status == status_filter)
    result = await session.execute(q)
    return [InvoiceOut.model_validate(inv) for inv in result.scalars().all()]


# NOTE: this route MUST be registered before /invoices/{invoice_id} so that
# Starlette's router matches the literal ".pdf" suffix first, before the
# catch-all {invoice_id} pattern grabs the whole "{uuid}.pdf" segment.
@platform_router.get(
    "/invoices/{invoice_id}.pdf",
    response_class=Response,
)
async def get_invoice_pdf(
    invoice_id: uuid.UUID,
    _user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> Response:
    from sqlalchemy import select

    from app.platform_.billing.models import InvoiceLineItem
    from app.platform_.billing.pdf import render_invoice_pdf

    invoice = await InvoiceService(session).get(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    line_result = await session.execute(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_order)
    )
    lines = list(line_result.scalars().all())
    pdf_bytes = render_invoice_pdf(invoice, lines)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="{invoice.invoice_number}.pdf"'
            ),
        },
    )


@platform_router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut)
async def get_invoice(
    invoice_id: uuid.UUID,
    _user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> InvoiceDetailOut:
    from sqlalchemy import select

    from app.platform_.billing.models import InvoiceLineItem

    invoice = await InvoiceService(session).get(invoice_id)
    if invoice is None:
        raise HTTPException(
            status_code=404, detail=f"Invoice {invoice_id} not found"
        )
    line_result = await session.execute(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_order)
    )
    lines = list(line_result.scalars().all())
    inv_dict = InvoiceOut.model_validate(invoice).model_dump()
    inv_dict["line_items"] = [
        {
            "id": line.id,
            "invoice_id": line.invoice_id,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "amount": line.amount,
            "line_order": line.line_order,
        }
        for line in lines
    ]
    return InvoiceDetailOut.model_validate(inv_dict)


@platform_router.post("/invoices/{invoice_id}/void")
async def void_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceVoidIn,
    user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> dict[str, str]:
    """Submit a void-invoice approval request. The actual void runs in
    the `billing.void_invoice` executor on approval.
    """
    invoice = await InvoiceService(session).get(invoice_id)
    if invoice is None:
        raise HTTPException(
            status_code=404, detail=f"Invoice {invoice_id} not found"
        )

    approval_request = await ApprovalService(session).submit(
        operation_type="billing.void_invoice",
        payload={"invoice_id": str(invoice_id), "reason": payload.reason},
        requested_by=user.id,
    )
    return {
        "status": "pending_approval",
        "approval_request_id": str(approval_request.id),
    }


# ── Payments ──────────────────────────────────────────────────────────────────


@platform_router.post("/invoices/{invoice_id}/payments")
async def record_payment(
    invoice_id: uuid.UUID,
    payload: PaymentRecordIn,
    user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> dict[str, str]:
    """Maker action: create Payment(pending) + ApprovalRequest in one tx.

    The checker approves via `POST /platform/approvals/{id}/approve`
    (which triggers the `billing.confirm_payment` executor) OR rejects via
    `POST /platform/billing/payments/{id}/reject`.
    """
    invoice = await InvoiceService(session).get(invoice_id)
    if invoice is None:
        raise HTTPException(
            status_code=404, detail=f"Invoice {invoice_id} not found"
        )

    try:
        pmt = await PaymentService(session).record(
            invoice_id=invoice_id,
            amount=payload.amount,
            currency=payload.currency,
            payment_method=payload.payment_method,
            external_reference=payload.external_reference,
            notes=payload.notes,
            recorded_by=user.id,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # If the payment was idempotently returned (same key, existing row),
    # it might already have an approval_request_id. Don't create a duplicate.
    if pmt.approval_request_id is not None:
        return {
            "status": "pending_approval",
            "payment_id": str(pmt.id),
            "approval_request_id": str(pmt.approval_request_id),
            "idempotent": "true",
        }

    approval_request = await ApprovalService(session).submit(
        operation_type="billing.confirm_payment",
        payload={"payment_id": str(pmt.id)},
        requested_by=user.id,
    )
    # Link the Payment to the ApprovalRequest.
    pmt.approval_request_id = approval_request.id
    await session.flush()

    return {
        "status": "pending_approval",
        "payment_id": str(pmt.id),
        "approval_request_id": str(approval_request.id),
    }


@platform_router.post("/payments/{payment_id}/reject")
async def reject_payment(
    payment_id: uuid.UUID,
    payload: PaymentRejectIn,
    user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> dict[str, str]:
    """Checker action: reject a pending payment.

    Pairs ApprovalService.reject + PaymentService.reject in one transaction.
    Self-rejection (maker == rejector) is rejected.
    """
    pmt = await PaymentService(session).get(payment_id)
    if pmt is None:
        raise HTTPException(
            status_code=404, detail=f"Payment {payment_id} not found"
        )
    if pmt.approval_request_id is None:
        raise HTTPException(
            status_code=409,
            detail=f"Payment {payment_id} has no associated approval request",
        )

    try:
        await ApprovalService(session).reject(
            request_id=pmt.approval_request_id,
            actor_user_id=user.id,
            reason=payload.reason,
        )
        await PaymentService(session).reject(
            payment_id=payment_id,
            rejected_by=user.id,
            reason=payload.reason,
        )
    except (ValueError, PaymentConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {"status": "rejected", "payment_id": str(payment_id)}


@platform_router.get(
    "/payments/pending-confirmation",
    response_model=list[PaymentOut],
)
async def list_pending_payments(
    _user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> list[PaymentOut]:
    from sqlalchemy import select

    from app.platform_.billing.models import Payment

    q = (
        select(Payment)
        .where(Payment.status == "pending")
        .order_by(Payment.recorded_at.desc())
    )
    result = await session.execute(q)
    return [PaymentOut.model_validate(p) for p in result.scalars().all()]


# ── Tenant-facing /billing/me endpoints ───────────────────────────────────────


async def _get_tenant_id_from_slug(
    request: Request,
    platform_session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> uuid.UUID:
    """Resolve the tenant UUID from the X-Tenant-Slug header.

    Billing data is stored in platform.* and keyed by tenant.id (UUID).
    The tenant schema context gives us the slug; we join to platform.tenants
    to get the stable primary key for billing lookups.
    """
    settings = get_settings()
    slug: str | None = request.headers.get(settings.tenant_header)
    if not slug:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required header: {settings.tenant_header}",
        )
    tenant = await platform_session.scalar(
        select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True))
    )
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")
    return tenant.id


# NOTE: /invoices/{invoice_id}.pdf MUST be registered BEFORE /invoices/{invoice_id}
# so that Starlette matches the literal ".pdf" suffix before the UUID catch-all.


@tenant_router.get(
    "/invoices/{invoice_id}.pdf",
    response_class=Response,
)
async def get_my_invoice_pdf(
    invoice_id: uuid.UUID,
    _user: Annotated[CurrentTenantUser, Depends(get_current_tenant_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    tenant_id: Annotated[uuid.UUID, Depends(_get_tenant_id_from_slug)],
) -> Response:
    from sqlalchemy import select

    from app.platform_.billing.models import InvoiceLineItem
    from app.platform_.billing.pdf import render_invoice_pdf

    invoice = await InvoiceService(session).get(invoice_id)
    # Cross-tenant access: 404 (not 403) to avoid leaking existence.
    if invoice is None or invoice.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    line_result = await session.execute(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_order)
    )
    lines = list(line_result.scalars().all())
    pdf_bytes = render_invoice_pdf(invoice, lines)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="{invoice.invoice_number}.pdf"'
            ),
        },
    )


@tenant_router.get("/subscription", response_model=SubscriptionOut)
async def get_my_subscription(
    _user: Annotated[CurrentTenantUser, Depends(get_current_tenant_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    tenant_id: Annotated[uuid.UUID, Depends(_get_tenant_id_from_slug)],
) -> SubscriptionOut:
    sub = await SubscriptionService(session).get_live_for_tenant(tenant_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="No active subscription")
    return SubscriptionOut.model_validate(sub)


@tenant_router.get("/invoices", response_model=list[InvoiceOut])
async def list_my_invoices(
    _user: Annotated[CurrentTenantUser, Depends(get_current_tenant_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    tenant_id: Annotated[uuid.UUID, Depends(_get_tenant_id_from_slug)],
) -> list[InvoiceOut]:
    from sqlalchemy import select

    from app.platform_.billing.models import Invoice

    q = (
        select(Invoice)
        .where(Invoice.tenant_id == tenant_id)
        .order_by(Invoice.created_at.desc())
    )
    result = await session.execute(q)
    return [InvoiceOut.model_validate(inv) for inv in result.scalars().all()]


@tenant_router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut)
async def get_my_invoice(
    invoice_id: uuid.UUID,
    _user: Annotated[CurrentTenantUser, Depends(get_current_tenant_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    tenant_id: Annotated[uuid.UUID, Depends(_get_tenant_id_from_slug)],
) -> InvoiceDetailOut:
    from sqlalchemy import select

    from app.platform_.billing.models import InvoiceLineItem

    invoice = await InvoiceService(session).get(invoice_id)
    # Cross-tenant access: 404 (not 403) to avoid leaking existence.
    if invoice is None or invoice.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    line_result = await session.execute(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_order)
    )
    lines = list(line_result.scalars().all())
    inv_dict = InvoiceOut.model_validate(invoice).model_dump()
    inv_dict["line_items"] = [
        {
            "id": line.id,
            "invoice_id": line.invoice_id,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "amount": line.amount,
            "line_order": line.line_order,
        }
        for line in lines
    ]
    return InvoiceDetailOut.model_validate(inv_dict)
