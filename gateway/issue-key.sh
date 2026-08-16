#!/usr/bin/env bash
# Issue the agent a per-app virtual key (ADR-0006): budgeted, rate-limited,
# rotatable. Re-running issues a fresh key — that IS the rotation procedure.
#
#   ./gateway/issue-key.sh
#   # paste the printed key into .env as LITELLM_API_KEY, then:
#   docker compose up -d --force-recreate agent
set -euo pipefail

GATEWAY=${GATEWAY:-http://localhost:4000}
MASTER_KEY=${LITELLM_MASTER_KEY:-$(grep '^LITELLM_MASTER_KEY=' .env | cut -d= -f2-)}

KEY=$(curl -sf "$GATEWAY/key/generate" \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H 'content-type: application/json' \
  -d "{
    \"key_alias\": \"agent-$(date +%s)\",
    \"max_budget\": 5,
    \"rpm_limit\": 30,
    \"metadata\": {\"service\": \"agent\"}
  }" | python3 -c "import sys, json; print(json.load(sys.stdin)['key'])")

echo "$KEY"
echo >&2
echo "Virtual key issued: budget \$5, 30 rpm." >&2
echo "Set it in .env:  LITELLM_API_KEY=$KEY" >&2
echo "Then:            docker compose up -d --force-recreate agent" >&2
