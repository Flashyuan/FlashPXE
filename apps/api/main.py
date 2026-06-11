#!/usr/bin/env python3
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

SERVER_IP = os.environ.get("SERVER_IP", "192.168.1.168")
SYNABOOT_PORT = int(os.environ.get("SYNABOOT_PORT", "8080"))
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

IMAGE_EXTENSIONS = {
    ".iso": "iso",
    ".wim": "wim",
    ".esd": "esd",
    ".efi": "efi",
    ".img": "image",
    ".initrd": "initrd",
}
SPECIAL_NAMES = {
    "wimboot": "wimboot",
    "vmlinuz": "linux-kernel",
    "initrd": "initrd",
    "boot.wim": "wim",
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


def scan_images() -> list[dict]:
    conn = connect_db()
    now = int(time.time())
    rows: list[dict] = []
    seen: set[str] = set()

    for path in sorted(IMAGES_DIR.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        kind = file_kind(path)
        if not kind:
            continue
        rel_path = safe_relative(path, IMAGES_DIR)
        category = category_from_path(rel_path)
        seen.add(rel_path)
        row = {
            "id": hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:16],
            "name": path.name,
            "category": category,
            "kind": kind,
            "rel_path": rel_path,
            "url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/{rel_path}",
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "menu_enabled": 1,
            "boot_method": boot_method(category, kind, rel_path),
            "description": "",
            "scanned_at": now,
        }
        conn.execute(
            """
            INSERT INTO images (
                id, name, category, kind, rel_path, size_bytes, sha256,
                menu_enabled, boot_method, description, scanned_at
            )
            VALUES (
                :id, :name, :category, :kind, :rel_path, :size_bytes, :sha256,
                :menu_enabled, :boot_method, :description, :scanned_at
            )
            ON CONFLICT(rel_path) DO UPDATE SET
                name=excluded.name,
                category=excluded.category,
                kind=excluded.kind,
                size_bytes=excluded.size_bytes,
                sha256=excluded.sha256,
                boot_method=excluded.boot_method,
                scanned_at=excluded.scanned_at
            """,
            row,
        )
        rows.append(row)

    if seen:
        placeholders = ",".join("?" for _ in seen)
        conn.execute(f"DELETE FROM images WHERE rel_path NOT IN ({placeholders})", tuple(seen))
    else:
        conn.execute("DELETE FROM images")
    conn.commit()
    conn.close()
    write_menu(rows)
    return rows


def list_images() -> list[dict]:
    conn = connect_db()
    rows = [
        dict(row) | {"url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/{row['rel_path']}"}
        for row in conn.execute("SELECT * FROM images ORDER BY category, rel_path")
    ]
    conn.close()
    return rows


def get_image(image_id: str) -> dict | None:
    conn = connect_db()
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row) | {"url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/{row['rel_path']}"}


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


def menu_enabled(rel_path: str | None = None, *, category: str | None = None, kind: str | None = None) -> bool:
    conn = connect_db()
    clauses: list[str] = []
    params: list[str] = []
    if rel_path is not None:
        clauses.append("rel_path = ?")
        params.append(rel_path)
    if category is not None:
        clauses.append("category = ?")
        params.append(category)
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    where = " AND ".join(clauses) if clauses else "1=1"
    rows = conn.execute(f"SELECT menu_enabled FROM images WHERE {where}", tuple(params)).fetchall()
    conn.close()
    if not rows:
        return True
    return any(row["menu_enabled"] == 1 for row in rows)


def hotpe_ready() -> bool:
    required = ["wimboot", "bootmgr", "BCD", "boot.sdi", "boot.wim"]
    return all((IMAGES_DIR / "pe" / "hotpe" / name).is_file() and menu_enabled(f"pe/hotpe/{name}") for name in required)


def ubuntu2204_ready() -> bool:
    base = IMAGES_DIR / "linux" / "ubuntu-22.04.3"
    iso_path = first_ubuntu_iso()
    return (
        (base / "casper" / "vmlinuz").is_file()
        and menu_enabled("linux/ubuntu-22.04.3/casper/vmlinuz")
        and (base / "casper" / "initrd").is_file()
        and menu_enabled("linux/ubuntu-22.04.3/casper/initrd")
        and any(base.glob("*.iso"))
        and menu_enabled(iso_path)
    )


def first_ubuntu_iso() -> str:
    base = IMAGES_DIR / "linux" / "ubuntu-22.04.3"
    iso = next(iter(sorted(base.glob("*.iso"))), None)
    name = iso.name if iso else "ubuntu-22.04.3-live-server-amd64.iso"
    return f"linux/ubuntu-22.04.3/{name}"


