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

private_paths=(
  "commercial"
  "private-commercial"
  "private"
  "enterprise"
  "proprietary"
  "paid"
  "dist-commercial"
  "dist-obfuscated"
)

info "SynaBoot private commercial scope preflight"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail "必须在 Git 工作区内运行"
fi

tracked_private="$(
  git ls-files \
    commercial 'commercial/**' \
    private-commercial 'private-commercial/**' \
    private 'private/**' \
    enterprise 'enterprise/**' \
    proprietary 'proprietary/**' \
    paid 'paid/**' \
    dist-commercial 'dist-commercial/**' \
    dist-obfuscated 'dist-obfuscated/**' \
    2>/dev/null || true
)"
if [[ -n "$tracked_private" ]]; then
  printf '%s\n' "$tracked_private" >&2
  fail "商业/私有工作区文件已被 Git 跟踪，禁止进入免费版发布线"
fi

staged_private="$(git diff --cached --name-only --diff-filter=ACMR | grep -E '^(commercial|private-commercial|private|enterprise|proprietary|paid|dist-commercial|dist-obfuscated)(/|$)' || true)"
if [[ -n "$staged_private" ]]; then
  printf '%s\n' "$staged_private" >&2
  fail "商业/私有工作区文件已被暂存，禁止 commit/push 到免费版发布线"
fi

untracked_private="$(git ls-files --others --exclude-standard | grep -E '^(commercial|private-commercial|private|enterprise|proprietary|paid|dist-commercial|dist-obfuscated)(/|$)' || true)"
if [[ -n "$untracked_private" ]]; then
  printf '%s\n' "$untracked_private" >&2
  fail "商业/私有路径出现在未忽略 untracked 范围，请检查 .gitignore"
fi

for path in "${private_paths[@]}"; do
  if ! git check-ignore -q "$path/.synaboot-ignore-probe"; then
    fail "私有商业路径未被 .gitignore 覆盖: ${path}/"
  fi
done

tracked_forbidden_artifacts="$(git ls-files | grep -Ei '\.(obf\.js|obf\.py|min\.private\.js|license|lic)$|(^|/)(commercial|private-commercial|private|enterprise|proprietary|paid|dist-commercial|dist-obfuscated)(/|$)' || true)"
if [[ -n "$tracked_forbidden_artifacts" ]]; then
  printf '%s\n' "$tracked_forbidden_artifacts" >&2
  fail "免费发布线存在商业、授权或混淆相关 tracked 文件"
fi

staged_forbidden_artifacts="$(git diff --cached --name-only --diff-filter=ACMR | grep -Ei '\.(obf\.js|obf\.py|min\.private\.js|license|lic)$|(^|/)(commercial|private-commercial|private|enterprise|proprietary|paid|dist-commercial|dist-obfuscated)(/|$)' || true)"
if [[ -n "$staged_forbidden_artifacts" ]]; then
  printf '%s\n' "$staged_forbidden_artifacts" >&2
  fail "暂存区存在商业、授权或混淆相关文件"
fi

runtime_boundary_files=(
  "docker-compose.yml"
  "apps/api/main.py"
  "apps/web/assets/app.js"
  "apps/web/index.html"
)
private_runtime_re='(^|[^[:alnum:]_.-])(commercial|private-commercial|private|enterprise|proprietary|paid|dist-commercial|dist-obfuscated)(/|:|$)'
for file in "${runtime_boundary_files[@]}"; do
  [[ -f "$file" ]] || continue
  if grep -Einq "$private_runtime_re" "$file"; then
    grep -Ein "$private_runtime_re" "$file" >&2
    fail "${file} 包含私有商业路径引用，禁止成为免费版默认运行依赖"
  fi
done

info "private_paths_ignored=${#private_paths[@]}"
info "tracked_private_files=0"
info "staged_private_files=0"
info "untracked_public_private_files=0"
info "default_runtime_private_path_refs=0"
info "APPROVED: 商业私有工作区与混淆产物未进入免费版 Git 发布范围"
