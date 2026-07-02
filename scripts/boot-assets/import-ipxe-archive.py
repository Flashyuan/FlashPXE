#!/usr/bin/env python3
"""从本地 iPXE 归档导入已审核 loader。

该脚本不下载归档，只从管理员提供的本地 `ipxeboot.tar.gz` 或等价归档中
读取固定白名单成员，并复用 `import-loader.py` 的本地导入校验与 provenance
记录逻辑。
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import stat
import sys
import tarfile
import tempfile
from pathlib import Path


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
BUILDS_ROOT = ROOT / "data" / "builds" / "loader-archive-import"
IMPORT_LOADER_PATH = ROOT / "scripts" / "boot-assets" / "import-loader.py"
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024

ARCHIVE_MEMBER_CANDIDATES = {
    "ipxe.efi": [
        "ipxeboot/x86_64-sb/ipxe.efi",
        "ipxeboot/x86_64-efi/ipxe.efi",
        "x86_64-efi-sb/ipxe.efi",
        "x86_64-efi/ipxe.efi",
    ],
    "snponly.efi": [
        "ipxeboot/x86_64-sb/snponly.efi",
        "ipxeboot/x86_64-efi/snponly.efi",
        "x86_64-efi-sb/snponly.efi",
        "x86_64-efi/snponly.efi",
    ],
    "undionly.kpxe": [
        "ipxeboot/x86_64-pcbios/undionly.kpxe",
        "x86_64-pcbios/undionly.kpxe",
        "undionly.kpxe",
    ],
    "ipxe.iso": [
        "ipxe.iso",
        "ipxeboot/ipxe.iso",
    ],
}


def fail(message: str) -> None:
    raise SystemExit(f"BLOCKED: {message}")


def load_import_loader_module():
    spec = importlib.util.spec_from_file_location("synaboot_import_loader", IMPORT_LOADER_PATH)
    if spec is None or spec.loader is None:
        fail(f"无法加载导入模块: {IMPORT_LOADER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ensure_no_symlink_chain(path: Path) -> None:
    current = path if path.exists() else path.parent
    for candidate in [current, *current.parents]:
        if candidate == candidate.parent:
            break
        if candidate.is_symlink():
            fail(f"路径父级包含 symlink: {candidate}")


def open_archive_no_follow(path: Path) -> int:
    if path.is_symlink():
        fail(f"归档不能是 symlink: {path}")
    ensure_no_symlink_chain(path)
    if not path.exists():
        fail(f"归档不存在: {path}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(path, flags)


def validate_archive_fd(archive_fd: int, archive_label: str) -> os.stat_result:
    archive_stat = os.fstat(archive_fd)
    if not stat.S_ISREG(archive_stat.st_mode):
        fail(f"归档不是普通文件: {archive_label}")
    if archive_stat.st_size <= 0:
        fail("归档为空")
    if archive_stat.st_size > MAX_ARCHIVE_BYTES:
        fail(f"归档过大: {archive_stat.st_size} > {MAX_ARCHIVE_BYTES}")
    return archive_stat


def choose_member(archive: tarfile.TarFile, filename: str) -> tarfile.TarInfo:
    allowed = set(ARCHIVE_MEMBER_CANDIDATES[filename])
    for member in archive:
        if member.name in allowed:
            validate_member(member, filename)
            return member
    fail(f"归档中找不到允许的 {filename} 成员")


def validate_member(member: tarfile.TarInfo, filename: str) -> None:
    if member.name.startswith("/") or ".." in Path(member.name).parts:
        fail(f"归档成员路径非法: {member.name}")
    if not member.isfile():
        fail(f"归档成员不是普通文件: {member.name}")
    if not member.name.endswith(f"/{filename}") and member.name != filename:
        fail(f"归档成员文件名不匹配: {member.name}")
    if member.size <= 0:
        fail(f"归档成员为空: {member.name}")
    if member.size > MAX_MEMBER_BYTES:
        fail(f"归档成员过大: {member.size} > {MAX_MEMBER_BYTES}")


def extract_member_to_temp(archive: tarfile.TarFile, member: tarfile.TarInfo, work_dir: Path) -> Path:
    source = archive.extractfile(member)
    if source is None:
        fail(f"无法读取归档成员: {member.name}")
    target = work_dir / Path(member.name).name
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    remaining = member.size
    try:
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            while remaining > 0:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    fail("归档成员读取提前结束")
                remaining -= len(chunk)
                handle.write(chunk)
    finally:
        if fd >= 0:
            os.close(fd)
        source.close()
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从本地 iPXE 归档导入 loader")
    parser.add_argument("archive", help="本地 ipxeboot.tar.gz 或等价归档路径")
    parser.add_argument("filename", choices=sorted(ARCHIVE_MEMBER_CANDIDATES), help="目标白名单文件名")
    parser.add_argument("--reviewed-by", default="local-admin", help="审核人或责任人标识")
    parser.add_argument("--source-label", default="official-ipxe-local-archive", help="来源说明")
    parser.add_argument("--source-version", default="", help="可复核版本、release 或 commit")
    parser.add_argument("--source-url", default="https://github.com/ipxe/ipxe/releases/latest/download/ipxeboot.tar.gz", help="归档来源 URL 记录；脚本不会访问该 URL")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    archive_path = Path(args.archive).expanduser()
    BUILDS_ROOT.mkdir(parents=True, exist_ok=True)
    ensure_no_symlink_chain(BUILDS_ROOT)
    import_loader = load_import_loader_module()

    with tempfile.TemporaryDirectory(prefix="ipxe-archive-", dir=BUILDS_ROOT) as temp_dir:
        work_dir = Path(temp_dir)
        archive_fd = open_archive_no_follow(archive_path)
        validate_archive_fd(archive_fd, str(archive_path))
        try:
            with os.fdopen(archive_fd, "rb") as archive_file:
                archive_fd = -1
                with tarfile.open(fileobj=archive_file, mode="r:*") as archive:
                    member = choose_member(archive, args.filename)
                    temp_loader = extract_member_to_temp(archive, member, work_dir)
        finally:
            if archive_fd >= 0:
                os.close(archive_fd)
        target, metadata_path, sha256 = import_loader.import_loader_file(
            source=temp_loader,
            filename=args.filename,
            reviewed_by=args.reviewed_by,
            source_label=args.source_label,
            source_version=args.source_version,
            source_url=args.source_url,
            provenance_extra={
                "archive_path": str(archive_path.resolve()),
                "archive_name": archive_path.name,
                "archive_member": member.name,
                "archive_imported": True,
            },
        )

    print(f"IMPORTED: {target.relative_to(ROOT)}")
    print(f"METADATA: {metadata_path.relative_to(ROOT)}")
    print(f"SHA256: {sha256}")
    print("NEXT: 重新查看 /api/boot-assets；Phase 3 网络服务仍保持禁用。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, tarfile.TarError) as exc:
        fail(str(exc))
