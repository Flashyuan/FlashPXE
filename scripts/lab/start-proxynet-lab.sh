#!/usr/bin/env bash
set -euo pipefail

# SYNABOOT_LAB_ONLY_BIND=10.101.8.135
# SYNABOOT_LAB_ONLY_INTERFACE=ens19
# SYNABOOT_REQUIRES_MANUAL_SUDO_CONFIRMATION=1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

LAB_IFACE="${SYNABOOT_LAB_IFACE:-ens19}"
LAB_IP="${SYNABOOT_LAB_IP:-10.101.8.135}"
PROD_IFACE="${SYNABOOT_PROD_IFACE:-ens18}"
PROD_IP="${SYNABOOT_PROD_IP:-192.168.1.168}"
CONFIRM_VALUE="I_UNDERSTAND_PROXYNET_LAB_ONLY_${LAB_IP}_${LAB_IFACE}"
STATE_DIR="$ROOT_DIR/data/builds/proxynet-lab"
CONF_FILE="$STATE_DIR/dnsmasq-proxynet-lab.conf"
PID_FILE="$STATE_DIR/dnsmasq.pid"

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

info() {
  printf 'INFO: %s\n' "$1"
}

[[ "$LAB_IFACE" == "ens19" ]] || fail "实验接口必须是 ens19"
[[ "$LAB_IP" == "10.101.8.135" ]] || fail "实验 IP 必须是 10.101.8.135"
[[ "$PROD_IFACE" == "ens18" ]] || fail "生产接口期望 ens18"
[[ "$PROD_IP" == "192.168.1.168" ]] || fail "生产 IP 期望 192.168.1.168"
[[ "${SYNABOOT_PROXYNET_LAB_CONFIRM:-}" == "$CONFIRM_VALUE" ]] \
  || fail "缺少确认环境变量：SYNABOOT_PROXYNET_LAB_CONFIRM=${CONFIRM_VALUE}"

if [[ "${EUID}" -ne 0 ]]; then
  cat >&2 <<EOF
BLOCKED: 启动 ProxyNet lab 需要 root 权限绑定 UDP 67/69。
请确认只在 PVE 隔离网段 ${LAB_IP}/${LAB_IFACE} 中执行后，手动运行：

  sudo SYNABOOT_PROXYNET_LAB_CONFIRM=${CONFIRM_VALUE} \\
    SYNABOOT_LAB_IFACE=${LAB_IFACE} SYNABOOT_LAB_IP=${LAB_IP} \\
    bash scripts/lab/start-proxynet-lab.sh
EOF
  exit 2
fi

bash scripts/lab/render-proxynet-lab-assets.sh
[[ -f "$CONF_FILE" ]] || fail "缺少 dnsmasq 配置: ${CONF_FILE}"

if ss -lntu | grep -Eq '(^|[[:space:]])(udp|udp6)[[:space:]].*:(67|69|4011)[[:space:]]'; then
  ss -lntu | grep -E ':(67|69|4011)[[:space:]]' >&2 || true
  fail "启动前已存在 UDP 67/69/4011 监听"
fi

if ss -lntu | grep -Eq "0\\.0\\.0\\.0:(67|69|4011)|${PROD_IP}:(67|69|4011)"; then
  fail "检测到通配或生产 IP 上的 PXE 相关监听"
fi

dnsmasq --test --conf-file="$CONF_FILE" >/dev/null
dnsmasq --conf-file="$CONF_FILE"

sleep 1
[[ -f "$PID_FILE" ]] || fail "dnsmasq 未写入 pidfile"
if ! ps -p "$(cat "$PID_FILE")" -o comm= | grep -Fxq dnsmasq; then
  fail "pidfile 指向的进程不是 dnsmasq"
fi

if ss -lntu | grep -Eq "0\\.0\\.0\\.0:(67|69|4011)|${PROD_IP}:(67|69|4011)"; then
  bash scripts/lab/stop-proxynet-lab.sh || true
  fail "启动后检测到通配或生产 IP 上的 PXE 相关监听，已尝试停止"
fi

info "APPROVED: ProxyNet lab started on ${LAB_IFACE}/${LAB_IP}"
info "pid=$(cat "$PID_FILE")"
info "stop_command=sudo bash scripts/lab/stop-proxynet-lab.sh"
ss -lntu | grep -E ':(67|69|4011)[[:space:]]' || true
