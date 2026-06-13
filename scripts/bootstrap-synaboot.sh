#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

START_SERVICES=0
FORCE_ENV=0
SERVER_IP_VALUE="${SERVER_IP:-}"
HTTP_BIND_VALUE="${SYNABOOT_HTTP_BIND:-18080}"
HTTP_PORT_VALUE="${SYNABOOT_HTTP_PORT:-18080}"

usage() {
  cat <<'EOF'
用法:
  bash scripts/bootstrap-synaboot.sh [选项]

选项:
  --server-ip <IP>       写入 .env 的 SERVER_IP，默认尝试从本机地址推断。
  --http-bind <BIND>     Docker 发布绑定，默认 18080；本机验证可用 127.0.0.1:18180。
  --http-port <PORT>     应用展示端口，默认 18080。
  --force-env            覆盖已有 .env。
  --start                预检通过后执行 docker compose up -d --build。
  -h, --help             显示帮助。

安全边界:
  - 不安装 Docker 或系统包。
  - 不修改现有网络设备、地址分配、解析、转发或安全策略。
  - 不启用任何自动网络启动服务或文件共享服务。
  - 不使用 host network 或 privileged。
EOF
}

info() {
  printf 'INFO: %s\n' "$1"
}

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server-ip)
      [[ $# -ge 2 ]] || fail "--server-ip 需要参数"
      SERVER_IP_VALUE="$2"
      shift 2
      ;;
    --http-bind)
      [[ $# -ge 2 ]] || fail "--http-bind 需要参数"
      HTTP_BIND_VALUE="$2"
      shift 2
      ;;
    --http-port)
      [[ $# -ge 2 ]] || fail "--http-port 需要参数"
      HTTP_PORT_VALUE="$2"
      shift 2
      ;;
    --force-env)
      FORCE_ENV=1
      shift
      ;;
    --start)
      START_SERVICES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "未知参数: $1"
      ;;
  esac
done

validate_ip_or_empty() {
  local value="$1"
  [[ -z "$value" ]] && return 0
  [[ "$value" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "SERVER_IP 格式不正确: $value"
}

validate_port() {
  local value="$1"
  [[ "$value" =~ ^[0-9]+$ ]] || fail "端口必须是整数: $value"
  (( value >= 1 && value <= 65535 )) || fail "端口超出范围: $value"
}

validate_bind() {
  local value="$1"
  if [[ "$value" == *:* ]]; then
    local port="${value##*:}"
    validate_port "$port"
  else
    validate_port "$value"
  fi
}

guess_server_ip() {
  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^192\.168\.1\.' | head -n 1 || true
  fi
}

generate_token() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  else
    python3 - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
  fi
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少命令: $1"
}

validate_ip_or_empty "$SERVER_IP_VALUE"
validate_bind "$HTTP_BIND_VALUE"
validate_port "$HTTP_PORT_VALUE"

if [[ -z "$SERVER_IP_VALUE" ]]; then
  SERVER_IP_VALUE="$(guess_server_ip)"
fi
if [[ -z "$SERVER_IP_VALUE" ]]; then
  SERVER_IP_VALUE="192.168.1.168"
  info "未能自动推断 SERVER_IP，使用默认示例值 ${SERVER_IP_VALUE}；请按实际服务器 IP 修改 .env"
fi

info "SynaBoot bootstrap"
info "SERVER_IP=${SERVER_IP_VALUE}"
info "SYNABOOT_HTTP_BIND=${HTTP_BIND_VALUE}"
info "SYNABOOT_HTTP_PORT=${HTTP_PORT_VALUE}"

require_command docker
docker compose version >/dev/null 2>&1 || fail "Docker Compose 不可用，请先安装 Docker Compose 插件"

if [[ -f .env && "$FORCE_ENV" -ne 1 ]]; then
  info ".env 已存在，保留现有配置；如需覆盖请使用 --force-env"
else
  admin_token="$(generate_token)"
  umask 077
  cat > .env <<EOF
SERVER_IP=${SERVER_IP_VALUE}
SYNABOOT_HTTP_BIND=${HTTP_BIND_VALUE}
SYNABOOT_HTTP_PORT=${HTTP_PORT_VALUE}
SYNABOOT_DATA_DIR=./data
SYNABOOT_ADMIN_TOKEN=${admin_token}
EOF
  info "已生成 .env；管理员 token 仅保存在本机 .env，且 .env 已被 Git 忽略"
fi

bash init-directories.sh
bash scripts/preflight/check-release-scope.sh
bash scripts/preflight/check-private-commercial-scope.sh
bash scripts/preflight/check-edition-boundary.sh
bash scripts/preflight/check-public-runtime-boundary.sh
bash scripts/preflight/check-autoinstall-boundary.sh
bash scripts/preflight/check-subagent-governance.sh
bash scripts/preflight/check-network-safety.sh
bash scripts/preflight/check-compose-config-safe.sh

if [[ "$START_SERVICES" -eq 1 ]]; then
  info "按 --start 请求启动服务"
  docker compose up -d --build
  info "Web UI: http://${SERVER_IP_VALUE}:${HTTP_PORT_VALUE}/"
  info "iPXE 菜单: http://${SERVER_IP_VALUE}:${HTTP_PORT_VALUE}/boot/menu.ipxe"
  info "镜像仓库: http://${SERVER_IP_VALUE}:${HTTP_PORT_VALUE}/images/"
else
  info "未传 --start，bootstrap 到预检为止。确认后可运行: docker compose up -d --build"
fi
