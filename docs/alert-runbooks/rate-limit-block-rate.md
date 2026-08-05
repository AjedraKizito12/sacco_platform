# Alert: Rate-limit block rate elevated

Definition: `infra/observability/logfire/alerts/rate-limit-block-rate.json`

- **Severity:** warning
- **Trigger condition:** `sacco_rate_limit_blocks_total` (counter, labelled
  `{policy, audience}`) grows by more than 100 within the trailing minute.

## First: this is NOT a limiter outage

The rate limiter **fails open** — a Redis error allows the request through and
sets `sacco_rate_limit_redis_health=0` instead. So a spike in *blocks* means
the limiter is working and actively rejecting traffic, not that it is broken.
If you are here because the platform feels degraded, check
`sacco_rate_limit_redis_health` first — that is the outage signal.

## Likely causes

- **Credential stuffing / brute force** against an anonymous auth policy —
  `audience=anonymous`, `policy=auth_login` (or `auth_password_reset`). A
  single or small set of source IPs hammering `/auth/token`.
- **Scraping / abusive automation** against `anonymous_default`.
- **A mis-tuned limit throttling legitimate traffic** — `audience=tenant` /
  `member` / `platform` on `authenticated_default`, `reporting`, or `export`.
  This is the false-positive case: a real workload outgrew the budget.

## Response steps

1. Break the metric out by the `policy` and `audience` labels (Logfire
   dashboard or ad-hoc query) to see which bucket is driving the spike. The
   audience label is the fork in the road: `anonymous` → likely abuse;
   authenticated → likely a limit that is too low.
2. **If anonymous / abuse:** correlate with the FastAPI span data for the
   affected path and source IP (blocks carry no user_id by design, but the
   spans show `http.target` and client host). Confirm it is hostile traffic,
   not a broken client retry loop. Mitigate upstream (Caddy / WAF / IP block)
   — the limiter is already doing its job of shedding the load; the alert is
   telling you an attack is in progress.
3. **If authenticated / false positive:** identify the tenant or workload.
   The fix is a **per-plan override**, not a code change: set
   `rate_limit_overrides` under `subscription_plans.features` for the
   relevant plan (see `docs/rate-limit-policies.md`). The Redis override
   cache is 300s, so the new limit takes effect within ~5 minutes.
4. If the limit itself is wrong for everyone (not just one plan), change the
   default in `app/core/rate_limit/policies.py` (`_RULES`) — that is a code
   change and a deploy.
5. In a genuine emergency where the limiter is doing more harm than good,
   the kill switch is `RATE_LIMIT_ENABLED=false` (pass-through). Prefer a
   targeted override over the global kill switch.

## Escalation

- Suspected attack that upstream mitigation can't contain → platform
  on-call / security.
- Repeated false positives for the same plan → tune the plan override and
  fold the finding back into the default policy table if it generalises.
