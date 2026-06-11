#!/usr/bin/env bash
set -euo pipefail

SERVER_IP="${SERVER_IP:-192.168.1.168}"
SYNABOOT_HTTP_PORT="${SYNABOOT_HTTP_PORT:-18080}"
API_URL="${SYNABOOT_MENU_GENERATE_URL:-http://${SERVER_IP}:${SYNABOOT_HTTP_PORT}/api/menu/generate}"
ADMIN_TOKEN="${SYNABOOT_ADMIN_TOKEN:-}"

if [[ -z "$ADMIN_TOKEN" ]]; then
  printf 'ERROR: SYNABOOT_ADMIN_TOKEN is required to regenerate menu.ipxe\n' >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  printf 'ERROR: curl is required\n' >&2
  exit 1
fi

tmp_file="$(mktemp)"
cleanup() {
  rm -f "$tmp_file"
}
trap cleanup EXIT

http_code="$(
  curl -sS \
    -X POST \
    -H "X-SynaBoot-Admin-Token: ${ADMIN_TOKEN}" \
    -o "$tmp_file" \
    -w '%{http_code}' \
    "$API_URL"
)"

if [[ "$http_code" != "200" ]]; then
  printf 'ERROR: menu generation failed: HTTP %s\n' "$http_code" >&2
  cat "$tmp_file" >&2
  exit 1
fi

cat "$tmp_file"
