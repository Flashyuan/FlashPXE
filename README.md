# SynaBoot

SynaBoot 是一个面向内网的零侵入 HTTP/iPXE Boot 与系统镜像部署平台。

默认示例：

```text
SERVER_IP=192.168.1.168
Web UI=http://192.168.1.168:18080/
iPXE 菜单=http://192.168.1.168:18080/boot/menu.ipxe
镜像仓库=http://192.168.1.168:18080/images/
```

## 网络安全边界

SynaBoot 不接管现有局域网。

本项目不会：

- 启用 DHCP Server。
- 启用 ProxyDHCP。
- 启用 TFTP。
- 修改路由器、OpenWrt、TP-Link、交换机、AP、VLAN、DNS、路由、防火墙。
- 开放 UDP `67/68/69/4011`。
- 使用 Docker `network_mode: host`。
- 使用 Docker `privileged: true`。
- 上传内部 ISO/镜像到公网 SaaS。

普通网卡 PXE 自动发现不属于零侵入模式。用户需要使用 iPXE 启动介质、手动 UEFI HTTP Boot，或由外部管理员已经配置好的 chain 入口访问 SynaBoot 菜单。

Phase 3 自动网络启动入口仍处于门禁状态。已根据管理员只读截图确认
主路由为 TP-Link `TL-ER6120T`，当前未在管理界面找到 DHCP Option
`66/67` 或等价 boot option 配置入口，因此默认不依赖主路由 DHCP
Option 路线。

相关只读文档：

- `docs/BOOT_ENTRY_INTEGRATION.md`：启动入口集成边界。
- `docs/BOOT_ENTRY_LOCAL_VERIFICATION.md`：本地设备能力确认记录。
- `docs/PROXYDHCP_FEASIBILITY.md`：受控 ProxyDHCP 可行性评估。
- `docs/PROXYDHCP_PACKET_REVIEW.md`：未来经审批隔离验证的报文字段判读标准。
- `docs/TFTP_LOADER_SCOPE.md`：未来 TFTP loader 文件范围。
- `docs/PHASE3_ROLLBACK_CHECKLIST.md`：Phase 3 回滚证据清单。
- `docs/PHASE3_REVIEW_TEMPLATES.md`：网络安全与安全审计模板。

## 部署

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

bootstrap 不会安装系统包，不会修改现有网络设备、地址分配、解析、转发或安全策略，
也不会启用任何自动网络启动服务或文件共享服务。
默认会运行发布范围、私有商业范围、版本边界、公开运行时、subagent 治理、
网络安全预检和安全 Compose 配置检查，不会启动服务，除非显式传入
`--start`。

Web UI 的“网络安全”页面会显示只读部署就绪状态，包括数据目录、配置文件、
访问 URL 和 admin token 是否已配置。该页面不会读取或展示 `.env` 内容。

手动部署流程如下。

准备 `.env`：

```bash
cp .env.example .env
```

建议在 `.env` 中设置：

```text
SERVER_IP=192.168.1.168
SYNABOOT_HTTP_BIND=18080
SYNABOOT_HTTP_PORT=18080
SYNABOOT_ADMIN_TOKEN=请替换为强随机token
```

初始化目录并做安全预检：

```bash
bash init-directories.sh
bash scripts/preflight/check-release-scope.sh
bash scripts/preflight/check-private-commercial-scope.sh
bash scripts/preflight/check-edition-boundary.sh
bash scripts/preflight/check-public-runtime-boundary.sh
bash scripts/preflight/check-network-safety.sh
bash scripts/preflight/check-compose-config-safe.sh
```

发布前可收集免费版证据摘要：

```bash
bash scripts/preflight/collect-release-evidence.sh
```

该命令只读运行，不启动服务，不读取 `.env` 内容，不写日志或构建产物。
它会校验免费版 manifest 的关键字段，并输出商业相关关键词命中文件清单，
供 `git_audit_agent` 在 commit/push 前复核。
它也会确认商业私有目录、license 和混淆产物没有进入免费版 Git 发布范围。

完整发布检查清单见：

```text
docs/FREE_RELEASE_CHECKLIST.md
```

版本边界决策记录见：

```text
docs/EDITION_BOUNDARY_DECISION.md
```

