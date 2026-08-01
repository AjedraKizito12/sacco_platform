# Runbook: Single-tenant recovery

**When to use:** one tenant's data is damaged (bad import, accidental bulk
delete, a tenant-scoped migration gone wrong) but the rest of the platform is
healthy. Rolling the whole cluster back with
[PITR](./restore-from-pitr.md) would punish every other tenant, so instead we
restore a **throwaway** copy of the cluster to the target time, extract just
that tenant's schema, and load it back into the live primary.

> Each tenant lives in its own Postgres schema named `tenant_<slug>`. This
> procedure moves exactly one such schema. It never touches `platform` or any
> other tenant.

## Preconditions

- The tenant slug, e.g. `demo_sacco` → schema `tenant_demo_sacco`.
- A recovery target timestamp (UTC) at which the tenant's data was still good.
- The pgBackRest repo + secrets (as in the PITR runbook).
- A maintenance window for the affected tenant only — its users should be locked
  out (suspend the tenant, or coordinate) while its schema is swapped.

## Procedure

1. **Restore a throwaway cluster to the target time.** This reuses the drill's
   ephemeral-container approach so the live primary is never at risk. Bring up an
   isolated Postgres from the archiving image, restore into it as `postgres`, and
   start it. (The verify drill script `infra/backups/scripts/restore-staging.sh`
   does exactly this to a point-in-time of *latest*; for a specific target add
   `--type=time --target='<ts>'` to its `pgbackrest restore` line, or run the
   steps from [`restore-from-pitr.md`](./restore-from-pitr.md) against a scratch
   container name.)

2. **Dump only the tenant schema** from the throwaway cluster:
   ```bash
   docker exec <staging-container> pg_dump -U sacco -d sacco \
     --schema=tenant_demo_sacco --format=custom \
     --file=/tmp/tenant_demo_sacco.dump
   docker cp <staging-container>:/tmp/tenant_demo_sacco.dump ./tenant_demo_sacco.dump
   ```

3. **Preserve the current (damaged) schema on the primary** — do NOT drop it
   outright; rename it so you can diff / roll back.
   ```bash
   docker compose exec -T postgres psql -U sacco -d sacco -c \
     "ALTER SCHEMA tenant_demo_sacco RENAME TO tenant_demo_sacco_damaged_20260801;"
   ```

4. **Restore the tenant schema into the live primary.**
   ```bash
   docker cp ./tenant_demo_sacco.dump sacco-platform-postgres-1:/tmp/t.dump
   docker compose exec -T postgres pg_restore -U sacco -d sacco \
     --schema=tenant_demo_sacco /tmp/t.dump
   ```

5. **Verify the tenant, then re-open it.**
   ```bash
   docker compose exec -T postgres psql -U sacco -d sacco -c \
     "SET search_path TO tenant_demo_sacco; SELECT count(*) FROM members;"
   ```
   Reactivate the tenant once the counts look right.

6. **Clean up** once you are confident:
   ```bash
   docker rm -f <staging-container>
   # After a retention period, drop the renamed damaged schema:
   # DROP SCHEMA tenant_demo_sacco_damaged_20260801 CASCADE;
   ```

## Cautions

- **Never restore the `platform` schema this way.** `platform.tenants`,
  subscriptions, billing, and signing keys are cluster-global and must stay
  current. A single-tenant recovery moves only `tenant_<slug>`.
- **search_path matters.** Tenant tables declare no schema and resolve via
  `SET LOCAL search_path`. Always qualify with `--schema=tenant_<slug>` on
  dump/restore and set `search_path` explicitly when verifying — a bare
  `SELECT ... FROM members` hits whatever schema is first on the path.
- **Cross-schema references.** Tenant rows reference `platform` (e.g. audit
  actor ids, billing) by plain UUID, not FK across schemas, so a schema-only
  restore does not break referential integrity — but a restored tenant may point
  at `platform` rows (users, subscription state) that have since changed. Sanity-
  check billing/subscription status after the swap.
- **Sequences and identity.** `pg_restore` of a custom-format schema dump carries
  sequence state; confirm no id collisions if the tenant kept transacting after
  the target time (it should have been locked out — step 0).
