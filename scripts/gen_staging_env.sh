#!/usr/bin/env bash
# Generate .env.staging from .env.staging.example with strong random secrets.
# Usage: STAGING_DOMAIN=your.tld scripts/gen_staging_env.sh
set -euo pipefail

cd "$(dirname "$0")/.."
OUT=.env.staging
[ -f "$OUT" ] && { echo "ERROR: $OUT already exists; refusing to overwrite." >&2; exit 1; }
: "${STAGING_DOMAIN:?Set STAGING_DOMAIN=your.tld}"

KEK=$(openssl rand -base64 32)
COOKIE=$(openssl rand -hex 32)
PGPW=$(openssl rand -hex 24)
MQPW=$(openssl rand -hex 24)

sed \
  -e "s|^STAGING_DOMAIN=.*|STAGING_DOMAIN=${STAGING_DOMAIN}|" \
  -e "s|^JWT_KEK=.*|JWT_KEK=${KEK}|" \
  -e "s|^COOKIE_SECRET=.*|COOKIE_SECRET=${COOKIE}|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PGPW}|" \
  -e "s|^RABBITMQ_PASSWORD=.*|RABBITMQ_PASSWORD=${MQPW}|" \
  -e "s|REPLACE_ME_random@postgres|${PGPW}@postgres|" \
  -e "s|REPLACE_ME_random@rabbitmq|${MQPW}@rabbitmq|" \
  -e "s|staging\\.example\\.com|staging.${STAGING_DOMAIN}|g" \
  -e "s|api-staging\\.example\\.com|api-staging.${STAGING_DOMAIN}|g" \
  .env.staging.example > "$OUT"

chmod 600 "$OUT"
echo "Wrote $OUT (mode 600). Review it, then run scripts/deploy.sh."