启动服务：

```bash
docker compose up -d
```

访问：

- Web UI：`http://192.168.1.168:18080/`
- 镜像仓库：`http://192.168.1.168:18080/images/`
- iPXE 菜单：`http://192.168.1.168:18080/boot/menu.ipxe`

如果宿主机 `18080/tcp` 已被占用，请先确认端口归属。不要通过修改防火墙、路由、网关、DNS、DHCP 或交换机配置绕过冲突。

本机临时验证可使用 loopback 端口：

```bash
SYNABOOT_HTTP_BIND=127.0.0.1:18180 SYNABOOT_HTTP_PORT=18180 docker compose up -d --build
```

验证后关闭：

```bash
docker compose down
```

## 放置镜像

所有镜像都放在 `data/images` 下。

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

HotPE 需要：

```text
data/images/pe/hotpe/
├── wimboot
├── bootmgr
├── BCD
├── boot.sdi
└── boot.wim
```

Ubuntu/Linux 需要同一目录下同时具备 ISO、kernel、initrd 和 livefs：

```text
data/images/linux/ubuntu-22.04.3/
├── ubuntu-22.04.3-desktop-amd64.iso
└── casper/
    ├── vmlinuz
    ├── initrd
    └── *.squashfs

data/images/linux/ubuntu-24.04/
├── ubuntu-24.04.3-desktop-amd64.iso
└── casper/
    ├── vmlinuz
    ├── initrd
    └── *.squashfs
```

Windows ISO/WIM/ESD 放入 `data/images/windows/` 后，默认通过 HotPE 辅助安装，不作为通用直接启动项。

真实 ISO 放好后，可运行服务级 smoke test：

```bash
bash scripts/preflight/check-real-iso-smoke.sh
```

该脚本会启动 Compose、扫描 4 个真实 ISO、检查 Web UI/API/菜单/镜像仓库，
并默认执行 `docker compose down`。如需保留服务用于手工查看，可设置
`SYNABOOT_SMOKE_KEEP_RUNNING=1`。

## 扫描与菜单

镜像放入 `data/images` 后，在 Web UI 点击“扫描镜像”，输入 `SYNABOOT_ADMIN_TOKEN`。

不建议在 shell 命令历史中写入管理员 token。需要脚本化管理时，应使用受控
本机会话，并避免把 `.env`、终端输出或 token 截图提交到 Git、工单或聊天。

扫描会生成：

- 文件大小。
- `mtime_ns`。
- SHA256。
- `scan_status`。
- `boot_readiness`。
- `menu_enabled`。

只有满足以下条件的条目会进入 iPXE 菜单：

```text
scan_status=present
boot_readiness=ready
menu_enabled=true
```

生成菜单后可查看：

```bash
curl http://192.168.1.168:18080/boot/menu.ipxe
```

## 自动安装草稿

Web UI 的“自动安装”页面可以创建 Ubuntu 和 Windows 自动安装模板草稿。

当前免费版边界：

- 只保存模板草稿、变量白名单和模板预览。
- 不限制基础草稿创建和预览数量。
- 默认不绑定启动菜单。
- 默认不生成清盘、分区、格式化策略。
- 默认不执行无人值守安装。
- 模板用于真实装机前必须由管理员人工审查。
- “绑定规划”只读展示可作为未来绑定候选的 Windows/Linux ISO 和兼容草稿数量，
  并列出同系统类型的兼容草稿；这些候选对不会保存为绑定关系，也不会接入启动菜单。

高级脚本库、多脚本绑定、默认策略、超时策略、按主机匹配和审计报表属于后续商业版候选能力；
基础装机、镜像扫描和手动启动流程保持免费。

## 版本能力边界

Web UI 的“版本能力”页面读取 `config/synaboot/capabilities.free.json`，
展示免费核心能力、免费版不限项、未来商业候选能力，以及禁止进入 GitHub
免费发布线的内容。

同一页面也会读取 `config/synaboot/editions.public.json`，展示 Free、
Professional、Enterprise 和 Usage-based 的第一版公开边界。

当前阶段该页面只做公开说明：

- 不实现 license。
- 不实现支付。
- 不接入联网授权。
- 不阻断免费核心流程。
- 不包含商业源码或混淆产物。

