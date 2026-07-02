#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

SYNABOOT_DATA_DIR="$tmp_dir" \
SYNABOOT_ADMIN_TOKEN="test-admin-token" \
SYNABOOT_SERVER_IP="10.101.8.135" \
SYNABOOT_FEISHU_UBUNTU_DEB_URL="https://example.com/feishu-linux-amd64.deb" \
PYTHONDONTWRITEBYTECODE=1 \
python3 - <<'PY'
import importlib.util
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

root = Path.cwd()
spec = importlib.util.spec_from_file_location("synaboot_api_smoke", root / "apps/api/main.py")
api = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(api)

api.connect_db().close()

for rel_path in [
    "pe/hotpe/wimboot",
    "windows/win11/boot/BCD",
    "windows/win11/boot/boot.sdi",
    "windows/win11/boot/boot.wim",
    "linux/ubuntu-24.04/ubuntu-24.04-desktop-amd64.iso",
    "linux/ubuntu-24.04/casper/vmlinuz",
    "linux/ubuntu-24.04/casper/initrd",
    "linux/ubuntu-24.04/casper/filesystem.squashfs",
]:
    path = api.IMAGES_DIR / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synaboot-smoke")

api.scan_images()
conn = api.connect_db()
now = 2_000_000_000
for index in range(2):
    conn.execute(
        """
        INSERT INTO client_sessions (
            session_id, session_token_hash, mac, ip, uuid, serial, asset, manufacturer, product, platform,
            buildarch, state, selected_target, selected_label, first_seen_at, last_seen_at, expires_at, evidence
        ) VALUES (?, ?, ?, ?, ?, '', '', '', '', 'efi', 'x86_64', 'waiting_assignment', '', '', ?, ?, ?, '{}')
        """,
        (
            f"session-{index}",
            api.hash_session_token(f"session-token-{index}"),
            f"52:54:00:00:00:0{index}",
            f"10.101.8.14{index}",
            f"uuid-{index}",
            now,
            now,
            now + 900,
        ),
    )
conn.execute(
    """
    INSERT INTO client_sessions (
        session_id, session_token_hash, mac, ip, uuid, serial, asset, manufacturer, product, platform,
        buildarch, state, selected_target, selected_label, first_seen_at, last_seen_at, expires_at, evidence
    ) VALUES (?, ?, ?, ?, ?, '', '', '', '', 'efi', 'x86_64', 'waiting_assignment', '', '', ?, ?, ?, '{}')
    """,
    (
        "session-rollback",
        api.hash_session_token("session-token-rollback"),
        "52:54:00:00:00:99",
        "10.101.8.199",
        "uuid-rollback",
        now,
        now,
        now + 900,
    ),
)
for session_id, mac, ip, uuid in [
    ("session-windows-os", "52:54:00:00:00:88", "10.101.8.188", "uuid-windows-os"),
    ("session-windows-software", "52:54:00:00:00:77", "10.101.8.177", "uuid-windows-software"),
    ("session-profile-guard", "52:54:00:00:00:66", "10.101.8.166", "uuid-profile-guard"),
    ("session-package-guard", "52:54:00:00:00:55", "10.101.8.155", "uuid-package-guard"),
    ("session-windows-direct", "52:54:00:00:00:54", "10.101.8.154", "uuid-windows-direct"),
    ("session-windows-feishu", "52:54:00:00:00:53", "10.101.8.153", "uuid-windows-feishu"),
    ("session-combined-guard", "52:54:00:00:00:44", "10.101.8.144", "uuid-combined-guard"),
    ("session-http-guard", "52:54:00:00:00:33", "10.101.8.133", "uuid-http-guard"),
    ("session-failure-guard", "52:54:00:00:00:22", "10.101.8.122", "uuid-failure-guard"),
]:
    conn.execute(
        """
        INSERT INTO client_sessions (
            session_id, session_token_hash, mac, ip, uuid, serial, asset, manufacturer, product, platform,
            buildarch, state, selected_target, selected_label, first_seen_at, last_seen_at, expires_at, evidence
        ) VALUES (?, ?, ?, ?, ?, '', '', '', '', 'efi', 'x86_64', 'waiting_assignment', '', '', ?, ?, ?, '{}')
        """,
        (
            session_id,
            api.hash_session_token(f"{session_id}-token"),
            mac,
            ip,
            uuid,
            now,
            now,
            now + 900,
        ),
    )
conn.execute(
    """
    UPDATE software_variants
    SET review_status='approved',
        signature_policy='vendor_signed',
        download_url='https://example.com/chrome.msi',
        official_source_url='https://example.com/chrome',
        install_action='msi_install',
        enabled=1
    WHERE id='chrome-windows-x64'
    """
)
conn.execute(
    """
    UPDATE software_variants
    SET review_status='approved',
        signature_policy='vendor_signed',
        download_url='https://go.microsoft.com/fwlink/?linkid=2243204',
        official_source_url='https://learn.microsoft.com/deployoffice/overview-office-deployment-tool',
        install_action='office_odt_install',
        installer_type='office_odt',
        package_name='ProPlus2021Volume',
        enabled=1
    WHERE id='office-windows-odt'
    """
)
conn.commit()
conn.close()

try:
    api.update_software_variant(
        "winscp-windows-x64",
        {
            "review_status": "approved",
            "enabled": True,
            "signature_policy": "vendor_signed",
            "download_url": "https://example.com/WinSCP-Setup.exe",
            "official_source_url": "https://winscp.net/eng/download.php",
            "install_action": "exe_install",
            "installer_type": "exe",
            "silent_args": "",
        },
    )
except ValueError as cause:
    if "silent_args_required_for_exe_install" not in str(cause):
        raise
else:
    raise SystemExit("BLOCKED: Windows EXE without silent args was accepted")
winscp_review = api.update_software_variant(
    "winscp-windows-x64",
    {
        "review_status": "approved",
        "enabled": True,
        "signature_policy": "vendor_signed",
        "download_url": "https://example.com/WinSCP-Setup.exe",
        "official_source_url": "https://winscp.net/eng/download.php",
        "install_action": "exe_install",
        "installer_type": "exe",
        "silent_args": "/VERYSILENT /ALLUSERS /NORESTART",
        "selection_priority": 5,
    },
)
if not winscp_review["assignable"]:
    raise SystemExit(f"BLOCKED: reviewed Windows EXE silent installer should become assignable: {winscp_review}")

api.create_software_package(
    {
        "id": "corp-tool",
        "name": "Corp Tool",
        "vendor": "Admin reviewed",
        "category": "运维",
        "description": "Windows 管理员审核直链安装器样例。",
        "homepage_url": "https://downloads.example.com/corp-tool",
        "icon_key": "package",
    }
)
custom_windows_variant = api.create_software_variant(
    "corp-tool",
    {
        "id": "corp-tool-windows-x64",
        "os_family": "windows",
        "installer_type": "exe",
        "official_source_url": "",
        "download_url": "https://downloads.example.com/corp-tool-setup.exe",
        "source_policy": "admin_reviewed_download",
        "signature_policy": "vendor_signed",
        "install_action": "exe_install",
        "silent_args": "/S /norestart",
        "risk_level": "medium",
    },
)
if custom_windows_variant["assignable"] or "review_required" not in custom_windows_variant["blocked_reasons"]:
    raise SystemExit(f"BLOCKED: admin-reviewed Windows direct installer should require review first: {custom_windows_variant}")
custom_windows_variant = api.update_software_variant(
    "corp-tool-windows-x64",
    {"review_status": "approved", "enabled": True},
)
if not custom_windows_variant["assignable"]:
    raise SystemExit(f"BLOCKED: approved admin-reviewed Windows direct installer should become assignable: {custom_windows_variant}")

try:
    api.update_software_variant("chrome-ubuntu-amd64", {"download_url": f"https://{api.SERVER_IP}/images/chrome.deb"})
except ValueError as cause:
    if "third_party_binary_must_not_be_hosted_by_synaboot" not in str(cause):
        raise
else:
    raise SystemExit("BLOCKED: software variant update accepted a SynaBoot-hosted installer URL")

try:
    api.update_software_variant("chrome-ubuntu-amd64", {"official_source_url": f"https://{api.SERVER_IP}/boot/fake-vendor"})
