#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

HTTP_URL="${SYNABOOT_SMOKE_HTTP_URL:-http://localhost:18080}"
KEEP_RUNNING="${SYNABOOT_SMOKE_KEEP_RUNNING:-0}"

required_iso_paths=(
  "data/images/pe/hotpe/HotPE-V2.8.251018.iso"
  "data/images/windows/win11/Win11_24H2_Pro_Chinese_Simplified_x64.iso"
  "data/images/linux/ubuntu-22.04.3/ubuntu-22.04.3-desktop-amd64.iso"
  "data/images/linux/ubuntu-24.04/ubuntu-24.04.3-desktop-amd64.iso"
)

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

info() {
  printf 'INFO: %s\n' "$1"
}

cleanup() {
  if [[ "$KEEP_RUNNING" != "1" ]]; then
    docker compose down >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

info "SynaBoot real ISO smoke preflight"
info "http_url=${HTTP_URL}"
info "keep_running=${KEEP_RUNNING}"

command -v docker >/dev/null 2>&1 || fail "缺少 docker 命令"
docker compose version >/dev/null 2>&1 || fail "Docker Compose 不可用"

for iso_path in "${required_iso_paths[@]}"; do
  [[ -f "$iso_path" ]] || fail "缺少真实 ISO: ${iso_path}"
  [[ ! -L "$iso_path" ]] || fail "真实 ISO 不能是 symlink: ${iso_path}"
  if ! git check-ignore -q "$iso_path"; then
    fail "真实 ISO 未被 Git 忽略: ${iso_path}"
  fi
done
info "required_iso_files=present_and_ignored"

bash scripts/preflight/check-network-safety.sh
bash scripts/preflight/check-compose-config-safe.sh

docker compose up -d --build

# 首轮真实 ISO 扫描会计算大文件 SHA256，可能超过 Nginx 默认上游超时。
# 这里在 API 容器内直接调用只读扫描函数，仍只写入项目 data/metadata 与 menu.ipxe。
docker compose exec -T synaboot-api python3 - <<'PY'
import json
import main

images = main.scan_images()
summary = {
    "image_count": len(images),
    "iso_count": sum(1 for image in images if image.get("kind") == "iso"),
    "ready_count": sum(1 for image in images if image.get("boot_readiness") == "ready"),
}
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
PY

python3 - "$HTTP_URL" <<'PY'
import json
import sys
from urllib.request import urlopen

base = sys.argv[1].rstrip("/")


def fetch_text(path: str) -> str:
    with urlopen(f"{base}{path}", timeout=20) as response:
        if response.status != 200:
            raise SystemExit(f"BLOCKED: {path} HTTP {response.status}")
        return response.read().decode("utf-8", errors="replace")


html = fetch_text("/")
if "SynaBoot" not in html:
    raise SystemExit("BLOCKED: Web UI 首页未返回 SynaBoot 内容")

images_payload = json.loads(fetch_text("/api/images"))
images = images_payload.get("images") or []
by_path = {image.get("relative_path") or image.get("rel_path"): image for image in images}

expected = {
    "data/images/pe/hotpe/HotPE-V2.8.251018.iso": ("source_iso", "needs_extraction", "incomplete"),
    "data/images/windows/win11/Win11_24H2_Pro_Chinese_Simplified_x64.iso": ("windows_source_iso", "uses_hotpe", "needs_hotpe"),
    "data/images/linux/ubuntu-22.04.3/ubuntu-22.04.3-desktop-amd64.iso": ("source_iso", "prepared", "ready"),
    "data/images/linux/ubuntu-24.04/ubuntu-24.04.3-desktop-amd64.iso": ("source_iso", "prepared", "ready"),
}

for host_path, (source_role, prep_status, boot_readiness) in expected.items():
    rel_path = host_path.removeprefix("data/images/")
    image = by_path.get(rel_path)
    if not image:
        raise SystemExit(f"BLOCKED: /api/images 缺少 {rel_path}")
    if image.get("source_role") != source_role:
        raise SystemExit(f"BLOCKED: {rel_path} source_role={image.get('source_role')!r}")
    if image.get("preparation_status") != prep_status:
        raise SystemExit(f"BLOCKED: {rel_path} preparation_status={image.get('preparation_status')!r}")
    if image.get("boot_readiness") != boot_readiness:
        raise SystemExit(f"BLOCKED: {rel_path} boot_readiness={image.get('boot_readiness')!r}")

menu = fetch_text("/boot/menu.ipxe")
blocked_menu_terms = [
    "HotPE-V2.8.251018.iso",
    "Win11_24H2_Pro_Chinese_Simplified_x64.iso",
]
for term in blocked_menu_terms:
    if term in menu:
        raise SystemExit(f"BLOCKED: raw ISO 被写入 menu.ipxe: {term}")
for term in ("ubuntu-22.04.3-desktop-amd64.iso", "ubuntu-24.04.3-desktop-amd64.iso"):
    if term not in menu:
        raise SystemExit(f"BLOCKED: prepared Linux ISO 未进入 menu.ipxe: {term}")

images_index = fetch_text("/images/")
if "Index of /images/" not in images_index:
    raise SystemExit("BLOCKED: /images/ 未返回镜像仓库索引")

print("INFO: web_ui=ok")
print("INFO: api_images=ok")
print("INFO: menu_raw_iso_absent=ok")
print("INFO: images_index=ok")
PY

if [[ "$KEEP_RUNNING" == "1" ]]; then
  info "KEEP_RUNNING=1，服务保持运行"
else
  info "即将执行 docker compose down"
fi

info "APPROVED: 真实 ISO smoke test 通过"
