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

info "SynaBoot autoinstall boundary preflight"

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import ast
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

api_path = Path("apps/api/main.py")
capabilities_path = Path("config/synaboot/capabilities.free.json")
runtime_allowlist_path = Path("config/synaboot/public-runtime.allowlist.json")


def block(message: str) -> None:
    raise SystemExit(f"BLOCKED: {message}")


try:
    api_text = api_path.read_text(encoding="utf-8")
    module_ast = ast.parse(api_text, filename=str(api_path))
except FileNotFoundError:
    block(f"缺少 API 文件: {api_path}")
except SyntaxError as exc:
    block(f"{api_path} 语法错误: line={exc.lineno} offset={exc.offset}")

for forbidden_table in ("image_autoinstall_bindings", "autoinstall_policies"):
    if re.search(rf"CREATE\s+TABLE[^\n;]+{forbidden_table}", api_text, flags=re.IGNORECASE | re.DOTALL):
        block(f"Phase 2.12 不得创建真实绑定/策略表: {forbidden_table}")

api_strings = {
    node.value
    for node in ast.walk(module_ast)
    if isinstance(node, ast.Constant) and isinstance(node.value, str)
}
autoinstall_api_paths = sorted(
    value.rstrip("/")
    for value in api_strings
    if value.startswith("/api/autoinstall")
)
allowed_autoinstall_paths = {
    "/api/autoinstall-profiles",
    "/api/autoinstall-binding-plan",
    "/api/autoinstall-bindings/plan",
}
unexpected_paths = sorted(set(autoinstall_api_paths) - allowed_autoinstall_paths)
if unexpected_paths:
    for path in unexpected_paths:
        print(f"BLOCKED: unexpected_autoinstall_api_path={path}")
    block("自动安装 API 超出 Phase 2.12 草稿/只读规划范围")

if "write_api_available" not in api_text or '"write_api_available": False' not in api_text:
    block("autoinstall_binding_plan 必须显式声明 write_api_available=False")
if "runtime_binding_enabled" not in api_text or '"runtime_binding_enabled": False' not in api_text:
    block("autoinstall_binding_plan 必须显式声明 runtime_binding_enabled=False")
if "menu_integration_enabled" not in api_text or '"menu_integration_enabled": False' not in api_text:
    block("autoinstall_binding_plan 必须显式声明 menu_integration_enabled=False")
if "policy_matching_enabled" not in api_text or '"policy_matching_enabled": False' not in api_text:
    block("autoinstall_binding_plan 必须显式声明 policy_matching_enabled=False")
if "draft_review_required" not in api_text:
    block("autoinstall profile 必须保持人工审查草稿状态")
if "manual_review_required_no_storage_autopartition" not in api_text:
    block("autoinstall profile 必须声明不自动生成清盘分区策略")

spec = importlib.util.spec_from_file_location("synaboot_api_boundary", api_path)
api = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(api)
for os_family in ("ubuntu", "windows"):
    template_kind, template_preview, variables = api.autoinstall_template(os_family)
    if not isinstance(template_kind, str) or not isinstance(template_preview, str):
        block(f"{os_family} autoinstall template 返回值类型异常")
    if not isinstance(variables, list) or not all(isinstance(item, str) for item in variables):
        block(f"{os_family} autoinstall variables 必须是字符串白名单")
    if re.search(r"(?im)^\s*storage\s*:", template_preview):
        block(f"{os_family} autoinstall 模板不得默认包含 storage 自动分区配置")
    forbidden_template_terms = (
        "DiskConfiguration",
        "CreatePartitions",
        "ModifyPartitions",
        "ProductKey",
        "AutoLogon",
        "{{PASSWORD",
        "{{TOKEN",
        "{{SECRET",
        "{{PRIVATE_KEY",
    )
    for term in forbidden_template_terms:
        if term.lower() in template_preview.lower():
            block(f"{os_family} autoinstall 模板包含禁止默认项: {term}")

try:
    capabilities = json.loads(capabilities_path.read_text(encoding="utf-8"))
except FileNotFoundError:
    block(f"缺少免费版能力 manifest: {capabilities_path}")
except json.JSONDecodeError as exc:
    block(f"{capabilities_path} 不是合法 JSON: line={exc.lineno} column={exc.colno}")

free_limits = capabilities.get("free_limits") or {}
if free_limits.get("basic_autoinstall_profile_drafts_limited") is not False:
    block("免费版基础自动安装草稿不得限量")
required_guarantees = {
    "basic_autoinstall_profile_drafts",
    "autoinstall_template_variable_allowlist",
    "autoinstall_template_preview",
}
missing = sorted(required_guarantees - set(capabilities.get("core_free_guarantees") or []))
if missing:
    block(f"免费版能力 manifest 缺少自动安装草稿保障: {missing}")

try:
    runtime_allowlist = json.loads(runtime_allowlist_path.read_text(encoding="utf-8"))
except FileNotFoundError:
    block(f"缺少公开运行时白名单: {runtime_allowlist_path}")
except json.JSONDecodeError as exc:
    block(f"{runtime_allowlist_path} 不是合法 JSON: line={exc.lineno} column={exc.colno}")

exact_paths = set(runtime_allowlist.get("exact_api_paths") or [])
missing_paths = sorted(allowed_autoinstall_paths - exact_paths)
if missing_paths:
    block(f"公开运行时白名单缺少自动安装 API: {missing_paths}")

print(f"INFO: autoinstall_api_path_count={len(autoinstall_api_paths)}")
print("INFO: autoinstall_binding_write_api=absent")
print("INFO: autoinstall_policy_tables=absent")
print("INFO: autoinstall_templates_safe_draft=present")
PY

info "APPROVED: 自动安装草稿边界符合免费版发布线"