except ValueError as cause:
    if "official_source_url_must_not_be_hosted_by_synaboot" not in str(cause):
        raise
else:
    raise SystemExit("BLOCKED: software variant update accepted a SynaBoot-hosted official source URL")

target = next(item["target"] for item in api.boot_target_catalog() if item["kind"] == "linux")
windows_target = next(item["target"] for item in api.boot_target_catalog() if item["kind"] == "windows")

created_package = api.create_software_package(
    {
        "id": "htop",
        "name": "htop",
        "vendor": "Ubuntu archive",
        "category": "运维",
        "description": "交互式进程查看工具。",
        "homepage_url": "https://packages.ubuntu.com/search?keywords=htop",
        "icon_key": "terminal",
    }
)
if created_package["id"] != "htop" or created_package["variants"]:
    raise SystemExit(f"BLOCKED: software package metadata create failed: {created_package}")

try:
    api.create_software_variant(
        "htop",
        {
            "id": "htop-ubuntu-apt-blocked",
            "os_family": "ubuntu",
            "installer_type": "apt",
            "official_source_url": f"https://{api.SERVER_IP}/images/htop",
            "download_url": "https://packages.ubuntu.com/search?keywords=htop",
            "source_policy": "official_package_repo",
            "signature_policy": "repo_signed",
            "install_action": "apt_package",
            "package_name": "htop",
        },
    )
except ValueError as cause:
    if "official_source_url_must_not_be_hosted_by_synaboot" not in str(cause):
        raise
else:
    raise SystemExit("BLOCKED: software variant create accepted a SynaBoot-hosted official source URL")

created_variant = api.create_software_variant(
    "htop",
    {
        "id": "htop-ubuntu-apt",
        "os_family": "ubuntu",
        "installer_type": "apt",
        "official_source_url": "https://packages.ubuntu.com/search?keywords=htop",
        "download_url": "",
        "source_policy": "official_package_repo",
        "signature_policy": "repo_signed",
        "install_action": "apt_package",
        "package_name": "htop",
        "risk_level": "low",
    },
)
if created_variant["assignable"] or "review_required" not in created_variant["blocked_reasons"]:
    raise SystemExit("BLOCKED: newly created software variant should require review before assignment")
try:
    api.resolve_software_plan(["htop-ubuntu-apt"], target)
except ValueError as cause:
    if "software_variant_not_approved:htop-ubuntu-apt" not in str(cause):
        raise
else:
    raise SystemExit("BLOCKED: unapproved newly created software variant entered assignment plan")

approved_created_variant = api.update_software_variant("htop-ubuntu-apt", {"review_status": "approved", "enabled": True})
if not approved_created_variant["assignable"] or "download_url_must_be_https" in approved_created_variant["blocked_reasons"]:
    raise SystemExit(f"BLOCKED: reviewed created apt variant should become assignable: {approved_created_variant}")
archived_package = api.update_software_package_status("htop", "archived")
if archived_package["status"] != "archived":
    raise SystemExit(f"BLOCKED: software package archive did not persist: {archived_package}")
if any(package["id"] == "htop" for package in api.list_software_packages(os_family="ubuntu", include_blocked=False)):
    raise SystemExit("BLOCKED: archived software package remained assignable in package catalog")
try:
    api.resolve_software_plan([], target, package_ids=["htop"])
except ValueError as cause:
    if "software_package_no_assignable_variant:htop:ubuntu" not in str(cause):
        raise
else:
    raise SystemExit("BLOCKED: archived software package entered assignment plan")
restored_package = api.update_software_package_status("htop", "available")
if restored_package["status"] != "available":
    raise SystemExit(f"BLOCKED: software package restore did not persist: {restored_package}")

try:
    api.create_software_profile(
        {
            "id": "ubuntu-invalid-tools",
            "name": "Ubuntu 无效集合",
            "description": "应拒绝未审核或不可分配的软件版本。",
            "os_family": "ubuntu",
            "variant_ids": ["vscode-ubuntu-amd64"],
            "risk_level": "medium",
        }
    )
except ValueError as cause:
    if "software_variant_not_assignable:vscode-ubuntu-amd64" not in str(cause):
        raise
else:
    raise SystemExit("BLOCKED: software profile accepted an unassignable variant")

created_profile = api.create_software_profile(
    {
        "id": "ubuntu-ops-tools",
        "name": "Ubuntu 运维工具",
        "description": "使用 Ubuntu 官方仓库安装基础运维工具。",
        "os_family": "ubuntu",
        "variant_ids": ["curl-ubuntu-apt", "htop-ubuntu-apt"],
        "risk_level": "low",
    }
)
if not created_profile["assignable"] or created_profile["variant_ids"] != ["curl-ubuntu-apt", "htop-ubuntu-apt"]:
    raise SystemExit(f"BLOCKED: reviewed software profile should be assignable: {created_profile}")
api.update_software_package_status("htop", "archived")
profile_after_package_archive = next(profile for profile in api.list_software_profiles(os_family="ubuntu") if profile["id"] == "ubuntu-ops-tools")
if profile_after_package_archive["assignable"]:
    raise SystemExit("BLOCKED: software profile stayed assignable while one referenced application was archived")
if any(profile["id"] == "ubuntu-ops-tools" for profile in api.compatible_software_profiles_for_target({"target": target, "software_assignment_enabled": True})):
    raise SystemExit("BLOCKED: profile with archived application remained compatible for assignment")
try:
    api.resolve_software_plan(["htop-ubuntu-apt"], target)
except ValueError as cause:
    if "package_archived" not in str(cause):
        raise
else:
    raise SystemExit("BLOCKED: explicit variant id bypassed archived software package")
try:
    api.resolve_software_plan([], target, profile_ids=["ubuntu-ops-tools"])
except ValueError as cause:
    if "software_profile_not_assignable:ubuntu-ops-tools" not in str(cause):
        raise
else:
    raise SystemExit("BLOCKED: software profile with archived package entered assignment plan")
api.update_software_package_status("htop", "available")
profile_after_package_restore = next(profile for profile in api.list_software_profiles(os_family="ubuntu") if profile["id"] == "ubuntu-ops-tools")
if not profile_after_package_restore["assignable"]:
    raise SystemExit("BLOCKED: software profile did not become assignable after referenced application restore")
archived_profile = api.update_software_profile_status("ubuntu-ops-tools", "archived")
if archived_profile["assignable"] or archived_profile["status"] != "archived":
    raise SystemExit(f"BLOCKED: archived software profile should not be assignable: {archived_profile}")
if any(profile["id"] == "ubuntu-ops-tools" for profile in api.compatible_software_profiles_for_target({"target": target, "software_assignment_enabled": True})):
    raise SystemExit("BLOCKED: archived software profile remained compatible for assignment")
restored_profile = api.update_software_profile_status("ubuntu-ops-tools", "available")
if not restored_profile["assignable"] or restored_profile["status"] != "available":
    raise SystemExit(f"BLOCKED: restored software profile should be assignable: {restored_profile}")

feishu_review = api.get_software_variant("feishu-ubuntu-amd64")
if not feishu_review or not feishu_review["assignable"] or feishu_review.get("install_action") != "download_deb":
    raise SystemExit(f"BLOCKED: configured Feishu Ubuntu deb variant should be assignable: {feishu_review}")

os.environ.pop("SYNABOOT_FEISHU_UBUNTU_DEB_URL", None)
conn = api.connect_db()
conn.execute(
    """
    UPDATE software_variants
    SET download_url = 'https://lf9-ug-sign.feishucdn.com/ee-appcenter/test/Feishu-linux_x64-test.deb?signature=test',
        installer_type = 'deb',
        install_action = 'official_download',
        install_command_template = '',
        review_status = 'approved',
        enabled = 1
    WHERE id = 'feishu-ubuntu-amd64'
    """
)
conn.commit()
api.ensure_software_catalog(conn)
conn.close()
manual_feishu_review = api.get_software_variant("feishu-ubuntu-amd64")
if (
    not manual_feishu_review
    or not manual_feishu_review["assignable"]
    or manual_feishu_review.get("install_action") != "download_deb"
    or manual_feishu_review.get("install_command_template") != "apt_install_downloaded_deb"
):
    raise SystemExit(f"BLOCKED: manually maintained Feishu deb URL did not migrate to assignable download_deb: {manual_feishu_review}")
