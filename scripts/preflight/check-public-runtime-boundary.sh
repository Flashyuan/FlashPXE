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

info "SynaBoot public runtime boundary preflight"

nginx_config="config/nginx/default.conf"
[[ -f "$nginx_config" ]] || fail "缺少 Nginx 配置: ${nginx_config}"
grep -Fq 'provenance\.json' "$nginx_config" || fail "Nginx 必须拒绝公开访问 provenance 文件"
grep -Fq 'return 404;' "$nginx_config" || fail "Nginx provenance 拒绝规则必须返回 404"

python3 - <<'PY'
import ast
import json
import re
from pathlib import Path

api_path = Path("apps/api/main.py")
web_roots = [Path("apps/web/src"), Path("apps/web/assets/app.js")]
allowlist_path = Path("config/synaboot/public-runtime.allowlist.json")

blocked_endpoint_words = (
    "license",
    "licence",
    "payment",
    "billing",
    "subscription",
    "activation",
    "activate",
    "professional",
    "enterprise",
    "usage",
    "paid",
    "commercial",
    "obfuscat",
)


def block(message: str) -> None:
    raise SystemExit(f"BLOCKED: {message}")


def load_allowlist() -> dict:
    try:
        data = json.loads(allowlist_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        block(f"缺少公开运行时白名单: {allowlist_path}")
    except json.JSONDecodeError as exc:
        block(f"{allowlist_path} 不是合法 JSON: line={exc.lineno} column={exc.colno}")
    if not isinstance(data, dict):
        block(f"{allowlist_path} 顶层必须是 JSON object")
    expected = {
        "schema_version": "synaboot.public-runtime-allowlist.v1",
        "purpose": "free_public_runtime_api_boundary",
        "commercial_code_included": False,
        "online_activation_required": False,
    }
    for key, expected_value in expected.items():
        if data.get(key) != expected_value:
            block(f"{allowlist_path}:{key} expected {expected_value!r}, actual {data.get(key)!r}")
    return data


def api_string_constants() -> set[str]:
    try:
        module = ast.parse(api_path.read_text(encoding="utf-8"), filename=str(api_path))
    except FileNotFoundError:
        block(f"缺少 API 文件: {api_path}")
    except SyntaxError as exc:
        block(f"{api_path} 语法错误: line={exc.lineno} offset={exc.offset}")
    values: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.add(node.value)
    return values


def web_api_urls() -> set[str]:
    paths: list[Path] = []
    for root in web_roots:
        if root.is_file():
            paths.append(root)
        elif root.is_dir():
            paths.extend(sorted(p for p in root.rglob("*") if p.suffix in {".js", ".jsx", ".ts", ".tsx"}))
    if not paths:
        block("缺少 Web 运行时代码: apps/web/src 或 apps/web/assets/app.js")
    text_parts = []
    for path in paths:
        try:
            text_parts.append(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            block(f"Web 文件不是 UTF-8: {path}")
    text = "\n".join(text_parts)
    # 只检查前端静态 fetch URL；模板字符串中的动态 id 会保留 /api/... 前缀。
    static_matches = re.findall(r"""["'`](/api/[^"'`$]*)["'`]""", text)
    template_prefixes = re.findall(r"""`(/api/[^`$]*)\$\{""", text)
    matches = [*static_matches, *template_prefixes]
    return {match.rstrip("/") for match in matches}


def normalize_api_path(value: str) -> str | None:
    value = value.strip()
    if not value.startswith("/api/"):
        return None
    value = value.split("?", 1)[0]
    return value.rstrip("/")


allowlist = load_allowlist()
exact_api_paths = set(allowlist.get("exact_api_paths") or [])
allowed_api_prefixes = tuple(allowlist.get("allowed_api_prefixes") or [])
if not all(isinstance(path, str) and path.startswith("/api/") for path in exact_api_paths):
    block(f"{allowlist_path}:exact_api_paths 必须全部是 /api/... 字符串")
if not all(isinstance(path, str) and path.startswith("/api/") and path.endswith("/") for path in allowed_api_prefixes):
    block(f"{allowlist_path}:allowed_api_prefixes 必须全部是以 /api/.../ 结尾的字符串")

api_paths = sorted({
    path
    for value in api_string_constants()
    for path in [normalize_api_path(value)]
    if path
})
web_paths = sorted({
    path
    for value in web_api_urls()
    for path in [normalize_api_path(value)]
    if path
})

blocked_hits = []
for source, paths in (("api", api_paths), ("web", web_paths)):
    for path in paths:
        lowered = path.lower()
        if any(word in lowered for word in blocked_endpoint_words):
            blocked_hits.append(f"{source}:{path}")

if blocked_hits:
    for hit in blocked_hits:
        print(hit)
    block("公开运行时代码出现商业授权、收费层、支付、激活或混淆相关 API 入口")

unexpected_paths = []
for source, paths in (("api", api_paths), ("web", web_paths)):
    for path in paths:
        allowed = path in exact_api_paths or any(path.startswith(prefix.rstrip("/")) for prefix in allowed_api_prefixes)
        if not allowed:
            unexpected_paths.append(f"{source}:{path}")

if unexpected_paths:
    for hit in unexpected_paths:
        print(hit)
    block("公开运行时代码出现未登记 API 入口，请先更新白名单并完成审查")

unused_exact_paths = sorted(exact_api_paths - set(api_paths) - set(web_paths))
if unused_exact_paths:
    for path in unused_exact_paths:
        print(f"unused:{path}")
    block("公开运行时白名单包含当前代码未引用的 API 入口，请删除或补充审查说明")

print(f"INFO: api_endpoint_count={len(api_paths)}")
print(f"INFO: web_api_reference_count={len(web_paths)}")
print("INFO: public_runtime_allowlist=matched")
print("INFO: public_runtime_commercial_endpoints=absent")
PY

info "APPROVED: 公开运行时代码未发现商业实现 API 入口"
