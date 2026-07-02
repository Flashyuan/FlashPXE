#!/usr/bin/env python3
import hashlib
import hmac
import ipaddress
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

SERVER_IP = os.environ.get("SERVER_IP", "192.168.1.168")
SYNABOOT_PORT = int(os.environ.get("SYNABOOT_PORT", "18080"))
SYNABOOT_NFS_SERVER = os.environ.get("SYNABOOT_NFS_SERVER", SERVER_IP)
API_HOST = os.environ.get("SYNABOOT_API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("SYNABOOT_API_PORT", "8000"))
ADMIN_TOKEN = os.environ.get("SYNABOOT_ADMIN_TOKEN", "")
DATA_DIR = Path(os.environ.get("SYNABOOT_DATA_DIR", "/app/data")).resolve()
CONFIG_DIR = Path(os.environ.get("SYNABOOT_CONFIG_DIR", "/app/config")).resolve()
IMAGES_DIR = DATA_DIR / "images"
BOOT_DIR = DATA_DIR / "boot"
METADATA_DIR = DATA_DIR / "metadata"
BUILDS_DIR = DATA_DIR / "builds"
LOGS_DIR = DATA_DIR / "logs"
DB_PATH = METADATA_DIR / "synaboot.sqlite3"
LAST_WRITE_BY_CLIENT: dict[str, float] = {}
CAPABILITIES_PATH = CONFIG_DIR / "synaboot" / "capabilities.free.json"
EDITION_CATALOG_PATH = CONFIG_DIR / "synaboot" / "editions.public.json"
ALLOWED_SOFTWARE_SOURCE_POLICIES = {"official_vendor", "official_package_repo", "approved_enterprise_mirror", "admin_reviewed_download"}
ASSIGNABLE_SOFTWARE_REVIEW_STATUSES = {"approved"}
ASSIGNABLE_SIGNATURE_POLICIES = {"vendor_signed", "repo_signed", "sha256_required"}
SOFTWARE_REVIEW_STATUSES = {"needs_review", "approved", "blocked"}
SOFTWARE_RISK_LEVELS = {"low", "medium", "high"}
INSTALL_PRESET_STATUSES = {"available", "archived"}
INSTALL_PRESET_REVIEW_STATUSES = {"approved", "needs_review"}
SOFTWARE_INSTALL_CONTEXTS = {"winpe", "system_first_boot", "user_logon", "linux_first_boot"}
SOFTWARE_RESTART_BEHAVIORS = {"none", "allow", "defer", "requires_confirmation"}
SOFTWARE_INSTALL_LOCATION_POLICIES = {"system_default", "installer_supported_path", "portable_folder", "not_supported"}
POSTINSTALL_EVENT_STAGES = {"plan", "runner", "variant"}
POSTINSTALL_EVENT_STATUSES = {"requested", "started", "completed", "failed", "blocked", "skipped"}
UBUNTU_RUNNER_ACTIONS = {"apt_package", "download_deb"}
WINDOWS_RUNNER_ACTIONS = {"msi_install", "exe_install", "office_odt_install"}
DEFAULT_WINDOWS_SOFTWARE_PACKAGE_IDS = ["microsoft-office"]
UBUNTU_DEFAULT_APT_SOURCE_HOSTS = {"packages.ubuntu.com", "archive.ubuntu.com", "security.ubuntu.com", "ports.ubuntu.com"}
SAFE_APT_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]{0,127}$")
SAFE_OFFICE_PRODUCT_ID_RE = re.compile(r"^[A-Za-z0-9]{3,64}$")
SAFE_KMS_HOST_RE = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$")
SAFE_SOFTWARE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,80}$")
SAFE_SOFTWARE_INSTALLER_TYPE_RE = re.compile(r"^[A-Za-z0-9._+-]{1,40}$")
SAFE_SILENT_ARGS_RE = re.compile(r"^[A-Za-z0-9 ._=/,:;+\-!]*$")
SENSITIVE_EVENT_TEXT_RE = re.compile(
    r"(?i)(token|session_token|password|passwd|secret|api[_-]?key|private[_-]?key|authorization)[A-Za-z0-9._/=: -]*"
)
SAFE_TITLE_RE = re.compile(r"[^A-Za-z0-9._ -]+")
SAFE_IMAGE_REL_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
SAFE_IPXE_TEXT_RE = re.compile(r"[^A-Za-z0-9._/ -]+")

IMAGE_EXTENSIONS = {
    ".iso": "iso",
    ".wim": "wim",
    ".esd": "esd",
    ".efi": "efi",
    ".img": "image",
    ".qcow2": "image",
    ".vhd": "image",
    ".vhdx": "image",
    ".initrd": "initrd",
    ".squashfs": "livefs",
}
SPECIAL_NAMES = {
    "wimboot": "wimboot",
    "bootmgr": "bootmgr",
    "bcd": "bcd",
    "boot.sdi": "boot-sdi",
    "vmlinuz": "linux-kernel",
    "initrd": "initrd",
    "boot.wim": "wim",
}
LOADER_CATALOG = [
    {
        "id": "ipxe-efi",
        "filename": "ipxe.efi",
        "purpose": "UEFI HTTP Boot / UEFI PXE chainload",
        "architecture": "uefi-x64",
        "boot_mode": ["uefi"],
        "transport": ["http", "future-tftp"],
        "source_type": "unknown",
        "source_guidance": "Use an official iPXE prebuilt file for experiments, or a locally audited build with recorded commit and hash.",
        "secure_boot_risk": {"level": "high", "reason": "Unsigned iPXE EFI loaders are commonly blocked by Secure Boot."},
    },
    {
        "id": "snponly-efi",
        "filename": "snponly.efi",
        "purpose": "UEFI PXE chainload using the firmware SNP driver",
        "architecture": "uefi-x64",
        "boot_mode": ["uefi"],
        "transport": ["future-tftp"],
        "source_type": "unknown",
        "source_guidance": "Use a verified iPXE snponly.efi binary from an approved internal source.",
        "secure_boot_risk": {"level": "high", "reason": "Unsigned iPXE EFI loaders are commonly blocked by Secure Boot."},
    },
    {
        "id": "undionly-kpxe",
        "filename": "undionly.kpxe",
        "purpose": "Legacy BIOS PXE chainload using UNDI",
        "architecture": "bios",
        "boot_mode": ["bios"],
        "transport": ["future-tftp"],
        "source_type": "unknown",
        "source_guidance": "Use a verified iPXE undionly.kpxe binary from an approved internal source.",
        "secure_boot_risk": {"level": "not_applicable", "reason": "Legacy BIOS PXE does not use UEFI Secure Boot, but binary provenance still matters."},
    },
    {
        "id": "ipxe-iso",
        "filename": "ipxe.iso",
        "purpose": "Manual iPXE ISO boot media",
        "architecture": "bios-or-uefi",
        "boot_mode": ["bios", "uefi"],
        "transport": ["removable-media"],
        "source_type": "unknown",
        "source_guidance": "Use a verified iPXE ISO from an approved internal source.",
        "secure_boot_risk": {"level": "high", "reason": "Secure Boot behavior depends on firmware and ISO contents."},
    },
]

DEFAULT_SOFTWARE_CATALOG = [
    {
        "id": "feishu",
        "name": "飞书",
        "vendor": "ByteDance",
        "category": "协作",
        "description": "即时沟通、会议、文档与团队协作。",
        "homepage_url": "https://www.feishu.cn/",
        "icon_key": "feishu",
        "status": "available",
        "review_status": "needs_review",
        "variants": [
            {
                "id": "feishu-windows-x64",
                "os_family": "windows",
                "os_version_constraint": "windows_10_or_11",
                "arch": "x86_64",
                "version": "7.68.6",
                "installer_type": "msi",
                "official_source_url": "https://www.feishu.cn/hc/zh-CN/articles/360049067543-%E4%BD%BF%E7%94%A8-msi-%E6%96%87%E4%BB%B6%E6%89%B9%E9%87%8F%E9%83%A8%E7%BD%B2%E9%A3%9E%E4%B9%A6%E5%AE%A2%E6%88%B7%E7%AB%AF",
                "download_url": "https://sf3-cn.feishucdn.com/obj/hera-cn/download/Feishu-win32_x64-7.68.6-signed.msi",
                "source_policy": "admin_reviewed_download",
                "sha256": "",
                "signature_policy": "vendor_signed",
                "install_phase": "windows_first_boot",
                "install_action": "msi_install",
                "install_command_template": "msi_install",
                "silent_args": "/qn /norestart",
                "requires_network": 1,
                "risk_level": "medium",
                "review_status": "approved",
                "enabled": 1,
                "notes": "按飞书官方 MSI 批量部署教程配置；客户端首次启动后直接从飞书 CDN 下载 MSI 并静默安装，SynaBoot 不托管安装包。",
            },
            {
                "id": "feishu-ubuntu-amd64",
                "os_family": "ubuntu",
                "os_version_constraint": ">=22.04",
                "arch": "x86_64",
                "version": "latest",
                "installer_type": "deb",
                "official_source_url": "https://www.feishu.cn/download",
                "download_url": "https://www.feishu.cn/download",
                "source_policy": "official_vendor",
                "sha256": "",
                "signature_policy": "vendor_signed",
                "install_phase": "linux_first_boot",
                "install_action": "official_download",
                "install_command_template": "",
                "silent_args": "",
                "requires_network": 1,
                "risk_level": "medium",
                "review_status": "needs_review",
                "enabled": 1,
                "notes": "Linux 客户端需确认官方 deb 直链、hash 或签名策略后才能自动安装。",
            },
        ],
    },
    {
        "id": "chrome",
        "name": "Google Chrome",
        "vendor": "Google",
        "category": "浏览器",
        "description": "常用浏览器，适合办公与 Web 系统访问。",
        "homepage_url": "https://chromeenterprise.google/download/",
        "icon_key": "chrome",
        "status": "available",
        "review_status": "needs_review",
        "variants": [
            {
                "id": "chrome-windows-x64",
                "os_family": "windows",
                "os_version_constraint": "windows_10_or_11",
                "arch": "x86_64",
                "version": "latest",
                "installer_type": "msi",
                "official_source_url": "https://chromeenterprise.google/download/",
                "download_url": "https://chromeenterprise.google/download/",
                "source_policy": "official_vendor",
                "sha256": "",
                "signature_policy": "vendor_signed",
                "install_phase": "windows_first_boot",
                "install_action": "official_download",
                "install_command_template": "",
                "silent_args": "/qn /norestart",
                "requires_network": 1,
                "risk_level": "medium",
                "review_status": "needs_review",
                "enabled": 1,
                "notes": "Chrome Enterprise MSI 直链和 hash 会随版本变化，需纳入企业审核后启用。",
            },
            {
                "id": "chrome-ubuntu-amd64",
                "os_family": "ubuntu",
                "os_version_constraint": ">=22.04",
                "arch": "x86_64",
                "version": "stable",
                "installer_type": "deb",
                "official_source_url": "https://www.google.com/chrome/",
                "download_url": "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb",
                "source_policy": "official_vendor",
                "sha256": "",
                "signature_policy": "vendor_signed",
                "install_phase": "linux_first_boot",
                "install_action": "download_deb",
                "install_command_template": "apt_install_downloaded_deb",
                "silent_args": "",
                "requires_network": 1,
                "risk_level": "medium",
                "review_status": "needs_review",
                "enabled": 1,
                "notes": "官方 deb 会配置 Google 软件源；需补 hash 或签名验证流程后启用自动安装。",
            },
        ],
    },
    {
        "id": "vscode",
        "name": "Visual Studio Code",
        "vendor": "Microsoft",
        "category": "开发工具",
        "description": "轻量代码编辑器和脚本维护工具。",
        "homepage_url": "https://code.visualstudio.com/download",
        "icon_key": "vscode",
        "status": "available",
        "review_status": "needs_review",
        "variants": [
            {
                "id": "vscode-windows-x64",
                "os_family": "windows",
                "os_version_constraint": "windows_10_or_11",
                "arch": "x86_64",
                "version": "stable",
                "installer_type": "exe",
                "official_source_url": "https://code.visualstudio.com/download",
                "download_url": "https://code.visualstudio.com/download",
                "source_policy": "official_vendor",
                "sha256": "",
                "signature_policy": "vendor_signed",
                "install_phase": "windows_first_boot",
                "install_action": "official_download",
                "install_command_template": "",
                "silent_args": "/verysilent /mergetasks=!runcode",
                "requires_network": 1,
                "risk_level": "medium",
                "review_status": "needs_review",
                "enabled": 1,
                "notes": "需确认 User/System 安装器选择、静默参数、hash 后启用。",
            },
            {
                "id": "vscode-ubuntu-amd64",
                "os_family": "ubuntu",
                "os_version_constraint": ">=22.04",
                "arch": "x86_64",
                "version": "stable",
                "installer_type": "deb",
                "official_source_url": "https://code.visualstudio.com/docs/setup/linux",
                "download_url": "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64",
                "source_policy": "official_vendor",
                "sha256": "",
                "signature_policy": "vendor_signed",
                "install_phase": "linux_first_boot",
                "install_action": "download_deb",
                "install_command_template": "apt_install_downloaded_deb",
                "silent_args": "",
                "requires_network": 1,
                "risk_level": "medium",
                "review_status": "needs_review",
                "enabled": 1,
                "notes": "官方 Linux 文档提供 deb 和 apt 源方式；需补 hash 或签名验证后启用。",
            },
        ],
    },
    {
        "id": "winscp",
        "name": "WinSCP",
        "vendor": "WinSCP",
        "category": "运维",
        "description": "Windows 文件传输和远程维护工具。",
        "homepage_url": "https://winscp.net/eng/download.php",
        "icon_key": "winscp",
        "status": "available",
        "review_status": "needs_review",
        "variants": [
            {
                "id": "winscp-windows-x64",
                "os_family": "windows",
                "os_version_constraint": "windows_10_or_11",
                "arch": "x86_64",
                "version": "latest",
                "installer_type": "exe",
                "official_source_url": "https://winscp.net/eng/download.php",
                "download_url": "https://winscp.net/eng/download.php",
                "source_policy": "official_vendor",
                "sha256": "",
                "signature_policy": "vendor_signed",
                "install_phase": "windows_first_boot",
                "install_action": "official_download",
                "install_command_template": "",
                "silent_args": "/VERYSILENT /ALLUSERS /NORESTART",
                "requires_network": 1,
                "risk_level": "medium",
                "review_status": "needs_review",
                "enabled": 1,
                "notes": "官方文档提供静默参数；需确认具体安装器直链和 hash 后启用。",
            },
        ],
    },
    {
        "id": "microsoft-office",
        "name": "Microsoft Office",
        "vendor": "Microsoft",
        "category": "办公",
        "description": "Office 办公套件；通过 Office Deployment Tool 从 Microsoft 官方来源安装。",
        "homepage_url": "https://learn.microsoft.com/deployoffice/overview-office-deployment-tool",
        "icon_key": "office",
        "status": "available",
        "review_status": "needs_review",
        "variants": [
            {
                "id": "office-windows-odt",
                "os_family": "windows",
                "os_version_constraint": "windows_10_or_11",
                "arch": "x86_64",
                "version": "latest",
                "installer_type": "office_odt",
                "official_source_url": "https://learn.microsoft.com/deployoffice/overview-office-deployment-tool",
                "download_url": "https://go.microsoft.com/fwlink/?linkid=2243204",
                "source_policy": "official_vendor",
                "sha256": "",
                "signature_policy": "vendor_signed",
                "install_phase": "windows_first_boot",
                "install_action": "office_odt_install",
                "package_name": "ProPlus2021Volume",
                "install_command_template": "office_odt_configure",
                "silent_args": "",
                "requires_network": 1,
                "risk_level": "medium",
                "review_status": "needs_review",
                "enabled": 1,
                "notes": "默认产品 ID 面向 Office 2021 ProPlus 批量授权场景；管理员需确认 ODT 官方直链、Office 授权类型和 KMS/MAK/订阅策略后再批准。",
            },
        ],
    },
    {
        "id": "curl",
        "name": "curl",
        "vendor": "Ubuntu archive",
        "category": "运维",
        "description": "常用命令行 HTTP 客户端，用于脚本下载、连通性测试和自动化维护。",
        "homepage_url": "https://packages.ubuntu.com/search?keywords=curl",
        "icon_key": "terminal",
        "status": "available",
        "review_status": "approved",
        "variants": [
            {
                "id": "curl-ubuntu-apt",
                "os_family": "ubuntu",
                "os_version_constraint": ">=22.04",
                "arch": "x86_64",
                "version": "repo",
                "installer_type": "apt",
                "official_source_url": "https://packages.ubuntu.com/search?keywords=curl",
                "download_url": "https://packages.ubuntu.com/search?keywords=curl",
                "source_policy": "official_package_repo",
                "sha256": "",
                "signature_policy": "repo_signed",
                "install_phase": "linux_first_boot",
                "install_action": "apt_package",
                "package_name": "curl",
                "install_command_template": "apt_install_package",
                "silent_args": "",
                "requires_network": 1,
                "risk_level": "low",
                "review_status": "approved",
                "enabled": 1,
                "notes": "通过 Ubuntu 官方 apt 仓库安装，使用仓库签名校验，不在 SynaBoot 服务器保存安装包。",
            },
        ],
    },
]

DEFAULT_SOFTWARE_PROFILES = [
    {
        "id": "ubuntu-basic-tools",
        "name": "Ubuntu 基础工具",
        "description": "Ubuntu 安装后自动安装基础命令行工具；当前只包含已验证的官方 apt 软件。",
        "os_family": "ubuntu",
        "variant_ids": ["curl-ubuntu-apt"],
        "status": "available",
        "review_status": "approved",
        "risk_level": "low",
    },
]

DEFAULT_FREE_CAPABILITIES = {
    "schema_version": "synaboot.capabilities.v1",
    "edition": "free",
    "release_channel": "free",
    "owner_local_full_feature_allowed": True,
    "github_public_release": True,
    "commercial_code_included": False,
    "online_activation_required": False,
    "free_limits": {
        "basic_image_count_limited": False,
        "basic_menu_generation_limited": False,
        "manual_ipxe_http_boot_limited": False,
        "basic_autoinstall_profile_drafts_limited": False,
        "offline_core_requires_license": False,
    },
    "core_free_guarantees": [
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
    ],
    "paid_feature_placeholders": [
        "multi_script_binding",
        "advanced_variable_expansion_preview",
        "default_autoinstall_policy",
        "host_or_mac_based_autoinstall_policy",
        "bulk_image_lifecycle_management",
        "multi_admin_rbac",
        "audit_reports",
        "multi_node_management",
        "enterprise_identity_integration",
        "commercial_support",
    ],
    "blocked_from_public_release": [
        "commercial_source_code",
        "private_license_files",
        "obfuscated_commercial_bundles",
        "real_os_images",
        "generated_databases",
        "logs",
        "build_artifacts",
        "secrets",
    ],
}

DEFAULT_EDITION_CATALOG = {
    "schema_version": "synaboot.editions.v1",
    "catalog_purpose": "public_display_only_no_license_gate",
    "pricing_model_status": "proposal_not_enforcement",
    "commercial_code_included": False,
    "online_activation_required": False,
    "tiers": [
        {
            "id": "free",
            "name": "Free",
            "billing": "free",
            "summary": "基础装机闭环永久免费。",
            "included": [
                "Docker Compose 本地部署",
                "HTTP 镜像仓库",
                "本地 ISO 扫描",
                "HotPE 辅助 Windows 安装",
                "Ubuntu/Linux 基础启动准备",
                "iPXE HTTP 菜单生成",
                "手动 iPXE USB/ISO/EFI 启动",
                "手动 UEFI HTTP Boot",
                "基础 Web UI 镜像管理",
                "基础 Image Factory 模板",
                "Ubuntu autoinstall / Windows Autounattend 安全草稿",
                "模板预览与变量白名单展示",
                "网络安全 preflight",
                "Phase 3 只读启动入口状态",
                "基础文档、教程和故障排查",
            ],
            "limits": {
                "basic_image_count_limited": False,
                "basic_menu_generation_limited": False,
                "manual_ipxe_http_boot_limited": False,
                "basic_autoinstall_profile_drafts_limited": False,
                "offline_core_requires_license": False,
            },
        },
        {
            "id": "professional",
            "name": "Professional",
            "billing": "subscription_or_one_time_purchase_candidate",
            "summary": "面向小团队和高频装机管理员的高级效率能力。",
            "candidate_features": [
                "自动安装脚本库管理",
                "一个 ISO 绑定多个自动安装方案",
                "高级变量扩展预览",
                "默认镜像、默认脚本、菜单超时和脚本选择超时",
                "批量镜像标签、版本和生命周期管理",
                "一键诊断包导出",
                "更完整的 ISO 准备向导",
                "小团队离线授权或一次性买断候选",
            ],
        },
        {
            "id": "enterprise",
            "name": "Enterprise",
            "billing": "subscription_or_support_contract_candidate",
            "summary": "面向企业治理、规模化和长期支持。",
            "candidate_features": [
                "多管理员账号与 RBAC",
                "审计日志和操作追踪",
                "多节点/多站点管理",
                "镜像同步、校验和保留策略",
                "LDAP/OIDC 企业身份集成",
                "装机报表、成功率、失败原因和机型统计",
                "企业支持、长期维护和升级策略",
                "大规模无人值守装机治理能力",
            ],
        },
        {
            "id": "usage_based",
            "name": "Usage-based",
            "billing": "per_use_or_project_service_candidate",
            "summary": "面向高价值、大规模或专家服务型任务的按次/项目制候选。",
            "candidate_features": [
                "大规模批量无人值守装机任务",
                "企业级驱动包/脚本注入流水线",
                "自动生成定制镜像任务",
                "远程协助诊断",
                "专家模板生成",
            ],
        },
    ],
    "guardrails": [
        "当前 GitHub 分支只发布 Free 免费版代码。",
        "Professional/Enterprise 当前仅为公开候选说明，不包含实现代码。",
        "Usage-based 当前仅为按次或项目制候选说明，不包含实现代码。",
        "商业源码、私有 license 和混淆产物不得进入 GitHub 免费发布线。",
        "本机 owner/developer 私有全功能能力不得依赖公网授权才能使用。",
        "任何收费能力都不得削弱基础装机和网络安全门禁。",
    ],
}


def ensure_dirs() -> None:
    for path in (IMAGES_DIR, BOOT_DIR, METADATA_DIR, BUILDS_DIR, LOGS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def connect_db() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS images (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            kind TEXT NOT NULL,
            rel_path TEXT NOT NULL UNIQUE,
            size_bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            menu_enabled INTEGER NOT NULL DEFAULT 1,
            boot_method TEXT NOT NULL,
            description TEXT NOT NULL,
            scanned_at INTEGER NOT NULL
        )
        """
    )
    ensure_image_columns(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT NOT NULL,
            output_dir TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            note TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS autoinstall_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            os_family TEXT NOT NULL,
            template_kind TEXT NOT NULL,
            edition_tier TEXT NOT NULL,
            status TEXT NOT NULL,
            destructive_policy TEXT NOT NULL,
            variables TEXT NOT NULL,
            template_preview TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            note TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS client_sessions (
            session_id TEXT PRIMARY KEY,
            session_token_hash TEXT NOT NULL,
            mac TEXT NOT NULL,
            ip TEXT NOT NULL,
            uuid TEXT NOT NULL,
            serial TEXT NOT NULL,
            asset TEXT NOT NULL,
            manufacturer TEXT NOT NULL,
            product TEXT NOT NULL,
            platform TEXT NOT NULL,
            buildarch TEXT NOT NULL,
            state TEXT NOT NULL,
            selected_target TEXT NOT NULL,
            selected_label TEXT NOT NULL,
            first_seen_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            evidence TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deployment_assignments (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            session_ids TEXT NOT NULL DEFAULT '[]',
            source_image_id TEXT NOT NULL,
            boot_target TEXT NOT NULL,
            boot_label TEXT NOT NULL,
            software_package_ids TEXT NOT NULL DEFAULT '[]',
            software_profile_ids TEXT NOT NULL,
            software_variant_ids TEXT NOT NULL,
            resolved_software_plan TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL,
            created_by TEXT NOT NULL DEFAULT 'admin',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS install_presets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            os_family TEXT NOT NULL,
            boot_target TEXT NOT NULL,
            software_package_ids TEXT NOT NULL,
            software_profile_ids TEXT NOT NULL,
            settings_json TEXT NOT NULL,
            status TEXT NOT NULL,
            review_status TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            notes TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS client_events (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            assignment_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assignment_boot_tokens (
            assignment_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (assignment_id, session_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS software_packages (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            vendor TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            homepage_url TEXT NOT NULL,
            icon_key TEXT NOT NULL,
            status TEXT NOT NULL,
            review_status TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS software_variants (
            id TEXT PRIMARY KEY,
            package_id TEXT NOT NULL,
            os_family TEXT NOT NULL,
            os_version_constraint TEXT NOT NULL,
            arch TEXT NOT NULL,
            version TEXT NOT NULL,
            installer_type TEXT NOT NULL,
            official_source_url TEXT NOT NULL,
            download_url TEXT NOT NULL,
            source_policy TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            signature_policy TEXT NOT NULL,
            install_phase TEXT NOT NULL,
            install_action TEXT NOT NULL,
            package_name TEXT NOT NULL DEFAULT '',
            default_for_os INTEGER NOT NULL DEFAULT 0,
            selection_priority INTEGER NOT NULL DEFAULT 0,
            install_command_template TEXT NOT NULL,
            silent_args TEXT NOT NULL,
            requires_network INTEGER NOT NULL,
            risk_level TEXT NOT NULL,
            review_status TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            notes TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY(package_id) REFERENCES software_packages(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS software_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            os_family TEXT NOT NULL,
            variant_ids TEXT NOT NULL,
            status TEXT NOT NULL,
            review_status TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deployment_assignments_session ON deployment_assignments(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assignment_boot_tokens_expires ON assignment_boot_tokens(expires_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_client_events_assignment ON client_events(assignment_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_client_events_session ON client_events(session_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_software_variants_package ON software_variants(package_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_software_variants_os ON software_variants(os_family, enabled, review_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_software_profiles_os ON software_profiles(os_family, status, review_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_install_presets_os ON install_presets(os_family, status, review_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_client_sessions_last_seen ON client_sessions(last_seen_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_client_sessions_mac_uuid ON client_sessions(mac, uuid)")
    conn.commit()
    ensure_deployment_assignment_columns(conn)
    ensure_software_variant_columns(conn)
    ensure_install_orchestration_seed(conn)
    ensure_software_catalog(conn)
    ensure_software_profiles(conn)
    return conn


def ensure_deployment_assignment_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(deployment_assignments)")}
    migrations = {
        "session_ids": "ALTER TABLE deployment_assignments ADD COLUMN session_ids TEXT NOT NULL DEFAULT '[]'",
        "software_package_ids": "ALTER TABLE deployment_assignments ADD COLUMN software_package_ids TEXT NOT NULL DEFAULT '[]'",
        "resolved_software_plan": "ALTER TABLE deployment_assignments ADD COLUMN resolved_software_plan TEXT NOT NULL DEFAULT '{}'",
        "created_by": "ALTER TABLE deployment_assignments ADD COLUMN created_by TEXT NOT NULL DEFAULT 'admin'",
        "boot_token_hash": "ALTER TABLE deployment_assignments ADD COLUMN boot_token_hash TEXT NOT NULL DEFAULT ''",
        "boot_token_expires_at": "ALTER TABLE deployment_assignments ADD COLUMN boot_token_expires_at INTEGER NOT NULL DEFAULT 0",
        "install_preset_id": "ALTER TABLE deployment_assignments ADD COLUMN install_preset_id TEXT NOT NULL DEFAULT ''",
        "task_sequence_plan": "ALTER TABLE deployment_assignments ADD COLUMN task_sequence_plan TEXT NOT NULL DEFAULT '{}'",
    }
    for column, sql in migrations.items():
        if column not in columns:
            conn.execute(sql)
    rows = conn.execute("SELECT id, session_id FROM deployment_assignments WHERE session_ids = '[]' OR session_ids = ''").fetchall()
    for row in rows:
        conn.execute(
            "UPDATE deployment_assignments SET session_ids = ? WHERE id = ?",
            (json.dumps([row["session_id"]], ensure_ascii=False), row["id"]),
        )
    conn.commit()


def ensure_software_variant_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(software_variants)")}
    migrations = {
        "package_name": "ALTER TABLE software_variants ADD COLUMN package_name TEXT NOT NULL DEFAULT ''",
        "default_for_os": "ALTER TABLE software_variants ADD COLUMN default_for_os INTEGER NOT NULL DEFAULT 0",
        "selection_priority": "ALTER TABLE software_variants ADD COLUMN selection_priority INTEGER NOT NULL DEFAULT 0",
        "install_context": "ALTER TABLE software_variants ADD COLUMN install_context TEXT NOT NULL DEFAULT ''",
        "detection_rules": "ALTER TABLE software_variants ADD COLUMN detection_rules TEXT NOT NULL DEFAULT '[]'",
        "requirements_json": "ALTER TABLE software_variants ADD COLUMN requirements_json TEXT NOT NULL DEFAULT '{}'",
        "dependencies_json": "ALTER TABLE software_variants ADD COLUMN dependencies_json TEXT NOT NULL DEFAULT '[]'",
        "return_codes_json": "ALTER TABLE software_variants ADD COLUMN return_codes_json TEXT NOT NULL DEFAULT '{\"success\":[0],\"soft_reboot\":[3010]}'",
        "restart_behavior": "ALTER TABLE software_variants ADD COLUMN restart_behavior TEXT NOT NULL DEFAULT 'none'",
        "install_location_policy": "ALTER TABLE software_variants ADD COLUMN install_location_policy TEXT NOT NULL DEFAULT 'system_default'",
    }
    for column, sql in migrations.items():
        if column not in columns:
            conn.execute(sql)
    conn.commit()


def ensure_install_orchestration_seed(conn: sqlite3.Connection) -> None:
    now = int(time.time())
    preset_values = {
        "id": "windows-office-standard",
        "name": "Windows + Office 标准装机预设",
        "description": "Windows 安装后自动安装 Office 2021 ProPlus。",
        "os_family": "windows",
        "boot_target": "windows_setup",
        "software_package_ids": json.dumps(DEFAULT_WINDOWS_SOFTWARE_PACKAGE_IDS, ensure_ascii=False),
        "software_profile_ids": "[]",
        "settings_json": json.dumps(
            {
                "schema_version": "synaboot.install-preset-settings.v1",
                "office_kms_policy": "use_customer_managed_env_when_enabled",
                "hostname_rule": "manual_or_existing",
            },
            ensure_ascii=False,
        ),
        "created_at": now,
        "updated_at": now,
        "notes": "免费版第一阶段预设：保存系统和软件组合；不包含磁盘设置。",
    }
    install_preset_columns = {row["name"] for row in conn.execute("PRAGMA table_info(install_presets)")}
    if "partition_template_id" in install_preset_columns:
        conn.execute(
            """
            INSERT OR IGNORE INTO install_presets (
                id, name, description, os_family, boot_target, partition_template_id,
                software_package_ids, software_profile_ids, settings_json, status, review_status,
                created_at, updated_at, notes
            )
            VALUES (
                :id, :name, :description, :os_family, :boot_target, '',
                :software_package_ids, :software_profile_ids, :settings_json,
                'available', 'approved', :created_at, :updated_at, :notes
            )
            """,
            preset_values,
        )
        conn.execute(
            """
            UPDATE install_presets
            SET description = :description,
                partition_template_id = '',
                settings_json = :settings_json,
                notes = :notes,
                updated_at = :updated_at
            WHERE id = :id
            """,
            preset_values,
        )
    else:
        conn.execute(
            """
            INSERT OR IGNORE INTO install_presets (
                id, name, description, os_family, boot_target,
                software_package_ids, software_profile_ids, settings_json, status, review_status,
                created_at, updated_at, notes
            )
            VALUES (
                :id, :name, :description, :os_family, :boot_target,
                :software_package_ids, :software_profile_ids, :settings_json,
                'available', 'approved', :created_at, :updated_at, :notes
            )
            """,
            preset_values,
        )
        conn.execute(
            """
            UPDATE install_presets
            SET description = :description,
                settings_json = :settings_json,
                notes = :notes,
                updated_at = :updated_at
            WHERE id = :id
            """,
            preset_values,
        )
    conn.commit()


def ensure_software_catalog(conn: sqlite3.Connection) -> None:
    now = int(time.time())
    for package in DEFAULT_SOFTWARE_CATALOG:
        conn.execute(
            """
            INSERT OR IGNORE INTO software_packages (
                id, name, vendor, category, description, homepage_url,
                icon_key, status, review_status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                package["id"],
                package["name"],
                package["vendor"],
                package["category"],
                package["description"],
                package["homepage_url"],
                package["icon_key"],
                package["status"],
                package["review_status"],
                now,
                now,
            ),
        )
        for variant in package["variants"]:
            conn.execute(
                """
                INSERT OR IGNORE INTO software_variants (
                    id, package_id, os_family, os_version_constraint, arch, version,
                    installer_type, official_source_url, download_url, source_policy,
                    sha256, signature_policy, install_phase, install_action,
                    package_name, default_for_os, selection_priority,
                    install_command_template, silent_args, requires_network, risk_level,
                    review_status, enabled, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    variant["id"],
                    package["id"],
                    variant["os_family"],
                    variant["os_version_constraint"],
                    variant["arch"],
                    variant["version"],
                    variant["installer_type"],
                    variant["official_source_url"],
                    variant["download_url"],
                    variant["source_policy"],
                    variant["sha256"],
                    variant["signature_policy"],
                    variant["install_phase"],
                    variant["install_action"],
                    variant.get("package_name", ""),
                    int(bool(variant.get("default_for_os", False))),
                    int(variant.get("selection_priority", 0)),
                    variant["install_command_template"],
                    variant["silent_args"],
                    int(variant["requires_network"]),
                    variant["risk_level"],
                    variant["review_status"],
                    int(variant["enabled"]),
                    variant["notes"],
                    now,
                    now,
                ),
            )
    conn.execute(
        """
        UPDATE software_variants
        SET installer_type = 'deb', updated_at = ?
        WHERE id = 'chrome-ubuntu-amd64'
          AND installer_type = 'apt'
          AND install_action = 'download_deb'
        """,
        (now,),
    )
    # 旧数据库使用 INSERT OR IGNORE 初始化，已有默认软件元数据不会随代码自动升级。
    # 这里仅同步项目内置默认项，不覆盖管理员后续自定义新增的软件。
    conn.execute(
        """
        UPDATE software_variants
        SET installer_type = 'office_odt',
            official_source_url = 'https://learn.microsoft.com/deployoffice/overview-office-deployment-tool',
            download_url = 'https://go.microsoft.com/fwlink/?linkid=2243204',
            source_policy = 'official_vendor',
            signature_policy = 'vendor_signed',
            install_phase = 'windows_first_boot',
            install_action = 'office_odt_install',
            package_name = 'ProPlus2021Volume',
            install_command_template = 'office_odt_configure',
            silent_args = '',
            review_status = 'approved',
            enabled = 1,
            notes = 'Office 2021 ProPlus 通过 Microsoft Office Deployment Tool 安装；仅适用于管理员自有合法批量授权/KMS 环境。',
            updated_at = ?
        WHERE id = 'office-windows-odt'
        """,
        (now,),
    )
    conn.execute(
        """
        UPDATE software_variants
        SET version = '7.68.6',
            installer_type = 'msi',
            official_source_url = 'https://www.feishu.cn/hc/zh-CN/articles/360049067543-%E4%BD%BF%E7%94%A8-msi-%E6%96%87%E4%BB%B6%E6%89%B9%E9%87%8F%E9%83%A8%E7%BD%B2%E9%A3%9E%E4%B9%A6%E5%AE%A2%E6%88%B7%E7%AB%AF',
            download_url = 'https://sf3-cn.feishucdn.com/obj/hera-cn/download/Feishu-win32_x64-7.68.6-signed.msi',
            source_policy = 'admin_reviewed_download',
            signature_policy = 'vendor_signed',
            install_phase = 'windows_first_boot',
            install_action = 'msi_install',
            install_command_template = 'msi_install',
            silent_args = '/qn /norestart',
            review_status = 'approved',
            enabled = 1,
            notes = '按飞书官方 MSI 批量部署教程配置；客户端首次启动后直接从飞书 CDN 下载 MSI 并静默安装，SynaBoot 不托管安装包。',
            updated_at = ?
        WHERE id = 'feishu-windows-x64'
        """,
        (now,),
    )
    feishu_deb_url = os.environ.get("SYNABOOT_FEISHU_UBUNTU_DEB_URL", "").strip()
    if feishu_deb_url:
        conn.execute(
            """
            UPDATE software_variants
            SET installer_type = 'deb',
                download_url = ?,
                source_policy = 'official_vendor',
                signature_policy = 'vendor_signed',
                install_phase = 'linux_first_boot',
                install_action = 'download_deb',
                install_command_template = 'apt_install_downloaded_deb',
                review_status = 'approved',
                enabled = 1,
                notes = '通过管理员确认的飞书官方 Linux deb 直链安装；SynaBoot 不托管该安装包。',
                updated_at = ?
            WHERE id = 'feishu-ubuntu-amd64'
            """,
            (feishu_deb_url, now),
        )
    else:
        existing_feishu = conn.execute(
            """
            SELECT download_url
            FROM software_variants
            WHERE id = 'feishu-ubuntu-amd64'
              AND review_status = 'approved'
              AND enabled = 1
              AND installer_type = 'deb'
              AND install_action = 'official_download'
            """
        ).fetchone()
        existing_feishu_url = existing_feishu["download_url"].strip() if existing_feishu else ""
        # 管理员可能已经在软件市场里维护了真实官方 deb 直链，但旧记录仍停留在
        # official_download。此处只对 HTTPS、非 SynaBoot 托管、路径为 .deb 的飞书
        # Ubuntu 变体做兼容迁移，避免把普通下载页误标为可执行安装源。
        if existing_feishu_url and is_deb_download_url(existing_feishu_url) and not is_blocked_software_download_host(existing_feishu_url):
            conn.execute(
                """
                UPDATE software_variants
                SET source_policy = 'official_vendor',
                    signature_policy = 'vendor_signed',
                    install_phase = 'linux_first_boot',
                    install_action = 'download_deb',
                    install_command_template = 'apt_install_downloaded_deb',
                    notes = '通过管理员在软件市场确认的飞书官方 Linux deb 直链安装；SynaBoot 不托管该安装包。',
                    updated_at = ?
                WHERE id = 'feishu-ubuntu-amd64'
                """,
                (now,),
            )
        conn.execute(
            """
            UPDATE software_variants
            SET notes = '飞书 Ubuntu 自动安装需要配置 SYNABOOT_FEISHU_UBUNTU_DEB_URL 为官方 Linux deb 直链；下载页不是 deb 安装包，不能直接作为自动安装源。',
                updated_at = ?
            WHERE id = 'feishu-ubuntu-amd64'
              AND install_action = 'official_download'
            """,
            (now,),
        )
    conn.commit()


def ensure_software_profiles(conn: sqlite3.Connection) -> None:
    now = int(time.time())
    for profile in DEFAULT_SOFTWARE_PROFILES:
        conn.execute(
            """
            INSERT OR IGNORE INTO software_profiles (
                id, name, description, os_family, variant_ids, status,
                review_status, risk_level, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile["id"],
                profile["name"],
                profile["description"],
                profile["os_family"],
                json.dumps(profile["variant_ids"], ensure_ascii=False),
                profile["status"],
                profile["review_status"],
                profile["risk_level"],
                now,
                now,
            ),
        )
    conn.commit()


def ensure_image_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(images)")}
    migrations = {
        "display_name": "ALTER TABLE images ADD COLUMN display_name TEXT NOT NULL DEFAULT ''",
        "version": "ALTER TABLE images ADD COLUMN version TEXT NOT NULL DEFAULT ''",
        "architecture": "ALTER TABLE images ADD COLUMN architecture TEXT NOT NULL DEFAULT ''",
        "relative_path": "ALTER TABLE images ADD COLUMN relative_path TEXT NOT NULL DEFAULT ''",
        "mtime_ns": "ALTER TABLE images ADD COLUMN mtime_ns INTEGER NOT NULL DEFAULT 0",
        "sha256_cached": "ALTER TABLE images ADD COLUMN sha256_cached INTEGER NOT NULL DEFAULT 0",
        "scan_status": "ALTER TABLE images ADD COLUMN scan_status TEXT NOT NULL DEFAULT 'present'",
        "boot_readiness": "ALTER TABLE images ADD COLUMN boot_readiness TEXT NOT NULL DEFAULT 'unsupported'",
        "source_role": "ALTER TABLE images ADD COLUMN source_role TEXT NOT NULL DEFAULT 'artifact'",
        "preparation_status": "ALTER TABLE images ADD COLUMN preparation_status TEXT NOT NULL DEFAULT 'not_required'",
        "missing_artifacts": "ALTER TABLE images ADD COLUMN missing_artifacts TEXT NOT NULL DEFAULT '[]'",
        "next_action": "ALTER TABLE images ADD COLUMN next_action TEXT NOT NULL DEFAULT ''",
        "readiness_detail": "ALTER TABLE images ADD COLUMN readiness_detail TEXT NOT NULL DEFAULT ''",
        "last_seen_at": "ALTER TABLE images ADD COLUMN last_seen_at INTEGER NOT NULL DEFAULT 0",
        "updated_at": "ALTER TABLE images ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0",
        "missing_since": "ALTER TABLE images ADD COLUMN missing_since INTEGER",
    }
    for column, sql in migrations.items():
        if column not in columns:
            conn.execute(sql)
    conn.execute("UPDATE images SET display_name = name WHERE display_name = ''")
    conn.execute("UPDATE images SET relative_path = rel_path WHERE relative_path = ''")
    conn.execute("UPDATE images SET updated_at = scanned_at WHERE updated_at = 0")
    conn.execute("UPDATE images SET last_seen_at = scanned_at WHERE last_seen_at = 0")
    conn.commit()


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: object) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, status: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
    encoded = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def safe_relative(path: Path, root: Path) -> str:
    resolved = path.resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError("路径越界")
    return resolved.relative_to(root).as_posix()


def category_from_path(rel_path: str) -> str:
    first = rel_path.split("/", 1)[0]
    return first if first in {"pe", "windows", "linux", "tools", "custom"} else "custom"


def file_kind(path: Path) -> str | None:
    lower_name = path.name.lower()
    if lower_name in SPECIAL_NAMES:
        return SPECIAL_NAMES[lower_name]
    return IMAGE_EXTENSIONS.get(path.suffix.lower())


def is_scannable_path(path: Path) -> bool:
    parts = path.relative_to(IMAGES_DIR).parts
    if any(part.startswith(".") for part in parts):
        return False
    name = path.name.lower()
    if name.endswith(".tmp") or name.endswith(".part") or name.endswith(".download"):
        return False
    rel_path = path.relative_to(IMAGES_DIR).as_posix()
    return bool(SAFE_IMAGE_REL_PATH_RE.fullmatch(rel_path)) and "//" not in rel_path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def boot_method(category: str, kind: str, rel_path: str) -> str:
    if category == "pe" and kind == "iso":
        return "hotpe-iso-source"
    if category == "pe" or "hotpe" in rel_path:
        return "hotpe-wimboot"
    if category == "linux":
        return "linux-kernel-initrd"
    if category == "windows":
        return "hotpe-assisted"
    return "http-download"


def linux_group_ready(rel_path: str, present: set[str]) -> bool:
    directory = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
    if "/casper/" in rel_path:
        directory = rel_path.split("/casper/", 1)[0]
    if not directory:
        return False
    has_iso = any(path.startswith(f"{directory}/") and path.lower().endswith(".iso") for path in present)
    has_livefs = any(path.startswith(f"{directory}/casper/") and path.endswith(".squashfs") for path in present)
    return has_iso and f"{directory}/casper/vmlinuz" in present and f"{directory}/casper/initrd" in present and has_livefs


def hotpe_group_ready(present: set[str]) -> bool:
    return set(hotpe_required_artifacts()).issubset(present)


def hotpe_required_artifacts() -> list[str]:
    return [
        "pe/hotpe/wimboot",
        "pe/hotpe/bootmgr",
        "pe/hotpe/bootx64.efi",
        "pe/hotpe/BCD",
        "pe/hotpe/boot.sdi",
        "pe/hotpe/boot.wim",
    ]


def windows_wimboot_required_artifacts() -> list[str]:
    return [
        "pe/hotpe/wimboot",
        "windows/win11/boot/BCD",
        "windows/win11/boot/boot.sdi",
        "windows/win11/boot/boot.wim",
    ]


def linux_base_dir(rel_path: str) -> str:
    if "/casper/" in rel_path:
        return rel_path.split("/casper/", 1)[0]
    return rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""


def linux_required_artifacts(rel_path: str) -> list[str]:
    directory = linux_base_dir(rel_path)
    if not directory:
        return []
    return [
        f"{directory}/casper/vmlinuz",
        f"{directory}/casper/initrd",
    ]


def missing_artifacts_for(category: str, kind: str, rel_path: str, present: set[str]) -> list[str]:
    if category == "pe" and "pe/hotpe/" in rel_path:
        return [path for path in hotpe_required_artifacts() if path not in present]
    if category == "linux":
        directory = linux_base_dir(rel_path)
        missing = [path for path in linux_required_artifacts(rel_path) if path not in present]
        has_livefs = bool(directory) and any(
            path.startswith(f"{directory}/casper/") and path.endswith(".squashfs")
            for path in present
        )
        if directory and not has_livefs:
            missing.append(f"{directory}/casper/*.squashfs")
        return missing
    return []


def boot_readiness(category: str, kind: str, rel_path: str, present: set[str]) -> str:
    if category == "windows" and kind in {"iso", "wim", "esd"}:
        return "needs_hotpe"
    if category == "pe" and "pe/hotpe/" in rel_path:
        return "ready" if hotpe_group_ready(present) else "incomplete"
    if category == "linux":
        return "ready" if linux_group_ready(rel_path, present) else "incomplete"
    return "unsupported"


def source_role(category: str, kind: str, rel_path: str) -> str:
    if kind == "iso":
        if category in {"pe", "linux"}:
            return "source_iso"
        if category == "windows":
            return "windows_source_iso"
    if kind in {"linux-kernel", "initrd", "livefs", "wimboot", "bootmgr", "bcd", "boot-sdi", "wim"}:
        return "boot_artifact"
    return "repository_file"


def source_group_key(rel_path: str, category: str) -> str:
    if category == "linux":
        return linux_base_dir(rel_path)
    if category == "pe" and rel_path.startswith("pe/hotpe/"):
        return "pe/hotpe"
    if category == "windows" and rel_path.startswith("windows/win11/"):
        return "windows/win11"
    return rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""


def artifact_role_for(rel_path: str, kind: str) -> str:
    if rel_path.endswith("/casper/vmlinuz"):
        return "linux_kernel"
    if rel_path.endswith("/casper/initrd"):
        return "linux_initrd"
    if "/casper/" in rel_path and rel_path.endswith(".squashfs"):
        return "linux_livefs"
    lower = rel_path.lower()
    if lower.endswith("/wimboot"):
        return "hotpe_wimboot"
    if lower.endswith("/bootmgr"):
        return "hotpe_bootmgr"
    if lower.endswith("/bootx64.efi"):
        return "bootx64_efi"
    if lower.endswith("/bcd"):
        return "windows_bcd"
    if lower.endswith("/boot.sdi"):
        return "windows_boot_sdi"
    if lower.endswith("/boot.wim"):
        return "windows_boot_wim"
    return kind or "repository_file"


def detect_image_strategy(row: dict) -> dict:
    rel_path = row.get("relative_path") or row.get("rel_path", "")
    name = (row.get("name") or rel_path.rsplit("/", 1)[-1]).lower()
    category = row.get("category", "")
    kind = row.get("kind", "")
    target = f"{rel_path.lower()} {name}"
    result = {
        "os_family": "unknown",
        "detected_distro": "",
        "detected_version": "",
        "detected_arch": "",
        "detection_confidence": "low",
        "strategy_key": "unsupported_source_only",
        "strategy_display_name": "Unsupported source only",
        "strategy_status": "unsupported_source_only",
        "inventory_role": "repository_file",
        "object_type": "repository_file",
        "visibility": "detail",
        "artifact_role": artifact_role_for(rel_path, kind),
        "parent_relative_path": "",
        "detection_status": "unknown",
        "detection_strategy": "path_heuristic",
        "detection_evidence": [],
        "source_group": source_group_key(rel_path, category),
    }
    if kind == "iso" or row.get("source_role") in {"source_iso", "windows_source_iso"}:
        result["inventory_role"] = "source_iso"
        result["object_type"] = "source_image"
        result["visibility"] = "primary"
    elif row.get("source_role") == "boot_artifact":
        result["inventory_role"] = "detail_artifact"
        result["object_type"] = "derived_boot_artifact"
        result["visibility"] = "detail"
    if category == "windows" and kind == "iso":
        result.update(
            {
                "os_family": "windows",
                "detected_distro": "windows",
                "detection_confidence": "medium",
                "detection_status": "detected",
                "detection_evidence": ["path category is windows", "source file is iso"],
                "strategy_key": "windows_hotpe_assisted",
                "strategy_display_name": "Windows via HotPE",
                "strategy_status": "ready" if row.get("boot_readiness") == "needs_hotpe" else "needs_hotpe",
            }
        )
    elif category == "pe" and kind == "iso":
        result.update(
            {
                "os_family": "windows_pe",
                "detected_distro": "hotpe",
                "detection_confidence": "medium" if "hotpe" in target else "low",
                "detection_status": "detected" if "hotpe" in target else "partial",
                "detection_evidence": ["path category is pe", "source file is iso"],
                "strategy_key": "hotpe_wimboot",
                "strategy_display_name": "HotPE wimboot",
                "strategy_status": row.get("boot_readiness") or "incomplete",
            }
        )
    elif category == "linux" and kind == "iso" and ("proxmox" in target or re.search(r"\bpve\b", target)):
        result.update(
            {
                "os_family": "linux",
                "detected_distro": "proxmox-ve",
                "detection_confidence": "medium",
                "detection_status": "detected",
                "detection_evidence": ["filename/path indicates proxmox or pve", "strategy requires research"],
                "strategy_key": "research_required",
                "strategy_display_name": "Research required",
                "strategy_status": "research_required",
            }
        )
    elif category == "linux" and kind == "iso" and "debian" in target:
        version_match = re.search(r"debian[-_ ]([0-9]+(?:\.[0-9]+)*)", target)
        result.update(
            {
                "os_family": "linux",
                "detected_distro": "debian",
                "detected_version": version_match.group(1) if version_match else "",
                "detection_confidence": "medium",
                "detection_status": "detected",
                "detection_evidence": ["filename/path indicates debian", "official netboot strategy not implemented"],
                "strategy_key": "research_required",
                "strategy_display_name": "Debian netboot research required",
                "strategy_status": "research_required",
            }
        )
    elif category == "linux" and kind == "iso" and any(token in target for token in ["rhel", "redhat", "red hat", "rocky", "almalinux", "alma", "centos"]):
        distro = "rhel-family"
        if "rocky" in target:
            distro = "rocky-linux"
        elif "almalinux" in target or "alma" in target:
            distro = "almalinux"
        elif "centos" in target:
            distro = "centos"
        result.update(
            {
                "os_family": "linux",
                "detected_distro": distro,
                "detection_confidence": "medium",
                "detection_status": "detected",
                "detection_evidence": ["filename/path indicates rhel-family installer", "anaconda install tree strategy not implemented"],
                "strategy_key": "research_required",
                "strategy_display_name": "Anaconda install tree research required",
                "strategy_status": "research_required",
            }
        )
    elif category == "linux" and kind == "iso" and "ubuntu" in target:
        version_match = re.search(r"ubuntu[-_ ]([0-9]+(?:\.[0-9]+){1,2})", target)
        arch = "amd64" if "amd64" in target or "x86_64" in target else ""
        result.update(
            {
                "os_family": "linux",
                "detected_distro": "ubuntu",
                "detected_version": version_match.group(1) if version_match else "",
                "detected_arch": arch,
                "detection_confidence": "medium",
                "detection_status": "detected",
                "detection_evidence": ["filename/path indicates ubuntu", "linux casper strategy candidate"],
                "strategy_key": "ubuntu_desktop_nfs_livefs",
                "strategy_display_name": "Ubuntu Desktop NFS livefs",
                "strategy_status": row.get("boot_readiness") or "incomplete",
            }
        )
    elif category == "linux" and kind == "iso":
        result.update(
            {
                "os_family": "linux",
                "detection_confidence": "low",
                "detection_status": "partial",
                "detection_evidence": ["path category is linux", "no reviewed distro strategy matched"],
                "strategy_key": "research_required",
                "strategy_display_name": "Research required",
                "strategy_status": "research_required",
            }
        )
    result["os_distribution"] = result["detected_distro"]
    return result


def preparation_status(category: str, kind: str, rel_path: str, boot_state: str, missing: list[str]) -> str:
    if category == "windows" and kind in {"iso", "wim", "esd"}:
        return "uses_hotpe"
    if kind == "iso" and category in {"pe", "linux"}:
        return "prepared" if boot_state == "ready" else "needs_extraction"
    if missing:
        return "waiting_for_source"
    if boot_state == "ready":
        return "prepared"
    return "not_required"


def next_action_for(category: str, kind: str, boot_state: str, prep_state: str, missing: list[str]) -> str:
    if boot_state == "missing":
        return "文件已不存在，请重新扫描或放回原路径。"
    if category == "windows" and kind in {"iso", "wim", "esd"}:
        return "保留为 Windows 源镜像；HotPE 准备完成后从 HotPE 访问安装。"
    if category == "pe" and kind == "iso" and boot_state == "ready":
        return "HotPE 启动依赖已补齐，可通过 iPXE 菜单进入 HotPE。"
    if category == "pe" and kind == "iso":
        return "创建 HotPE ISO 准备任务，提取 wimboot、bootmgr、BCD、boot.sdi、boot.wim。"
    if category == "pe" and missing:
        return "等待 HotPE 启动依赖补齐：" + "，".join(missing)
    if category == "linux" and kind == "iso" and prep_state == "needs_extraction":
        return "创建 Ubuntu/Linux ISO 准备任务，提取 casper/vmlinuz、casper/initrd 和 casper/filesystem.squashfs。"
    if category == "linux" and missing:
        return "等待 Linux 启动依赖补齐：" + "，".join(missing)
    if boot_state == "ready":
        return "已满足启动依赖，可进入 iPXE 菜单。"
    return "可作为 HTTP 仓库文件保存，当前不会生成直接启动菜单项。"


def readiness_detail_for(boot_state: str, prep_state: str, missing: list[str]) -> str:
    if missing:
        return "缺少：" + "，".join(missing)
    if boot_state == "ready":
        return "启动依赖完整。"
    if prep_state == "uses_hotpe":
        return "Windows 镜像通过 HotPE 辅助安装。"
    if prep_state == "needs_extraction":
        return "源 ISO 已扫描，尚未提取启动依赖。"
    return "当前文件不生成启动项。"


def scan_images() -> list[dict]:
    conn = connect_db()
    now = int(time.time())
    rows: list[dict] = []
    seen: set[str] = set()
    existing = {
        row["rel_path"]: dict(row)
        for row in conn.execute("SELECT * FROM images")
    }
    discovered: list[dict] = []
    present_paths: set[str] = set()

    for path in sorted(IMAGES_DIR.rglob("*")):
        if path.is_symlink() or not path.is_file() or not is_scannable_path(path):
            continue
        kind = file_kind(path)
        if not kind:
            continue
        rel_path = safe_relative(path, IMAGES_DIR)
        category = category_from_path(rel_path)
        seen.add(rel_path)
        present_paths.add(rel_path)
        stat = path.stat()
        old = existing.get(rel_path)
        sha256_cached = bool(
            old
            and old.get("size_bytes") == stat.st_size
            and old.get("mtime_ns") == stat.st_mtime_ns
            and old.get("sha256")
            and old.get("scan_status") != "missing"
        )
        sha256 = old["sha256"] if sha256_cached else sha256_file(path)
        row = {
            "id": hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:16],
            "name": path.name,
            "display_name": old.get("display_name") or path.name if old else path.name,
            "category": category,
            "kind": kind,
            "rel_path": rel_path,
            "relative_path": rel_path,
            "url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/{rel_path}",
            "size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": sha256,
            "sha256_cached": 1 if sha256_cached else 0,
            "menu_enabled": old["menu_enabled"] if old else 1,
            "boot_method": boot_method(category, kind, rel_path),
            "boot_readiness": "unsupported",
            "source_role": source_role(category, kind, rel_path),
            "preparation_status": "not_required",
            "missing_artifacts": "[]",
            "next_action": "",
            "readiness_detail": "",
            "scan_status": "present",
            "description": "",
            "scanned_at": now,
            "last_seen_at": now,
            "updated_at": now,
            "missing_since": None,
        }
        discovered.append(row)

    for row in discovered:
        missing = missing_artifacts_for(row["category"], row["kind"], row["rel_path"], present_paths)
        row["boot_readiness"] = boot_readiness(row["category"], row["kind"], row["rel_path"], present_paths)
        row["preparation_status"] = preparation_status(
            row["category"],
            row["kind"],
            row["rel_path"],
            row["boot_readiness"],
            missing,
        )
        row["missing_artifacts"] = json.dumps(missing, ensure_ascii=False)
        row["next_action"] = next_action_for(
            row["category"],
            row["kind"],
            row["boot_readiness"],
            row["preparation_status"],
            missing,
        )
        row["readiness_detail"] = readiness_detail_for(row["boot_readiness"], row["preparation_status"], missing)
        conn.execute(
            """
            INSERT INTO images (
                id, name, display_name, category, kind, rel_path, relative_path, size_bytes, sha256,
                menu_enabled, boot_method, description, scanned_at,
                mtime_ns, sha256_cached, scan_status, boot_readiness, source_role, preparation_status,
                missing_artifacts, next_action, readiness_detail, last_seen_at, updated_at, missing_since
            )
            VALUES (
                :id, :name, :display_name, :category, :kind, :rel_path, :relative_path, :size_bytes, :sha256,
                :menu_enabled, :boot_method, :description, :scanned_at,
                :mtime_ns, :sha256_cached, :scan_status, :boot_readiness, :source_role, :preparation_status,
                :missing_artifacts, :next_action, :readiness_detail, :last_seen_at, :updated_at, :missing_since
            )
            ON CONFLICT(rel_path) DO UPDATE SET
                name=excluded.name,
                display_name=excluded.display_name,
                category=excluded.category,
                kind=excluded.kind,
                relative_path=excluded.relative_path,
                size_bytes=excluded.size_bytes,
                sha256=excluded.sha256,
                mtime_ns=excluded.mtime_ns,
                sha256_cached=excluded.sha256_cached,
                scan_status=excluded.scan_status,
                boot_readiness=excluded.boot_readiness,
                source_role=excluded.source_role,
                preparation_status=excluded.preparation_status,
                missing_artifacts=excluded.missing_artifacts,
                next_action=excluded.next_action,
                readiness_detail=excluded.readiness_detail,
                boot_method=excluded.boot_method,
                scanned_at=excluded.scanned_at,
                last_seen_at=excluded.last_seen_at,
                updated_at=excluded.updated_at,
                missing_since=NULL
            """,
            row,
        )
        rows.append(row)

    missing_paths = sorted(set(existing) - seen)
    for rel_path in missing_paths:
        old = existing[rel_path]
        missing_since = old.get("missing_since") or now
        conn.execute(
            """
            UPDATE images
            SET scan_status = 'missing',
                boot_readiness = 'missing',
                preparation_status = 'missing',
                missing_artifacts = '[]',
                next_action = '文件已不存在，请重新扫描或放回原路径。',
                readiness_detail = '文件缺失。',
                updated_at = ?,
                missing_since = ?
            WHERE rel_path = ?
            """,
            (now, missing_since, rel_path),
        )
    conn.commit()
    rows = [
        image_payload(dict(row))
        for row in conn.execute("SELECT * FROM images ORDER BY category, rel_path")
    ]
    conn.close()
    write_menu(rows)
    return rows


def list_images() -> list[dict]:
    conn = connect_db()
    rows = [
        image_payload(dict(row))
        for row in conn.execute("SELECT * FROM images ORDER BY category, rel_path")
    ]
    conn.close()
    return rows


def list_images_readonly_snapshot() -> list[dict]:
    if not DB_PATH.is_file() or DB_PATH.is_symlink():
        raise FileNotFoundError("metadata database is not available")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = [
            image_payload(dict(row))
            for row in conn.execute("SELECT * FROM images ORDER BY category, rel_path")
        ]
    finally:
        conn.close()
    return rows


def image_payload(row: dict) -> dict:
    row["display_name"] = row.get("display_name") or row.get("name", "")
    row["relative_path"] = row.get("relative_path") or row.get("rel_path", "")
    row["url"] = f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/{row['rel_path']}"
    row["sha256_cached"] = bool(row.get("sha256_cached"))
    try:
        row["missing_artifacts"] = json.loads(row.get("missing_artifacts") or "[]")
    except json.JSONDecodeError:
        row["missing_artifacts"] = []
    row.update(detect_image_strategy(row))
    row["is_primary_inventory"] = row.get("visibility") == "primary"
    return row


def images_inventory_payload(rows: list[dict]) -> dict:
    artifacts_by_group: dict[str, list[dict]] = {}
    source_images: list[dict] = []
    for row in rows:
        if row.get("is_primary_inventory"):
            source_images.append(dict(row))
        else:
            artifacts_by_group.setdefault(row.get("source_group") or "", []).append(row)

    source_by_group = {
        source.get("source_group") or "": source.get("relative_path") or source.get("rel_path") or ""
        for source in source_images
    }
    for source in source_images:
        group = source.get("source_group") or ""
        artifacts = artifacts_by_group.get(group, [])
        parent_relative_path = source.get("relative_path") or source.get("rel_path") or ""
        source["artifact_count"] = len(artifacts)
        source["artifacts"] = [
            {
                "id": artifact.get("id", ""),
                "object_type": artifact.get("object_type", "derived_boot_artifact"),
                "name": artifact.get("name", ""),
                "parent_relative_path": parent_relative_path,
                "relative_path": artifact.get("relative_path") or artifact.get("rel_path", ""),
                "kind": artifact.get("kind", ""),
                "artifact_role": artifact.get("artifact_role", ""),
                "size_bytes": artifact.get("size_bytes", 0),
                "boot_readiness": artifact.get("boot_readiness", ""),
                "preparation_status": artifact.get("preparation_status", ""),
                "source_role": artifact.get("source_role", ""),
            }
            for artifact in artifacts
        ]

    derived_artifacts = []
    for row in rows:
        if row.get("is_primary_inventory"):
            continue
        artifact = dict(row)
        artifact["parent_relative_path"] = source_by_group.get(artifact.get("source_group") or "", "")
        derived_artifacts.append(artifact)

    return {
        "schema_version": "synaboot.images.iso-first.v1",
        "inventory_mode": "source_iso_first",
        "compatibility_mode": "legacy_images_retained",
        "images": rows,
        "source_images": source_images,
        "artifacts": derived_artifacts,
        "derived_artifacts": derived_artifacts,
        "summary": {
            "total_files": len(rows),
            "source_image_count": len(source_images),
            "artifact_count": sum(1 for row in rows if not row.get("is_primary_inventory")),
            "ready_source_count": sum(1 for row in source_images if row.get("strategy_status") in {"ready", "needs_hotpe"}),
            "research_required_count": sum(1 for row in source_images if row.get("strategy_status") == "research_required"),
            "unsupported_source_count": sum(1 for row in source_images if row.get("strategy_status") == "unsupported_source_only"),
        },
    }


def get_image(image_id: str) -> dict | None:
    conn = connect_db()
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return image_payload(dict(row))


def set_image_menu_enabled(image_id: str, enabled: bool) -> dict | None:
    conn = connect_db()
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if row is None:
        conn.close()
        return None
    conn.execute("UPDATE images SET menu_enabled = ? WHERE id = ?", (1 if enabled else 0, image_id))
    conn.commit()
    conn.close()
    return get_image(image_id)


def set_image_metadata(image_id: str, payload: dict) -> dict | None:
    conn = connect_db()
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if row is None:
        conn.close()
        return None
    now = int(time.time())
    display_name = safe_text(payload.get("display_name"), 80) or row["display_name"] or row["name"]
    version = safe_text(payload.get("version"), 64)
    architecture = safe_text(payload.get("architecture"), 32)
    description = safe_text(payload.get("description"), 500)
    conn.execute(
        """
        UPDATE images
        SET display_name = ?,
            version = ?,
            architecture = ?,
            description = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (display_name, version, architecture, description, now, image_id),
    )
    conn.commit()
    conn.close()
    return get_image(image_id)


def menu_rows(rows: list[dict] | None = None) -> list[dict]:
    if rows is not None:
        return rows
    return list_images()


def row_enabled(row: dict) -> bool:
    return int(row.get("menu_enabled") or 0) == 1 and row.get("scan_status") == "present"


def hotpe_menu_ready(rows: list[dict]) -> bool:
    required = set(hotpe_required_artifacts())
    enabled_present = {row["rel_path"] for row in rows if row_enabled(row)}
    return required.issubset(enabled_present)


def linux_boot_entries(rows: list[dict]) -> list[dict]:
    entries: dict[str, dict] = {}
    ready_rows = [
        row
        for row in rows
        if row_enabled(row)
        and row.get("category") == "linux"
        and row.get("boot_readiness") == "ready"
    ]
    for row in ready_rows:
        rel_path = row["rel_path"]
        base = linux_base_dir(rel_path)
        entry = entries.setdefault(base, {"base": base, "iso": None, "kernel": None, "initrd": None, "livefs": None})
        if rel_path.lower().endswith(".iso"):
            entry["iso"] = rel_path
        elif rel_path.endswith("/casper/vmlinuz"):
            entry["kernel"] = rel_path
        elif rel_path.endswith("/casper/initrd"):
            entry["initrd"] = rel_path
        elif "/casper/" in rel_path and rel_path.endswith(".squashfs"):
            entry["livefs"] = rel_path
    return [
        entry
        for entry in entries.values()
        if entry.get("iso") and entry.get("kernel") and entry.get("initrd") and entry.get("livefs")
    ]


def windows_hotpe_available(rows: list[dict]) -> bool:
    return hotpe_menu_ready(rows) and any(
        row_enabled(row)
        and row.get("category") == "windows"
        and row.get("boot_readiness") == "needs_hotpe"
        for row in rows
    )


def windows_wimboot_ready(rows: list[dict]) -> bool:
    present = {row["rel_path"] for row in rows if row_enabled(row)}
    return set(windows_wimboot_required_artifacts()).issubset(present)


def readonly_image_rows_for_status() -> tuple[list[dict], str]:
    try:
        return list_images_readonly_snapshot(), "readonly_metadata"
    except FileNotFoundError:
        return [], "metadata_unavailable"


def windows_install_candidates(rows: list[dict] | None = None) -> dict:
    image_rows = rows if rows is not None else readonly_image_rows_for_status()[0]
    candidates = [
        {
            "id": row.get("id", ""),
            "display_name": row.get("display_name") or row.get("name", ""),
            "relative_path": row.get("relative_path") or row.get("rel_path", ""),
            "kind": row.get("kind", ""),
            "url": row.get("url", ""),
            "boot_method": row.get("boot_method", ""),
            "boot_readiness": row.get("boot_readiness", ""),
            "preparation_status": row.get("preparation_status", ""),
            "hotpe_required": row.get("boot_readiness") == "needs_hotpe",
            "direct_ipxe_supported": False,
            "client_install_test_status": "not_tested",
            "next_action": row.get("next_action", ""),
        }
        for row in image_rows
        if row_enabled(row)
        and row.get("category") == "windows"
        and row.get("kind") in {"iso", "wim", "esd"}
    ]
    return {
        "schema_version": "synaboot.windows-install-candidates.v1",
        "read_only": True,
        "direct_ipxe_supported": False,
        "client_install_test_status": "not_tested",
        "candidates": candidates,
        "candidate_count": len(candidates),
        "notes": [
            "Windows ISO/WIM/ESD entries are treated as source media for HotPE-assisted installation.",
            "SynaBoot does not generate a direct generic iPXE boot entry for raw Windows ISO files.",
            "A real HotPE client must verify opening the repository URL and launching the Win11 installer.",
        ],
    }


def hotpe_readiness_status() -> dict:
    rows, source = readonly_image_rows_for_status()
    present_paths = {row.get("relative_path") or row.get("rel_path", "") for row in rows if row.get("scan_status") == "present"}
    required = hotpe_required_artifacts()
    missing = [path for path in required if path not in present_paths]
    artifacts = [
        {
            "path": path,
            "present": path in present_paths,
            "role": path.rsplit("/", 1)[-1],
        }
        for path in required
    ]
    source_isos = [
        row
        for row in rows
        if row_enabled(row)
        and row.get("category") == "pe"
        and row.get("kind") == "iso"
        and "pe/hotpe/" in (row.get("relative_path") or row.get("rel_path", ""))
    ]
    hotpe_ready = hotpe_menu_ready(rows)
    windows = windows_install_candidates(rows)
    windows_candidates = windows["candidates"]
    windows_via_hotpe_candidate = hotpe_ready and bool(windows_candidates)
    status = "ready_for_client_test" if windows_via_hotpe_candidate else "blocked_missing_hotpe_artifacts"
    if not source_isos:
        status = "blocked_missing_hotpe_source_iso"
    if source == "metadata_unavailable":
        status = "metadata_unavailable"
    return {
        "schema_version": "synaboot.hotpe-readiness.v1",
        "read_only": True,
        "source": source,
        "status": status,
        "hotpe_source_iso_present": bool(source_isos),
        "hotpe_source_isos": [
            {
                "id": row.get("id", ""),
                "display_name": row.get("display_name") or row.get("name", ""),
                "relative_path": row.get("relative_path") or row.get("rel_path", ""),
                "url": row.get("url", ""),
                "preparation_status": row.get("preparation_status", ""),
                "boot_readiness": row.get("boot_readiness", ""),
                "next_action": row.get("next_action", ""),
            }
            for row in source_isos
        ],
        "required_artifacts": artifacts,
        "required_artifacts_present": len(missing) == 0,
        "missing_artifacts": missing,
        "hotpe_menu_ready": hotpe_ready,
        "windows_iso_candidates": windows_candidates,
        "windows_iso_candidate_count": len(windows_candidates),
        "windows_via_hotpe_candidate": windows_via_hotpe_candidate,
        "client_boot_test_status": "not_tested",
        "client_install_test_status": "not_tested",
        "repository_urls": {
            "images": f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/",
            "windows": f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/windows/",
            "hotpe": f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/pe/hotpe/",
        },
        "next_actions": [
            "Extract or provide wimboot, bootmgr, BCD, boot.sdi, and boot.wim under data/images/pe/hotpe/.",
            "Regenerate menu.ipxe after HotPE artifacts are present.",
            "Boot a real client into HotPE and verify it can open the Windows repository URL.",
            "Inside HotPE, open the uploaded Win11 image and verify the installer reaches disk selection.",
        ],
        "non_goals": [
            "This endpoint does not start DHCP, ProxyDHCP, TFTP, Samba, or any boot service.",
            "This endpoint does not prove a real client can install Windows until client evidence is recorded.",
        ],
    }


def ipxe_label(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").lower()[:48] or "entry"


def ipxe_url_path(rel_path: str) -> str:
    return quote(rel_path, safe="/._-")


def ipxe_text(value: str) -> str:
    return SAFE_IPXE_TEXT_RE.sub("-", value).strip()[:96] or "entry"


def nfs_boot_source(base: str) -> str:
    # Ubuntu casper 原生支持 NFS netboot；每个发行版目录使用独立只读 export。
    share_name = Path(base).name
    if not share_name:
        share_name = "ubuntu-livefs"
    return f"{SYNABOOT_NFS_SERVER}:/{share_name}"


def boot_target_catalog(_rows: list[dict] | None = None) -> list[dict]:
    rows = menu_rows(_rows)
    targets: list[dict] = []
    if windows_wimboot_ready(rows):
        targets.append(
            {
                "target": "windows_setup",
                "label": "Windows installer",
                "kind": "windows",
                "software_assignment_enabled": True,
                "postinstall_status": "setupcomplete_helper_ready",
                "postinstall_detail": "Windows 使用 HotPE/WinPE 显式注入 SetupComplete.cmd，首次启动后由 runner 从官方来源下载并安装软件。",
            }
        )
    if hotpe_menu_ready(rows):
        targets.append(
            {
                "target": "hotpe",
                "label": "HotPE recovery environment",
                "kind": "hotpe",
                "software_assignment_enabled": False,
                "postinstall_status": "not_applicable",
                "postinstall_detail": "HotPE 是维护/安装辅助环境，不作为普通业务软件的自动安装目标。",
            }
        )
    linux_entries = linux_boot_entries(rows)
    for index, entry in enumerate(linux_entries, start=1):
        label = f"linux_{ipxe_label(entry['base'])}"
        targets.append(
            {
                "target": label,
                "label": entry["base"],
                "kind": "linux",
                "software_assignment_enabled": True,
                "postinstall_status": "nocloud_ready_pending_client_verification",
                "postinstall_detail": "Ubuntu/Linux 使用 NoCloud autoinstall late-commands 写入首次启动 runner，客户端从官方来源下载软件。",
            }
        )
    return targets


def boot_target_label(target: str, _rows: list[dict] | None = None) -> str:
    for item in boot_target_catalog(_rows):
        if item["target"] == target:
            return str(item["label"])
    return ""


def flashpxe_console_lines() -> list[str]:
    return [
        "console --x 1024 --y 768 || echo Console resize skipped",
        "console --picture ${boot-url}/flashpxe-logo.png || echo FlashPXE picture skipped",
        "colour --basic 0 --rgb 0x000000 0 || echo Colour command skipped",
        "colour --basic 6 --rgb 0x00aaaa 6 || echo Colour command skipped",
        "colour --basic 7 --rgb 0xffffff 7 || echo Colour command skipped",
        "colour --basic 1 --rgb 0x00aaaa 1 || echo Colour command skipped",
        "cpair --foreground 7 --background 0 0 || echo Colour pair skipped",
        "cpair --foreground 6 --background 0 1 || echo Colour pair skipped",
        "cpair --foreground 7 --background 1 2 || echo Colour pair skipped",
        "cpair --foreground 6 --background 0 3 || echo Colour pair skipped",
    ]


def write_menu(_rows: list[dict] | None = None) -> str:
    ensure_dirs()
    rows = menu_rows(_rows)
    hotpe_ready = hotpe_menu_ready(rows)
    linux_entries = linux_boot_entries(rows)
    windows_ready = windows_wimboot_ready(rows)
    for index, entry in enumerate(linux_entries, start=1):
        entry["label"] = f"linux_{ipxe_label(entry['base'])}"
        entry["key"] = str(index) if index <= 9 else ""
    default_target = "windows_setup" if windows_ready else ("hotpe" if hotpe_ready else (linux_entries[0]["label"] if linux_entries else "shell"))
    hotpe_suffix = "  [default]" if default_target == "hotpe" else ""
    windows_suffix = "  [default]" if default_target == "windows_setup" else ""
    lines = [
        "#!ipxe",
        "",
        f"set server-ip {SERVER_IP}",
        f"set base-url http://${{server-ip}}:{SYNABOOT_PORT}",
        "set boot-url ${base-url}/boot",
        "set image-url ${base-url}/images",
        "isset ${platform} || set platform unknown",
        "isset ${synaboot-postinstall-args} || set synaboot-postinstall-args",
        "",
        ":start",
        *flashpxe_console_lines(),
        "menu FlashPXE",
        "item --gap --                                      FlashPXE",
        "item --gap --                                A fast netboot console",
        "item --gap --          ${server-ip}    ${platform}    ${base-url}",
        "item --gap --          ----------------------------------------------------------------------------",
        "item --gap --          Deployment Mode",
        "item --key a manual_menu   (A) Active install: choose an image manually  [default]",
        "item --key p passive_wait  (P) Passive install: wait for admin assignment",
        "item --gap --          ----------------------------------------------------------------------------",
        "item --key s shell         (S) Open iPXE shell",
        "item --key r reboot        (R) Reboot client",
        "item --key o poweroff      (O) Power off client",
        "choose --default manual_menu --timeout 15000 target && goto ${target} || goto start",
        "",
        ":manual_menu",
        "menu FlashPXE",
        "item --gap --                                      FlashPXE",
        "item --gap --                                Active install menu",
        "item --gap --          ${server-ip}    ${platform}    ${base-url}",
        "item --gap --          ----------------------------------------------------------------------------",
    ]
    if windows_ready:
        lines.extend(
            [
                "item --gap --          ISO Boot Menu",
                "item --gap --          SIZE      IMAGE",
                f"item --key w windows_setup  (W) Windows installer{windows_suffix}",
            ]
        )
    if hotpe_ready:
        lines.extend(
            [
                f"item --key h hotpe          (H) HotPE recovery environment{hotpe_suffix}",
            ]
        )
    if linux_entries:
        if not windows_ready and not hotpe_ready:
            lines.extend(["item --gap --          ISO Boot Menu", "item --gap --          SIZE      IMAGE"])
        for entry in linux_entries:
            key = entry["key"]
            key_prefix = f"({key}) " if key else "    "
            key_arg = f"--key {key} " if key else ""
            default_suffix = "  [default]" if default_target == entry["label"] else ""
            lines.append(f"item {key_arg}{entry['label']:<16} {key_prefix}{ipxe_text(entry['base'])}{default_suffix}")
    if not hotpe_ready and not linux_entries and not windows_ready:
        lines.extend(
            [
                "item --gap --          [ No Ready Boot Entries ]",
                "item --gap --          Prepare HotPE or Linux images from the admin UI.",
            ]
        )
    lines.extend(
        [
            "item --gap --          ----------------------------------------------------------------------------",
            "item --gap --          Tools Menu",
            "item --key b start          (B) Back to deployment mode selector",
            "item --key s shell          (S) Open iPXE shell",
            "item --key r reboot         (R) Reboot client",
            "item --key p poweroff       (P) Power off client",
        ]
    )
    lines.extend(
        [
            f"choose --default {default_target} --timeout 15000 target && goto ${{target}} || goto start",
            "",
            ":passive_wait",
            "echo Registering this client for admin-controlled deployment...",
            "chain --replace ${base-url}/api/ipxe/register?mac=${net0/mac}&uuid=${uuid}&serial=${serial}&asset=${asset}&manufacturer=${manufacturer}&product=${product}&platform=${platform}&buildarch=${buildarch}&ip=${net0/ip} || goto passive_failed",
            "",
            ":passive_failed",
            "echo Could not enter passive deployment mode.",
            "echo Press B to return, R to reboot, O to power off, or wait to retry.",
            "menu FlashPXE Passive install error",
            "item --key b start          (B) Back to deployment mode selector",
            "item --key r reboot         (R) Reboot client",
            "item --key o poweroff       (O) Power off client",
            "item retry                  Retry passive registration",
            "choose --default retry --timeout 5000 target && goto ${target} || goto retry",
            ":retry",
            "goto passive_wait",
            "",
            ":hotpe",
        ]
    )
    if hotpe_ready:
        lines.extend(
            [
                "echo Loading HotPE...",
                "imgfree",
                "kernel ${image-url}/pe/hotpe/wimboot pause",
                "initrd -n bootmgfw.efi ${image-url}/pe/hotpe/bootx64.efi bootmgfw.efi",
                "initrd -n BCD ${image-url}/pe/hotpe/BCD BCD",
                "initrd -n boot.sdi ${image-url}/pe/hotpe/boot.sdi boot.sdi",
                "initrd -n boot.wim ${image-url}/pe/hotpe/boot.wim boot.wim",
                "boot || goto boot_failed",
            ]
        )
    else:
        lines.extend(
            [
                "echo HotPE files are not enabled or not ready.",
                "goto start",
            ]
        )
    if windows_ready:
        lines.extend(
            [
                "",
                ":windows_setup",
                "echo Loading Windows installer...",
                "imgfree",
                "kernel ${image-url}/pe/hotpe/wimboot",
                "initrd -n BCD ${image-url}/windows/win11/boot/BCD BCD",
                "initrd -n boot.sdi ${image-url}/windows/win11/boot/boot.sdi boot.sdi",
                "initrd -n boot.wim ${image-url}/windows/win11/boot/boot.wim boot.wim",
                "boot || goto boot_failed",
            ]
        )
    for entry in linux_entries:
        kernel_args = f"ip=dhcp boot=casper netboot=nfs nfsroot={nfs_boot_source(entry['base'])}"
        if "ubuntu-24.04" in entry["base"]:
            kernel_args = f"{kernel_args} nomodeset"
        lines.extend(
            [
                "",
                f":{entry['label']}",
                f"echo Loading Ubuntu/Linux NFS livefs from {ipxe_text(entry['base'])}...",
                f"echo NFS source: {nfs_boot_source(entry['base'])}",
                "echo This mode mounts casper/*.squashfs from the read-only NFS export.",
                f"kernel ${{base-url}}/images/{ipxe_url_path(entry['kernel'])} {kernel_args} ${{synaboot-postinstall-args}} --- quiet splash",
                f"initrd ${{base-url}}/images/{ipxe_url_path(entry['initrd'])}",
                "boot || goto boot_failed",
            ]
        )
    lines.extend(
        [
            "",
            ":shell",
            "shell",
            "goto start",
            "",
            ":reboot",
            "reboot",
            "",
            ":poweroff",
            "poweroff",
            "",
            ":boot_failed",
            "echo Boot failed. Check image readiness in the SynaBoot admin UI.",
            "echo Press any key to return to the deployment console.",
            "prompt",
            "goto start",
            "",
        ]
    )
    menu = "\n".join(lines)
    (BOOT_DIR / "menu.ipxe").write_text(menu, encoding="utf-8")
    return menu


def read_menu() -> str:
    menu_path = BOOT_DIR / "menu.ipxe"
    if menu_path.is_file():
        return menu_path.read_text(encoding="utf-8")
    return f"""#!ipxe

set server-ip {SERVER_IP}
set base-url http://${{server-ip}}:{SYNABOOT_PORT}
set image-url ${{base-url}}/images
isset ${{platform}} || set platform unknown

:start
menu SynaBoot Deployment Console
item --gap --          ----------------------------------------
item --gap --          Phase 2 HTTP Boot | ${{platform}} | ${{base-url}}
item --gap --          Zero-intrusion mode: DHCP/ProxyDHCP/TFTP disabled
item --gap --          ----------------------------------------
item --gap --          [ No Ready Boot Entries ]
item --gap --          Prepare HotPE or Linux images from the admin UI.
item --gap --          [ Tools ]
item --key b start          (B) Back to deployment mode selector
item --key s shell          (S) Open iPXE shell
item --key r reboot         (R) Reboot client
item --key p poweroff       (P) Power off client
choose --default shell --timeout 15000 target && goto ${{target}} || goto start

:shell
shell
goto start

:reboot
reboot

:poweroff
poweroff

:boot_failed
echo Boot failed. Check image readiness in the SynaBoot admin UI.
echo Press any key to return to the deployment console.
prompt
goto start
"""


def query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    value = query.get(key, [default])[0]
    return str(value or default).strip()[:160]


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_is_valid(provided: str, expected_hash: str) -> bool:
    if not provided or not expected_hash:
        return False
    return hmac.compare_digest(hash_session_token(provided), expected_hash)


def ipxe_client_params(handler: BaseHTTPRequestHandler) -> dict:
    parsed = urlparse(handler.path)
    query = parse_qs(parsed.query, keep_blank_values=True)
    observed_ip = handler.client_address[0]
    mac = query_value(query, "mac").lower()
    uuid_value = query_value(query, "uuid").lower()
    return {
        "mac": mac,
        "uuid": uuid_value,
        "serial": query_value(query, "serial"),
        "asset": query_value(query, "asset"),
        "manufacturer": query_value(query, "manufacturer"),
        "product": query_value(query, "product"),
        "platform": query_value(query, "platform", "unknown"),
        "buildarch": query_value(query, "buildarch", "unknown"),
        "ip": observed_ip,
        "claimed_ip": query_value(query, "ip"),
    }


def register_client_session(handler: BaseHTTPRequestHandler) -> dict:
    params = ipxe_client_params(handler)
    now = int(time.time())
    expires_at = now + 900
    conn = connect_db()
    evidence = {
        "source": "ipxe_register",
        "observed_ip": params["ip"],
        "claimed_ip": params["claimed_ip"],
        "user_agent": handler.headers.get("User-Agent", "")[:160],
    }
    session_id = uuid.uuid4().hex
    token = uuid.uuid4().hex
    conn.execute(
        """
        INSERT INTO client_sessions (
            session_id, session_token_hash, mac, ip, uuid, serial, asset,
            manufacturer, product, platform, buildarch, state,
            selected_target, selected_label, first_seen_at, last_seen_at,
            expires_at, evidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            hash_session_token(token),
            params["mac"],
            params["ip"],
            params["uuid"],
            params["serial"],
            params["asset"],
            params["manufacturer"],
            params["product"],
            params["platform"],
            params["buildarch"],
            "waiting_assignment",
            "",
            "",
            now,
            now,
            expires_at,
            json.dumps(evidence, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()
    return {"session_id": session_id, "token": token, **params}


def passive_register_script(handler: BaseHTTPRequestHandler) -> str:
    session = register_client_session(handler)
    return f"""#!ipxe

set server-ip {SERVER_IP}
set boot-url http://${{server-ip}}:{SYNABOOT_PORT}/boot
set session-id {session['session_id']}
set session-token {session['token']}
set base-url http://{SERVER_IP}:{SYNABOOT_PORT}

:wait
{chr(10).join(flashpxe_console_lines())}
menu FlashPXE
item --gap --                                      FlashPXE
item --gap --                           Passive install waiting room
item --gap --          Waiting for admin deployment assignment
item --gap --          MAC: {ipxe_text(session.get('mac') or 'unknown')}
item --gap --          UUID: {ipxe_text(session.get('uuid') or 'unknown')}
item --gap --          Session: {session['session_id']}
item --gap --          ----------------------------------------------------------------------------
item --key b manual    (B) Return to deployment mode selector
item --key s shell     (S) Open iPXE shell
item --key r reboot    (R) Reboot client
item --key o poweroff  (O) Power off client
item refresh           Refresh assignment status
choose --default refresh --timeout 5000 target && goto ${{target}} || goto refresh

:refresh
chain --replace ${{base-url}}/api/ipxe/wait?session_id=${{session-id}}&token=${{session-token}} || goto wait

:manual
chain --replace ${{base-url}}/boot/menu.ipxe || goto wait

:shell
shell
goto wait

:reboot
reboot

:poweroff
poweroff
"""


def assigned_boot_script(target: str, assignment_id: str = "", session_id: str = "", boot_token: str = "") -> str:
    rows = menu_rows()
    targets = {item["target"]: item for item in boot_target_catalog(rows)}
    target_info = targets.get(target)
    if target_info is None:
        return passive_wait_script("", "", "Assigned target is no longer ready.")
    menu_lines = read_menu().splitlines()
    if menu_lines and menu_lines[0].strip() == "#!ipxe":
        menu_lines = menu_lines[1:]
    menu = "\n".join(menu_lines)
    assignment_token = ipxe_text(boot_token)
    base_assignment_url = f"${{base-url}}/api/postinstall/assignments/{ipxe_text(assignment_id)}"
    prelude_lines = [
        f"set synaboot-assignment-id {ipxe_text(assignment_id)}",
        f"set synaboot-session-id {ipxe_text(session_id)}",
        f"set synaboot-boot-token {assignment_token}",
    ]
    if target_info["kind"] == "linux":
        prelude_lines.extend(
            [
                f"set synaboot-seed-url {base_assignment_url}/nocloud/{ipxe_text(session_id)}/{assignment_token}/",
                f"set synaboot-plan-url {base_assignment_url}/plan?session_id={ipxe_text(session_id)}&token={assignment_token}",
                f"set synaboot-runner-url {base_assignment_url}/runner.sh?session_id={ipxe_text(session_id)}&token={assignment_token}",
                "set synaboot-postinstall-args autoinstall ds=nocloud-net\\;s=${synaboot-seed-url} synaboot.assignment_id=${synaboot-assignment-id} synaboot.session_id=${synaboot-session-id} synaboot.plan_url=${synaboot-plan-url} synaboot.runner_url=${synaboot-runner-url}",
            ]
        )
    elif target_info["kind"] == "windows":
        prelude_lines.extend(
            [
                f"set synaboot-plan-url {base_assignment_url}/plan?session_id={ipxe_text(session_id)}&token={assignment_token}",
                f"set synaboot-windows-runner-url {base_assignment_url}/runner.ps1?session_id={ipxe_text(session_id)}&token={assignment_token}",
                f"set synaboot-setupcomplete-url {base_assignment_url}/setupcomplete.cmd?session_id={ipxe_text(session_id)}&token={assignment_token}",
                "set synaboot-postinstall-args",
            ]
        )
    else:
        prelude_lines.append("set synaboot-postinstall-args")
    return f"""#!ipxe

set server-ip {SERVER_IP}
set base-url http://${{server-ip}}:{SYNABOOT_PORT}
set boot-url ${{base-url}}/boot
set image-url ${{base-url}}/images
isset ${{platform}} || set platform unknown
{chr(10).join(prelude_lines)}

echo FlashPXE admin assignment received: {ipxe_text(target)}
echo Assignment: {ipxe_text(assignment_id)}
goto {target}

{menu}
"""


def passive_wait_script(session_id: str, token: str, message: str = "No assignment yet.") -> str:
    sid = ipxe_text(session_id or "unknown")
    safe_message = ipxe_text(message)
    return f"""#!ipxe

set server-ip {SERVER_IP}
set boot-url http://${{server-ip}}:{SYNABOOT_PORT}/boot
set session-id {sid}
set session-token {ipxe_text(token)}
set base-url http://{SERVER_IP}:{SYNABOOT_PORT}

:wait
{chr(10).join(flashpxe_console_lines())}
menu FlashPXE
item --gap --                                      FlashPXE
item --gap --                           Passive install waiting room
item --gap --          {safe_message}
item --gap --          Session: {sid}
item --gap --          Waiting for admin deployment assignment
item --gap --          ----------------------------------------------------------------------------
item --key b manual    (B) Return to deployment mode selector
item --key s shell     (S) Open iPXE shell
item --key r reboot    (R) Reboot client
item --key o poweroff  (O) Power off client
item refresh           Refresh assignment status
choose --default refresh --timeout 5000 target && goto ${{target}} || goto refresh

:refresh
chain --replace ${{base-url}}/api/ipxe/wait?session_id=${{session-id}}&token=${{session-token}} || goto wait

:manual
chain --replace ${{base-url}}/boot/menu.ipxe || goto wait

:shell
shell
goto wait

:reboot
reboot

:poweroff
poweroff
"""


def passive_wait_response(handler: BaseHTTPRequestHandler) -> str:
    query = parse_qs(urlparse(handler.path).query, keep_blank_values=True)
    session_id = query_value(query, "session_id")
    token = query_value(query, "token")
    now = int(time.time())
    conn = connect_db()
    row = conn.execute("SELECT * FROM client_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None or not token_is_valid(token, row["session_token_hash"]):
        conn.close()
        return passive_wait_script("", "", "Session expired. Please re-enter passive mode.")
    conn.execute(
        """
        UPDATE client_sessions
        SET last_seen_at = ?, expires_at = ?,
            state = CASE WHEN selected_target = '' THEN 'waiting_assignment' ELSE state END
        WHERE session_id = ?
        """,
        (now, now + 900, session_id),
    )
    conn.commit()
    selected_target = row["selected_target"]
    assignment = latest_assignment_for_session(session_id) if selected_target else None
    if selected_target:
        conn.execute(
            "UPDATE client_sessions SET state = 'booting', last_seen_at = ?, expires_at = ? WHERE session_id = ?",
            (now, now + 900, session_id),
        )
        conn.commit()
    conn.close()
    if selected_target:
        if not assignment:
            return passive_wait_script(session_id, token, "Assigned task is missing. Please wait for admin.")
        try:
            boot_token = issue_assignment_boot_token(assignment["id"], session_id, token)
        except ValueError:
            return passive_wait_script("", "", "Session expired. Please re-enter passive mode.")
        return assigned_boot_script(selected_target, assignment["id"], session_id, boot_token)
    return passive_wait_script(session_id, token)


def client_session_payload(row: sqlite3.Row) -> dict:
    now = int(time.time())
    evidence = json.loads(row["evidence"] or "{}")
    state = row["state"]
    if row["expires_at"] < now:
        state = "timed_out"
    latest_assignment = latest_assignment_for_session(row["session_id"])
    assignment_summary = None
    if latest_assignment:
        events = list_assignment_session_events(latest_assignment["id"], row["session_id"], limit=10)
        variants = latest_assignment.get("resolved_software_plan", {}).get("variants", [])
        assignment_summary = {
            "id": latest_assignment["id"],
            "boot_target": latest_assignment["boot_target"],
            "boot_label": latest_assignment["boot_label"],
            "status": latest_assignment["status"],
            "session_event_summary": assignment_event_summary(events),
            "software_count": len(variants),
            "software_labels": [
                variant.get("package_name") or variant.get("id", "")
                for variant in variants
                if variant.get("package_name") or variant.get("id")
            ],
            "event_summary": assignment_event_summary(events),
        }
    return {
        "session_id": row["session_id"],
        "mac": row["mac"],
        "ip": row["ip"],
        "uuid": row["uuid"],
        "serial": row["serial"],
        "asset": row["asset"],
        "manufacturer": row["manufacturer"],
        "product": row["product"],
        "platform": row["platform"],
        "buildarch": row["buildarch"],
        "state": state,
        "selected_target": row["selected_target"],
        "selected_label": row["selected_label"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "expires_at": row["expires_at"],
        "online": row["expires_at"] >= now,
        "evidence": evidence,
        "latest_assignment": assignment_summary,
    }


def redacted_client_session_payload(row: sqlite3.Row) -> dict:
    full = client_session_payload(row)
    return {
        "session_id": full["session_id"],
        "state": full["state"],
        "selected_target": full["selected_target"],
        "selected_label": full["selected_label"],
        "platform": full["platform"],
        "buildarch": full["buildarch"],
        "first_seen_at": full["first_seen_at"],
        "last_seen_at": full["last_seen_at"],
        "expires_at": full["expires_at"],
        "online": full["online"],
        "redacted": True,
    }


def list_client_sessions(include_private: bool = False) -> dict:
    conn = connect_db()
    rows = conn.execute("SELECT * FROM client_sessions ORDER BY last_seen_at DESC LIMIT 100").fetchall()
    sessions = [client_session_payload(row) if include_private else redacted_client_session_payload(row) for row in rows]
    conn.close()
    return {
        "schema_version": "synaboot.client-sessions.v1",
        "access": "admin" if include_private else "redacted",
        "sessions": sessions,
        "assignable_targets": boot_target_catalog(),
        "summary": {
            "total": len(sessions),
            "online": sum(1 for item in sessions if item["online"]),
            "waiting": sum(1 for item in sessions if item["online"] and item["state"] == "waiting_assignment"),
            "assigned": sum(1 for item in sessions if item["online"] and bool(item["selected_target"])),
        },
    }


def get_client_session(session_id: str) -> dict | None:
    conn = connect_db()
    row = conn.execute("SELECT * FROM client_sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    return client_session_payload(row) if row is not None else None


def admin_session_payload(authenticated: bool) -> dict:
    return {
        "schema_version": "synaboot.admin-session.v1",
        "admin_configured": bool(ADMIN_TOKEN),
        "authenticated": authenticated,
        "write_actions": {
            "client_assignment": authenticated,
            "local_iso_scan": authenticated,
            "menu_generate": authenticated,
            "software_market": authenticated,
        },
        "image_drop_folder": IMAGES_DIR.as_posix(),
        "auto_refresh_seconds": 300,
    }


def list_software_profiles(os_family: str | None = None) -> list[dict]:
    conn = connect_db()
    if os_family:
        rows = conn.execute(
            "SELECT * FROM software_profiles WHERE os_family = ? ORDER BY name COLLATE NOCASE",
            (os_family,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM software_profiles ORDER BY os_family, name COLLATE NOCASE").fetchall()
    conn.close()
    variants_by_id = {variant["id"]: variant for variant in list_software_variants()}
    profiles: list[dict] = []
    for row in rows:
        variant_ids = json.loads(row["variant_ids"] or "[]")
        variants = [variants_by_id[variant_id] for variant_id in variant_ids if variant_id in variants_by_id]
        profiles.append(
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "os_family": row["os_family"],
                "variant_ids": variant_ids,
                "variants": variants,
                "status": row["status"],
                "review_status": row["review_status"],
                "risk_level": row["risk_level"],
                "assignable": row["status"] == "available"
                and row["review_status"] in ASSIGNABLE_SOFTWARE_REVIEW_STATUSES
                and all(variant.get("assignable") for variant in variants)
                and len(variants) == len(variant_ids),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return profiles


def create_software_profile(payload: dict) -> dict:
    profile_id = validate_software_id(str(payload.get("id", "")), "software_profile_id")
    name = bounded_text(payload.get("name"), 120)
    description = bounded_text(payload.get("description"), 500)
    os_family = bounded_text(payload.get("os_family"), 40)
    risk_level = bounded_text(payload.get("risk_level"), 40) or "medium"
    variant_ids = payload.get("variant_ids", [])
    if not name:
        raise ValueError("software_profile_name_required")
    if os_family not in {"windows", "ubuntu"}:
        raise ValueError("invalid_os_family")
    if risk_level not in SOFTWARE_RISK_LEVELS:
        raise ValueError("invalid_risk_level")
    if not isinstance(variant_ids, list):
        raise ValueError("software_profile_variant_ids_required")
    variant_ids = list(dict.fromkeys(str(item).strip() for item in variant_ids if str(item).strip()))
    if not variant_ids:
        raise ValueError("software_profile_variants_required")

    variants_by_id = {variant["id"]: variant for variant in list_software_variants()}
    errors: list[str] = []
    for variant_id in variant_ids:
        variant = variants_by_id.get(variant_id)
        if variant is None:
            errors.append(f"software_variant_not_found:{variant_id}")
            continue
        if variant.get("os_family") != os_family:
            errors.append(f"software_variant_incompatible:{variant_id}")
        if not variant.get("assignable"):
            errors.append(f"software_variant_not_assignable:{variant_id}:{','.join(variant.get('blocked_reasons', []))}")
    if errors:
        raise ValueError(";".join(errors))

    now = int(time.time())
    conn = connect_db()
    exists = conn.execute("SELECT id FROM software_profiles WHERE id = ?", (profile_id,)).fetchone()
    if exists is not None:
        conn.close()
        raise ValueError("software_profile_already_exists")
    conn.execute(
        """
        INSERT INTO software_profiles (
            id, name, description, os_family, variant_ids, status,
            review_status, risk_level, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'available', 'approved', ?, ?, ?)
        """,
        (
            profile_id,
            name,
            description,
            os_family,
            json.dumps(variant_ids, ensure_ascii=False),
            risk_level,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    profile = next((item for item in list_software_profiles() if item["id"] == profile_id), None)
    if profile is None:
        raise ValueError("software_profile_create_failed")
    return profile


def safe_json_object(value: object, default: dict | None = None) -> dict:
    if default is None:
        default = {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return dict(default)
        return parsed if isinstance(parsed, dict) else dict(default)
    return dict(default)


def safe_json_list(value: object, default: list | None = None) -> list:
    if default is None:
        default = []
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return list(default)
        return parsed if isinstance(parsed, list) else list(default)
    return list(default)


def install_preset_payload(row: sqlite3.Row | dict) -> dict:
    data = dict(row)
    return {
        "id": data["id"],
        "name": data["name"],
        "description": data["description"],
        "os_family": data["os_family"],
        "boot_target": data["boot_target"],
        "software_package_ids": safe_json_list(data.get("software_package_ids")),
        "software_profile_ids": safe_json_list(data.get("software_profile_ids")),
        "settings": safe_json_object(data.get("settings_json")),
        "status": data["status"],
        "review_status": data["review_status"],
        "created_at": data["created_at"],
        "updated_at": data["updated_at"],
        "notes": data["notes"],
        "assignable": data["status"] == "available" and data["review_status"] == "approved",
    }


def list_install_presets(os_family: str | None = None) -> list[dict]:
    conn = connect_db()
    if os_family:
        rows = conn.execute(
            "SELECT * FROM install_presets WHERE os_family = ? ORDER BY name COLLATE NOCASE",
            (os_family,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM install_presets ORDER BY os_family, name COLLATE NOCASE").fetchall()
    conn.close()
    return [install_preset_payload(row) for row in rows]


def get_install_preset(preset_id: str) -> dict | None:
    conn = connect_db()
    row = conn.execute("SELECT * FROM install_presets WHERE id = ?", (preset_id,)).fetchone()
    conn.close()
    return install_preset_payload(row) if row else None


def create_install_preset(payload: dict) -> dict:
    preset_id = validate_software_id(str(payload.get("id", "")), "install_preset_id")
    name = bounded_text(payload.get("name"), 120)
    description = bounded_text(payload.get("description"), 500)
    os_family = bounded_text(payload.get("os_family"), 40)
    boot_target = bounded_text(payload.get("boot_target"), 120)
    software_package_ids = [validate_software_id(str(item), "software_package_id") for item in safe_json_list(payload.get("software_package_ids"))]
    software_profile_ids = [validate_software_id(str(item), "software_profile_id") for item in safe_json_list(payload.get("software_profile_ids"))]
    settings = safe_json_object(payload.get("settings"))
    notes = bounded_text(payload.get("notes"), 1000)
    if os_family not in {"windows", "ubuntu"}:
        raise ValueError("invalid_os_family")
    if not name:
        raise ValueError("install_preset_name_required")
    if boot_target not in {target["target"] for target in boot_target_catalog()}:
        raise ValueError("invalid_or_unready_target")
    if os_family_for_boot_target(boot_target) not in {os_family, "linux"}:
        raise ValueError("install_preset_target_os_mismatch")
    targets = {target["target"]: target for target in boot_target_catalog()}
    if (software_package_ids or software_profile_ids) and not software_assignment_supported_for_target(targets[boot_target]):
        raise ValueError("install_preset_target_postinstall_not_ready")
    resolved = resolve_software_plan([], boot_target, software_profile_ids, software_package_ids)
    if resolved.get("errors"):
        raise ValueError("install_preset_software_invalid:" + ",".join(resolved["errors"]))
    now = int(time.time())
    conn = connect_db()
    exists = conn.execute("SELECT id FROM install_presets WHERE id = ?", (preset_id,)).fetchone()
    if exists:
        conn.close()
        raise ValueError("install_preset_already_exists")
    preset_values = {
        "id": preset_id,
        "name": name,
        "description": description,
        "os_family": os_family,
        "boot_target": boot_target,
        "software_package_ids": json.dumps(software_package_ids, ensure_ascii=False),
        "software_profile_ids": json.dumps(software_profile_ids, ensure_ascii=False),
        "settings_json": json.dumps(settings, ensure_ascii=False),
        "created_at": now,
        "updated_at": now,
        "notes": notes,
    }
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(install_presets)")}
    if "partition_template_id" in columns:
        conn.execute(
            """
            INSERT INTO install_presets (
                id, name, description, os_family, boot_target, partition_template_id,
                software_package_ids, software_profile_ids, settings_json, status, review_status,
                created_at, updated_at, notes
            )
            VALUES (
                :id, :name, :description, :os_family, :boot_target, '',
                :software_package_ids, :software_profile_ids, :settings_json,
                'available', 'approved', :created_at, :updated_at, :notes
            )
            """,
            preset_values,
        )
    else:
        conn.execute(
            """
            INSERT INTO install_presets (
                id, name, description, os_family, boot_target,
                software_package_ids, software_profile_ids, settings_json, status, review_status,
                created_at, updated_at, notes
            )
            VALUES (
                :id, :name, :description, :os_family, :boot_target,
                :software_package_ids, :software_profile_ids, :settings_json,
                'available', 'approved', :created_at, :updated_at, :notes
            )
            """,
            preset_values,
        )
    conn.commit()
    conn.close()
    preset = get_install_preset(preset_id)
    if preset is None:
        raise ValueError("install_preset_create_failed")
    return preset


def update_install_preset_status(preset_id: str, status: str) -> dict | None:
    preset_id = validate_software_id(preset_id, "install_preset_id")
    if status not in INSTALL_PRESET_STATUSES:
        raise ValueError("invalid_install_preset_status")
    conn = connect_db()
    current = conn.execute("SELECT id FROM install_presets WHERE id = ?", (preset_id,)).fetchone()
    if current is None:
        conn.close()
        return None
    conn.execute(
        "UPDATE install_presets SET status = ?, updated_at = ? WHERE id = ?",
        (status, int(time.time()), preset_id),
    )
    conn.commit()
    conn.close()
    return get_install_preset(preset_id)


def update_software_profile_status(profile_id: str, status: str) -> dict | None:
    profile_id = validate_software_id(profile_id, "software_profile_id")
    if status not in {"available", "archived"}:
        raise ValueError("invalid_software_profile_status")
    conn = connect_db()
    current = conn.execute("SELECT id FROM software_profiles WHERE id = ?", (profile_id,)).fetchone()
    if current is None:
        conn.close()
        return None
    conn.execute(
        "UPDATE software_profiles SET status = ?, updated_at = ? WHERE id = ?",
        (status, int(time.time()), profile_id),
    )
    conn.commit()
    conn.close()
    profile = next((item for item in list_software_profiles() if item["id"] == profile_id), None)
    return profile


def software_variant_payload(row: sqlite3.Row | dict) -> dict:
    data = dict(row)
    data["package_status"] = data.get("package_status", "available")
    data["requires_network"] = bool(data.get("requires_network"))
    data["enabled"] = bool(data.get("enabled"))
    data["default_for_os"] = bool(data.get("default_for_os"))
    data["selection_priority"] = int(data.get("selection_priority") or 0)
    data["install_context"] = data.get("install_context") or ("linux_first_boot" if data.get("os_family") == "ubuntu" else "system_first_boot")
    data["detection_rules"] = safe_json_list(data.get("detection_rules"))
    data["requirements"] = safe_json_object(data.get("requirements_json"))
    data["dependencies"] = safe_json_list(data.get("dependencies_json"))
    data["return_codes"] = safe_json_object(data.get("return_codes_json"), {"success": [0], "soft_reboot": [3010]})
    data["restart_behavior"] = data.get("restart_behavior") or "none"
    data["install_location_policy"] = data.get("install_location_policy") or "system_default"
    data["assignable"] = is_software_variant_assignable(data)
    data["blocked_reasons"] = software_variant_blocked_reasons(data)
    return data


def is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def is_deb_download_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.path.lower().endswith(".deb")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def windows_kms_activation_plan() -> dict:
    """返回 Windows/Office 合法 KMS 激活计划。

    SynaBoot 不内置 KMS 服务、不写死公共 KMS，也不保存产品密钥。这里仅允许
    管理员通过环境变量指定自有企业 KMS 主机；未配置时 runner 会跳过激活。
    """
    windows_enabled = env_bool("SYNABOOT_WINDOWS_KMS_ACTIVATE")
    office_enabled = env_bool("SYNABOOT_OFFICE_KMS_ACTIVATE")
    host = os.environ.get("SYNABOOT_KMS_HOST", "").strip()
    port_text = os.environ.get("SYNABOOT_KMS_PORT", "1688").strip() or "1688"
    try:
        port = int(port_text)
    except ValueError:
        port = 1688
    enabled = windows_enabled or office_enabled
    if enabled:
        if not SAFE_KMS_HOST_RE.match(host):
            raise ValueError("invalid_kms_host")
        if port < 1 or port > 65535:
            raise ValueError("invalid_kms_port")
    return {
        "mode": "customer_managed_kms",
        "enabled": enabled,
        "windows": windows_enabled,
        "office": office_enabled,
        "host": host if enabled else "",
        "port": port,
        "public_kms_embedded": False,
        "product_key_embedded": False,
    }


def is_blocked_software_download_host(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if not host:
        return True
    # 软件市场不能把 SynaBoot 自己的静态目录伪装成第三方软件下载源。
    if path.startswith(("/images", "/boot")):
        return True
    if host in {"localhost", "localhost.localdomain"}:
        return True
    if host == SERVER_IP.lower():
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if address.is_loopback or address.is_private or address.is_link_local or address.is_reserved:
        return True
    return False


def runner_actions_for_variant(variant: dict) -> set[str]:
    os_family = str(variant.get("os_family", ""))
    if os_family == "ubuntu":
        return UBUNTU_RUNNER_ACTIONS
    if os_family == "windows":
        return WINDOWS_RUNNER_ACTIONS
    return set()


def default_installer_type_for_action(install_action: str) -> str:
    return {
        "apt_package": "apt",
        "download_deb": "deb",
        "msi_install": "msi",
        "exe_install": "exe",
        "office_odt_install": "office_odt",
        "official_download": "installer",
    }.get(install_action, "installer")


def install_command_template_for_action(install_action: str) -> str:
    return {
        "apt_package": "apt_install_package",
        "download_deb": "apt_install_downloaded_deb",
        "msi_install": "msi_install",
        "exe_install": "exe_silent_install",
        "office_odt_install": "office_odt_configure",
        "official_download": "",
    }.get(install_action, "")


def is_supported_ubuntu_apt_source(variant: dict) -> bool:
    if variant.get("install_action") != "apt_package":
        return True
    if variant.get("source_policy") != "official_package_repo":
        return False
    host = (urlparse(str(variant.get("official_source_url", ""))).hostname or "").lower()
    return host in UBUNTU_DEFAULT_APT_SOURCE_HOSTS


def source_policy_requires_official_source_url(source_policy: str) -> bool:
    return source_policy != "admin_reviewed_download"


def is_direct_installer_action(install_action: str) -> bool:
    return install_action in {"download_deb", "msi_install", "exe_install", "office_odt_install"}


def software_variant_blocked_reasons(variant: dict) -> list[str]:
    reasons: list[str] = []
    install_action = str(variant.get("install_action", ""))
    download_url = str(variant.get("download_url", ""))
    source_policy = str(variant.get("source_policy", ""))
    official_source_url = str(variant.get("official_source_url", ""))
    if variant.get("package_status") == "archived":
        reasons.append("package_archived")
    if not variant.get("enabled"):
        reasons.append("disabled")
    if variant.get("review_status") not in ASSIGNABLE_SOFTWARE_REVIEW_STATUSES:
        reasons.append("review_required")
    if source_policy not in ALLOWED_SOFTWARE_SOURCE_POLICIES:
        reasons.append("source_policy_not_allowed")
    if variant.get("signature_policy") not in ASSIGNABLE_SIGNATURE_POLICIES:
        reasons.append("signature_policy_not_allowed")
    if source_policy == "admin_reviewed_download" and not is_direct_installer_action(install_action):
        reasons.append("source_policy_not_supported_for_action")
    if source_policy_requires_official_source_url(source_policy) and not is_https_url(official_source_url):
        reasons.append("official_source_url_must_be_https")
    if official_source_url and not is_https_url(official_source_url):
        reasons.append("official_source_url_must_be_https")
    if install_action != "apt_package" and not is_https_url(download_url):
        reasons.append("download_url_must_be_https")
    if official_source_url and is_blocked_software_download_host(official_source_url):
        reasons.append("official_source_must_not_be_hosted_by_synaboot")
    if variant.get("signature_policy") == "sha256_required" and not variant.get("sha256"):
        reasons.append("sha256_required")
    if download_url and is_blocked_software_download_host(download_url):
        reasons.append("third_party_binary_must_not_be_hosted_by_synaboot")
    if install_action not in {"official_download", "download_deb", "apt_package", "msi_install", "exe_install", "office_odt_install"}:
        reasons.append("install_action_not_allowlisted")
    elif install_action not in runner_actions_for_variant(variant):
        reasons.append("runner_action_not_ready")
    if variant.get("os_family") == "ubuntu" and variant.get("install_phase") != "linux_first_boot":
        reasons.append("install_phase_not_supported")
    if variant.get("os_family") == "windows" and variant.get("install_phase") != "windows_first_boot":
        reasons.append("install_phase_not_supported")
    if install_action == "download_deb" and variant.get("installer_type") != "deb":
        reasons.append("installer_type_not_supported")
    if install_action == "msi_install" and variant.get("installer_type") != "msi":
        reasons.append("installer_type_not_supported")
    if install_action == "exe_install" and variant.get("installer_type") != "exe":
        reasons.append("installer_type_not_supported")
    if install_action == "office_odt_install" and variant.get("installer_type") != "office_odt":
        reasons.append("installer_type_not_supported")
    if install_action == "apt_package" and not SAFE_APT_PACKAGE_RE.match(str(variant.get("package_name", ""))):
        reasons.append("package_name_invalid")
    if install_action == "office_odt_install" and not SAFE_OFFICE_PRODUCT_ID_RE.match(str(variant.get("package_name", ""))):
        reasons.append("office_product_id_invalid")
    if install_action == "apt_package" and not is_supported_ubuntu_apt_source(variant):
        reasons.append("apt_repo_not_supported")
    if variant.get("install_context") and variant.get("install_context") not in SOFTWARE_INSTALL_CONTEXTS:
        reasons.append("install_context_not_supported")
    if variant.get("restart_behavior") and variant.get("restart_behavior") not in SOFTWARE_RESTART_BEHAVIORS:
        reasons.append("restart_behavior_not_supported")
    if variant.get("install_location_policy") and variant.get("install_location_policy") not in SOFTWARE_INSTALL_LOCATION_POLICIES:
        reasons.append("install_location_policy_not_supported")
    return reasons


def is_software_variant_assignable(variant: dict) -> bool:
    return not software_variant_blocked_reasons(variant)


def software_package_payload(package: sqlite3.Row, variants: list[dict]) -> dict:
    return {
        "id": package["id"],
        "name": package["name"],
        "vendor": package["vendor"],
        "category": package["category"],
        "description": package["description"],
        "homepage_url": package["homepage_url"],
        "icon_key": package["icon_key"],
        "status": package["status"],
        "review_status": package["review_status"],
        "created_at": package["created_at"],
        "updated_at": package["updated_at"],
        "variants": variants,
    }


def list_software_packages(os_family: str | None = None, include_blocked: bool = True) -> list[dict]:
    conn = connect_db()
    packages = conn.execute("SELECT * FROM software_packages ORDER BY name COLLATE NOCASE").fetchall()
    result: list[dict] = []
    for package in packages:
        if not include_blocked and package["status"] != "available":
            continue
        params: list[object] = [package["id"]]
        where = "package_id = ?"
        if os_family:
            where += " AND os_family = ?"
            params.append(os_family)
        rows = conn.execute(
            f"""
            SELECT * FROM software_variants
            WHERE {where}
            ORDER BY os_family, default_for_os DESC, selection_priority DESC, updated_at DESC, id
            """,
            params,
        ).fetchall()
        variants = []
        for row in rows:
            variant = dict(row)
            variant["package_status"] = package["status"]
            variants.append(software_variant_payload(variant))
        if not include_blocked:
            variants = [variant for variant in variants if variant["assignable"]]
        if variants or not os_family:
            result.append(software_package_payload(package, variants))
    conn.close()
    return result


def get_software_package(package_id: str) -> dict | None:
    conn = connect_db()
    package = conn.execute("SELECT * FROM software_packages WHERE id = ?", (package_id,)).fetchone()
    if package is None:
        conn.close()
        return None
    variants = []
    for row in conn.execute(
            """
            SELECT * FROM software_variants
            WHERE package_id = ?
            ORDER BY os_family, default_for_os DESC, selection_priority DESC, updated_at DESC, id
            """,
            (package_id,),
        ):
        variant = dict(row)
        variant["package_status"] = package["status"]
        variants.append(software_variant_payload(variant))
    conn.close()
    return software_package_payload(package, variants)


def bounded_text(value: object, max_length: int) -> str:
    return str(value or "").strip()[:max_length]


def validate_software_id(value: str, field_name: str) -> str:
    normalized = value.strip().lower()
    if not SAFE_SOFTWARE_ID_RE.match(normalized):
        raise ValueError(f"invalid_{field_name}")
    return normalized


def create_software_package(payload: dict) -> dict:
    package_id = validate_software_id(str(payload.get("id", "")), "software_package_id")
    name = bounded_text(payload.get("name"), 120)
    vendor = bounded_text(payload.get("vendor"), 120)
    category = bounded_text(payload.get("category"), 80)
    description = bounded_text(payload.get("description"), 500)
    homepage_url = bounded_text(payload.get("homepage_url"), 500)
    icon_key = validate_software_id(str(payload.get("icon_key") or package_id), "icon_key")
    if not name:
        raise ValueError("software_package_name_required")
    if not vendor:
        raise ValueError("software_package_vendor_required")
    if not category:
        raise ValueError("software_package_category_required")
    if not is_https_url(homepage_url):
        raise ValueError("homepage_url_must_be_https")
    if is_blocked_software_download_host(homepage_url):
        raise ValueError("homepage_url_must_not_be_hosted_by_synaboot")

    now = int(time.time())
    conn = connect_db()
    exists = conn.execute("SELECT id FROM software_packages WHERE id = ?", (package_id,)).fetchone()
    if exists is not None:
        conn.close()
        raise ValueError("software_package_already_exists")
    conn.execute(
        """
        INSERT INTO software_packages (
            id, name, vendor, category, description, homepage_url,
            icon_key, status, review_status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'available', 'needs_review', ?, ?)
        """,
        (package_id, name, vendor, category, description, homepage_url, icon_key, now, now),
    )
    conn.commit()
    conn.close()
    package = get_software_package(package_id)
    if package is None:
        raise ValueError("software_package_create_failed")
    return package


def update_software_package_status(package_id: str, status: str) -> dict | None:
    package_id = validate_software_id(package_id, "software_package_id")
    if status not in {"available", "archived"}:
        raise ValueError("invalid_software_package_status")
    conn = connect_db()
    current = conn.execute("SELECT id FROM software_packages WHERE id = ?", (package_id,)).fetchone()
    if current is None:
        conn.close()
        return None
    conn.execute(
        "UPDATE software_packages SET status = ?, updated_at = ? WHERE id = ?",
        (status, int(time.time()), package_id),
    )
    conn.commit()
    conn.close()
    return get_software_package(package_id)


def list_software_variants(os_family: str | None = None, include_blocked: bool = True) -> list[dict]:
    conn = connect_db()
    if os_family:
        rows = conn.execute(
            """
            SELECT v.*, p.status AS package_status
            FROM software_variants v
            JOIN software_packages p ON p.id = v.package_id
            WHERE v.os_family = ?
            ORDER BY v.package_id, v.default_for_os DESC, v.selection_priority DESC, v.updated_at DESC, v.id
            """,
            (os_family,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT v.*, p.status AS package_status
            FROM software_variants v
            JOIN software_packages p ON p.id = v.package_id
            ORDER BY v.package_id, v.os_family, v.default_for_os DESC, v.selection_priority DESC, v.updated_at DESC, v.id
            """
        ).fetchall()
    conn.close()
    variants = [software_variant_payload(row) for row in rows]
    return variants if include_blocked else [variant for variant in variants if variant["assignable"]]


def get_software_variant(variant_id: str) -> dict | None:
    conn = connect_db()
    row = conn.execute(
        """
        SELECT v.*, p.status AS package_status
        FROM software_variants v
        JOIN software_packages p ON p.id = v.package_id
        WHERE v.id = ?
        """,
        (variant_id,),
    ).fetchone()
    conn.close()
    return software_variant_payload(row) if row else None


def create_software_variant(package_id: str, payload: dict) -> dict:
    package_id = validate_software_id(package_id, "software_package_id")
    variant_id = validate_software_id(str(payload.get("id", "")), "software_variant_id")
    os_family = bounded_text(payload.get("os_family"), 40)
    if os_family not in {"windows", "ubuntu"}:
        raise ValueError("invalid_os_family")
    install_action = bounded_text(payload.get("install_action"), 60) or "official_download"
    if install_action not in {"official_download", "download_deb", "apt_package", "msi_install", "exe_install", "office_odt_install"}:
        raise ValueError("invalid_install_action")
    installer_type = bounded_text(payload.get("installer_type"), 40)
    if not installer_type:
        installer_type = default_installer_type_for_action(install_action)
    if not SAFE_SOFTWARE_INSTALLER_TYPE_RE.match(installer_type):
        raise ValueError("invalid_installer_type")
    install_phase = "linux_first_boot" if os_family == "ubuntu" else "windows_first_boot"
    official_source_url = bounded_text(payload.get("official_source_url"), 500)
    download_url = bounded_text(payload.get("download_url"), 500)
    source_policy = bounded_text(payload.get("source_policy"), 80) or "official_vendor"
    signature_policy = bounded_text(payload.get("signature_policy"), 80) or "vendor_signed"
    risk_level = bounded_text(payload.get("risk_level"), 40) or "medium"
    package_name = bounded_text(payload.get("package_name"), 160)
    silent_args = bounded_text(payload.get("silent_args"), 200)
    install_context = bounded_text(payload.get("install_context"), 80) or ("linux_first_boot" if os_family == "ubuntu" else "system_first_boot")
    detection_rules = safe_json_list(payload.get("detection_rules"))
    requirements = safe_json_object(payload.get("requirements"))
    dependencies = safe_json_list(payload.get("dependencies"))
    return_codes = safe_json_object(payload.get("return_codes"), {"success": [0], "soft_reboot": [3010]})
    restart_behavior = bounded_text(payload.get("restart_behavior"), 80) or "none"
    install_location_policy = bounded_text(payload.get("install_location_policy"), 80) or "system_default"
    default_for_os = bool(payload.get("default_for_os", False))
    try:
        selection_priority = int(payload.get("selection_priority", 0) or 0)
    except (TypeError, ValueError):
        raise ValueError("invalid_selection_priority")
    if selection_priority < 0 or selection_priority > 1000:
        raise ValueError("invalid_selection_priority")
    sha256 = bounded_text(payload.get("sha256"), 80).lower()
    if source_policy not in ALLOWED_SOFTWARE_SOURCE_POLICIES:
        raise ValueError("invalid_source_policy")
    if signature_policy not in ASSIGNABLE_SIGNATURE_POLICIES:
        raise ValueError("invalid_signature_policy")
    if risk_level not in SOFTWARE_RISK_LEVELS:
        raise ValueError("invalid_risk_level")
    if install_context not in SOFTWARE_INSTALL_CONTEXTS:
        raise ValueError("invalid_install_context")
    if restart_behavior not in SOFTWARE_RESTART_BEHAVIORS:
        raise ValueError("invalid_restart_behavior")
    if install_location_policy not in SOFTWARE_INSTALL_LOCATION_POLICIES:
        raise ValueError("invalid_install_location_policy")
    if source_policy == "admin_reviewed_download" and not is_direct_installer_action(install_action):
        raise ValueError("source_policy_not_supported_for_action")
    if source_policy_requires_official_source_url(source_policy) and not is_https_url(official_source_url):
        raise ValueError("official_source_url_must_be_https")
    if official_source_url and not is_https_url(official_source_url):
        raise ValueError("official_source_url_must_be_https")
    if official_source_url and is_blocked_software_download_host(official_source_url):
        raise ValueError("official_source_url_must_not_be_hosted_by_synaboot")
    if install_action != "apt_package" and not is_https_url(download_url):
        raise ValueError("download_url_must_be_https")
    if download_url and is_blocked_software_download_host(download_url):
        raise ValueError("third_party_binary_must_not_be_hosted_by_synaboot")
    if sha256 and not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ValueError("invalid_sha256")
    if install_action == "office_odt_install":
        if package_name and not SAFE_OFFICE_PRODUCT_ID_RE.match(package_name):
            raise ValueError("invalid_office_product_id")
    elif package_name and not SAFE_APT_PACKAGE_RE.match(package_name):
        raise ValueError("invalid_package_name")
    if install_action == "apt_package" and not package_name:
        raise ValueError("package_name_required_for_apt_package")
    if install_action == "exe_install" and not silent_args:
        raise ValueError("silent_args_required_for_exe_install")
    if install_action == "office_odt_install" and not package_name:
        raise ValueError("office_product_id_required")
    if not SAFE_SILENT_ARGS_RE.match(silent_args):
        raise ValueError("invalid_silent_args")

    now = int(time.time())
    install_command_template = install_command_template_for_action(install_action)
    conn = connect_db()
    package = conn.execute("SELECT id FROM software_packages WHERE id = ?", (package_id,)).fetchone()
    if package is None:
        conn.close()
        raise ValueError("software_package_not_found")
    exists = conn.execute("SELECT id FROM software_variants WHERE id = ?", (variant_id,)).fetchone()
    if exists is not None:
        conn.close()
        raise ValueError("software_variant_already_exists")
    if default_for_os:
        conn.execute(
            "UPDATE software_variants SET default_for_os = 0, updated_at = ? WHERE package_id = ? AND os_family = ?",
            (now, package_id, os_family),
        )
    conn.execute(
        """
        INSERT INTO software_variants (
            id, package_id, os_family, os_version_constraint, arch, version,
            installer_type, official_source_url, download_url, source_policy,
            sha256, signature_policy, install_phase, install_action,
            package_name, default_for_os, selection_priority,
            install_context, detection_rules, requirements_json, dependencies_json,
            return_codes_json, restart_behavior, install_location_policy,
            install_command_template, silent_args, requires_network, risk_level,
            review_status, enabled, notes, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 'needs_review', 1, ?, ?, ?)
        """,
        (
            variant_id,
            package_id,
            os_family,
            bounded_text(payload.get("os_version_constraint"), 80) or (">=22.04" if os_family == "ubuntu" else "windows_10_or_11"),
            bounded_text(payload.get("arch"), 40) or "x86_64",
            bounded_text(payload.get("version"), 80) or "latest",
            installer_type,
            official_source_url,
            download_url,
            source_policy,
            sha256,
            signature_policy,
            install_phase,
            install_action,
            package_name,
            int(default_for_os),
            selection_priority,
            install_context,
            json.dumps(detection_rules, ensure_ascii=False),
            json.dumps(requirements, ensure_ascii=False),
            json.dumps(dependencies, ensure_ascii=False),
            json.dumps(return_codes, ensure_ascii=False),
            restart_behavior,
            install_location_policy,
            install_command_template,
            silent_args,
            risk_level,
            bounded_text(payload.get("notes"), 1000),
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    variant = get_software_variant(variant_id)
    if variant is None:
        raise ValueError("software_variant_create_failed")
    return variant


def update_software_variant(variant_id: str, payload: dict) -> dict | None:
    allowed_fields = {
        "review_status",
        "enabled",
        "signature_policy",
        "sha256",
        "official_source_url",
        "download_url",
        "source_policy",
        "install_action",
        "installer_type",
        "package_name",
        "silent_args",
        "default_for_os",
        "selection_priority",
        "install_context",
        "detection_rules",
        "requirements",
        "dependencies",
        "return_codes",
        "restart_behavior",
        "install_location_policy",
        "risk_level",
        "notes",
    }
    updates = {key: payload[key] for key in allowed_fields if key in payload}
    if not updates:
        raise ValueError("no_supported_software_variant_fields")

    if "review_status" in updates and updates["review_status"] not in SOFTWARE_REVIEW_STATUSES:
        raise ValueError("invalid_review_status")
    if "signature_policy" in updates and updates["signature_policy"] not in ASSIGNABLE_SIGNATURE_POLICIES:
        raise ValueError("invalid_signature_policy")
    if "source_policy" in updates and updates["source_policy"] not in ALLOWED_SOFTWARE_SOURCE_POLICIES:
        raise ValueError("invalid_source_policy")
    if "risk_level" in updates and updates["risk_level"] not in SOFTWARE_RISK_LEVELS:
        raise ValueError("invalid_risk_level")
    if "install_action" in updates:
        install_action = bounded_text(updates["install_action"], 60)
        if install_action not in {"official_download", "download_deb", "apt_package", "msi_install", "exe_install", "office_odt_install"}:
            raise ValueError("invalid_install_action")
        updates["install_action"] = install_action
        updates["install_command_template"] = install_command_template_for_action(install_action)
    if "installer_type" in updates:
        installer_type = bounded_text(updates["installer_type"], 40)
        if not SAFE_SOFTWARE_INSTALLER_TYPE_RE.match(installer_type):
            raise ValueError("invalid_installer_type")
        updates["installer_type"] = installer_type
    if "silent_args" in updates:
        silent_args = bounded_text(updates["silent_args"], 200)
        if not SAFE_SILENT_ARGS_RE.match(silent_args):
            raise ValueError("invalid_silent_args")
        updates["silent_args"] = silent_args
    if "enabled" in updates:
        updates["enabled"] = 1 if bool(updates["enabled"]) else 0
    if "default_for_os" in updates:
        updates["default_for_os"] = 1 if bool(updates["default_for_os"]) else 0
    if "selection_priority" in updates:
        try:
            selection_priority = int(updates["selection_priority"] or 0)
        except (TypeError, ValueError):
            raise ValueError("invalid_selection_priority")
        if selection_priority < 0 or selection_priority > 1000:
            raise ValueError("invalid_selection_priority")
        updates["selection_priority"] = selection_priority
    if "install_context" in updates:
        install_context = bounded_text(updates["install_context"], 80)
        if install_context not in SOFTWARE_INSTALL_CONTEXTS:
            raise ValueError("invalid_install_context")
        updates["install_context"] = install_context
    if "restart_behavior" in updates:
        restart_behavior = bounded_text(updates["restart_behavior"], 80)
        if restart_behavior not in SOFTWARE_RESTART_BEHAVIORS:
            raise ValueError("invalid_restart_behavior")
        updates["restart_behavior"] = restart_behavior
    if "install_location_policy" in updates:
        install_location_policy = bounded_text(updates["install_location_policy"], 80)
        if install_location_policy not in SOFTWARE_INSTALL_LOCATION_POLICIES:
            raise ValueError("invalid_install_location_policy")
        updates["install_location_policy"] = install_location_policy
    for input_key, storage_key, parser in [
        ("detection_rules", "detection_rules", safe_json_list),
        ("requirements", "requirements_json", safe_json_object),
        ("dependencies", "dependencies_json", safe_json_list),
        ("return_codes", "return_codes_json", safe_json_object),
    ]:
        if input_key in updates:
            updates[storage_key] = json.dumps(parser(updates[input_key]), ensure_ascii=False)
            del updates[input_key]
    if "sha256" in updates:
        sha256 = str(updates["sha256"]).strip().lower()
        if sha256 and not re.fullmatch(r"[a-f0-9]{64}", sha256):
            raise ValueError("invalid_sha256")
        updates["sha256"] = sha256
    if "package_name" in updates:
        package_name = str(updates["package_name"]).strip()
        updates["package_name"] = package_name
    if "notes" in updates:
        updates["notes"] = str(updates["notes"])[:1000]

    conn = connect_db()
    current = conn.execute("SELECT * FROM software_variants WHERE id = ?", (variant_id,)).fetchone()
    if current is None:
        conn.close()
        return None
    effective_install_action = str(updates.get("install_action", current["install_action"]))
    if "install_action" in updates and "installer_type" not in updates:
        updates["installer_type"] = default_installer_type_for_action(effective_install_action)
    effective_installer_type = str(updates.get("installer_type", current["installer_type"]))
    effective_package_name = str(updates.get("package_name", current["package_name"] or "")).strip()
    effective_download_url = str(updates.get("download_url", current["download_url"] or "")).strip()
    effective_source_policy = str(updates.get("source_policy", current["source_policy"] or ""))
    if effective_source_policy == "admin_reviewed_download" and not is_direct_installer_action(effective_install_action):
        conn.close()
        raise ValueError("source_policy_not_supported_for_action")
    if "official_source_url" in updates:
        official_source_url = str(updates["official_source_url"])
        if source_policy_requires_official_source_url(effective_source_policy) and not is_https_url(official_source_url):
            conn.close()
            raise ValueError("official_source_url_must_be_https")
        if official_source_url and not is_https_url(official_source_url):
            conn.close()
            raise ValueError("official_source_url_must_be_https")
        if official_source_url and is_blocked_software_download_host(official_source_url):
            conn.close()
            raise ValueError("official_source_url_must_not_be_hosted_by_synaboot")
    elif source_policy_requires_official_source_url(effective_source_policy) and not is_https_url(str(current["official_source_url"] or "")):
        conn.close()
        raise ValueError("official_source_url_must_be_https")
    if "download_url" in updates:
        download_url = str(updates["download_url"]).strip()
        updates["download_url"] = download_url
        if effective_install_action != "apt_package" and not is_https_url(download_url):
            conn.close()
            raise ValueError("download_url_must_be_https")
        if download_url and is_blocked_software_download_host(download_url):
            conn.close()
            raise ValueError("third_party_binary_must_not_be_hosted_by_synaboot")
    if effective_install_action == "apt_package" and not effective_package_name:
        conn.close()
        raise ValueError("package_name_required_for_apt_package")
    if effective_install_action == "apt_package" and not SAFE_APT_PACKAGE_RE.match(effective_package_name):
        conn.close()
        raise ValueError("invalid_package_name")
    if effective_install_action == "office_odt_install" and not effective_package_name:
        conn.close()
        raise ValueError("office_product_id_required")
    if effective_install_action == "exe_install" and not str(updates.get("silent_args", current["silent_args"] or "")).strip():
        conn.close()
        raise ValueError("silent_args_required_for_exe_install")
    if effective_install_action == "office_odt_install" and not SAFE_OFFICE_PRODUCT_ID_RE.match(effective_package_name):
        conn.close()
        raise ValueError("invalid_office_product_id")
    if effective_install_action == "download_deb" and effective_installer_type != "deb":
        conn.close()
        raise ValueError("installer_type_must_be_deb")
    if effective_install_action == "msi_install" and effective_installer_type != "msi":
        conn.close()
        raise ValueError("installer_type_must_be_msi")
    if effective_install_action == "exe_install" and effective_installer_type != "exe":
        conn.close()
        raise ValueError("installer_type_must_be_exe")
    if effective_install_action == "office_odt_install" and effective_installer_type != "office_odt":
        conn.close()
        raise ValueError("installer_type_must_be_office_odt")
    if effective_install_action != "apt_package" and not is_https_url(effective_download_url):
        conn.close()
        raise ValueError("download_url_must_be_https")
    if updates.get("default_for_os") == 1:
        now = int(time.time())
        conn.execute(
            """
            UPDATE software_variants
            SET default_for_os = 0, updated_at = ?
            WHERE package_id = ? AND os_family = ? AND id <> ?
            """,
            (now, current["package_id"], current["os_family"], variant_id),
        )
    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(
        f"UPDATE software_variants SET {set_clause} WHERE id = ?",
        [*updates.values(), variant_id],
    )
    conn.commit()
    conn.close()
    return get_software_variant(variant_id)


def os_family_for_boot_target(target: str) -> str:
    value = target.lower()
    if "windows" in value:
        return "windows"
    if "ubuntu" in value:
        return "ubuntu"
    if "linux" in value:
        return "linux"
    return ""


def software_assignment_supported_for_target(target: dict) -> bool:
    # 只有已经具备真实 OS 安装后执行通道的目标，才能附带软件安装计划。
    # Windows 通过 HotPE/WinPE 显式注入 SetupComplete.cmd 后，在首次启动执行 runner。
    return bool(target.get("software_assignment_enabled"))


def compatible_software_packages_for_target(target: dict) -> list[dict]:
    if not software_assignment_supported_for_target(target):
        return []
    os_family = os_family_for_boot_target(str(target.get("target", "")))
    if not os_family:
        return []
    return list_software_packages(os_family=os_family, include_blocked=False)


def compatible_software_profiles_for_target(target: dict) -> list[dict]:
    if not software_assignment_supported_for_target(target):
        return []
    os_family = os_family_for_boot_target(str(target.get("target", "")))
    if not os_family:
        return []
    return [
        profile
        for profile in list_software_profiles()
        if profile.get("assignable") and software_profile_compatible(profile, os_family)
    ]


def software_profile_compatible(profile: dict, os_family: str) -> bool:
    return profile["os_family"] == os_family or (os_family == "linux" and profile["os_family"] == "ubuntu")


def resolve_software_plan(
    variant_ids: list[str],
    boot_target: str,
    profile_ids: list[str] | None = None,
    package_ids: list[str] | None = None,
) -> dict:
    os_family = os_family_for_boot_target(boot_target)
    profile_ids = profile_ids or []
    package_ids = package_ids or []
    profiles_by_id = {profile["id"]: profile for profile in list_software_profiles()}
    variants_by_id = {variant["id"]: variant for variant in list_software_variants()}
    all_packages_by_id = {package["id"]: package for package in list_software_packages(include_blocked=True)}
    compatible_packages_by_id = {package["id"]: package for package in list_software_packages(os_family=os_family, include_blocked=False)}
    expanded_variant_ids: list[str] = []
    resolved: list[dict] = []
    errors: list[str] = []
    resolved_profiles: list[dict] = []
    resolved_packages: list[dict] = []

    for package_id in package_ids:
        package_id = str(package_id)
        package = all_packages_by_id.get(package_id)
        if package is None:
            errors.append(f"software_package_not_found:{package_id}")
            continue
        compatible_package = compatible_packages_by_id.get(package_id)
        compatible_variants = list((compatible_package or {}).get("variants", []))
        if not compatible_variants:
            errors.append(f"software_package_no_assignable_variant:{package_id}:{os_family}")
            continue
        variant = compatible_variants[0]
        resolved_packages.append(
            {
                "id": package["id"],
                "name": package["name"],
                "vendor": package.get("vendor", ""),
                "category": package.get("category", ""),
                "selected_variant_id": variant["id"],
            }
        )
        expanded_variant_ids.append(str(variant["id"]))

    for profile_id in profile_ids:
        profile = profiles_by_id.get(str(profile_id))
        if profile is None:
            errors.append(f"software_profile_not_found:{profile_id}")
            continue
        if profile.get("status") != "available" or profile.get("review_status") not in ASSIGNABLE_SOFTWARE_REVIEW_STATUSES:
            errors.append(f"software_profile_not_approved:{profile_id}")
            continue
        if not software_profile_compatible(profile, os_family):
            errors.append(f"software_profile_incompatible:{profile_id}")
            continue
        if not profile.get("assignable"):
            errors.append(f"software_profile_not_assignable:{profile_id}")
            continue
        resolved_profiles.append(
            {
                "id": profile["id"],
                "name": profile["name"],
                "os_family": profile["os_family"],
                "variant_ids": profile["variant_ids"],
            }
        )
        expanded_variant_ids.extend(str(item) for item in profile.get("variant_ids", []))

    expanded_variant_ids.extend(str(item) for item in variant_ids)
    deduped_variant_ids = list(dict.fromkeys(item for item in expanded_variant_ids if item))

    for variant_id in deduped_variant_ids:
        variant = variants_by_id.get(str(variant_id))
        if variant is None:
            errors.append(f"software_variant_not_found:{variant_id}")
            continue
        compatible = variant["os_family"] == os_family or (os_family == "linux" and variant["os_family"] == "ubuntu")
        if not compatible:
            errors.append(f"software_variant_incompatible:{variant_id}")
            continue
        if not variant["assignable"]:
            errors.append(f"software_variant_not_approved:{variant_id}:{','.join(variant['blocked_reasons'])}")
            continue
        resolved.append(
            {
                "id": variant["id"],
                "package_id": variant["package_id"],
                "os_family": variant["os_family"],
                "arch": variant["arch"],
                "version": variant["version"],
                "installer_type": variant["installer_type"],
                "official_source_url": variant["official_source_url"],
                "download_url": variant["download_url"],
                "source_policy": variant["source_policy"],
                "sha256": variant["sha256"],
                "signature_policy": variant["signature_policy"],
                "install_phase": variant["install_phase"],
                "install_action": variant["install_action"],
                "package_name": variant.get("package_name", ""),
                "silent_args": variant["silent_args"],
                "install_args": variant["silent_args"],
                "expected_exit_codes": [0],
                "timeout_seconds": 1800,
                "install_context": variant.get("install_context", ""),
                "detection_rules": variant.get("detection_rules", []),
                "requirements": variant.get("requirements", {}),
                "dependencies": variant.get("dependencies", []),
                "return_codes": variant.get("return_codes", {"success": [0], "soft_reboot": [3010]}),
                "restart_behavior": variant.get("restart_behavior", "none"),
                "install_location_policy": variant.get("install_location_policy", "system_default"),
                "requires_network": variant["requires_network"],
                "risk_level": variant["risk_level"],
                "review_status": variant["review_status"],
            }
        )
    if errors:
        raise ValueError(";".join(errors))
    return {
        "schema_version": "synaboot.software-plan.v1",
        "plan_version": 1,
        "generated_at": int(time.time()),
        "artifact_hosting_allowed": False,
        "third_party_binary_stored": False,
        "client_downloads_from_official_source": True,
        "os_family": os_family,
        "package_ids": [package["id"] for package in resolved_packages],
        "packages": resolved_packages,
        "profile_ids": [profile["id"] for profile in resolved_profiles],
        "profiles": resolved_profiles,
        "variants": resolved,
    }


def deployment_assignment_payload(row: sqlite3.Row) -> dict:
    software_package_ids = json.loads(row["software_package_ids"] or "[]")
    software_profile_ids = json.loads(row["software_profile_ids"] or "[]")
    software_variant_ids = json.loads(row["software_variant_ids"] or "[]")
    session_ids = json.loads(row["session_ids"] or "[]")
    resolved_software_plan = json.loads(row["resolved_software_plan"] or "{}")
    task_sequence_plan = json.loads(row["task_sequence_plan"] or "{}")
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "session_ids": session_ids,
        "source_image_id": row["source_image_id"],
        "boot_target": row["boot_target"],
        "boot_label": row["boot_label"],
        "software_package_ids": software_package_ids,
        "software_profile_ids": software_profile_ids,
        "software_variant_ids": software_variant_ids,
        "resolved_software_plan": resolved_software_plan,
        "install_preset_id": row["install_preset_id"],
        "task_sequence_plan": task_sequence_plan,
        "status": row["status"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "expires_at": row["expires_at"],
        "boot_token_expires_at": row["boot_token_expires_at"],
    }


def build_task_sequence_plan(
    boot_target: str,
    install_preset: dict | None,
    software_plan: dict,
) -> dict:
    os_family = os_family_for_boot_target(boot_target)
    steps = []
    if os_family == "windows":
        steps = [
            {"id": "boot_winpe", "status": "manual_or_existing", "execution": "boot_entry"},
            {"id": "collect_hardware", "status": "planned", "execution": "future_winpe_callback"},
            {"id": "apply_windows", "status": "manual_or_existing", "execution": "windows_setup_or_hotpe_tool"},
            {"id": "inject_bootstrap", "status": "available", "execution": "windows_hotpe_inject_helper"},
            {"id": "first_boot", "status": "available", "execution": "setupcomplete_bootstrap"},
            {"id": "install_software", "status": "available", "execution": "runner_ps1"},
            {"id": "detect_software", "status": "planned", "execution": "deployment_type_detection_rules"},
            {"id": "report_result", "status": "available", "execution": "postinstall_events"},
        ]
    elif os_family in {"ubuntu", "linux"}:
        steps = [
            {"id": "boot_installer", "status": "available", "execution": "ipxe_nocloud"},
            {"id": "install_software", "status": "available", "execution": "runner_sh"},
            {"id": "report_result", "status": "available", "execution": "postinstall_events"},
        ]
    return {
        "schema_version": "synaboot.task-sequence-plan.v1",
        "mode": "preview_and_bootstrap",
        "os_family": os_family,
        "boot_target": boot_target,
        "install_preset_id": install_preset["id"] if install_preset else "",
        "software_variant_count": len(software_plan.get("variants", [])),
        "steps": steps,
    }


def client_event_payload(row: sqlite3.Row | dict) -> dict:
    data = dict(row)
    data["payload"] = json.loads(data.get("payload") or "{}")
    return data


def list_assignment_events(assignment_id: str, limit: int = 20) -> list[dict]:
    conn = connect_db()
    rows = conn.execute(
        """
        SELECT * FROM client_events
        WHERE assignment_id = ?
        ORDER BY created_at DESC, rowid DESC
        LIMIT ?
        """,
        (assignment_id, limit),
    ).fetchall()
    conn.close()
    return [client_event_payload(row) for row in rows]


def list_assignment_session_events(assignment_id: str, session_id: str, limit: int = 20) -> list[dict]:
    conn = connect_db()
    rows = conn.execute(
        """
        SELECT * FROM client_events
        WHERE assignment_id = ? AND session_id = ?
        ORDER BY created_at DESC, rowid DESC
        LIMIT ?
        """,
        (assignment_id, session_id, limit),
    ).fetchall()
    conn.close()
    return [client_event_payload(row) for row in rows]


def assignment_event_summary(events: list[dict]) -> dict:
    summary = {
        "total": len(events),
        "last_status": "",
        "last_stage": "",
        "last_message": "",
        "last_event_at": 0,
        "completed": 0,
        "failed": 0,
        "blocked": 0,
    }
    if not events:
        return summary
    # 调用方传入的事件列表已经按最新优先排序；同秒事件用 rowid 打破顺序。
    latest = events[0]
    summary.update(
        {
            "last_status": latest.get("status", ""),
            "last_stage": latest.get("stage", ""),
            "last_message": latest.get("message", ""),
            "last_event_at": latest.get("created_at", 0),
            "completed": sum(1 for item in events if item.get("status") == "completed"),
            "failed": sum(1 for item in events if item.get("status") == "failed"),
            "blocked": sum(1 for item in events if item.get("status") == "blocked"),
        }
    )
    return summary


def get_deployment_assignment(assignment_id: str) -> dict | None:
    conn = connect_db()
    row = conn.execute("SELECT * FROM deployment_assignments WHERE id = ?", (assignment_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    assignment = deployment_assignment_payload(row)
    events = list_assignment_events(assignment["id"])
    return {**assignment, "recent_events": events, "event_summary": assignment_event_summary(events)}


def latest_assignment_for_session(session_id: str) -> dict | None:
    conn = connect_db()
    rows = conn.execute(
        """
        SELECT * FROM deployment_assignments
        WHERE session_id = ? OR session_ids != '[]'
        ORDER BY created_at DESC, rowid DESC
        """,
        (session_id,),
    ).fetchall()
    conn.close()
    row = None
    for candidate in rows:
        session_ids = json.loads(candidate["session_ids"] or "[]")
        if candidate["session_id"] == session_id or session_id in session_ids:
            row = candidate
            break
    return deployment_assignment_payload(row) if row else None


def list_deployment_assignments(limit: int = 100) -> list[dict]:
    conn = connect_db()
    rows = conn.execute("SELECT * FROM deployment_assignments ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    assignments = [deployment_assignment_payload(row) for row in rows]
    if not assignments:
        return []
    conn = connect_db()
    placeholders = ",".join("?" for _ in assignments)
    event_rows = conn.execute(
        f"""
        SELECT * FROM client_events
        WHERE assignment_id IN ({placeholders})
        ORDER BY created_at DESC, rowid DESC
        """,
        [item["id"] for item in assignments],
    ).fetchall()
    conn.close()
    events_by_assignment: dict[str, list[dict]] = {item["id"]: [] for item in assignments}
    for row in event_rows:
        event = client_event_payload(row)
        bucket = events_by_assignment.setdefault(event["assignment_id"], [])
        if len(bucket) < 20:
            bucket.append(event)
    return [
        {
            **assignment,
            "recent_events": events_by_assignment.get(assignment["id"], []),
            "event_summary": assignment_event_summary(events_by_assignment.get(assignment["id"], [])),
        }
        for assignment in assignments
    ]


def issue_assignment_boot_token(assignment_id: str, session_id: str, session_token: str) -> str:
    """为一次被动装机签发短期 boot token，避免把 session token 写入 kernel cmdline。"""
    assignment = get_deployment_assignment(assignment_id)
    if assignment is None:
        raise ValueError("deployment_assignment_not_found")
    if session_id not in assignment.get("session_ids", []):
        raise ValueError("deployment_assignment_session_mismatch")
    conn = connect_db()
    row = conn.execute("SELECT * FROM client_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None or row["expires_at"] < int(time.time()) or not token_is_valid(session_token, row["session_token_hash"]):
        conn.close()
        raise ValueError("invalid_session_token")
    token = uuid.uuid4().hex
    now = int(time.time())
    expires_at = now + 21600
    token_hash = hash_session_token(token)
    conn.execute(
        """
        UPDATE deployment_assignments
        SET boot_token_hash = ?, boot_token_expires_at = ?, expires_at = MAX(expires_at, ?), updated_at = ?
        WHERE id = ?
        """,
        (token_hash, expires_at, expires_at, now, assignment_id),
    )
    conn.execute(
        """
        INSERT INTO assignment_boot_tokens (
            assignment_id, session_id, token_hash, expires_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(assignment_id, session_id)
        DO UPDATE SET token_hash = excluded.token_hash,
                      expires_at = excluded.expires_at,
                      updated_at = excluded.updated_at
        """,
        (assignment_id, session_id, token_hash, expires_at, now, now),
    )
    conn.commit()
    conn.close()
    return token


def verify_postinstall_access(assignment_id: str, session_id: str, token: str) -> tuple[dict, dict]:
    conn = connect_db()
    assignment_row = conn.execute("SELECT * FROM deployment_assignments WHERE id = ?", (assignment_id,)).fetchone()
    if assignment_row is None:
        conn.close()
        raise ValueError("deployment_assignment_not_found")
    assignment = deployment_assignment_payload(assignment_row)
    if session_id not in assignment.get("session_ids", []):
        conn.close()
        raise ValueError("deployment_assignment_session_mismatch")
    row = conn.execute("SELECT * FROM client_sessions WHERE session_id = ?", (session_id,)).fetchone()
    boot_token_row = conn.execute(
        """
        SELECT * FROM assignment_boot_tokens
        WHERE assignment_id = ? AND session_id = ?
        """,
        (assignment_id, session_id),
    ).fetchone()
    conn.close()
    now = int(time.time())
    session_token_ok = bool(row and row["expires_at"] >= now and token_is_valid(token, row["session_token_hash"]))
    boot_token_ok = bool(
        boot_token_row
        and boot_token_row["expires_at"] >= now
        and token_is_valid(token, boot_token_row["token_hash"])
    )
    legacy_boot_token_ok = bool(
        not boot_token_row
        and assignment_row["boot_token_hash"]
        and assignment_row["boot_token_expires_at"] >= now
        and token_is_valid(token, assignment_row["boot_token_hash"])
    )
    if row is None or not (session_token_ok or boot_token_ok or legacy_boot_token_ok):
        raise ValueError("invalid_session_token")
    return assignment, client_session_payload(row)


def postinstall_plan_payload(assignment: dict, session: dict) -> dict:
    plan = dict(assignment.get("resolved_software_plan") or {})
    os_family = str(plan.get("os_family") or os_family_for_boot_target(assignment["boot_target"]))
    if os_family == "windows":
        allowed_install_actions = sorted(WINDOWS_RUNNER_ACTIONS)
    elif os_family in {"ubuntu", "linux"}:
        allowed_install_actions = sorted(UBUNTU_RUNNER_ACTIONS)
    else:
        allowed_install_actions = []
    plan["assignment_id"] = assignment["id"]
    plan["session_id"] = session["session_id"]
    plan["boot_target"] = assignment["boot_target"]
    plan["boot_label"] = assignment["boot_label"]
    plan["install_preset_id"] = assignment.get("install_preset_id", "")
    plan["task_sequence_plan"] = assignment.get("task_sequence_plan") or {}
    plan["execution_model"] = {
        "server_executes_installers": False,
        "client_downloads_from_official_source": True,
        "raw_command_allowed": False,
        "allowed_install_actions": allowed_install_actions,
    }
    if os_family == "windows":
        plan["activation"] = {"kms": windows_kms_activation_plan()}
    return plan


def validate_postinstall_plan_for_runner(plan: dict, os_family: str) -> None:
    if plan.get("third_party_binary_stored") is not False or plan.get("client_downloads_from_official_source") is not True:
        raise ValueError("invalid_postinstall_plan_policy")
    allowed_actions = WINDOWS_RUNNER_ACTIONS if os_family == "windows" else UBUNTU_RUNNER_ACTIONS
    expected_phase = "windows_first_boot" if os_family == "windows" else "linux_first_boot"
    expected_os_family = "windows" if os_family == "windows" else "ubuntu"
    for variant in plan.get("variants", []):
        if variant.get("os_family") != expected_os_family:
            raise ValueError(f"postinstall_os_family_mismatch:{variant.get('id')}:{variant.get('os_family')}")
        if variant.get("review_status") != "approved":
            raise ValueError(f"postinstall_variant_not_approved:{variant.get('id')}")
        if variant.get("install_phase") != expected_phase:
            raise ValueError(f"postinstall_phase_not_supported:{variant.get('id')}")
        if variant.get("install_action") not in allowed_actions:
            raise ValueError(f"postinstall_action_not_supported:{variant.get('id')}:{variant.get('install_action')}")
        if variant.get("install_action") == "apt_package" and not SAFE_APT_PACKAGE_RE.match(str(variant.get("package_name", ""))):
            raise ValueError(f"postinstall_package_name_invalid:{variant.get('id')}")
        if variant.get("install_action") == "apt_package" and not is_supported_ubuntu_apt_source(variant):
            raise ValueError(f"postinstall_apt_repo_not_supported:{variant.get('id')}")
        if variant.get("install_action") == "download_deb" and variant.get("installer_type") != "deb":
            raise ValueError(f"postinstall_installer_type_invalid:{variant.get('id')}")
        if variant.get("install_action") == "msi_install" and variant.get("installer_type") != "msi":
            raise ValueError(f"postinstall_installer_type_invalid:{variant.get('id')}")
        if variant.get("install_action") == "exe_install":
            if variant.get("installer_type") != "exe":
                raise ValueError(f"postinstall_installer_type_invalid:{variant.get('id')}")
            if not str(variant.get("silent_args", "")).strip():
                raise ValueError(f"postinstall_exe_silent_args_required:{variant.get('id')}")
        if variant.get("install_action") == "office_odt_install":
            if variant.get("installer_type") != "office_odt":
                raise ValueError(f"postinstall_installer_type_invalid:{variant.get('id')}")
            if not SAFE_OFFICE_PRODUCT_ID_RE.match(str(variant.get("package_name", ""))):
                raise ValueError(f"postinstall_office_product_id_invalid:{variant.get('id')}")
        download_url = str(variant.get("download_url", ""))
        if variant.get("install_action") != "apt_package" and not is_https_url(download_url):
            raise ValueError(f"postinstall_download_url_blocked:{variant.get('id')}")
        if download_url and is_blocked_software_download_host(download_url):
            raise ValueError(f"postinstall_download_url_blocked:{variant.get('id')}")
        if variant.get("signature_policy") == "sha256_required" and not variant.get("sha256"):
            raise ValueError(f"postinstall_sha256_required:{variant.get('id')}")


def shell_single_quote(value: object) -> str:
    text = str(value)
    return "'" + text.replace("'", "'\"'\"'") + "'"


def ps_single_quote(value: object) -> str:
    text = str(value)
    return "'" + text.replace("'", "''") + "'"


def sanitize_event_message(value: object) -> str:
    text = SENSITIVE_EVENT_TEXT_RE.sub("<redacted>", str(value))
    return SAFE_IPXE_TEXT_RE.sub("-", text)[:160]


def bounded_int(value: object, min_value: int, max_value: int) -> int:
    if isinstance(value, bool):
        raise ValueError("invalid_integer_payload")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("invalid_integer_payload") from None
    if number < min_value or number > max_value:
        raise ValueError("integer_payload_out_of_range")
    return number


def ubuntu_postinstall_runner(assignment: dict, session: dict, token: str) -> str:
    plan = postinstall_plan_payload(assignment, session)
    validate_postinstall_plan_for_runner(plan, "ubuntu")
    lines = [
        "#!/bin/sh",
        "set -eu",
        "",
        "# SynaBoot Ubuntu first-boot postinstall runner.",
        "# 只消费后端已审核的 resolved_software_plan，不执行 raw command。",
        f"ASSIGNMENT_ID={shell_single_quote(assignment['id'])}",
        f"SESSION_ID={shell_single_quote(session['session_id'])}",
        f"SESSION_TOKEN={shell_single_quote(token)}",
        f"BASE_URL={shell_single_quote(f'http://{SERVER_IP}:{SYNABOOT_PORT}')}",
        "WORK_DIR=/var/lib/synaboot/postinstall",
        "mkdir -p \"$WORK_DIR\"",
        "PLAN_FILE=\"$WORK_DIR/plan.json\"",
        "log_event() {",
        "  stage=\"$1\"; status=\"$2\"; message=\"$3\"",
        "  python3 - \"$BASE_URL\" \"$ASSIGNMENT_ID\" \"$SESSION_ID\" \"$SESSION_TOKEN\" \"$stage\" \"$status\" \"$message\" <<'PY' || true",
        "import json, sys, urllib.request",
        "base, assignment, session, token, stage, status, message = sys.argv[1:8]",
        "payload = json.dumps({'session_id': session, 'token': token, 'stage': stage, 'status': status, 'message': message}).encode()",
        "req = urllib.request.Request(f'{base}/api/postinstall/assignments/{assignment}/events', data=payload, headers={'Content-Type': 'application/json'}, method='POST')",
        "urllib.request.urlopen(req, timeout=10).read()",
        "PY",
        "}",
        "log_event runner started 'Ubuntu postinstall runner started'",
        "trap 'code=$?; if [ \"$code\" -ne 0 ]; then log_event runner failed \"Ubuntu postinstall runner failed\"; fi' EXIT",
        "python3 - \"$BASE_URL\" \"$ASSIGNMENT_ID\" \"$SESSION_ID\" \"$SESSION_TOKEN\" \"$PLAN_FILE\" <<'PY'",
        "import sys, urllib.request",
        "base, assignment, session, token, plan_file = sys.argv[1:6]",
        "url = f'{base}/api/postinstall/assignments/{assignment}/plan?session_id={session}&token={token}'",
        "data = urllib.request.urlopen(url, timeout=30).read()",
        "open(plan_file, 'wb').write(data)",
        "PY",
        "python3 - \"$BASE_URL\" \"$ASSIGNMENT_ID\" \"$SESSION_ID\" \"$SESSION_TOKEN\" \"$PLAN_FILE\" <<'PY'",
        "import hashlib, ipaddress, json, os, re, subprocess, sys, tempfile, time, urllib.parse, urllib.request",
        "base, assignment, session, token, plan_file = sys.argv[1:6]",
        "plan = json.load(open(plan_file, encoding='utf-8'))",
        "safe_pkg = re.compile(r'^[a-z0-9][a-z0-9+.-]{0,127}$')",
        "allowed_actions = {'apt_package', 'download_deb'}",
        "def send_event(stage, status, message, payload=None):",
        "    body = {'session_id': session, 'token': token, 'stage': stage, 'status': status, 'message': message}",
        "    if payload:",
        "        body['payload'] = payload",
        "    data = json.dumps(body).encode()",
        "    req = urllib.request.Request(f'{base}/api/postinstall/assignments/{assignment}/events', data=data, headers={'Content-Type': 'application/json'}, method='POST')",
        "    try:",
        "        urllib.request.urlopen(req, timeout=10).read()",
        "    except Exception:",
        "        pass",
        "def blocked_url(value):",
        "    parsed = urllib.parse.urlparse(value)",
        "    if parsed.scheme != 'https' or not parsed.netloc:",
        "        return True",
        "    if parsed.path.startswith(('/images', '/boot')):",
        "        return True",
        "    host = (parsed.hostname or '').lower()",
        "    if host in {'localhost', 'localhost.localdomain'}:",
        "        return True",
        "    try:",
        "        addr = ipaddress.ip_address(host)",
        "    except ValueError:",
        "        return False",
        "    return addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved",
        "def wait_for_apt_locks():",
        "    lock_paths = ['/var/lib/dpkg/lock-frontend', '/var/lib/dpkg/lock', '/var/cache/apt/archives/lock']",
        "    deadline = time.time() + 300",
        "    while time.time() < deadline:",
        "        busy = False",
        "        for lock_path in lock_paths:",
        "            if os.path.exists(lock_path):",
        "                try:",
        "                    subprocess.check_call(['fuser', lock_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)",
        "                    busy = True",
        "                    break",
        "                except (FileNotFoundError, subprocess.CalledProcessError):",
        "                    continue",
        "        if not busy:",
        "            return",
        "        time.sleep(5)",
        "    raise SystemExit('apt/dpkg lock timeout')",
        "if plan.get('third_party_binary_stored') is not False or plan.get('client_downloads_from_official_source') is not True:",
        "    raise SystemExit('invalid plan policy')",
        "if plan.get('os_family') not in {'ubuntu', 'linux'}:",
        "    raise SystemExit('invalid plan os_family')",
        "for item in plan.get('variants', []):",
        "    variant_id = str(item.get('id') or 'unknown')",
        "    try:",
        "        send_event('variant', 'started', f'Installing {variant_id}', {'variant_id': variant_id})",
        "        action = item.get('install_action')",
        "        url = item.get('download_url', '')",
        "        sha256 = item.get('sha256', '')",
        "        if item.get('os_family') != 'ubuntu' or item.get('install_phase') != 'linux_first_boot' or item.get('review_status') != 'approved':",
        "            raise SystemExit(f'blocked variant policy: {variant_id}')",
        "        if action not in allowed_actions:",
        "            raise SystemExit(f'blocked install action: {action}')",
        "        if item.get('signature_policy') == 'sha256_required' and not sha256:",
        "            raise SystemExit(f'missing sha256 for {variant_id}')",
        "        wait_for_apt_locks()",
        "        if action == 'apt_package':",
        "            pkg = item.get('package_name', '')",
        "            if not safe_pkg.match(pkg):",
        "                raise SystemExit(f'invalid apt package name for {variant_id}')",
        "            subprocess.check_call(['apt-get', 'update'])",
        "            subprocess.check_call(['apt-get', 'install', '-y', pkg])",
        "        elif action == 'download_deb':",
        "            if item.get('installer_type') != 'deb':",
        "                raise SystemExit(f'invalid installer type for {variant_id}')",
        "            if blocked_url(url):",
        "                raise SystemExit(f'blocked download url for {variant_id}')",
        "            fd, path = tempfile.mkstemp(suffix='.deb')",
        "            os.close(fd)",
        "            try:",
        "                urllib.request.urlretrieve(url, path)",
        "                if sha256:",
        "                    digest = hashlib.sha256()",
        "                    with open(path, 'rb') as handle:",
        "                        for chunk in iter(lambda: handle.read(1024 * 1024), b''):",
        "                            digest.update(chunk)",
        "                    if digest.hexdigest().lower() != sha256.lower():",
        "                        raise SystemExit(f'sha256 mismatch for {variant_id}')",
        "                subprocess.check_call(['apt-get', 'install', '-y', path])",
        "            finally:",
        "                try:",
        "                    os.remove(path)",
        "                except FileNotFoundError:",
        "                    pass",
        "        send_event('variant', 'completed', f'Installed {variant_id}', {'variant_id': variant_id})",
        "    except BaseException:",
        "        send_event('variant', 'failed', f'Install failed for {variant_id}', {'variant_id': variant_id})",
        "        raise",
        "PY",
        "trap - EXIT",
        "log_event runner completed 'Ubuntu postinstall runner completed'",
    ]
    if not plan.get("variants"):
        lines.extend(["", "echo 'No software variants assigned; nothing to install.'"])
    return "\n".join(lines) + "\n"


def windows_postinstall_runner(assignment: dict, session: dict, token: str) -> str:
    plan = postinstall_plan_payload(assignment, session)
    validate_postinstall_plan_for_runner(plan, "windows")
    return f"""# SynaBoot Windows first-boot postinstall runner.
# 只消费后端已审核的 resolved_software_plan，不执行 raw command。
# Office 使用 Microsoft Office Deployment Tool；Windows/Office 激活仅使用管理员配置的自有 KMS。
$ErrorActionPreference = "Stop"
$AssignmentId = {ps_single_quote(assignment['id'])}
$SessionId = {ps_single_quote(session['session_id'])}
$SessionToken = {ps_single_quote(token)}
$BaseUrl = {ps_single_quote(f'http://{SERVER_IP}:{SYNABOOT_PORT}')}
$WorkDir = Join-Path $env:ProgramData "SynaBoot\\PostInstall"
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
$PlanFile = Join-Path $WorkDir "plan.json"

function Send-SynaBootEvent([string]$Stage, [string]$Status, [string]$Message, [hashtable]$Payload = @{{}}) {{
  $BodyObject = @{{ session_id = $SessionId; token = $SessionToken; stage = $Stage; status = $Status; message = $Message }}
  if ($Payload.Count -gt 0) {{ $BodyObject.payload = $Payload }}
  $Body = $BodyObject | ConvertTo-Json -Compress
  try {{ Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/postinstall/assignments/$AssignmentId/events" -ContentType "application/json" -Body $Body | Out-Null }} catch {{ }}
}}

Send-SynaBootEvent "runner" "started" "Windows postinstall runner started"
try {{
Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/postinstall/assignments/$AssignmentId/plan?session_id=$SessionId&token=$SessionToken" -OutFile $PlanFile
$Plan = Get-Content $PlanFile -Raw | ConvertFrom-Json
if ($Plan.third_party_binary_stored -ne $false -or $Plan.client_downloads_from_official_source -ne $true) {{ throw "Invalid SynaBoot software plan policy" }}
if ($Plan.os_family -ne "windows") {{ throw "Invalid SynaBoot software plan os_family" }}

function Test-SynaBootDownloadUrl([string]$Url) {{
  $Uri = [System.Uri]$Url
  if ($Uri.Scheme -ne "https") {{ return $false }}
  if ($Uri.AbsolutePath.StartsWith("/images") -or $Uri.AbsolutePath.StartsWith("/boot")) {{ return $false }}
  $HostName = $Uri.Host.ToLowerInvariant()
  if ($HostName -eq "localhost" -or $HostName -eq "localhost.localdomain") {{ return $false }}
  $Address = $null
  if ([System.Net.IPAddress]::TryParse($HostName, [ref]$Address)) {{
    $Bytes = $Address.GetAddressBytes()
    if ($Address.IsIPv6LinkLocal -or [System.Net.IPAddress]::IsLoopback($Address)) {{ return $false }}
    if ($Bytes.Length -eq 4) {{
      if ($Bytes[0] -eq 10 -or $Bytes[0] -eq 127 -or ($Bytes[0] -eq 169 -and $Bytes[1] -eq 254) -or ($Bytes[0] -eq 172 -and $Bytes[1] -ge 16 -and $Bytes[1] -le 31) -or ($Bytes[0] -eq 192 -and $Bytes[1] -eq 168)) {{ return $false }}
    }}
  }}
  return $true
}}

function Test-SynaBootOfficeProductId([string]$ProductId) {{
  return $ProductId -match '^[A-Za-z0-9]{{3,64}}$'
}}

function Get-SynaBootOfficeChannel([string]$ProductId) {{
  if ($ProductId -match '2024.*Volume$') {{ return "PerpetualVL2024" }}
  if ($ProductId -match '2021.*Volume$') {{ return "PerpetualVL2021" }}
  if ($ProductId -match '2019.*Volume$') {{ return "PerpetualVL2019" }}
  return "Current"
}}

function Invoke-SynaBootMsiInstall($Item) {{
  $Installer = Join-Path $WorkDir ($Item.id + ".msi")
  try {{
    Invoke-WebRequest -UseBasicParsing -Uri $Item.download_url -OutFile $Installer
    if ($Item.sha256) {{
      $Actual = (Get-FileHash -Algorithm SHA256 $Installer).Hash.ToLower()
      if ($Actual -ne $Item.sha256.ToLower()) {{ throw "sha256 mismatch for $($Item.id)" }}
    }}
    $Args = @("/i", $Installer)
    if ($Item.silent_args) {{ $Args += $Item.silent_args }}
    $Process = Start-Process msiexec.exe -ArgumentList $Args -Wait -PassThru -NoNewWindow
    $SuccessCodes = @($Item.return_codes.success)
    $SoftRebootCodes = @($Item.return_codes.soft_reboot)
    if (($SuccessCodes + $SoftRebootCodes) -notcontains $Process.ExitCode) {{ throw "msiexec failed with exit code $($Process.ExitCode)" }}
  }} finally {{
    Remove-Item -LiteralPath $Installer -Force -ErrorAction SilentlyContinue
  }}
}}

function Invoke-SynaBootExeInstall($Item) {{
  $Installer = Join-Path $WorkDir ($Item.id + ".exe")
  try {{
    Invoke-WebRequest -UseBasicParsing -Uri $Item.download_url -OutFile $Installer
    if ($Item.sha256) {{
      $Actual = (Get-FileHash -Algorithm SHA256 $Installer).Hash.ToLower()
      if ($Actual -ne $Item.sha256.ToLower()) {{ throw "sha256 mismatch for $($Item.id)" }}
    }}
    $Args = @()
    if ($Item.silent_args) {{ $Args += $Item.silent_args }}
    if (-not $Args.Count) {{ throw "EXE installer requires reviewed silent_args: $($Item.id)" }}
    $Process = Start-Process -FilePath $Installer -ArgumentList $Args -Wait -PassThru -NoNewWindow
    $SuccessCodes = @($Item.return_codes.success)
    $SoftRebootCodes = @($Item.return_codes.soft_reboot)
    if (($SuccessCodes + $SoftRebootCodes) -notcontains $Process.ExitCode) {{ throw "EXE installer failed with exit code $($Process.ExitCode)" }}
  }} finally {{
    Remove-Item -LiteralPath $Installer -Force -ErrorAction SilentlyContinue
  }}
}}

function Invoke-SynaBootOfficeOdtInstall($Item) {{
  $ProductId = [string]$Item.package_name
  if (-not (Test-SynaBootOfficeProductId $ProductId)) {{ throw "Invalid Office product id: $($Item.id)" }}
  $OdtInstaller = Join-Path $WorkDir ($Item.id + "-odt.exe")
  $OdtDir = Join-Path $WorkDir ($Item.id + "-odt")
  $Channel = Get-SynaBootOfficeChannel $ProductId
  try {{
    New-Item -ItemType Directory -Force -Path $OdtDir | Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri $Item.download_url -OutFile $OdtInstaller
    if ($Item.sha256) {{
      $Actual = (Get-FileHash -Algorithm SHA256 $OdtInstaller).Hash.ToLower()
      if ($Actual -ne $Item.sha256.ToLower()) {{ throw "sha256 mismatch for $($Item.id)" }}
    }}
    $Extract = Start-Process -FilePath $OdtInstaller -ArgumentList @("/quiet", "/extract:$OdtDir") -Wait -PassThru -NoNewWindow
    if ($Extract.ExitCode -ne 0) {{ throw "Office Deployment Tool extract failed with exit code $($Extract.ExitCode)" }}
    $SetupExe = Join-Path $OdtDir "setup.exe"
    if (-not (Test-Path -LiteralPath $SetupExe -PathType Leaf)) {{ throw "Office setup.exe not found after ODT extract" }}
    $ConfigFile = Join-Path $OdtDir "configuration.xml"
    @"
<Configuration>
  <Add OfficeClientEdition="64" Channel="$Channel">
    <Product ID="$ProductId">
      <Language ID="MatchOS" />
    </Product>
  </Add>
  <Display Level="None" AcceptEULA="TRUE" />
  <Property Name="AUTOACTIVATE" Value="1" />
</Configuration>
"@ | Set-Content -LiteralPath $ConfigFile -Encoding UTF8
    $Install = Start-Process -FilePath $SetupExe -ArgumentList @("/configure", $ConfigFile) -Wait -PassThru -NoNewWindow
    if ($Install.ExitCode -ne 0) {{ throw "Office Deployment Tool configure failed with exit code $($Install.ExitCode)" }}
  }} finally {{
    Remove-Item -LiteralPath $OdtInstaller -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $OdtDir -Recurse -Force -ErrorAction SilentlyContinue
  }}
}}

function Get-SynaBootOfficeOsppPath {{
  $Candidates = @(
    "$env:ProgramFiles\\Microsoft Office\\Office16\\OSPP.VBS",
    "${{env:ProgramFiles(x86)}}\\Microsoft Office\\Office16\\OSPP.VBS",
    "$env:ProgramFiles\\Microsoft Office\\root\\Office16\\OSPP.VBS",
    "${{env:ProgramFiles(x86)}}\\Microsoft Office\\root\\Office16\\OSPP.VBS"
  )
  foreach ($Path in $Candidates) {{
    if ($Path -and (Test-Path -LiteralPath $Path -PathType Leaf)) {{ return $Path }}
  }}
  return ""
}}

function Invoke-SynaBootWindowsKmsActivation($Kms) {{
  if (-not $Kms -or -not $Kms.enabled -or -not $Kms.windows) {{ return }}
  if (-not $Kms.host -or -not $Kms.port) {{ throw "KMS host or port missing for Windows activation" }}
  $Slmgr = Join-Path $env:SystemRoot "System32\\slmgr.vbs"
  Send-SynaBootEvent "runner" "started" "Windows KMS activation started" @{{ action_id = "windows_kms_activation" }}
  cscript.exe //nologo $Slmgr /skms "$($Kms.host):$($Kms.port)"
  cscript.exe //nologo $Slmgr /ato
  Send-SynaBootEvent "runner" "completed" "Windows KMS activation completed" @{{ action_id = "windows_kms_activation" }}
}}

function Invoke-SynaBootOfficeKmsActivation($Kms) {{
  if (-not $Kms -or -not $Kms.enabled -or -not $Kms.office) {{ return }}
  if (-not $Kms.host -or -not $Kms.port) {{ throw "KMS host or port missing for Office activation" }}
  $Ospp = Get-SynaBootOfficeOsppPath
  if (-not $Ospp) {{ throw "Office ospp.vbs not found for KMS activation" }}
  Send-SynaBootEvent "runner" "started" "Office KMS activation started" @{{ action_id = "office_kms_activation" }}
  cscript.exe //nologo $Ospp /sethst:$($Kms.host)
  cscript.exe //nologo $Ospp /setprt:$($Kms.port)
  cscript.exe //nologo $Ospp /act
  Send-SynaBootEvent "runner" "completed" "Office KMS activation completed" @{{ action_id = "office_kms_activation" }}
}}

foreach ($Item in $Plan.variants) {{
  $VariantId = [string]$Item.id
  try {{
    Send-SynaBootEvent "variant" "started" "Installing $VariantId" @{{ variant_id = $VariantId }}
    if ($Item.os_family -ne "windows" -or $Item.install_phase -ne "windows_first_boot" -or $Item.review_status -ne "approved") {{
      throw "Blocked SynaBoot software variant policy: $VariantId"
    }}
    if ($Item.install_action -notin @("msi_install", "exe_install", "office_odt_install")) {{
      throw "Blocked SynaBoot install action: $($Item.install_action)"
    }}
    if ($Item.install_action -eq "msi_install" -and $Item.installer_type -ne "msi") {{
      throw "Blocked SynaBoot installer type: $VariantId"
    }}
    if ($Item.install_action -eq "exe_install" -and $Item.installer_type -ne "exe") {{
      throw "Blocked SynaBoot installer type: $VariantId"
    }}
    if ($Item.install_action -eq "office_odt_install" -and $Item.installer_type -ne "office_odt") {{
      throw "Blocked SynaBoot installer type: $VariantId"
    }}
    if (-not (Test-SynaBootDownloadUrl $Item.download_url)) {{
      throw "Blocked SynaBoot download URL: $VariantId"
    }}
    if ($Item.signature_policy -eq "sha256_required" -and -not $Item.sha256) {{
      throw "Missing required sha256: $VariantId"
    }}
    switch ($Item.install_action) {{
      "msi_install" {{ Invoke-SynaBootMsiInstall $Item }}
      "exe_install" {{ Invoke-SynaBootExeInstall $Item }}
      "office_odt_install" {{ Invoke-SynaBootOfficeOdtInstall $Item }}
    }}
    Send-SynaBootEvent "variant" "completed" "Installed $VariantId" @{{ variant_id = $VariantId }}
  }} catch {{
    Send-SynaBootEvent "variant" "failed" "Install failed for $VariantId" @{{ variant_id = $VariantId }}
    throw
  }}
}}
Invoke-SynaBootWindowsKmsActivation $Plan.activation.kms
Invoke-SynaBootOfficeKmsActivation $Plan.activation.kms
Send-SynaBootEvent "runner" "completed" "Windows postinstall runner completed"
}} catch {{
  Send-SynaBootEvent "runner" "failed" "Windows postinstall runner failed"
  throw
}}
"""


def ubuntu_nocloud_meta_data(assignment: dict, session: dict) -> str:
    instance_id = f"synaboot-{assignment['id']}-{session['session_id']}"
    return f"""instance-id: {instance_id}
local-hostname: synaboot-client
"""


def ubuntu_nocloud_user_data(assignment: dict, session: dict, token: str) -> str:
    validate_postinstall_plan_for_runner(postinstall_plan_payload(assignment, session), "ubuntu")
    runner_url = f"http://{SERVER_IP}:{SYNABOOT_PORT}/api/postinstall/assignments/{assignment['id']}/runner.sh?session_id={session['session_id']}&token={token}"
    runner_url_shell = shell_single_quote(runner_url)
    return f"""#cloud-config
autoinstall:
  version: 1
  interactive-sections:
    - identity
    - storage
  late-commands:
    - curtin in-target --target=/target -- mkdir -p /usr/local/sbin /etc/systemd/system /var/lib/synaboot/postinstall
    - |
      cat > /target/usr/local/sbin/synaboot-postinstall-bootstrap.sh <<'EOF'
      #!/bin/sh
      set -eu
      WORK_DIR=/var/lib/synaboot/postinstall
      RUNNER_URL={runner_url_shell}
      mkdir -p "$WORK_DIR"
      attempt=1
      while [ "$attempt" -le 20 ]; do
        if command -v curl >/dev/null 2>&1; then
          curl -fsSL "$RUNNER_URL" -o "$WORK_DIR/runner.sh" && break
        else
          wget -O "$WORK_DIR/runner.sh" "$RUNNER_URL" && break
        fi
        rm -f "$WORK_DIR/runner.sh"
        attempt=$((attempt + 1))
        sleep 15
      done
      test -s "$WORK_DIR/runner.sh"
      chmod 700 "$WORK_DIR/runner.sh"
      /bin/sh "$WORK_DIR/runner.sh"
      rm -f "$WORK_DIR/runner.sh"
      systemctl disable synaboot-postinstall.service >/dev/null 2>&1 || true
      EOF
    - chmod 700 /target/usr/local/sbin/synaboot-postinstall-bootstrap.sh
    - |
      cat > /target/etc/systemd/system/synaboot-postinstall.service <<'EOF'
      [Unit]
      Description=SynaBoot first-boot software installation
      After=network-online.target
      Wants=network-online.target
      StartLimitBurst=20
      StartLimitIntervalSec=15min

      [Service]
      Type=oneshot
      ExecStart=/usr/local/sbin/synaboot-postinstall-bootstrap.sh
      RemainAfterExit=yes
      Restart=on-failure
      RestartSec=30s

      [Install]
      WantedBy=multi-user.target
      EOF
    - curtin in-target --target=/target -- systemctl enable synaboot-postinstall.service
"""


def windows_setupcomplete_cmd(assignment: dict, session: dict, token: str) -> str:
    validate_postinstall_plan_for_runner(postinstall_plan_payload(assignment, session), "windows")
    runner_url = f"http://{SERVER_IP}:{SYNABOOT_PORT}/api/postinstall/assignments/{assignment['id']}/runner.ps1?session_id={session['session_id']}&token={token}"
    runner_url_ps = ps_single_quote(runner_url)
    return f"""@echo off
set WORKDIR=%ProgramData%\\SynaBoot\\PostInstall
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "New-Item -ItemType Directory -Force -Path $env:ProgramData\\SynaBoot\\PostInstall | Out-Null; Invoke-WebRequest -Uri {runner_url_ps} -OutFile $env:ProgramData\\SynaBoot\\PostInstall\\runner.ps1; powershell.exe -NoProfile -ExecutionPolicy Bypass -File $env:ProgramData\\SynaBoot\\PostInstall\\runner.ps1"
exit /b %ERRORLEVEL%
"""


def windows_hotpe_injection_helper_ps1(assignment: dict, session: dict, token: str) -> str:
    """生成 HotPE/WinPE 中手动注入 SetupComplete 的受控辅助脚本。

    该脚本是 Windows 软件自动安装闭环的受控注入点。它优先使用管理员明确传入的
    Windows 根目录；如未传入，只在唯一发现一个离线 Windows 目录时自动注入。
    脚本不执行分区/格式化，也不下载第三方软件包；真正的软件安装发生在已安装
    Windows 的首次启动 runner 中。
    """
    validate_postinstall_plan_for_runner(postinstall_plan_payload(assignment, session), "windows")
    setupcomplete_url = f"http://{SERVER_IP}:{SYNABOOT_PORT}/api/postinstall/assignments/{assignment['id']}/setupcomplete.cmd?session_id={session['session_id']}&token={token}"
    setupcomplete_url_ps = ps_single_quote(setupcomplete_url)
    assignment_id_ps = ps_single_quote(assignment["id"])
    session_id_ps = ps_single_quote(session["session_id"])
    return f"""# SynaBoot Windows postinstall injection helper for HotPE/WinPE.
# 用途：在已确认目标 Windows 目录后，写入 SetupComplete.cmd。
# 安全边界：不清盘，不格式化，不改网络，不托管第三方软件安装包。
param(
  [string]$WindowsRoot = ""
)

$ErrorActionPreference = "Stop"
$AssignmentId = {assignment_id_ps}
$SessionId = {session_id_ps}
$SetupCompleteUrl = {setupcomplete_url_ps}

function Get-SynaBootWindowsRootCandidates {{
  $Candidates = New-Object System.Collections.Generic.List[string]
  Get-PSDrive -PSProvider FileSystem | ForEach-Object {{
    $RootPath = $_.Root.TrimEnd("\\")
    if ($RootPath) {{
      foreach ($Candidate in @((Join-Path $RootPath "Windows"), $RootPath)) {{
        $SystemHive = Join-Path $Candidate "System32\\config\\SYSTEM"
        if (Test-Path -LiteralPath $SystemHive -PathType Leaf) {{
          if (-not $Candidates.Contains($Candidate)) {{ $Candidates.Add($Candidate) }}
        }}
      }}
    }}
  }}
  return @($Candidates)
}}

$Root = $WindowsRoot.TrimEnd("\\", "/")
if ($Root) {{
  if (-not (Test-Path -LiteralPath $Root -PathType Container)) {{
    throw "WindowsRoot does not exist: $Root"
  }}
  $WindowsDir = if ((Split-Path -Leaf $Root) -ieq "Windows") {{ $Root }} else {{ Join-Path $Root "Windows" }}
}} else {{
  $Candidates = @(Get-SynaBootWindowsRootCandidates)
  if ($Candidates.Count -eq 0) {{
    throw "No installed Windows directory was found. Re-run with -WindowsRoot X:\\Windows after installation."
  }}
  if ($Candidates.Count -gt 1) {{
    throw ("Multiple Windows directories found: " + ($Candidates -join ", ") + ". Re-run with explicit -WindowsRoot.")
  }}
  $WindowsDir = $Candidates[0]
}}
if (-not (Test-Path -LiteralPath $WindowsDir -PathType Container)) {{
  throw "Windows directory not found: $WindowsDir"
}}

$SystemHive = Join-Path $WindowsDir "System32\\config\\SYSTEM"
if (-not (Test-Path -LiteralPath $SystemHive -PathType Leaf)) {{
  throw "Target does not look like an installed Windows system: $SystemHive"
}}

$ScriptsDir = Join-Path $WindowsDir "Setup\\Scripts"
New-Item -ItemType Directory -Force -Path $ScriptsDir | Out-Null
$SetupCompletePath = Join-Path $ScriptsDir "SetupComplete.cmd"

Invoke-WebRequest -UseBasicParsing -Uri $SetupCompleteUrl -OutFile $SetupCompletePath
if (-not (Test-Path -LiteralPath $SetupCompletePath -PathType Leaf)) {{
  throw "SetupComplete.cmd was not written"
}}

$Marker = Join-Path $ScriptsDir "synaboot-postinstall-assignment.txt"
@(
  "assignment_id=$AssignmentId",
  "session_id=$SessionId",
  "created_at=$(Get-Date -Format o)",
  "note=SetupComplete.cmd will download the token-protected runner from SynaBoot on first boot."
) | Set-Content -LiteralPath $Marker -Encoding ASCII

Write-Host "SynaBoot SetupComplete.cmd injected into $SetupCompletePath"
Write-Host "Reboot into the installed Windows system to run the postinstall runner."
"""


def record_postinstall_event(assignment_id: str, payload: dict) -> dict:
    session_id = str(payload.get("session_id", "")).strip()
    token = str(payload.get("token", "")).strip()
    assignment, _session = verify_postinstall_access(assignment_id, session_id, token)
    stage = str(payload.get("stage", ""))[:80]
    status = str(payload.get("status", ""))[:80]
    if stage not in POSTINSTALL_EVENT_STAGES:
        raise ValueError("invalid_postinstall_event_stage")
    if status not in POSTINSTALL_EVENT_STATUSES:
        raise ValueError("invalid_postinstall_event_status")
    event_payload = payload.get("payload", {})
    if not isinstance(event_payload, dict):
        raise ValueError("invalid_postinstall_event_payload")
    allowed_payload: dict[str, object] = {}
    for key in {"variant_id", "action_id"}:
        if key in event_payload:
            allowed_payload[key] = SAFE_IPXE_TEXT_RE.sub("-", str(event_payload.get(key, "")))[:120]
    if "exit_code" in event_payload:
        allowed_payload["exit_code"] = bounded_int(event_payload.get("exit_code"), -32768, 32767)
    if "duration_seconds" in event_payload:
        allowed_payload["duration_seconds"] = bounded_int(event_payload.get("duration_seconds"), 0, 86400)
    event = {
        "id": uuid.uuid4().hex,
        "session_id": session_id,
        "assignment_id": assignment["id"],
        "event_type": "postinstall",
        "stage": stage,
        "status": status,
        "message": sanitize_event_message(payload.get("message", "")),
        "payload": json.dumps(allowed_payload, ensure_ascii=False),
        "created_at": int(time.time()),
    }
    conn = connect_db()
    conn.execute(
        """
        INSERT INTO client_events (
            id, session_id, assignment_id, event_type, stage, status, message, payload, created_at
        ) VALUES (
            :id, :session_id, :assignment_id, :event_type, :stage, :status, :message, :payload, :created_at
        )
        """,
        event,
    )
    if stage == "runner":
        conn.execute(
            "UPDATE deployment_assignments SET status = ?, updated_at = ? WHERE id = ?",
            (f"postinstall_{event['status']}"[:80], event["created_at"], assignment["id"]),
        )
    else:
        conn.execute(
            "UPDATE deployment_assignments SET updated_at = ? WHERE id = ?",
            (event["created_at"], assignment["id"]),
        )
    conn.commit()
    conn.close()
    return {**event, "payload": allowed_payload}


def assignment_options(session_ids: list[str]) -> dict | None:
    sessions = [get_client_session(session_id) for session_id in session_ids if session_id]
    sessions = [session for session in sessions if session is not None]
    if not sessions:
        return None
    targets = boot_target_catalog()
    software_by_target = {target["target"]: compatible_software_packages_for_target(target) for target in targets}
    profiles_by_target = {target["target"]: compatible_software_profiles_for_target(target) for target in targets}
    install_presets_by_target: dict[str, list[dict]] = {}
    for target in targets:
        target_id = target["target"]
        os_family = os_family_for_boot_target(target_id)
        template_family = "ubuntu" if os_family == "linux" else os_family
        if template_family:
            install_presets_by_target[target_id] = [
                preset
                for preset in list_install_presets(os_family=template_family)
                if preset.get("boot_target") == target_id and preset.get("assignable")
            ]
        else:
            install_presets_by_target[target_id] = []
    first_software_target = next((target for target in targets if software_by_target.get(target["target"])), None)
    os_families = sorted({os_family_for_boot_target(target["target"]) for target in targets if os_family_for_boot_target(target["target"])})
    return {
        "schema_version": "synaboot.assignment-options.v1",
        "session": sessions[0],
        "sessions": sessions,
        "boot_targets": targets,
        "compatible_software_packages": software_by_target.get(first_software_target["target"], []) if first_software_target else [],
        "compatible_software_by_target": software_by_target,
        "compatible_software_profiles_by_target": profiles_by_target,
        "install_presets_by_target": install_presets_by_target,
        "install_presets": [
            preset
            for presets in install_presets_by_target.values()
            for preset in presets
        ],
        "compatible_software_variants": [
            variant
            for packages in software_by_target.values()
            for package in packages
            for variant in package.get("variants", [])
        ],
        "software_profiles": list_software_profiles(),
        "software_market_status": "ready",
        "software_market_policy": {
            "artifact_hosting_allowed": False,
            "third_party_binary_stored": False,
            "client_downloads_from_official_source": True,
            "allowed_source_policies": sorted(ALLOWED_SOFTWARE_SOURCE_POLICIES),
            "assignable_review_statuses": sorted(ASSIGNABLE_SOFTWARE_REVIEW_STATUSES),
            "supported_os_families": os_families,
        },
        "conflicts": [],
        "notes": [
            "软件市场只保存官方来源、安装模板和校验策略，不托管第三方安装包。",
            "未通过审核或缺少校验策略的软件只展示，不会进入自动安装任务。",
            "安装任务预设只保存系统和软件组合；不包含清盘、格式化或磁盘设置。",
        ],
    }


def assign_client_session(session_id: str, target: str) -> dict | None:
    targets = {item["target"]: item for item in boot_target_catalog()}
    if target not in targets:
        raise ValueError("invalid_or_unready_target")
    conn = connect_db()
    row = conn.execute("SELECT * FROM client_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        conn.close()
        return None
    now = int(time.time())
    conn.execute(
        """
        UPDATE client_sessions
        SET selected_target = ?, selected_label = ?, state = 'assignment_received',
            last_seen_at = ?, expires_at = ?
        WHERE session_id = ?
        """,
        (target, targets[target]["label"], now, now + 900, session_id),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM client_sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    return client_session_payload(updated)


def create_deployment_assignment(payload: dict) -> dict | None:
    raw_session_ids = payload.get("session_ids")
    if raw_session_ids is None:
        raw_session_ids = [payload.get("session_id", "")]
    if not isinstance(raw_session_ids, list):
        raise ValueError("session_ids_required")
    session_ids = list(dict.fromkeys(str(item).strip() for item in raw_session_ids if str(item).strip()))
    session_id = session_ids[0] if session_ids else ""
    boot_target = str(payload.get("boot_target") or payload.get("target") or "").strip()
    if not session_ids:
        raise ValueError("session_ids_required")
    if not boot_target:
        raise ValueError("boot_target_required")
    targets = {item["target"]: item for item in boot_target_catalog()}
    if boot_target not in targets:
        raise ValueError("invalid_or_unready_target")
    software_profile_ids = payload.get("software_profile_ids", [])
    software_package_ids = payload.get("software_package_ids", [])
    software_variant_ids = payload.get("software_variant_ids", [])
    install_preset_id = str(payload.get("install_preset_id", "") or "").strip()
    if not isinstance(software_profile_ids, list) or not isinstance(software_variant_ids, list) or not isinstance(software_package_ids, list):
        raise ValueError("invalid_software_selection")
    install_preset = get_install_preset(install_preset_id) if install_preset_id else None
    if install_preset_id and not install_preset:
        raise ValueError("install_preset_not_found")
    if install_preset:
        if not install_preset.get("assignable"):
            raise ValueError("install_preset_not_assignable")
        if install_preset.get("boot_target") != boot_target:
            raise ValueError("install_preset_target_mismatch")
        software_package_ids = list(dict.fromkeys([*install_preset.get("software_package_ids", []), *software_package_ids]))
        software_profile_ids = list(dict.fromkeys([*install_preset.get("software_profile_ids", []), *software_profile_ids]))
    if (software_variant_ids or software_profile_ids or software_package_ids) and not software_assignment_supported_for_target(targets[boot_target]):
        raise ValueError(f"postinstall_injection_not_ready:{targets[boot_target]['kind']}")
    software_package_ids = [str(item) for item in software_package_ids]
    software_profile_ids = [str(item) for item in software_profile_ids]
    software_variant_ids = [str(item) for item in software_variant_ids]
    if os_family_for_boot_target(boot_target) == "windows" and software_assignment_supported_for_target(targets[boot_target]):
        software_package_ids = list(dict.fromkeys([*software_package_ids, *DEFAULT_WINDOWS_SOFTWARE_PACKAGE_IDS]))
    resolved_software_plan = resolve_software_plan(software_variant_ids, boot_target, software_profile_ids, software_package_ids)
    task_sequence_plan = build_task_sequence_plan(boot_target, install_preset, resolved_software_plan)

    now = int(time.time())
    assignment_id = uuid.uuid4().hex[:16]
    row = {
        "id": assignment_id,
        "session_id": session_id,
        "session_ids": json.dumps(session_ids, ensure_ascii=False),
        "source_image_id": str(payload.get("source_image_id", "")),
        "boot_target": boot_target,
        "boot_label": targets[boot_target]["label"],
        "software_package_ids": json.dumps(software_package_ids, ensure_ascii=False),
        "software_profile_ids": json.dumps(software_profile_ids, ensure_ascii=False),
        "software_variant_ids": json.dumps(software_variant_ids, ensure_ascii=False),
        "resolved_software_plan": json.dumps(resolved_software_plan, ensure_ascii=False),
        "install_preset_id": install_preset_id,
        "task_sequence_plan": json.dumps(task_sequence_plan, ensure_ascii=False),
        "status": "assignment_received",
        "created_by": "admin",
        "created_at": now,
        "updated_at": now,
        "expires_at": now + 900,
    }
    conn = connect_db()
    placeholders = ",".join("?" for _ in session_ids)
    existing_rows = conn.execute(
        f"SELECT * FROM client_sessions WHERE session_id IN ({placeholders})",
        session_ids,
    ).fetchall()
    if len(existing_rows) != len(session_ids):
        conn.close()
        return None
    try:
        conn.execute("BEGIN")
        for item in session_ids:
            conn.execute(
                """
                UPDATE client_sessions
                SET selected_target = ?, selected_label = ?, state = 'assignment_received',
                    last_seen_at = ?, expires_at = ?
                WHERE session_id = ?
                """,
                (boot_target, targets[boot_target]["label"], now, now + 900, item),
            )
        conn.execute(
            """
            INSERT INTO deployment_assignments (
                id, session_id, session_ids, source_image_id, boot_target, boot_label,
                software_package_ids, software_profile_ids, software_variant_ids, resolved_software_plan,
                install_preset_id, task_sequence_plan, status, created_by,
                created_at, updated_at, expires_at
            )
            VALUES (
                :id, :session_id, :session_ids, :source_image_id, :boot_target, :boot_label,
                :software_package_ids, :software_profile_ids, :software_variant_ids, :resolved_software_plan,
                :install_preset_id, :task_sequence_plan, :status, :created_by,
                :created_at, :updated_at, :expires_at
            )
            """,
            row,
        )
        updated_rows = conn.execute(
            f"SELECT * FROM client_sessions WHERE session_id IN ({placeholders})",
            session_ids,
        ).fetchall()
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    sessions_by_id = {item["session_id"]: client_session_payload(item) for item in updated_rows}
    sessions = [sessions_by_id[item] for item in session_ids]
    session = sessions[0]
    return {
        **row,
        "session_ids": session_ids,
        "software_package_ids": software_package_ids,
        "software_profile_ids": software_profile_ids,
        "software_variant_ids": software_variant_ids,
        "resolved_software_plan": resolved_software_plan,
        "install_preset_id": install_preset_id,
        "task_sequence_plan": task_sequence_plan,
        "session": session,
        "sessions": sessions,
    }


def list_jobs() -> list[dict]:
    conn = connect_db()
    rows = [job_payload(dict(row)) for row in conn.execute("SELECT * FROM jobs ORDER BY created_at DESC")]
    conn.close()
    return rows


def get_job(job_id: str) -> dict | None:
    conn = connect_db()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return job_payload(dict(row))


def job_payload(row: dict) -> dict:
    row["package"] = job_package_summary(row)
    return row


def job_output_path(job: dict) -> Path:
    output_dir = job.get("output_dir", "")
    root = BUILDS_DIR.resolve()
    resolved = (DATA_DIR / output_dir).resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError("任务目录越界")
    return resolved


def job_package_summary(job: dict) -> dict:
    try:
        output_path = job_output_path(job)
    except ValueError:
        return {"status": "blocked", "reason": "任务目录越界"}
    package_root = output_path / "package"
    summary = {
        "status": "missing",
        "root": safe_relative(package_root, DATA_DIR) if package_root.exists() else "",
        "manifest_path": "",
        "source": None,
        "required_outputs": [],
        "safety": {},
        "tools": [],
        "tool_status": [],
        "readme_files": [],
        "prepare_script": "",
    }
    if not package_root.is_dir() or package_root.is_symlink():
        return summary
    readmes = []
    for readme in sorted(package_root.rglob("README*")):
        if readme.is_file() and not readme.is_symlink():
            readmes.append(safe_relative(readme, DATA_DIR))
    summary["readme_files"] = readmes[:20]
    for script in sorted(package_root.rglob("prepare.sh")):
        if script.is_file() and not script.is_symlink():
            summary["prepare_script"] = safe_relative(script, DATA_DIR)
            break
    for manifest in sorted(package_root.rglob("manifest.json")):
        if not manifest.is_file() or manifest.is_symlink():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary["status"] = "invalid_manifest"
            summary["manifest_path"] = safe_relative(manifest, DATA_DIR)
            return summary
        summary.update(
            {
                "status": "ready",
                "manifest_path": safe_relative(manifest, DATA_DIR),
                "source": data.get("source"),
                "required_outputs": data.get("required_outputs") or [],
                "safety": data.get("safety") or {},
                "tools": data.get("tools") or [],
                "tool_status": data.get("tool_status") or [],
            }
        )
        return summary
    summary["status"] = "ready_without_manifest"
    return summary


def append_job_event(job_id: str, event: str, payload: dict | None = None) -> None:
    job = get_job(job_id)
    if job is None:
        return
    try:
        log_path = job_output_path(job) / "logs" / "events.jsonl"
    except ValueError:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    item = {"event": event, "job_id": job_id, "created_at": int(time.time())}
    if payload:
        item.update(payload)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(item, ensure_ascii=False) + "\n")


def list_job_events(job_id: str) -> list[dict] | None:
    job = get_job(job_id)
    if job is None:
        return None
    try:
        log_path = job_output_path(job) / "logs" / "events.jsonl"
    except ValueError:
        return None
    if not log_path.is_file():
        return []
    events: list[dict] = []
    with log_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                item = {"event": "invalid_log_line", "raw": line[:500]}
            events.append(item)
    return events[-200:]


def update_job_status(job_id: str, target_status: str) -> dict | None:
    allowed_transitions = {
        "pending": {"draft"},
        "canceled": {"draft", "pending"},
    }
    if target_status not in allowed_transitions:
        return None
    conn = connect_db()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        conn.close()
        return None
    if row["status"] not in allowed_transitions[target_status]:
        conn.close()
        return dict(row) | {"transition_error": f"{row['status']} -> {target_status}"}
    try:
        status_path = job_output_path(dict(row)) / "status.json"
    except ValueError:
        conn.close()
        return None
    now = int(time.time())
    conn.execute(
        "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
        (target_status, now, job_id),
    )
    conn.commit()
    conn.close()
    status_path.write_text(json.dumps({"status": target_status, "updated_at": now}, ensure_ascii=False, indent=2), encoding="utf-8")
    append_job_event(job_id, "status_changed", {"from": row["status"], "to": target_status})
    return get_job(job_id)


def normalize_job_kind(kind: object) -> str:
    return {
        "ubuntu-autoinstall": "ubuntu-autoinstall-template",
        "ubuntu-autoinstall-template": "ubuntu-autoinstall-template",
        "ubuntu-xorriso-iso": "ubuntu-xorriso-iso",
        "windows-adk-package": "windows-adk-package",
        "hotpe-iso-prepare": "hotpe-iso-prepare",
        "ubuntu-iso-extract-kernel-initrd": "ubuntu-iso-extract-kernel-initrd",
    }.get(kind, "ubuntu-autoinstall-template")


def job_source_payload(payload: dict, kind: str) -> dict | None:
    if kind not in {"hotpe-iso-prepare", "ubuntu-iso-extract-kernel-initrd"}:
        return None
    source_image_id = safe_text(payload.get("source_image_id"), 80)
    if not source_image_id:
        raise ValueError("source_image_id_required")
    image = get_image(source_image_id)
    if image is None:
        raise ValueError("source_image_not_found")
    if image.get("scan_status") != "present":
        raise ValueError("source_image_not_present")
    if image.get("preparation_status") != "needs_extraction":
        raise ValueError("source_image_not_needing_extraction")
    if kind == "hotpe-iso-prepare" and not (
        image.get("category") == "pe"
        and image.get("kind") == "iso"
        and str(image.get("relative_path", "")).startswith("pe/hotpe/")
    ):
        raise ValueError("hotpe_iso_required")
    if kind == "ubuntu-iso-extract-kernel-initrd" and not (
        image.get("category") == "linux"
        and image.get("kind") == "iso"
    ):
        raise ValueError("linux_iso_required")
    rel_path = str(image["relative_path"])
    target_dir = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
    return {
        "image_id": image["id"],
        "name": image.get("display_name") or image.get("name"),
        "relative_path": rel_path,
        "target_dir": target_dir,
        "sha256": image.get("sha256", ""),
        "size_bytes": image.get("size_bytes", 0),
    }


def create_job(payload: dict) -> dict:
    kind = normalize_job_kind(payload.get("kind") if isinstance(payload, dict) else None)
    source = job_source_payload(payload, kind)
    now = int(time.time())
    job_id = uuid.uuid4().hex[:12]
    title = safe_title(payload.get("title"), f"{kind}-{job_id}")
    output_dir = BUILDS_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "logs").mkdir(parents=True, exist_ok=True)
    (output_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (output_dir / "work").mkdir(parents=True, exist_ok=True)
    (output_dir / "output" / "artifacts").mkdir(parents=True, exist_ok=True)
    (output_dir / "package").mkdir(parents=True, exist_ok=True)

    # 任务框架只生成安全的配置模板，不执行磁盘或系统修改。
    if kind == "ubuntu-autoinstall-template":
        package_dir = output_dir / "package" / "ubuntu"
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "user-data").write_text(ubuntu_user_data(title), encoding="utf-8")
        (package_dir / "meta-data").write_text(f"instance-id: {job_id}\nlocal-hostname: synaboot-client\n", encoding="utf-8")
        (package_dir / "README.md").write_text("请人工审查 user-data，确认密码 hash 与安装策略后再使用。\n", encoding="utf-8")
        note = "已生成 Ubuntu autoinstall 模板；请人工审查后再用于安装介质。"
    elif kind == "ubuntu-xorriso-iso":
        package_dir = output_dir / "package" / "ubuntu-xorriso"
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "README.md").write_text(ubuntu_xorriso_readme(job_id), encoding="utf-8")
        note = "已生成 Ubuntu xorriso ISO 任务说明；默认只处理 data/images 内的 ISO。"
    elif kind == "hotpe-iso-prepare":
        package_dir = output_dir / "package" / "hotpe-iso-prepare"
        package_dir.mkdir(parents=True, exist_ok=True)
        write_prepare_package(package_dir, job_id, kind, source)
        note = "已生成 HotPE ISO 准备任务；原始 ISO 只读，输出目标为 data/images/pe/hotpe。"
    elif kind == "ubuntu-iso-extract-kernel-initrd":
        package_dir = output_dir / "package" / "ubuntu-iso-extract"
        package_dir.mkdir(parents=True, exist_ok=True)
        write_prepare_package(package_dir, job_id, kind, source)
        note = "已生成 Ubuntu/Linux ISO kernel/initrd 提取任务；原始 ISO 只读。"
    else:
        package_dir = output_dir / "package" / "windows-adk"
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "README-WINDOWS-ADK.txt").write_text(windows_adk_readme(job_id), encoding="utf-8")
        note = "已生成 Windows ADK/DISM 外部构建包说明；需在 Windows 构建机执行。"

    row = {
        "id": job_id,
        "kind": kind,
        "status": "draft",
        "title": title,
        "output_dir": output_dir.relative_to(DATA_DIR).as_posix(),
        "created_at": now,
        "updated_at": now,
        "note": note,
    }
    job_record = row | ({"source": source} if source else {})
    (output_dir / "job.json").write_text(json.dumps(job_record, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "status.json").write_text(json.dumps({"status": "draft", "updated_at": now}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "logs" / "events.jsonl").write_text(json.dumps({"event": "created", "job_id": job_id, "created_at": now}, ensure_ascii=False) + "\n", encoding="utf-8")
    conn = connect_db()
    conn.execute(
        """
        INSERT INTO jobs (id, kind, status, title, output_dir, created_at, updated_at, note)
        VALUES (:id, :kind, :status, :title, :output_dir, :created_at, :updated_at, :note)
        """,
        row,
    )
    conn.commit()
    conn.close()
    return row


def write_prepare_package(package_dir: Path, job_id: str, kind: str, source: dict | None) -> None:
    if source is None:
        raise ValueError("source_required")
    if kind == "hotpe-iso-prepare":
        required_outputs = hotpe_required_artifacts()
        readme = hotpe_prepare_readme(job_id, source)
        script = hotpe_prepare_script(job_id, source)
    else:
        required_outputs = linux_required_artifacts(source["relative_path"])
        readme = ubuntu_extract_readme(job_id, source)
        script = ubuntu_extract_script(job_id, source)
    tools = (
        ["prepare-linux-boot-artifacts.sh", "extract-iso9660-file.py"]
        if kind == "ubuntu-iso-extract-kernel-initrd"
        else ["prepare-hotpe-boot-artifacts.sh", "extract-iso9660-file.py", "extract-udf-file.py"]
    )
    manifest = {
        "job_id": job_id,
        "kind": kind,
        "source": source,
        "required_outputs": required_outputs,
        "safety": {
            "source_iso_readonly": True,
            "overwrite_existing_outputs": False,
            "writes_outside_project_data": False,
            "installs_dependencies": False,
            "destructive_disk_operations": False,
        },
        "tools": tools,
        "tool_status": iso_extract_tool_status(),
    }
    (package_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (package_dir / "README.md").write_text(readme, encoding="utf-8")
    script_path = package_dir / "prepare.sh"
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o755)


def iso_extract_tool_status() -> list[dict]:
    return [
        {
            "name": "extract-iso9660-file.py",
            "available": (DATA_DIR.parent / "scripts" / "image-factory" / "extract-iso9660-file.py").is_file()
            or Path("scripts/image-factory/extract-iso9660-file.py").is_file(),
            "purpose": "读取 ISO9660 内容，并按项目白名单、路径边界和大小上限提取启动依赖",
        },
        {
            "name": "bsdtar",
            "available": shutil.which("bsdtar") is not None,
            "purpose": "HotPE 准备任务的可选 ISO 解包工具；Ubuntu/Linux livefs 准备不再使用",
        },
        {
            "name": "7z",
            "available": shutil.which("7z") is not None,
            "purpose": "HotPE 准备任务的可选 ISO 解包工具；Ubuntu/Linux livefs 准备不再使用",
        },
    ]


def shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def prepare_script_common(job_id: str, source: dict, extra: str) -> str:
    source_rel = shell_single_quote(source["relative_path"])
    target_rel = shell_single_quote(source["target_dir"])
    return f"""#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${{SYNABOOT_ROOT_DIR:-$(cd "$(dirname "${{BASH_SOURCE[0]}}")/../../../.." && pwd)}}"
SOURCE_REL={source_rel}
TARGET_REL={target_rel}
SOURCE="$ROOT_DIR/data/images/$SOURCE_REL"
TARGET="$ROOT_DIR/data/images/$TARGET_REL"
WORK="$ROOT_DIR/data/builds/{job_id}/work/extract"

fail() {{
  printf 'BLOCKED: %s\\n' "$1" >&2
  exit 1
}}

[[ -f "$SOURCE" ]] || fail "源 ISO 不存在: $SOURCE_REL"
[[ -d "$TARGET" ]] || fail "目标目录不存在: $TARGET_REL"
mkdir -p "$WORK"

canonical_child_path() {{
  python3 - "$1" "$2" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
child = Path(sys.argv[2])
resolved_parent = child.parent.resolve()
candidate = resolved_parent / child.name
if root != resolved_parent and root not in resolved_parent.parents:
    raise SystemExit(1)
print(candidate)
PY
}}

canonical_dir_path() {{
  python3 - "$1" "$2" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
directory = Path(sys.argv[2]).resolve()
if root != directory and root not in directory.parents:
    raise SystemExit(1)
print(directory)
PY
}}

{extra}
"""


def ubuntu_extract_script(job_id: str, source: dict) -> str:
    return prepare_script_common(
        job_id,
        source,
"""[[ ! -L "$TARGET" ]] || fail "目标目录是 symlink，拒绝写入"
TARGET_CANONICAL="$(canonical_dir_path "$ROOT_DIR/data/images" "$TARGET")" || fail "目标目录越界"
CASPER_DIR="$TARGET_CANONICAL/casper"
[[ ! -L "$CASPER_DIR" ]] || fail "目标 casper 目录是 symlink，拒绝写入"

bash "$ROOT_DIR/scripts/image-factory/prepare-linux-boot-artifacts.sh"

for artifact in "$CASPER_DIR/vmlinuz" "$CASPER_DIR/initrd"; do
  [[ -f "$artifact" ]] || fail "准备后仍缺少 Ubuntu 启动文件: ${artifact#$ROOT_DIR/}"
  [[ ! -L "$artifact" ]] || fail "准备结果是 symlink，拒绝使用: ${artifact#$ROOT_DIR/}"
done
compgen -G "$CASPER_DIR/*.squashfs" >/dev/null || fail "准备后仍缺少 Ubuntu livefs: ${CASPER_DIR#$ROOT_DIR/}/*.squashfs"

printf 'APPROVED: 已准备 casper/vmlinuz、casper/initrd 和 casper/*.squashfs\\n'
""",
    )


def hotpe_prepare_script(job_id: str, source: dict) -> str:
    return prepare_script_common(
        job_id,
        source,
        """[[ "$TARGET_REL" == "pe/hotpe" ]] || fail "HotPE 准备任务只允许写入 data/images/pe/hotpe"

bash "$ROOT_DIR/scripts/image-factory/prepare-hotpe-boot-artifacts.sh" "$SOURCE_REL"
""",
    )


def ubuntu_extract_readme(job_id: str, source: dict) -> str:
    return f"""# Ubuntu/Linux ISO livefs 准备任务

任务 ID: {job_id}

源 ISO:

```text
data/images/{source['relative_path']}
```

目标输出:

```text
data/images/{source['target_dir']}/casper/vmlinuz
data/images/{source['target_dir']}/casper/initrd
data/images/{source['target_dir']}/casper/*.squashfs
```

安全边界:

- 原始 ISO 只读，不删除、不改写。
- 如果目标文件已存在，`prepare.sh` 会校验为普通文件并保留，不会覆盖。
- Ubuntu/Linux livefs 准备强制使用项目内 ISO9660 提取器，按白名单和大小上限提取。
- 不执行分区、格式化、写真实块设备、mount 宿主敏感目录等操作。

执行前请人工审查 `manifest.json` 和 `prepare.sh`。
"""


def hotpe_prepare_readme(job_id: str, source: dict) -> str:
    return f"""# HotPE ISO 准备任务

任务 ID: {job_id}

源 ISO:

```text
data/images/{source['relative_path']}
```

目标输出:

```text
data/images/pe/hotpe/wimboot
data/images/pe/hotpe/bootmgr
data/images/pe/hotpe/BCD
data/images/pe/hotpe/boot.sdi
data/images/pe/hotpe/boot.wim
```

当前阶段说明:

- `prepare.sh` 会调用项目内 HotPE 准备脚本，只从固定候选路径提取
  `bootmgr`、`BCD`、`boot.sdi`、`boot.wim`。
- 当前已支持 HotPE UDF 布局：`bootmgr`、`Boot/bcd`、
  `Boot/boot.sdi`、`HotPE/Boot.wim`。
- 如果 ISO 使用其它隐藏启动镜像布局或文件不在候选路径内，脚本会 fail-fast，
  需要管理员人工确认 ISO 内部布局。
- `wimboot` 通常来自 iPXE/wimboot 工具文件，不一定包含在 HotPE ISO 中，需要管理员提供已审查来源。

安全边界:

- 原始 ISO 只读，不删除、不改写。
- 目标文件已存在时必须拒绝覆盖。
- 不自动下载或安装解包工具。
- 不执行分区、格式化、写真实块设备、mount 宿主敏感目录等操作。
"""


def ubuntu_user_data(title: str) -> str:
    _ = title
    return """#cloud-config
autoinstall:
  version: 1
  identity:
    hostname: synaboot-client
    username: synaboot
    password: "$6$REPLACE_WITH_HASHED_PASSWORD"
  locale: zh_CN.UTF-8
  keyboard:
    layout: us
  # Phase 2 默认不生成 storage 自动分区配置。
  # 如需自动分区，必须由管理员二次确认后手动添加。
  packages: []
  late-commands:
    - curtin in-target --target=/target -- echo "Provisioned by SynaBoot"
"""


def autoinstall_template(os_family: str) -> tuple[str, str, list[str]]:
    if os_family == "windows":
        return (
            "windows-autounattend",
            """<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
  <!-- SynaBoot 免费版只生成安全草稿；分区、密钥、账号和密码必须由管理员人工补齐。 -->
  <settings pass="windowsPE">
    <component name="Microsoft-Windows-Setup" processorArchitecture="{{ARCH}}" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <UserData>
        <AcceptEula>true</AcceptEula>
      </UserData>
    </component>
  </settings>
</unattend>
""",
            ["ARCH"],
        )
    return (
        "ubuntu-cloud-init",
        """#cloud-config
autoinstall:
  version: 1
  identity:
    hostname: "{{HOSTNAME}}"
    username: "{{USERNAME}}"
    password: "$6$REPLACE_WITH_HASHED_PASSWORD"
  locale: zh_CN.UTF-8
  keyboard:
    layout: us
  # 免费版默认不生成 storage 自动分区配置，避免误清盘。
  packages: []
""",
        ["HOSTNAME", "USERNAME"],
    )


def normalize_autoinstall_family(value: object) -> str:
    family = safe_text(value, 32).lower()
    if family in {"windows", "win11", "winserver"}:
        return "windows"
    return "ubuntu"


def list_autoinstall_profiles() -> list[dict]:
    conn = connect_db()
    rows = [dict(row) for row in conn.execute("SELECT * FROM autoinstall_profiles ORDER BY created_at DESC")]
    conn.close()
    return [autoinstall_profile_payload(row) for row in rows]


def autoinstall_binding_plan() -> dict:
    images = [
        image
        for image in list_images()
        if image.get("scan_status") == "present"
        and image.get("kind") == "iso"
        and image.get("category") in {"linux", "windows"}
    ]
    profiles = list_autoinstall_profiles()
    profiles_by_family = {
        "ubuntu": [profile for profile in profiles if profile.get("os_family") == "ubuntu"],
        "windows": [profile for profile in profiles if profile.get("os_family") == "windows"],
    }
    candidates = []
    for image in images:
        os_family = "windows" if image.get("category") == "windows" else "ubuntu"
        compatible_profiles = [
            {
                "profile_id": profile.get("id", ""),
                "profile_name": profile.get("name", ""),
                "template_kind": profile.get("template_kind", ""),
                "status": profile.get("status", ""),
                "variables": profile.get("variables", []),
                "planning_state": "preview_only",
                "write_enabled": False,
            }
            for profile in profiles_by_family.get(os_family, [])
        ]
        candidates.append(
            {
                "image_id": image.get("id", ""),
                "image_name": image.get("display_name") or image.get("name") or "",
                "relative_path": image.get("relative_path") or image.get("rel_path") or "",
                "os_family": os_family,
                "compatible_profile_count": len(compatible_profiles),
                "compatible_profiles": compatible_profiles,
                "readiness": image.get("boot_readiness", ""),
                "preparation_status": image.get("preparation_status", ""),
                "planning_state": "preview_only",
                "status": "planning_only_disabled",
                "disabled_reason_code": "requires_future_commercial_binding_feature",
                "disabled_reason_text": "真实 ISO/profile 绑定、默认脚本和菜单接入属于后续 Professional 候选能力。",
                "required_edition": "professional_candidate",
                "menu_integration_available": False,
                "write_enabled": False,
                "next_action": "当前免费版仅展示绑定规划；不会写入绑定关系，也不会接入启动菜单。",
            }
        )
    return {
        "schema_version": "synaboot.autoinstall-binding-plan.v1",
        "status": "planning_only_disabled",
        "edition": "free",
        "runtime_binding_enabled": False,
        "menu_integration_enabled": False,
        "policy_matching_enabled": False,
        "write_api_available": False,
        "reason": "Phase 2.12 只管理自动安装草稿。ISO 绑定、默认策略、超时和按主机匹配属于后续 Professional/Enterprise 候选能力。",
        "free_scope": [
            "展示可绑定的 ISO 候选",
            "展示兼容草稿数量",
            "提示后续人工审查步骤",
            "不执行无人值守安装",
        ],
        "commercial_candidate_scope": [
            "一个 ISO 绑定多个自动安装方案",
            "默认脚本与菜单超时",
            "按 MAC、机型或标签匹配策略",
            "绑定审计与批量报表",
        ],
        "safety_guards": [
            "不写入 image_autoinstall_bindings 表",
            "不修改 iPXE 菜单",
            "不生成磁盘分区或清盘配置",
            "不启用 DHCP、ProxyDHCP 或 TFTP",
            "不需要 license 或在线激活即可使用免费核心功能",
        ],
        "profiles_total": len(profiles),
        "candidate_images_total": len(candidates),
        "candidates": candidates,
    }


def autoinstall_profile_payload(row: dict) -> dict:
    try:
        variables = json.loads(row.get("variables") or "[]")
    except json.JSONDecodeError:
        variables = []
    row["variables"] = variables
    row.pop("image_id", None)
    row["capability"] = {
        "edition": row.get("edition_tier", "free"),
        "free_core": True,
        "runtime_execution_enabled": False,
        "binding_model": "future_image_autoinstall_bindings",
    }
    return row


def autoinstall_profile_columns(conn: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in conn.execute("PRAGMA table_info(autoinstall_profiles)")}


def capabilities_status() -> dict:
    capabilities = dict(DEFAULT_FREE_CAPABILITIES)
    source = "embedded_default"
    if CAPABILITIES_PATH.is_file() and not CAPABILITIES_PATH.is_symlink():
        try:
            loaded = json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                capabilities = loaded
                source = "config_file"
        except (OSError, json.JSONDecodeError):
            source = "embedded_default_invalid_config"
    capabilities["edition"] = "free"
    capabilities["release_channel"] = "free"
    capabilities["github_public_release"] = True
    capabilities["commercial_code_included"] = False
    capabilities["online_activation_required"] = False
    capabilities["source"] = source
    capabilities["config_path"] = "config/synaboot/capabilities.free.json"
    capabilities["runtime_enforcement"] = "display_only_no_license_gate"
    capabilities["owner_local_full_feature_note"] = "本机 owner/developer 私有全功能能力不得进入 GitHub 免费发布线。"
    capabilities["edition_catalog"] = edition_catalog_status()
    return capabilities


def edition_catalog_status() -> dict:
    catalog = dict(DEFAULT_EDITION_CATALOG)
    source = "embedded_default"
    if EDITION_CATALOG_PATH.is_file() and not EDITION_CATALOG_PATH.is_symlink():
        try:
            loaded = json.loads(EDITION_CATALOG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                catalog = loaded
                source = "config_file"
        except (OSError, json.JSONDecodeError):
            source = "embedded_default_invalid_config"
    catalog["catalog_purpose"] = "public_display_only_no_license_gate"
    catalog["commercial_code_included"] = False
    catalog["online_activation_required"] = False
    catalog["source"] = source
    catalog["config_path"] = "config/synaboot/editions.public.json"
    return catalog


def create_autoinstall_profile(payload: dict) -> dict:
    os_family = normalize_autoinstall_family(payload.get("os_family") if isinstance(payload, dict) else None)
    template_kind, template_preview, variables = autoinstall_template(os_family)
    now = int(time.time())
    profile_id = uuid.uuid4().hex[:12]
    fallback_name = f"{os_family}-{profile_id}"
    name = safe_title(payload.get("name") if isinstance(payload, dict) else None, fallback_name)
    row = {
        "id": profile_id,
        "name": name,
        "os_family": os_family,
        "template_kind": template_kind,
        "edition_tier": "free",
        "status": "draft_review_required",
        "destructive_policy": "manual_review_required_no_storage_autopartition",
        "variables": json.dumps(variables, ensure_ascii=False),
        "template_preview": template_preview,
        "created_at": now,
        "updated_at": now,
        "note": "免费版只创建自动安装模板草稿；默认不绑定清盘分区策略，也不自动执行安装。",
    }
    conn = connect_db()
    columns = autoinstall_profile_columns(conn)
    insert_row = dict(row)
    if "image_id" in columns:
        # 兼容 Phase 2.12 早期本地草案库；新模型不再使用 profile 直连 ISO。
        insert_row["image_id"] = ""
    insert_columns = [column for column in insert_row if column in columns]
    placeholders = ", ".join(f":{column}" for column in insert_columns)
    conn.execute(
        f"""
        INSERT INTO autoinstall_profiles ({", ".join(insert_columns)})
        VALUES ({placeholders})
        """,
        insert_row,
    )
    conn.commit()
    conn.close()
    return autoinstall_profile_payload(row)


def safe_title(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    normalized = SAFE_TITLE_RE.sub("-", value.strip())[:80].strip(" .-_")
    return normalized or fallback


def safe_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", value).strip()
    return normalized[:limit]


def token_matches(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def windows_adk_readme(job_id: str) -> str:
    return f"""SynaBoot Windows ADK/DISM 外部构建任务包

任务 ID: {job_id}

一期只生成任务包说明，不在 Ubuntu 服务器上执行 Windows 镜像封装。
请在已安装 Windows ADK 的 Windows 构建机上执行 DISM、oscdimg 等步骤。

安全边界:
- 不从 SynaBoot 服务器自动格式化客户机磁盘。
- 不在 Linux 上宣称完整封装 Windows ISO。
- 输出 ISO/WIM 后再人工放回 data/images/windows/ 对应目录。
"""


def ubuntu_xorriso_readme(job_id: str) -> str:
    return f"""SynaBoot Ubuntu xorriso ISO 任务说明

任务 ID: {job_id}

二期仅提供安全的任务目录与说明模板。
执行前必须确认输入 ISO 位于 data/images 内，输出写入 data/builds/<job-id>/output/artifacts。

安全边界:
- 不写入真实块设备。
- 不执行自动分区或格式化。
- 不挂载宿主系统目录。
- autoinstall 默认不生成 storage 自动分区配置。
"""


def network_safety_status() -> dict:
    boot_metadata_proxy = phase3_3a_boot_metadata_proxy_feasibility()
    return {
        "status": "APPROVED_SCOPE",
        "server_ip": SERVER_IP,
        "http_port": SYNABOOT_PORT,
        "admin_configured": bool(ADMIN_TOKEN),
        "web_url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/",
        "menu_url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/menu.ipxe",
        "images_url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/",
        "allowed": ["HTTP 18080/tcp", "Docker bridge network", "static /images", "static /boot", "API reverse proxy"],
        "forbidden": ["DHCP", "ProxyDHCP", "TFTP", "Samba by default", "host network", "privileged containers", "UDP 67/68/69/4011"],
        "phase3_gate": {
            "model_phase": "3.1",
            "display_phase": "3.4",
            "status": "router_option_path_not_recommended_but_blocked",
            "allowed_next_step": "controlled_boot_metadata_proxy_feasibility_evaluation_only",
            "implementation_allowed": False,
            "service_enablement_allowed": False,
            "production_lan_testing_allowed": False,
            "boot_metadata_proxy": {
                "product_name": boot_metadata_proxy["product_name"],
                "status": boot_metadata_proxy["status"],
                "read_only": boot_metadata_proxy["read_only"],
                "runtime_enabled": boot_metadata_proxy["runtime_enabled"],
                "implementation_allowed": boot_metadata_proxy["implementation_allowed"],
                "production_lan_allowed": boot_metadata_proxy["production_lan_allowed"],
                "product_promise": boot_metadata_proxy["product_promise"],
            },
        },
    }


def deployment_path_status(label: str, path: Path) -> dict:
    return {
        "label": label,
        "path": str(path.relative_to(DATA_DIR.parent)) if path.is_relative_to(DATA_DIR.parent) else str(path),
        "exists": path.exists(),
        "is_dir": path.is_dir(),
        "writable_expected": label in {"images", "boot", "metadata", "builds", "logs"},
    }


def deployment_status() -> dict:
    paths = [
        deployment_path_status("data", DATA_DIR),
        deployment_path_status("images", IMAGES_DIR),
        deployment_path_status("boot", BOOT_DIR),
        deployment_path_status("metadata", METADATA_DIR),
        deployment_path_status("builds", BUILDS_DIR),
        deployment_path_status("logs", LOGS_DIR),
    ]
    config_files = [
        {
            "label": "capabilities.free.json",
            "path": "config/synaboot/capabilities.free.json",
            "exists": CAPABILITIES_PATH.is_file() and not CAPABILITIES_PATH.is_symlink(),
        },
        {
            "label": "editions.public.json",
            "path": "config/synaboot/editions.public.json",
            "exists": EDITION_CATALOG_PATH.is_file() and not EDITION_CATALOG_PATH.is_symlink(),
        },
    ]
    required_paths_ready = all(item["exists"] and item["is_dir"] for item in paths)
    admin_ready = bool(ADMIN_TOKEN)
    return {
        "status": "ready" if required_paths_ready and admin_ready else "needs_attention",
        "readiness_scope": "目录与进程内配置前置条件，不代表服务已启动或网络启动已接入。",
        "server_ip": SERVER_IP,
        "http_port": SYNABOOT_PORT,
        "web_url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/",
        "menu_url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/menu.ipxe",
        "images_url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/",
        "admin_configured": admin_ready,
        "env_file_present": (Path.cwd() / ".env").is_file(),
        "env_contents_exposed": False,
        "paths": paths,
        "config_files": config_files,
        "config_files_required_for_start": False,
        "runtime_checks": [
            "只读部署状态，不运行 docker、ip、route、iptables、nftables 或防火墙命令。",
            "不读取 .env 内容，不返回 SYNABOOT_ADMIN_TOKEN。",
            "不启用 DHCP、ProxyDHCP、TFTP、Samba、host network 或 privileged。",
        ],
        "next_actions": [
            "若路径缺失，运行 bash init-directories.sh 或安全 bootstrap。",
            "若 admin token 未配置，在 .env 中设置 SYNABOOT_ADMIN_TOKEN 后重启服务。",
            "发布或提交前运行 bash scripts/preflight/collect-release-evidence.sh。",
        ],
    }


def loader_status(item: dict) -> dict:
    filename = item["filename"]
    loader_root = BOOT_DIR / "loaders"
    metadata_root = BOOT_DIR / "loader-metadata"
    rel_path = f"loaders/{filename}"
    path = loader_root / filename
    metadata_path = metadata_root / f"{filename}.json"
    parent_symlink = BOOT_DIR.is_symlink() or loader_root.is_symlink()
    metadata_parent_symlink = BOOT_DIR.is_symlink() or metadata_root.is_symlink()
    is_symlink = path.is_symlink()
    present = (path.exists() or is_symlink) and not parent_symlink
    is_regular_file = present and path.is_file() and not is_symlink
    usable = present and is_regular_file and not is_symlink and not parent_symlink
    stat = path.stat() if usable else None
    mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else ""
    sha256 = sha256_file(path) if usable else ""
    provenance: dict = {}
    provenance_status = "missing"
    metadata_symlink = metadata_path.is_symlink()
    metadata_present = metadata_path.exists() or metadata_symlink
    metadata_regular_file = False
    if metadata_present and metadata_parent_symlink:
        provenance_status = "blocked_parent_symlink"
    elif metadata_symlink:
        provenance_status = "blocked_symlink"
    elif metadata_path.exists():
        metadata_regular_file = metadata_path.is_file()
        if not metadata_regular_file:
            provenance_status = "not_regular_file"
        else:
            try:
                provenance = json.loads(metadata_path.read_text(encoding="utf-8"))
                provenance_status = "recorded"
            except (OSError, json.JSONDecodeError):
                provenance = {}
                provenance_status = "invalid"
    provenance_sha256_matches = bool(sha256 and provenance.get("sha256") == sha256)
    review_status = provenance.get("review_status", "")
    provenance_required_fields_valid = bool(
        provenance.get("schema_version") == "synaboot.loader-provenance.v1"
        and provenance.get("filename") == filename
        and provenance.get("relative_path") == f"data/boot/loaders/{filename}"
        and provenance.get("metadata_path") == f"data/boot/loader-metadata/{filename}.json"
        and provenance.get("filename_allowlist_matched") is True
        and provenance.get("target_regular_file") is True
        and provenance.get("target_inside_loader_root") is True
        and provenance.get("network_services_enabled") is False
        and provenance.get("tftp_enabled") is False
        and provenance.get("proxydhcp_enabled") is False
        and provenance.get("dhcp_enabled") is False
    )
    reviewed_for_lab = bool(
        usable
        and provenance_status == "recorded"
        and provenance_required_fields_valid
        and provenance_sha256_matches
        and review_status == "local_admin_approved_pending_isolated_boot_test"
    )
    status = (
        "usable"
        if usable
        else ("blocked_parent_symlink" if parent_symlink else ("blocked_symlink" if is_symlink else ("not_regular_file" if present else "missing")))
    )
    warnings = [] if usable else [status]
    if usable and not reviewed_for_lab:
        warnings.append("provenance_required_for_pxe_lab_review")
    return {
        "id": item["id"],
        "filename": filename,
        "allowed": True,
        "purpose": item["purpose"],
        "architecture": item["architecture"],
        "boot_mode": item["boot_mode"],
        "transport": item["transport"],
        "present": present,
        "is_symlink": is_symlink,
        "parent_symlink": parent_symlink,
        "is_regular_file": is_regular_file,
        "usable": usable,
        "reviewed_for_lab": reviewed_for_lab,
        "review_status": review_status,
        "size_bytes": stat.st_size if stat else 0,
        "mtime_ns": stat.st_mtime_ns if stat else 0,
        "mtime": mtime,
        "sha256": sha256,
        "url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/{rel_path}",
        "path": f"data/boot/{rel_path}",
        "status": status,
        "provenance": {
            "status": provenance_status,
            "present": metadata_present and not metadata_parent_symlink,
            "is_symlink": metadata_symlink,
            "parent_symlink": metadata_parent_symlink,
            "is_regular_file": metadata_regular_file,
            "path": f"data/boot/loader-metadata/{filename}.json",
            "schema_version": provenance.get("schema_version", ""),
            "required_fields_valid": provenance_required_fields_valid,
            "source_label": provenance.get("source_label", ""),
            "source_version": provenance.get("source_version", ""),
            "source_url": provenance.get("source_url", ""),
            "reviewed_by": provenance.get("reviewed_by", ""),
            "imported_at": provenance.get("imported_at", ""),
            "sha256_matches": provenance_sha256_matches,
        },
        "source_recommendation": {
            "type": item["source_type"],
            "note": item["source_guidance"],
        },
        "secure_boot_risk": item["secure_boot_risk"],
        "warnings": warnings,
    }


def boot_assets_status() -> dict:
    loaders = [loader_status(item) for item in LOADER_CATALOG]
    return {
        "schema_version": "boot-assets.v1",
        "phase": "3.2",
        "mode": "readonly_inventory",
        "enabled": False,
        "operation_allowed": False,
        "root": "data/boot/loaders",
        "allowed_filenames": [item["filename"] for item in LOADER_CATALOG],
        "loaders": loaders,
        "guardrails": [
            "This API only inventories fixed loader filenames.",
            "It does not download, generate, replace, delete, or execute boot loaders.",
            "Local imports must use scripts/boot-assets/import-loader.py to record provenance.",
            "Symlinks are not accepted as present loader files.",
            "TFTP and ProxyDHCP remain disabled.",
        ],
    }


def pxe_ipv4_readiness(loaders: list[dict]) -> dict:
    metadata_status = "readonly_snapshot"
    metadata_error = ""
    try:
        rows = list_images_readonly_snapshot()
    except (OSError, sqlite3.Error):
        rows = []
        metadata_status = "unavailable"
        metadata_error = "metadata_unavailable"
    loader_by_name = {loader["filename"]: loader for loader in loaders}
    preferred_loaders = [loader_by_name.get("snponly.efi"), loader_by_name.get("ipxe.efi")]
    usable_loaders = [
        loader
        for loader in preferred_loaders
        if loader and loader.get("usable") and loader.get("reviewed_for_lab")
    ]
    ready_menu_rows = [
        row
        for row in rows
        if row_enabled(row)
        and row.get("scan_status") == "present"
        and row.get("boot_readiness") == "ready"
    ]
    source_iso_rows = [
        row
        for row in rows
        if row.get("scan_status") == "present"
        and row.get("kind") == "iso"
    ]
    windows_hotpe_rows = [
        row
        for row in rows
        if row_enabled(row)
        and row.get("scan_status") == "present"
        and row.get("category") == "windows"
        and row.get("boot_readiness") == "needs_hotpe"
    ]
    menu_path = BOOT_DIR / "menu.ipxe"
    menu_present = menu_path.is_file() and not menu_path.is_symlink()
    missing_prerequisites: list[str] = []
    if not menu_present:
        missing_prerequisites.append("data/boot/menu.ipxe is missing or not a regular file.")
    if not usable_loaders:
        missing_prerequisites.append("No reviewed UEFI PXE loader found; import an approved snponly.efi or ipxe.efi with scripts/boot-assets/import-loader.py.")
    if not ready_menu_rows:
        missing_prerequisites.append("No menu-enabled image currently has boot_readiness=ready; scan and prepare HotPE or Linux boot artifacts first.")
    blocking_items = [
        "Phase 3.3 network boot gate remains blocked; this summary does not authorize ProxyDHCP, TFTP, or production LAN testing.",
        *missing_prerequisites,
    ]
    if metadata_error:
        blocking_items.append("Image metadata database is unavailable in this context; run inside the deployed SynaBoot data directory or scan images first.")
    return {
        "schema_version": "pxe-ipv4-readiness.v1",
        "mode": "readonly_summary_only",
        "status": "blocked_by_phase3_gate" if blocking_items else "ready_for_isolated_lab_review",
        "target": "UEFI PXE IPv4 -> audited iPXE EFI loader -> HTTP menu.ipxe -> SynaBoot image menu",
        "operation_allowed": False,
        "service_enablement_allowed": False,
        "production_lan_testing_allowed": False,
        "production_lan_allowed": False,
        "runtime_enabled": False,
        "boot_tested": False,
        "safety_invariants": {
            "production_lan_enabled": False,
            "production_lan_allowed": False,
            "dhcp_server_enabled": False,
            "dhcp_lease_assignment_allowed": False,
            "proxydhcp_enabled": False,
            "tftp_enabled": False,
            "udp_67_open": False,
            "udp_69_open": False,
            "udp_4011_open": False,
            "docker_host_network_allowed": False,
            "docker_privileged_allowed": False,
            "host_network_mutation_allowed": False,
            "openwrt_mutation_allowed": False,
            "tplink_dhcp_replacement_allowed": False,
            "default_gateway_change_allowed": False,
            "auto_enable_boot_services_allowed": False,
        },
        "lab_prerequisites_met": menu_present and bool(usable_loaders) and bool(ready_menu_rows),
        "menu": {
            "path": "data/boot/menu.ipxe",
            "present": menu_present,
            "url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/menu.ipxe",
        },
        "preferred_loaders": [
            {
                "filename": loader["filename"],
                "status": loader["status"],
                "usable": loader["usable"],
                "reviewed_for_lab": loader.get("reviewed_for_lab", False),
                "review_status": loader.get("review_status", ""),
                "provenance": loader.get("provenance", {}),
                "path": loader["path"],
                "url": loader["url"] if loader.get("usable") and loader.get("reviewed_for_lab") else "",
                "secure_boot_risk": loader.get("secure_boot_risk", {}),
            }
            for loader in preferred_loaders
            if loader
        ],
        "image_menu": {
            "metadata_status": metadata_status,
            "metadata_error": metadata_error,
            "database_rows": len(rows),
            "source_iso_count": len(source_iso_rows),
            "ready_menu_entry_count": len(ready_menu_rows),
            "windows_hotpe_candidate_count": len(windows_hotpe_rows),
            "ready_entries": [
                {
                    "id": row["id"],
                    "name": row["display_name"],
                    "relative_path": row["relative_path"],
                    "boot_method": row["boot_method"],
                    "boot_readiness": row["boot_readiness"],
                }
                for row in ready_menu_rows[:20]
            ],
        },
        "next_actions": [
            "Scan images after placing ISO files so the metadata database reflects current data/images contents.",
            "Prepare HotPE or Linux boot artifacts until at least one menu-enabled entry has boot_readiness=ready.",
            "For Linux ISO files, run scripts/image-factory/prepare-linux-boot-artifacts.sh; it uses the built-in ISO9660 extractor with path and size limits.",
            "Import an internally approved snponly.efi or ipxe.efi with scripts/boot-assets/import-loader.py, then verify SHA256 and provenance in /api/boot-assets.",
            "Keep Phase 3.3 blocked until isolated lab review is approved by network_safety_agent, security_audit_agent, and project_decision_agent.",
        ],
        "blocking_items": blocking_items,
    }


def pxe_lab_boot_metadata_plan(loaders: list[dict]) -> dict:
    loader_by_name = {loader["filename"]: loader for loader in loaders}
    snponly = loader_by_name.get("snponly.efi", {})
    ipxe = loader_by_name.get("ipxe.efi", {})
    reviewed_candidates = [
        loader
        for loader in (snponly, ipxe)
        if loader.get("usable") and loader.get("reviewed_for_lab")
    ]
    preferred = snponly if snponly.get("usable") and snponly.get("reviewed_for_lab") else (reviewed_candidates[0] if reviewed_candidates else {})
    fallback = ipxe if preferred.get("filename") != "ipxe.efi" and ipxe.get("usable") and ipxe.get("reviewed_for_lab") else {}
    menu_url = f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/menu.ipxe"
    preferred_filename = preferred.get("filename", "")
    return {
        "schema_version": "pxe-lab-boot-metadata-plan.v1",
        "phase": "3.9",
        "mode": "readonly_plan_only",
        "status": "blocked_until_lab_service_authorized",
        "phase3_status": "blocked_by_phase3_gate",
        "operation_allowed": False,
        "service_enablement_allowed": False,
        "runtime_enabled": False,
        "production_lan_allowed": False,
        "production_lan_testing_allowed": False,
        "boot_tested": False,
        "generates_config_files": False,
        "config_generation_allowed": False,
        "command_execution_allowed": False,
        "starts_services": False,
        "writes_router_config": False,
        "safety_invariants": {
            "dhcp_server_enabled": False,
            "dhcp_lease_assignment_allowed": False,
            "proxydhcp_enabled": False,
            "tftp_enabled": False,
            "udp_67_open": False,
            "udp_69_open": False,
            "udp_4011_open": False,
            "tplink_dhcp_replacement_allowed": False,
            "openwrt_mutation_allowed": False,
            "default_gateway_change_allowed": False,
        },
        "target_chain": [
            "UEFI PXE IPv4 client obtains ordinary IP lease from the approved isolated-lab DHCP server.",
            "Future approved boot metadata points only to a reviewed iPXE EFI loader.",
            "Future approved TFTP, if any, serves only fixed loader filenames from data/boot/loaders.",
            f"iPXE chains to {menu_url}.",
            "SynaBoot HTTP menu serves prepared OS entries.",
        ],
        "candidate_boot_metadata": {
            "bootfile": preferred_filename,
            "fallback_bootfile": fallback.get("filename", ""),
            "server_hint": SERVER_IP,
            "menu_url": menu_url,
            "tftp_root": "data/boot/loaders",
            "allowed_tftp_files": [
                loader["filename"]
                for loader in loaders
                if "future-tftp" in loader.get("transport", [])
            ],
            "forbidden_tftp_files": [
                "menu.ipxe",
                "ipxe.iso",
                "README.txt",
                "*.iso",
                "*.wim",
                "*.esd",
                "*.img",
                "*.vhd",
                "*.vhdx",
                "*.json",
                "../*",
            ],
        },
        "loader_evidence": [
            {
                "filename": loader.get("filename", ""),
                "usable": loader.get("usable", False),
                "reviewed_for_lab": loader.get("reviewed_for_lab", False),
                "sha256": loader.get("sha256", ""),
                "provenance_status": loader.get("provenance", {}).get("status", ""),
                "sha256_matches": loader.get("provenance", {}).get("sha256_matches", False),
                "secure_boot_risk": loader.get("secure_boot_risk", {}),
            }
            for loader in (snponly, ipxe)
            if loader
        ],
        "proxy_dhcp_metadata_fields": [
            "PXE/UEFI client identification evidence only; do not answer ordinary DHCP clients.",
            "Client Architecture / Option 93 evidence for UEFI x86_64 must be captured before enabling any lab service.",
            "Boot server and bootfile metadata may be evaluated only in an isolated lab after approval.",
            "Do not include router, gateway, DNS, subnet mask, lease time, NAT, route, or ordinary DHCP lease fields.",
        ],
        "forbidden_dhcp_fields": [
            "router",
            "default gateway",
            "DNS server",
            "subnet mask",
            "lease time",
            "DHCP ACK",
            "DHCP NAK",
            "ordinary DHCP Server Identifier",
            "classless static route",
            "DHCP address pool",
            "DHCP lease allocation",
        ],
        "required_packet_evidence": [
            "Packet capture proves SynaBoot does not assign DHCP leases.",
            "Packet capture proves no router/gateway/DNS/subnet/lease options are sent by SynaBoot.",
            "Packet capture proves only the intended isolated UEFI PXE test client receives boot metadata.",
            "TFTP request, if later approved, is for the selected reviewed bootfile only.",
            "HTTP request reaches the SynaBoot menu URL after iPXE starts.",
        ],
        "rollback_checks": [
            "Stop the approved lab-only boot metadata service, if it is ever authorized.",
            "Verify UDP 67, 69, and 4011 are no longer listening.",
            "Verify the lab client returns to ordinary DHCP behavior.",
            "Verify production TP-Link 192.168.1.1 and OpenWrt 192.168.1.4 were not modified.",
        ],
        "blocking_items": [
            "This is a readonly plan, not executable configuration.",
            "No ProxyDHCP, TFTP, DHCP, or UDP boot service is enabled by this API state.",
            "Production LAN testing remains forbidden until a separate approval chain completes.",
            "Do not use this plan on the production LAN.",
        ],
        "next_gate": [
            "network_safety_agent approves an isolated lab boundary.",
            "security_audit_agent approves any future service implementation.",
            "project_decision_agent authorizes lab-only runtime validation.",
        ],
    }


def phase3_3a_boot_metadata_proxy_feasibility() -> dict:
    """Phase 3.3-A 只读产品边界，不代表任何运行时授权。"""
    return {
        "schema_version": "phase3.3a-boot-metadata-proxy-feasibility.v1",
        "phase": "3.3-A",
        "product_name": "Boot Metadata Proxy",
        "alternate_names": ["PXE/HTTP Boot Metadata Proxy", "ProxyDHCP metadata-only candidate", "ProxyNet-like metadata supplement"],
        "status": "documentation_only_blocked",
        "mode": "feasibility_only",
        "read_only": True,
        "implementation_allowed": False,
        "runtime_enabled": False,
        "service_enablement_allowed": False,
        "config_generation_allowed": False,
        "write_api_available": False,
        "production_lan_allowed": False,
        "production_lan_testing_allowed": False,
        "dhcp_server_allowed": False,
        "dhcp_lease_assignment_allowed": False,
        "proxy_dhcp_allowed": False,
        "tftp_allowed": False,
        "udp_67_open": False,
        "udp_69_open": False,
        "udp_4011_open": False,
        "router_mutation_allowed": False,
        "gateway_mutation_allowed": False,
        "firewall_mutation_allowed": False,
        "dns_mutation_allowed": False,
        "docker_network_mutation_allowed": False,
        "product_promise": [
            "SynaBoot 可以补齐路由器无法下发 PXE/HTTP Boot 启动元数据的缺口。",
            "SynaBoot 不得接管 DHCP、DNS、默认网关或普通网络配置。",
            "该能力只允许响应 PXEClient / HTTPClient，并只返回 bootfile、next-server 或 HTTP boot URL。",
            "必须隔离实验通过，必须一键关闭，生产 LAN 启用前必须由用户二次确认。",
        ],
        "confirmed_facts": [
            "管理员已确认当前 TP-Link TL-ER6120T 不支持下发所需 PXE/HTTP Boot 启动元数据。",
            "当前项目 HTTP 菜单仍通过 18080/tcp 提供。",
            "当前 API 状态没有启用 DHCP、ProxyDHCP、TFTP 或 UDP boot service。",
        ],
        "missing_facts": [
            "隔离实验网络边界尚未记录。",
            "PXEClient / HTTPClient 报文识别证据尚未采集。",
            "SynaBoot 不发送 lease、router、DNS、lease time 的抓包证据尚未采集。",
            "一键关闭和回滚脚本尚未进入可执行实现阶段。",
        ],
        "blocked_by": [
            "Phase 3.3-A 当前只允许文档、只读 API、只读 UI 和只读预检。",
            "尚无隔离实验验证、网络安全审查、安全审计、项目决策授权和用户生产二次确认。",
        ],
        "required_approvals": [
            "research_agent",
            "network_safety_agent",
            "security_audit_agent",
            "project_decision_agent",
            "user_manual_isolated_lab_confirmation",
            "user_production_lan_second_confirmation",
        ],
        "candidate_modes": [
            {
                "id": "proxy_dhcp_metadata_only",
                "label": "ProxyDHCP metadata-only",
                "allowed_now": False,
                "future_scope": "isolated_lab_only_after_approval",
                "assigns_ip_leases": False,
                "allowed_response_clients": ["PXEClient", "HTTPClient"],
                "allowed_metadata": ["next-server", "bootfile", "HTTP boot URL"],
            },
            {
                "id": "tftp_loader_only",
                "label": "TFTP loader-only",
                "allowed_now": False,
                "future_scope": "isolated_lab_only_after_approval",
                "root_boundary": "data/boot/loaders",
                "allowed_files": ["snponly.efi", "ipxe.efi"],
            },
            {
                "id": "http_chainload",
                "label": "HTTP chainload",
                "allowed_now": True,
                "future_scope": "current_http_reference_only",
                "menu_url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/menu.ipxe",
            },
        ],
        "explicit_non_goals": [
            "不实现 DHCP Server。",
            "不替换 TP-Link DHCP lease server。",
            "不提供网关、DNS、subnet、lease time、route 或 NAT 配置。",
            "不响应普通非 PXE/HTTP Boot 客户端。",
            "不修改 TP-Link、OpenWrt、交换机、AP、VLAN、DNS、路由或防火墙。",
        ],
        "proxy_dhcp_metadata_boundary": {
            "responds_only_to": ["PXEClient", "HTTPClient"],
            "allowed_fields": ["bootfile", "next-server", "HTTP boot URL", "PXE/EFI identification metadata"],
            "forbidden_fields": [
                "yiaddr lease",
                "router/default gateway",
                "DNS server",
                "subnet mask",
                "lease time",
                "DHCPACK for ordinary lease",
                "DHCPNAK",
                "classless static route",
            ],
        },
        "tftp_loader_scope": {
            "allowed_now": False,
            "future_root_boundary": "data/boot/loaders",
            "future_allowlist": ["snponly.efi", "ipxe.efi"],
            "forbidden": ["ISO", "WIM", "ESD", "IMG", "VHD", "VHDX", "directories", "symlinks", "path traversal"],
        },
        "packet_review_requirements": [
            "TP-Link 或隔离 DHCP server 仍负责分配普通 IP lease。",
            "SynaBoot 的 yiaddr 必须保持 0.0.0.0 或等价非租约语义。",
            "SynaBoot 不发送 router、DNS、subnet、lease time 或 route。",
            "SynaBoot 对普通 DHCP 客户端静默。",
            "SynaBoot 只对 PXEClient / HTTPClient 返回启动元数据。",
        ],
        "transition_requirements": [
            "Phase 3.3-B 只能在隔离实验网络中启动。",
            "启用任何 UDP 67/69/4011 前必须重新获得 network_safety_agent、security_audit_agent 和 project_decision_agent 审批。",
            "生产 LAN 启用前必须有隔离实验证据、一键关闭方案和用户二次确认。",
        ],
        "rollback_requirements": [
            "必须能一键关闭未来 Boot Metadata Proxy。",
            "关闭后 UDP 67、69、4011 必须无监听。",
            "关闭后客户端必须回到普通 DHCP 或手动 HTTP/iPXE 启动路径。",
            "生产 TP-Link 192.168.1.1 与 OpenWrt 192.168.1.4 不得被修改。",
        ],
        "evidence_requirements": [
            "隔离实验边界说明。",
            "PXEClient / HTTPClient 识别证据。",
            "普通客户端无响应证据。",
            "禁止 DHCP 字段未出现的抓包判读结论。",
            "HTTP menu URL 到达证据。",
            "一键关闭后的 UDP 端口关闭证据。",
        ],
        "related_documents": [
            "docs/PROXYDHCP_FEASIBILITY.md",
            "docs/PROXYDHCP_PACKET_REVIEW.md",
            "docs/TFTP_LOADER_SCOPE.md",
            "docs/PHASE3_ROLLBACK_CHECKLIST.md",
            "docs/PHASE3_REVIEW_TEMPLATES.md",
            "docs/NETWORK_SAFETY.md",
            "docs/ARCHITECTURE.md",
        ],
    }


def isolated_lab_boot_services_disabled_skeleton(loaders: list[dict]) -> dict:
    loader_by_name = {loader["filename"]: loader for loader in loaders}
    menu_url = f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/menu.ipxe"
    loader_candidates = [
        loader
        for loader in (loader_by_name.get("snponly.efi"), loader_by_name.get("ipxe.efi"))
        if loader
    ]
    return {
        "schema_version": "isolated-lab-boot-services-disabled-skeleton.v1",
        "phase": "3.10",
        "mode": "isolated_lab_boot_services_disabled_skeleton",
        "environment_scope": "isolated_lab_only",
        "status": "blocked_disabled_skeleton_only",
        "approval_status": "not_approved_for_runtime",
        "read_only": True,
        "enabled": False,
        "runtime_enabled": False,
        "service_authorization_allowed": False,
        "service_start_allowed": False,
        "config_generation_allowed": False,
        "command_execution_allowed": False,
        "compose_change_allowed": False,
        "production_lan_allowed": False,
        "production_lan_testing_allowed": False,
        "boot_tested": False,
        "target_chain_model": [
            "UEFI PXE IPv4 client in an isolated lab requests boot metadata.",
            "Future approved boot metadata points to one reviewed iPXE EFI loader.",
            "Future approved loader-only transfer, if separately authorized, uses only the fixed loader allowlist.",
            f"The loader chains to the existing HTTP menu {menu_url}.",
            "SynaBoot HTTP menu displays prepared OS entries.",
        ],
        "service_profiles": [
            {
                "id": "proxy_dhcp_metadata_only",
                "label": "ProxyDHCP metadata-only candidate",
                "service_enabled": False,
                "runtime_available": False,
                "runtime_authorization_allowed": False,
                "assigns_ip_leases": False,
                "allowed_scope": "future_isolated_lab_review_only",
                "gated_ports": ["udp/67", "udp/4011"],
            },
            {
                "id": "tftp_loader_only",
                "label": "TFTP loader-only candidate",
                "service_enabled": False,
                "runtime_available": False,
                "runtime_authorization_allowed": False,
                "allowed_scope": "future_isolated_lab_review_only",
                "root_boundary": "data/boot/loaders",
                "gated_ports": ["udp/69"],
            },
        ],
        "reference_targets": [
            {
                "id": "http_menu_target",
                "label": "HTTP menu target",
                "current_reference_only": True,
                "changes_http_topology": False,
                "url": menu_url,
            },
        ],
        "bootfile_candidates": [
            {
                "filename": loader.get("filename", ""),
                "usable": loader.get("usable", False),
                "reviewed_for_lab": loader.get("reviewed_for_lab", False),
                "sha256": loader.get("sha256", ""),
                "path": loader.get("path", ""),
                "source_label": loader.get("provenance", {}).get("source_label", ""),
                "provenance_status": loader.get("provenance", {}).get("status", ""),
                "sha256_matches": loader.get("provenance", {}).get("sha256_matches", False),
            }
            for loader in loader_candidates
        ],
        "tftp_loader_allowlist": [
            loader["filename"]
            for loader in loaders
            if "future-tftp" in loader.get("transport", [])
        ],
        "forbidden_transfer_scope": [
            "menu.ipxe",
            "ipxe.iso",
            "*.iso",
            "*.wim",
            "*.esd",
            "*.img",
            "*.vhd",
            "*.vhdx",
            "*.json",
            "../*",
            "absolute paths",
            "symlinks",
            "directories",
        ],
        "http_menu_target": {
            "url": menu_url,
            "current_reference_only": True,
            "changes_http_topology": False,
        },
        "client_evidence_template": [
            "firmware boot entry label, for example UEFI: PXE IPv4",
            "PXEClient or HTTPClient identification evidence",
            "client architecture evidence such as UEFI x86_64",
            "NIC model and firmware version",
            "observed boot behavior",
            "known failure reason if the chainload does not reach the menu",
        ],
        "failure_modes": [
            "Client receives no boot metadata in the isolated lab.",
            "Client requests a bootfile outside the reviewed allowlist.",
            "Firmware rejects the reviewed loader, possibly due to Secure Boot policy.",
            "Loader starts but cannot reach the HTTP menu URL.",
            "Any non-test client receives boot metadata.",
            "Any packet shows ordinary DHCP lease assignment by SynaBoot.",
        ],
        "rollback_plan": [
            "Keep this disabled skeleton unchanged.",
            "Do not open UDP 67, 69, or 4011.",
            "Do not modify TP-Link DHCP settings.",
            "Do not modify OpenWrt gateway, route, NAT, firewall, DNS, VLAN, switch, or AP settings.",
            "Return clients to iPXE USB/ISO or manual UEFI HTTP Boot while Phase 3 remains blocked.",
        ],
        "gates": {
            "research_review": "required_before_runtime",
            "network_safety_review": "required_before_runtime",
            "security_audit_review": "required_before_runtime",
            "project_decision": "required_before_runtime",
            "isolated_lab_confirmation": "required_before_runtime",
        },
        "safety_invariants": {
            "dhcp_server_enabled": False,
            "dhcp_lease_assignment_allowed": False,
            "proxydhcp_enabled": False,
            "tftp_enabled": False,
            "udp_67_open": False,
            "udp_69_open": False,
            "udp_4011_open": False,
            "router_config_generation_allowed": False,
            "compose_boot_service_generation_allowed": False,
            "host_network_allowed": False,
            "privileged_container_allowed": False,
            "tplink_mutation_allowed": False,
            "openwrt_mutation_allowed": False,
            "default_gateway_change_allowed": False,
        },
        "blocked_actions": [
            "Do not generate service configuration.",
            "Do not start DHCP, ProxyDHCP, or TFTP.",
            "Do not open UDP 67, 69, or 4011.",
            "Do not modify docker-compose.yml for boot services.",
            "Do not modify TP-Link or OpenWrt settings.",
            "Do not use this disabled skeleton on the production LAN.",
        ],
        "next_gate": [
            "research_agent resolves remaining router, firmware, and protocol unknowns.",
            "network_safety_agent approves a real isolated lab boundary.",
            "security_audit_agent approves any future runtime design.",
            "project_decision_agent authorizes lab-only runtime validation.",
        ],
    }


def udp_port_evidence() -> list[dict]:
    observed: set[int] = set()
    sources = []
    for source in (Path("/proc/net/udp"), Path("/proc/net/udp6")):
        if not source.is_file():
            continue
        sources.append(str(source))
        try:
            lines = source.read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) < 2 or ":" not in parts[1]:
                continue
            port_hex = parts[1].rsplit(":", 1)[1]
            try:
                observed.add(int(port_hex, 16))
            except ValueError:
                continue
    return [
        {
            "port": port,
            "protocol": "udp",
            "observed_in_api_namespace": port in observed,
            "host_level_evidence_required": "scripts/preflight/check-network-safety.sh",
            "sources": sources,
        }
        for port in (67, 69, 4011)
    ]


def isolated_lab_evidence_package(loaders: list[dict]) -> dict:
    readiness = pxe_ipv4_readiness(loaders)
    skeleton = isolated_lab_boot_services_disabled_skeleton(loaders)
    ready_entries = readiness.get("image_menu", {}).get("ready_entries", [])
    reviewed_loaders = [
        loader
        for loader in skeleton.get("bootfile_candidates", [])
        if loader.get("usable") and loader.get("reviewed_for_lab") and loader.get("sha256_matches")
    ]
    udp_evidence = udp_port_evidence()
    udp_blocked = [item for item in udp_evidence if item["observed_in_api_namespace"]]
    evidence_checks = [
        {
            "id": "http_menu_reference",
            "status": "passed" if readiness.get("menu", {}).get("present") else "blocked",
            "summary": readiness.get("menu", {}).get("url", ""),
            "next_action": "" if readiness.get("menu", {}).get("present") else "Regenerate menu.ipxe and rerun preflight.",
        },
        {
            "id": "reviewed_uefi_loader",
            "status": "passed" if reviewed_loaders else "blocked",
            "summary": ", ".join(loader["filename"] for loader in reviewed_loaders) or "No reviewed loader available.",
            "next_action": "" if reviewed_loaders else "Import and review snponly.efi or ipxe.efi before requesting lab validation.",
        },
        {
            "id": "ready_image_entries",
            "status": "passed" if ready_entries else "blocked",
            "summary": f"ready_entries={len(ready_entries)}",
            "next_action": "" if ready_entries else "Prepare at least one image entry until boot_readiness=ready.",
        },
        {
            "id": "udp_boot_ports_in_api_namespace",
            "status": "passed" if not udp_blocked else "blocked",
            "summary": "No UDP 67/69/4011 socket observed by API namespace." if not udp_blocked else "One or more gated UDP boot ports are observed.",
            "next_action": "" if not udp_blocked else "Stop and investigate before any lab request.",
        },
        {
            "id": "disabled_skeleton_gate",
            "status": "passed" if skeleton.get("enabled") is False and skeleton.get("runtime_enabled") is False else "blocked",
            "summary": "Phase 3.10 disabled skeleton remains non-runnable.",
            "next_action": "Do not proceed if any runtime or service gate is true.",
        },
    ]
    blocking_items = [
        "This evidence package is not an experiment authorization.",
        "Production LAN testing remains forbidden.",
        "Do not use this evidence package on the production LAN.",
        "DHCP, ProxyDHCP, TFTP, and UDP boot services remain disabled.",
        "Manual isolated lab facts and reviewer approvals are still required before runtime validation.",
    ]
    if any(item["status"] != "passed" for item in evidence_checks):
        blocking_items.append("One or more evidence checks are not ready for an isolated lab request.")
    return {
        "schema_version": "phase3-isolated-lab-evidence-package.v1",
        "phase": "3.11",
        "mode": "readonly_evidence_package",
        "status": "not_authorized",
        "read_only": True,
        "enabled": False,
        "secrets_included": False,
        "secret_redaction_applied": True,
        "secret_fields_allowed": False,
        "sensitive_values_exposed": False,
        "raw_commands_included": False,
        "config_generation_allowed": False,
        "command_execution_allowed": False,
        "service_start_allowed": False,
        "compose_generation_allowed": False,
        "router_config_generation_allowed": False,
        "production_lan_allowed": False,
        "production_lan_testing_allowed": False,
        "packet_capture_started": False,
        "network_probe_started": False,
        "boot_tested": False,
        "requested_scope": "single_machine_isolated_lab_uefi_pxe_ipv4",
        "authorization_request": {
            "status": "draft_not_authorized",
            "request_is_authorization": False,
            "requested_outcome": "Allow a future single-machine isolated lab validation after all reviewers approve.",
            "required_reviewers": [
                "research_agent",
                "network_safety_agent",
                "security_audit_agent",
                "project_decision_agent",
                "user_manual_confirmation",
            ],
            "approval_state": {
                "research_review": "required_before_runtime",
                "network_safety_review": "required_before_runtime",
                "security_audit_review": "required_before_runtime",
                "project_decision": "required_before_runtime",
                "user_manual_confirmation": "required_before_runtime",
            },
        },
        "evidence_checks": evidence_checks,
        "udp_port_evidence": udp_evidence,
        "boot_readiness_evidence": {
            "menu_url": readiness.get("menu", {}).get("url", ""),
            "menu_present": readiness.get("menu", {}).get("present", False),
            "reviewed_loaders": reviewed_loaders,
            "ready_image_entry_count": len(ready_entries),
            "ready_image_entries": ready_entries[:20],
            "candidate_bootfile": reviewed_loaders[0]["filename"] if reviewed_loaders else "",
            "http_menu_reference_only": True,
        },
        "production_lan_safety_statement": {
            "primary_dhcp_invariant": "192.168.1.1",
            "default_gateway_invariant": "192.168.1.4",
            "synaboot_assigns_dhcp_leases": False,
            "tplink_mutation_allowed": False,
            "openwrt_mutation_allowed": False,
            "host_network_mutation_allowed": False,
        },
        "network_service_state": {
            "dhcp_server_enabled": False,
            "dhcp_lease_assignment_allowed": False,
            "proxydhcp_enabled": False,
            "tftp_enabled": False,
            "udp_67_open": False,
            "udp_69_open": False,
            "udp_4011_open": False,
            "host_network_allowed": False,
            "privileged_container_allowed": False,
        },
        "manual_lab_declaration_required": [
            "Confirm the test client is a single intended UEFI PXE IPv4 machine.",
            "Confirm the lab switch, VLAN, or cable path cannot affect production clients.",
            "Confirm the production LAN remains out of scope for this request.",
            "Confirm the lab DHCP lease source, gateway, subnet, and SynaBoot test IP before runtime validation.",
            "Confirm rollback means stopping any future lab service and returning to USB iPXE or manual UEFI HTTP Boot.",
            "Confirm no TP-Link or OpenWrt production configuration will be changed.",
        ],
        "client_evidence_template": skeleton.get("client_evidence_template", []),
        "expected_observations": [
            "The intended lab client enters UEFI: PXE IPv4.",
            "The client requests only the reviewed bootfile candidate.",
            "The loader reaches the HTTP menu URL.",
            "The SynaBoot menu displays ready image entries.",
            "No ordinary DHCP lease is assigned by SynaBoot.",
        ],
        "forbidden_outputs": [
            "raw shell command",
            "dnsmasq configuration",
            "tftpd configuration",
            "router configuration",
            "docker compose boot service definition",
            "UDP 67/69/4011 listener instruction",
            ".env contents",
            "token or secret value",
        ],
        "blocking_items": blocking_items,
        "next_gate": [
            "Resolve any blocked evidence checks.",
            "Record manual isolated lab facts.",
            "Request fresh research, network safety, security, and project decision approval before runtime validation.",
        ],
    }


def isolated_lab_config_intent_package(loaders: list[dict]) -> dict:
    readiness = pxe_ipv4_readiness(loaders)
    skeleton = isolated_lab_boot_services_disabled_skeleton(loaders)
    menu_url = f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/menu.ipxe"
    reviewed_loaders = [
        loader
        for loader in skeleton.get("bootfile_candidates", [])
        if loader.get("usable") and loader.get("reviewed_for_lab") and loader.get("sha256_matches")
    ]
    candidate_bootfile = reviewed_loaders[0]["filename"] if reviewed_loaders else ""
    return {
        "schema_version": "phase3-isolated-lab-config-intent-package.v1",
        "phase": "3.12",
        "mode": "readonly_config_intent_package",
        "status": "not_authorized",
        "read_only": True,
        "request_is_authorization": False,
        "enabled": False,
        "authorized": False,
        "runtime_enabled": False,
        "secrets_included": False,
        "secret_redaction_applied": True,
        "secret_fields_allowed": False,
        "sensitive_values_exposed": False,
        "env_contents_exposed": False,
        "raw_commands_included": False,
        "config_files_generated": False,
        "config_generation_allowed": False,
        "command_execution_allowed": False,
        "service_start_allowed": False,
        "write_api_available": False,
        "compose_change_allowed": False,
        "router_config_generation_allowed": False,
        "production_lan_allowed": False,
        "production_lan_testing_allowed": False,
        "packet_capture_started": False,
        "network_probe_started": False,
        "task_consumption_allowed": False,
        "boot_tested": False,
        "environment_scope": "single_machine_isolated_lab_only",
        "intended_services": {
            "proxy_dhcp_metadata_only": "disabled_intent_only",
            "tftp_loader_only": "disabled_intent_only",
        },
        "network_service_state": {
            "dhcp_server_enabled": False,
            "dhcp_lease_assignment_allowed": False,
            "proxydhcp_enabled": False,
            "tftp_enabled": False,
            "udp_67_open": False,
            "udp_69_open": False,
            "udp_4011_open": False,
            "host_network_allowed": False,
            "privileged_container_allowed": False,
        },
        "intended_ports": [
            {
                "port": item["port"],
                "protocol": item["protocol"],
                "observed_listening": item["observed_in_api_namespace"],
                "desired_listening": False,
                "scope": "future_isolated_lab_review_only",
            }
            for item in udp_port_evidence()
        ],
        "candidate_bootfile": {
            "value": candidate_bootfile,
            "status": "intent_only",
            "tested": False,
            "applies_to": "isolated_lab_only",
        },
        "loader_allowlist": [
            {
                "name": loader.get("filename", ""),
                "reviewed": loader.get("reviewed_for_lab", False),
                "sha256": loader.get("sha256", ""),
                "served_by_loader_transfer": False,
                "path_reference": loader.get("path", ""),
            }
            for loader in reviewed_loaders
        ],
        "http_chain_target": {
            "menu_url": menu_url,
            "role": "ipxe_chain_target",
            "current_reference_only": True,
            "changes_http_topology": False,
            "reachable_from_pxe_path_tested": False,
        },
        "intent_chain": [
            "UEFI PXE IPv4 test client requests boot metadata inside a single-machine isolated lab only.",
            "Future reviewed metadata may point to one reviewed EFI loader candidate.",
            "The loader candidate would chain to the existing HTTP menu target.",
            "The HTTP menu would show ready image entries already present in SynaBoot.",
            "This package records intent only and does not authorize or perform runtime validation.",
        ],
        "client_validation_checklist": [
            {
                "id": "boot_mode_seen",
                "expected": "UEFI PXE IPv4",
                "observed": "",
                "passed": False,
            },
            {
                "id": "pxe_vendor_class",
                "expected": "PXEClient",
                "observed": "",
                "passed": False,
            },
            {
                "id": "bootfile_requested",
                "expected_one_of": [loader["filename"] for loader in reviewed_loaders],
                "observed": "",
                "passed": False,
            },
            {
                "id": "loader_reaches_http_menu",
                "expected_url": menu_url,
                "observed": "",
                "passed": False,
            },
            {
                "id": "ready_image_menu_rendered",
                "expected_ready_entry_count": readiness.get("image_menu", {}).get("ready_menu_entry_count", 0),
                "observed": "",
                "passed": False,
            },
        ],
        "manual_authorization_gates": [
            "research_agent_review_required_before_runtime",
            "network_safety_agent_review_required_before_runtime",
            "security_audit_agent_review_required_before_runtime",
            "project_decision_agent_review_required_before_runtime",
            "user_manual_isolated_lab_confirmation_required_before_runtime",
        ],
        "rollback_triggers": [
            "Any non-test client receives boot metadata.",
            "Any SynaBoot component assigns an ordinary DHCP lease.",
            "Any gated UDP boot port is observed outside an approved isolated lab.",
            "The test client does not reach the HTTP menu target.",
            "Production TP-Link or OpenWrt configuration is requested or changed.",
        ],
        "blocked_actions": [
            "Do not generate network boot service settings.",
            "Do not enable ProxyDHCP or TFTP from this intent package.",
            "Do not provide executable command text.",
            "Do not expose token, password, cookie, or private key material.",
            "Do not provide router or firewall change steps.",
            "Do not use this intent package on the production LAN.",
        ],
        "next_gate": [
            "Keep this package readonly and not authorized.",
            "Gather manual isolated lab facts outside the production LAN.",
            "Request fresh reviewer approvals before any runtime validation phase.",
        ],
    }


def isolated_lab_source_skeleton_package(loaders: list[dict]) -> dict:
    intent = isolated_lab_config_intent_package(loaders)
    reviewed_names = [loader.get("name", "") for loader in intent.get("loader_allowlist", [])]
    return {
        "schema_version": "phase3-isolated-lab-source-skeleton.v1",
        "phase": "3.13",
        "package_kind": "isolated_lab_boot_services_source_skeleton",
        "mode": "readonly_source_skeleton",
        "status": "not_runnable",
        "read_only": True,
        "fixture_only": True,
        "offline_package_only": True,
        "source_kind": "fixture_model_only",
        "request_is_authorization": False,
        "enabled": False,
        "authorized": False,
        "runtime_enabled": False,
        "runtime_available": False,
        "service_start_allowed": False,
        "service_started": False,
        "command_execution_allowed": False,
        "raw_commands_included": False,
        "config_generation_allowed": False,
        "config_files_generated": False,
        "write_api_available": False,
        "compose_integration_allowed": False,
        "compose_change_allowed": False,
        "docker_compose_modified": False,
        "router_change_allowed": False,
        "router_config_generation_allowed": False,
        "gateway_change_allowed": False,
        "firewall_change_allowed": False,
        "production_lan_allowed": False,
        "production_lan_testing_allowed": False,
        "host_network_allowed": False,
        "privileged_container_allowed": False,
        "task_consumption_allowed": False,
        "packet_send_allowed": False,
        "packet_capture_allowed": False,
        "packet_capture_started": False,
        "active_probe_allowed": False,
        "network_probe_started": False,
        "boot_tested": False,
        "forbidden_runtime_import": True,
        "requires_future_design_review": True,
        "requires_network_safety_review": True,
        "requires_security_audit_review": True,
        "requires_project_decision": True,
        "network_service_state": {
            "dhcp_server_enabled": False,
            "dhcp_lease_assignment_allowed": False,
            "proxydhcp_enabled": False,
            "tftp_enabled": False,
            "udp_67_open": False,
            "udp_69_open": False,
            "udp_4011_open": False,
            "udp_67_enabled": False,
            "udp_69_enabled": False,
            "udp_4011_enabled": False,
            "udp_67_listening": False,
            "udp_69_listening": False,
            "udp_4011_listening": False,
            "udp_67_mapped": False,
            "udp_69_mapped": False,
            "udp_4011_mapped": False,
            "host_network_allowed": False,
            "privileged_container_allowed": False,
        },
        "runtime_entrypoints": [],
        "compose_services": [],
        "generated_files": [],
        "opened_ports": [],
        "task_consumers": [],
        "network_listeners": [],
        "intended_services": {
            "proxy_dhcp_metadata_model": {
                "state": "source_placeholder_only",
                "enabled": False,
                "startable": False,
            },
            "tftp_loader_model": {
                "state": "source_placeholder_only",
                "enabled": False,
                "startable": False,
            },
        },
        "intended_ports": [
            {
                "port": item["port"],
                "protocol": item["protocol"],
                "observed_listening": item["observed_in_api_namespace"],
                "desired_listening": False,
                "model_only": True,
            }
            for item in udp_port_evidence()
        ],
        "offline_protocol_model": {
            "pxe_client_identification": {
                "vendor_class_expected": "PXEClient",
                "client_architecture_expected": "UEFI x64",
                "model_only": True,
            },
            "boot_metadata_intent": {
                "assigns_lease": False,
                "includes_gateway": False,
                "includes_dns": False,
                "includes_subnet": False,
                "includes_route": False,
                "candidate_bootfile": intent.get("candidate_bootfile", {}).get("value", ""),
                "reviewed_loader_names": reviewed_names,
            },
            "loader_transfer_scope": {
                "purpose": "future_loader_transfer_only",
                "service_enabled": False,
                "port_exposed": False,
                "root_path": "",
                "allowlist": [
                    {
                        "name": name,
                        "reviewed": True,
                        "served": False,
                    }
                    for name in reviewed_names
                ],
            },
            "http_chain_target": {
                "menu_url": intent.get("http_chain_target", {}).get("menu_url", ""),
                "role": "post_loader_ipxe_menu",
                "reachable_via_pxe_tested": False,
                "production_lan_supported": False,
            },
        },
        "offline_fixture_reference": {
            "path": "config/synaboot/phase3.13-isolated-lab-source-skeleton.disabled.json",
            "fixture_only": True,
            "loaded_at_runtime": False,
            "contains_real_client_data": False,
        },
        "client_evidence_fixture": [
            {
                "id": "boot_mode",
                "expected": "UEFI PXE IPv4",
                "observed": "",
                "passed": False,
            },
            {
                "id": "bootfile_request",
                "expected_one_of": reviewed_names,
                "observed": "",
                "passed": False,
            },
            {
                "id": "loader_start",
                "expected": "iPXE banner or menu handoff",
                "observed": "",
                "passed": False,
            },
            {
                "id": "http_menu_fetch",
                "expected": intent.get("http_chain_target", {}).get("menu_url", ""),
                "observed": "",
                "passed": False,
            },
            {
                "id": "ready_image_menu",
                "expected": "menu lists ready image entries",
                "observed": "",
                "passed": False,
            },
        ],
        "authorization_gates": [
            "research_agent_review_required_before_runtime",
            "network_safety_agent_review_required_before_runtime",
            "security_audit_agent_review_required_before_runtime",
            "project_decision_agent_review_required_before_runtime",
            "manual_isolated_lab_confirmation_required_before_runtime",
        ],
        "blocked_actions": [
            "Do not convert this source skeleton into a runnable service.",
            "Do not start or prepare ProxyDHCP or TFTP runtime from this source skeleton.",
            "Do not generate network boot service settings.",
            "Do not open, map, or expose UDP boot ports.",
            "Do not emit network packets or capture production LAN traffic.",
            "Do not use this source skeleton on the production LAN.",
        ],
        "next_gate": [
            "Keep this source skeleton offline and not runnable.",
            "Request fresh reviewer approvals before any runtime design.",
            "Obtain user manual isolated lab confirmation before any client interaction.",
        ],
    }


def isolated_lab_manual_declaration_gate() -> dict:
    expected_menu = f"http://<synaboot-lab-address>:{SYNABOOT_PORT}/boot/menu.ipxe"
    required_facts = [
        {
            "key": "physical_isolation_confirmed",
            "label": "实验网络与生产网络已隔离",
            "required": True,
            "status": "missing",
            "template_only": True,
            "stores_value": False,
        },
        {
            "key": "single_intended_test_client_confirmed",
            "label": "仅一个预期测试终端参与",
            "required": True,
            "status": "missing",
            "template_only": True,
            "stores_value": False,
        },
        {
            "key": "non_production_scope_confirmed",
            "label": "范围限定为非生产实验环境",
            "required": True,
            "status": "missing",
            "template_only": True,
            "stores_value": False,
        },
        {
            "key": "lab_addressing_source_identified",
            "label": "实验环境地址来源已人工确认",
            "required": True,
            "status": "missing",
            "template_only": True,
            "stores_value": False,
        },
        {
            "key": "lab_gateway_subnet_known",
            "label": "实验环境网关与网段已人工确认",
            "required": True,
            "status": "missing",
            "template_only": True,
            "stores_value": False,
        },
        {
            "key": "synaboot_lab_address_confirmed",
            "label": "SynaBoot 实验环境地址已人工确认",
            "required": True,
            "status": "missing",
            "template_only": True,
            "stores_value": False,
        },
        {
            "key": "rollback_plan_confirmed",
            "label": "实验异常时的断开与回滚方案已确认",
            "required": True,
            "status": "missing",
            "template_only": True,
            "stores_value": False,
        },
        {
            "key": "no_tplink_or_openwrt_change_confirmed",
            "label": "不变更 TP-Link 或 OpenWrt 生产配置",
            "required": True,
            "status": "missing",
            "template_only": True,
            "stores_value": False,
        },
        {
            "key": "no_production_lan_participation_confirmed",
            "label": "生产网络不参与本次实验",
            "required": True,
            "status": "missing",
            "template_only": True,
            "stores_value": False,
        },
    ]
    return {
        "schema_version": "phase3-isolated-lab-manual-declaration-gate.v1",
        "phase": "3.14",
        "gate_kind": "isolated_lab_manual_declaration_gate",
        "mode": "readonly_manual_declaration_gate",
        "template_mode": "readonly_manual_declaration_template",
        "status": "missing_facts",
        "submission_status": "not_submitted",
        "authorization_status": "not_authorized",
        "read_only": True,
        "template_only": True,
        "request_is_authorization": False,
        "collects_user_input": False,
        "stores_user_input": False,
        "contains_real_client_data": False,
        "contains_real_mac": False,
        "contains_real_ip": False,
        "contains_customer_info": False,
        "secrets_included": False,
        "raw_commands_included": False,
        "config_snippets_included": False,
        "write_api_available": False,
        "write_api_allowed": False,
        "database_write_allowed": False,
        "task_consumption_allowed": False,
        "config_generation_allowed": False,
        "config_files_generated": False,
        "command_execution_allowed": False,
        "service_start_allowed": False,
        "service_started": False,
        "runtime_enabled": False,
        "runtime_unlock_allowed": False,
        "enabled": False,
        "authorized": False,
        "production_lan_allowed": False,
        "production_lan_testing_allowed": False,
        "gateway_change_allowed": False,
        "route_change_allowed": False,
        "firewall_change_allowed": False,
        "dns_change_allowed": False,
        "packet_capture_allowed": False,
        "packet_capture_started": False,
        "network_probe_allowed": False,
        "network_probe_started": False,
        "active_probe_allowed": False,
        "command_execution_started": False,
        "compose_change_allowed": False,
        "host_network_allowed": False,
        "privileged_container_allowed": False,
        "router_read_allowed": False,
        "router_write_allowed": False,
        "tplink_read_allowed": False,
        "tplink_write_allowed": False,
        "openwrt_read_allowed": False,
        "openwrt_write_allowed": False,
        "boot_tested": False,
        "network_service_state": {
            "dhcp_server_enabled": False,
            "dhcp_enabled": False,
            "proxydhcp_enabled": False,
            "tftp_enabled": False,
            "udp_67_open": False,
            "udp_69_open": False,
            "udp_4011_open": False,
            "udp_67_opened": False,
            "udp_69_opened": False,
            "udp_4011_opened": False,
            "udp_67_mapped": False,
            "udp_69_mapped": False,
            "udp_4011_mapped": False,
            "udp_67_listening": False,
            "udp_69_listening": False,
            "udp_4011_listening": False,
        },
        "required_manual_facts": required_facts,
        "missing_facts": [item["key"] for item in required_facts],
        "authorization_gates": [
            "research_agent_review_required_before_runtime",
            "network_safety_agent_review_required_before_runtime",
            "security_audit_agent_review_required_before_runtime",
            "project_decision_agent_review_required_before_runtime",
            "user_manual_isolated_lab_confirmation_required_before_runtime",
        ],
        "boot_path_checklist": [
            {
                "id": "client_boot_entry",
                "expected": "UEFI PXE IPv4",
                "observed": "",
                "passed": False,
            },
            {
                "id": "loader_request",
                "expected_one_of": ["snponly.efi", "ipxe.efi"],
                "observed": "",
                "passed": False,
            },
            {
                "id": "http_menu_target",
                "expected": expected_menu,
                "observed": "",
                "passed": False,
            },
            {
                "id": "ready_image_menu",
                "expected": "ready image entries visible in iPXE menu",
                "observed": "",
                "passed": False,
            },
        ],
        "blocked_actions": [
            "Do not treat this declaration template as runtime authorization.",
            "Do not collect hardware address, customer, asset, or host identity values.",
            "Do not collect real environment addresses.",
            "Do not generate network boot service settings.",
            "Do not start or expose boot services from this gate.",
            "Do not use this gate on the production network.",
        ],
        "next_gate": [
            "Keep all declaration items missing until a separate approved submission design exists.",
            "Request fresh reviewer approvals before any isolated runtime validation.",
            "Keep production routing, gateway, firewall, and name resolution unchanged.",
        ],
    }


def isolated_lab_runtime_authorization_plan(manual_gate: dict) -> dict:
    missing_facts = list(manual_gate.get("missing_facts", []))
    return {
        "schema_version": "phase3-isolated-lab-runtime-authorization-plan.v1",
        "phase": "3.15",
        "plan_id": "isolated_lab_runtime_authorization_plan",
        "status": "blocked_until_manual_facts_and_approvals",
        "read_only": True,
        "source": "static_pre_review_plan",
        "depends_on_manual_gate_phase": manual_gate.get("phase", "3.14"),
        "request_is_authorization": False,
        "authorization_granted": False,
        "runtime_enabled": False,
        "runtime_start_allowed": False,
        "service_start_allowed": False,
        "service_started": False,
        "config_generation_allowed": False,
        "config_files_generated": False,
        "write_api_available": False,
        "write_api_allowed": False,
        "database_write_allowed": False,
        "task_consumption_allowed": False,
        "production_lan_allowed": False,
        "production_lan_testing_allowed": False,
        "boot_tested": False,
        "observations_recorded": False,
        "packet_capture_allowed": False,
        "packet_capture_started": False,
        "network_probe_allowed": False,
        "network_probe_started": False,
        "active_probe_allowed": False,
        "command_execution_allowed": False,
        "host_network_allowed": False,
        "privileged_container_allowed": False,
        "router_change_allowed": False,
        "gateway_change_allowed": False,
        "routing_change_allowed": False,
        "firewall_change_allowed": False,
        "dns_change_allowed": False,
        "normal_dhcp_leases_enabled": False,
        "network_service_state": {
            "dhcp_server_enabled": False,
            "proxydhcp_enabled": False,
            "tftp_enabled": False,
            "udp_67_open": False,
            "udp_69_open": False,
            "udp_4011_open": False,
            "udp_67_listening": False,
            "udp_69_listening": False,
            "udp_4011_listening": False,
            "udp_67_mapped": False,
            "udp_69_mapped": False,
            "udp_4011_mapped": False,
        },
        "missing_manual_facts": missing_facts,
        "manual_gate_status": manual_gate.get("status", ""),
        "manual_gate_ready": False,
        "required_approvals": [
            {
                "role": "research_agent",
                "status": "required_before_runtime",
                "stores_value": False,
            },
            {
                "role": "network_safety_agent",
                "status": "required_before_runtime",
                "stores_value": False,
            },
            {
                "role": "security_audit_agent",
                "status": "required_before_runtime",
                "stores_value": False,
            },
            {
                "role": "project_decision_agent",
                "status": "required_before_runtime",
                "stores_value": False,
            },
            {
                "role": "user_manual_confirmation",
                "status": "required_before_runtime",
                "stores_value": False,
            },
        ],
        "runtime_scope_candidates": [
            {
                "id": "single_client_isolated_lab",
                "status": "candidate_only",
                "allowed_to_execute": False,
                "requires_manual_fact_clearance": True,
            },
            {
                "id": "loader_transfer_for_reviewed_files_only",
                "status": "candidate_only",
                "allowed_to_execute": False,
                "requires_manual_fact_clearance": True,
            },
            {
                "id": "boot_metadata_without_ordinary_leases",
                "status": "candidate_only",
                "allowed_to_execute": False,
                "requires_manual_fact_clearance": True,
            },
        ],
        "explicit_non_goals": [
            "Do not use this plan as runtime authorization.",
            "Do not create ordinary client leases from SynaBoot.",
            "Do not change production routing, gateway, firewall, or name resolution.",
            "Do not generate router, service, or container override settings.",
            "Do not start boot services from this plan.",
            "Do not record real client or environment values in this plan.",
        ],
        "transition_requirements": [
            "All manual declaration facts must be cleared by a separate approved design.",
            "Research, network safety, security, and project decision approvals must be fresh for runtime.",
            "The isolated lab scope must remain separate from production clients.",
            "Rollback conditions must be reviewed before any client interaction.",
            "Boot evidence collection design must be reviewed before any packet interaction.",
        ],
        "rollback_conditions": [
            "Any non-test endpoint appears in the experiment path.",
            "Any ordinary lease assignment by SynaBoot is detected.",
            "Any production network change is requested.",
            "Any boot service is requested outside an approved isolated lab.",
            "The loader does not reach the HTTP menu target.",
        ],
        "boot_evidence_requirements": [
            {
                "id": "firmware_entry_selected",
                "expected": "UEFI PXE IPv4",
                "observed": "",
                "passed": False,
            },
            {
                "id": "reviewed_loader_requested",
                "expected_one_of": ["snponly.efi", "ipxe.efi"],
                "observed": "",
                "passed": False,
            },
            {
                "id": "http_menu_reached",
                "expected": "menu.ipxe reached by the reviewed loader",
                "observed": "",
                "passed": False,
            },
            {
                "id": "ready_image_menu_visible",
                "expected": "ready image entries visible in SynaBoot menu",
                "observed": "",
                "passed": False,
            },
            {
                "id": "no_ordinary_lease_from_synaboot",
                "expected": "SynaBoot does not assign ordinary client leases",
                "observed": "",
                "passed": False,
            },
        ],
        "future_research_items": [
            "Confirm production router boot metadata capability without changing ordinary leases.",
            "Confirm firmware behavior across representative UEFI PXE IPv4 clients.",
            "Confirm isolated lab response ordering and failure modes before runtime.",
            "Confirm rollback proof required before any production evaluation.",
        ],
        "next_gate": [
            "Keep this plan readonly and blocked.",
            "Design a separate authorization object only after manual facts are cleared.",
            "Request fresh reviewer approvals before any service or packet interaction.",
        ],
    }


def isolated_lab_runtime_authorization_draft(manual_gate: dict, runtime_plan: dict) -> dict:
    return {
        "schema_version": "phase3-isolated-lab-runtime-authorization-draft.v1",
        "phase": "3.16",
        "draft_id": "isolated_lab_runtime_authorization_draft",
        "status": "draft_blocked_until_evidence_and_approvals",
        "read_only": True,
        "source": "static_read_only_authorization_draft",
        "depends_on_manual_gate_phase": manual_gate.get("phase", "3.14"),
        "depends_on_plan_phase": runtime_plan.get("phase", "3.15"),
        "is_authorization_result": False,
        "is_state_transition_event": False,
        "is_runtime_config_source": False,
        "request_is_authorization": False,
        "authorized": False,
        "authorization_granted": False,
        "manual_facts_cleared": False,
        "runtime_enabled": False,
        "runtime_start_allowed": False,
        "service_start_allowed": False,
        "service_started": False,
        "config_generation_allowed": False,
        "config_files_generated": False,
        "write_api_available": False,
        "write_api_allowed": False,
        "database_write_allowed": False,
        "task_consumption_allowed": False,
        "production_lan_allowed": False,
        "production_lan_boot_allowed": False,
        "production_lan_testing_allowed": False,
        "boot_tested": False,
        "observations_recorded": False,
        "packet_capture_allowed": False,
        "packet_capture_started": False,
        "network_probe_allowed": False,
        "network_probe_started": False,
        "command_execution_allowed": False,
        "host_network": False,
        "host_network_allowed": False,
        "privileged": False,
        "privileged_container_allowed": False,
        "tp_link_modified": False,
        "openwrt_modified": False,
        "routing_modified": False,
        "gateway_modified": False,
        "firewall_modified": False,
        "dns_modified": False,
        "normal_dhcp_leases_enabled": False,
        "network_service_state": {
            "dhcp_server_enabled": False,
            "proxydhcp_enabled": False,
            "tftp_enabled": False,
            "udp_67_open": False,
            "udp_69_open": False,
            "udp_4011_open": False,
            "udp_67_listening": False,
            "udp_69_listening": False,
            "udp_4011_listening": False,
            "udp_67_mapped": False,
            "udp_69_mapped": False,
            "udp_4011_mapped": False,
        },
        "required_evidence": [
            {
                "id": "manual_facts_cleared_by_separate_design",
                "status": "missing",
                "required": True,
                "stores_value": False,
            },
            {
                "id": "fresh_reviewer_approvals_collected",
                "status": "missing",
                "required": True,
                "stores_value": False,
            },
            {
                "id": "isolated_scope_reviewed",
                "status": "missing",
                "required": True,
                "stores_value": False,
            },
            {
                "id": "rollback_plan_reviewed",
                "status": "missing",
                "required": True,
                "stores_value": False,
            },
            {
                "id": "boot_evidence_collection_reviewed",
                "status": "missing",
                "required": True,
                "stores_value": False,
            },
        ],
        "required_approvals": [
            {
                "role": "network_safety_agent",
                "status": "missing",
                "required": True,
                "stores_value": False,
            },
            {
                "role": "security_audit_agent",
                "status": "missing",
                "required": True,
                "stores_value": False,
            },
            {
                "role": "project_decision_agent",
                "status": "missing",
                "required": True,
                "stores_value": False,
            },
            {
                "role": "user_manual_confirmation",
                "status": "missing",
                "required": True,
                "stores_value": False,
            },
        ],
        "isolated_scope_requirements": [
            "The future authorization must describe an isolated non-production scope.",
            "The future authorization must exclude production clients.",
            "The future authorization must not change production routing or gateway behavior.",
            "The future authorization must keep ordinary client leases outside SynaBoot.",
        ],
        "rollback_plan_requirements": [
            "The future authorization must define immediate stop conditions.",
            "The future authorization must define how the lab path is disconnected.",
            "The future authorization must define how to confirm production clients remain unaffected.",
        ],
        "boot_evidence_collection_plan": [
            {
                "id": "uefi_pxe_ipv4_entry",
                "expected": "UEFI PXE IPv4 entry selected on the isolated test client",
                "observed": "",
                "passed": False,
            },
            {
                "id": "reviewed_loader_request",
                "expected_one_of": ["snponly.efi", "ipxe.efi"],
                "observed": "",
                "passed": False,
            },
            {
                "id": "http_menu_reached",
                "expected": "reviewed loader reaches the HTTP menu",
                "observed": "",
                "passed": False,
            },
            {
                "id": "ready_menu_visible",
                "expected": "ready image menu is visible",
                "observed": "",
                "passed": False,
            },
            {
                "id": "no_ordinary_leases_from_synaboot",
                "expected": "SynaBoot does not assign ordinary client leases",
                "observed": "",
                "passed": False,
            },
        ],
        "explicit_non_goals": [
            "This draft is not runtime authorization.",
            "This draft is not a state transition event.",
            "This draft is not a runtime configuration source.",
            "This draft must not start boot services.",
            "This draft must not generate network service settings.",
            "This draft must not touch the production LAN.",
        ],
        "transition_requirements": [
            "Create a separate authorization object only after missing evidence is cleared.",
            "Collect fresh reviewer approvals before any runtime transition.",
            "Keep this draft out of task, service, and configuration consumers.",
        ],
        "next_gate": [
            "Keep this authorization draft readonly and blocked.",
            "Design a separate submission model before storing any real values.",
            "Do not execute, generate, or transition from this draft.",
        ],
    }


def boot_entry_status() -> dict:
    menu_url = f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/menu.ipxe"
    loaders = boot_assets_status()["loaders"]
    manual_gate = isolated_lab_manual_declaration_gate()
    runtime_plan = isolated_lab_runtime_authorization_plan(manual_gate)
    return {
        "schema_version": "boot-entry.v1",
        "phase": "3.1",
        "display_phase": "3.4",
        "display_status": "readonly_boot_entry_with_local_fact_gate",
        "mode": "readonly_display_only",
        "status": "READONLY_MODEL_ONLY",
        "enabled": False,
        "default_enabled": False,
        "operation_allowed": False,
        "local_confirmed": False,
        "summary": "Phase 3 boot entry integration is modeled only. No DHCP, ProxyDHCP, or TFTP service is enabled.",
        "documentation": {
            "integration_guide": {
                "label": "Phase 3 boot entry integration guide",
                "path": "docs/BOOT_ENTRY_INTEGRATION.md",
                "purpose": "Readonly safety boundary, verification order, and rollback principles.",
            },
            "local_verification_template": {
                "label": "Local TP-Link capability verification template",
                "path": "docs/BOOT_ENTRY_LOCAL_VERIFICATION.md",
                "purpose": "Readonly evidence record for the TL-ER6120T constraint and Phase 3.3 gate.",
            },
            "proxydhcp_feasibility": {
                "label": "Boot Metadata Proxy feasibility evaluation",
                "path": "docs/PROXYDHCP_FEASIBILITY.md",
                "purpose": "Documentation-only Phase 3.3-A feasibility gate for PXE/HTTP boot metadata. No implementation or service enablement is approved.",
            },
            "proxydhcp_packet_review": {
                "label": "Boot Metadata Proxy packet review checklist",
                "path": "docs/PROXYDHCP_PACKET_REVIEW.md",
                "purpose": "Documentation-only field allow/deny checklist for future isolated verification.",
            },
            "tftp_loader_scope": {
                "label": "TFTP loader scope",
                "path": "docs/TFTP_LOADER_SCOPE.md",
                "purpose": "Documentation-only fixed loader allowlist for future isolated verification.",
            },
            "phase3_rollback_checklist": {
                "label": "Phase 3 rollback checklist",
                "path": "docs/PHASE3_ROLLBACK_CHECKLIST.md",
                "purpose": "Documentation-only rollback evidence checklist. No network change is approved.",
            },
            "phase3_review_templates": {
                "label": "Phase 3 review templates",
                "path": "docs/PHASE3_REVIEW_TEMPLATES.md",
                "purpose": "Documentation-only network and security review templates for future gates.",
            },
        },
        "local_verification_template": "docs/BOOT_ENTRY_LOCAL_VERIFICATION.md",
        "phase3_3a_boot_metadata_proxy_feasibility": phase3_3a_boot_metadata_proxy_feasibility(),
        "pxe_ipv4_readiness": pxe_ipv4_readiness(loaders),
        "pxe_lab_boot_metadata_plan": pxe_lab_boot_metadata_plan(loaders),
        "isolated_lab_boot_services_disabled_skeleton": isolated_lab_boot_services_disabled_skeleton(loaders),
        "isolated_lab_evidence_package": isolated_lab_evidence_package(loaders),
        "isolated_lab_config_intent_package": isolated_lab_config_intent_package(loaders),
        "isolated_lab_source_skeleton_package": isolated_lab_source_skeleton_package(loaders),
        "isolated_lab_manual_declaration_gate": manual_gate,
        "isolated_lab_runtime_authorization_plan": runtime_plan,
        "isolated_lab_runtime_authorization_draft": isolated_lab_runtime_authorization_draft(manual_gate, runtime_plan),
        "isolated_validation_plan": {
            "phase": "3.5",
            "mode": "readonly_plan_only",
            "status": "blocked_until_isolated_lab_approved",
            "read_only": True,
            "runtime_enabled": False,
            "production_lan_allowed": False,
            "requires_manual_authorization": True,
            "safety_invariants": {
                "primary_dhcp_invariant": "192.168.1.1",
                "default_gateway_invariant": "192.168.1.4",
                "dhcp_server_enabled": False,
                "proxydhcp_enabled": False,
                "tftp_enabled": False,
                "assigns_dhcp_leases": False,
                "changes_gateway": False,
                "udp_ports_allowed": [],
            },
            "purpose": "Prepare evidence requirements for a future isolated UEFI PXE IPv4 validation without enabling runtime network boot services.",
            "target_chain": [
                "UEFI PXE IPv4 test client requests boot metadata in an isolated lab only.",
                "Existing production TP-Link DHCP and OpenWrt gateway remain untouched.",
                "Future approved boot metadata points to an audited iPXE EFI loader.",
                f"iPXE chains to {menu_url}.",
                "SynaBoot HTTP menu displays only prepared image entries.",
            ],
            "environment_requirements": [
                "Use an isolated switch, test VLAN, or single-client lab that cannot affect production clients.",
                "Document the lab DHCP lease server, gateway, subnet, and SynaBoot test IP before any packet test.",
                "Keep production TP-Link 192.168.1.1 and OpenWrt 192.168.1.4 configuration unchanged.",
                "Use only approved loader filenames from data/boot/loaders.",
            ],
            "allowed_preparation": [
                "Read /api/boot-entry and /api/boot-assets.",
                "Verify loader file presence, regular-file status, SHA256, and Secure Boot risk.",
                "Prepare review records from docs/PHASE3_REVIEW_TEMPLATES.md.",
                "Prepare expected packet fields from docs/PROXYDHCP_PACKET_REVIEW.md.",
                "Prepare rollback evidence checklist from docs/PHASE3_ROLLBACK_CHECKLIST.md.",
            ],
            "forbidden_actions": [
                "Do not enable DHCP, ProxyDHCP, TFTP, or DHCPv6 Boot.",
                "Do not open UDP 67, 68, 69, or 4011.",
                "Do not change docker-compose.yml to host network or privileged containers.",
                "Do not change TP-Link DHCP lease, DNS, gateway, address pool, or boot options in production.",
                "Do not change OpenWrt route, NAT, firewall, DNS, VLAN, switch, AP, or IPv6 RA settings.",
                "Do not run packet tests on the production LAN before approval.",
            ],
            "required_evidence_before_lab": [
                "research_agent records remaining router and firmware unknowns.",
                "network_safety_agent approves the isolated lab boundary.",
                "security_audit_agent approves loader scope, path limits, and Docker/network posture.",
                "project_decision_agent authorizes the lab-only validation direction.",
                "git_audit_agent records diff, preflight output, and generated-file scope before milestone closeout.",
            ],
            "success_criteria_for_future_lab": [
                "A test client reaches the SynaBoot menu from UEFI PXE IPv4 in the isolated lab.",
                "No SynaBoot component assigns normal DHCP leases.",
                "Default gateway observed by the test client matches the lab plan.",
                "TFTP, if later approved, serves only allowlisted loader files.",
                "HTTP menu and image URLs load from the SynaBoot server.",
                "Stopping the approved lab service restores the lab client to ordinary DHCP behavior.",
            ],
            "exit_conditions": [
                "Any packet shows SynaBoot assigning IP leases.",
                "Any packet changes gateway, DNS, route, or lease options outside the approved boot metadata.",
                "A non-PXE client receives boot metadata unexpectedly.",
                "A loader path escapes data/boot/loaders or resolves through a symlink.",
                "The test touches production LAN services or clients.",
            ],
            "implementation_allowed": False,
            "service_enablement_allowed": False,
            "production_lan_testing_allowed": False,
        },
        "phase3_3_gate": {
            "status": "router_option_path_not_recommended_but_blocked",
            "reason": "TL-ER6120T identity is screenshot-confirmed, and the administrator confirmed it cannot provide the required PXE/HTTP Boot metadata. Router DHCP Option path is not recommended; only controlled Boot Metadata Proxy feasibility evaluation is allowed.",
            "operational_assumption": "Do not rely on the main router DHCP Option 66/67 path unless later evidence proves it is available and safe.",
            "allowed_next_step": "controlled_boot_metadata_proxy_feasibility_evaluation_only",
            "template": "docs/BOOT_ENTRY_LOCAL_VERIFICATION.md",
            "confirmed_evidence": [
                "Router model: TP-Link TL-ER6120T.",
                "Hardware version: TL-ER6120T 1.0.",
                "Current firmware: 1.2.2 Build 240829 Rel.84642n.",
                "Router UI screenshot did not show DHCP Option 66/67 or equivalent boot option settings.",
                "Administrator confirmed the TL-ER6120T cannot provide the required PXE/HTTP Boot metadata.",
            ],
            "missing_local_facts": [
                "Whether TL-ER6120T exposes next-server / boot server settings in another readonly page.",
                "Whether TL-ER6120T exposes bootfile / Option 67 settings in another readonly page.",
                "Whether TL-ER6120T can match Vendor Class Option 60 for PXEClient or HTTPClient.",
                "Whether TL-ER6120T can match Client Architecture Option 93 for BIOS versus UEFI clients.",
                "Whether firmware 1.2.3 changes boot metadata capabilities.",
            ],
            "blocked_until": [
                "Readonly local evidence proves router boot metadata settings exist and are safe, or project_decision_agent approves continuing only with controlled Boot Metadata Proxy feasibility evaluation.",
                "network_safety_agent and security_audit_agent approve any future isolated validation plan.",
                "No production LAN test, ProxyDHCP/TFTP enablement, or UDP 67/68/69/4011 exposure is requested by this API state.",
            ],
            "do_not_infer": [
                "Do not infer Option 66/67 support from the device model alone.",
                "Do not infer safe PXE behavior from a firmware update notice.",
                "Do not treat the ProxyDHCP candidate as approved implementation work.",
            ],
        },
        "phase3_3_feasibility": {
            "mode": "documentation_only",
            "status": "blocked_for_implementation",
            "candidate": "boot_metadata_proxy_feasibility_only",
            "product_name": "Boot Metadata Proxy",
            "doc": "docs/PROXYDHCP_FEASIBILITY.md",
            "packet_review_doc": "docs/PROXYDHCP_PACKET_REVIEW.md",
            "tftp_loader_scope_doc": "docs/TFTP_LOADER_SCOPE.md",
            "rollback_checklist_doc": "docs/PHASE3_ROLLBACK_CHECKLIST.md",
            "review_templates_doc": "docs/PHASE3_REVIEW_TEMPLATES.md",
            "implementation_allowed": False,
            "service_enablement_allowed": False,
            "production_lan_testing_allowed": False,
            "required_gates": [
                "research_agent",
                "network_safety_agent",
                "security_audit_agent",
                "project_decision_agent",
            ],
        },
        "server": {
            "server_ip": SERVER_IP,
            "http_port": SYNABOOT_PORT,
            "base_url": f"http://{SERVER_IP}:{SYNABOOT_PORT}",
            "menu_url": menu_url,
            "http_boot_loader_url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/loaders/ipxe.efi",
        },
        "lan_contract": {
            "dhcp_lease_server": "TP-Link TL-ER6120T 192.168.1.1",
            "default_gateway": "192.168.1.4",
            "synaboot_assigns_dhcp_leases": False,
            "compose_network_change_allowed": False,
            "router_change_performed_by_api": False,
        },
        "recommended_urls": {
            "web": f"http://{SERVER_IP}:{SYNABOOT_PORT}/",
            "ipxe_menu": menu_url,
            "http_ipv4_loader": f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/loaders/ipxe.efi",
            "pxe_uefi_loader": "ipxe.efi",
            "pxe_chain_menu": f"chain {menu_url}",
            "images": f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/",
        },
        "entries": [
            {
                "id": "uefi-http-ipv4",
                "label": "UEFI HTTP IPv4",
                "enabled": False,
                "status": "needs_local_verification",
                "requires_manual_external_change": True,
                "target": f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/loaders/ipxe.efi",
                "chain": [f"HTTP loader URL", f"iPXE chain {menu_url}"],
                "blocked_by": ["TL-ER6120T HTTPClient vendor-class support is not locally verified", "Secure Boot compatibility is not verified"],
            },
            {
                "id": "uefi-pxe-ipv4",
                "label": "UEFI PXE IPv4",
                "enabled": False,
                "status": "needs_local_verification",
                "requires_manual_external_change": True,
                "next_server": SERVER_IP,
                "bootfile": "snponly.efi or ipxe.efi",
                "chain": ["PXE boot metadata", f"iPXE chain {menu_url}"],
                "blocked_by": ["Option 67 / bootfile support is not locally verified", "Client Architecture / Option 93 matching is not verified"],
            },
            {
                "id": "uefi-http-ipv6",
                "label": "UEFI HTTP IPv6",
                "enabled": False,
                "status": "blocked",
                "requires_manual_external_change": True,
                "target": "requires verified LAN IPv6 RA/DHCPv6 and HTTP Boot URL",
                "chain": ["IPv6 HTTP boot metadata", "iPXE menu chain"],
                "blocked_by": ["LAN IPv6 RA/DHCPv6 boot support is not verified", "SynaBoot does not modify OpenWrt IPv6 configuration"],
            },
            {
                "id": "uefi-pxe-ipv6",
                "label": "UEFI PXE IPv6",
                "enabled": False,
                "status": "blocked",
                "requires_manual_external_change": True,
                "target": "requires verified DHCPv6/PXE boot metadata",
                "chain": ["IPv6 PXE metadata", "iPXE menu chain"],
                "blocked_by": ["DHCPv6 PXE support is not verified", "SynaBoot does not modify router RA/DHCPv6/firewall settings"],
            },
        ],
        "optional_services": [
            {
                "id": "proxydhcp",
                "label": "ProxyDHCP metadata only",
                "enabled": False,
                "status": "blocked",
                "requires_manual_external_change": True,
                "ports": ["udp/67", "udp/4011"],
                "guardrails": ["must not assign IP leases", "must not set gateway or DNS", "must pass network_safety_agent and security_audit_agent"],
            },
            {
                "id": "tftp",
                "label": "TFTP boot loader serving",
                "enabled": False,
                "status": "blocked",
                "requires_manual_external_change": True,
                "ports": ["udp/69"],
                "root": "data/boot/loaders",
                "guardrails": ["serve boot loaders only", "must remain disabled by default", "must pass network_safety_agent and security_audit_agent"],
            },
        ],
        "services": {
            "proxy_dhcp": {
                "enabled": False,
                "available_in_phase": False,
                "mode": "metadata_only_when_future_approved",
                "would_assign_ip_leases": False,
                "udp_ports": [67, 4011],
                "activation_gate": "network_safety_agent + security_audit_agent + project_decision_agent",
            },
            "tftp": {
                "enabled": False,
                "available_in_phase": False,
                "root": "./data/boot/loaders",
                "allowed_files_scope": "boot loaders only",
                "udp_ports": [69],
                "activation_gate": "network_safety_agent + security_audit_agent + project_decision_agent",
            },
        },
        "loaders": loaders,
        "safety": {
            "dhcp_server_enabled": False,
            "proxydhcp_enabled": False,
            "tftp_enabled": False,
            "assigns_dhcp_leases": False,
            "changes_gateway": False,
            "gateway_expected": "192.168.1.4",
            "existing_dhcp_server_expected": "192.168.1.1",
            "blocked_actions": [
                "Do not enable DHCP.",
                "Do not enable ProxyDHCP.",
                "Do not enable TFTP.",
                "Do not modify gateway, DNS, routes, firewall, VLAN, switch, or AP configuration.",
                "Do not generate directly executable router configuration steps before local verification.",
            ],
        },
        "local_verification_required": [
            "Treat TL-ER6120T model, hardware version, and firmware version as screenshot-confirmed evidence.",
            "Do not rely on the router DHCP Option 66/67 path unless later readonly evidence proves the settings exist and are safe.",
            "Confirm whether next-server / boot server is available.",
            "Confirm whether Vendor Class Option 60 can distinguish PXEClient and HTTPClient.",
            "Confirm whether Client Architecture Option 93 can distinguish BIOS and UEFI clients.",
            "Keep Phase 3.3 blocked; only controlled ProxyDHCP feasibility evaluation may be researched next.",
            "Validate any future boot metadata behavior only in an isolated test VLAN or single-client lab before production use.",
        ],
        "safety_gates": [
            "TP-Link 192.168.1.1 remains the only normal DHCP lease server.",
            "Default gateway remains OpenWrt 192.168.1.4.",
            "No Docker host network or privileged container is enabled.",
            "No UDP 67/68/69/4011 listener is enabled by Phase 3.1.",
            "Any Phase 3.3 ProxyDHCP/TFTP design requires network_safety_agent and security_audit_agent approval.",
        ],
        "safety_gates_detail": {
            "phase3_1_allowed": ["GET /api/boot-entry", "readonly recommended URLs", "verification gaps and gate status"],
            "phase3_1_forbidden": [
                "enable DHCP service",
                "enable ProxyDHCP",
                "enable TFTP",
                "modify docker-compose.yml",
                "publish UDP 67/69/4011",
                "modify TP-Link router configuration",
                "modify OpenWrt gateway, route, NAT, firewall, DNS, VLAN, switch, or AP configuration",
                "change default gateway 192.168.1.4",
                "assign normal DHCP leases from SynaBoot",
            ],
            "future_activation_required_approvals": [
                "research_agent fact confirmation",
                "network_safety_agent APPROVED",
                "security_audit_agent APPROVED",
                "project_decision_agent authorization",
            ],
        },
    }


class Handler(BaseHTTPRequestHandler):
    def redacted_request_text(self, value: str) -> str:
        value = re.sub(r"([?&]token=)[^&\s]+", r"\1<redacted>", value)
        value = re.sub(r"([?&]session_token=)[^&\s]+", r"\1<redacted>", value)
        value = re.sub(
            r"(/api/postinstall/assignments/[^/\s]+/nocloud/[^/\s]+/)[^/\s]+/",
            r"\1<redacted>/",
            value,
        )
        return value

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        sys.stderr.write(
            "%s - - [%s] \"%s\" %s %s\n"
            % (self.client_address[0], self.log_date_time_string(), self.redacted_request_text(self.requestline), str(code), str(size))
        )

    def log_message(self, format: str, *args: object) -> None:
        message = self.redacted_request_text(format % args)
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), message))

    def has_admin_header(self) -> bool:
        if not ADMIN_TOKEN:
            return False
        provided = self.headers.get("X-SynaBoot-Admin-Token", "")
        return token_matches(provided, ADMIN_TOKEN)

    def require_admin(self) -> bool:
        client = self.client_address[0]
        now = time.time()
        last = LAST_WRITE_BY_CLIENT.get(client, 0)
        if now - last < 2:
            json_response(self, 429, {"error": "rate_limited"})
            return False
        LAST_WRITE_BY_CLIENT[client] = now
        if not ADMIN_TOKEN:
            json_response(self, 403, {"error": "admin_actions_disabled"})
            return False
        provided = self.headers.get("X-SynaBoot-Admin-Token", "")
        if not token_matches(provided, ADMIN_TOKEN):
            json_response(self, 403, {"error": "invalid_admin_token"})
            return False
        return True

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            json_response(self, 200, {"status": "ok", "server_ip": SERVER_IP, "admin_configured": bool(ADMIN_TOKEN)})
        elif path == "/api/admin/session":
            if not ADMIN_TOKEN:
                json_response(self, 200, admin_session_payload(False))
            elif self.has_admin_header():
                json_response(self, 200, admin_session_payload(True))
            else:
                json_response(self, 403, {"error": "invalid_admin_token", **admin_session_payload(False)})
        elif path == "/api/ipxe/register":
            text_response(self, 200, passive_register_script(self))
        elif path == "/api/ipxe/wait":
            text_response(self, 200, passive_wait_response(self))
        elif path == "/api/client-sessions":
            json_response(self, 200, list_client_sessions(include_private=self.has_admin_header()))
        elif path == "/api/assignment-options":
            if not self.has_admin_header():
                json_response(self, 403, {"error": "invalid_admin_token" if ADMIN_TOKEN else "admin_actions_disabled"})
                return
            query = parse_qs(urlparse(self.path).query)
            session_id = query_value(query, "session_id")
            session_ids_value = query_value(query, "session_ids")
            session_ids = [item.strip() for item in session_ids_value.split(",") if item.strip()] if session_ids_value else [session_id]
            options = assignment_options(session_ids)
            if options is None:
                json_response(self, 404, {"error": "client_session_not_found"})
            else:
                json_response(self, 200, options)
        elif path == "/api/software-packages":
            query = parse_qs(urlparse(self.path).query)
            os_family = query_value(query, "os_family") or None
            include_blocked = query_value(query, "include_blocked") != "false"
            json_response(
                self,
                200,
                {
                    "schema_version": "synaboot.software-packages.v1",
                    "policy": {
                        "artifact_hosting_allowed": False,
                        "third_party_binary_stored": False,
                        "client_downloads_from_official_source": True,
                    },
                    "packages": list_software_packages(os_family=os_family, include_blocked=include_blocked),
                },
            )
        elif path.startswith("/api/software-packages/"):
            package_id = path.rstrip("/").rsplit("/", 1)[-1]
            package = get_software_package(package_id)
            if package is None:
                json_response(self, 404, {"error": "software_package_not_found"})
            else:
                json_response(self, 200, package)
        elif path == "/api/software-variants":
            query = parse_qs(urlparse(self.path).query)
            os_family = query_value(query, "os_family") or None
            include_blocked = query_value(query, "include_blocked") != "false"
            json_response(
                self,
                200,
                {
                    "schema_version": "synaboot.software-variants.v1",
                    "variants": list_software_variants(os_family=os_family, include_blocked=include_blocked),
                },
            )
        elif path == "/api/software-profiles":
            query = parse_qs(urlparse(self.path).query)
            os_family = query_value(query, "os_family") or None
            json_response(
                self,
                200,
                {
                    "schema_version": "synaboot.software-profiles.v1",
                    "policy": {
                        "artifact_hosting_allowed": False,
                        "third_party_binary_stored": False,
                        "profile_groups_assignable_variants_only": True,
                    },
                    "profiles": list_software_profiles(os_family=os_family),
                },
            )
        elif path == "/api/install-presets":
            query = parse_qs(urlparse(self.path).query)
            os_family = query_value(query, "os_family") or None
            json_response(
                self,
                200,
                {
                    "schema_version": "synaboot.install-presets.v1",
                    "policy": {
                        "disk_configuration_enabled": False,
                        "software_source": "official_download_or_repo_only",
                    },
                    "presets": list_install_presets(os_family=os_family),
                },
            )
        elif path.startswith("/api/install-presets/"):
            preset_id = path.rstrip("/").rsplit("/", 1)[-1]
            preset = get_install_preset(preset_id)
            if preset is None:
                json_response(self, 404, {"error": "install_preset_not_found"})
            else:
                json_response(self, 200, preset)
        elif path.startswith("/api/software-variants/"):
            variant_id = path.rstrip("/").rsplit("/", 1)[-1]
            variant = get_software_variant(variant_id)
            if variant is None:
                json_response(self, 404, {"error": "software_variant_not_found"})
            else:
                json_response(self, 200, variant)
        elif path == "/api/deployment-assignments":
            if not self.has_admin_header():
                json_response(self, 403, {"error": "invalid_admin_token" if ADMIN_TOKEN else "admin_actions_disabled"})
                return
            json_response(self, 200, {"schema_version": "synaboot.deployment-assignments.v1", "assignments": list_deployment_assignments()})
        elif path.startswith("/api/deployment-assignments/"):
            if not self.has_admin_header():
                json_response(self, 403, {"error": "invalid_admin_token" if ADMIN_TOKEN else "admin_actions_disabled"})
                return
            assignment_id = path.rstrip("/").rsplit("/", 1)[-1]
            assignment = get_deployment_assignment(assignment_id)
            if assignment is None:
                json_response(self, 404, {"error": "deployment_assignment_not_found"})
            else:
                json_response(self, 200, assignment)
        elif path.startswith("/api/postinstall/assignments/") and "/nocloud/" in path:
            parts = path.strip("/").split("/")
            if len(parts) != 8:
                json_response(self, 404, {"error": "not_found"})
                return
            assignment_id = parts[3]
            session_id = parts[5]
            token = parts[6]
            seed_file = parts[7]
            try:
                assignment, session = verify_postinstall_access(assignment_id, session_id, token)
            except ValueError as exc:
                json_response(self, 403 if str(exc) == "invalid_session_token" else 404, {"error": str(exc)})
                return
            if seed_file == "meta-data":
                text_response(self, 200, ubuntu_nocloud_meta_data(assignment, session), content_type="text/plain; charset=utf-8")
            elif seed_file == "user-data":
                try:
                    text_response(self, 200, ubuntu_nocloud_user_data(assignment, session, token), content_type="text/cloud-config; charset=utf-8")
                except ValueError as exc:
                    json_response(self, 400, {"error": str(exc)})
            else:
                json_response(self, 404, {"error": "not_found"})
        elif path.startswith("/api/postinstall/assignments/"):
            parts = path.strip("/").split("/")
            if len(parts) != 5:
                json_response(self, 404, {"error": "not_found"})
                return
            assignment_id = parts[3]
            action = parts[4]
            query = parse_qs(urlparse(self.path).query)
            session_id = query_value(query, "session_id")
            token = query_value(query, "token")
            try:
                assignment, session = verify_postinstall_access(assignment_id, session_id, token)
            except ValueError as exc:
                json_response(self, 403 if str(exc) == "invalid_session_token" else 404, {"error": str(exc)})
                return
            if action == "plan":
                json_response(self, 200, postinstall_plan_payload(assignment, session))
            elif action == "runner.sh":
                try:
                    text_response(self, 200, ubuntu_postinstall_runner(assignment, session, token), content_type="text/x-shellscript; charset=utf-8")
                except ValueError as exc:
                    json_response(self, 400, {"error": str(exc)})
            elif action == "runner.ps1":
                try:
                    text_response(self, 200, windows_postinstall_runner(assignment, session, token), content_type="text/plain; charset=utf-8")
                except ValueError as exc:
                    json_response(self, 400, {"error": str(exc)})
            elif action == "setupcomplete.cmd":
                try:
                    text_response(self, 200, windows_setupcomplete_cmd(assignment, session, token), content_type="text/plain; charset=utf-8")
                except ValueError as exc:
                    json_response(self, 400, {"error": str(exc)})
            elif action == "windows-hotpe-inject.ps1":
                try:
                    text_response(self, 200, windows_hotpe_injection_helper_ps1(assignment, session, token), content_type="text/plain; charset=utf-8")
                except ValueError as exc:
                    json_response(self, 400, {"error": str(exc)})
            else:
                json_response(self, 404, {"error": "not_found"})
        elif path == "/api/images":
            json_response(self, 200, images_inventory_payload(list_images()))
        elif path.startswith("/api/images/"):
            image_id = path.rstrip("/").rsplit("/", 1)[-1]
            image = get_image(image_id)
            if image is None:
                json_response(self, 404, {"error": "image_not_found"})
            else:
                json_response(self, 200, image)
        elif path == "/api/menu":
            text_response(self, 200, read_menu())
        elif path == "/api/jobs":
            json_response(self, 200, {"jobs": list_jobs()})
        elif path == "/api/autoinstall-profiles":
            json_response(self, 200, {"profiles": list_autoinstall_profiles()})
        elif path in {"/api/autoinstall-binding-plan", "/api/autoinstall-bindings/plan"}:
            json_response(self, 200, autoinstall_binding_plan())
        elif path == "/api/capabilities":
            json_response(self, 200, capabilities_status())
        elif path == "/api/hotpe-readiness":
            json_response(self, 200, hotpe_readiness_status())
        elif path == "/api/windows-install-candidates":
            json_response(self, 200, windows_install_candidates())
        elif path.startswith("/api/jobs/") and path.endswith("/events"):
            job_id = path.split("/")[-2]
            events = list_job_events(job_id)
            if events is None:
                json_response(self, 404, {"error": "job_not_found"})
            else:
                json_response(self, 200, {"events": events})
        elif path.startswith("/api/jobs/"):
            job_id = path.rstrip("/").rsplit("/", 1)[-1]
            job = get_job(job_id)
            if job is None:
                json_response(self, 404, {"error": "job_not_found"})
            else:
                json_response(self, 200, job)
        elif path in {"/api/network-safety", "/api/safety"}:
            json_response(self, 200, network_safety_status())
        elif path == "/api/deployment-status":
            json_response(self, 200, deployment_status())
        elif path == "/api/boot-entry":
            json_response(self, 200, boot_entry_status())
        elif path == "/api/boot-assets":
            json_response(self, 200, boot_assets_status())
        else:
            json_response(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/postinstall/assignments/") and path.endswith("/events"):
            parts = path.strip("/").split("/")
            if len(parts) != 5:
                json_response(self, 404, {"error": "not_found"})
                return
            payload = self.read_json_payload()
            if payload is None:
                return
            try:
                event = record_postinstall_event(parts[3], payload)
            except ValueError as exc:
                json_response(self, 403 if str(exc) == "invalid_session_token" else 400, {"error": str(exc)})
                return
            json_response(self, 201, event)
            return
        if not self.require_admin():
            return
        if path == "/api/deployment-assignments":
            payload = self.read_json_payload()
            if payload is None:
                return
            try:
                assignment = create_deployment_assignment(payload)
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
                return
            if assignment is None:
                json_response(self, 404, {"error": "client_session_not_found"})
            else:
                json_response(self, 201, assignment)
            return
        if path == "/api/software-packages":
            payload = self.read_json_payload()
            if payload is None:
                return
            try:
                package = create_software_package(payload)
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
                return
            json_response(self, 201, package)
            return
        if path == "/api/install-presets":
            payload = self.read_json_payload()
            if payload is None:
                return
            try:
                preset = create_install_preset(payload)
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
                return
            json_response(self, 201, preset)
            return
        if path.startswith("/api/install-presets/") and (path.endswith("/archive") or path.endswith("/restore")):
            parts = path.strip("/").split("/")
            if len(parts) != 4:
                json_response(self, 404, {"error": "not_found"})
                return
            status = "archived" if parts[3] == "archive" else "available"
            try:
                preset = update_install_preset_status(parts[2], status)
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
                return
            if preset is None:
                json_response(self, 404, {"error": "install_preset_not_found"})
            else:
                json_response(self, 200, preset)
            return
        if path.startswith("/api/software-packages/") and (path.endswith("/archive") or path.endswith("/restore")):
            parts = path.strip("/").split("/")
            if len(parts) != 4:
                json_response(self, 404, {"error": "not_found"})
                return
            status = "archived" if parts[3] == "archive" else "available"
            try:
                package = update_software_package_status(parts[2], status)
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
                return
            if package is None:
                json_response(self, 404, {"error": "software_package_not_found"})
            else:
                json_response(self, 200, package)
            return
        if path.startswith("/api/software-packages/") and path.endswith("/variants"):
            parts = path.strip("/").split("/")
            if len(parts) != 4:
                json_response(self, 404, {"error": "not_found"})
                return
            payload = self.read_json_payload()
            if payload is None:
                return
            try:
                variant = create_software_variant(parts[2], payload)
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
                return
            json_response(self, 201, variant)
            return
        if path == "/api/software-profiles":
            payload = self.read_json_payload()
            if payload is None:
                return
            try:
                profile = create_software_profile(payload)
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
                return
            json_response(self, 201, profile)
            return
        if path.startswith("/api/software-profiles/") and (path.endswith("/archive") or path.endswith("/restore")):
            parts = path.strip("/").split("/")
            if len(parts) != 4:
                json_response(self, 404, {"error": "not_found"})
                return
            status = "archived" if parts[3] == "archive" else "available"
            try:
                profile = update_software_profile_status(parts[2], status)
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
                return
            if profile is None:
                json_response(self, 404, {"error": "software_profile_not_found"})
            else:
                json_response(self, 200, profile)
            return
        if path.startswith("/api/software-variants/") and path.endswith("/review"):
            variant_id = path.split("/")[-2]
            payload = self.read_json_payload()
            if payload is None:
                return
            try:
                variant = update_software_variant(variant_id, payload)
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
                return
            if variant is None:
                json_response(self, 404, {"error": "software_variant_not_found"})
            else:
                json_response(self, 200, variant)
            return
        if path.startswith("/api/client-sessions/") and path.endswith("/assign"):
            session_id = path.split("/")[-2]
            payload = self.read_json_payload()
            if payload is None:
                return
            try:
                session = assign_client_session(session_id, str(payload.get("target", "")))
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
                return
            if session is None:
                json_response(self, 404, {"error": "client_session_not_found"})
            else:
                json_response(self, 200, session)
            return
        if path == "/api/scan":
            images = scan_images()
            json_response(self, 200, {"images": images, "count": len(images)})
            return
        if path == "/api/menu/generate":
            text_response(self, 200, write_menu())
            return
        if path.startswith("/api/images/") and path.endswith("/enable"):
            image_id = path.split("/")[-2]
            image = set_image_menu_enabled(image_id, True)
            if image is None:
                json_response(self, 404, {"error": "image_not_found"})
            else:
                write_menu()
                json_response(self, 200, image)
            return
        if path.startswith("/api/images/") and path.endswith("/disable"):
            image_id = path.split("/")[-2]
            image = set_image_menu_enabled(image_id, False)
            if image is None:
                json_response(self, 404, {"error": "image_not_found"})
            else:
                write_menu()
                json_response(self, 200, image)
            return
        if path.startswith("/api/images/") and path.endswith("/metadata"):
            image_id = path.split("/")[-2]
            payload = self.read_json_payload()
            if payload is None:
                return
            image = set_image_metadata(image_id, payload)
            if image is None:
                json_response(self, 404, {"error": "image_not_found"})
            else:
                write_menu()
                json_response(self, 200, image)
            return
        if path == "/api/autoinstall-profiles":
            payload = self.read_json_payload()
            if payload is None:
                return
            try:
                profile = create_autoinstall_profile(payload)
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
                return
            json_response(self, 201, profile)
            return
        if path in {
            "/api/jobs/ubuntu-autoinstall",
            "/api/jobs/ubuntu-autoinstall-template",
            "/api/jobs/ubuntu-xorriso-iso",
            "/api/jobs/windows-adk-package",
            "/api/jobs/hotpe-iso-prepare",
            "/api/jobs/ubuntu-iso-extract-kernel-initrd",
        }:
            kind = path.rsplit("/", 1)[-1]
            try:
                job = create_job({"kind": kind})
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
                return
            json_response(self, 201, job)
            return
        if path.startswith("/api/jobs/") and path.endswith(("/submit", "/cancel")):
            job_id = path.split("/")[-2]
            target_status = "pending" if path.endswith("/submit") else "canceled"
            job = update_job_status(job_id, target_status)
            if job is None:
                json_response(self, 404, {"error": "job_not_found_or_unsupported_transition"})
            elif job.get("transition_error"):
                json_response(self, 409, {"error": "invalid_transition", "detail": job["transition_error"], "job": job})
            else:
                json_response(self, 200, job)
            return
        if path != "/api/jobs":
            json_response(self, 404, {"error": "not_found"})
            return
        payload = self.read_json_payload()
        if payload is None:
            return
        try:
            job = create_job(payload)
        except ValueError as exc:
            json_response(self, 400, {"error": str(exc)})
            return
        json_response(self, 201, job)

    def read_json_payload(self) -> dict | None:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 65536:
            json_response(self, 413, {"error": "payload_too_large"})
            return None
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            json_response(self, 400, {"error": "invalid_json"})
            return None
        if not isinstance(payload, dict):
            json_response(self, 400, {"error": "invalid_json_object"})
            return None
        return payload


def main() -> None:
    ensure_dirs()
    connect_db().close()
    server = ThreadingHTTPServer((API_HOST, API_PORT), Handler)
    print(f"SynaBoot API listening on {API_HOST}:{API_PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
