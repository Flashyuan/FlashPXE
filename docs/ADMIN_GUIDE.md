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

推荐使用安全 bootstrap：

```bash
bash scripts/bootstrap-synaboot.sh --server-ip 192.168.1.168
```

该脚本会生成 `.env`、初始化目录、运行发布范围预检、网络安全预检和
安全 Compose 配置检查。默认不会启动服务。

确认无误后启动：

```bash
docker compose up -d --build
```

如需预检通过后直接启动：

```bash
bash scripts/bootstrap-synaboot.sh --server-ip 192.168.1.168 --start
```

bootstrap 不安装系统包，不修改网络设备、地址分配、解析、转发或安全策略，
也不启用 DHCP、ProxyDHCP、TFTP 或 Samba。
默认会运行发布范围、私有商业范围、版本边界、公开运行时、subagent 治理、
网络安全预检和安全 Compose 配置检查，不会启动服务，除非显式传入
`--start`。

手动部署时，复制配置：

```bash
cp .env.example .env
```

编辑 `.env`，不要把 token 发到聊天、工单或 Git：

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
bash scripts/preflight/check-release-scope.sh
bash scripts/preflight/check-private-commercial-scope.sh
bash scripts/preflight/check-compose-config-safe.sh
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
curl http://localhost:18080/api/deployment-status
```

如果 `18080/tcp` 被占用，不要修改防火墙或路由绕过。应先确认端口归属，再在 `.env` 中改用另一个未占用 TCP 端口，并同步 `SYNABOOT_HTTP_BIND` 与 `SYNABOOT_HTTP_PORT`。

Web UI 的“网络安全”页会显示“部署就绪”只读看板，包括数据目录、配置文件、
访问 URL 和 admin token 是否已配置。该看板不读取或展示 `.env` 内容，
也不代表服务已经接管网络启动。

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
├── bootx64.efi
├── BCD
├── boot.sdi
└── boot.wim
```

Ubuntu/Linux：

```text
data/images/linux/ubuntu-22.04.3/
└── ubuntu-22.04.3-desktop-amd64.iso

data/images/linux/ubuntu-24.04/
└── ubuntu-24.04.3-desktop-amd64.iso
```

Windows：

```text
data/images/windows/win11/Windows11_24H2.iso
```

注意：Windows ISO/WIM/ESD 默认通过 HotPE 辅助安装，不作为 iPXE 直接启动项。

raw ISO 放入后，Web UI 会显示准备状态、缺失文件和下一步动作。Ubuntu
ISO 需要提取 `casper/vmlinuz` 与 `casper/initrd` 后才会成为可启动条目。
HotPE ISO 需要人工准备 `wimboot`、`bootmgr`、`bootx64.efi`、`BCD`、`boot.sdi`、
`boot.wim`，并确认来源可信。

HotPE 的外置工具模块可能位于 ISO 内的 `HotProgMods/*.HPM` 和
`HotPE/Data/`，不一定包含在 `boot.wim` 内。若 wimboot 启动后桌面工具
较少，可提取运行时模块：

```bash
python3 scripts/image-factory/extract-hotpe-runtime-assets.py
```

提取后可通过实验 SMB 共享在 HotPE 中访问：

```text
\\10.101.8.135\synaboot-images\pe\hotpe\runtime\HotProgMods
```

真实 ISO 放好后，可运行服务级 smoke test：

```bash
bash scripts/preflight/check-real-iso-smoke.sh
```

该脚本会启动 Compose、扫描 4 个真实 ISO、检查 Web UI/API/菜单/镜像仓库，
并默认执行 `docker compose down`。如需保留服务用于手工查看，可设置
`SYNABOOT_SMOKE_KEEP_RUNNING=1`。

## 4. 扫描镜像

方式 A：Web UI

1. 打开 `http://192.168.1.168:18080/`。
2. 进入“镜像仓库”。
3. 点击“扫描镜像”。
4. 输入 `.env` 中配置的 `SYNABOOT_ADMIN_TOKEN`。
5. 检查 `scan_status`、`boot_readiness`、`menu_enabled`。

不建议在 shell 命令历史中写入管理员 token。需要脚本化管理时，应使用受控
本机会话，并避免把 `.env`、终端输出或 token 截图提交到 Git、工单或聊天。

扫描结果含义：

- `scan_status=present`：文件存在。
- `scan_status=missing`：元数据存在，但文件已丢失。
- `boot_readiness=ready`：可进入 iPXE 菜单。
- `boot_readiness=incomplete`：缺少启动依赖。
- `boot_readiness=needs_hotpe`：需要先启动 HotPE。
- `boot_readiness=unsupported`：可存储/下载，但不会生成启动项。

## 5. 生成菜单

Web UI 中点击“重新生成菜单”，输入管理员 token。不要在 shell 命令历史、
截图、工单或聊天中暴露该 token。

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

