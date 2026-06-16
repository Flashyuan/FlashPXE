#!/usr/bin/env bash
set -euo pipefail

# SYNABOOT_LAB_ONLY_BIND=10.101.8.135
# SYNABOOT_LAB_ONLY_INTERFACE=ens19

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

docker compose -p synaboot-smb-lab -f docker-compose.smb-lab.yml down
ss -lntu | grep -E '(:445\b|:139\b)' || true
