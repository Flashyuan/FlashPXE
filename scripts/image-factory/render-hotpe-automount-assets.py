#!/usr/bin/env python3
"""生成 HotPE 自动挂载 SMB 和模块加载运行时资产。

该脚本只写入本机运行数据目录，不执行 Windows/HotPE 命令，不修改 boot.wim。
含 SMB 密码的脚本只能生成到 data/secrets，下游需要由管理员手动注入 HotPE
或在实验环境中按受控方式调用。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = ROOT / "scripts" / "image-factory" / "templates" / "hotpe"
SECRETS_ROOT = ROOT / "data" / "secrets" / "hotpe" / "automount"
PUBLIC_AUTOMOUNT_ROOT = ROOT / "data" / "images" / "pe" / "hotpe" / "runtime" / "AutoMount"
HOTPE_MODULE_ROOT = ROOT / "data" / "images" / "pe" / "hotpe" / "runtime" / "HotProgMods"
BOOT_WIM = ROOT / "data" / "images" / "pe" / "hotpe" / "boot.wim"

SAFE_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._$ -]{1,80}$")
SAFE_USER_RE = re.compile(r"^[A-Za-z0-9._@+\\/-]{1,128}$")
SAFE_PASSWORD_RE = re.compile(r"^[^%!\"&|<>`^\r\n]{1,256}$")
SAFE_HPM_RE = re.compile(r"^[^\\/:*?\"<>|\r\n]{1,180}\.HPM$", re.IGNORECASE)


def fail(message: str) -> None:
    print(f"BLOCKED: {message}", file=sys.stderr)
    raise SystemExit(1)


def info(message: str) -> None:
    print(f"INFO: {message}")


def env_value(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def require_safe(label: str, value: str, pattern: re.Pattern[str]) -> str:
    if not value:
        fail(f"{label} 不能为空")
    if not pattern.fullmatch(value):
        fail(f"{label} 包含不允许的字符")
    return value


def ensure_child(parent: Path, child: Path, label: str) -> Path:
    parent_real = parent.resolve()
    child_parent = child.parent.resolve()
    if parent_real != child_parent and parent_real not in child_parent.parents:
        fail(f"{label} 越界")
    return child


def ensure_not_symlink(path: Path, label: str) -> None:
    current = path
    checks = [current, *current.parents]
    root = ROOT.resolve()
    for item in checks:
        try:
            resolved = item.resolve()
        except FileNotFoundError:
            continue
        if root != resolved and root not in resolved.parents:
            break
        if item.exists() and item.is_symlink():
            fail(f"{label} 禁止经过 symlink: {item}")


def sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_template(name: str) -> str:
    path = ensure_child(TEMPLATE_ROOT, TEMPLATE_ROOT / name, "模板路径")
    return path.read_text(encoding="utf-8")


def module_names() -> list[str]:
    if not HOTPE_MODULE_ROOT.is_dir():
        return []
    names = []
    for item in sorted(HOTPE_MODULE_ROOT.iterdir(), key=lambda entry: entry.name.lower()):
        if item.is_file() and SAFE_HPM_RE.fullmatch(item.name):
            names.append(item.name)
    return names


def write_secret_file(path: Path, content: str) -> None:
    ensure_child(SECRETS_ROOT, path, "secret 输出路径")
    ensure_not_symlink(path, "secret 输出路径")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(content)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def write_public_file(path: Path, content: str) -> None:
    ensure_child(PUBLIC_AUTOMOUNT_ROOT, path, "public 输出路径")
    ensure_not_symlink(path, "public 输出路径")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    os.chmod(path, 0o644)


def render() -> dict:
    host = require_safe("SYNABOOT_HOTPE_SMB_HOST", env_value("SYNABOOT_HOTPE_SMB_HOST", "10.101.8.135"), SAFE_HOST_RE)
    user = require_safe("SYNABOOT_HOTPE_SMB_USER", env_value("SYNABOOT_HOTPE_SMB_USER", "synaboot"), SAFE_USER_RE)
    password = require_safe("SYNABOOT_HOTPE_SMB_PASSWORD", env_value("SYNABOOT_HOTPE_SMB_PASSWORD"), SAFE_PASSWORD_RE)
    images_share = require_safe(
        "SYNABOOT_HOTPE_SMB_IMAGES_SHARE",
        env_value("SYNABOOT_HOTPE_SMB_IMAGES_SHARE", "synaboot-images"),
        SAFE_NAME_RE,
    )
    modules_share = require_safe(
        "SYNABOOT_HOTPE_SMB_MODULES_SHARE",
        env_value("SYNABOOT_HOTPE_SMB_MODULES_SHARE", "hotpe-mods"),
        SAFE_NAME_RE,
    )
    windows_share = require_safe(
        "SYNABOOT_HOTPE_SMB_WINDOWS_SHARE",
        env_value("SYNABOOT_HOTPE_SMB_WINDOWS_SHARE", "win11"),
        SAFE_NAME_RE,
    )

    before_boot_wim = sha256_file(BOOT_WIM)
    modules = module_names()
    load_lines = []
    for name in modules:
        escaped = name.replace("%", "%%")
        load_lines.append(f'if exist "M:\\{escaped}" start "" "M:\\{escaped}"')
    if not load_lines:
        load_lines.append("echo [WARN] No reviewed HotPE HPM modules were found on M:.")

    mount_content = load_template("mount-synaboot-shares.cmd.tpl")
    replacements = {
        "{{SMB_HOST}}": host,
        "{{SMB_USER}}": user,
        "{{SMB_PASSWORD}}": password,
        "{{IMAGES_SHARE}}": images_share,
        "{{MODULES_SHARE}}": modules_share,
        "{{WINDOWS_SHARE}}": windows_share,
    }
    for token, value in replacements.items():
        mount_content = mount_content.replace(token, value)

    loader_content = load_template("load-hotpe-modules.cmd.tpl").replace("{{MODULE_LOAD_LINES}}", "\n".join(load_lines))

    write_secret_file(SECRETS_ROOT / "mount-synaboot-shares.cmd", mount_content)
    write_secret_file(SECRETS_ROOT / "load-hotpe-modules.cmd", loader_content)

    manifest = {
        "schema_version": "synaboot.hotpe-automount.v1",
        "runtime_only": True,
        "secret_files_gitignored": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "smb_host": host,
        "shares": {
            "images": images_share,
            "modules": modules_share,
            "windows": windows_share,
        },
        "drive_plan": {
            "Z:": f"\\\\{host}\\{images_share}",
            "M:": f"\\\\{host}\\{modules_share}",
            "W:": f"\\\\{host}\\{windows_share}",
        },
        "module_load_level": "level1_open_reviewed_hpm_files",
        "module_count": len(modules),
        "modules": modules,
        "boot_wim_sha256_before": before_boot_wim,
        "boot_wim_sha256_after": sha256_file(BOOT_WIM),
        "secret_output_dir": "data/secrets/hotpe/automount",
        "public_output_dir": "data/images/pe/hotpe/runtime/AutoMount",
    }
    write_public_file(PUBLIC_AUTOMOUNT_ROOT / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    write_public_file(
        PUBLIC_AUTOMOUNT_ROOT / "README.txt",
        "\n".join(
            [
                "SynaBoot HotPE AutoMount public marker.",
                "",
                "This directory intentionally contains no SMB password.",
                "Runtime scripts with credentials are generated under data/secrets/hotpe/automount.",
                "Copy those runtime scripts into HotPE only inside the controlled lab flow.",
                "",
            ]
        ),
    )

    if manifest["boot_wim_sha256_before"] != manifest["boot_wim_sha256_after"]:
        fail("boot.wim sha256 changed during render")
    return manifest


def main() -> int:
    if not env_value("SYNABOOT_HOTPE_SMB_PASSWORD"):
        fail("必须设置 SYNABOOT_HOTPE_SMB_PASSWORD，脚本不会生成空密码挂载资产")
    manifest = render()
    info("hotpe_automount_assets=rendered")
    info(f"smb_host={manifest['smb_host']}")
    info(f"module_count={manifest['module_count']}")
    info("secret_output_dir=data/secrets/hotpe/automount")
    info("public_output_dir=data/images/pe/hotpe/runtime/AutoMount")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