print("INFO: feishu_manual_deb_migration=ok")

api.create_software_package(
    {
        "id": "official-link-demo",
        "name": "官方链接演示",
        "vendor": "Example Vendor",
        "category": "协作",
        "description": "用于验证软件市场只保存官方来源链接和受控安装元数据。",
        "homepage_url": "https://example.com/official-link-demo",
        "icon_key": "official-link-demo",
    }
)
official_link_variant = api.create_software_variant(
    "official-link-demo",
    {
        "id": "official-link-demo-ubuntu",
        "os_family": "ubuntu",
        "installer_type": "installer",
        "official_source_url": "https://example.com/official-link-demo",
        "download_url": "https://example.com/official-link-demo",
        "source_policy": "official_vendor",
        "signature_policy": "vendor_signed",
        "install_action": "official_download",
        "risk_level": "low",
    },
)
official_link_variant = api.update_software_variant(
    "official-link-demo-ubuntu",
    {"review_status": "approved", "enabled": True},
)
if official_link_variant["assignable"] or "runner_action_not_ready" not in official_link_variant["blocked_reasons"]:
    raise SystemExit("BLOCKED: official-download-only software became assignable")
official_deb_variant = api.update_software_variant(
    "official-link-demo-ubuntu",
    {
        "install_action": "download_deb",
        "installer_type": "deb",
        "download_url": "https://example.com/official-link-demo.deb",
        "silent_args": "",
        "review_status": "approved",
        "enabled": True,
    },
)
if not official_deb_variant["assignable"]:
    raise SystemExit(f"BLOCKED: controlled official deb metadata update did not become assignable: {official_deb_variant}")
demo_plan = api.resolve_software_plan([], target, package_ids=["official-link-demo"])
if [variant["id"] for variant in demo_plan.get("variants", [])] != ["official-link-demo-ubuntu"]:
    raise SystemExit(f"BLOCKED: updated official deb variant did not resolve through package selection: {demo_plan}")
api.update_software_package_status("official-link-demo", "archived")
print("INFO: software_variant_execution_metadata_update=ok")

chrome_review = api.update_software_variant(
    "chrome-ubuntu-amd64",
    {
        "review_status": "approved",
        "signature_policy": "vendor_signed",
        "download_url": "https://example.com/chrome.deb",
        "official_source_url": "https://example.com/chrome",
        "default_for_os": True,
        "selection_priority": 10,
        "enabled": True,
    },
)
if not chrome_review["assignable"]:
    raise SystemExit(f"BLOCKED: approved Ubuntu deb variant is not assignable: {chrome_review['blocked_reasons']}")
created_chrome_variant = api.create_software_variant(
    "chrome",
    {
        "id": "chrome-ubuntu-default-apt",
        "os_family": "ubuntu",
        "installer_type": "apt",
        "official_source_url": "https://example.com/chrome-apt",
        "download_url": "",
        "source_policy": "official_package_repo",
        "signature_policy": "repo_signed",
        "install_action": "apt_package",
        "package_name": "google-chrome-stable",
        "default_for_os": True,
        "selection_priority": 50,
        "risk_level": "low",
    },
)
if created_chrome_variant["assignable"] or "review_required" not in created_chrome_variant["blocked_reasons"]:
    raise SystemExit("BLOCKED: newly created default Chrome variant should require review before assignment")
chrome_default_review = api.update_software_variant(
    "chrome-ubuntu-default-apt",
    {
        "review_status": "approved",
        "enabled": True,
        "default_for_os": True,
        "selection_priority": 50,
    },
)
if chrome_default_review["assignable"] or "apt_repo_not_supported" not in chrome_default_review["blocked_reasons"]:
    raise SystemExit(f"BLOCKED: external apt repo variant must not be assignable until repo setup is implemented: {chrome_default_review}")
if not chrome_default_review["default_for_os"]:
    raise SystemExit(f"BLOCKED: reviewed external apt repo variant should still preserve default metadata: {chrome_default_review}")
old_chrome = api.get_software_variant("chrome-ubuntu-amd64")
if old_chrome["default_for_os"]:
    raise SystemExit("BLOCKED: setting a new default did not clear previous Chrome Ubuntu default")

curl_variant = api.get_software_variant("curl-ubuntu-apt")
if not curl_variant or not curl_variant["assignable"] or curl_variant.get("package_name") != "curl":
    raise SystemExit(f"BLOCKED: default Ubuntu apt package variant is not assignable: {curl_variant}")
profiles = api.list_software_profiles(os_family="ubuntu")
ubuntu_profile = next((profile for profile in profiles if profile["id"] == "ubuntu-basic-tools"), None)
if not ubuntu_profile or not ubuntu_profile["assignable"] or ubuntu_profile.get("variant_ids") != ["curl-ubuntu-apt"]:
    raise SystemExit(f"BLOCKED: default Ubuntu software profile is not assignable: {ubuntu_profile}")
if not any(profile["id"] == "ubuntu-ops-tools" and profile["assignable"] for profile in profiles):
    raise SystemExit("BLOCKED: custom software profile was not listed as assignable")

options = api.assignment_options(["session-0", "session-1"])
if not options or len(options["sessions"]) != 2:
    raise SystemExit("BLOCKED: assignment_options did not return both sessions")
windows_option = next(item for item in options["boot_targets"] if item["kind"] == "windows")
if windows_option.get("software_assignment_enabled") is not True:
    raise SystemExit("BLOCKED: Windows target should expose software assignment through SetupComplete helper")
if windows_option.get("postinstall_status") != "setupcomplete_helper_ready":
    raise SystemExit(f"BLOCKED: Windows target did not advertise SetupComplete helper readiness: {windows_option}")
install_presets_by_target = options.get("install_presets_by_target") or {}
windows_presets = install_presets_by_target.get(windows_target) or []
default_windows_preset = next((item for item in windows_presets if item.get("id") == "windows-office-standard"), None)
if not default_windows_preset:
    raise SystemExit(f"BLOCKED: assignment options did not expose the default Windows Office install preset: {windows_presets}")
if "microsoft-office" not in default_windows_preset.get("software_package_ids", []):
    raise SystemExit(f"BLOCKED: Windows standard preset did not include Office package: {default_windows_preset}")
custom_preset = api.create_install_preset(
    {
        "id": "windows-winscp-standard",
        "name": "Windows WinSCP 标准预设",
        "description": "Windows 安装后自动安装 WinSCP 和默认 Office。",
        "os_family": "windows",
        "boot_target": windows_target,
        "software_package_ids": ["winscp"],
        "software_profile_ids": [],
        "settings": {"schema_version": "synaboot.install-preset-settings.v1"},
    }
)
if not custom_preset["assignable"] or custom_preset.get("software_package_ids") != ["winscp"]:
    raise SystemExit(f"BLOCKED: custom Windows install preset should be assignable: {custom_preset}")
archived_preset = api.update_install_preset_status("windows-winscp-standard", "archived")
if not archived_preset or archived_preset["assignable"] or archived_preset["status"] != "archived":
    raise SystemExit(f"BLOCKED: archived install preset should not be assignable: {archived_preset}")
restored_preset = api.update_install_preset_status("windows-winscp-standard", "available")
if not restored_preset or not restored_preset["assignable"] or restored_preset["status"] != "available":
    raise SystemExit(f"BLOCKED: restored install preset should be assignable: {restored_preset}")
software_by_target = options.get("compatible_software_by_target") or {}
windows_target_packages = software_by_target.get(windows_target) or []
windows_target_variants = [variant for package in windows_target_packages for variant in package.get("variants", [])]
if not any(variant.get("id") == "chrome-windows-x64" for variant in windows_target_variants):
    raise SystemExit("BLOCKED: Windows target did not expose approved MSI software")
feishu_windows_variant = next((variant for variant in windows_target_variants if variant.get("id") == "feishu-windows-x64"), None)
if not feishu_windows_variant:
    raise SystemExit("BLOCKED: Windows target did not expose Feishu MSI software")
if feishu_windows_variant.get("install_action") != "msi_install" or feishu_windows_variant.get("installer_type") != "msi":
    raise SystemExit(f"BLOCKED: Feishu Windows variant must use MSI install action: {feishu_windows_variant}")
