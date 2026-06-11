#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KIND="${1:-}"

case "${KIND}" in
  ubuntu-autoinstall|windows-adk-package) ;;
  *)
    printf '用法: %s ubuntu-autoinstall|windows-adk-package\n' "$0" >&2
    exit 2
    ;;
esac

JOB_ID="$(date -u +%Y%m%d%H%M%S)-${KIND}"
OUT_DIR="${ROOT_DIR}/data/builds/${JOB_ID}"
mkdir -p "${OUT_DIR}"

if [[ "${KIND}" == "ubuntu-autoinstall" ]]; then
  cat >"${OUT_DIR}/user-data" <<'TEMPLATE'
#cloud-config
autoinstall:
  version: 1
  identity:
    hostname: synaboot-client
    username: synaboot
    password: "$6$CHANGE_ME"
  ssh:
    install-server: true
  # Phase 1 默认不生成 storage 自动分区配置。
  # 如需自动分区，必须由管理员二次确认后手动添加。
TEMPLATE
  printf 'instance-id: synaboot\nlocal-hostname: synaboot-client\n' >"${OUT_DIR}/meta-data"
else
  cat >"${OUT_DIR}/README.md" <<'TEMPLATE'
# Windows ADK/DISM 外部构建任务

请在 Windows 构建机上使用 ADK/DISM 执行镜像定制。
SynaBoot Phase 1 只保存任务包和产物，不在 Ubuntu 上承诺完整封装 Windows ISO。
TEMPLATE
fi

printf 'Created %s\n' "${OUT_DIR}"
