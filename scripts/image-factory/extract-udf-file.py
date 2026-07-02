#!/usr/bin/env python3
"""从 UDF ISO 镜像中只读提取单个白名单文件。

该工具用于 HotPE ISO 启动依赖准备。它不挂载 ISO，不执行 ISO 内文件，
只解析 UDF 元数据并将允许的文件流式复制到指定 data/images 子目录。
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path


SECTOR_SIZE = 2048
COPY_CHUNK_SIZE = 1024 * 1024
MAX_EXTRACT_BYTES = {
    "bootmgr": 64 * 1024 * 1024,
    "bootmgfw.efi": 64 * 1024 * 1024,
    "bootx64.efi": 64 * 1024 * 1024,
    "bcd": 32 * 1024 * 1024,
    "boot.sdi": 128 * 1024 * 1024,
    "boot.wim": 2 * 1024 * 1024 * 1024,
}


@dataclass(frozen=True)
class UdfExtent:
    length: int
    position: int


@dataclass(frozen=True)
class UdfFileEntry:
    location: int
    info_length: int
    allocation_extents: list[UdfExtent]


@dataclass(frozen=True)
class UdfDirEntry:
    name: str
    location: int
    is_dir: bool


@dataclass(frozen=True)
class UdfVolume:
    partition_start: int
    logical_block_size: int
    root_location: int


def fail(message: str) -> None:
    print(f"BLOCKED: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_sector(handle, sector: int, iso_size: int) -> bytes:
    if sector < 0 or (sector + 1) * SECTOR_SIZE > iso_size:
        fail("UDF sector 越界，镜像可能异常或损坏")
    handle.seek(sector * SECTOR_SIZE)
    data = handle.read(SECTOR_SIZE)
    if len(data) != SECTOR_SIZE:
        fail("读取 UDF sector 失败，镜像可能不完整")
    return data


def tag_id(data: bytes) -> int:
    if len(data) < 16:
        fail("UDF 描述符过短")
    return int.from_bytes(data[0:2], "little")


def descriptor_location(data: bytes) -> int:
    return int.from_bytes(data[12:16], "little")


def parse_short_ad(data: bytes) -> UdfExtent:
    if len(data) != 8:
        fail("UDF short_ad 长度异常")
    raw_length = int.from_bytes(data[0:4], "little")
    length = raw_length & 0x3FFFFFFF
    position = int.from_bytes(data[4:8], "little")
    if length < 0 or position < 0:
        fail("UDF extent 异常")
    return UdfExtent(length=length, position=position)


def parse_long_ad(data: bytes) -> UdfExtent:
    if len(data) < 16:
        fail("UDF long_ad 长度异常")
    raw_length = int.from_bytes(data[0:4], "little")
    length = raw_length & 0x3FFFFFFF
    position = int.from_bytes(data[4:8], "little")
    partition_ref = int.from_bytes(data[8:10], "little")
    if partition_ref != 0:
        fail("当前提取器只支持单分区 UDF 镜像")
    return UdfExtent(length=length, position=position)


def find_anchor(handle, iso_size: int) -> tuple[int, int]:
    candidates = [256]
    total_sectors = iso_size // SECTOR_SIZE
    if total_sectors > 256:
        candidates.append(total_sectors - 256)
    for sector in candidates:
        data = read_sector(handle, sector, iso_size)
        if tag_id(data) != 2:
            continue
        main_len = int.from_bytes(data[16:20], "little")
        main_loc = int.from_bytes(data[20:24], "little")
        if main_len <= 0 or main_loc <= 0:
            fail("UDF Anchor Volume Descriptor Pointer 异常")
        return main_loc, main_len
    fail("未找到 UDF Anchor Volume Descriptor Pointer")


def parse_volume(handle, iso_size: int) -> UdfVolume:
    main_loc, main_len = find_anchor(handle, iso_size)
    partition_start: int | None = None
    logical_block_size: int | None = None
    root_extent: UdfExtent | None = None
    sectors = (main_len + SECTOR_SIZE - 1) // SECTOR_SIZE
    for sector in range(main_loc, main_loc + sectors):
        data = read_sector(handle, sector, iso_size)
        ident = tag_id(data)
        if ident == 5:
            partition_start = int.from_bytes(data[188:192], "little")
        elif ident == 6:
            logical_block_size = int.from_bytes(data[212:216], "little")
            root_extent = parse_long_ad(data[248:264])
        elif ident == 8:
            break
    if partition_start is None:
        fail("UDF 缺少 Partition Descriptor")
    if logical_block_size != SECTOR_SIZE:
        fail("当前提取器只支持 2048 字节 UDF logical block")
    if root_extent is None:
        fail("UDF 缺少 File Set Descriptor 入口")
    fsd_sector = partition_start + root_extent.position
    fsd = read_sector(handle, fsd_sector, iso_size)
    if tag_id(fsd) != 256:
        fail("UDF File Set Descriptor 异常")
    root_icb = parse_long_ad(fsd[400:416])
    return UdfVolume(
        partition_start=partition_start,
        logical_block_size=logical_block_size,
        root_location=root_icb.position,
    )


def read_partition_block(handle, volume: UdfVolume, location: int, iso_size: int) -> bytes:
    return read_sector(handle, volume.partition_start + location, iso_size)


def parse_file_entry(handle, volume: UdfVolume, location: int, iso_size: int) -> UdfFileEntry:
    data = read_partition_block(handle, volume, location, iso_size)
    if tag_id(data) != 261:
        fail(f"UDF 文件入口不是 File Entry: {location}")
    if descriptor_location(data) != location:
        fail("UDF File Entry descriptor location 不匹配")
    info_length = int.from_bytes(data[56:64], "little")
    ext_attr_len = int.from_bytes(data[168:172], "little")
    alloc_len = int.from_bytes(data[172:176], "little")
    alloc_start = 176 + ext_attr_len
    alloc_end = alloc_start + alloc_len
    if alloc_start < 176 or alloc_end > len(data):
        fail("UDF allocation descriptor 越界")
    extents: list[UdfExtent] = []
    for pos in range(alloc_start, alloc_end, 8):
        extent = parse_short_ad(data[pos : pos + 8])
        if extent.length:
            extents.append(extent)
    return UdfFileEntry(location=location, info_length=info_length, allocation_extents=extents)


def read_file_bytes(handle, volume: UdfVolume, entry: UdfFileEntry, iso_size: int) -> bytes:
    if entry.info_length > 128 * 1024 * 1024:
        fail("目录或小文件读取超过安全上限")
    chunks: list[bytes] = []
    remaining = entry.info_length
    for extent in entry.allocation_extents:
        if remaining <= 0:
            break
        length = min(extent.length, remaining)
        offset = (volume.partition_start + extent.position) * SECTOR_SIZE
        if offset + length > iso_size:
            fail("UDF 文件 extent 越界")
        handle.seek(offset)
        data = handle.read(length)
        if len(data) != length:
            fail("读取 UDF 文件内容失败，镜像可能不完整")
        chunks.append(data)
        remaining -= length
    if remaining != 0:
        fail("UDF 文件 extent 长度不足")
    return b"".join(chunks)


def decode_osta_name(raw: bytes) -> str:
    if not raw:
        return ""
    compression_id = raw[0]
    if compression_id == 8:
        return raw[1:].decode("latin-1")
    if compression_id == 16:
        return raw[1:].decode("utf-16-be")
    fail("不支持的 UDF OSTA 压缩文件名编码")


def align4(value: int) -> int:
    return (value + 3) & ~3


def iter_directory(handle, volume: UdfVolume, location: int, iso_size: int) -> list[UdfDirEntry]:
    entry = parse_file_entry(handle, volume, location, iso_size)
    data = read_file_bytes(handle, volume, entry, iso_size)
    result: list[UdfDirEntry] = []
    pos = 0
    while pos + 38 <= len(data):
        record = data[pos:]
        ident = tag_id(record)
        if ident == 0:
            break
        if ident != 257:
            fail("UDF 目录记录不是 File Identifier Descriptor")
        file_characteristics = record[18]
        name_len = record[19]
        icb = parse_long_ad(record[20:36])
        impl_use_len = int.from_bytes(record[36:38], "little")
        name_start = 38 + impl_use_len
        name_end = name_start + name_len
        if name_end > len(record):
            fail("UDF 文件名越界")
        name = decode_osta_name(record[name_start:name_end])
        record_len = align4(name_end)
        if record_len <= 0:
            fail("UDF 目录记录长度异常")
        pos += record_len
        if not name or file_characteristics & 0x08:
            continue
        result.append(
            UdfDirEntry(
                name=name,
                location=icb.position,
                is_dir=bool(file_characteristics & 0x02),
            )
        )
    return result


def find_record(handle, volume: UdfVolume, wanted_path: str, iso_size: int) -> tuple[UdfDirEntry, UdfFileEntry]:
    parts = [part for part in wanted_path.strip("/").split("/") if part]
    if not parts:
        fail("目标路径不能为空")
    current = volume.root_location
    found: UdfDirEntry | None = None
    for index, part in enumerate(parts):
        entries = iter_directory(handle, volume, current, iso_size)
        matches = [entry for entry in entries if entry.name.lower() == part.lower()]
        if not matches:
            fail(f"UDF 内缺少预期文件: {wanted_path}")
        found = matches[0]
        if index < len(parts) - 1:
            if not found.is_dir:
                fail("UDF 路径中间节点不是目录")
            current = found.location
    if found is None or found.is_dir:
        fail("目标路径是目录，不是普通文件")
    file_entry = parse_file_entry(handle, volume, found.location, iso_size)
    return found, file_entry


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
    max_size = MAX_EXTRACT_BYTES.get(Path(wanted_path).name.lower())
    if max_size is None:
        fail("当前 UDF 提取器只允许提取 HotPE 启动白名单文件")
    target = safe_output_path(output, allowed_root)
    iso_size = iso.stat().st_size
    with iso.open("rb") as handle:
        volume = parse_volume(handle, iso_size)
        _record, entry = find_record(handle, volume, wanted_path, iso_size)
        if entry.info_length <= 0 or entry.info_length > max_size:
            fail("UDF 内目标文件大小超过安全上限")
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            with os.fdopen(fd, "wb") as file:
                fd = -1
                remaining = entry.info_length
                for extent in entry.allocation_extents:
                    if remaining <= 0:
                        break
                    length = min(extent.length, remaining)
                    offset = (volume.partition_start + extent.position) * SECTOR_SIZE
                    if offset + length > iso_size:
                        fail("UDF 文件 extent 越界")
                    handle.seek(offset)
                    chunk_remaining = length
                    while chunk_remaining > 0:
                        chunk = handle.read(min(COPY_CHUNK_SIZE, chunk_remaining))
                        if not chunk:
                            fail("读取 UDF 文件内容失败，镜像可能不完整")
                        file.write(chunk)
                        chunk_remaining -= len(chunk)
                    remaining -= length
                if remaining != 0:
                    fail("UDF 文件 extent 长度不足")
            os.chmod(target, 0o644)
        except BaseException:
            if fd >= 0:
                os.close(fd)
            try:
                target.unlink()
            except OSError:
                pass
            raise
    print(f"APPROVED: extracted {wanted_path} -> {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract one file from a UDF ISO image.")
    parser.add_argument("--iso", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allowed-root", required=True)
    args = parser.parse_args()
    extract_file(
        iso=Path(args.iso),
        wanted_path=args.path,
        output=Path(args.output),
        allowed_root=Path(args.allowed_root),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
