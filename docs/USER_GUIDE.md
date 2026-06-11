# SynaBoot 用户指南

## 访问地址

- Web UI：`http://192.168.1.168:8080/`
- iPXE 菜单：`http://192.168.1.168:8080/boot/menu.ipxe`
- 镜像仓库：`http://192.168.1.168:8080/images/`

## 启动方式

Phase 1 不接管现有 DHCP。用户需要使用 iPXE USB/ISO/EFI，或支持手动 URL 的
UEFI HTTP Boot。

iPXE Shell 中可执行：

```ipxe
chain http://192.168.1.168:8080/boot/menu.ipxe
```

也可以查看本地启动介质说明：

```bash
bash scripts/create-ipxe-usb.sh
```

如需通过 HTTP 提供 iPXE loader，请将真实文件放入：

```text
data/boot/loaders/ipxe.efi
data/boot/loaders/ipxe.iso
```

## 放置镜像

所有镜像都放在 `data/images` 下。

放入文件后，需要设置 `SYNABOOT_ADMIN_TOKEN`，再通过 Web UI 或命令触发扫描：

```bash
SYNABOOT_ADMIN_TOKEN=<管理员token> bash scripts/sync-metadata.sh
```

`GET /api/images` 只读取缓存，不会触发全量 SHA256 扫描。
