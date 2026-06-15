#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${SYNABOOT_ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
HOTPE_DIR="${ROOT_DIR}/data/images/pe/hotpe"
ISO9660_EXTRACTOR="${ROOT_DIR}/scripts/image-factory/extract-iso9660-file.py"
UDF_EXTRACTOR="${ROOT_DIR}/scripts/image-factory/extract-udf-file.py"

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

info() {
  printf 'INFO: %s\n' "$1"
}

canonical_dir_path() {
  python3 - "$1" "$2" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
directory = Path(sys.argv[2]).resolve()
if root != directory and root not in directory.parents:
    raise SystemExit(1)
print(directory)
PY
}

canonical_child_path() {
  python3 - "$1" "$2" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
child = Path(sys.argv[2])
resolved_parent = child.parent.resolve()
candidate = resolved_parent / child.name
if root != resolved_parent and root not in resolved_parent.parents:
    raise SystemExit(1)
print(candidate)
PY
}

ensure_no_symlink_chain() {
  local path="$1"
  local label="$2"
  local current=""
  IFS='/' read -r -a parts <<<"${path#/}"
  for part in "${parts[@]}"; do
    [[ -n "$part" ]] || continue
    current="${current}/${part}"
    [[ ! -L "$current" ]] || fail "${label} 路径包含 symlink，拒绝处理: ${current#$ROOT_DIR/}"
  done
}

ensure_regular_existing_target() {
  local artifact="$1"
  local label="$2"
  [[ ! -L "$artifact" ]] || fail "${label} 是 symlink，拒绝处理: ${artifact#$ROOT_DIR/}"
  [[ -f "$artifact" ]] || fail "${label} 已存在但不是普通文件: ${artifact#$ROOT_DIR/}"
}

