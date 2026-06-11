#!/usr/bin/env bash
set -euo pipefail

API_URL="${SYNABOOT_SCAN_URL:-http://localhost:8080/api/scan}"
ADMIN_TOKEN="${SYNABOOT_ADMIN_TOKEN:-}"

if [[ -z "$ADMIN_TOKEN" ]]; then
  echo "SYNABOOT_ADMIN_TOKEN is required for metadata scan." >&2
  exit 2
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl not found; cannot request metadata scan" >&2
  exit 1
fi

curl --fail --silent --show-error \
  -X POST \
  -H "X-SynaBoot-Admin-Token: ${ADMIN_TOKEN}" \
  "$API_URL" >/dev/null
echo "SynaBoot metadata scan requested."
