#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

info() {
  printf 'INFO: %s\n' "$1"
}

compose_file="docker-compose.yml"
server_ip="${SERVER_IP:-192.168.1.168}"
http_port="${SYNABOOT_HTTP_PORT:-18080}"

info "SynaBoot network safety preflight"
info "SERVER_IP=${server_ip}"
info "HTTP_PORT=${http_port}/tcp"

if [[ -f "$compose_file" ]]; then
  grep -Eiq 'network_mode:[[:space:]]*host' "$compose_file" && fail "docker-compose.yml 禁止使用 host network"
  grep -Eiq 'privileged:[[:space:]]*true' "$compose_file" && fail "docker-compose.yml 禁止 privileged 容器"
  grep -Eiq '(^|[[:space:]-])/(etc|var/run/docker\.sock)(/|[[:space:]]*:)' "$compose_file" && fail "docker-compose.yml 禁止挂载宿主机敏感路径"
  grep -Eiq 'source:[[:space:]]*/($|[[:space:]])|-[[:space:]]*/[[:space:]]*:' "$compose_file" && fail "docker-compose.yml 禁止挂载宿主机根目录"
  grep -Eq '(^|[^0-9])(67|68|69|4011):' "$compose_file" && fail "docker-compose.yml 禁止暴露 DHCP/TFTP/ProxyDHCP 相关端口"
  grep -Eiq 'dnsmasq|tftp|proxydhcp|dhcp' "$compose_file" && fail "docker-compose.yml 禁止包含 DHCP/ProxyDHCP/TFTP 服务"
else
  info "docker-compose.yml 不存在，跳过 Compose 检查"
fi

if command -v ss >/dev/null 2>&1; then
  listeners="$(ss -lntu || true)"
  printf '%s\n' "$listeners" | grep -Eq ':(67|68|69|4011)[[:space:]]' && fail "当前主机已监听 DHCP/TFTP/ProxyDHCP 相关端口"
  if printf '%s\n' "$listeners" | grep -Eq ":${http_port}[[:space:]]"; then
    info "端口 ${http_port}/tcp 当前已有监听；部署前请确认是否为 SynaBoot 或其他预期服务"
  else
    info "端口 ${http_port}/tcp 当前未监听"
  fi
  if printf '%s\n' "$listeners" | grep -Eq ':(137|138|139|445)[[:space:]]'; then
    info "Samba 相关端口已有监听；Phase 2 默认不会启用 Samba"
  else
    info "Samba 相关端口当前未监听"
  fi
else
  info "未找到 ss，跳过监听端口检查"
fi

if command -v hostname >/dev/null 2>&1; then
  info "当前主机 IP: $(hostname -I 2>/dev/null | xargs || true)"
fi

if [[ -f /etc/resolv.conf ]]; then
  info "DNS 配置只读摘要:"
  grep -E '^[[:space:]]*nameserver[[:space:]]+' /etc/resolv.conf || true
fi

danger_patterns=(
  'iptables'
  'nft'
  'ufw'
  'firewall-cmd'
  'ip[[:space:]]+route'
  'route[[:space:]]+add'
  'nmcli[[:space:]]+connection[[:space:]]+modify'
  'dnsmasq'
  'tftp'
  'proxydhcp'
)

while IFS= read -r script; do
  [[ "$script" == "scripts/preflight/check-network-safety.sh" ]] && continue
  for pattern in "${danger_patterns[@]}"; do
    if grep -Eiq "$pattern" "$script"; then
      fail "脚本 ${script} 包含危险网络关键字: ${pattern}"
    fi
  done
done < <(find scripts -type f | sort)

info "APPROVED: 当前文件未发现 Phase 2 禁止网络行为"
