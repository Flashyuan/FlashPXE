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

extractor="scripts/image-factory/extract-iso9660-file.py"
prepare_script="scripts/image-factory/prepare-linux-boot-artifacts.sh"

info "SynaBoot ISO extractor safety preflight"

[[ -f "$extractor" ]] || fail "缺少 ISO9660 提取器"
[[ -f "$prepare_script" ]] || fail "缺少 Linux 启动依赖准备脚本"

python3 - <<'PY'
import ast
from pathlib import Path

for path in [
    Path("scripts/image-factory/extract-iso9660-file.py"),
]:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
print("INFO: extractor_ast=valid")
PY

grep -q 'MAX_EXTRACT_BYTES' "$extractor" || fail "提取器必须限制目标文件大小"
grep -q 'validate_extent' "$extractor" || fail "提取器必须校验 extent 越界"
grep -q 'os.O_EXCL' "$extractor" || fail "提取器必须使用不覆盖写入"
grep -q 'allowed_root' "$extractor" || fail "提取器必须校验 allowed-root"
grep -q 'COPY_CHUNK_SIZE' "$extractor" || fail "提取器必须流式复制"

grep -q 'safe_reset_work_dir' "$prepare_script" || fail "准备脚本必须使用安全 work 目录校验"
grep -q 'ensure_no_symlink_chain' "$prepare_script" || fail "准备脚本必须拒绝 symlink 父路径"
grep -q 'extract-iso9660-file.py' "$prepare_script" || fail "准备脚本必须接入项目内 ISO9660 fallback"
if grep -Eq 'rm[[:space:]]+-rf' "$prepare_script"; then
  fail "准备脚本禁止使用 rm -rf 清理动态工作目录"
fi
if grep -Eq 'mount|losetup|mkfs|parted|sfdisk|dd[[:space:]]+if=' "$prepare_script" "$extractor"; then
  fail "ISO 准备脚本禁止挂载 ISO 或执行磁盘类操作"
fi

info "APPROVED: ISO 提取器安全不变量有效"