if feishu_windows_variant.get("download_url") != "https://sf3-cn.feishucdn.com/obj/hera-cn/download/Feishu-win32_x64-7.68.6-signed.msi":
    raise SystemExit(f"BLOCKED: Feishu Windows MSI URL mismatch: {feishu_windows_variant}")
if not any(variant.get("id") == "winscp-windows-x64" for variant in windows_target_variants):
    raise SystemExit("BLOCKED: Windows target did not expose approved EXE silent software")
if not any(variant.get("id") == "corp-tool-windows-x64" for variant in windows_target_variants):
    raise SystemExit("BLOCKED: Windows target did not expose admin-reviewed direct installer software")
if not any(variant.get("id") == "office-windows-odt" for variant in windows_target_variants):
    raise SystemExit("BLOCKED: Windows target did not expose approved Office ODT software")
profiles_by_target = options.get("compatible_software_profiles_by_target") or {}
ubuntu_target_packages = software_by_target.get(target) or []
ubuntu_target_variants = [variant for package in ubuntu_target_packages for variant in package.get("variants", [])]
if not ubuntu_target_variants:
    raise SystemExit("BLOCKED: Ubuntu target did not expose compatible assignable software")
if any(not variant.get("assignable") for variant in ubuntu_target_variants):
    raise SystemExit("BLOCKED: assignment options exposed unassignable software variant")
if any(variant.get("os_family") != "ubuntu" for variant in ubuntu_target_variants):
    raise SystemExit("BLOCKED: assignment options exposed a non-Ubuntu software variant for Ubuntu target")
if not any(variant.get("id") == "feishu-ubuntu-amd64" for variant in ubuntu_target_variants):
    raise SystemExit("BLOCKED: assignment options did not expose configured Feishu Ubuntu deb variant")
if not any(variant.get("id") == "curl-ubuntu-apt" for variant in ubuntu_target_variants):
    raise SystemExit("BLOCKED: assignment options did not expose default curl apt variant for Ubuntu target")
if any(variant.get("id") == "chrome-ubuntu-default-apt" for variant in ubuntu_target_variants):
    raise SystemExit("BLOCKED: assignment options exposed external apt repo variant before repo setup is implemented")
ubuntu_target_profiles = profiles_by_target.get(target) or []
if not any(profile.get("id") == "ubuntu-basic-tools" and profile.get("assignable") for profile in ubuntu_target_profiles):
    raise SystemExit("BLOCKED: assignment options did not expose default Ubuntu software profile for Ubuntu target")
if any(profile.get("os_family") != "ubuntu" or not profile.get("assignable") for profile in ubuntu_target_profiles):
    raise SystemExit("BLOCKED: assignment options exposed incompatible or unassignable software profile for Ubuntu target")

assignment = api.create_deployment_assignment(
    {
        "session_ids": ["session-0", "session-1"],
        "boot_target": target,
        "software_variant_ids": ["curl-ubuntu-apt"],
        "software_profile_ids": [],
    }
)
if not assignment or len(assignment["sessions"]) != 2:
    raise SystemExit("BLOCKED: batch deployment assignment was not created")

plan = assignment["resolved_software_plan"]
if plan.get("third_party_binary_stored") is not False:
    raise SystemExit("BLOCKED: software plan must not store third-party binaries")
if plan.get("client_downloads_from_official_source") is not True:
    raise SystemExit("BLOCKED: client must download software from official source")
if plan["variants"][0]["install_action"] != "apt_package" or plan["variants"][0]["package_name"] != "curl":
    raise SystemExit("BLOCKED: persisted software plan lost default apt package action")

postinstall_event_token = ""
boot_tokens = {}
for session_id in ["session-0", "session-1"]:
    latest = api.latest_assignment_for_session(session_id)
    if not latest or latest["id"] != assignment["id"]:
        raise SystemExit(f"BLOCKED: latest assignment missing for {session_id}")
    boot_token = api.issue_assignment_boot_token(assignment["id"], session_id, f"session-token-{session_id[-1]}")
    script = api.assigned_boot_script(target, assignment["id"], session_id, boot_token)
    if "ds=nocloud-net\\;s=${synaboot-seed-url}" not in script:
        raise SystemExit("BLOCKED: Ubuntu assigned script did not include escaped NoCloud seed")
    if f"nocloud/{session_id}/{boot_token}/" not in script:
        raise SystemExit("BLOCKED: Ubuntu assigned script did not include assignment boot token seed path")
    boot_tokens[session_id] = boot_token
    assignment_for_runner, session = api.verify_postinstall_access(assignment["id"], session_id, boot_token)
    postinstall_plan = api.postinstall_plan_payload(assignment_for_runner, session)
    if postinstall_plan.get("execution_model", {}).get("allowed_install_actions") != ["apt_package", "download_deb"]:
        raise SystemExit(f"BLOCKED: Ubuntu postinstall plan exposed unsupported runner actions: {postinstall_plan}")
    if postinstall_plan["variants"][0]["install_action"] != "apt_package" or postinstall_plan["variants"][0]["package_name"] != "curl":
        raise SystemExit("BLOCKED: postinstall plan did not expose persisted apt package action")
    user_data = api.ubuntu_nocloud_user_data(assignment_for_runner, session, boot_token)
    if "synaboot-postinstall.service" not in user_data:
        raise SystemExit("BLOCKED: Ubuntu NoCloud user-data did not install first-boot service")
    if "while [ \"$attempt\" -le 20 ]" not in user_data or "Restart=on-failure" not in user_data or "RestartSec=30s" not in user_data:
        raise SystemExit("BLOCKED: Ubuntu NoCloud bootstrap must retry transient runner download failures")
    if "StartLimitBurst=20" not in user_data or "StartLimitIntervalSec=15min" not in user_data:
        raise SystemExit("BLOCKED: Ubuntu NoCloud bootstrap retry must be bounded")
    if "rm -f \"$WORK_DIR/runner.sh\"" not in user_data:
        raise SystemExit("BLOCKED: Ubuntu NoCloud bootstrap must remove token-bearing runner after success")
    runner = api.ubuntu_postinstall_runner(assignment_for_runner, session, boot_token)
    if "third_party_binary_stored" not in runner or "raw command" not in runner.lower():
        raise SystemExit("BLOCKED: Ubuntu runner policy guard text missing")
    if "send_event('variant', 'started'" not in runner or "send_event('variant', 'completed'" not in runner or "send_event('variant', 'failed'" not in runner:
        raise SystemExit("BLOCKED: Ubuntu runner did not report per-software variant events")
    if "log_event runner failed" not in runner:
        raise SystemExit("BLOCKED: Ubuntu runner did not report runner failure events")
    if "handle.read(1024 * 1024)" not in runner or "os.remove(path)" not in runner:
        raise SystemExit("BLOCKED: Ubuntu download_deb runner must stream hash checks and remove temporary deb files")
    if session_id == "session-0":
        postinstall_event_token = boot_token

for target_session, wrong_token in [
    ("session-0", boot_tokens["session-1"]),
    ("session-1", boot_tokens["session-0"]),
]:
    try:
        api.verify_postinstall_access(assignment["id"], target_session, wrong_token)
    except ValueError as cause:
        if "invalid_session_token" not in str(cause):
            raise
    else:
        raise SystemExit("BLOCKED: boot token from one batch session could access another session")

try:
    api.record_postinstall_event(
        assignment["id"],
        {
            "session_id": "session-1",
            "token": boot_tokens["session-0"],
            "stage": "runner",
            "status": "started",
            "message": "cross session token should fail",
        },
    )
except ValueError as cause:
    if "invalid_session_token" not in str(cause):
        raise
else:
    raise SystemExit("BLOCKED: cross-session boot token was accepted for postinstall event")

server = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()
http_base = f"http://127.0.0.1:{server.server_port}"
try:
    plan_url = f"{http_base}/api/postinstall/assignments/{assignment['id']}/plan?session_id=session-0&token={boot_tokens['session-0']}"
    http_plan = json.loads(urllib.request.urlopen(plan_url, timeout=10).read().decode("utf-8"))
    if http_plan["variants"][0]["id"] != "curl-ubuntu-apt" or http_plan["client_downloads_from_official_source"] is not True:
        raise SystemExit(f"BLOCKED: HTTP postinstall plan mismatch: {http_plan}")
    runner_url = f"{http_base}/api/postinstall/assignments/{assignment['id']}/runner.sh?session_id=session-0&token={boot_tokens['session-0']}"
    http_runner = urllib.request.urlopen(runner_url, timeout=10).read().decode("utf-8")
    if "apt-get" not in http_runner or "PLAN_FILE" not in http_runner or "invalid plan policy" not in http_runner:
        raise SystemExit("BLOCKED: HTTP Ubuntu runner did not include plan fetch and policy guards")
    if "send_event('variant', 'started'" not in http_runner or "log_event runner failed" not in http_runner:
        raise SystemExit("BLOCKED: HTTP Ubuntu runner did not include event reporting")
    if "handle.read(1024 * 1024)" not in http_runner or "os.remove(path)" not in http_runner:
        raise SystemExit("BLOCKED: HTTP Ubuntu runner did not clean download_deb temporary files")
    user_data_url = f"{http_base}/api/postinstall/assignments/{assignment['id']}/nocloud/session-0/{boot_tokens['session-0']}/user-data"
    http_user_data = urllib.request.urlopen(user_data_url, timeout=10).read().decode("utf-8")
    if "synaboot-postinstall.service" not in http_user_data or "/runner.sh?session_id=session-0" not in http_user_data:
        raise SystemExit("BLOCKED: HTTP NoCloud user-data did not reference the per-session runner")
    if "while [ \"$attempt\" -le 20 ]" not in http_user_data or "Restart=on-failure" not in http_user_data or "RestartSec=30s" not in http_user_data:
        raise SystemExit("BLOCKED: HTTP NoCloud user-data did not include bounded runner download retry")
    if "StartLimitBurst=20" not in http_user_data or "StartLimitIntervalSec=15min" not in http_user_data:
        raise SystemExit("BLOCKED: HTTP NoCloud user-data did not bound service retries")
    if "rm -f \"$WORK_DIR/runner.sh\"" not in http_user_data:
        raise SystemExit("BLOCKED: HTTP NoCloud user-data did not remove token-bearing runner after success")
    wrong_plan_url = f"{http_base}/api/postinstall/assignments/{assignment['id']}/plan?session_id=session-1&token={boot_tokens['session-0']}"
    try:
        urllib.request.urlopen(wrong_plan_url, timeout=10).read()
    except urllib.error.HTTPError as cause:
        if cause.code != 403:
            raise
    else:
        raise SystemExit("BLOCKED: HTTP postinstall endpoint accepted a cross-session boot token")
    event_url = f"{http_base}/api/postinstall/assignments/{assignment['id']}/events"
    payload = json.dumps(
        {
            "session_id": "session-0",
            "token": boot_tokens["session-0"],
            "stage": "runner",
            "status": "started",
            "message": "HTTP runner event",
            "payload": {"variant_id": "curl-ubuntu-apt"},
        }
    ).encode("utf-8")
    request = urllib.request.Request(event_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    http_event = json.loads(urllib.request.urlopen(request, timeout=10).read().decode("utf-8"))
    if http_event.get("payload", {}).get("variant_id") != "curl-ubuntu-apt":
        raise SystemExit(f"BLOCKED: HTTP postinstall event payload mismatch: {http_event}")
finally:
    server.shutdown()
    server.server_close()

api.record_postinstall_event(
    assignment["id"],
    {
        "session_id": "session-0",
        "token": postinstall_event_token,
        "stage": "runner",
        "status": "started",
        "message": "Ubuntu postinstall runner started",
    },
)
api.record_postinstall_event(
    assignment["id"],
    {
        "session_id": "session-0",
        "token": postinstall_event_token,
        "stage": "variant",
        "status": "completed",
        "message": "curl variant completed before runner finished",
        "payload": {"variant_id": "curl-ubuntu-apt", "duration_seconds": 6},
    },
)
listed_assignment_before_runner_done = next(item for item in api.list_deployment_assignments() if item["id"] == assignment["id"])
if listed_assignment_before_runner_done["status"] == "postinstall_completed":
    raise SystemExit("BLOCKED: variant completed event must not mark entire assignment completed")
if listed_assignment_before_runner_done["event_summary"]["last_status"] != "completed":
    raise SystemExit("BLOCKED: variant completed event should remain visible in event summary")
api.record_postinstall_event(
    assignment["id"],
    {
        "session_id": "session-0",
        "token": postinstall_event_token,
        "stage": "runner",
        "status": "completed",
        "message": "Ubuntu postinstall runner completed",
        "payload": {"variant_id": "curl-ubuntu-apt", "duration_seconds": 12},
    },
)

listed_assignment = next(item for item in api.list_deployment_assignments() if item["id"] == assignment["id"])
if listed_assignment["event_summary"]["last_status"] != "completed":
    raise SystemExit("BLOCKED: deployment assignment list did not expose completed postinstall status")
if not listed_assignment["recent_events"] or listed_assignment["recent_events"][0]["payload"].get("variant_id") != "curl-ubuntu-apt":
    raise SystemExit("BLOCKED: deployment assignment list did not expose recent postinstall event payload")
client_sessions = api.list_client_sessions(include_private=True)["sessions"]
session_summary = next(item for item in client_sessions if item["session_id"] == "session-0")
latest_assignment = session_summary.get("latest_assignment") or {}
if latest_assignment.get("id") != assignment["id"]:
    raise SystemExit("BLOCKED: client session did not expose latest deployment assignment")
if latest_assignment.get("software_labels") != ["curl"]:
    raise SystemExit("BLOCKED: client session did not expose selected software labels")
if latest_assignment.get("event_summary", {}).get("last_status") != "completed":
    raise SystemExit("BLOCKED: client session did not expose latest postinstall event status")
session_one_summary = next(item for item in client_sessions if item["session_id"] == "session-1")
session_one_latest = session_one_summary.get("latest_assignment") or {}
if session_one_latest.get("id") != assignment["id"]:
    raise SystemExit("BLOCKED: second batch client session did not expose latest deployment assignment")
if session_one_latest.get("event_summary", {}).get("last_status"):
    raise SystemExit("BLOCKED: client session leaked another session's postinstall event status")
if session_one_latest.get("session_event_summary", {}).get("last_status"):
    raise SystemExit("BLOCKED: client session leaked another session's postinstall session_event_summary")

server = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()
http_base = f"http://127.0.0.1:{server.server_port}"
try:
    wait_url = f"{http_base}/api/ipxe/wait?session_id=session-0&token=session-token-0"
    wait_script = urllib.request.urlopen(wait_url, timeout=10).read().decode("utf-8")
    if assignment["id"] not in wait_script or "ds=nocloud-net\\;s=${synaboot-seed-url}" not in wait_script:
        raise SystemExit("BLOCKED: passive wait endpoint did not return assigned Ubuntu NoCloud boot script")
    if "/api/postinstall/assignments/" not in wait_script or "/nocloud/session-0/" not in wait_script:
        raise SystemExit("BLOCKED: passive wait endpoint did not expose per-session postinstall URLs")
    if f"/api/postinstall/assignments/{assignment['id']}/plan?session_id=session-0" not in wait_script:
        raise SystemExit("BLOCKED: passive wait endpoint did not bind the postinstall plan URL to the selected assignment")
    if f"/api/postinstall/assignments/{assignment['id']}/runner.sh?session_id=session-0" not in wait_script:
        raise SystemExit("BLOCKED: passive wait endpoint did not bind the runner URL to the selected assignment")
    if "synaboot-plan-url" not in wait_script or "synaboot-runner-url" not in wait_script:
        raise SystemExit("BLOCKED: passive wait endpoint lost software postinstall boot variables")
    conn = api.connect_db()
    wait_row = conn.execute("SELECT state, selected_target FROM client_sessions WHERE session_id = 'session-0'").fetchone()
    conn.close()
    if wait_row["state"] != "booting" or wait_row["selected_target"] != target:
        raise SystemExit("BLOCKED: passive wait endpoint did not mark assigned client as booting")
finally:
    server.shutdown()
    server.server_close()

rollback_result = api.create_deployment_assignment(
    {
        "session_ids": ["session-rollback", "missing-session"],
        "boot_target": target,
        "software_variant_ids": [],
        "software_profile_ids": [],
    }
)
if rollback_result is not None:
    raise SystemExit("BLOCKED: missing session batch assignment should fail closed")

conn = api.connect_db()
rollback_row = conn.execute(
    "SELECT selected_target, state FROM client_sessions WHERE session_id = 'session-rollback'"
).fetchone()
assignment_count = conn.execute("SELECT COUNT(*) AS count FROM deployment_assignments").fetchone()["count"]
conn.close()
if rollback_row["selected_target"] != "" or rollback_row["state"] != "waiting_assignment":
    raise SystemExit("BLOCKED: failed batch assignment polluted waiting client session")
if assignment_count != 1:
    raise SystemExit(f"BLOCKED: failed rollback path created unexpected assignment count={assignment_count}")

windows_software_assignment = api.create_deployment_assignment(
    {
        "session_ids": ["session-windows-os"],
        "boot_target": windows_target,
        "install_preset_id": "windows-office-standard",
        "software_variant_ids": ["chrome-windows-x64", "office-windows-odt"],
        "software_profile_ids": [],
    }
)
if not windows_software_assignment:
    raise SystemExit("BLOCKED: Windows software assignment should be available through SetupComplete helper")
windows_helper_token = api.issue_assignment_boot_token(
    windows_software_assignment["id"],
    "session-windows-os",
    "session-windows-os-token",
)
windows_helper = api.windows_hotpe_injection_helper_ps1(
    windows_software_assignment,
    api.get_client_session("session-windows-os"),
    windows_helper_token,
)
windows_plan = api.postinstall_plan_payload(windows_software_assignment, api.get_client_session("session-windows-os"))
windows_task_sequence = windows_software_assignment.get("task_sequence_plan", {})
if windows_software_assignment.get("install_preset_id") != "windows-office-standard":
    raise SystemExit(f"BLOCKED: Windows assignment lost install preset id: {windows_software_assignment}")
if "partition_template_id" in windows_software_assignment or "partition_template" in windows_task_sequence:
    raise SystemExit(f"BLOCKED: Windows assignment must not expose partition preset fields: {windows_software_assignment}")
if windows_plan.get("install_preset_id") != "windows-office-standard" or "partition_template_id" in windows_plan:
    raise SystemExit(f"BLOCKED: Windows postinstall plan lost preset id or exposed partition ids: {windows_plan}")
if windows_plan.get("execution_model", {}).get("allowed_install_actions") != ["exe_install", "msi_install", "office_odt_install"]:
    raise SystemExit(f"BLOCKED: Windows postinstall plan exposed unsupported runner actions: {windows_plan}")
if windows_plan.get("activation", {}).get("kms", {}).get("enabled") is not False:
    raise SystemExit(f"BLOCKED: Windows KMS activation must be disabled unless admin configures it: {windows_plan}")
if windows_plan.get("activation", {}).get("kms", {}).get("public_kms_embedded") is not False:
    raise SystemExit("BLOCKED: Windows activation plan must never embed a public KMS host")
os.environ["SYNABOOT_KMS_HOST"] = "kms.example.internal"
os.environ["SYNABOOT_WINDOWS_KMS_ACTIVATE"] = "1"
os.environ["SYNABOOT_OFFICE_KMS_ACTIVATE"] = "1"
kms_enabled_plan = api.postinstall_plan_payload(windows_software_assignment, api.get_client_session("session-windows-os"))
if kms_enabled_plan.get("activation", {}).get("kms", {}).get("host") != "kms.example.internal":
    raise SystemExit(f"BLOCKED: Windows KMS host was not propagated to postinstall plan: {kms_enabled_plan}")
if kms_enabled_plan.get("activation", {}).get("kms", {}).get("windows") is not True or kms_enabled_plan.get("activation", {}).get("kms", {}).get("office") is not True:
    raise SystemExit(f"BLOCKED: Windows/Office KMS activation flags were not propagated: {kms_enabled_plan}")
for key in ["SYNABOOT_KMS_HOST", "SYNABOOT_WINDOWS_KMS_ACTIVATE", "SYNABOOT_OFFICE_KMS_ACTIVATE"]:
    os.environ.pop(key, None)
office_plan_variant = next((variant for variant in windows_plan.get("variants", []) if variant.get("id") == "office-windows-odt"), None)
if not office_plan_variant or office_plan_variant.get("package_name") != "ProPlus2021Volume":
    raise SystemExit(f"BLOCKED: Windows postinstall plan lost Office product id: {windows_plan}")
if "microsoft-office" not in windows_software_assignment.get("software_package_ids", []):
    raise SystemExit(f"BLOCKED: Windows assignment did not auto-include default Office package: {windows_software_assignment}")
if "param(" not in windows_helper or '[string]$WindowsRoot = ""' not in windows_helper:
    raise SystemExit("BLOCKED: Windows HotPE helper must allow explicit WindowsRoot with guarded auto-detect")
if "Multiple Windows directories found" not in windows_helper or "No installed Windows directory was found" not in windows_helper:
    raise SystemExit("BLOCKED: Windows HotPE helper must fail closed on ambiguous or missing Windows roots")
if "SetupComplete.cmd injected" not in windows_helper or "setupcomplete.cmd?session_id=session-windows-os" not in windows_helper:
    raise SystemExit("BLOCKED: Windows HotPE helper did not include SetupComplete injection path")
if any(forbidden in windows_helper.lower() for forbidden in ["diskpart", "format.com", "clear-disk", "initialize-disk"]):
    raise SystemExit("BLOCKED: Windows HotPE helper must not partition or format disks")
windows_runner = api.windows_postinstall_runner(
    windows_software_assignment,
    api.get_client_session("session-windows-os"),
    windows_helper_token,
)
for expected in [
    "Invoke-SynaBootMsiInstall",
    "Invoke-SynaBootExeInstall",
    "Invoke-SynaBootOfficeOdtInstall",
    "Invoke-SynaBootWindowsKmsActivation",
    "Invoke-SynaBootOfficeKmsActivation",
    "Office Deployment Tool",
]:
    if expected not in windows_runner:
        raise SystemExit(f"BLOCKED: Windows runner missing expected Office/KMS support marker: {expected}")
if "Remove-Item -LiteralPath $Installer" not in windows_runner or "Remove-Item -LiteralPath $OdtDir" not in windows_runner:
    raise SystemExit("BLOCKED: Windows runner must remove temporary MSI and ODT files")
if 'Send-SynaBootEvent "variant" "started"' not in windows_runner or 'Send-SynaBootEvent "variant" "completed"' not in windows_runner:
    raise SystemExit("BLOCKED: Windows runner did not report per-software variant events")
if "cscript.exe //nologo $Slmgr /skms" not in windows_runner or "cscript.exe //nologo $Ospp /sethst" not in windows_runner:
    raise SystemExit("BLOCKED: Windows runner did not include legitimate slmgr/ospp KMS activation calls")

windows_default_office_assignment = api.create_deployment_assignment(
    {
        "session_ids": ["session-windows-software"],
        "boot_target": windows_target,
        "software_variant_ids": [],
        "software_profile_ids": [],
    }
)
if not windows_default_office_assignment:
    raise SystemExit("BLOCKED: Windows default Office assignment was not created")
default_office_variants = [variant["id"] for variant in windows_default_office_assignment["resolved_software_plan"].get("variants", [])]
if default_office_variants != ["office-windows-odt"]:
    raise SystemExit(f"BLOCKED: Windows OS assignment should auto-include only default Office variant: {default_office_variants}")

windows_exe_assignment = api.create_deployment_assignment(
    {
        "session_ids": ["session-package-guard"],
        "boot_target": windows_target,
        "software_package_ids": ["winscp"],
        "software_variant_ids": [],
        "software_profile_ids": [],
    }
)
if not windows_exe_assignment:
    raise SystemExit("BLOCKED: Windows EXE package assignment was not created")
windows_exe_variants = [variant["id"] for variant in windows_exe_assignment["resolved_software_plan"].get("variants", [])]
if "winscp-windows-x64" not in windows_exe_variants or "office-windows-odt" not in windows_exe_variants:
    raise SystemExit(f"BLOCKED: Windows EXE assignment should include selected EXE plus default Office: {windows_exe_variants}")
windows_exe_plan = api.postinstall_plan_payload(windows_exe_assignment, api.get_client_session("session-package-guard"))
api.validate_postinstall_plan_for_runner(windows_exe_plan, "windows")

windows_direct_assignment = api.create_deployment_assignment(
    {
        "session_ids": ["session-windows-direct"],
        "boot_target": windows_target,
        "software_package_ids": ["corp-tool"],
        "software_variant_ids": [],
        "software_profile_ids": [],
    }
)
if not windows_direct_assignment:
    raise SystemExit("BLOCKED: Windows admin-reviewed direct installer assignment was not created")
windows_direct_variants = [variant["id"] for variant in windows_direct_assignment["resolved_software_plan"].get("variants", [])]
if "corp-tool-windows-x64" not in windows_direct_variants or "office-windows-odt" not in windows_direct_variants:
    raise SystemExit(f"BLOCKED: Windows admin-reviewed direct installer assignment should include selected EXE plus default Office: {windows_direct_variants}")
windows_direct_plan = api.postinstall_plan_payload(windows_direct_assignment, api.get_client_session("session-windows-direct"))
api.validate_postinstall_plan_for_runner(windows_direct_plan, "windows")
corp_tool_plan_variant = next((variant for variant in windows_direct_plan.get("variants", []) if variant.get("id") == "corp-tool-windows-x64"), None)
if not corp_tool_plan_variant or corp_tool_plan_variant.get("source_policy") != "admin_reviewed_download":
    raise SystemExit(f"BLOCKED: Windows postinstall plan lost admin-reviewed direct download source policy: {windows_direct_plan}")
if corp_tool_plan_variant.get("official_source_url"):
    raise SystemExit(f"BLOCKED: admin-reviewed Windows installer should not require an official source URL: {corp_tool_plan_variant}")

windows_feishu_assignment = api.create_deployment_assignment(
    {
        "session_ids": ["session-windows-feishu"],
        "boot_target": windows_target,
        "software_package_ids": ["feishu"],
        "software_variant_ids": [],
        "software_profile_ids": [],
    }
)
if not windows_feishu_assignment:
    raise SystemExit("BLOCKED: Windows Feishu MSI assignment was not created")
windows_feishu_variants = [variant["id"] for variant in windows_feishu_assignment["resolved_software_plan"].get("variants", [])]
if "feishu-windows-x64" not in windows_feishu_variants or "office-windows-odt" not in windows_feishu_variants:
    raise SystemExit(f"BLOCKED: Windows Feishu assignment should include Feishu MSI plus default Office: {windows_feishu_variants}")
windows_feishu_plan = api.postinstall_plan_payload(windows_feishu_assignment, api.get_client_session("session-windows-feishu"))
api.validate_postinstall_plan_for_runner(windows_feishu_plan, "windows")
feishu_plan_variant = next((variant for variant in windows_feishu_plan.get("variants", []) if variant.get("id") == "feishu-windows-x64"), None)
if not feishu_plan_variant or feishu_plan_variant.get("silent_args") != "/qn /norestart":
    raise SystemExit(f"BLOCKED: Windows Feishu MSI plan lost silent install args: {windows_feishu_plan}")

package_assignment = api.create_deployment_assignment(
    {
        "session_ids": ["session-http-guard"],
        "boot_target": target,
        "software_package_ids": ["chrome"],
        "software_variant_ids": [],
        "software_profile_ids": [],
    }
)
if not package_assignment:
    raise SystemExit("BLOCKED: Ubuntu software package assignment was not created")
package_plan = package_assignment["resolved_software_plan"]
if package_assignment.get("software_package_ids") != ["chrome"]:
    raise SystemExit(f"BLOCKED: assignment lost selected software package ids: {package_assignment}")
if package_assignment.get("software_variant_ids") != []:
    raise SystemExit(f"BLOCKED: package-based assignment should not require frontend variant ids: {package_assignment}")
if package_plan.get("package_ids") != ["chrome"]:
    raise SystemExit(f"BLOCKED: resolved software plan lost selected package id: {package_plan}")
if [variant["id"] for variant in package_plan.get("variants", [])] != ["chrome-ubuntu-amd64"]:
    raise SystemExit(f"BLOCKED: selected app package did not resolve to Ubuntu variant: {package_plan}")
if package_plan["packages"][0].get("selected_variant_id") != "chrome-ubuntu-amd64":
    raise SystemExit(f"BLOCKED: resolved package did not record selected assignable variant: {package_plan}")

conn = api.connect_db()
package_guard_row = conn.execute(
    "SELECT selected_target, state FROM client_sessions WHERE session_id = 'session-http-guard'"
).fetchone()
assignment_count = conn.execute("SELECT COUNT(*) AS count FROM deployment_assignments").fetchone()["count"]
conn.close()
if package_guard_row["selected_target"] != target or package_guard_row["state"] != "assignment_received":
    raise SystemExit("BLOCKED: accepted software package assignment did not update waiting client session")
if assignment_count != 7:
    raise SystemExit(f"BLOCKED: software package assignment created unexpected assignment count={assignment_count}")

profile_assignment = api.create_deployment_assignment(
    {
        "session_ids": ["session-profile-guard"],
        "boot_target": target,
        "software_variant_ids": [],
        "software_profile_ids": ["ubuntu-ops-tools"],
    }
)
if not profile_assignment:
    raise SystemExit("BLOCKED: Ubuntu software profile assignment was not created")
profile_plan = profile_assignment["resolved_software_plan"]
if profile_plan.get("profile_ids") != ["ubuntu-ops-tools"]:
    raise SystemExit(f"BLOCKED: resolved software plan lost profile id: {profile_plan}")
if [variant["id"] for variant in profile_plan.get("variants", [])] != ["curl-ubuntu-apt", "htop-ubuntu-apt"]:
    raise SystemExit(f"BLOCKED: software profile did not expand to selected variants: {profile_plan}")

conn = api.connect_db()
profile_guard_row = conn.execute(
    "SELECT selected_target, state FROM client_sessions WHERE session_id = 'session-profile-guard'"
).fetchone()
assignment_count = conn.execute("SELECT COUNT(*) AS count FROM deployment_assignments").fetchone()["count"]
conn.close()
if profile_guard_row["selected_target"] != target or profile_guard_row["state"] != "assignment_received":
    raise SystemExit("BLOCKED: accepted software profile assignment did not update waiting client session")
if assignment_count != 8:
    raise SystemExit(f"BLOCKED: software profile assignment created unexpected assignment count={assignment_count}")

combined_assignment = api.create_deployment_assignment(
    {
        "session_ids": ["session-combined-guard"],
        "boot_target": target,
        "software_package_ids": ["htop"],
        "software_profile_ids": ["ubuntu-ops-tools"],
        "software_variant_ids": [],
    }
)
if not combined_assignment:
    raise SystemExit("BLOCKED: combined software package/profile assignment was not created")
combined_plan = combined_assignment["resolved_software_plan"]
if combined_plan.get("package_ids") != ["htop"] or combined_plan.get("profile_ids") != ["ubuntu-ops-tools"]:
    raise SystemExit(f"BLOCKED: combined software plan lost package/profile audit ids: {combined_plan}")
if combined_plan["packages"][0].get("selected_variant_id") != "htop-ubuntu-apt":
    raise SystemExit(f"BLOCKED: combined software package did not resolve selected variant: {combined_plan}")
if [variant["id"] for variant in combined_plan.get("variants", [])] != ["htop-ubuntu-apt", "curl-ubuntu-apt"]:
    raise SystemExit(f"BLOCKED: combined software selection did not dedupe package/profile variants: {combined_plan}")

conn = api.connect_db()
combined_guard_row = conn.execute(
    "SELECT selected_target, state FROM client_sessions WHERE session_id = 'session-combined-guard'"
).fetchone()
assignment_count = conn.execute("SELECT COUNT(*) AS count FROM deployment_assignments").fetchone()["count"]
conn.close()
if combined_guard_row["selected_target"] != target or combined_guard_row["state"] != "assignment_received":
    raise SystemExit("BLOCKED: accepted combined software assignment did not update waiting client session")
if assignment_count != 9:
    raise SystemExit(f"BLOCKED: combined software assignment created unexpected assignment count={assignment_count}")

server = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()
http_base = f"http://127.0.0.1:{server.server_port}"
try:
    options_request = urllib.request.Request(
        f"{http_base}/api/assignment-options?session_id=session-http-guard",
        headers={"X-SynaBoot-Admin-Token": "test-admin-token"},
    )
    http_options = json.loads(urllib.request.urlopen(options_request, timeout=10).read().decode("utf-8"))
    if not any(item.get("target") == target for item in http_options.get("boot_targets", [])):
        raise SystemExit("BLOCKED: HTTP assignment options did not expose Ubuntu boot target")
    if not any(package.get("id") == "htop" for package in (http_options.get("compatible_software_by_target", {}).get(target) or [])):
        raise SystemExit("BLOCKED: HTTP assignment options did not expose compatible software package")
    if not any(profile.get("id") == "ubuntu-ops-tools" for profile in (http_options.get("compatible_software_profiles_by_target", {}).get(target) or [])):
        raise SystemExit("BLOCKED: HTTP assignment options did not expose compatible software profile")
    if not any(preset.get("id") == "windows-office-standard" for preset in (http_options.get("install_presets_by_target", {}).get(windows_target) or [])):
        raise SystemExit("BLOCKED: HTTP assignment options did not expose Windows install presets")
    presets_request = urllib.request.Request(
        f"{http_base}/api/install-presets?os_family=windows",
        headers={"X-SynaBoot-Admin-Token": "test-admin-token"},
    )
    http_presets = json.loads(urllib.request.urlopen(presets_request, timeout=10).read().decode("utf-8"))
    if not any(preset.get("id") == "windows-office-standard" for preset in http_presets.get("presets", [])):
        raise SystemExit("BLOCKED: HTTP install preset list did not expose default Windows preset")

    unauth_payload = json.dumps({"session_ids": ["session-http-guard"], "boot_target": target}).encode("utf-8")
    unauth_request = urllib.request.Request(
        f"{http_base}/api/deployment-assignments",
        data=unauth_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(unauth_request, timeout=10).read()
    except urllib.error.HTTPError as cause:
        if cause.code != 403:
            raise
    else:
        raise SystemExit("BLOCKED: HTTP deployment assignment accepted a missing admin token")
    time.sleep(2.1)

    payload = json.dumps(
        {
            "session_ids": ["session-http-guard"],
            "boot_target": target,
            "software_package_ids": ["htop"],
            "software_profile_ids": ["ubuntu-ops-tools"],
            "software_variant_ids": [],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{http_base}/api/deployment-assignments",
        data=payload,
        headers={"Content-Type": "application/json", "X-SynaBoot-Admin-Token": "test-admin-token"},
        method="POST",
    )
    http_assignment = json.loads(urllib.request.urlopen(request, timeout=10).read().decode("utf-8"))
    http_plan = http_assignment.get("resolved_software_plan", {})
    if http_assignment.get("software_package_ids") != ["htop"] or http_assignment.get("software_profile_ids") != ["ubuntu-ops-tools"]:
        raise SystemExit(f"BLOCKED: HTTP assignment response lost selected software ids: {http_assignment}")
    if [variant["id"] for variant in http_plan.get("variants", [])] != ["htop-ubuntu-apt", "curl-ubuntu-apt"]:
        raise SystemExit(f"BLOCKED: HTTP assignment did not resolve and dedupe package/profile software: {http_plan}")
    list_request = urllib.request.Request(
        f"{http_base}/api/deployment-assignments/{http_assignment['id']}",
        headers={"X-SynaBoot-Admin-Token": "test-admin-token"},
    )
    fetched_assignment = json.loads(urllib.request.urlopen(list_request, timeout=10).read().decode("utf-8"))
    if fetched_assignment.get("id") != http_assignment["id"] or fetched_assignment.get("resolved_software_plan", {}).get("package_ids") != ["htop"]:
        raise SystemExit(f"BLOCKED: HTTP fetched assignment did not persist software plan: {fetched_assignment}")
    wait_after_http_url = f"{http_base}/api/ipxe/wait?session_id=session-http-guard&token=session-http-guard-token"
    wait_after_http_script = urllib.request.urlopen(wait_after_http_url, timeout=10).read().decode("utf-8")
    if http_assignment["id"] not in wait_after_http_script:
        raise SystemExit("BLOCKED: passive wait script did not pick up the HTTP-created deployment assignment")
    if "ds=nocloud-net\\;s=${synaboot-seed-url}" not in wait_after_http_script:
        raise SystemExit("BLOCKED: HTTP-created assignment did not return Ubuntu NoCloud boot args")
    if f"/api/postinstall/assignments/{http_assignment['id']}/plan?session_id=session-http-guard" not in wait_after_http_script:
        raise SystemExit("BLOCKED: HTTP-created assignment did not bind the passive client plan URL")
    if f"/api/postinstall/assignments/{http_assignment['id']}/runner.sh?session_id=session-http-guard" not in wait_after_http_script:
        raise SystemExit("BLOCKED: HTTP-created assignment did not bind the passive client runner URL")
finally:
    server.shutdown()
    server.server_close()

conn = api.connect_db()
http_guard_row = conn.execute(
    "SELECT selected_target, state FROM client_sessions WHERE session_id = 'session-http-guard'"
).fetchone()
assignment_count = conn.execute("SELECT COUNT(*) AS count FROM deployment_assignments").fetchone()["count"]
conn.close()
if http_guard_row["selected_target"] != target or http_guard_row["state"] != "booting":
    raise SystemExit("BLOCKED: HTTP software assignment did not advance passive client to booting after wait")
if assignment_count != 10:
    raise SystemExit(f"BLOCKED: HTTP software assignment created unexpected assignment count={assignment_count}")

failed_assignment = api.create_deployment_assignment(
    {
        "session_ids": ["session-failure-guard"],
        "boot_target": target,
        "software_variant_ids": ["curl-ubuntu-apt"],
        "software_profile_ids": [],
    }
)
if not failed_assignment:
    raise SystemExit("BLOCKED: failure guard assignment was not created")
failed_token = api.issue_assignment_boot_token(
    failed_assignment["id"],
    "session-failure-guard",
    "session-failure-guard-token",
)
api.record_postinstall_event(
    failed_assignment["id"],
    {
        "session_id": "session-failure-guard",
        "token": failed_token,
        "stage": "variant",
        "status": "failed",
        "message": "curl variant failed before runner finished",
        "payload": {"variant_id": "curl-ubuntu-apt", "exit_code": 100},
    },
)
failed_mid = api.get_deployment_assignment(failed_assignment["id"])
if failed_mid["status"] == "postinstall_failed":
    raise SystemExit("BLOCKED: variant failed event must not mark entire assignment failed before runner reports failure")
api.record_postinstall_event(
    failed_assignment["id"],
    {
        "session_id": "session-failure-guard",
        "token": failed_token,
        "stage": "runner",
        "status": "failed",
        "message": "Ubuntu postinstall runner failed",
        "payload": {"exit_code": 100, "duration_seconds": 8},
    },
)
failed_listed = api.get_deployment_assignment(failed_assignment["id"])
if failed_listed["status"] != "postinstall_failed":
    raise SystemExit(f"BLOCKED: runner failed event did not mark assignment failed: {failed_listed}")
if failed_listed["event_summary"]["failed"] < 2 or failed_listed["event_summary"]["last_stage"] != "runner":
    raise SystemExit(f"BLOCKED: failure summary did not expose runner failure: {failed_listed['event_summary']}")
failed_client = next(
    item for item in api.list_client_sessions(include_private=True)["sessions"] if item["session_id"] == "session-failure-guard"
)
if failed_client.get("latest_assignment", {}).get("event_summary", {}).get("last_status") != "failed":
    raise SystemExit("BLOCKED: client session did not expose latest failed postinstall status")

print("INFO: software_market_policy=official-source-client-download")
print("INFO: software_catalog_create=ok")
print("INFO: software_variant_review_guard=ok")
print("INFO: software_catalog_archive=ok")
print("INFO: batch_assignment=ok")
print("INFO: assignment_rollback=ok")
print("INFO: ubuntu_nocloud_postinstall=ok")
print("INFO: postinstall_http_endpoints=ok")
print("INFO: postinstall_event_visibility=ok")
print("INFO: passive_wait_assignment_flow=ok")
print("INFO: windows_hotpe_injection_helper=ok")
print("INFO: windows_postinstall_injection_guard=ok")
print("INFO: software_package_selection=ok")
print("INFO: software_profile_expansion=ok")
print("INFO: software_combined_selection=ok")
print("INFO: software_http_assignment=ok")
print("INFO: postinstall_status_mapping=ok")
PY
