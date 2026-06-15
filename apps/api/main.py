#!/usr/bin/env python3
import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse

SERVER_IP = os.environ.get("SERVER_IP", "192.168.1.168")
SYNABOOT_PORT = int(os.environ.get("SYNABOOT_PORT", "18080"))
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
    conn.commit()
    return conn


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


def text_response(handler: BaseHTTPRequestHandler, status: int, body: str) -> None:
    encoded = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
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
    return has_iso and f"{directory}/casper/vmlinuz" in present and f"{directory}/casper/initrd" in present


def hotpe_group_ready(present: set[str]) -> bool:
    return set(hotpe_required_artifacts()).issubset(present)


def hotpe_required_artifacts() -> list[str]:
    return [
        "pe/hotpe/wimboot",
        "pe/hotpe/bootmgr",
        "pe/hotpe/BCD",
        "pe/hotpe/boot.sdi",
        "pe/hotpe/boot.wim",
    ]


def linux_base_dir(rel_path: str) -> str:
    if "/casper/" in rel_path:
        return rel_path.split("/casper/", 1)[0]
    return rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""


def linux_required_artifacts(rel_path: str) -> list[str]:
    directory = linux_base_dir(rel_path)
    if not directory:
        return []
    return [f"{directory}/casper/vmlinuz", f"{directory}/casper/initrd"]


def missing_artifacts_for(category: str, kind: str, rel_path: str, present: set[str]) -> list[str]:
    if category == "pe" and "pe/hotpe/" in rel_path:
        return [path for path in hotpe_required_artifacts() if path not in present]
    if category == "linux":
        return [path for path in linux_required_artifacts(rel_path) if path not in present]
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
    if kind in {"linux-kernel", "initrd", "wimboot", "bootmgr", "bcd", "boot-sdi", "wim"}:
        return "boot_artifact"
    return "repository_file"


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
        return "创建 Ubuntu/Linux ISO 准备任务，提取 casper/vmlinuz 和 casper/initrd。"
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
    return row


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
    required = {
        "pe/hotpe/wimboot",
        "pe/hotpe/bootmgr",
        "pe/hotpe/BCD",
        "pe/hotpe/boot.sdi",
        "pe/hotpe/boot.wim",
    }
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
        base = rel_path.split("/casper/", 1)[0] if "/casper/" in rel_path else rel_path.rsplit("/", 1)[0]
        entry = entries.setdefault(base, {"base": base, "iso": None, "kernel": None, "initrd": None})
        if rel_path.lower().endswith(".iso"):
            entry["iso"] = rel_path
        elif rel_path.endswith("/casper/vmlinuz"):
            entry["kernel"] = rel_path
        elif rel_path.endswith("/casper/initrd"):
            entry["initrd"] = rel_path
    return [
        entry
        for entry in entries.values()
        if entry.get("iso") and entry.get("kernel") and entry.get("initrd")
    ]


def windows_hotpe_available(rows: list[dict]) -> bool:
    return hotpe_menu_ready(rows) and any(
        row_enabled(row)
        and row.get("category") == "windows"
        and row.get("boot_readiness") == "needs_hotpe"
        for row in rows
    )


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


