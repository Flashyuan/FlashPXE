#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

info() {
  printf 'INFO: %s\n' "$1"
}

section() {
  printf '\n== %s ==\n' "$1"
}

count_lines() {
  if [[ -z "$1" ]]; then
    printf '0'
  else
    printf '%s\n' "$1" | wc -l | tr -d ' '
  fi
}

section "release target"
current_branch="$(git branch --show-current)"
current_upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
info "branch=${current_branch}"
info "upstream=${current_upstream:-none}"
info "release_channel=${SYNABOOT_RELEASE_CHANNEL:-free}"
origin_url="$(git remote get-url origin 2>/dev/null || true)"
if [[ "${origin_url}" != *github.com* ]]; then
  printf 'BLOCKED: origin remote is not a GitHub URL\n' >&2
  exit 1
fi
info "origin_remote=github"
info "origin_host=github.com"

section "git scope summary"
tracked_changed="$(git diff --name-only --diff-filter=ACMR || true)"
staged_changed="$(git diff --cached --name-only --diff-filter=ACMR || true)"
untracked_public="$(git ls-files --others --exclude-standard || true)"
ignored_runtime="$(git status --ignored --short | awk '/^!! / {print $2}' || true)"
info "tracked_changed_count=$(count_lines "$tracked_changed")"
info "staged_changed_count=$(count_lines "$staged_changed")"
info "untracked_public_count=$(count_lines "$untracked_public")"
info "ignored_runtime_count=$(count_lines "$ignored_runtime")"

section "required preflights"
bash scripts/preflight/check-release-scope.sh
bash scripts/preflight/check-private-commercial-scope.sh
bash scripts/preflight/check-edition-boundary.sh
bash scripts/preflight/check-public-runtime-boundary.sh
bash scripts/preflight/check-autoinstall-boundary.sh
bash scripts/preflight/check-software-assignment-flow.sh
bash scripts/preflight/check-subagent-governance.sh
bash scripts/preflight/check-iso-extractor-safety.sh
bash scripts/preflight/check-loader-import-safety.sh
bash scripts/preflight/check-network-safety.sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/preflight/check-phase3-gates.py
bash scripts/preflight/check-compose-config-safe.sh
git diff --check
git diff --cached --check

section "public manifests"
python3 - <<'PY'
import json
from pathlib import Path

checks = [
    (
        Path("config/synaboot/capabilities.free.json"),
        {
            "edition": "free",
            "release_channel": "free",
            "commercial_code_included": False,
            "online_activation_required": False,
        },
    ),
    (
        Path("config/synaboot/editions.public.json"),
        {
            "commercial_code_included": False,
            "online_activation_required": False,
        },
    ),
]
for path, expected in checks:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, expected_value in expected.items():
        actual = data.get(key)
        if actual is not expected_value and actual != expected_value:
            raise SystemExit(f"BLOCKED: {path}:{key} expected {expected_value!r}, actual {actual!r}")
print("INFO: public_manifest_fields=valid")
PY
info "capabilities_manifest=config/synaboot/capabilities.free.json"
info "editions_catalog=config/synaboot/editions.public.json"
info "commercial_code_included=false"
info "online_activation_required=false"

section "commercial indicator review"
release_paths="$(printf '%s\n%s\n%s\n' "$tracked_changed" "$staged_changed" "$untracked_public" | awk 'NF' | sort -u)"
indicator_hits="$(
  if [[ -n "$release_paths" ]]; then
    while IFS= read -r release_path; do
      [[ -f "$release_path" ]] || continue
      rg -l -i 'commercial|professional|enterprise|license|licen[cs]e|paid|payment|billing|subscription|activation|obfuscat|dist-obfuscated|private-commercial' -- "$release_path" 2>/dev/null || true
    done <<< "$release_paths" | sort -u
  fi
)"
info "commercial_indicator_file_count=$(count_lines "$indicator_hits")"
if [[ -n "$indicator_hits" ]]; then
  printf '%s\n' "$indicator_hits" | sed 's/^/INFO: commercial_indicator_file=/'
  INDICATOR_HITS="$indicator_hits" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path("config/synaboot/commercial-indicators.allowlist.json")
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except FileNotFoundError:
    raise SystemExit(f"BLOCKED: 缺少商业关键词 allowlist: {path}")
except json.JSONDecodeError as exc:
    raise SystemExit(f"BLOCKED: {path} 不是合法 JSON: line={exc.lineno} column={exc.colno}")

expected = {
    "schema_version": "synaboot.commercial-indicators-allowlist.v1",
    "purpose": "free_release_commercial_keyword_review_boundary",
    "commercial_code_included": False,
    "online_activation_required": False,
}
for key, expected_value in expected.items():
    actual = data.get(key)
    if actual != expected_value:
        raise SystemExit(f"BLOCKED: {path}:{key} expected {expected_value!r}, actual {actual!r}")

allowed = set(data.get("allowed_files") or [])
hits = {line.strip() for line in os.environ.get("INDICATOR_HITS", "").splitlines() if line.strip()}
unexpected = sorted(hits - allowed)
if unexpected:
    for item in unexpected:
        print(f"BLOCKED: unexpected_commercial_indicator_file={item}")
    raise SystemExit("BLOCKED: 商业关键词命中文件未登记 allowlist")

unused = sorted(allowed - hits)
if unused:
    for item in unused:
        print(f"INFO: unused_commercial_indicator_allowlist_file={item}")

print("INFO: commercial_indicator_allowlist=matched")
PY
  info "commercial_indicator_review=allowlist_matched_requires_git_audit_semantic_review"
else
  info "commercial_indicator_review=no_hits"
fi

section "token disclosure guard"
bash scripts/preflight/check-token-disclosure.sh

section "runtime safety"
if ss -lntu 2>/dev/null | grep -q ':18080'; then
  info "http_18080=listening"
else
  info "http_18080=not_listening"
fi
if find apps scripts -path '*/__pycache__*' -print | grep -q .; then
  printf 'BLOCKED: Python bytecode cache exists under apps/ or scripts/\n' >&2
  exit 1
fi
info "python_bytecode_cache=absent"

section "result"
info "APPROVED: release evidence checks passed for the free-edition GitHub line"
