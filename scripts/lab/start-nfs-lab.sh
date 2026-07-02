#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

LAB_IFACE="${SYNABOOT_LAB_IFACE:-ens19}"
LAB_IP="${SYNABOOT_LAB_IP:-10.101.8.135}"
NFS_IP="${SYNABOOT_NFS_LAB_IP:-10.101.8.136}"
PROD_IFACE="${SYNABOOT_PROD_IFACE:-ens18}"
PROD_IP="${SYNABOOT_PROD_IP:-192.168.1.168}"
CONFIRM="${SYNABOOT_NFS_LAB_CONFIRM:-}"

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

info() {
  printf 'INFO: %s\n' "$1"
}

[[ "$CONFIRM" == "I_UNDERSTAND_NFS_LAB_ONLY_10.101.8.135_ens19_READONLY" ]] \
  || fail "必须设置 SYNABOOT_NFS_LAB_CONFIRM=I_UNDERSTAND_NFS_LAB_ONLY_10.101.8.135_ens19_READONLY"
[[ "$LAB_IFACE" == "ens19" ]] || fail "实验接口必须是 ens19，当前: ${LAB_IFACE}"
[[ "$LAB_IP" == "10.101.8.135" ]] || fail "实验 IP 必须是 10.101.8.135，当前: ${LAB_IP}"
[[ "$NFS_IP" == "10.101.8.136" ]] || fail "NFS 实验 IP 必须是 10.101.8.136，当前: ${NFS_IP}"
[[ "$PROD_IFACE" == "ens18" ]] || fail "生产接口期望 ens18，当前: ${PROD_IFACE}"
[[ "$PROD_IP" == "192.168.1.168" ]] || fail "生产 IP 期望 192.168.1.168，当前: ${PROD_IP}"

ip -4 addr show dev "$LAB_IFACE" | grep -Fq "${LAB_IP}/24" \
  || fail "${LAB_IFACE} 未持有 ${LAB_IP}/24"
ip -4 addr show dev "$PROD_IFACE" | grep -Fq "${PROD_IP}/24" \
  || fail "${PROD_IFACE} 未持有 ${PROD_IP}/24"
ip route show default | grep -Fq "dev ${PROD_IFACE}" \
  || fail "默认路由必须仍在生产接口 ${PROD_IFACE}"

[[ -f data/images/linux/ubuntu-22.04.3/casper/filesystem.squashfs ]] \
  || fail "缺少 Ubuntu 22.04.3 livefs"
find data/images/linux/ubuntu-24.04/casper -maxdepth 1 -type f -name '*.squashfs' -print -quit | grep -q . \
  || fail "缺少 Ubuntu 24.04 livefs"

if ping -c 1 -W 1 "$NFS_IP" >/dev/null 2>&1; then
  fail "NFS 实验 IP ${NFS_IP} 已有响应，拒绝占用"
fi

if ss -lntu | grep -Eq "(${PROD_IP}:(111|2049|20048)|${LAB_IP}:(111|2049|20048)|0\.0\.0\.0:(111|2049|20048)|:::(111|2049|20048))"; then
  ss -lntu | grep -E ':(111|2049|20048)\b' || true
  fail "启动前已有不符合实验边界的 NFS/RPC 监听"
fi

docker compose -p synaboot-nfs-lab -f docker-compose.nfs-lab.yml up -d --build synaboot-nfs-lab

container_ip=""
for _ in 1 2 3 4 5; do
  container_ip="$(docker inspect synaboot-nfs-lab --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null || true)"
  if [[ "$container_ip" == "$NFS_IP" ]]; then
    break
  fi
  sleep 1
done
[[ "$container_ip" == "$NFS_IP" ]] || fail "NFS 容器未获得 ${NFS_IP}，当前: ${container_ip:-missing}"

docker exec synaboot-nfs-lab rpcinfo -p "$NFS_IP" | grep -Eq '100003.*nfs' \
  || fail "NFS 容器内 rpcinfo 未看到 nfs 程序注册"

LISTEN="$(ss -lntu | grep -E ':(111|2049|20048)\b' || true)"
printf '%s\n' "$LISTEN"
if printf '%s\n' "$LISTEN" | grep -Eq "(${PROD_IP}:(111|2049|20048)|${LAB_IP}:(111|2049|20048)|0\.0\.0\.0:(111|2049|20048)|:::(111|2049|20048))"; then
  fail "NFS/RPC 不应在宿主网络命名空间监听"
fi

docker inspect synaboot-nfs-lab \
  --format 'Privileged={{.HostConfig.Privileged}} NetworkMode={{.HostConfig.NetworkMode}} Binds={{json .HostConfig.Binds}} PortBindings={{json .HostConfig.PortBindings}}'

info "nfs_export=${NFS_IP}:/ubuntu-22.04.3"
info "nfs_export=${NFS_IP}:/ubuntu-24.04"
info "nfs_auth=sys_readonly_all_squash"
