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

info "SynaBoot token disclosure preflight"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail "必须在 Git 工作区内运行"
fi

release_paths="$(
  printf '%s\n%s\n%s\n' \
    "$(git diff --name-only --diff-filter=ACMR || true)" \
    "$(git diff --cached --name-only --diff-filter=ACMR || true)" \
    "$(git ls-files --others --exclude-standard || true)" \
    | awk 'NF' | sort -u
)"

token_example_hits="$(
  if [[ -n "$release_paths" ]]; then
    while IFS= read -r release_path; do
      [[ -f "$release_path" ]] || continue
      [[ "$release_path" == "scripts/preflight/check-token-disclosure.sh" ]] && continue
      rg -n -H 'SYNABOOT_ADMIN_TOKEN=[^[:space:]]+[[:space:]]+(bash|docker|curl|python|python3|node|sh|docker compose|compose)|local-smoke-token|<管理员token>' -- "$release_path" 2>/dev/null \
        | awk -F: '{print $1 ":" $2}' || true
    done <<< "$release_paths"
  fi
)"

if [[ -n "$token_example_hits" ]]; then
  printf '%s\n' "$token_example_hits" >&2
  fail "发布范围存在内联管理员 token 命令示例或历史 token 占位"
fi

info "inline_admin_token_examples=absent"
