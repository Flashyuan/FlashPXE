#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

SCRIPT="scripts/boot-assets/import-loader.py"
ARCHIVE_SCRIPT="scripts/boot-assets/import-ipxe-archive.py"
API="apps/api/main.py"

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

info() {
  printf 'INFO: %s\n' "$1"
}

info "SynaBoot loader import safety preflight"

[[ -f "$SCRIPT" ]] || fail "缺少 loader 导入脚本: ${SCRIPT}"
[[ -f "$ARCHIVE_SCRIPT" ]] || fail "缺少 iPXE 归档导入脚本: ${ARCHIVE_SCRIPT}"

python3 - <<'PY' || fail "loader 导入脚本语法错误"
import ast
from pathlib import Path

ast.parse(Path("scripts/boot-assets/import-loader.py").read_text(encoding="utf-8"))
ast.parse(Path("scripts/boot-assets/import-ipxe-archive.py").read_text(encoding="utf-8"))
PY

for marker in \
  "ALLOWED_LOADERS" \
  "\"ipxe.efi\"" \
  "\"snponly.efi\"" \
  "\"undionly.kpxe\"" \
  "\"ipxe.iso\"" \
  "os.O_EXCL" \
  "validate_pe_file" \
  "validate_iso9660_file" \
  "source_sha256" \
  "loader_type" \
  "phase3_status" \
  "filename_allowlist_matched" \
  "ensure_no_symlink_chain" \
  "network_services_enabled" \
  "tftp_enabled" \
  "proxydhcp_enabled" \
  "dhcp_enabled"; do
  if ! grep -Fq "$marker" "$SCRIPT"; then
    fail "loader 导入脚本缺少安全标记: ${marker}"
  fi
done

if rg -n 'curl|wget|urlopen|requests|socket|subprocess|os\.system|Popen|docker|iptables|nft|ip route|dnsmasq|in\.tftpd|tftpd' "$SCRIPT"; then
  fail "loader 导入脚本包含禁止的联网、执行或网络服务关键字"
fi

if rg -n 'rm -rf|shutil\.rmtree|chmod\(.*0o7|chmod \+x' "$SCRIPT"; then
  fail "loader 导入脚本包含危险删除或可执行权限逻辑"
fi

for marker in \
  "ARCHIVE_MEMBER_CANDIDATES" \
  "ipxeboot/x86_64-sb/ipxe.efi" \
  "ipxeboot/x86_64-sb/snponly.efi" \
  "extract_member_to_temp" \
  "import_loader_file" \
  "archive_member" \
  "archive_imported"; do
  if ! grep -Fq "$marker" "$ARCHIVE_SCRIPT"; then
    fail "iPXE 归档导入脚本缺少安全标记: ${marker}"
  fi
done

if rg -n 'curl|wget|urlopen|requests|socket|subprocess|os\.system|Popen|docker|iptables|nft|ip route|dnsmasq|in\.tftpd|tftpd|extractall' "$ARCHIVE_SCRIPT"; then
  fail "iPXE 归档导入脚本包含禁止的联网、执行、网络服务或整包解压关键字"
fi

if rg -n 'rm -rf|shutil\.rmtree|chmod\(.*0o7|chmod \+x' "$ARCHIVE_SCRIPT"; then
  fail "iPXE 归档导入脚本包含危险删除或可执行权限逻辑"
fi

for marker in \
  "loader-metadata" \
  "reviewed_for_lab" \
  "provenance_sha256_matches" \
  "local_admin_approved_pending_isolated_boot_test" \
  "scripts/boot-assets/import-loader.py"; do
  if ! grep -Fq "$marker" "$API"; then
    fail "API 缺少 loader provenance 标记: ${marker}"
  fi
done

info "loader_import_script=${SCRIPT}"
info "ipxe_archive_import_script=${ARCHIVE_SCRIPT}"
info "loader_import_overwrite=blocked_by_O_EXCL"
info "loader_import_network_services=disabled"
info "APPROVED: loader 导入流程保持本地、白名单、不可覆盖且不启用网络服务"
