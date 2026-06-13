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

info "SynaBoot free GitHub push readiness preflight"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail "必须在 Git 工作区内运行"
fi

bash scripts/preflight/collect-release-evidence.sh

current_branch="$(git branch --show-current)"
current_upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
origin_url="$(git remote get-url origin 2>/dev/null || true)"
tracked_dirty="$(git diff --name-only --diff-filter=ACMR || true)"
staged_dirty="$(git diff --cached --name-only --diff-filter=ACMR || true)"
untracked_public="$(git ls-files --others --exclude-standard || true)"

[[ "$current_branch" == "${SYNABOOT_FREE_BRANCH:-codex/synaboot-phase1}" ]] \
  || fail "当前分支不是免费版发布线: ${current_branch}"
[[ "$current_upstream" == "${SYNABOOT_FREE_UPSTREAM:-origin/codex/synaboot-phase1}" ]] \
  || fail "当前 upstream 不是免费版 GitHub 发布线: ${current_upstream:-none}"
[[ "$origin_url" == *github.com* ]] || fail "origin remote 不是 GitHub"

if [[ -n "$tracked_dirty" ]]; then
  printf '%s\n' "$tracked_dirty" >&2
  fail "存在未提交 tracked 变更；push 前必须先完成审计、提交或明确放弃"
fi
if [[ -n "$staged_dirty" ]]; then
  printf '%s\n' "$staged_dirty" >&2
  fail "存在暂存但未提交的变更；push 前必须先提交或取消暂存"
fi
if [[ -n "$untracked_public" ]]; then
  printf '%s\n' "$untracked_public" >&2
  fail "存在未跟踪 public 文件；push 前必须纳入审计提交或加入正确忽略规则"
fi

info "branch=${current_branch}"
info "upstream=${current_upstream}"
info "origin_remote=github"
info "working_tree=clean_for_push"
info "APPROVED: 当前免费版分支具备 push 前只读就绪证据"