def write_menu(_rows: list[dict] | None = None) -> str:
    ensure_dirs()
    lines = [
        "#!ipxe",
        "",
        f"set server-ip {SERVER_IP}",
        f"set base-url http://${{server-ip}}:{SYNABOOT_PORT}",
        "set boot-url ${base-url}/boot",
        "set image-url ${base-url}/images",
        "",
        ":start",
        "menu SynaBoot Phase 1 - HTTP Boot",
        "item --gap --          === PE / Recovery ===",
        "item hotpe            HotPE via wimboot",
        "item --gap --          === Linux ===",
        "item ubuntu22043      Ubuntu 22.04.3 Live Server",
        "item --gap --          === Windows ===",
        "item windows_hotpe    Windows installation via HotPE",
        "item --gap --          === Tools ===",
        "item shell            iPXE shell",
        "item reboot           Reboot",
        "choose --default hotpe --timeout 15000 target && goto ${target} || goto start",
        "",
        ":hotpe",
    ]
    if hotpe_ready():
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
                "echo HotPE files are not ready.",
                "echo Put wimboot, bootmgr, BCD, boot.sdi and boot.wim under ${image-url}/pe/hotpe/.",
                "goto start",
            ]
        )
    lines.extend(
        [
            "",
            ":windows_hotpe",
            "echo Windows ISO should be installed from HotPE.",
            "echo Boot HotPE, then open ${image-url}/windows/.",
            "goto hotpe",
            "",
            ":ubuntu22043",
        ]
    )
    if ubuntu2204_ready():
        iso_path = first_ubuntu_iso()
        lines.extend(
            [
                "echo Loading Ubuntu 22.04.3 installer...",
                "set ubuntu-url ${image-url}/linux/ubuntu-22.04.3",
                f"kernel ${{ubuntu-url}}/casper/vmlinuz ip=dhcp url=${{base-url}}/images/{iso_path} ---",
                "initrd ${ubuntu-url}/casper/initrd",
                "boot || goto boot_failed",
            ]
        )
    else:
        lines.extend(
            [
                "echo Ubuntu 22.04.3 files are not ready.",
                "echo Put ISO, casper/vmlinuz and casper/initrd under ${image-url}/linux/ubuntu-22.04.3/.",
                "goto start",
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
menu SynaBoot Phase 1 - HTTP Boot
item shell iPXE shell
item reboot Reboot
choose --default shell --timeout 15000 target && goto ${{target}} || goto start

:shell
shell
goto start

:reboot
reboot
"""


def list_jobs() -> list[dict]:
    conn = connect_db()
    rows = [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY created_at DESC")]
    conn.close()
    return rows


def create_job(payload: dict) -> dict:
    kind = payload.get("kind") if isinstance(payload, dict) else None
    if kind not in {"ubuntu-autoinstall", "windows-adk-package"}:
        kind = "ubuntu-autoinstall"
    now = int(time.time())
    job_id = uuid.uuid4().hex[:12]
    title = safe_title(payload.get("title"), f"{kind}-{job_id}")
    output_dir = BUILDS_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "logs").mkdir(parents=True, exist_ok=True)
    (output_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (output_dir / "output" / "artifacts").mkdir(parents=True, exist_ok=True)
    (output_dir / "package").mkdir(parents=True, exist_ok=True)

    # 任务框架只生成安全的配置模板，不执行磁盘或系统修改。
    if kind == "ubuntu-autoinstall":
        package_dir = output_dir / "package" / "ubuntu"
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "user-data").write_text(ubuntu_user_data(title), encoding="utf-8")
        (package_dir / "meta-data").write_text(f"instance-id: {job_id}\nlocal-hostname: synaboot-client\n", encoding="utf-8")
        (package_dir / "README.md").write_text("请人工审查 user-data，确认密码 hash 与安装策略后再使用。\n", encoding="utf-8")
        note = "已生成 Ubuntu autoinstall 模板；请人工审查后再用于安装介质。"
    else:
        package_dir = output_dir / "package" / "windows-adk"
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "README-WINDOWS-ADK.txt").write_text(windows_adk_readme(job_id), encoding="utf-8")
        note = "已生成 Windows ADK/DISM 外部构建包说明；需在 Windows 构建机执行。"

    row = {
        "id": job_id,
        "kind": kind,
        "status": "pending",
        "title": title,
        "output_dir": output_dir.relative_to(DATA_DIR).as_posix(),
        "created_at": now,
        "updated_at": now,
        "note": note,
    }
    (output_dir / "job.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "status.json").write_text(json.dumps({"status": "pending", "updated_at": now}, ensure_ascii=False, indent=2), encoding="utf-8")
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
  # Phase 1 默认不生成 storage 自动分区配置。
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


def network_safety_status() -> dict:
    return {
        "status": "APPROVED_SCOPE",
        "server_ip": SERVER_IP,
        "http_port": SYNABOOT_PORT,
        "menu_url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/boot/menu.ipxe",
        "images_url": f"http://{SERVER_IP}:{SYNABOOT_PORT}/images/",
        "allowed": ["HTTP 8080/tcp", "Docker bridge network", "static /images", "static /boot", "API reverse proxy"],
        "forbidden": ["DHCP", "ProxyDHCP", "TFTP", "Samba by default", "host network", "privileged containers", "UDP 67/68/69/4011"],
    }


class Handler(BaseHTTPRequestHandler):
    def require_admin(self) -> bool:
        if not ADMIN_TOKEN:
            json_response(self, 403, {"error": "admin_actions_disabled"})
            return False
        provided = self.headers.get("X-SynaBoot-Admin-Token", "")
        if provided != ADMIN_TOKEN:
            json_response(self, 403, {"error": "invalid_admin_token"})
            return False
        client = self.client_address[0]
        now = time.time()
        last = LAST_WRITE_BY_CLIENT.get(client, 0)
        if now - last < 2:
            json_response(self, 429, {"error": "rate_limited"})
            return False
        LAST_WRITE_BY_CLIENT[client] = now
        return True

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            json_response(self, 200, {"status": "ok", "server_ip": SERVER_IP})
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
        elif path in {"/api/network-safety", "/api/safety"}:
            json_response(self, 200, network_safety_status())
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
        if path in {"/api/jobs/ubuntu-autoinstall", "/api/jobs/windows-adk-package"}:
            kind = path.rsplit("/", 1)[-1]
            json_response(self, 201, create_job({"kind": kind}))
            return
        if path != "/api/jobs":
            json_response(self, 404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > 65536:
            json_response(self, 413, {"error": "payload_too_large"})
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            json_response(self, 400, {"error": "invalid_json"})
            return
        json_response(self, 201, create_job(payload))

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
