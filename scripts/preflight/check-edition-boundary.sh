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

info "SynaBoot edition boundary preflight"

python3 - <<'PY'
import ast
import json
from pathlib import Path

capabilities_path = Path("config/synaboot/capabilities.free.json")
catalog_path = Path("config/synaboot/editions.public.json")
api_path = Path("apps/api/main.py")


def block(message: str) -> None:
    raise SystemExit(f"BLOCKED: {message}")


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        block(f"缺少版本边界文件: {path}")
    except json.JSONDecodeError as exc:
        block(f"{path} 不是合法 JSON: line={exc.lineno} column={exc.colno}")
    if not isinstance(data, dict):
        block(f"{path} 顶层必须是 JSON object")
    return data


def load_api_default(name: str) -> dict:
    try:
        module = ast.parse(api_path.read_text(encoding="utf-8"), filename=str(api_path))
    except FileNotFoundError:
        block(f"缺少 API 文件: {api_path}")
    except SyntaxError as exc:
        block(f"{api_path} 语法错误: line={exc.lineno} offset={exc.offset}")
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    block(f"{api_path}:{name} 必须是可静态解析的 literal")
                if not isinstance(value, dict):
                    block(f"{api_path}:{name} 必须是 dict")
                return value
    block(f"{api_path} 缺少 {name}")


capabilities = load_json(capabilities_path)
catalog = load_json(catalog_path)
api_capabilities = load_api_default("DEFAULT_FREE_CAPABILITIES")
api_catalog = load_api_default("DEFAULT_EDITION_CATALOG")

if api_capabilities != capabilities:
    block(f"{api_path}:DEFAULT_FREE_CAPABILITIES 必须与 {capabilities_path} 完全一致")
if api_catalog != catalog:
    block(f"{api_path}:DEFAULT_EDITION_CATALOG 必须与 {catalog_path} 完全一致")

expected_capability_fields = {
    "schema_version": "synaboot.capabilities.v1",
    "edition": "free",
    "release_channel": "free",
    "owner_local_full_feature_allowed": True,
    "github_public_release": True,
    "commercial_code_included": False,
    "online_activation_required": False,
}
for key, expected in expected_capability_fields.items():
    if capabilities.get(key) != expected:
        block(f"{capabilities_path}:{key} expected {expected!r}, actual {capabilities.get(key)!r}")

free_limits = capabilities.get("free_limits")
if not isinstance(free_limits, dict):
    block(f"{capabilities_path}:free_limits 必须是 object")
for key in (
    "basic_image_count_limited",
    "basic_menu_generation_limited",
    "manual_ipxe_http_boot_limited",
    "basic_autoinstall_profile_drafts_limited",
    "offline_core_requires_license",
):
    if free_limits.get(key) is not False:
        block(f"{capabilities_path}:free_limits.{key} 必须为 false")

required_free_guarantees = {
    "docker_compose_deploy",
    "http_image_repository",
    "local_iso_scan",
    "hotpe_assisted_windows_install",
    "ubuntu_linux_basic_boot_preparation",
    "ipxe_http_menu_generation",
    "manual_ipxe_usb_iso_efi_boot",
    "manual_uefi_http_boot",
    "basic_web_image_management",
    "basic_autoinstall_profile_drafts",
    "autoinstall_template_variable_allowlist",
    "autoinstall_template_preview",
    "network_safety_preflight",
    "phase3_readonly_boot_entry_status",
}
actual_free_guarantees = set(capabilities.get("core_free_guarantees") or [])
missing_guarantees = sorted(required_free_guarantees - actual_free_guarantees)
if missing_guarantees:
    block(f"{capabilities_path}:core_free_guarantees 缺少 {missing_guarantees}")

expected_catalog_fields = {
    "schema_version": "synaboot.editions.v1",
    "catalog_purpose": "public_display_only_no_license_gate",
    "pricing_model_status": "proposal_not_enforcement",
    "commercial_code_included": False,
    "online_activation_required": False,
}
for key, expected in expected_catalog_fields.items():
    if catalog.get(key) != expected:
        block(f"{catalog_path}:{key} expected {expected!r}, actual {catalog.get(key)!r}")

tiers = catalog.get("tiers")
if not isinstance(tiers, list):
    block(f"{catalog_path}:tiers 必须是 array")
tier_ids = {tier.get("id") for tier in tiers if isinstance(tier, dict)}
required_tier_ids = {"free", "professional", "enterprise", "usage_based"}
missing_tiers = sorted(required_tier_ids - tier_ids)
if missing_tiers:
    block(f"{catalog_path}:tiers 缺少 {missing_tiers}")

for tier in tiers:
    if not isinstance(tier, dict):
        block(f"{catalog_path}:tiers 中存在非 object 项")
    tier_id = tier.get("id")
    if tier_id == "free":
        if tier.get("billing") != "free":
            block(f"{catalog_path}:free.billing 必须为 free")
        limits = tier.get("limits")
        if not isinstance(limits, dict):
            block(f"{catalog_path}:free.limits 必须是 object")
        if any(value is not False for value in limits.values()):
            block(f"{catalog_path}:free.limits 所有值必须为 false")
    elif tier_id in {"professional", "enterprise", "usage_based"}:
        if "candidate" not in str(tier.get("billing", "")):
            block(f"{catalog_path}:{tier_id}.billing 必须声明为 candidate")
        if not tier.get("candidate_features"):
            block(f"{catalog_path}:{tier_id}.candidate_features 不能为空")

guardrails = "\n".join(str(item) for item in (catalog.get("guardrails") or []))
for required_text in (
    "当前 GitHub 分支只发布 Free 免费版代码",
    "不包含实现代码",
    "商业源码、私有 license 和混淆产物不得进入 GitHub 免费发布线",
    "任何收费能力都不得削弱基础装机和网络安全门禁",
):
    if required_text not in guardrails:
        block(f"{catalog_path}:guardrails 缺少关键边界: {required_text}")

print("INFO: edition_boundary_manifest=valid")
print("INFO: api_embedded_defaults=match_public_manifests")
print("INFO: free_core_license_gate=absent")
print("INFO: commercial_tiers=proposal_only")
PY

info "APPROVED: 版本边界 manifest 符合免费发布线"
