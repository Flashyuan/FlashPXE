#!/usr/bin/env python3
"""从 ISO9660 镜像中只读提取单个文件。

该工具只服务于 SynaBoot 的启动依赖准备：
从可信放置在 data/images 下的 ISO 中提取白名单内的启动文件。
它不挂载 ISO，不写目标文件以外路径，不解析或执行 ISO 内脚本。
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path


SECTOR_SIZE = 2048
MAX_EXTRACT_BYTES = {
    "vmlinuz": 128 * 1024 * 1024,
    "initrd": 1024 * 1024 * 1024,
    "bootmgr": 64 * 1024 * 1024,
    "bootmgfw.efi": 64 * 1024 * 1024,
    "bootx64.efi": 64 * 1024 * 1024,
    "bcd": 16 * 1024 * 1024,
    "boot.sdi": 256 * 1024 * 1024,
    "boot.wim": 8 * 1024 * 1024 * 1024,
    "install_sources.yaml": 16 * 1024 * 1024,
    "casper-uuid": 16 * 1024 * 1024,
    "casper-uuid-generic": 16 * 1024 * 1024,
    "casper_uuid_generic": 16 * 1024 * 1024,
    "info": 16 * 1024 * 1024,
}
COPY_CHUNK_SIZE = 1024 * 1024
MAX_DIRECTORY_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class IsoRecord:
    name: str
    extent: int
    size: int
    is_dir: bool


def fail(message: str) -> None:
    print(f"BLOCKED: {message}", file=sys.stderr)
    raise SystemExit(1)


def normalize_iso_name(raw: bytes) -> str:
    if raw == b"\x00":
        return "."
    if raw == b"\x01":
        return ".."
    try:
        name = raw.decode("ascii")
    except UnicodeDecodeError:
        fail("ISO 目录记录包含非 ASCII 文件名，当前安全提取器不处理该情况")
    if ";" in name:
        name = name.split(";", 1)[0]
    return name.rstrip(".").lower()


def parse_record(record: bytes) -> IsoRecord:
    if len(record) < 34:
        fail("ISO 目录记录过短")
    name_len = record[32]
    name_start = 33
    name_end = name_start + name_len
    if name_end > len(record):
        fail("ISO 目录记录文件名越界")
    return IsoRecord(
        name=normalize_iso_name(record[name_start:name_end]),
        extent=int.from_bytes(record[2:6], "little"),
        size=int.from_bytes(record[10:14], "little"),
        is_dir=bool(record[25] & 0x02),
    )


def validate_extent(extent: int, size: int, iso_size: int | None = None) -> None:
    if extent <= 0 or size < 0:
        fail("ISO extent 或 size 异常")
    if iso_size is not None and extent * SECTOR_SIZE + size > iso_size:
        fail("ISO extent 越界，镜像可能异常或损坏")


def read_extent(handle, extent: int, size: int, iso_size: int | None = None) -> bytes:
    validate_extent(extent, size, iso_size)
    handle.seek(extent * SECTOR_SIZE)
    data = handle.read(size)
    if len(data) != size:
        fail("读取 ISO extent 失败，镜像可能不完整")
    return data


def iter_directory(handle, record: IsoRecord, iso_size: int | None = None) -> list[IsoRecord]:
    if record.size > MAX_DIRECTORY_BYTES:
        fail("ISO 目录超过安全大小上限，拒绝读取")
    data = read_extent(handle, record.extent, record.size, iso_size)
    entries: list[IsoRecord] = []
    pos = 0
    while pos < len(data):
        length = data[pos]
        if length == 0:
            pos = ((pos // SECTOR_SIZE) + 1) * SECTOR_SIZE
            continue
        raw_record = data[pos : pos + length]
        parsed = parse_record(raw_record)
        if parsed.name not in {".", ".."}:
            entries.append(parsed)
        pos += length
    return entries


def root_record(handle) -> IsoRecord:
    handle.seek(16 * SECTOR_SIZE)
    descriptor = handle.read(SECTOR_SIZE)
    if len(descriptor) != SECTOR_SIZE or descriptor[0] != 1 or descriptor[1:6] != b"CD001":
        fail("未找到 ISO9660 Primary Volume Descriptor")
    return parse_record(descriptor[156 : 156 + descriptor[156]])


def find_record(handle, wanted_path: str) -> IsoRecord:
    parts = [part.lower() for part in wanted_path.strip("/").split("/") if part]
    if not parts:
        fail("目标路径不能为空")
    current = root_record(handle)
    iso_size = os.fstat(handle.fileno()).st_size
    for index, part in enumerate(parts):
        if not current.is_dir:
            fail("ISO 路径中间节点不是目录")
        matches = [entry for entry in iter_directory(handle, current, iso_size) if entry.name == part]
        if not matches:
            fail(f"ISO 内缺少预期文件: {wanted_path}")
        current = matches[0]
        if index < len(parts) - 1 and not current.is_dir:
            fail("ISO 路径中间节点不是目录")
    if current.is_dir:
        fail("目标路径是目录，不是普通文件")
    return current


def list_dir_records(iso: Path, wanted_path: str) -> list[IsoRecord]:
    if not iso.is_file() or iso.is_symlink():
        fail("源 ISO 不存在、不是普通文件或是 symlink")
    with iso.open("rb") as handle:
        iso_size = os.fstat(handle.fileno()).st_size
        parts = [part.lower() for part in wanted_path.strip("/").split("/") if part]
        current = root_record(handle)
        for part in parts:
            matches = [entry for entry in iter_directory(handle, current, iso_size) if entry.name == part]
            if not matches or not matches[0].is_dir:
                fail(f"ISO 内缺少预期目录: {wanted_path}")
            current = matches[0]
        return iter_directory(handle, current, iso_size)


def safe_output_path(output: Path, allowed_root: Path) -> Path:
    allowed = allowed_root.resolve()
    parent = output.parent.resolve()
    if allowed != parent and allowed not in parent.parents:
        fail("输出路径越界")
    if output.exists() or output.is_symlink():
        fail("目标文件已存在，拒绝覆盖")
    try:
        relative_parent = parent.relative_to(allowed)
    except ValueError:
        fail("输出路径越界")
    current = allowed
    for part in relative_parent.parts:
        current = current / part
        if current.is_symlink():
            fail("输出路径父级包含 symlink，拒绝写入")
    return parent / output.name


def extract_file(iso: Path, wanted_path: str, output: Path, allowed_root: Path) -> None:
    if not iso.is_file() or iso.is_symlink():
        fail("源 ISO 不存在、不是普通文件或是 symlink")
    iso_size = iso.stat().st_size
    target = safe_output_path(output, allowed_root)
    with iso.open("rb") as handle:
        record = find_record(handle, wanted_path)
        validate_extent(record.extent, record.size, iso_size)
        target_name = Path(wanted_path).name.lower()
        max_size = MAX_EXTRACT_BYTES.get(target_name)
        if max_size is None and target_name.endswith(".squashfs"):
            max_size = 12 * 1024 * 1024 * 1024
        if max_size is None and target_name.endswith(".manifest"):
            max_size = 128 * 1024 * 1024
        if max_size is None and target_name.endswith(".size"):
            max_size = 16 * 1024 * 1024
        if max_size is None:
            fail("当前提取器只允许提取项目白名单内的启动文件")
        if record.size > max_size:
            fail("ISO 内目标文件超过安全大小上限")
        handle.seek(record.extent * SECTOR_SIZE)
        remaining = record.size
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(target, flags, 0o644)
        try:
            with os.fdopen(fd, "wb") as file:
                while remaining > 0:
                    chunk = handle.read(min(COPY_CHUNK_SIZE, remaining))
                    if not chunk:
                        fail("读取 ISO 文件内容失败，镜像可能不完整")
                    file.write(chunk)
                    remaining -= len(chunk)
        except BaseException:
            try:
                target.unlink()
            except OSError:
                pass
            raise
    print(f"APPROVED: extracted {wanted_path} -> {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract one file from an ISO9660 image.")
    parser.add_argument("--iso", required=True)
    parser.add_argument("--path")
    parser.add_argument("--output")
    parser.add_argument("--allowed-root")
    parser.add_argument("--list-dir")
    args = parser.parse_args()

    if args.list_dir:
        for record in list_dir_records(Path(args.iso), args.list_dir):
            kind = "dir" if record.is_dir else "file"
            print(f"{record.name}\t{kind}\t{record.size}")
        return 0

    if not args.path or not args.output or not args.allowed_root:
        fail("--path、--output 和 --allowed-root 必须同时提供")

    extract_file(
        iso=Path(args.iso),
        wanted_path=args.path,
        output=Path(args.output),
        allowed_root=Path(args.allowed_root),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
