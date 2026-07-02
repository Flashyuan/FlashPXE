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

info "SynaBoot Docker Compose config preflight"

command -v docker >/dev/null 2>&1 || fail "缺少 docker 命令"
docker compose version >/dev/null 2>&1 || fail "Docker Compose 不可用"

# docker compose config 会展开 .env。这里用固定占位覆盖管理员 token，并丢弃
# 渲染后的配置，避免验证日志、终端滚动或聊天记录泄露真实 token。
SYNABOOT_ADMIN_TOKEN="__synaboot_redacted_for_config_check__" \
  docker compose config >/dev/null

info "compose_config=valid"
info "admin_token_output=redacted"
info "APPROVED: Docker Compose 配置可解析且未输出管理员 token"
