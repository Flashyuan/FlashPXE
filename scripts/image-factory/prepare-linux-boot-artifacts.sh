#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${SYNABOOT_ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
IMAGES_DIR="${ROOT_DIR}/data/images"
LINUX_DIR="${IMAGES_DIR}/linux"
WORK_ROOT="${ROOT_DIR}/data/builds/linux-boot-artifacts"

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

ensure_child_dir() {
  local root="$1"
  local child="$2"
  local label="$3"
  local resolved_root resolved_child
  resolved_root="$(canonical_dir_path "$ROOT_DIR" "$root")" || fail "${label} 根目录越界"
  if [[ -e "$child" ]]; then
    [[ ! -L "$child" ]] || fail "${label} 是 symlink，拒绝处理: ${child#$ROOT_DIR/}"
    resolved_child="$(canonical_dir_path "$resolved_root" "$child")" || fail "${label} 路径越界: ${child#$ROOT_DIR/}"
  else
    resolved_child="$(canonical_child_path "$resolved_root" "$child")" || fail "${label} 路径越界: ${child#$ROOT_DIR/}"
  fi
  case "$resolved_child" in
    "$resolved_root"/*|"${resolved_root}") ;;
    *) fail "${label} 不在允许目录内: ${child#$ROOT_DIR/}" ;;
  esac
  printf '%s\n' "$resolved_child"
}

safe_reset_work_dir() {
  local work="$1"
  local resolved_work
  [[ -n "$work" && "$work" != "/" ]] || fail "工作目录异常，拒绝清理"
  resolved_work="$(ensure_child_dir "$WORK_ROOT" "$work" "工作目录")"
  case "$resolved_work" in
    "$WORK_ROOT_CANONICAL"/*) ;;
    *) fail "工作目录不在 WORK_ROOT 内，拒绝清理: ${work#$ROOT_DIR/}" ;;
  esac
  [[ ! -e "$resolved_work" ]] || fail "工作目录已存在，拒绝自动清理: ${resolved_work#$ROOT_DIR/}"
  mkdir -p "$resolved_work"
  printf '%s\n' "$resolved_work"
}

extract_from_iso() {
  local source="$1"
  local target_dir="$2"
  local work="$3"

  work="$(safe_reset_work_dir "$work")"

  if command -v bsdtar >/dev/null 2>&1; then
    bsdtar -C "$work" -xf "$source" casper/vmlinuz casper/initrd
  elif command -v 7z >/dev/null 2>&1; then
    7z x -y -o"$work" "$source" casper/vmlinuz casper/initrd >/dev/null
  elif [[ -f "$ROOT_DIR/scripts/image-factory/extract-iso9660-file.py" ]]; then
    mkdir -p "$work/casper"
    python3 "$ROOT_DIR/scripts/image-factory/extract-iso9660-file.py" \
      --iso "$source" \
      --path casper/vmlinuz \
      --output "$work/casper/vmlinuz" \
      --allowed-root "$work"
    python3 "$ROOT_DIR/scripts/image-factory/extract-iso9660-file.py" \
      --iso "$source" \
      --path casper/initrd \
      --output "$work/casper/initrd" \
      --allowed-root "$work"
  else
    fail "未找到 bsdtar、7z 或项目内 ISO9660 提取器。请先补齐并审查解包工具。"
  fi

  local extracted_vmlinuz="${work}/casper/vmlinuz"
  local extracted_initrd="${work}/casper/initrd"
  for artifact in "$extracted_vmlinuz" "$extracted_initrd"; do
    [[ -e "$artifact" ]] || fail "ISO 内缺少预期文件: ${artifact#$work/}"
    [[ ! -L "$artifact" ]] || fail "ISO 解包结果是 symlink，拒绝复制: ${artifact#$work/}"
    [[ -f "$artifact" ]] || fail "ISO 解包结果不是普通文件，拒绝复制: ${artifact#$work/}"
  done

  local casper_dir="${target_dir}/casper"
  [[ ! -L "$casper_dir" ]] || fail "目标 casper 目录是 symlink，拒绝写入: ${casper_dir#$ROOT_DIR/}"
  mkdir -p "$casper_dir"

  local vmlinuz_target initrd_target
  vmlinuz_target="$(canonical_child_path "$IMAGES_DIR" "${casper_dir}/vmlinuz")" || fail "vmlinuz 目标路径越界"
  initrd_target="$(canonical_child_path "$IMAGES_DIR" "${casper_dir}/initrd")" || fail "initrd 目标路径越界"

  [[ ! -e "$vmlinuz_target" ]] || fail "目标文件已存在，拒绝覆盖: ${vmlinuz_target#$ROOT_DIR/}"
  [[ ! -e "$initrd_target" ]] || fail "目标文件已存在，拒绝覆盖: ${initrd_target#$ROOT_DIR/}"

  cp "$extracted_vmlinuz" "$vmlinuz_target"
  cp "$extracted_initrd" "$initrd_target"
  info "prepared=${target_dir#$ROOT_DIR/}/casper/vmlinuz ${target_dir#$ROOT_DIR/}/casper/initrd"
}

main() {
  ensure_no_symlink_chain "$ROOT_DIR/data" "data"
  ensure_no_symlink_chain "$IMAGES_DIR" "images"
  ensure_no_symlink_chain "$LINUX_DIR" "linux images"
  ensure_no_symlink_chain "$ROOT_DIR/data/builds" "builds"
  [[ -d "$LINUX_DIR" ]] || fail "Linux 镜像目录不存在: data/images/linux"
  [[ ! -L "$LINUX_DIR" ]] || fail "Linux 镜像目录是 symlink，拒绝处理"
  mkdir -p "$WORK_ROOT"
  ensure_no_symlink_chain "$WORK_ROOT" "work root"
  WORK_ROOT_CANONICAL="$(canonical_dir_path "$ROOT_DIR/data/builds" "$WORK_ROOT")" || fail "WORK_ROOT 路径越界"

  local found=0
  while IFS= read -r -d '' iso; do
    found=1
    [[ -f "$iso" ]] || continue
    [[ ! -L "$iso" ]] || fail "ISO 不能是 symlink: ${iso#$ROOT_DIR/}"

    local target_dir casper_dir
    target_dir="$(dirname "$iso")"
    target_dir="$(canonical_dir_path "$IMAGES_DIR" "$target_dir")" || fail "目标目录越界: ${target_dir#$ROOT_DIR/}"
    casper_dir="${target_dir}/casper"

    if [[ -f "${casper_dir}/vmlinuz" && -f "${casper_dir}/initrd" ]]; then
      info "already_prepared=${target_dir#$ROOT_DIR/}"
      continue
    fi

    local rel work_id work
    rel="${iso#$LINUX_DIR/}"
    work_id="$(printf '%s' "$rel" | sha256sum | awk '{print $1}')"
    work="${WORK_ROOT}/${work_id}"
    info "extracting=${iso#$ROOT_DIR/}"
    extract_from_iso "$iso" "$target_dir" "$work"
  done < <(find "$LINUX_DIR" -type f -name '*.iso' -print0 | sort -z)

  [[ "$found" -eq 1 ]] || fail "未找到 Linux ISO: data/images/linux/**/*.iso"
  info "DONE: Linux 启动依赖准备完成。请重新扫描镜像并生成菜单。"
}

main "$@"
