#!/usr/bin/env bash
set -euo pipefail

# SYNABOOT_LAB_ONLY_BIND=10.101.8.135
# SYNABOOT_LAB_ONLY_INTERFACE=ens19
# SYNABOOT_REQUIRES_MANUAL_SUDO_CONFIRMATION=1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

LAB_IP="${SYNABOOT_LAB_IP:-10.101.8.135}"
PROD_IP="${SYNABOOT_PROD_IP:-192.168.1.168}"
STATE_DIR="$ROOT_DIR/data/builds/proxynet-lab"
PID_FILE="$STATE_DIR/dnsmasq.pid"

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

info() {
  printf 'INFO: %s\n' "$1"
}

[[ "$LAB_IP" == "10.101.8.135" ]] || fail "实验 IP 必须是 10.101.8.135"
[[ "$PROD_IP" == "192.168.1.168" ]] || fail "生产 IP 期望 192.168.1.168"

if [[ "${EUID}" -ne 0 ]]; then
  cat >&2 <<EOF
BLOCKED: 停止 ProxyNet lab 需要 root 权限。
请手动运行：

  sudo bash scripts/lab/stop-proxynet-lab.sh
EOF
  exit 2
fi

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE")"
  if [[ "$pid" =~ ^[0-9]+$ ]] && ps -p "$pid" -o comm= | grep -Fxq dnsmasq; then
    kill "$pid"
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

if ss -lntu | grep -Eq "10\\.101\\.8\\.135:(67|69|4011)|0\\.0\\.0\\.0:(67|69|4011)|${PROD_IP}:(67|69|4011)"; then
  ss -lntu | grep -E ':(67|69|4011)[[:space:]]' >&2 || true
  fail "ProxyNet lab UDP listener still present"
fi

info "APPROVED: ProxyNet lab stopped"