当前已根据管理员截图确认主路由为 TP-Link `TL-ER6120T`，且管理员已
确认当前设备不能下发本项目所需的 PXE/HTTP Boot 启动元数据。因此
默认不依赖主路由 DHCP Option 路线，后续只允许 documentation-only 的
Boot Metadata Proxy 可行性评估。

Boot Metadata Proxy 的产品承诺是：SynaBoot 可以补齐路由器无法下发
PXE/HTTP Boot 启动元数据的缺口，但不得接管 DHCP、DNS、默认网关或
普通网络配置。当前阶段它只作为只读规划展示，不是可启用服务。

Web UI 的“启动入口”页展示本地事实门禁，“网络安全”页通过
`/api/network-safety.phase3_gate` 同步展示 Phase 3.3 门禁。两处都只是
只读提醒，不提供路由器配置、服务启用或生产 LAN 测试入口；其中允许实现、
允许启用服务、允许生产 LAN 测试均应保持为 `False`。

只读参考文档与本文位于同一 `docs/` 目录：

- `BOOT_ENTRY_LOCAL_VERIFICATION.md`：本地设备能力确认记录。
- `PROXYDHCP_FEASIBILITY.md`：Boot Metadata Proxy 可行性评估。
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

当前 `menu.ipxe` 使用文本模式部署控制台样式：顶部展示 Phase 2 HTTP Boot、
服务地址和零侵入模式，菜单按 Windows Deployment、PE / Recovery、
Linux Deployment、Tools 分组，并用快捷键与 `[default]` 标出默认启动项。
这只是 HTTP/iPXE 菜单展示优化，不会启用 DHCP、ProxyDHCP、TFTP，
也不会修改 LAN 路由、网关、防火墙或 DNS。

## 7. 自动安装草稿

Web UI 的“自动安装”页可以创建 Ubuntu 和 Windows 自动安装模板草稿。

当前免费版只提供安全草稿管理：

- 保存模板草稿、变量白名单和模板预览。
- 默认不生成清盘、分区、格式化策略。
- 默认不执行无人值守安装。
- 不把 profile 接入启动菜单。
- “绑定规划”只读展示未来可兼容的 ISO/profile 候选对，但不会保存绑定关系。

真实自动安装前，管理员必须人工审查模板内容、账号策略、密码 hash、
磁盘策略和数据覆盖风险。

## 8. 版本能力与商业边界

Web UI 的“版本能力”页展示 Free、Professional、Enterprise 和 Usage-based
的公开候选边界。

当前 GitHub 分支只作为免费版发布线：

- 基础装机、镜像扫描、菜单生成、手动 iPXE/HTTP Boot、基础自动安装草稿保持免费。
- 商业源码、私有 license、混淆 bundle 和客户交付包不得进入当前分支。
- 本机 owner/developer 可以在 `.gitignore` 覆盖的私有目录中保留未来全功能能力。
- 免费核心不因无 license、无联网而降级。

商业私有流程边界见：

```text
docs/PRIVATE_COMMERCIAL_FLOW.md
```

## 9. 发布前检查

提交或推送免费版前，先按专门清单执行只读检查：

```bash
bash scripts/preflight/check-release-scope.sh
bash scripts/preflight/check-private-commercial-scope.sh
bash scripts/preflight/check-edition-boundary.sh
bash scripts/preflight/check-public-runtime-boundary.sh
bash scripts/preflight/collect-release-evidence.sh
git diff --check
git diff --cached --check
```

必须确认 `.env`、真实 ISO、SQLite、日志、构建产物、私有 license、
商业源码和混淆产物没有进入 Git 范围。

远程 push 前必须经过 `git_audit_agent` 审查、`project_decision_agent`
确认发布方向，并获得用户二次确认。

完整规则见：

```text
docs/FREE_RELEASE_CHECKLIST.md
```

## 10. 日常维护

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

## 11. 故障排查

Web UI 打不开：

- 检查 `docker compose ps`。
- 运行 `bash scripts/preflight/check-network-safety.sh` 查看只读端口摘要。
- 检查 `SYNABOOT_HTTP_BIND` 与 `SYNABOOT_HTTP_PORT` 是否一致。

菜单里没有镜像：

- 确认文件位于 `data/images`。
- 执行扫描。
- 检查 `boot_readiness` 是否为 `ready`。
- 检查 `menu_enabled` 是否启用。

Ubuntu 无法启动：

- 确认同一目录下有 ISO、`casper/vmlinuz`、`casper/initrd`、至少一个 `casper/*.squashfs`。
- SMB/CIFS livefs 模式需要只读共享能访问到该 Ubuntu 目录；HTTP fallback 会下载整 ISO，低内存机器可能失败。
- 查看镜像详情中的 `preparation_status`、`missing_artifacts` 和 `next_action`。

Windows 无法直接启动：

- 这是预期行为。请先启动 HotPE，再访问 Windows 镜像仓库。

自动安装没有执行：

- 这是预期行为。当前免费版只管理草稿、模板预览和只读绑定规划。

## 12. 变更端口

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
