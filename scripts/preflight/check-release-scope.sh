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

release_channel="${SYNABOOT_RELEASE_CHANNEL:-free}"
expected_branch="${SYNABOOT_FREE_BRANCH:-codex/synaboot-phase1}"
expected_upstream="${SYNABOOT_FREE_UPSTREAM:-origin/codex/synaboot-phase1}"
info "SynaBoot release scope preflight"
info "RELEASE_CHANNEL=${release_channel}"

if [[ "${release_channel}" != "free" ]]; then
  fail "当前仓库只允许校验 free 发布范围；商业版本必须使用本机私有流程，不得 push 到当前 GitHub 分支"
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail "必须在 Git 工作区内运行"
fi

current_branch="$(git branch --show-current)"
current_upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
info "CURRENT_BRANCH=${current_branch}"
info "CURRENT_UPSTREAM=${current_upstream:-none}"

if [[ "${current_branch}" != "${expected_branch}" ]]; then
  fail "当前分支不是免费版发布线: expected=${expected_branch}, actual=${current_branch}"
fi

if [[ "${current_upstream}" != "${expected_upstream}" ]]; then
  fail "当前上游不是免费版 GitHub 发布线: expected=${expected_upstream}, actual=${current_upstream:-none}"
fi

forbidden_path_re='(^|/)(commercial|private-commercial|private|enterprise|proprietary|paid|dist-commercial|dist-obfuscated)(/|$)'
forbidden_generated_path_re='^data/(logs|builds)(/|$)|^data/metadata/.*\.(sqlite3|sqlite|db)$'
forbidden_ext_re='\.(iso|wim|esd|img|vhd|vhdx|qcow2|obf\.js|obf\.py|min\.private\.js|license|lic|sqlite3|sqlite|db)$'
forbidden_secret_re='(^|/)(\.env|.*\.pem|.*\.key|.*_rsa|.*_ed25519)$'

check_paths() {
  local label="$1"
  local paths="$2"
  [[ -z "${paths}" ]] && return 0
  while IFS= read -r path; do
    [[ -z "${path}" ]] && continue
    if [[ "${path}" == */.gitkeep ]]; then
      continue
    fi
    if [[ "${path}" =~ ${forbidden_path_re} ]]; then
      fail "${label} 包含商业/私有路径，禁止进入免费版 GitHub 分支: ${path}"
    fi
    if [[ "${path}" =~ ${forbidden_generated_path_re} ]]; then
      fail "${label} 包含数据库、日志或构建产物，禁止进入免费版 GitHub 分支: ${path}"
    fi
    if [[ "${path,,}" =~ ${forbidden_ext_re} ]]; then
      fail "${label} 包含镜像、授权或混淆产物，禁止进入免费版 GitHub 分支: ${path}"
    fi
    if [[ "${path}" =~ ${forbidden_secret_re} ]]; then
      fail "${label} 包含疑似密钥或环境文件，禁止进入 Git: ${path}"
    fi
  done <<< "${paths}"
}

tracked_paths="$(git ls-files)"
staged_paths="$(git diff --cached --name-only --diff-filter=ACMR || true)"
untracked_paths="$(git ls-files --others --exclude-standard || true)"

check_paths "tracked files" "${tracked_paths}"
check_paths "staged files" "${staged_paths}"
check_paths "untracked files" "${untracked_paths}"

if git diff --cached --name-only --diff-filter=ACMR | grep -q .; then
  info "发现暂存文件，已完成 tracked/staged/untracked 免费版发布范围检查"
else
  info "当前无暂存文件，已完成 tracked/untracked 免费版发布范围检查"
fi

info "APPROVED: 当前 Git 范围符合免费版发布边界"
