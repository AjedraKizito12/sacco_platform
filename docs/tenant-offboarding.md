# Tenant Offboarding & Retention (Phase 7)

A staged, **reversible-until-archived** tenant lifecycle with an audit trail,
customer notifications, a method-aware read-only gate, and Phase-4-style
infra-side encrypted archival.

## Lifecycle state machine

```
                cancel (MC q=2)          +7d beat            +83d beat
   ┌────────┐  ───────────────►  ┌───────────┐  ─────────►  ┌───────────┐
   │ active │                    │ cancelled │             │ read_only │
   └────────┘  ◄───────────────  └───────────┘  ◄─────────  └───────────┘
        ▲            restore            restore  (schema still present) │
        │  restore                                                      │ +83d beat
        └──────────────────────────────────────────────┐               ▼
                                                        │        ┌──────────┐
                             restore is REFUSED once    │        │ archived │
                             archive_checksum is set    └────────└──────────┘
                             (schema physically dropped)                 │  +2555d beat
                                                                         ▼
                                                                 ┌──────────────┐
                                                                 │ hard_deleted │
                                                                 └──────────────┘
```

- `active → cancelled` — operator action, **maker-checker quorum 2**
  (`tenant.cancel` executor). Hard-cancels billing in the same transaction.
- `cancelled → read_only → archived → hard_deleted` — time-based, driven by
  three daily beat sweeps once the retention window for each state elapses.
- `restore` (direct, superuser) returns any of `cancelled`/`read_only`/
  `archived` to `active` — **but only while `archive_checksum IS NULL`**
  (the schema still exists). After physical archival, restore is refused.
- `hard_deleted` is terminal.

`OffboardingService` (`app/platform_/tenants/offboarding_service.py`) is the
**only** writer of `lifecycle_state`, the `*_at` timestamps, and
`retention_hold_until`, and the only inserter of `tenant_lifecycle_events`.
Offboarding **never** sets `is_active = false` — a `read_only` tenant must stay
resolvable so GETs reach the gate.

## Retention windows (settings)

| Setting | Default | Transition |
|---|---|---|
| `OFFBOARDING_READ_ONLY_DAYS` | 7 | cancelled → read_only |
| `OFFBOARDING_ARCHIVE_DAYS` | 83 | read_only → archived |
| `OFFBOARDING_HARD_DELETE_DAYS` | 2555 (~7y) | archived → hard_deleted |

Per-tenant deviation is only via `retention_hold_until` (a legal hold). The
`read_only → archived` sweep skips any tenant whose `retention_hold_until` is
in the future. Extend it via `POST /platform/tenants/{id}/extend-retention`.

## Request gate (method-aware)

`_check_offboarding_gate(slug, method)` in `app/core/db.py` runs on every
tenant-scoped request, **before** the subscription gate:

| lifecycle_state | GET/HEAD/OPTIONS | writes |
|---|---|---|
| `active` (or no row) | allow | allow |
| `read_only` | allow | **403** "Tenant is read-only (offboarding)." |
| `cancelled` / `archived` / `hard_deleted` | **403** | **403** "Tenant has been offboarded." |

`get_platform_session` is **not** gated — operators manage tenants in any state.

## Endpoints

| Endpoint | Auth | Maker-checker |
|---|---|---|
| `POST /platform/tenants/{id}/cancel` | superuser | **yes, q=2** (`tenant.cancel`) |
| `POST /platform/tenants/{id}/restore` | superuser | no (direct) |
| `POST /platform/tenants/{id}/extend-retention` | superuser | no (direct) |
| `GET /platform/tenants/{id}/lifecycle` | support+ | — (timeline read) |
| `GET /platform/tenants?lifecycle_state=archived` | support+ | — (archived list) |

Billing coupling: `cancel` calls `SubscriptionService.cancel(cancel_at_period_end=False)`
in the same transaction (the quorum-2 maker-checker is the authorising signal).
`restore` leaves `subscription_status` untouched — re-assign a plan separately
to resume billing.

## Notifications

Each transition (cancelled / read_only / archived / restored — **not**
hard_deleted) publishes a platform-outbox event; `offboarding_consumer`
(`app/core/notifications/offboarding_consumer.py`, 60s beat) bridges it to every
active admin `tenant_user`'s in-app/email feed. Notices only — context is
`{tenant_name, to_state, occurred_at}`, no secrets/PII.

## Physical archival (infra-side)

The app only sets `lifecycle_state='archived'`. The physical
`pg_dump → age-encrypt → upload → DROP SCHEMA CASCADE → write telemetry`
happens entirely in `infra/offboarding/` (nightly systemd timer), keyed off the
"ready" signal `lifecycle_state='archived' AND archive_checksum IS NULL`. No
`pg_dump`, `age`, S3 client, or `DROP SCHEMA` lives in the app image. See
`infra/offboarding/README.md`.

### Retrieving an archive (restore after physical archival)

There is **no in-app download**. To recover a physically archived tenant:

1. Read `archive_storage_key`, `archive_size_bytes`, `archive_checksum` from
   `platform.tenants` for the tenant.
2. Fetch the object: `aws s3 cp s3://$OFFBOARDING_BUCKET/<key> ./t.sql.age`.
   Verify `sha256sum` matches `archive_checksum`.
3. Decrypt with the **age private key** (kept off the archival host):
   `age -d -i key.txt t.sql.age > t.sql`.
4. `psql` the dump into a fresh schema on a recovery instance and reconcile
   manually. This is a deliberate manual runbook, not an API surface —
   physical archival is meant to be a rare, audited recovery.

## Monitoring

`infra/observability/logfire/alerts/offboarding-archive-stuck.json` (staged
`unavailable`) documents the alert for tenants stuck in `archived` with a null
checksum > 24h (i.e. the infra job failed). Runbook:
`docs/alert-runbooks/offboarding-archive-stuck.md`.
