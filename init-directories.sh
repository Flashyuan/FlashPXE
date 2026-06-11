#!/usr/bin/env bash
set -euo pipefail

mkdir -p .codex/agents apps/api apps/web apps/worker config/nginx config/samba config/synaboot \
  data/images/{pe/hotpe,pe/wepe,windows/win11,windows/winserver,linux/ubuntu-22.04.3,linux/ubuntu-24.04,tools,custom} \
  data/boot/{loaders,templates} data/builds data/metadata data/logs scripts/preflight scripts/image-factory docs

echo "SynaBoot project directories initialized."
