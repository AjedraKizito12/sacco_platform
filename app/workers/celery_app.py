from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "sacco",
    broker=settings.redis_url,  # Redis as broker (rabbitmq for events, redis for tasks)
    include=[
        "app.core.outbox.worker",
        "app.core.outbox.retention",
        "app.platform_.provisioning.tasks",
        "app.modules.iam.beat",
        "app.modules.fees.consumer",
        "app.modules.fees.beat",
        "app.modules.credit.beat",
        "app.modules.credit.consumer",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "relay-platform-outbox": {
            "task": "app.core.outbox.worker.relay_platform_outbox",
            "schedule": 5.0,
        },
        "relay-tenant-outbox": {
            "task": "app.core.outbox.worker.relay_tenant_outbox",
            "schedule": 5.0,
        },
        "purge-outbox-retention": {
            "task": "app.core.outbox.retention.purge_outbox_retention",
            "schedule": 30 * 24 * 3600,  # monthly
        },
        "expire-approval-requests": {
            "task": "app.modules.maker_checker.service.expire_approval_requests",
            "schedule": 3600.0,  # hourly
        },
        "advance-jwt-key-lifecycle": {
            "task": "app.modules.iam.beat.advance_key_lifecycle",
            "schedule": 3600.0,  # hourly
        },
        "rotate-jwt-keys-if-due": {
            "task": "app.modules.iam.beat.rotate_signing_keys_if_due",
            "schedule": 24 * 3600.0,  # daily
        },
        "cleanup-iam-sessions": {
            "task": "app.modules.iam.beat.cleanup_sessions",
            "schedule": 24 * 3600.0,  # daily
        },
        "consume-fee-events": {
            "task": "app.modules.fees.consumer.consume_fee_events",
            "schedule": 60.0,  # every minute
        },
        "consume-credit-events": {
            "task": "app.modules.credit.consumer.consume_credit_events",
            "schedule": 60.0,  # every minute
        },
        "assess-scheduled-fees": {
            "task": "app.modules.fees.beat.assess_scheduled_fees",
            "schedule": 24 * 3600.0,  # daily
        },
        "retry-partial-fee-collections": {
            "task": "app.modules.fees.beat.retry_partial_fee_collections",
            "schedule": 24 * 3600.0,  # daily
        },
        "accrue-reducing-balance-interest": {
            "task": "app.modules.credit.beat.accrue_reducing_balance_interest",
            "schedule": 24 * 3600.0,  # daily
        },
        "mark-loans-in-arrears": {
            "task": "app.modules.credit.beat.mark_loans_in_arrears",
            "schedule": 24 * 3600.0,  # daily
        },
        "reconcile-loan-snapshots": {
            "task": "app.modules.credit.beat.reconcile_loan_snapshots",
            "schedule": 24 * 3600.0,  # daily
        },
    },
)
