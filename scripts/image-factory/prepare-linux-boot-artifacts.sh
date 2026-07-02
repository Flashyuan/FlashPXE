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

install_missing_artifact() {
  local source="$1"
  local target="$2"
  local label="$3"

  if [[ -e "$target" ]]; then
    [[ ! -L "$target" ]] || fail "${label} 目标是 symlink，拒绝使用: ${target#$ROOT_DIR/}"
    [[ -f "$target" ]] || fail "${label} 目标不是普通文件，拒绝使用: ${target#$ROOT_DIR/}"
    info "kept_existing=${target#$ROOT_DIR/}"
    return
  fi

  cp "$source" "$target"
}

ensure_regular_artifact() {
  local path="$1"
  local label="$2"
  [[ -e "$path" ]] || fail "${label} 不存在: ${path#$ROOT_DIR/}"
  [[ ! -L "$path" ]] || fail "${label} 是 symlink，拒绝使用: ${path#$ROOT_DIR/}"
  [[ -f "$path" ]] || fail "${label} 不是普通文件，拒绝使用: ${path#$ROOT_DIR/}"
}

ensure_ready_linux_artifacts() {
  local casper_dir="$1"
  ensure_regular_artifact "${casper_dir}/vmlinuz" "vmlinuz"
  ensure_regular_artifact "${casper_dir}/initrd" "initrd"

  local found_livefs=0
  local livefs
  shopt -s nullglob
  for livefs in "${casper_dir}"/*.squashfs; do
    ensure_regular_artifact "$livefs" "livefs"
    found_livefs=1
  done
  shopt -u nullglob
  [[ "$found_livefs" -eq 1 ]] || fail "缺少 livefs: ${casper_dir#$ROOT_DIR/}/*.squashfs"
}

create_casper_compat_aliases() {
  local casper_dir="$1"
  local source basename stem alias
  if [[ -f "${casper_dir}/install_sources.yaml" && ! -e "${casper_dir}/install-sources.yaml" ]]; then
    ln "${casper_dir}/install_sources.yaml" "${casper_dir}/install-sources.yaml"
    chmod 0644 "${casper_dir}/install-sources.yaml"
    info "casper_alias=${casper_dir#$ROOT_DIR/}/install-sources.yaml -> ${casper_dir#$ROOT_DIR/}/install_sources.yaml"
  fi
  shopt -s nullglob
  for source in "${casper_dir}"/*.squashfs; do
    ensure_regular_artifact "$source" "livefs alias source"
    basename="$(basename "$source")"
    [[ "$basename" == *_* ]] || continue
    stem="${basename%.squashfs}"
    alias="${casper_dir}/${stem//_/.}.squashfs"
    [[ "$alias" != "$source" ]] || continue
    if [[ -e "$alias" ]]; then
      ensure_regular_artifact "$alias" "livefs alias"
      continue
    fi
    ln "$source" "$alias"
    chmod 0644 "$alias"
    info "casper_alias=${alias#$ROOT_DIR/} -> ${source#$ROOT_DIR/}"
  done
  shopt -u nullglob
}

extract_from_iso() {
  local source="$1"
  local target_dir="$2"
  local work="$3"

  work="$(safe_reset_work_dir "$work")"
  local required_iso_paths=(
    "casper/vmlinuz"
    "casper/initrd"
  )
  local optional_iso_paths=(
    "casper/filesystem.size"
    "casper/filesystem.manifest"
    "casper/install_sources.yaml"
    ".disk/casper-uuid"
    ".disk/casper-uuid-generic"
    ".disk/casper_uuid_generic"
    ".disk/info"
  )
  local livefs_paths=()
  local companion_paths=()
  if [[ -f "$ROOT_DIR/scripts/image-factory/extract-iso9660-file.py" ]]; then
    while IFS=$'\t' read -r name kind _size; do
      if [[ "$kind" == "file" && "$name" == *.squashfs ]]; then
        livefs_paths+=("casper/$name")
      elif [[ "$kind" == "file" && ( "$name" == *.manifest || "$name" == *.size || "$name" == *.gpg || "$name" == "install-sources.yaml" ) ]]; then
        companion_paths+=("casper/$name")
      fi
    done < <(python3 "$ROOT_DIR/scripts/image-factory/extract-iso9660-file.py" --iso "$source" --list-dir casper)
  fi
  [[ "${#livefs_paths[@]}" -gt 0 ]] || fail "ISO 内缺少 casper/*.squashfs livefs 文件"
  required_iso_paths+=("${livefs_paths[@]}")

  if [[ -f "$ROOT_DIR/scripts/image-factory/extract-iso9660-file.py" ]]; then
    mkdir -p "$work/casper"
    local iso_path
    for iso_path in "${required_iso_paths[@]}"; do
      mkdir -p "$work/$(dirname "$iso_path")"
      python3 "$ROOT_DIR/scripts/image-factory/extract-iso9660-file.py" \
        --iso "$source" \
        --path "$iso_path" \
        --output "$work/$iso_path" \
        --allowed-root "$work"
    done
    for iso_path in "${optional_iso_paths[@]}" "${companion_paths[@]}"; do
      mkdir -p "$work/$(dirname "$iso_path")"
      python3 "$ROOT_DIR/scripts/image-factory/extract-iso9660-file.py" \
        --iso "$source" \
        --path "$iso_path" \
        --output "$work/$iso_path" \
        --allowed-root "$work" >/dev/null 2>&1 || true
    done
  else
    fail "未找到项目内 ISO9660 提取器。请先补齐并审查 scripts/image-factory/extract-iso9660-file.py。"
  fi

  local extracted_vmlinuz="${work}/casper/vmlinuz"
  local extracted_initrd="${work}/casper/initrd"
  for artifact in "$extracted_vmlinuz" "$extracted_initrd"; do
    [[ -e "$artifact" ]] || fail "ISO 内缺少预期文件: ${artifact#$work/}"
    [[ ! -L "$artifact" ]] || fail "ISO 解包结果是 symlink，拒绝复制: ${artifact#$work/}"
    [[ -f "$artifact" ]] || fail "ISO 解包结果不是普通文件，拒绝复制: ${artifact#$work/}"
  done
  local livefs_path
  for livefs_path in "${livefs_paths[@]}"; do
    local extracted_livefs="${work}/${livefs_path}"
    [[ -e "$extracted_livefs" ]] || fail "ISO 内缺少预期文件: ${extracted_livefs#$work/}"
    [[ ! -L "$extracted_livefs" ]] || fail "ISO 解包结果是 symlink，拒绝复制: ${extracted_livefs#$work/}"
    [[ -f "$extracted_livefs" ]] || fail "ISO 解包结果不是普通文件，拒绝复制: ${extracted_livefs#$work/}"
  done

  local casper_dir="${target_dir}/casper"
  local disk_dir="${target_dir}/.disk"
  [[ ! -L "$casper_dir" ]] || fail "目标 casper 目录是 symlink，拒绝写入: ${casper_dir#$ROOT_DIR/}"
  mkdir -p "$casper_dir"
  [[ ! -L "$disk_dir" ]] || fail "目标 .disk 目录是 symlink，拒绝写入: ${disk_dir#$ROOT_DIR/}"
  mkdir -p "$disk_dir"

  local vmlinuz_target initrd_target size_target manifest_target install_sources_target uuid_target uuid_generic_target uuid_generic_legacy_target disk_info_target
  vmlinuz_target="$(canonical_child_path "$IMAGES_DIR" "${casper_dir}/vmlinuz")" || fail "vmlinuz 目标路径越界"
  initrd_target="$(canonical_child_path "$IMAGES_DIR" "${casper_dir}/initrd")" || fail "initrd 目标路径越界"
  size_target="$(canonical_child_path "$IMAGES_DIR" "${casper_dir}/filesystem.size")" || fail "filesystem.size 目标路径越界"
  manifest_target="$(canonical_child_path "$IMAGES_DIR" "${casper_dir}/filesystem.manifest")" || fail "filesystem.manifest 目标路径越界"
  install_sources_target="$(canonical_child_path "$IMAGES_DIR" "${casper_dir}/install_sources.yaml")" || fail "install_sources.yaml 目标路径越界"
  uuid_target="$(canonical_child_path "$IMAGES_DIR" "${disk_dir}/casper-uuid")" || fail "casper-uuid 目标路径越界"
  uuid_generic_target="$(canonical_child_path "$IMAGES_DIR" "${disk_dir}/casper-uuid-generic")" || fail "casper-uuid-generic 目标路径越界"
  uuid_generic_legacy_target="$(canonical_child_path "$IMAGES_DIR" "${disk_dir}/casper_uuid_generic")" || fail "casper_uuid_generic 目标路径越界"
  disk_info_target="$(canonical_child_path "$IMAGES_DIR" "${disk_dir}/info")" || fail ".disk/info 目标路径越界"

  install_missing_artifact "$extracted_vmlinuz" "$vmlinuz_target" "vmlinuz"
  install_missing_artifact "$extracted_initrd" "$initrd_target" "initrd"
  for livefs_path in "${livefs_paths[@]}"; do
    local livefs_name livefs_target
    livefs_name="$(basename "$livefs_path")"
    livefs_target="$(canonical_child_path "$IMAGES_DIR" "${casper_dir}/${livefs_name}")" || fail "${livefs_name} 目标路径越界"
    install_missing_artifact "$work/$livefs_path" "$livefs_target" "$livefs_name"
  done
  for companion_path in "${companion_paths[@]}"; do
    local companion_name companion_target
    [[ -f "$work/$companion_path" ]] || continue
    companion_name="$(basename "$companion_path")"
    companion_target="$(canonical_child_path "$IMAGES_DIR" "${casper_dir}/${companion_name}")" || fail "${companion_name} 目标路径越界"
    install_missing_artifact "$work/$companion_path" "$companion_target" "$companion_name"
  done
  [[ ! -f "$work/casper/filesystem.size" ]] || install_missing_artifact "$work/casper/filesystem.size" "$size_target" "filesystem.size"
  [[ ! -f "$work/casper/filesystem.manifest" ]] || install_missing_artifact "$work/casper/filesystem.manifest" "$manifest_target" "filesystem.manifest"
  [[ ! -f "$work/casper/install_sources.yaml" ]] || install_missing_artifact "$work/casper/install_sources.yaml" "$install_sources_target" "install_sources.yaml"
  [[ ! -f "$work/.disk/casper-uuid" ]] || install_missing_artifact "$work/.disk/casper-uuid" "$uuid_target" "casper-uuid"
  [[ ! -f "$work/.disk/casper-uuid-generic" ]] || install_missing_artifact "$work/.disk/casper-uuid-generic" "$uuid_generic_target" "casper-uuid-generic"
  [[ -f "$work/.disk/casper-uuid-generic" || ! -f "$work/.disk/casper_uuid_generic" ]] || install_missing_artifact "$work/.disk/casper_uuid_generic" "$uuid_generic_target" "casper-uuid-generic"
  [[ ! -f "$work/.disk/casper_uuid_generic" ]] || install_missing_artifact "$work/.disk/casper_uuid_generic" "$uuid_generic_legacy_target" "casper_uuid_generic"
  [[ ! -f "$work/.disk/info" ]] || install_missing_artifact "$work/.disk/info" "$disk_info_target" ".disk/info"
  create_casper_compat_aliases "$casper_dir"
  ensure_ready_linux_artifacts "$casper_dir"
  chmod 0755 "$casper_dir" "$disk_dir"
  chmod 0644 "$vmlinuz_target" "$initrd_target"
  local ready_livefs
  for ready_livefs in "${casper_dir}"/*.squashfs; do
    chmod 0644 "$ready_livefs"
  done
  [[ ! -f "$size_target" ]] || chmod 0644 "$size_target"
  [[ ! -f "$manifest_target" ]] || chmod 0644 "$manifest_target"
  [[ ! -f "$install_sources_target" ]] || chmod 0644 "$install_sources_target"
  [[ ! -f "$uuid_target" ]] || chmod 0644 "$uuid_target"
  [[ ! -f "$uuid_generic_target" ]] || chmod 0644 "$uuid_generic_target"
  [[ ! -f "$uuid_generic_legacy_target" ]] || chmod 0644 "$uuid_generic_legacy_target"
  [[ ! -f "$disk_info_target" ]] || chmod 0644 "$disk_info_target"
  info "prepared=${target_dir#$ROOT_DIR/}/casper/vmlinuz ${target_dir#$ROOT_DIR/}/casper/initrd ${#livefs_paths[@]} livefs layer(s)"
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

    if [[ -e "${casper_dir}/vmlinuz" || -e "${casper_dir}/initrd" ]] \
      && compgen -G "${casper_dir}/*.squashfs" >/dev/null \
      && [[ -f "${target_dir}/.disk/casper-uuid-generic" ]]; then
      create_casper_compat_aliases "$casper_dir"
      ensure_ready_linux_artifacts "$casper_dir"
      info "already_prepared=${target_dir#$ROOT_DIR/}"
      continue
    fi

    local rel work_id work
    rel="${iso#$LINUX_DIR/}"
    work_id="$(printf '%s' "$rel" | sha256sum | awk '{print $1}')"
    work="${WORK_ROOT}/${work_id}-$(date +%s)-$$"
    info "extracting=${iso#$ROOT_DIR/}"
    extract_from_iso "$iso" "$target_dir" "$work"
  done < <(find "$LINUX_DIR" -type f -name '*.iso' -print0 | sort -z)

  [[ "$found" -eq 1 ]] || fail "未找到 Linux ISO: data/images/linux/**/*.iso"
  info "DONE: Linux 启动依赖准备完成。请重新扫描镜像并生成菜单。"
}

main "$@"
