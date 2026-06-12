# SynaBoot 管理员教程

本文面向负责部署和维护 SynaBoot 的管理员。

默认地址：

```text
SERVER_IP=192.168.1.168
HTTP_PORT=18080
Web UI=http://192.168.1.168:18080/
iPXE_MENU=http://192.168.1.168:18080/boot/menu.ipxe
IMAGES=http://192.168.1.168:18080/images/
```

## 1. 安全边界

SynaBoot 是零侵入 HTTP/iPXE Boot 平台。

管理员不得为了部署 SynaBoot 执行以下操作：

- 启用 DHCP Server。
- 启用 ProxyDHCP。
- 启用 TFTP。
- 修改路由器、OpenWrt、TP-Link、交换机、AP、VLAN、DNS、路由、防火墙。
- 开放 UDP `67/68/69/4011`。
- 使用 Docker `network_mode: host`。
- 使用 Docker `privileged: true`。
- 上传内部 ISO/镜像到公网 SaaS。

普通 PXE 自动发现不属于本项目零侵入范围。客户端应使用 iPXE 启动介质、手动 UEFI HTTP Boot，或外部已有 chain 入口。

## 2. 首次部署

复制配置：

```bash
cp .env.example .env
```

编辑 `.env`：

```text
SERVER_IP=192.168.1.168
SYNABOOT_HTTP_BIND=18080
SYNABOOT_HTTP_PORT=18080
SYNABOOT_ADMIN_TOKEN=请替换为强随机token
```

初始化目录：

```bash
bash init-directories.sh
```

运行安全预检：

```bash
bash scripts/preflight/check-network-safety.sh
docker compose config
```

启动：

```bash
docker compose up -d
```

验证：

```bash
curl http://localhost:18080/
curl http://localhost:18080/boot/menu.ipxe
curl http://localhost:18080/images/
curl http://localhost:18080/api/images
```

如果 `18080/tcp` 被占用，不要修改防火墙或路由绕过。应先确认端口归属，再在 `.env` 中改用另一个未占用 TCP 端口，并同步 `SYNABOOT_HTTP_BIND` 与 `SYNABOOT_HTTP_PORT`。

## 3. 放置镜像

所有镜像必须放在：

```text
data/images/
```

推荐目录：

```text
data/images/
├── pe/
│   └── hotpe/
├── windows/
│   └── win11/
├── linux/
│   └── ubuntu-22.04.3/
├── tools/
└── custom/
```

HotPE：

```text
data/images/pe/hotpe/
├── wimboot
├── bootmgr
├── BCD
├── boot.sdi
└── boot.wim
```

Ubuntu/Linux：

```text
data/images/linux/ubuntu-22.04.3/
├── ubuntu-22.04.3-live-server-amd64.iso
└── casper/
    ├── vmlinuz
    └── initrd
```

Windows：

```text
data/images/windows/win11/Windows11_24H2.iso
```

注意：Windows ISO/WIM/ESD 默认通过 HotPE 辅助安装，不作为 iPXE 直接启动项。

## 4. 扫描镜像

方式 A：Web UI

1. 打开 `http://192.168.1.168:18080/`。
2. 进入“镜像仓库”。
3. 点击“扫描镜像”。
4. 输入 `.env` 中配置的 `SYNABOOT_ADMIN_TOKEN`。
5. 检查 `scan_status`、`boot_readiness`、`menu_enabled`。

方式 B：脚本

```bash
SYNABOOT_ADMIN_TOKEN=<管理员token> bash scripts/sync-metadata.sh
```

扫描结果含义：

- `scan_status=present`：文件存在。
- `scan_status=missing`：元数据存在，但文件已丢失。
- `boot_readiness=ready`：可进入 iPXE 菜单。
- `boot_readiness=incomplete`：缺少启动依赖。
- `boot_readiness=needs_hotpe`：需要先启动 HotPE。
- `boot_readiness=unsupported`：可存储/下载，但不会生成启动项。

## 5. 生成菜单

Web UI 中点击“重新生成菜单”，输入管理员 token。

也可以执行：

```bash
SYNABOOT_ADMIN_TOKEN=<管理员token> bash scripts/generate-ipxe-menu.sh
```

只有满足以下条件的镜像会进入菜单：

```text
scan_status=present
boot_readiness=ready
menu_enabled=true
```

查看菜单：

```bash
curl http://localhost:18080/boot/menu.ipxe
```

## 6. 客户端启动入口

Phase 3 自动网络启动入口仍处于门禁状态。管理员只读确认清单见
`BOOT_ENTRY_INTEGRATION.md`。

当前已根据管理员截图确认主路由为 TP-Link `TL-ER6120T`，但管理员未在
管理界面找到 DHCP Option `66/67` 或等价 boot option 配置入口。因此
默认不依赖主路由 DHCP Option 路线，后续只允许 documentation-only 的
受控 ProxyDHCP 可行性评估。

Web UI 的“启动入口”页展示本地事实门禁，“网络安全”页通过
`/api/network-safety.phase3_gate` 同步展示 Phase 3.3 门禁。两处都只是
只读提醒，不提供路由器配置、服务启用或生产 LAN 测试入口；其中允许实现、
允许启用服务、允许生产 LAN 测试均应保持为 `False`。

只读参考文档与本文位于同一 `docs/` 目录：

- `BOOT_ENTRY_LOCAL_VERIFICATION.md`：本地设备能力确认记录。
- `PROXYDHCP_FEASIBILITY.md`：受控 ProxyDHCP 可行性评估。
- `PROXYDHCP_PACKET_REVIEW.md`：未来经审批隔离验证的报文字段判读标准。
- `TFTP_LOADER_SCOPE.md`：未来 TFTP loader 文件范围。
- `PHASE3_ROLLBACK_CHECKLIST.md`：Phase 3 回滚证据清单。
- `PHASE3_REVIEW_TEMPLATES.md`：网络安全与安全审计模板。

提供给用户的 iPXE chain 地址：

```text
http://192.168.1.168:18080/boot/menu.ipxe
```

iPXE Shell：

```ipxe
chain http://192.168.1.168:18080/boot/menu.ipxe
```

手动 UEFI HTTP Boot 使用同一 URL。

## 7. 日常维护

查看服务：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs --tail=100
```

停止：

```bash
docker compose down
```

更新镜像文件后：

1. 放入或删除 `data/images` 下的文件。
2. 重新扫描。
3. 检查状态。
4. 重新生成菜单。
5. 从测试客户端验证启动。

## 8. 故障排查

Web UI 打不开：

- 检查 `docker compose ps`。
- 检查端口是否监听：`ss -ltnp | grep 18080`。
- 检查 `SYNABOOT_HTTP_BIND` 与 `SYNABOOT_HTTP_PORT` 是否一致。

菜单里没有镜像：

- 确认文件位于 `data/images`。
- 执行扫描。
- 检查 `boot_readiness` 是否为 `ready`。
- 检查 `menu_enabled` 是否启用。

Ubuntu 无法启动：

- 确认同一目录下有 ISO、`casper/vmlinuz`、`casper/initrd`。

Windows 无法直接启动：

- 这是预期行为。请先启动 HotPE，再访问 Windows 镜像仓库。

## 9. 变更端口

如果 `18080/tcp` 也被占用，可在 `.env` 中改成其他未占用 TCP 端口：

```text
SYNABOOT_HTTP_BIND=19080
SYNABOOT_HTTP_PORT=19080
```

然后重启：

```bash
docker compose down
docker compose up -d
```

不要通过修改防火墙、路由、DNS、DHCP 或交换机配置来解决端口冲突。
