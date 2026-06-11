#!/usr/bin/env python3
import hashlib
import hmac
import json
import os
import re
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
IMAGES_DIR = DATA_DIR / "images"
BOOT_DIR = DATA_DIR / "boot"
METADATA_DIR = DATA_DIR / "metadata"
BUILDS_DIR = DATA_DIR / "builds"
LOGS_DIR = DATA_DIR / "logs"
DB_PATH = METADATA_DIR / "synaboot.sqlite3"
LAST_WRITE_BY_CLIENT: dict[str, float] = {}
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
    required = {
        "pe/hotpe/wimboot",
        "pe/hotpe/bootmgr",
        "pe/hotpe/BCD",
        "pe/hotpe/boot.sdi",
        "pe/hotpe/boot.wim",
    }
    return required.issubset(present)


def boot_readiness(category: str, kind: str, rel_path: str, present: set[str]) -> str:
    if category == "windows" and kind in {"iso", "wim", "esd"}:
        return "needs_hotpe"
    if category == "pe" and "pe/hotpe/" in rel_path:
        return "ready" if hotpe_group_ready(present) else "incomplete"
    if category == "linux":
        return "ready" if linux_group_ready(rel_path, present) else "incomplete"
    return "unsupported"


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
            "scan_status": "present",
            "description": "",
            "scanned_at": now,
            "last_seen_at": now,
            "updated_at": now,
            "missing_since": None,
        }
        discovered.append(row)

    for row in discovered:
        row["boot_readiness"] = boot_readiness(row["category"], row["kind"], row["rel_path"], present_paths)
        conn.execute(
            """
            INSERT INTO images (
                id, name, display_name, category, kind, rel_path, relative_path, size_bytes, sha256,
                menu_enabled, boot_method, description, scanned_at,
                mtime_ns, sha256_cached, scan_status, boot_readiness, last_seen_at, updated_at, missing_since
            )
            VALUES (
                :id, :name, :display_name, :category, :kind, :rel_path, :relative_path, :size_bytes, :sha256,
                :menu_enabled, :boot_method, :description, :scanned_at,
                :mtime_ns, :sha256_cached, :scan_status, :boot_readiness, :last_seen_at, :updated_at, :missing_since
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
                updated_at = ?,
                missing_since = ?
            WHERE rel_path = ?
            """,
            (now, missing_since, rel_path),
        )
    conn.commit()
    rows = [
        dict(row) | {"url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/{row['rel_path']}"}
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


def image_payload(row: dict) -> dict:
    row["display_name"] = row.get("display_name") or row.get("name", "")
    row["relative_path"] = row.get("relative_path") or row.get("rel_path", "")
    row["url"] = f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/{row['rel_path']}"
    row["sha256_cached"] = bool(row.get("sha256_cached"))
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
    rows = [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY created_at DESC")]
    conn.close()
    return rows


def get_job(job_id: str) -> dict | None:
    conn = connect_db()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def job_output_path(job: dict) -> Path:
    output_dir = job.get("output_dir", "")
    root = BUILDS_DIR.resolve()
    resolved = (DATA_DIR / output_dir).resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError("任务目录越界")
    return resolved


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


def create_job(payload: dict) -> dict:
    kind = payload.get("kind") if isinstance(payload, dict) else None
    kind = {
        "ubuntu-autoinstall": "ubuntu-autoinstall-template",
        "ubuntu-autoinstall-template": "ubuntu-autoinstall-template",
        "ubuntu-xorriso-iso": "ubuntu-xorriso-iso",
        "windows-adk-package": "windows-adk-package",
    }.get(kind, "ubuntu-autoinstall-template")
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
    (output_dir / "job.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
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
    }


def loader_status(item: dict) -> dict:
    filename = item["filename"]
    loader_root = BOOT_DIR / "loaders"
    rel_path = f"loaders/{filename}"
    path = loader_root / filename
    parent_symlink = BOOT_DIR.is_symlink() or loader_root.is_symlink()
    is_symlink = path.is_symlink()
    present = (path.exists() or is_symlink) and not parent_symlink
    is_regular_file = present and path.is_file() and not is_symlink
    usable = present and is_regular_file and not is_symlink and not parent_symlink
    stat = path.stat() if usable else None
    mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else ""
    status = (
        "usable"
        if usable
        else ("blocked_parent_symlink" if parent_symlink else ("blocked_symlink" if is_symlink else ("not_regular_file" if present else "missing")))
    )
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
        "size_bytes": stat.st_size if stat else 0,
        "mtime_ns": stat.st_mtime_ns if stat else 0,
        "mtime": mtime,
        "sha256": sha256_file(path) if usable else "",
        "url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/{rel_path}",
        "path": f"data/boot/{rel_path}",
        "status": status,
        "source_recommendation": {
            "type": item["source_type"],
            "note": item["source_guidance"],
        },
        "secure_boot_risk": item["secure_boot_risk"],
        "warnings": [] if usable else [status],
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
            "It does not download, generate, upload, replace, delete, or execute boot loaders.",
            "Symlinks are not accepted as present loader files.",
            "TFTP and ProxyDHCP remain disabled.",
        ],
    }


def boot_entry_status() -> dict:
    menu_url = f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/menu.ipxe"
    loaders = boot_assets_status()["loaders"]
    return {
        "schema_version": "boot-entry.v1",
        "phase": "3.1",
        "mode": "readonly_display_only",
        "status": "READONLY_MODEL_ONLY",
        "enabled": False,
        "default_enabled": False,
        "operation_allowed": False,
        "local_confirmed": False,
        "summary": "Phase 3 boot entry integration is modeled only. No DHCP, ProxyDHCP, or TFTP service is enabled.",
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
            "Confirm exact TP-Link model, hardware version, and firmware version.",
            "Confirm whether DHCP Option 66 and Option 67 are available.",
            "Confirm whether next-server / boot server is available.",
            "Confirm whether Vendor Class Option 60 can distinguish PXEClient and HTTPClient.",
            "Confirm whether Client Architecture Option 93 can distinguish BIOS and UEFI clients.",
            "Validate DHCP offers in an isolated test VLAN or single-client lab before production use.",
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
        if path in {
            "/api/jobs/ubuntu-autoinstall",
            "/api/jobs/ubuntu-autoinstall-template",
            "/api/jobs/ubuntu-xorriso-iso",
            "/api/jobs/windows-adk-package",
        }:
            kind = path.rsplit("/", 1)[-1]
            json_response(self, 201, create_job({"kind": kind}))
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
        json_response(self, 201, create_job(payload))

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
