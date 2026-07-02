#!/usr/bin/env python3
"""安全导入管理员已审核的 wimboot 到 HotPE 镜像目录。

脚本只接受本地文件，复制到 data/images/pe/hotpe/wimboot，并在非公开
data/metadata 中记录 provenance。
它不下载、不执行 wimboot，也不启用 DHCP、ProxyDHCP、TFTP 或任何网络服务。
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
HOTPE_ROOT = ROOT / "data" / "images" / "pe" / "hotpe"
METADATA_ROOT = ROOT / "data" / "metadata" / "wimboot-provenance"
TARGET = HOTPE_ROOT / "wimboot"
METADATA = METADATA_ROOT / "wimboot.json"
COPY_CHUNK_SIZE = 1024 * 1024
MAX_WIMBOOT_BYTES = 16 * 1024 * 1024


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


def validate_source(source_fd: int, source_label: str) -> os.stat_result:
    source_stat = os.fstat(source_fd)
    if not stat.S_ISREG(source_stat.st_mode):
        fail(f"源文件不是普通文件: {source_label}")
    if source_stat.st_size <= 0:
        fail("wimboot 源文件为空")
    if source_stat.st_size > MAX_WIMBOOT_BYTES:
        fail(f"wimboot 源文件过大: {source_stat.st_size} > {MAX_WIMBOOT_BYTES}")
    header = os.pread(source_fd, 2, 0)
    if header not in {b"MZ", b"\xeb\x3c", b"\xeb\x4c"}:
        fail("wimboot 文件头不符合预期，请确认来源")
    return source_stat


def sha256_source_fd(source_fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(source_fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(source_fd, COPY_CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


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
    parser = argparse.ArgumentParser(description="导入本地已审核 wimboot")
    parser.add_argument("source", help="本地 wimboot 源文件路径")
    parser.add_argument("--reviewed-by", default="local-admin", help="审核人或责任人标识，不写 token/密码")
    parser.add_argument("--source-label", default="official-ipxe-wimboot", help="来源说明")
    parser.add_argument("--source-version", default="", help="可复核版本、release 或 commit")
    parser.add_argument("--source-url", default="", help="可复核来源 URL；脚本不会访问该 URL")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser()
    HOTPE_ROOT.mkdir(parents=True, exist_ok=True)
    METADATA_ROOT.mkdir(parents=True, exist_ok=True)
    ensure_no_symlink_chain(HOTPE_ROOT)
    ensure_no_symlink_chain(METADATA_ROOT)
    ensure_inside(TARGET, HOTPE_ROOT, "wimboot target")
    ensure_inside(METADATA, METADATA_ROOT, "wimboot metadata")
    if TARGET.exists() or TARGET.is_symlink():
        fail(f"目标 wimboot 已存在，禁止覆盖: {TARGET}")
    if METADATA.exists() or METADATA.is_symlink():
        fail(f"目标 metadata 已存在，禁止覆盖: {METADATA}")

    source_fd = open_source_no_follow(source)
    try:
        source_stat = validate_source(source_fd, str(source))
        source_sha256 = sha256_source_fd(source_fd)
        target_sha256 = copy_fd_no_overwrite(source_fd, TARGET)
        if source_sha256 != target_sha256:
            if TARGET.exists() and TARGET.is_file() and not TARGET.is_symlink():
                TARGET.unlink()
            fail("复制后 SHA256 与源文件不一致")
    finally:
        os.close(source_fd)

    payload = {
        "schema_version": "synaboot.wimboot-provenance.v1",
        "relative_path": "data/images/pe/hotpe/wimboot",
        "sha256": target_sha256,
        "source_sha256": source_sha256,
        "size_bytes": TARGET.stat().st_size,
        "source_name": source.name,
        "source_size_bytes": source_stat.st_size,
        "source_label": args.source_label,
        "source_version": args.source_version,
        "source_url": args.source_url,
        "reviewed_by": args.reviewed_by,
        "review_status": "local_admin_approved_pending_client_boot_test",
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "network_services_enabled": False,
        "dhcp_enabled": False,
        "proxydhcp_enabled": False,
        "tftp_enabled": False,
    }
    write_metadata_no_overwrite(METADATA, payload)
    print(f"IMPORTED: {TARGET.relative_to(ROOT)}")
    print(f"METADATA: {METADATA.relative_to(ROOT)}")
    print(f"SHA256: {target_sha256}")
    print("NEXT: 运行 scripts/image-factory/prepare-hotpe-boot-artifacts.sh 并重新扫描镜像。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as exc:
        fail(str(exc))
