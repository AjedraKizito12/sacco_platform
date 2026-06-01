"""Billing payment-processor package.

Re-exports the public surface. Stubs (Flutterwave/Stripe/MoMo) are
intentionally NOT re-exported — code paths that need them import them
directly from their module so the import error surface is small.
"""
from app.platform_.billing.processors.base import PaymentProcessor, ProcessorResult
from app.platform_.billing.processors.offline import OfflineProcessor

__all__ = ["OfflineProcessor", "PaymentProcessor", "ProcessorResult"]
