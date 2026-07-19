#!/usr/bin/env bash
# Redeploy the SACCO staging stack: pull, build, migrate, restart.
# Run as the deploy user on the VPS, from the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.staging.yml --env-file .env.staging"

[ -f .env.staging ] || { echo "ERROR: .env.staging missing. Run scripts/gen_staging_env.sh first." >&2; exit 1; }

echo "==> Pulling latest code"
git pull --ff-only

echo "==> Building images"
$COMPOSE build

echo "==> Running migrations"
$COMPOSE run --rm migrate

echo "==> Starting services"
$COMPOSE up -d

echo "==> Status"
$COMPOSE ps
echo "Deploy complete. Portal: https://staging.$(grep '^STAGING_DOMAIN=' .env.staging | cut -d= -f2)"
