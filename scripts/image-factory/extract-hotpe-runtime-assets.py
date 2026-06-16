#!/usr/bin/env python3
"""从 HotPE ISO 只读提取外置运行时模块。

HotPE 的大量桌面工具不在 boot.wim 内，而在 ISO 根目录的 HotProgMods
和 HotPE/Data 等外置目录中。wimboot 只加载 boot.wim 时不会自动挂载
这些目录。本脚本只解析 UDF 元数据并复制允许目录到 data/images 下，
不挂载 ISO，不执行 ISO 内文件。
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UDF_SCRIPT = ROOT / "scripts" / "image-factory" / "extract-udf-file.py"
SECTOR_SIZE = 2048
COPY_CHUNK_SIZE = 1024 * 1024
ALLOWED_PREFIXES = ("HotProgMods/", "HotPE/Data/", "HotPE/HotPE.INI", "HotPE/confi.ini")
MAX_SINGLE_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


def fail(message: str) -> None:
    print(f"BLOCKED: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_udf_module():
    spec = importlib.util.spec_from_file_location("synaboot_udf_extract", UDF_SCRIPT)
    if spec is None or spec.loader is None:
        fail(f"无法加载 UDF 提取模块: {UDF_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["synaboot_udf_extract"] = module
    spec.loader.exec_module(module)
    return module


def ensure_child(parent: Path, child: Path, label: str) -> Path:
    parent_real = parent.resolve()
    child_real = child.resolve()
    if parent_real != child_real and parent_real not in child_real.parents:
        fail(f"{label} 越界")
    return child_real


def safe_join(root: Path, rel_path: str) -> Path:
    parts = [part for part in Path(rel_path).parts if part not in {"", ".", ".."}]
    if not parts:
        fail("输出路径为空")
    return ensure_child(root, root.joinpath(*parts), "输出路径")


def is_allowed(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/").strip("/")
    lower = normalized.lower()
    for prefix in ALLOWED_PREFIXES:
        if lower == prefix.lower().strip("/") or lower.startswith(prefix.lower()):
            return True
    return False


def iter_tree(udf, handle, volume, iso_size: int, location: int, prefix: str = ""):
    for entry in udf.iter_directory(handle, volume, location, iso_size):
        rel_path = f"{prefix}{entry.name}"
        yield rel_path, entry
        if entry.is_dir:
            yield from iter_tree(udf, handle, volume, iso_size, entry.location, rel_path + "/")


def ensure_public_dirs(output_root: Path, directory: Path) -> None:
    current = directory
    while current == output_root or output_root in current.parents:
        os.chmod(current, 0o755)
        if current == output_root:
            break
        current = current.parent


def copy_file(udf, handle, volume, iso_size: int, entry, target: Path, output_root: Path) -> int:
    file_entry = udf.parse_file_entry(handle, volume, entry.location, iso_size)
    if file_entry.info_length < 0 or file_entry.info_length > MAX_SINGLE_FILE_BYTES:
        fail(f"文件过大或异常: {target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    ensure_public_dirs(output_root, target.parent)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "wb") as output:
            fd = -1
            remaining = file_entry.info_length
            for extent in file_entry.allocation_extents:
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
                        fail("读取 UDF 文件内容失败")
                    output.write(chunk)
                    chunk_remaining -= len(chunk)
                remaining -= length
            if remaining != 0:
                fail("UDF 文件 extent 长度不足")
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            target.unlink()
        except OSError:
            pass
        raise
    os.chmod(target, 0o644)
    return file_entry.info_length


def extract_runtime(iso: Path, output_dir: Path) -> None:
    if not iso.is_file() or iso.is_symlink():
        fail("源 HotPE ISO 不存在、不是普通文件或是 symlink")
    images_root = (ROOT / "data" / "images").resolve()
    output = ensure_child(images_root, output_dir, "输出目录")
    if output.exists():
        fail(f"输出目录已存在，拒绝覆盖: {output}")
    udf = load_udf_module()
    iso_size = iso.stat().st_size
    copied = 0
    files = 0
    try:
        with iso.open("rb") as handle:
            volume = udf.parse_volume(handle, iso_size)
            for rel_path, entry in iter_tree(udf, handle, volume, iso_size, volume.root_location):
                if entry.is_dir or not is_allowed(rel_path):
                    continue
                target = safe_join(output, rel_path)
                copied += copy_file(udf, handle, volume, iso_size, entry, target, output)
                files += 1
                if copied > MAX_TOTAL_BYTES:
                    fail("HotPE 运行时提取总量超过安全上限")
    except BaseException:
        if output.exists():
            shutil.rmtree(output)
        raise
    print(f"APPROVED: extracted_hotpe_runtime_files={files} bytes={copied} output={output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract HotPE runtime modules from a UDF ISO.")
    parser.add_argument("--iso", default=str(ROOT / "data/images/pe/hotpe/HotPE-V2.8.251018.iso"))
    parser.add_argument("--output-dir", default=str(ROOT / "data/images/pe/hotpe/runtime"))
    args = parser.parse_args()
    extract_runtime(Path(args.iso), Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