## 启动客户端

iPXE Shell 中执行：

```ipxe
chain http://192.168.1.168:18080/boot/menu.ipxe
```

或使用支持手动 URL 的 UEFI HTTP Boot，输入同一菜单地址。

进入 SynaBoot 菜单后：

1. 使用方向键选择可启动条目。
2. 选择 HotPE 可进入 PE 环境。
3. 选择 Linux installer 可通过 HTTP 加载 kernel、initrd 和 ISO。
4. Windows 镜像请选择 Windows via HotPE，进入 HotPE 后再访问 Windows 镜像仓库。
5. 若菜单中没有目标镜像，请回到 Web UI 检查 `scan_status`、`boot_readiness` 和 `menu_enabled`。

如需准备 iPXE 启动介质，可查看脚本说明：

```bash
bash scripts/create-ipxe-usb.sh
```

该脚本只输出制作说明，不会格式化磁盘。

## HotPE 与 Windows

推荐流程：

1. 从 SynaBoot 菜单启动 HotPE。
2. 在 HotPE 内访问：

```text
http://192.168.1.168:18080/images/windows/
```

3. 手动打开 Windows ISO/WIM/ESD 进行安装或维护。

Samba 默认关闭。若后续启用 Samba，必须先通过 `network_safety_agent` 审查，并保持只读共享 `data/images`。

## Image Factory

二期提供安全任务框架：

- `ubuntu-autoinstall-template`
- `ubuntu-xorriso-iso`
- `windows-adk-package`

任务输出位于：

```text
data/builds/<job-id>/
```

安全边界：

- 不自动格式化磁盘。
- 不自动分区。
- 不向真实块设备写入。
- Ubuntu autoinstall 默认不生成 `storage:` 自动分区配置。
- Windows ADK/DISM 只生成外部 Windows 构建机任务包。

## 常见问题

为什么普通 PXE 找不到 SynaBoot？

因为零侵入模式不修改现有 DHCP，也不启用 ProxyDHCP/TFTP。请使用 iPXE 启动介质、手动 UEFI HTTP Boot，或外部管理员已存在的 chain 入口。

为什么 Windows 镜像显示 `needs_hotpe`？

Windows ISO/WIM/ESD 不作为通用 iPXE 直接启动项。推荐先启动 HotPE，再从 HTTP 镜像仓库访问 Windows 镜像。

为什么扫描按钮需要 token？

扫描会写入 `data/metadata` 并可能重新生成 `data/boot/menu.ipxe`，属于管理操作，必须使用 `SYNABOOT_ADMIN_TOKEN`。

## 更多文档

- `PLAN.md`：开发计划和二期里程碑。
- `AGENTS.md`：项目级 Codex 安全和协作规则。
- `docs/ADMIN_GUIDE.md`：管理员部署、镜像管理、菜单生成和维护教程。
- `docs/USER_GUIDE.md`：用户启动电脑、选择系统和安装系统教程。
- `docs/ARCHITECTURE.md`：架构说明与图例。
- `docs/NETWORK_SAFETY.md`：网络安全边界。
- `docs/FREE_RELEASE_CHECKLIST.md`：免费版发布前检查清单。
- `docs/PRIVATE_COMMERCIAL_FLOW.md`：私有商业功能、混淆打包和免费发布线隔离边界。
- `docs/BOOT_ENTRY_INTEGRATION.md`：Phase 3 启动入口集成门禁。
- `docs/BOOT_ENTRY_LOCAL_VERIFICATION.md`：本地设备能力确认记录。
- `docs/PROXYDHCP_FEASIBILITY.md`：受控 ProxyDHCP 可行性评估。
- `docs/PROXYDHCP_PACKET_REVIEW.md`：未来经审批隔离验证的报文字段判读标准。
- `docs/TFTP_LOADER_SCOPE.md`：未来 TFTP loader 文件范围。
- `docs/PHASE3_ROLLBACK_CHECKLIST.md`：Phase 3 回滚证据清单。
- `docs/PHASE3_REVIEW_TEMPLATES.md`：网络安全与安全审计模板。
- `docs/HOTPE_INTEGRATION.md`：HotPE 集成说明。
- `docs/IMAGE_FACTORY.md`：镜像工厂说明。
