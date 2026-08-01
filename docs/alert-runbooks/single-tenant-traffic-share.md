# Alert: Single tenant dominating request traffic

Definition: `infra/observability/logfire/alerts/single-tenant-traffic-share.json`

- **Severity:** warning
- **Trigger condition:** one `tenant_schema` span-attribute value accounts
  for more than 10% of all tenant-scoped HTTP server span volume over a
  trailing window (suggested 15m).

## Likely causes

- A legitimate, unusually active tenant (e.g. running a large batch import,
  a bulk report export, or heavy member self-service traffic).
- A misbehaving client integration/script for one tenant polling or
  retrying aggressively (e.g. a broken frontend polling loop, or a script
  hitting an endpoint in a tight loop without backoff).
- A credential-stuffing/scraping attempt scoped to one tenant's login or
  search endpoints.
- A stuck retry loop somewhere in that tenant's own integration hitting a
  failing endpoint repeatedly.

## Response steps

1. Open the tenant-drilldown dashboard (`tenant-drilldown.json`) filtered
   to the flagged `tenant_schema` — check request rate, error rate, and
   which routes (`http.route`) dominate.
2. If the traffic is concentrated on a single route, check whether it's a
   legitimate heavy operation (e.g. reporting export, statement PDF) or a
   clear anomaly (auth endpoint hit thousands of times).
3. Check the tenant's recent support history / any planned bulk operations
   before assuming abuse.
4. If it looks like a retry storm or abusive pattern, consider whether
   Phase 6 (Rate Limiting & Abuse Protection — not yet started as of
   Phase 5 close-out) would have prevented this; in the meantime this may
   require manual intervention (contacting the tenant, or a temporary
   suspend via `TenantService.suspend()` through the maker-checker
   executor if abuse is confirmed and severe).
5. If it's legitimate heavy usage, this may be a capacity-planning signal
   rather than an incident — note it for the tenant's plan/capacity
   conversation.

## Escalation

- If the traffic pattern is degrading other tenants' latency/error rates
  (correlate with the `api-error-rate` / `p99-latency` alerts), treat as an
  active incident and consider emergency mitigation.
- If it's confirmed abusive and isolated, this can be handled as a
  support/security follow-up rather than a page.
