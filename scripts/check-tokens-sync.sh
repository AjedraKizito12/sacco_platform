#!/usr/bin/env bash
# scripts/check-tokens-sync.sh
# Verify admin/packages/ui/src/tokens.css is byte-identical to
# docs/tokens.css. Fails CI if they drift.

set -euo pipefail

CANONICAL="docs/tokens.css"
COPY="admin/packages/ui/src/tokens.css"

if ! [ -f "$CANONICAL" ]; then
  echo "FAIL: canonical tokens file missing: $CANONICAL"
  exit 1
fi
if ! [ -f "$COPY" ]; then
  echo "FAIL: portal copy missing: $COPY"
  exit 1
fi

if ! cmp -s "$CANONICAL" "$COPY"; then
  echo "FAIL: tokens.css is out of sync."
  echo "  Canonical: $CANONICAL"
  echo "  Copy:      $COPY"
  echo ""
  echo "Diff:"
  diff "$CANONICAL" "$COPY" || true
  echo ""
  echo "Fix: edit $CANONICAL only, then run:"
  echo "  cp $CANONICAL $COPY"
  exit 1
fi

echo "tokens.css in sync"
