#!/usr/bin/env python3
"""安全导入管理员已审核的 iPXE loader。

该脚本只接受本地文件，复制到 data/boot/loaders 固定白名单文件名，并在
data/boot/loader-metadata 记录来源与 hash。它不下载、不生成、不执行 loader，
也不启用 DHCP、ProxyDHCP、TFTP 或任何网络服务。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA_BOOT = ROOT / "data" / "boot"
LOADER_ROOT = DATA_BOOT / "loaders"
METADATA_ROOT = DATA_BOOT / "loader-metadata"
COPY_CHUNK_SIZE = 1024 * 1024

ALLOWED_LOADERS = {
    "ipxe.efi": {"max_bytes": 16 * 1024 * 1024, "magic": "pe", "loader_type": "uefi-efi", "usage": "UEFI HTTP Boot / UEFI PXE IPv4 chainload", "transport": ["http", "future-tftp"]},
    "snponly.efi": {"max_bytes": 16 * 1024 * 1024, "magic": "pe", "loader_type": "uefi-efi", "usage": "UEFI PXE IPv4 chainload using firmware SNP driver", "transport": ["future-tftp"]},
    "undionly.kpxe": {"max_bytes": 16 * 1024 * 1024, "magic": "any", "loader_type": "bios-pxe", "usage": "Legacy BIOS PXE chainload", "transport": ["future-tftp"]},
    "ipxe.iso": {"max_bytes": 128 * 1024 * 1024, "magic": "iso9660", "loader_type": "bootable-iso", "usage": "Manual iPXE ISO boot media", "transport": ["removable-media"]},
}


def fail(message: str) -> None:
    raise SystemExit(f"BLOCKED: {message}")


def ensure_no_symlink_chain(path: Path) -> None:
    current = path if path.exists() else path.parent
    for candidate in [current, *current.parents]:
        if candidate == candidate.parent:
            break
        if candidate.is_symlink():
            fail(f"路径父级包含 symlink: {candidate}")


def ensure_inside(path: Path, root: Path, label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        fail(f"{label} 越出允许根目录: {path}")


def open_source_no_follow(source: Path) -> int:
    if source.is_symlink():
        fail(f"源文件不能是 symlink: {source}")
    ensure_no_symlink_chain(source)
    if not source.exists():
        fail(f"源文件不存在: {source}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(source, flags)


def validate_source_fd(source_fd: int, filename: str, source_label: str) -> os.stat_result:
    source_stat = os.fstat(source_fd)
    if not stat.S_ISREG(source_stat.st_mode):
        fail(f"源文件不是普通文件: {source_label}")
    if source_stat.st_size <= 0:
        fail("源文件为空")
    max_bytes = ALLOWED_LOADERS[filename]["max_bytes"]
    if source_stat.st_size > max_bytes:
        fail(f"源文件过大: {source_stat.st_size} > {max_bytes}")
    return source_stat


def validate_pe_file(source_fd: int) -> None:
    header = os.pread(source_fd, 0x40, 0)
    if len(header) < 0x40 or header[:2] != b"MZ":
        fail("EFI loader 必须是 PE/COFF 文件，缺少 MZ 头")
    pe_offset = int.from_bytes(header[0x3C:0x40], "little")
    if pe_offset <= 0 or pe_offset > 1024 * 1024:
        fail("EFI loader PE header offset 异常")
    if os.pread(source_fd, 4, pe_offset) != b"PE\0\0":
        fail("EFI loader 缺少 PE 签名")


def validate_iso9660_file(source_fd: int) -> None:
    if os.pread(source_fd, 5, 0x8001) != b"CD001":
        fail("ipxe.iso 必须包含 ISO9660 CD001 标识")


def validate_magic(source_fd: int, filename: str) -> None:
    magic = ALLOWED_LOADERS[filename]["magic"]
    if magic == "pe":
        validate_pe_file(source_fd)
    elif magic == "iso9660":
        validate_iso9660_file(source_fd)


def copy_fd_no_overwrite(source_fd: int, target: Path) -> str:
    digest = hashlib.sha256()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.lseek(source_fd, 0, os.SEEK_SET)
        with os.fdopen(fd, "wb") as dst:
            fd = -1
            while True:
                chunk = os.read(source_fd, COPY_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
                dst.write(chunk)
    except Exception:
        if fd >= 0:
            os.close(fd)
        if target.exists() and target.is_file() and not target.is_symlink():
            target.unlink()
        raise
    os.chmod(target, 0o644)
    return digest.hexdigest()


def sha256_source_fd(source_fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(source_fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(source_fd, COPY_CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def write_metadata_no_overwrite(path: Path, payload: dict) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(encoded)
            handle.write(b"\n")
    except Exception:
        if fd >= 0:
            os.close(fd)
        if path.exists() and path.is_file() and not path.is_symlink():
            path.unlink()
        raise
    os.chmod(path, 0o644)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入本地已审核 iPXE loader")
    parser.add_argument("source", help="本地源文件路径")
    parser.add_argument("filename", choices=sorted(ALLOWED_LOADERS), help="目标白名单文件名")
    parser.add_argument("--reviewed-by", default="local-admin", help="审核人或责任人标识，不写 token/密码")
    parser.add_argument("--source-label", default="local-admin-provided", help="来源说明，例如 internal-build 或 official-ipxe")
    parser.add_argument("--source-version", default="", help="可复核版本、commit 或构建编号")
    parser.add_argument("--source-url", default="", help="可复核来源 URL，可留空；脚本不会访问该 URL")
    return parser.parse_args()


def import_loader_file(
    source: Path,
    filename: str,
    reviewed_by: str,
    source_label: str,
    source_version: str = "",
    source_url: str = "",
    provenance_extra: dict | None = None,
) -> tuple[Path, Path, str]:
    LOADER_ROOT.mkdir(parents=True, exist_ok=True)
    METADATA_ROOT.mkdir(parents=True, exist_ok=True)
    ensure_no_symlink_chain(DATA_BOOT)
    ensure_no_symlink_chain(LOADER_ROOT)
    ensure_no_symlink_chain(METADATA_ROOT)

    target = LOADER_ROOT / filename
    metadata_path = METADATA_ROOT / f"{filename}.json"
    ensure_inside(target, LOADER_ROOT, "loader target")
    ensure_inside(metadata_path, METADATA_ROOT, "loader metadata")

    if target.exists() or target.is_symlink():
        fail(f"目标 loader 已存在，禁止覆盖: {target}")
    if metadata_path.exists() or metadata_path.is_symlink():
        fail(f"目标 metadata 已存在，禁止覆盖: {metadata_path}")

    source_fd = open_source_no_follow(source)
    try:
        source_stat = validate_source_fd(source_fd, filename, str(source))
        validate_magic(source_fd, filename)
        source_sha256 = sha256_source_fd(source_fd)

        sha256 = copy_fd_no_overwrite(source_fd, target)
        if sha256 != source_sha256:
            if target.exists() and target.is_file() and not target.is_symlink():
                target.unlink()
            fail("复制后 SHA256 与源文件不一致")
        target_stat = target.stat()
        loader_spec = ALLOWED_LOADERS[filename]
        payload = {
            "schema_version": "synaboot.loader-provenance.v1",
            "filename": filename,
            "relative_path": f"data/boot/loaders/{filename}",
            "metadata_path": f"data/boot/loader-metadata/{filename}.json",
            "sha256": sha256,
            "source_sha256": source_sha256,
            "size_bytes": target_stat.st_size,
            "mtime_ns": target_stat.st_mtime_ns,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "source_path": str(source.resolve()),
            "source_name": source.name,
            "source_size_bytes": source_stat.st_size,
            "source_label": source_label,
            "source_version": source_version,
            "source_url": source_url,
            "reviewed_by": reviewed_by,
            "review_status": "local_admin_approved_pending_isolated_boot_test",
            "loader_type": loader_spec["loader_type"],
            "expected_usage": loader_spec["usage"],
            "phase_availability": "available_for_manual_or_future_phase3",
            "phase3_status": "blocked",
            "transport": loader_spec["transport"],
            "filename_allowlist_matched": True,
            "target_regular_file": True,
            "target_inside_loader_root": True,
            "metadata_written": True,
            "secure_boot_risk_acknowledged": filename.endswith(".efi") or filename == "ipxe.iso",
            "network_services_enabled": False,
            "tftp_enabled": False,
            "proxydhcp_enabled": False,
            "dhcp_enabled": False,
        }
        if provenance_extra:
            payload.update(provenance_extra)
        write_metadata_no_overwrite(metadata_path, payload)
    except Exception:
        if target.exists() and target.is_file() and not target.is_symlink():
            target.unlink()
        raise
    finally:
        os.close(source_fd)
    return target, metadata_path, sha256


def main() -> int:
    args = parse_args()
    filename = args.filename
    source = Path(args.source).expanduser()

    target, metadata_path, sha256 = import_loader_file(
        source=source,
        filename=filename,
        reviewed_by=args.reviewed_by,
        source_label=args.source_label,
        source_version=args.source_version,
        source_url=args.source_url,
    )

    print(f"IMPORTED: {target.relative_to(ROOT)}")
    print(f"METADATA: {metadata_path.relative_to(ROOT)}")
    print(f"SHA256: {sha256}")
    print("NEXT: 重新查看 /api/boot-assets；Phase 3 网络服务仍保持禁用。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as exc:
        fail(str(exc))
