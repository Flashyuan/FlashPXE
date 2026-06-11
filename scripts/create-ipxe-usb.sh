#!/usr/bin/env bash
set -euo pipefail

SERVER_IP="${SERVER_IP:-192.168.1.168}"
SYNABOOT_HTTP_PORT="${SYNABOOT_HTTP_PORT:-18080}"

cat <<EOF
SynaBoot Phase 2 iPXE 启动介质说明

本脚本不会自动格式化、分区或写入 U 盘。

请使用你已验证来源的 iPXE USB/ISO/EFI 启动介质，并在 iPXE shell 中执行：

  chain http://${SERVER_IP}:${SYNABOOT_HTTP_PORT}/boot/menu.ipxe

如果你已准备好自定义 iPXE 构建环境，可将启动脚本嵌入 iPXE：

  #!ipxe
  chain http://${SERVER_IP}:${SYNABOOT_HTTP_PORT}/boot/menu.ipxe

可选 loader 放置路径：

  data/boot/loaders/ipxe.efi
  data/boot/loaders/ipxe.iso

放入真实 loader 后，它们会通过以下 URL 提供：

  http://${SERVER_IP}:${SYNABOOT_HTTP_PORT}/boot/loaders/ipxe.efi
  http://${SERVER_IP}:${SYNABOOT_HTTP_PORT}/boot/loaders/ipxe.iso
EOF
