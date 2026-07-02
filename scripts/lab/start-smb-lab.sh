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
CONFIRM="${SYNABOOT_SMB_LAB_CONFIRM:-}"

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

info() {
  printf 'INFO: %s\n' "$1"
}

[[ "$CONFIRM" == "I_UNDERSTAND_SMB_LAB_ONLY_10.101.8.135_ens19_READONLY" ]] \
  || fail "必须设置 SYNABOOT_SMB_LAB_CONFIRM=I_UNDERSTAND_SMB_LAB_ONLY_10.101.8.135_ens19_READONLY"
[[ "$LAB_IFACE" == "ens19" ]] || fail "实验接口必须是 ens19，当前: ${LAB_IFACE}"
[[ "$LAB_IP" == "10.101.8.135" ]] || fail "实验 IP 必须是 10.101.8.135，当前: ${LAB_IP}"
[[ "$PROD_IFACE" == "ens18" ]] || fail "生产接口期望 ens18，当前: ${PROD_IFACE}"
[[ "$PROD_IP" == "192.168.1.168" ]] || fail "生产 IP 期望 192.168.1.168，当前: ${PROD_IP}"

ip -4 addr show dev "$LAB_IFACE" | grep -Fq "${LAB_IP}/24" \
  || fail "${LAB_IFACE} 未持有 ${LAB_IP}/24"
ip -4 addr show dev "$PROD_IFACE" | grep -Fq "${PROD_IP}/24" \
  || fail "${PROD_IFACE} 未持有 ${PROD_IP}/24"
ip route show default | grep -Fq "dev ${PROD_IFACE}" \
  || fail "默认路由必须仍在生产接口 ${PROD_IFACE}"

if ss -lntu | grep -Eq "(${PROD_IP}:445|0\.0\.0\.0:445|:::445|:139\\b)"; then
  ss -lntu | grep -E "(:445\\b|:139\\b)" || true
  fail "启动前已有不符合实验边界的 SMB 监听"
fi

docker compose -p synaboot-smb-lab -f docker-compose.smb-lab.yml up -d --build synaboot-smb-lab

LISTEN=""
for _ in 1 2 3 4 5; do
  LISTEN="$(ss -lntu | grep -E '(:445\b|:139\b)' || true)"
  if printf '%s\n' "$LISTEN" | grep -Fq "${LAB_IP}:445"; then
    break
  fi
  sleep 1
done
printf '%s\n' "$LISTEN"
printf '%s\n' "$LISTEN" | grep -Fq "${LAB_IP}:445" \
  || fail "未看到 ${LAB_IP}:445 监听"
if printf '%s\n' "$LISTEN" | grep -Eq "(${PROD_IP}:445|0\.0\.0\.0:445|:::445|:139\\b)"; then
  fail "SMB 监听暴露到非实验边界"
fi

docker inspect synaboot-smb-lab \
  --format 'Privileged={{.HostConfig.Privileged}} NetworkMode={{.HostConfig.NetworkMode}} Binds={{json .HostConfig.Binds}} PortBindings={{json .HostConfig.PortBindings}}'

info "smb_share=\\\\${LAB_IP}\\synaboot-images"
info "hotpe_mods_share=\\\\${LAB_IP}\\hotpe-mods"
info "win11_share=\\\\${LAB_IP}\\win11"
info "smb_auth=synaboot_readonly"
info "hotpe_mods=\\\\${LAB_IP}\\hotpe-mods"
info "windows_iso=\\\\${LAB_IP}\\synaboot-images\\windows\\win11\\Win11_24H2_Pro_Chinese_Simplified_x64.iso"
info "windows_iso_short=\\\\${LAB_IP}\\win11\\Win11_24H2_Pro_Chinese_Simplified_x64.iso"