resolve_source_iso() {
  local requested="${1:-}"
  if [[ -n "$requested" ]]; then
    local candidate="$requested"
    if [[ "$candidate" != /* ]]; then
      case "$candidate" in
        data/images/pe/hotpe/*) candidate="${ROOT_DIR}/${candidate}" ;;
        pe/hotpe/*) candidate="${ROOT_DIR}/data/images/${candidate}" ;;
        *) fail "HotPE ISO 相对路径必须位于 data/images/pe/hotpe/ 或 pe/hotpe/" ;;
      esac
    fi
    candidate="$(canonical_child_path "$HOTPE_DIR_CANONICAL" "$candidate")" || fail "HotPE ISO 路径越界"
    [[ "$candidate" == "$HOTPE_DIR_CANONICAL"/*.iso ]] || fail "HotPE ISO 必须位于 data/images/pe/hotpe/*.iso"
    [[ -f "$candidate" ]] || fail "HotPE ISO 不存在: ${candidate#$ROOT_DIR/}"
    [[ ! -L "$candidate" ]] || fail "HotPE ISO 不能是 symlink: ${candidate#$ROOT_DIR/}"
    printf '%s\n' "$candidate"
    return
  fi

  local found=()
  while IFS= read -r -d '' iso; do
    found+=("$iso")
  done < <(find "$HOTPE_DIR_CANONICAL" -maxdepth 1 -type f -name '*.iso' -print0 | sort -z)

  case "${#found[@]}" in
    0) fail "未找到 HotPE ISO: data/images/pe/hotpe/*.iso" ;;
    1) printf '%s\n' "${found[0]}" ;;
    *) fail "发现多个 HotPE ISO，请显式传入其中一个路径" ;;
  esac
}

extract_with_tool() {
  local tool="$1"
  local source="$2"
  local wanted="$3"
  local target="$4"
  local label="$5"

  [[ -f "$tool" ]] || return 1
  if python3 "$tool" \
    --iso "$source" \
    --path "$wanted" \
    --output "$target" \
    --allowed-root "$HOTPE_DIR_CANONICAL"; then
    info "prepared=${target#$ROOT_DIR/} source_path=${wanted} extractor=$(basename "$tool")"
    return 0
  fi
  [[ ! -e "$target" ]] || fail "${label} 提取失败后留下目标文件，拒绝继续: ${target#$ROOT_DIR/}"
  return 1
}

extract_first_match() {
  local source="$1"
  local target="$2"
  local label="$3"
  shift 3

  if [[ -e "$target" ]]; then
    ensure_regular_existing_target "$target" "$label"
    info "already_present=${target#$ROOT_DIR/}"
    return
  fi

  local canonical_target
  canonical_target="$(canonical_child_path "$HOTPE_DIR_CANONICAL" "$target")" || fail "${label} 目标路径越界"
  [[ "$canonical_target" == "$HOTPE_DIR_CANONICAL"/* ]] || fail "${label} 目标不在 HotPE 目录内"
  [[ ! -e "$canonical_target" ]] || fail "${label} 目标文件已存在，拒绝覆盖: ${canonical_target#$ROOT_DIR/}"

  local wanted
  for wanted in "$@"; do
    if extract_with_tool "$UDF_EXTRACTOR" "$source" "$wanted" "$canonical_target" "$label"; then
      return
    fi
    if extract_with_tool "$ISO9660_EXTRACTOR" "$source" "$wanted" "$canonical_target" "$label"; then
      return
    fi
  done

  fail "ISO 内缺少 ${label} 的已知候选路径，请人工确认 HotPE ISO 布局"
}

report_wimboot_guidance() {
  cat >&2 <<'EOF'
BLOCKED: 缺少 data/images/pe/hotpe/wimboot
INFO: wimboot 通常不在 HotPE ISO 内，应由管理员从已审查的 iPXE/wimboot
INFO: 发布包或本地可信构建产物中导入。
INFO: 安全导入建议：
INFO: 1. 将 wimboot 放入临时审查目录，记录来源、版本和 sha256。
INFO: 2. 确认文件为普通文件且不是 symlink。
INFO: 3. 复制到 data/images/pe/hotpe/wimboot；不要覆盖已有文件。
INFO: 4. 重新运行本脚本和扫描流程，确认 HotPE 五件套齐全。
EOF
  exit 1
}

main() {
  ensure_no_symlink_chain "$ROOT_DIR/data" "data"
  ensure_no_symlink_chain "$ROOT_DIR/data/images" "images"
  ensure_no_symlink_chain "$HOTPE_DIR" "hotpe"
  [[ -d "$HOTPE_DIR" ]] || fail "HotPE 目录不存在: data/images/pe/hotpe"
  [[ ! -L "$HOTPE_DIR" ]] || fail "HotPE 目录是 symlink，拒绝处理"
  [[ -f "$ISO9660_EXTRACTOR" ]] || fail "缺少项目内 ISO9660 提取器: scripts/image-factory/extract-iso9660-file.py"
  [[ -f "$UDF_EXTRACTOR" ]] || fail "缺少项目内 UDF 提取器: scripts/image-factory/extract-udf-file.py"

  HOTPE_DIR_CANONICAL="$(canonical_dir_path "$ROOT_DIR/data/images" "$HOTPE_DIR")" || fail "HotPE 目录越界"
  local source_iso
  source_iso="$(resolve_source_iso "${1:-}")"
  info "source_iso=${source_iso#$ROOT_DIR/}"

  extract_first_match "$source_iso" "$HOTPE_DIR_CANONICAL/bootmgr" "bootmgr" \
    "bootmgr"
  extract_first_match "$source_iso" "$HOTPE_DIR_CANONICAL/BCD" "BCD" \
    "Boot/bcd" "boot/BCD" "EFI/MICROSOFT/BOOT/BCD" "efi/microsoft/boot/BCD" "BCD"
  extract_first_match "$source_iso" "$HOTPE_DIR_CANONICAL/boot.sdi" "boot.sdi" \
    "Boot/boot.sdi" "boot/boot.sdi" "EFI/MICROSOFT/BOOT/boot.sdi" "boot.sdi"
  extract_first_match "$source_iso" "$HOTPE_DIR_CANONICAL/boot.wim" "boot.wim" \
    "HotPE/Boot.wim" "sources/boot.wim" "boot/boot.wim" "boot.wim"

  if [[ ! -e "$HOTPE_DIR_CANONICAL/wimboot" ]]; then
    report_wimboot_guidance
  fi
  ensure_regular_existing_target "$HOTPE_DIR_CANONICAL/wimboot" "wimboot"
  chmod 0644 \
    "$HOTPE_DIR_CANONICAL/wimboot" \
    "$HOTPE_DIR_CANONICAL/bootmgr" \
    "$HOTPE_DIR_CANONICAL/BCD" \
    "$HOTPE_DIR_CANONICAL/boot.sdi" \
    "$HOTPE_DIR_CANONICAL/boot.wim"

  info "DONE: HotPE bootmgr/BCD/boot.sdi/boot.wim/wimboot 已齐全。请重新扫描镜像并生成菜单。"
}

main "$@"