def write_menu(_rows: list[dict] | None = None) -> str:
    ensure_dirs()
    rows = menu_rows(_rows)
    hotpe_ready = hotpe_menu_ready(rows)
    linux_entries = linux_boot_entries(rows)
    windows_ready = windows_hotpe_available(rows)
    lines = [
        "#!ipxe",
        "",
        f"set server-ip {SERVER_IP}",
        f"set base-url http://${{server-ip}}:{SYNABOOT_PORT}",
        "set boot-url ${base-url}/boot",
        "set image-url ${base-url}/images",
        "",
        ":start",
        "menu SynaBoot Phase 2 - HTTP/iPXE Boot",
    ]
    if hotpe_ready:
        lines.extend(["item --gap --          === PE / Recovery ===", "item hotpe            HotPE via wimboot"])
    if linux_entries:
        lines.append("item --gap --          === Linux ===")
        for entry in linux_entries:
            label = f"linux_{ipxe_label(entry['base'])}"
            entry["label"] = label
            lines.append(f"item {label:<16} Linux installer - {ipxe_text(entry['base'])}")
    if windows_ready:
        lines.extend(["item --gap --          === Windows ===", "item windows_hotpe    Windows installation via HotPE"])
    lines.extend(
        [
            "item --gap --          === Tools ===",
            "item shell            iPXE shell",
            "item reboot           Reboot",
            "item poweroff         Power off",
        ]
    )
    default_target = "hotpe" if hotpe_ready else (linux_entries[0]["label"] if linux_entries else "shell")
    lines.extend(
        [
            f"choose --default {default_target} --timeout 15000 target && goto ${{target}} || goto start",
            "",
            ":hotpe",
        ]
    )
    if hotpe_ready:
        lines.extend(
            [
                "echo Loading HotPE...",
                "kernel ${image-url}/pe/hotpe/wimboot",
                "initrd ${image-url}/pe/hotpe/bootmgr bootmgr",
                "initrd ${image-url}/pe/hotpe/BCD BCD",
                "initrd ${image-url}/pe/hotpe/boot.sdi boot.sdi",
                "initrd ${image-url}/pe/hotpe/boot.wim boot.wim",
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
                ":windows_hotpe",
                "echo Windows ISO/WIM/ESD should be installed from HotPE.",
                "echo Boot HotPE, then open ${image-url}/windows/.",
                "goto hotpe",
            ]
        )
    for entry in linux_entries:
        lines.extend(
            [
                "",
                f":{entry['label']}",
                f"echo Loading Linux installer from {ipxe_text(entry['base'])}...",
                f"kernel ${{base-url}}/images/{ipxe_url_path(entry['kernel'])} ip=dhcp url=${{base-url}}/images/{ipxe_url_path(entry['iso'])} ---",
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
            "echo Boot failed. Press any key to return to menu.",
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

:start
menu SynaBoot Phase 2 - HTTP/iPXE Boot
item --gap --          === No ready images ===
item shell iPXE shell
item reboot Reboot
item poweroff Power off
choose --default shell --timeout 15000 target && goto ${{target}} || goto start

:shell
shell
goto start

:reboot
reboot

:poweroff
poweroff

:boot_failed
echo Boot failed. Press any key to return to menu.
prompt
goto start
"""


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
        ["bsdtar", "7z", "extract-iso9660-file.py"]
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
    tools = []
    for name in ("bsdtar", "7z"):
        tools.append(
            {
                "name": name,
                "available": shutil.which(name) is not None,
                "purpose": "读取 ISO 内容并提取启动依赖",
            }
        )
    return tools


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

for artifact in "$CASPER_DIR/vmlinuz" "$CASPER_DIR/initrd"; do
  [[ ! -e "$artifact" ]] || fail "目标文件已存在，拒绝覆盖: ${artifact#$ROOT_DIR/}"
done

if command -v bsdtar >/dev/null 2>&1; then
  bsdtar -C "$WORK" -xf "$SOURCE" casper/vmlinuz casper/initrd
elif command -v 7z >/dev/null 2>&1; then
  7z x -y -o"$WORK" "$SOURCE" casper/vmlinuz casper/initrd >/dev/null
else
  fail "未找到 bsdtar 或 7z。请先由管理员安装并审查解包工具。"
fi

EXTRACTED_VMLINUX="$WORK/casper/vmlinuz"
EXTRACTED_INITRD="$WORK/casper/initrd"
for extracted in "$EXTRACTED_VMLINUX" "$EXTRACTED_INITRD"; do
  [[ -e "$extracted" ]] || fail "ISO 内缺少预期文件: ${extracted#$WORK/}"
  [[ ! -L "$extracted" ]] || fail "ISO 解包结果是 symlink，拒绝复制: ${extracted#$WORK/}"
  [[ -f "$extracted" ]] || fail "ISO 解包结果不是普通文件，拒绝复制: ${extracted#$WORK/}"
done

mkdir -p "$CASPER_DIR"
[[ ! -L "$CASPER_DIR" ]] || fail "目标 casper 目录是 symlink，拒绝写入"
VMLINUX_TARGET="$(canonical_child_path "$ROOT_DIR/data/images" "$CASPER_DIR/vmlinuz")" || fail "vmlinuz 目标路径越界"
INITRD_TARGET="$(canonical_child_path "$ROOT_DIR/data/images" "$CASPER_DIR/initrd")" || fail "initrd 目标路径越界"
[[ ! -e "$VMLINUX_TARGET" ]] || fail "目标文件已存在，拒绝覆盖: ${VMLINUX_TARGET#$ROOT_DIR/}"
[[ ! -e "$INITRD_TARGET" ]] || fail "目标文件已存在，拒绝覆盖: ${INITRD_TARGET#$ROOT_DIR/}"
cp "$EXTRACTED_VMLINUX" "$VMLINUX_TARGET"
cp "$EXTRACTED_INITRD" "$INITRD_TARGET"
printf 'APPROVED: 已提取 casper/vmlinuz 和 casper/initrd\\n'
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
    return f"""# Ubuntu/Linux ISO kernel/initrd 准备任务

任务 ID: {job_id}

源 ISO:

```text
data/images/{source['relative_path']}
```

目标输出:

```text
data/images/{source['target_dir']}/casper/vmlinuz
data/images/{source['target_dir']}/casper/initrd
```

安全边界:

- 原始 ISO 只读，不删除、不改写。
- 如果目标文件已存在，`prepare.sh` 会直接拒绝覆盖。
- 只使用本机已存在的 `bsdtar` 或 `7z`，不会自动安装新依赖。
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
            "For Linux ISO files, run scripts/image-factory/prepare-linux-boot-artifacts.sh; it prefers bsdtar/7z and falls back to the built-in ISO9660 extractor.",
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
        elif path == "/api/images":
            json_response(self, 200, {"images": list_images()})
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
        if not self.require_admin():
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

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)


def main() -> None:
    ensure_dirs()
    connect_db().close()
    server = ThreadingHTTPServer((API_HOST, API_PORT), Handler)
    print(f"SynaBoot API listening on {API_HOST}:{API_PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
