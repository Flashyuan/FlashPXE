# SynaBoot 项目开发计划（Codex Goal Mode）

> 项目目标：在 **保证现有局域网不断网、主 DHCP 仍由 TP-Link TL-ER6120T 承担、默认网关保持 192.168.1.4 OpenWrt** 的前提下，在一台 Ubuntu 22.04 服务器上部署一个局域网内部可访问的 iPXE/HTTP Boot 系统安装平台。用户可像 Ventoy 一样选择多个系统镜像进行安装，支持 HotPE、Windows 11、Ubuntu 22.04.3 等镜像，并支持后续制作/封装预装软件、驱动和配置的自定义镜像。

---

## 2026-06-17 实验环境启动安装结论

实验环境已经验证 Windows 11、HotPE、Ubuntu 22.04.3 Desktop、Ubuntu 24.04 Desktop 均可通过 FlashPXE 进入对应安装/启动流程。正式菜单收敛为四个镜像入口，不再显示 HTTP RAM fallback 和 Diagnostics。

关键结论：

- Windows 安装：通过 `wimboot + Windows boot.wim` 进入安装器，SMB 仅用于进入 PE 后访问 Windows 镜像和模块目录。
- HotPE 启动：通过 `wimboot + bootmgfw.efi + BCD + boot.sdi + boot.wim` 启动；诊断入口只保留在排错记录中，不进入正式菜单。
- Ubuntu Desktop：通过 HTTP 加载 `casper/vmlinuz` 和 `casper/initrd`，通过只读 NFS 提供 casper livefs；不得再使用 SMB/CIFS 作为 Ubuntu livefs 来源。
- Ubuntu Desktop NFS 目录必须包含 `.disk/casper-uuid-generic`、`.disk/info`、`casper/*.squashfs`，并保证匿名只读可读。
- HTTP ISO RAM fallback 会在低内存客户端出现 `No space left on device`，仅可作为临时诊断，不作为正式部署路径。
- 实验 NFS 采用独立 macvlan 地址，避免 Docker bridge/端口映射导致 NFSv3 RPC 语义不完整；真实环境建议使用独立受控 NFS 地址或单独实验网段 VM。

详细复盘见：`docs/BOOT_INSTALL_ISSUES_SUMMARY.md`。

---

## 0. 最高优先级安全原则

本项目运行在生产办公局域网内，任何可能影响现有网络通信的行为都必须先审查、再变更、可回滚。Phase 1/2 继续保持零侵入；Phase 3 允许在明确审批后做受控网络启动集成，但不得让局域网断网，不得迁移主 DHCP，不得改变默认网关。

### 0.1 绝对禁止

任何 agent、脚本、服务、Docker Compose、安装命令，都不得执行以下操作：

- 不得安装、启动、启用 DHCP Server。
- 不得让 SynaBoot 取代 TP-Link TL-ER6120T 成为 DHCP 地址分配服务器。
- 不得将 DHCP 默认网关从 `192.168.1.4` 改为其他地址。
- 不得修改 OpenWrt 网关、路由、NAT、防火墙、DNS 转发等生产转发路径。
- 不得修改主机 DNS。
- 不得修改交换机、AP、VLAN、STP、端口隔离、ACL 配置。
- 不得执行 `iptables`、`nft`、`ufw`、`firewalld`、`route`、`ip route add/change/del`、`nmcli connection modify` 等会改变现有网络路径/防火墙/路由的命令。
- 不得让 Docker 容器使用 `network_mode: host`，除非 NetworkSafetyAgent 明确批准。
- 不得在未审批、未维护窗口、未回滚方案的情况下监听 UDP 67/68/69/4011。
- 不得在未审批的情况下启用 ProxyDHCP、TFTP、DHCPv6 Boot 服务。
- 不得在未审批的情况下修改 TP-Link 企业路由器 DHCP 启动选项。
- 不得让任何服务成为默认网关、DNS 或 DHCP。

### 0.1.1 Phase 3 受控允许项

为实现 BIOS/UEFI 中 `UEFI: HTTP IPv4`、`UEFI: PXE IPv4`、`UEFI: HTTP IPv6`、`UEFI: PXE IPv6` 自动进入 SynaBoot，Phase 3 允许在审批后引入以下能力：

- 在 TP-Link TL-ER6120T 的 DHCP 中只增加网络启动相关 Option，不改变地址池、租约、DNS、网关。
- 在 SynaBoot 服务器上提供 HTTP Boot loader、iPXE loader、TFTP bootfile、可选 ProxyDHCP。
- 允许监听启动所需端口，但必须默认关闭、显式启用、可回滚，并由 `network_safety_agent` 和 `security_audit_agent` 双审查。
- 允许为 IPv6 HTTP/PXE Boot 设计 DHCPv6/RA 前提检查，但不得自动改 OpenWrt 或主路由 IPv6 配置。

### 0.2 必须确认安全后才能执行

涉及以下内容时必须先由 `network_safety_agent` 审查：

- Docker Compose 端口映射。
- Samba/SMB 服务端口。
- HTTP/HTTPS 服务端口。
- 是否绑定到 `0.0.0.0`。
- 是否使用特权容器。
- 是否需要挂载 `/var/run/docker.sock`。
- 是否需要访问宿主机网络。
- 是否需要读取或写入系统目录。
- 是否需要安装系统服务。
- 是否需要以 root 运行脚本。

### 0.3 本项目一期网络策略

一期只允许做：

- HTTP/HTTPS 镜像仓库。
- iPXE 启动脚本服务。
- Web 管理页面。
- 可选 Samba 镜像共享。
- 本地文件存储。
- Docker Compose 部署。

一期不做：

- 传统 PXE DHCP。
- ProxyDHCP。
- TFTP 网络启动。
- 自动接管网络启动。
- DHCP Option 66/67。
- VLAN。
- 跨网段 PXE。
- 路由器/交换机联动。

---

## 1. 项目名称

项目名：`SynaBoot`

目标定位：

```text
SynaBoot = iPXE HTTP Boot 平台 + 镜像仓库 + HotPE 集成 + Windows/Linux 安装入口 + 镜像制作工厂
```

---

## 2. 用户侧体验目标

### 2.1 一期用户启动方式

由于现有主路由已经提供 DHCP，且当前不允许影响现网 DHCP，一期采用零侵入启动方式：

方式 A：iPXE USB/ISO/EFI 启动

```text
用户开机
  ↓
按 F12 / F11 / ESC / Boot Menu
  ↓
选择 U 盘或 iPXE 启动项
  ↓
iPXE 自动访问 http://<SYNABOOT_SERVER_IP>:18080/boot/menu.ipxe
  ↓
显示 SynaBoot 菜单
  ↓
选择 HotPE / Windows / Ubuntu / 工具
```

方式 B：UEFI HTTP Boot 手动 URL（如果设备 BIOS 支持）

```text
用户开机
  ↓
进入 UEFI HTTP Boot
  ↓
输入或选择 http://<SYNABOOT_SERVER_IP>:18080/boot/ipxe.efi 或 menu.ipxe
  ↓
进入菜单
```

> 注意：在不改 DHCP 的前提下，普通“网卡 PXE 启动”不会自动找到 SynaBoot 服务器。因此一期用户需要 iPXE 启动介质或设备支持手动 UEFI HTTP Boot URL。

### 2.2 预期启动菜单

```text
====================================================
                  SynaBoot v1.0
          Internal OS Deployment Platform
====================================================

[PE / Recovery]
  1. HotPE
  2. WePE / Custom PE

[Windows]
  3. Windows 11 24H2 ISO
  4. Windows 11 Workstation Custom Image
  5. Windows Server 2025 ISO

[Linux]
  6. Ubuntu 22.04.3 Installer
  7. Ubuntu 24.04 LTS Installer
  8. Debian Installer

[Tools]
  9. Clonezilla
  10. Memtest86+
  11. Reboot
  12. Poweroff

====================================================
Use ↑ ↓ to select, Enter to boot.
Images are managed by SynaBoot Web UI.
====================================================
```

---

## 3. 服务器部署环境

目标服务器：

- OS：Ubuntu 22.04 LTS
- 部署方式：Docker Compose
- 局域网网段：`192.168.1.0/24`
- SynaBoot 服务 IP：由管理员指定，例如 `192.168.1.168` 或其他固定 IP
- 访问方式：
  - Web UI：`http://<SERVER_IP>:18080`
  - 镜像 HTTP 仓库：`http://<SERVER_IP>:18080/images/`
  - iPXE 菜单：`http://<SERVER_IP>:18080/boot/menu.ipxe`
  - Samba 共享（可选）：`\\<SERVER_IP>\images`

---

## 4. 目录规划

项目仓库目录：

```text
synaboot/
├── AGENTS.md
├── PLAN.md
├── README.md
├── docker-compose.yml
├── .env.example
├── .codex/
│   ├── config.toml
│   └── agents/
│       ├── network-safety-agent.toml
│       ├── architecture-agent.toml
│       ├── boot-entry-agent.toml
│       ├── storage-agent.toml
│       ├── image-factory-agent.toml
│       ├── webui-agent.toml
│       └── security-audit-agent.toml
├── apps/
│   ├── api/
│   ├── web/
│   └── worker/
├── config/
│   ├── nginx/
│   ├── samba/
│   └── synaboot/
├── data/
│   ├── images/
│   │   ├── pe/
│   │   │   ├── hotpe/
│   │   │   └── wepe/
│   │   ├── windows/
│   │   │   ├── win11/
│   │   │   └── winserver/
│   │   ├── linux/
│   │   │   ├── ubuntu-22.04.3/
│   │   │   └── ubuntu-24.04/
│   │   ├── tools/
│   │   └── custom/
│   ├── boot/
│   │   ├── menu.ipxe
│   │   ├── loaders/
│   │   └── templates/
│   ├── builds/
│   ├── metadata/
│   └── logs/
├── scripts/
│   ├── preflight/
│   ├── generate-ipxe-menu.sh
│   ├── create-ipxe-usb.sh
│   └── sync-metadata.sh
└── docs/
    ├── USER_GUIDE.md
    ├── HOTPE_INTEGRATION.md
    ├── IMAGE_FACTORY.md
    └── NETWORK_SAFETY.md
```

实际镜像统一放入：

```text
./data/images/
```

---

## 5. 核心功能模块

## 5.1 Web 管理平台

功能：

- 镜像列表展示。
- 镜像分类：PE、Windows、Linux、Tools、Custom。
- 镜像元数据维护：
  - 名称
  - 类型
  - 版本
  - 架构
  - 文件路径
  - 文件大小
  - SHA256
  - 描述
  - 是否显示在启动菜单
  - 启动方式
- 生成 iPXE 菜单。
- 展示 HotPE 访问 Windows 镜像的说明。
- 展示 iPXE 启动介质制作说明。
- 展示安全状态检查结果。
- 后续支持构建任务管理。

技术建议：

- 后端：FastAPI
- 前端：Vue 3 或 React
- 数据库：SQLite 起步，后续可换 PostgreSQL
- 静态文件服务：Nginx
- 部署：Docker Compose

一期可以先做极简 UI：

```text
镜像列表
上传/登记镜像
启用/禁用菜单项
生成 menu.ipxe
查看启动 URL
查看 Samba 地址
```

---

## 5.2 iPXE HTTP Boot

必须实现：

- `GET /boot/menu.ipxe`
- `GET /boot/loaders/ipxe.efi`
- `GET /boot/loaders/ipxe.iso`
- `GET /images/...`

`menu.ipxe` 由平台生成。

样例：

```ipxe
#!ipxe

set server_ip ${next-server}
set base-url http://192.168.1.168:18080

:start
menu SynaBoot v1.0 - Internal OS Deployment Platform
item --gap -- PE / Recovery
item hotpe HotPE - Windows PE Environment
item --gap -- Windows
item win11 Windows 11 24H2 ISO via HotPE
item --gap -- Linux
item ubuntu2204 Ubuntu 22.04.3 Installer
item --gap -- Tools
item reboot Reboot
item shell iPXE Shell
choose --default hotpe --timeout 30000 target && goto ${target}

:hotpe
echo Loading HotPE...
kernel ${base-url}/images/pe/hotpe/wimboot
initrd ${base-url}/images/pe/hotpe/bootmgr bootmgr
initrd ${base-url}/images/pe/hotpe/BCD BCD
initrd ${base-url}/images/pe/hotpe/boot.sdi boot.sdi
initrd ${base-url}/images/pe/hotpe/boot.wim boot.wim
boot

:ubuntu2204
echo Loading Ubuntu 22.04.3 installer...
kernel ${base-url}/images/linux/ubuntu-22.04.3/casper/vmlinuz ip=dhcp url=${base-url}/images/linux/ubuntu-22.04.3/ubuntu-22.04.3-live-server-amd64.iso
initrd ${base-url}/images/linux/ubuntu-22.04.3/casper/initrd
boot

:win11
echo Windows ISO should be installed from HotPE.
echo Boot HotPE, then open \\192.168.1.168\images or http://192.168.1.168:18080/images/windows/
goto hotpe

:reboot
reboot

:shell
shell
```

> 注意：Windows ISO 不建议直接通过 iPXE 原生启动安装。推荐先启动 HotPE，然后从 Samba/HTTP 镜像仓库访问 Windows ISO 或 WIM 文件进行安装。

---

## 5.3 HotPE 集成

目标：

用户选择 HotPE 后进入 PE 环境，HotPE 内可以访问平台中的 Windows 镜像。

需要支持两种访问方式：

### 方式 A：Samba 共享

共享地址：

```text
\\<SERVER_IP>\images
```

HotPE 内手动执行：

```bat
net use Z: \\192.168.1.168\images
```

如需要用户名密码：

```bat
net use Z: \\192.168.1.168\images /user:synaboot readonly-password
```

然后用户在 Z 盘中访问：

```text
Z:\windows\win11\Windows11_24H2.iso
Z:\windows\win11\sources\install.wim
```

### 方式 B：HTTP 下载/访问

访问：

```text
http://192.168.1.168:18080/images/windows/
```

HotPE 中可用浏览器或下载工具打开。

一期推荐：

- HTTP 必做。
- Samba 可选。
- Samba 启动前必须检查宿主机端口 445/139/137/138 是否被占用。
- Samba 只能共享 `./data/images`。
- Samba 账号只读优先。
- 不允许匿名写入。

---

## 5.4 Windows 镜像支持

一期支持手动放置：

```text
data/images/windows/win11/Windows11_24H2.iso
data/images/windows/win11/README.txt
```

HotPE 进入后，用户从 Samba 或 HTTP 访问。

二期支持：

- `install.wim` 展示。
- `install.esd` 展示。
- Windows 版本识别。
- 驱动包管理。
- Autounattend.xml 模板。
- DISM 注入驱动。
- DISM 注入更新补丁。
- 生成自定义 ISO。

---

## 5.5 Ubuntu/Linux 镜像支持

一期支持：

- 手动放入 Ubuntu ISO。
- 从 ISO 中提取 `casper/vmlinuz` 和 `casper/initrd` 到对应目录。
- 通过 iPXE 加载内核和 initrd。
- ISO 通过 HTTP 提供给安装器。

示例目录：

```text
data/images/linux/ubuntu-22.04.3/
├── ubuntu-22.04.3-live-server-amd64.iso
└── casper/
    ├── vmlinuz
    └── initrd
```

二期支持：

- 自动挂载 ISO 并提取内核。
- Subiquity autoinstall。
- cloud-init user-data/meta-data。
- 预置 apt 源、用户、SSH Key、软件包。
- 生成自定义 autoinstall ISO。

---

## 5.6 镜像制作工厂

一期只做 UI 和任务框架，不直接做复杂封装。

必须实现：

- 构建任务模型。
- 构建任务日志。
- 构建任务状态：
  - pending
  - running
  - success
  - failed
- 构建输出目录：
  - `data/builds/<job-id>/`
- 构建脚本模板目录：
  - `data/boot/templates/`
  - `scripts/image-factory/`

二期实现：

### Windows

- 使用 Windows ADK / DISM 的外部工作机模式。
- Ubuntu 服务器只负责生成配置文件和任务包。
- 支持导入驱动、软件包、Autounattend.xml。
- 输出自定义 ISO 或 WIM。

注意：

- Linux 上直接完整封装 Windows ISO 能力有限。
- Windows 镜像封装推荐用 Windows 构建机或 WinPE/ADK 环境执行。
- Ubuntu 平台可以作为任务编排和镜像仓库。

### Ubuntu

- 使用 cloud-init / autoinstall。
- 使用 xorriso 重新打包 ISO。
- 支持预装软件列表。
- 支持 SSH、用户、主机名、apt 源、脚本。
- 输出自定义 Ubuntu ISO。

---

## 6. Docker Compose 设计约束

### 6.1 必须遵守

- 不使用 `network_mode: host`。
- 不使用 `privileged: true`。
- 不挂载宿主机 `/`。
- 不挂载 `/etc`。
- 不挂载 `/var/run/docker.sock`。
- 不开放 UDP 67/68/69/4011。
- 不运行 DHCP/TFTP 服务。
- 所有端口必须由 `network_safety_agent` 审查。
- 默认只开放：
  - `18080:8080/tcp` Web/HTTP 镜像服务
  - 可选 `8443:8443/tcp` HTTPS
  - 可选 Samba 端口，必须 preflight 后才允许

### 6.2 Compose 一期服务

```text
synaboot-api
synaboot-web
synaboot-nginx
synaboot-worker
synaboot-db
synaboot-samba optional
```

建议先实现最小版本：

```text
nginx + api + sqlite + worker
```

---

## 7. Preflight 安全检查

必须实现 `scripts/preflight/check-network-safety.sh`。

检查内容：

- 当前服务器 IP。
- 默认网关。
- DNS。
- 当前监听端口。
- 是否已有服务占用对外 HTTP 端口，默认 `18080/tcp`。
- 是否已有服务占用 445/139/137/138。
- 是否存在 DHCP/TFTP 端口监听。
- Docker Compose 是否包含禁止项。
- 是否包含 `network_mode: host`。
- 是否包含 `privileged: true`。
- 是否暴露 UDP 67/68/69/4011。
- 是否包含危险命令关键字：
  - `iptables`
  - `nft`
  - `ufw`
  - `firewall-cmd`
  - `ip route`
  - `route add`
  - `dhcp`
  - `dnsmasq`
  - `tftp`

若发现风险，必须直接失败并输出原因，不得继续部署。

---

## 8. Codex Subagents 分工

Codex 官方支持通过 `.codex/agents/*.toml` 定义 project-scoped custom agents。每个 agent 必须有 `name`、`description`、`developer_instructions`。本项目必须使用 subagents，并且所有代码变更都要经过安全监管。

### 8.1 research_agent

前置调查 agent。

职责：

- 调查外部事实、设备能力、协议行为和官方文档。
- 回答其他 subagents 遇到的知识库或互联网检索问题。
- 对 TL-ER6120T/TL-ER6120 的 DHCP Option、PXE、HTTP Boot 能力给出证据化结论。
- 明确区分已确认事实、推断、未知项和必须本地验证的内容。
- 不直接修改任何生产网络配置。

### 8.2 project_decision_agent

项目决策 agent。

职责：

- 代替用户把控项目方向、重大技术路线、阶段优先级和方案取舍。
- 始终围绕最终目标推进：局域网电脑通过 `UEFI: PXE IPv4` 进入 SynaBoot，选择预置 ISO/镜像并开始安装系统。
- 只在出现决策性问题时触发，不参与普通实现细节。
- 在 `research_agent`、`network_safety_agent`、`security_audit_agent` 和相关实现 agent 提供足够信息后做取舍。
- 可以批准 `git_audit_agent` 将审计通过的本地 commit push 到 GitHub 当前分支。
- 不得覆盖 `network_safety_agent` 或 `security_audit_agent` 的 `BLOCKED` 结论。
- 不得批准会影响当前局域网正常 DHCP、默认网关、内网通信或外网连接的方案。

### 8.3 network_safety_agent

最高优先级监管 agent。

职责：

- 审查所有网络相关代码、compose、脚本、文档。
- 拦截任何可能影响内网通信的行为。
- 对其他 subagents 输出的方案进行安全复核。
- 对所有端口开放、网络模式、系统命令进行审批。
- 输出明确结论：`APPROVED` 或 `BLOCKED`。

强约束：

- 只读审查优先。
- 不直接修改生产网络。
- 不得为了完成功能放宽安全要求。
- 任何不确定都必须 `BLOCKED`。

### 8.4 architecture_agent

职责：

- 设计整体架构。
- 设计目录结构。
- 设计 API。
- 设计数据库模型。
- 拆分 milestone。
- 不得修改网络配置。

### 8.5 boot_entry_agent

职责：

- 设计 iPXE menu。
- 设计 HotPE 启动项。
- 设计 Ubuntu 启动项。
- 设计 iPXE ISO/EFI 生成脚本。
- 设计 Phase 3 HTTP Boot、PXE Boot、iPXE chainload 启动链。
- 维护 `ipxe.efi`、`snponly.efi`、`undionly.kpxe` 等 boot loader 元数据。
- 遇到设备能力或协议兼容性疑问时，先请求 `research_agent` 调查。
- 不得直接修改 TP-Link、OpenWrt、交换机、AP、网关、DNS、路由、防火墙。
- ProxyDHCP/TFTP 只能作为 Phase 3 受控可选模块，默认关闭并经过双审查。

### 8.6 storage_agent

职责：

- 设计镜像目录。
- 设计 HTTP 静态文件服务。
- 设计可选 Samba 共享。
- 实现镜像扫描、hash、元数据。
- Samba 变更必须先让 network_safety_agent 审查。

### 8.7 image_factory_agent

职责：

- 设计镜像制作任务系统。
- 设计 Ubuntu autoinstall 镜像制作流程。
- 设计 Windows ADK/DISM 外部构建流程。
- 不得在 Ubuntu 上假装可以完整无风险封装所有 Windows 镜像。
- 必须明确哪些任务需要 Windows 构建机。

### 8.8 webui_agent

职责：

- 实现 Web UI。
- 实现镜像管理页面。
- 实现启动菜单预览。
- 实现任务管理页面。
- 使用本地个人 skills 辅助 Web UI 与 API-backed 管理页面重构：
  `design-review`、`design-taste-frontend`、`frontend-design`、`shadcn-ui`、
  `tailwind-design-system`。
- `design-review` 用于 UI 改动后的视觉、交互、响应式和可访问性复核；
  需要设计评审时必须截图，不得只看代码。
- `design-taste-frontend` 只作为反模板化、文案质量、视觉层级和响应式自检清单；
  SynaBoot 是运维/装机管理后台，不得强行套用 landing page、portfolio 或
  marketing hero 模式。
- `frontend-design` 用于色彩、字体、间距、信息层级和用户可理解文案。
- `shadcn-ui` 与 `tailwind-design-system` 当前已被批准用于管理后台现代化
  重构：允许采用 Vite React、TypeScript、Tailwind CSS 和 shadcn 风格的
  自有组件；不得引入外部 CDN 运行时依赖，不得加入未审查的商业授权、
  支付、订阅、联网激活或生产 LAN 开关入口。
- 不得引入公网依赖。
- 不得上传镜像到第三方。

### 8.9 tutorial_docs_agent

职责：

- 编写和维护 README、用户指南、管理员指南和架构说明。
- 绘制服务拓扑、启动链路、镜像扫描、菜单生成、subagents 协作图。
- 编写 Phase 3 自动网络启动入口集成说明。
- 固化安全边界、回滚步骤和验证方法。
- 不得编写未经审查的路由器、DHCP、ProxyDHCP、TFTP 实操教程。

### 8.10 security_audit_agent

职责：

- 审查代码安全。
- 审查权限、路径穿越、上传文件、命令执行风险。
- 审查 Docker 安全。
- 审查日志是否泄露敏感信息。
- 与 network_safety_agent 一起做最终验收。

---

## 9. Milestones

## Milestone 0：安全骨架

目标：

- 创建仓库结构。
- 创建 AGENTS.md。
- 创建 `.codex/config.toml`。
- 创建 `.codex/agents/*.toml`。
- 创建 PLAN.md。
- 创建 README.md。
- 创建 preflight 脚本初版。
- 不部署任何服务。

验收：

- `find . -maxdepth 3 -type f` 结构正确。
- `scripts/preflight/check-network-safety.sh` 可运行。
- 危险 compose 示例能被拦截。

## Milestone 1：静态镜像仓库

目标：

- Docker Compose 启动 Nginx。
- 只开放 `18080/tcp` 对外 HTTP 服务。
- 映射 `./data/images` 为 HTTP 静态目录。
- 提供 `/images/` 浏览。
- 提供 `/boot/menu.ipxe` 静态样例。

验收：

```bash
curl http://localhost:18080/
curl http://localhost:18080/boot/menu.ipxe
curl http://localhost:18080/images/
```

不得：

- 不得启动 DHCP/TFTP。
- 不得修改路由/防火墙。

## Milestone 2：镜像元数据扫描

目标：

- Worker 扫描 `data/images`。
- 识别 ISO/WIM/EFI/WIMBOOT/initrd/vmlinuz。
- 生成 SQLite 元数据。
- 生成 SHA256。
- Web API 返回镜像列表。

验收：

```bash
curl http://localhost:18080/api/images
```

## Milestone 3：动态 iPXE 菜单

目标：

- 根据启用的镜像生成 `menu.ipxe`。
- 支持 PE、Windows、Linux、Tools 分类。
- Windows 项默认提示“通过 HotPE 安装”。
- Ubuntu 项支持 vmlinuz/initrd/url 参数。
- HotPE 项支持 wimboot 模式。

验收：

```bash
curl http://localhost:18080/boot/menu.ipxe
```

## Milestone 4：HotPE 镜像访问

目标：

- Web UI 展示 HotPE 使用说明。
- 生成 `HOTPE_INTEGRATION.md`。
- 可选 Samba 服务设计，但默认不启用。
- 提供 `net use` 命令模板。
- 提供 HTTP 镜像访问路径。

验收：

- 文档清晰。
- Samba 未启用时不开放 445。
- 启用 Samba 前 preflight 通过。

## Milestone 5：Web UI

目标：

- 镜像列表。
- 镜像详情。
- 启用/禁用菜单。
- 菜单预览。
- 启动 URL 展示。
- 用户操作指南。

验收：

- 浏览器访问 `http://<SERVER_IP>:18080` 可用。
- 不需要公网。
- 不依赖外部 CDN。

## Milestone 6：镜像制作工厂框架

目标：

- 构建任务数据模型。
- 任务创建页面。
- 任务日志。
- Ubuntu autoinstall 模板。
- Windows ADK 外部构建任务包模板。

验收：

- 可以创建“构建任务”。
- 可以生成任务目录。
- 可以生成配置文件。
- 不要求一期真正完成 Windows ISO 封装。

## Milestone 7：安全验收

目标：

- network_safety_agent 审查全部文件。
- security_audit_agent 审查全部文件。
- 检查是否存在禁止端口/命令/网络模式。
- 输出 `docs/SECURITY_REVIEW.md`。

验收：

- 所有 BLOCKED 项必须修复。
- 所有网络相关行为必须有解释。
- 最终可部署方案不会影响现网通信。

---

## 10. Codex Goal Mode 启动提示

在项目根目录运行 Codex 后，使用以下 Goal：

```text
/goal 按 PLAN.md 开发 SynaBoot。必须使用 subagents：
1. 先让 research_agent 调查不确定的外部事实、设备能力和协议限制。
2. 决策性问题交给 project_decision_agent，代替用户把控方向和重大取舍。
3. 再让 network_safety_agent 审查 PLAN.md、AGENTS.md、docker-compose.yml、所有脚本的网络安全边界。
4. 让 architecture_agent 设计最小可用架构和目录。
5. 让 boot_entry_agent 实现 iPXE HTTP Boot 菜单生成；Phase 1/2 严禁 DHCP/ProxyDHCP/TFTP。
6. 让 storage_agent 实现 data/images 镜像仓库扫描和 HTTP 静态访问。
7. 让 webui_agent 实现最小 Web UI。
8. 让 image_factory_agent 只实现镜像制作任务框架和 Ubuntu autoinstall 模板，不要承诺 Linux 上完整封装 Windows ISO。
9. 让 tutorial_docs_agent 维护 README、架构说明、用户教程和安全边界文档。
10. 最后让 security_audit_agent 和 network_safety_agent 共同审查所有变更。
11. 每完成一个功能或 milestone 后，让 git_audit_agent 审查 diff；通过后可准备本地 commit；push 当前 GitHub 分支前必须经 project_decision_agent 批准并获得用户二次确认。

强制要求：
- 不得修改 DHCP。
- 不得启用 ProxyDHCP。
- 不得启用 TFTP。
- 不得修改路由、防火墙、网关、DNS。
- 不得使用 host network。
- 不得使用 privileged 容器。
- 不得开放 UDP 67/68/69/4011。
- 所有网络相关变更必须先审查后执行。
- 如果不确定是否影响局域网通信，必须停止并标记 BLOCKED。
- 一期只实现 iPXE HTTP Boot + HTTP 镜像仓库 + HotPE 访问镜像 + Web UI + 镜像制作任务框架。
```

---

## 11. 手动放置镜像规则

你后续手动放入镜像时，建议路径如下：

### HotPE

```text
data/images/pe/hotpe/
├── wimboot
├── bootmgr
├── BCD
├── boot.sdi
└── boot.wim
```

### Windows 11

```text
data/images/windows/win11/
└── Windows11_24H2.iso
```

### Ubuntu 22.04.3

```text
data/images/linux/ubuntu-22.04.3/
├── ubuntu-22.04.3-live-server-amd64.iso
└── casper/
    ├── vmlinuz
    └── initrd
```

### 工具

```text
data/images/tools/
├── clonezilla/
└── memtest/
```

---

## 12. 非目标说明

本项目一期不解决：

- 裸机按 F12 选择普通 PXE 后自动进入平台。
- 传统 PXE DHCP 自动发现。
- 跨网段 PXE。
- 路由器 Option 66/67 自动下发。
- WDS/MDT 完整替代。
- Windows 镜像在 Linux 上完整无人工封装。
- 生产环境自动格式化磁盘。
- 无确认无人值守安装。

这些功能后续可以在确认安全和审批后再做。

---

## 13. 最终验收标准

项目一期完成后，应满足：

- 在 Ubuntu 22.04 上通过 Docker Compose 启动。
- 不改变现有局域网 DHCP/路由/DNS/防火墙。
- Web UI 可访问。
- `/boot/menu.ipxe` 可访问。
- `/images/` 可访问。
- 用户可通过 iPXE USB/ISO/EFI 进入菜单。
- 菜单中可选择 HotPE。
- HotPE 中可访问平台 Windows 镜像。
- Ubuntu 镜像可通过 iPXE 引导安装。
- Windows ISO 可通过 HotPE 访问安装。
- 镜像制作工厂有任务框架和模板。
- 有完整安全审查文档。

---

## 14. 二期开发前提

二期开发在一期已经完工的基础上继续推进。

一期已完成的基础能力包括：

- Docker Compose 友好的基础服务骨架。
- HTTP 镜像仓库。
- `/boot/menu.ipxe` iPXE 菜单入口。
- `/images/` 静态镜像访问入口。
- 基础 Web UI。
- 基础 API/Worker 框架。
- `data/images`、`data/boot`、`data/metadata`、`data/builds` 等数据目录。
- 网络安全 preflight 检查。
- `.codex/agents` 项目级 subagents 基础定义。

二期不得推翻一期安全边界。

二期目标是把一期基础平台增强为可实际部署、可扫描镜像、可生成菜单、可教学交付的零侵入 HTTP/iPXE Boot 平台。

后续二期代码开发必须通过 `/goal` 启动，并按本 `PLAN.md` 的二期进度执行。

---

## 15. 二期网络安全模型

二期继续采用零侵入网络模型。

默认服务地址：

```text
SERVER_IP=192.168.1.168
Web UI=http://192.168.1.168:18080/
镜像仓库=http://192.168.1.168:18080/images/
iPXE 菜单=http://192.168.1.168:18080/boot/menu.ipxe
```

二期允许的启动方式：

1. iPXE USB/ISO/EFI 启动介质。
2. 手动 UEFI HTTP Boot。
3. 外部管理员已经配置好的 PXE/iPXE chain 入口。

第三种只表示 SynaBoot 提供 HTTP 菜单 URL：

```text
http://192.168.1.168:18080/boot/menu.ipxe
```

SynaBoot 本身不配置、不修改、不接管外部 PXE 环境。

二期明确不做：

- 普通 PXE 自动发现。
- DHCP Server。
- ProxyDHCP。
- TFTP。
- 路由器 DHCP Option 66/67 配置。
- OpenWrt、TP-Link、交换机、AP、VLAN、DNS、路由、防火墙配置。
- 跨网段 PXE/DHCP Relay。
- Docker `network_mode: host`。
- Docker `privileged: true`。
- UDP 67/68/69/4011 端口开放。

任何涉及端口、Compose 网络、Samba、HTTP 监听地址、PXE 文档表述的变更，都必须先由 `network_safety_agent` 审查。

---

## 16. 二期 Subagents 编排

二期开发必须开启 subagents 模式。

所有 subagent 输出都必须包含：

- `APPROVED` 或 `BLOCKED` 结论。
- 关键假设。
- 涉及文件或模块。
- 风险点。
- 建议验证命令。

冲突处理规则：

- `network_safety_agent` 与 `security_audit_agent` 优先级最高。
- 只要网络安全或安全审计输出 `BLOCKED`，相关开发必须停止。
- `project_decision_agent` 负责方向、优先级和重大取舍，但不得绕过安全 agent 的限制。
- 其他 agent 的方案不得绕过安全 agent 或决策 agent 的限制。

### 16.1 research_agent

二期/三期前置调查 agent。

职责：

- 调查框架、协议、设备、固件、loader 等外部事实。
- 当其他 agent 遇到知识库或互联网问题时，负责检索并反馈证据化结论。
- 不直接做架构决策，不直接修改代码，不修改生产网络配置。

### 16.2 project_decision_agent

项目决策 agent。

触发条件：

- 多个技术路线都可行，需要选择方向。
- agent 之间结论冲突，但没有安全 BLOCKED。
- 需要决定某项功能进入当前阶段、后续阶段还是放弃。
- 需要决定是否从 TP-Link DHCP Boot Option 切换到受控 ProxyDHCP。
- `git_audit_agent` 准备推送阶段性 commit，需要确认是否符合项目方向。

职责：

- 代替用户把控项目方向、阶段目标、重大取舍和优先级。
- 将最终目标固定为 `UEFI: PXE IPv4 -> SynaBoot 菜单 -> 选择预置 ISO/镜像 -> 开始安装系统`。
- 在不影响现有局域网 DHCP、网关、内网通信和外网连接的前提下做决策。
- 对被批准的方向输出条件、后续参与 agent 和验证要求。
- 不覆盖 `network_safety_agent` 或 `security_audit_agent` 的 `BLOCKED`。

### 16.3 network_safety_agent

前置审查 agent。

职责：

- 审查所有网络相关计划、代码、Compose、脚本、文档。
- 审查 Samba 是否仍为默认关闭。
- 审查是否存在 DHCP/ProxyDHCP/TFTP/UDP 67/68/69/4011。
- 审查是否存在 host network、privileged、危险挂载、路由/防火墙命令。

### 16.4 architecture_agent

架构统筹 agent。

职责：

- 基于一期已完成代码继续拆分二期模块。
- 定义 API、元数据、任务状态、菜单生成的数据流。
- 保持现有轻量架构，不在二期强行迁移 FastAPI/React/Vue。

### 16.5 storage_agent

镜像仓库 agent。

职责：

- 设计并实现 `data/images` 本地扫描。
- 维护镜像元数据。
- 维护 SHA256 缓存。
- 判断镜像启动就绪状态。
- 拒绝路径穿越、绝对路径、软链接越界。

### 16.6 boot_entry_agent

HTTP/iPXE agent。

职责：

- 设计元数据驱动的 `menu.ipxe`。
- 只生成 HTTP/iPXE 菜单。
- 支持 HotPE、Ubuntu/Linux、Tools。
- Windows ISO/WIM 只生成 HotPE 辅助安装说明，不伪装成通用直接启动。
- 保留 `shell`、`reboot`、`poweroff`、`boot_failed` 等安全入口。
- Phase 3 设计 HTTP Boot/PXE Boot/iPXE chainload 参数，但不得直接修改生产网络设备。

### 16.7 webui_agent

Web UI agent。

职责：

- 沿用现有轻量静态 Web。
- 不引入外部 CDN。
- 2026-06-16 起，管理后台前端允许采用 React + TypeScript + Tailwind CSS
  的现代主题重构；免费版发布线仍不得加入商业授权、支付、订阅、联网激活或
  生产 LAN 自动启用入口。
- 实现 Dashboard、镜像仓库、镜像详情、菜单预览、HotPE 指南、构建任务、网络安全页。
- 所有写操作必须通过 admin token。
- 后续 Web UI/网页后端联动重构必须使用本地个人 skills 作为检查框架：
  `design-review`、`design-taste-frontend`、`frontend-design`、`shadcn-ui`、
  `tailwind-design-system`。
- 这些 skills 已被授权用于管理后台现代化迁移；Tailwind/shadcn/React
  迁移必须经过 `security_audit_agent` 和 `git_audit_agent` 审查，且不能
  破坏免费核心能力、镜像数据边界和网络安全边界。

### 16.8 image_factory_agent

镜像工厂 agent。

职责：

- 设计 Ubuntu autoinstall 模板任务。
- 设计 Ubuntu ISO 重打包任务。
- 设计 Windows ADK/DISM 外部构建任务包。
- 不在 Linux 容器内承诺完整封装 Windows ISO。
- 不执行真实磁盘格式化、分区、写盘。

### 16.9 tutorial_docs_agent

二期新增文档 agent。

需要新增定义文件：

```text
.codex/agents/tutorial-docs-agent.toml
```

职责：

- 梳理项目框架和架构说明书。
- 产出总体架构图、启动链路图、镜像扫描流程图、菜单生成流程图、任务状态图、subagents 协作图。
- 产出对外教学用 `README.md`。
- 将 network safety 和 security audit 的结论固化进文档。

禁止：

- 不得写 DHCP/ProxyDHCP/TFTP 配置教程。
- 不得写路由器、OpenWrt、TP-Link、交换机、AP、VLAN、防火墙修改步骤。
- 不得暗示 SynaBoot 能在零侵入模式下自动接管普通 PXE 客户端。
- 不得包含真实 token、真实账号密码或敏感内网信息。

### 16.10 security_audit_agent

最终安全审计 agent。

职责：

- 审查路径穿越、命令注入、权限绕过、日志泄露、token 暴露。
- 审查 Docker Compose 安全。
- 审查文档是否存在危险网络操作指引。
- 与 `network_safety_agent` 一起完成二期最终验收。

### 16.11 git_audit_agent

阶段收口与 Git 审计 agent。

职责：

- 每完成一个功能、一个 milestone 或一组阶段性代码后自动介入。
- 审查 git diff、暂存范围、未跟踪文件和生成文件。
- 确认无无关文件、无秘密信息、无危险网络变更。
- 确认必要验证命令已经执行，或明确记录未执行原因。
- 审计通过后可在用户确认范围内 stage 并创建本地 commit。
- commit message 必须说明阶段目标、核心变更和安全边界。
- 若变更涉及网络、Compose、脚本、启动入口或安全边界，push 前必须有 `network_safety_agent` 和/或 `security_audit_agent` 的通过结论。
- push 到 GitHub 当前分支前必须记录 remote、branch、commit range、提交摘要和风险摘要。
- `project_decision_agent` 确认符合项目方向后，经用户二次确认后才可 push 到 GitHub 当前分支。
- 不得 push secrets、`.env`、真实凭据、无关文件、危险脚本或未审查的网络影响变更。

---

## 17. 二期核心功能计划

### 17.1 镜像扫描与元数据

二期采用“本地放置镜像 + Web/API 扫描登记”模式。

不做浏览器大文件上传。

镜像统一放入：

```text
./data/images/
```

扫描规则：

- 只扫描 `data/images` 内部文件。
- 拒绝绝对路径。
- 拒绝 `..` 路径穿越。
- 跳过软链接。
- 跳过隐藏临时文件。
- 按 `relative_path + size_bytes + mtime_ns` 判断 SHA256 是否可复用。
- 文件变化时重新分块计算 SHA256。

元数据至少包含：

- `id`
- `display_name`
- `category`
- `kind`
- `relative_path`
- `size_bytes`
- `mtime_ns`
- `sha256`
- `scan_status`
- `boot_method`
- `boot_readiness`
- `menu_enabled`
- `description`
- `updated_at`

启动就绪状态：

- `ready`：可进入 iPXE 菜单。
- `incomplete`：缺少启动依赖。
- `needs_hotpe`：需要先启动 HotPE。
- `unsupported`：可存储/下载，但不生成启动项。
- `missing`：元数据存在，但文件已不存在。

### 17.2 动态 iPXE 菜单

`menu.ipxe` 必须由元数据生成。

进入菜单的条件：

```text
menu_enabled=true
boot_readiness=ready
```

菜单必须支持：

- PE / Recovery。
- Windows via HotPE。
- Linux。
- Tools。
- Reboot。
- Poweroff。
- iPXE Shell。
- Boot failed fallback。

Windows 镜像处理规则：

- Windows ISO/WIM/ESD 默认标记为 `needs_hotpe`。
- 菜单中不得把 Windows ISO 伪装成可原生直接启动。
- UI 和 README 必须说明：先进入 HotPE，再通过 HTTP 或可选 Samba 访问 Windows 镜像。

Ubuntu/Linux 处理规则：

- 必须同时具备 kernel、initrd、ISO URL 等必要资源才可标记 `ready`。
- 缺少 `vmlinuz`、`initrd` 或 ISO 时标记为 `incomplete`。

### 17.3 Web UI

二期 Web UI 页面：

- Dashboard：
  - 服务地址。
  - 菜单地址。
  - 镜像数量。
  - 启动就绪数量。
  - 网络安全状态。

- 镜像仓库：
  - 扫描结果。
  - 分类筛选。
  - SHA256。
  - 启动就绪状态。
  - 菜单启用/禁用。

- 镜像详情：
  - 路径。
  - 大小。
  - SHA256。
  - 启动方式。
  - 缺失依赖提示。

- iPXE 菜单预览：
  - 查看当前 `menu.ipxe`。
  - 受保护重新生成菜单。

- HotPE 指南：
  - 说明 Windows ISO/WIM 通过 HotPE 安装。
  - 提供 HTTP 镜像访问地址。
  - Samba 只作为可选项说明。

- 构建任务：
  - Ubuntu autoinstall 模板任务。
  - Ubuntu ISO 任务。
  - Windows ADK 外部任务包。

- 网络安全：
  - 明确显示禁止项。
  - 明确 SynaBoot 不配置 DHCP/ProxyDHCP/TFTP/路由器/防火墙。

### 17.4 API 权限边界

可公开只读：

- `GET /api/health`
- `GET /api/images`
- `GET /api/images/<id>`
- `GET /api/menu`
- `GET /api/jobs`
- `GET /api/network-safety`
- `GET /images/`
- `GET /boot/menu.ipxe`

必须 admin token 保护：

- `POST /api/scan`
- `POST /api/menu/generate`
- 镜像登记。
- 镜像编辑。
- 镜像启用/禁用。
- 构建任务创建。
- 构建任务取消。
- 构建任务重试。
- 任何写入 `data/metadata`、`data/boot`、`data/builds` 的操作。

### 17.5 可选 Samba

二期可以保留 Samba 可选能力规划。

默认要求：

- 默认关闭。
- 不随 `docker compose up -d` 自动启动。
- 只能通过独立 profile 或明确命令启用。
- 启用前必须运行 preflight。
- 启用前必须由 `network_safety_agent` 审查。
- 只读共享 `data/images`。
- 不允许匿名写入。
- 不使用 host network。
- 不使用 privileged。

### 17.6 Image Factory

二期支持任务框架增强。

任务类型：

- `ubuntu-autoinstall-template`
- `ubuntu-xorriso-iso`
- `windows-adk-package`

任务目录：

```text
data/builds/<job-id>/
├── job.json
├── status.json
├── logs/
│   └── events.jsonl
├── inputs/
├── work/
├── package/
└── output/
    └── artifacts/
```

任务状态：

```text
draft -> pending -> running -> success
draft -> pending -> running -> failed
draft -> pending -> canceled
```

安全要求：

- 创建任务默认进入 `draft`。
- 执行任务必须 admin token 确认。
- Ubuntu autoinstall 默认不生成 `storage:` 自动分区配置。
- 不执行 `mkfs`、`parted`、`dd` 到真实设备。
- 不接受真实块设备路径作为目标。
- Windows ADK/DISM 只生成外部 Windows 构建机任务包。
- 日志不得记录 token、密码、私钥。

### 17.7 教程与 README

二期必须产出可对外教学的 `README.md`。

README 必须覆盖：

- SynaBoot 是什么。
- 零侵入网络边界。
- 部署前提。
- `.env` 配置。
- `SERVER_IP=192.168.1.168` 示例。
- Docker Compose 启动。
- 放置镜像到 `data/images`。
- Web UI 扫描镜像。
- 生成 iPXE 菜单。
- iPXE USB/ISO/EFI 使用方式。
- 手动 UEFI HTTP Boot 使用方式。
- HotPE 访问 Windows 镜像。
- Ubuntu/Linux 启动说明。
- 常见问题。
- 安全禁止项。

README 必须避免：

- 不得写“开箱即用自动接管 PXE”。
- 不得写路由器 DHCP Option 66/67 操作教程。
- 不得写 OpenWrt、TP-Link、交换机、AP 配置步骤。
- 不得建议开放 UDP 67/68/69/4011。
- 不得使用公网 CDN、SaaS 上传、第三方镜像托管。

---

## 18. 二期 Milestones

### Milestone 2.0：二期计划同步

状态：已完成。

目标：

- 将二期计划写入 `PLAN.md`。
- 明确一期已完工后的二期开发前提。
- 明确后续使用 `/goal` 和 subagents 模式开发。

验收：

- `PLAN.md` 包含二期网络模型、subagents 编排、功能计划、测试验收。
- `project_decision_agent` 确认阶段方向后才开始二期/三期代码实现。

### Milestone 2.1：网络安全复核

状态：已完成。

目标：

- `network_safety_agent` 审查二期计划。
- 复核 Compose、脚本、文档是否仍符合零侵入模型。

验收：

- 网络审查输出 `APPROVED`。
- 无 DHCP/ProxyDHCP/TFTP/UDP 67/68/69/4011。
- 无 host network、privileged、危险挂载。

### Milestone 2.2：镜像扫描与元数据

状态：已完成。

目标：

- 实现 `data/images` 安全扫描。
- 实现 SHA256 缓存。
- 实现镜像元数据读写。
- 实现启动就绪状态判断。

验收：

```bash
curl http://localhost:18080/api/images
```

返回镜像列表、分类、SHA256、状态、菜单启用字段。

### Milestone 2.3：动态菜单生成

状态：已完成。

目标：

- 根据元数据生成 `data/boot/menu.ipxe`。
- 只把 `menu_enabled=true` 且 `boot_readiness=ready` 的条目写入菜单。
- 支持 HotPE、Linux、Tools。
- Windows via HotPE 明确提示。

验收：

```bash
curl http://localhost:18080/boot/menu.ipxe
```

可看到按当前镜像生成的菜单。

### Milestone 2.4：Web UI 增强

状态：已完成。

目标：

- Dashboard。
- 镜像仓库。
- 镜像详情。
- 菜单预览。
- HotPE 指南。
- 构建任务页。
- 网络安全页。

验收：

- 不依赖外部 CDN。
- 未配置 admin token 时写操作不可用。
- 状态显示清楚区分 `boot_readiness` 和 `menu_enabled`。

### Milestone 2.5：Image Factory 增强

状态：已完成。

目标：

- Ubuntu autoinstall 模板任务。
- Ubuntu ISO 任务。
- Windows ADK 外部任务包。
- 任务状态、日志、输出目录。

验收：

- 能创建 draft 任务。
- 能生成任务目录和配置文件。
- 不执行真实磁盘破坏性操作。

### Milestone 2.6：教程与架构文档

状态：已完成。

目标：

- 新增 `tutorial_docs_agent` 定义。
- 产出对外 `README.md`。
- 产出架构说明和图例。

验收：

- README 能指导完成部署、放镜像、扫描、进入菜单、选择镜像。
- 文档不包含危险网络配置步骤。
- 图例能说明服务拓扑、启动链路、镜像扫描、菜单生成、subagents 协作。

### Milestone 2.7：二期最终安全验收

状态：已完成。

目标：

- `network_safety_agent` 终审。
- `security_audit_agent` 终审。
- `git_audit_agent` 阶段收口审查、准备本地 commit，并在决策通过且用户二次确认后 push 当前分支。

验收：

- 所有审查均为 `APPROVED`。
- 所有 BLOCKED 项已修复。
- 每个功能或 milestone 均有对应 git 审计记录和本地 commit。
- `git_audit_agent` 记录目标 remote/branch/commit range 和风险摘要。
- `project_decision_agent` 确认阶段方向后，push 当前 GitHub 分支前仍需用户二次确认。

验证记录：

- `network_safety_agent` 终审：`APPROVED`。
- `security_audit_agent` 复审：`APPROVED`。
- `git_audit_agent` 复审：`APPROVED`，审查范围为 `origin/codex/synaboot-phase1..HEAD`。
- `project_decision_agent` 推送决策：`APPROVED`。
- 本地提交与远端同步：
  - `9bde724 Enhance Phase 2 management workflows`
  - `22cfcba Align subagent governance with SynaBoot plan`
- 已 push 到 `origin/codex/synaboot-phase1`，本地与远端计数为 `0 0`。
- 最终本地验证补充：
  - `python3 -m py_compile apps/api/main.py apps/worker/scan_images.py`
  - `node --check apps/web/assets/app.js`
  - `bash scripts/preflight/check-network-safety.sh`
  - `bash scripts/preflight/check-compose-config-safe.sh`
  - loopback API smoke test 覆盖镜像元数据和 Image Factory 任务状态流。
- 此前本机 `8080/tcp` 已有监听，因此默认对外端口已迁移到 `18080/tcp`。本轮已使用默认端口完成验证：

```bash
docker compose up -d --build
curl http://localhost:18080/
curl http://localhost:18080/boot/menu.ipxe
curl http://localhost:18080/images/
curl http://localhost:18080/api/network-safety
docker compose down
```

结果：

- Web UI 可访问。
- `/boot/menu.ipxe` 返回 Phase 2 安全空菜单。
- `/images/` 可访问。
- `/api/network-safety` 返回 JSON，确认 `menu_url` 与 `images_url` 使用 `18080/tcp`。
- 验证后已执行 `docker compose down`。

---

## 19. 二期验证命令

优先使用本地安全命令。

```bash
bash scripts/preflight/check-network-safety.sh
bash scripts/preflight/check-compose-config-safe.sh
python -m compileall apps
bash -n scripts/preflight/check-network-safety.sh
curl http://localhost:18080/
curl http://localhost:18080/boot/menu.ipxe
curl http://localhost:18080/images/
curl http://localhost:18080/api/images
```

如需启动服务验证：

```bash
docker compose up -d
curl http://localhost:18080/
curl http://localhost:18080/boot/menu.ipxe
curl http://localhost:18080/images/
docker compose down
```

若默认对外端口已被宿主机其他服务占用，只允许使用 `.env` 调整 HTTP TCP 端口或使用 loopback 测试映射。

不得通过修改防火墙、路由、网关、DNS、DHCP 或交换机配置来规避端口冲突。

---

## 20. 二期 Goal Mode 启动提示

二期开工时使用新的 `/goal`。

推荐提示：

```text
/goal SERVER_IP 是 192.168.1.168。当前 SynaBoot 一期已完工，请严格按 PLAN.md 的二期计划继续开发。

必须开启 subagents 模式，并使用 .codex/agents 中定义的 agents：
1. research_agent 先调查不确定的外部事实、设备能力和协议限制。
2. 决策性问题交给 project_decision_agent，代替用户把控方向和重大取舍。
3. 所有网络相关变更再由 network_safety_agent 审查。
4. architecture_agent 负责二期架构和接口契约。
5. storage_agent 实现 data/images 扫描、元数据和 SHA256 缓存。
6. boot_entry_agent 实现 HTTP-only iPXE 动态菜单；Phase 3 另行设计受控 HTTP/PXE 自动启动入口。
7. webui_agent 实现二期 Web UI 页面，不依赖 CDN。
8. image_factory_agent 实现安全的镜像工厂任务框架。
9. tutorial_docs_agent 负责架构说明书、图例和对外 README。
10. security_audit_agent 和 network_safety_agent 做最终审查。
11. git_audit_agent 在每个功能或 milestone 完成后审查 diff；通过后可准备本地 commit；push 当前 GitHub 分支前必须经 project_decision_agent 批准并获得用户二次确认。

强制安全要求：
- 不得启用 DHCP。
- 不得启用 ProxyDHCP。
- 不得启用 TFTP。
- 不得修改路由器、OpenWrt、TP-Link、交换机、AP、VLAN、DNS、路由、防火墙。
- 不得使用 host network。
- 不得使用 privileged 容器。
- 不得开放 UDP 67/68/69/4011。
- 不得挂载宿主 /、/etc、/var/run/docker.sock。
- 不得上传内部 ISO/镜像到公网 SaaS。
- 不确定是否影响局域网通信时，必须停止并标记 BLOCKED。

开发顺序必须按 PLAN.md 二期 Milestones 2.1 到 2.7 推进。
每完成一个 milestone，先更新 PLAN.md 进度，再继续下一步。
```

---

## 21. Phase 3：自动网络启动入口集成

Phase 3 的目标是让用户在主板启动菜单中选择以下入口时，能够自动进入 SynaBoot 镜像选择界面：

- `UEFI: HTTP IPv4 <NIC>`
- `UEFI: PXE IPv4 <NIC>`
- `UEFI: HTTP IPv6 <NIC>`
- `UEFI: PXE IPv6 <NIC>`

安全前提：

- 主 DHCP 服务器继续由 `192.168.1.1` TP-Link TL-ER6120T 承担。
- 默认网关必须继续是 `192.168.1.4` OpenWrt。
- SynaBoot 服务器必须使用固定 IP 或 DHCP 保留地址，禁止与 DHCP 地址池冲突。
- 所有网络启动变更必须先有回滚步骤，并在维护窗口中执行。
- 任何变更不得影响普通终端继续获取 IP、访问网关、访问互联网和访问内网服务。

Phase 3 产品承诺：

```text
SynaBoot 可以补齐路由器无法下发 PXE/HTTP Boot 启动元数据的缺口，
但不得接管 DHCP、DNS、默认网关或普通网络配置。
```

该能力在产品上命名为 **Boot Metadata Proxy** 或
**PXE/HTTP Boot Metadata Proxy**，不得命名或实现为普通 DHCP Server。
它只允许补充启动信息：

- 识别 `PXEClient` / `HTTPClient`。
- 返回 `next-server`、`bootfile` 或 HTTP boot URL。
- 配合受控 TFTP 仅提供 iPXE/UEFI loader 白名单文件。

它必须禁止：

- 分配 IP 或提供 DHCP lease。
- 提供 router/default gateway option。
- 提供 DNS option。
- 提供 lease time。
- 响应普通非 PXE/HTTP Boot DHCP 客户端。
- 修改 TP-Link、OpenWrt、交换机、AP、VLAN、DNS、路由或防火墙。

该能力必须默认关闭，必须先通过隔离实验，必须具备一键关闭能力，
生产 LAN 启用前必须再次由用户明确二次确认。

### 21.0 Phase 3 前置调查门禁

Phase 3 不允许从假设直接进入设计或实现。所有外部事实不确定的问题，必须先交给 `research_agent` 调查并输出证据包，再由对应 agent 继续设计。

`research_agent` 职责：

- 调查 TL-ER6120T/TL-ER6120 的硬件版本、固件版本、DHCP Option 能力和限制。
- 调查 DHCP Option 66、Option 67、next-server、bootfile-url、Vendor Class、Client Architecture 对 PXE/HTTP Boot 的影响。
- 调查 UEFI PXE IPv4、UEFI HTTP Boot、iPXE chainload、TFTP、ProxyDHCP 的兼容性和已知坑。
- 当其他 subagent 需要知识库或互联网信息时，统一由 `research_agent` 检索并反馈。
- 输出证据来源、可信度、已确认事实、未知项、对 SynaBoot 的影响和推荐下一步。

当前已知初步调查结论：

- TP-Link 官方 TL-ER6120 V3 固件发布说明显示曾新增 DHCP Option 66、150、159、160、176、242 支持。
- 未在同一官方发布说明中看到 TL-ER6120 V3 明确新增 Option 67 的直接证据。
- TP-Link/Omada 文档说明 Option 66 用于 TFTP server 信息，Option 67 用于 TFTP boot file 路径。
- 社区资料显示，部分 TP-Link/Omada 路由即使提供 66/67，也可能因为缺少 next-server 或实现差异导致 PXE 客户端仍取错 TFTP server。

因此，在本项目实际执行前必须本地确认：

- 当前设备到底是 `TL-ER6120T` 还是 `TL-ER6120`，硬件版本和固件版本分别是什么。
- Web 管理界面是否支持 DHCP Option 66。
- Web 管理界面是否支持 DHCP Option 67 或等价的 Network Boot/File Name 字段。
- 是否支持 next-server / boot server IP。
- 是否支持按 Vendor Class（如 `PXEClient`、`HTTPClient`）或客户端架构区分启动参数。

调查门禁结论规则：

- 若 TP-Link 能完整提供 PXE 所需 boot server + bootfile，并且不会改变租约、DNS、网关，则优先走主路由 DHCP Boot Option 模式。
- 若 TP-Link 只支持 Option 66、不支持 Option 67/next-server，或 PXE 客户端实际取错 boot server，则不强行在 TP-Link 上硬配，转入 SynaBoot 受控 ProxyDHCP 方案评估。
- 若管理员已在当前 TL-ER6120T 上确认无法下发 PXE/HTTP Boot 启动元数据，
  则 Phase 3 方向转为由 SynaBoot 服务器提供受控 Boot Metadata Proxy，
  补齐路由器能力缺口；该结论不解除隔离实验和生产二次确认门禁。
- 若设备能力无法确认，Phase 3 标记为 `BLOCKED`，不得启用 TFTP/ProxyDHCP，也不得修改生产 DHCP。

### 21.1 推荐实现路径

推荐优先级：

1. **主路由 DHCP Boot Option 模式**。
   - TP-Link 仍发放客户端 IP、网关、DNS。
   - 仅增加 HTTP Boot/PXE 所需的 bootfile 信息。
   - 这是最符合“主 DHCP 不迁移”的方案。
   - 必须先验证 TL-ER6120T 是否支持按客户端类型或 Vendor Class 区分 `HTTPClient` 与 `PXEClient`。
   - 若只能全局下发单一 bootfile，不能直接用于同时覆盖 HTTP Boot 和 PXE Boot。

2. **SynaBoot 辅助 ProxyDHCP 模式**。
   - 仅当 TP-Link 无法按客户端类型下发 bootfile 时使用。
   - 产品命名统一为 Boot Metadata Proxy，强调补齐 boot metadata，
     不接管 DHCP 租约、DNS、网关或普通网络配置。
   - 只回答 PXE/HTTP Boot 引导信息，不分配 IP。
   - 必须默认关闭，启用前双审查，生产 LAN 启用前必须二次确认。

3. **iPXE USB/ISO/EFI 保底模式**。
   - 当某些主板固件不支持 HTTP Boot、IPv6 Boot 或 Secure Boot 阻止未签名 loader 时使用。

### 21.2 IPv4 HTTP Boot

目标入口：

```text
UEFI: HTTP IPv4 Realtek PCIe 2.5GBE Family Controller
```

必要条件：

- 客户端网卡和主板固件支持 UEFI HTTP Boot。
- 客户端可从 TP-Link DHCP 获取 IPv4 地址。
- DHCP 响应中能为 HTTP Boot 客户端提供 HTTP URL。
- HTTP URL 指向 SynaBoot 的 UEFI loader，例如：

```text
http://<SYNABOOT_SERVER_IP>:18080/boot/loaders/ipxe.efi
```

引导链：

```text
UEFI HTTP IPv4
  → TP-Link DHCP 获取 IP 和 boot URL
  → HTTP 下载 ipxe.efi
  → iPXE chain http://<SYNABOOT_SERVER_IP>:18080/boot/menu.ipxe
  → SynaBoot 镜像选择菜单
```

注意：

- 部分 UEFI HTTP Boot 固件对非 80 端口兼容性较差。若 `:18080` 无法启动，Phase 3 可新增受审查的 `80/tcp` HTTP Boot 入口，但不得改防火墙或网关。
- Secure Boot 可能拒绝未签名 `ipxe.efi`。此时需要关闭 Secure Boot，或使用可信签名 loader。

### 21.3 IPv4 PXE Boot

目标入口：

```text
UEFI: PXE IPv4 Realtek PCIe 2.5GBE Family Controller
```

必要条件：

- 客户端可从 TP-Link DHCP 获取 IPv4 地址。
- PXE 客户端能获得 boot server 和 bootfile。
- SynaBoot 提供 TFTP 或可被 PXE 固件支持的 NBP 下载方式。
- bootfile 推荐先加载 iPXE，再由 iPXE 使用 HTTP 进入菜单。

引导链：

```text
UEFI PXE IPv4
  → TP-Link DHCP 获取 IP、网关 192.168.1.4、PXE bootfile
  → 下载 snponly.efi/ipxe.efi
  → iPXE chain http://<SYNABOOT_SERVER_IP>:18080/boot/menu.ipxe
  → SynaBoot 镜像选择菜单
```

实现方式：

- 首选：TP-Link DHCP 下发 PXE bootfile，SynaBoot 只提供 TFTP/HTTP bootfile。
- 备选：SynaBoot 启用 ProxyDHCP，只向 PXE 客户端补充 bootfile，不发 IP。

### 21.4 IPv6 HTTP/PXE Boot

目标入口：

```text
UEFI: HTTP IPv6 Realtek PCIe 2.5GBE Family Controller
UEFI: PXE IPv6 Realtek PCIe 2.5GBE Family Controller
```

必要条件：

- 局域网 IPv6 已正确启用。
- 客户端可通过 RA/SLAAC/DHCPv6 获得 IPv6 地址和路由。
- DHCPv6 或等效机制能提供 IPv6 bootfile URL。
- SynaBoot HTTP/TFTP 服务绑定 IPv6 地址并通过本地链路可达。

约束：

- Phase 3 不自动修改 OpenWrt IPv6、RA、DHCPv6 或防火墙。
- 如果当前 LAN 没有稳定 IPv6 管理能力，IPv6 启动项标记为“需外部网络前提”，不得伪装为已支持。

### 21.5 Router/DHCP 配置边界

TP-Link TL-ER6120T 仍是唯一 DHCP 地址分配方。

允许变更范围：

- DHCP bootfile/next-server/boot-url 等启动选项。
- 按客户端类型区分 HTTP Boot、PXE Boot、普通 DHCP 客户端。
- 为 SynaBoot 服务器配置固定地址或 DHCP 地址保留。

前置验证：

- 确认 TL-ER6120T 固件版本。
- 确认是否支持 DHCP Option 66/67、bootfile URL、next-server。
- 确认是否支持按 Vendor Class 或客户端架构区分 HTTP Boot 和 PXE Boot。
- 若不支持区分，优先切换到 SynaBoot 辅助 ProxyDHCP 模式，而不是给所有客户端下发同一个 bootfile。

禁止变更范围：

- 改 DHCP 地址池导致普通终端无法续租。
- 改默认网关，必须保持 `192.168.1.4`。
- 改 DNS、VLAN、ACL、防火墙、NAT、静态路由。
- 关闭或迁移主 DHCP。
- 让 SynaBoot 同时提供普通 DHCP 地址分配。

回滚要求：

- 记录变更前 DHCP 配置截图或导出配置。
- 先在单台测试机或测试 VLAN 验证。
- 若普通终端续租失败、网关错误、无法访问内网或互联网，立即撤销 boot option/ProxyDHCP/TFTP。

### 21.6 Phase 3 Subagents 重塑

#### 21.6.1 research_agent

Phase 3 前置调查 agent。

职责：

- 在任何 Phase 3 网络启动方案设计前，先调查外部事实和设备能力。
- 回答其他 subagent 提出的知识库或互联网检索问题。
- 优先引用官方文档、固件发布说明、RFC、iPXE/ProxyDHCP/TFTP 项目文档。
- 将社区经验标注为低可信度辅助证据。
- 明确区分已确认事实、推断、未知项和必须本地验证的内容。
- 对 TL-ER6120T 是否支持 Option 66/67、next-server、Vendor Class 区分能力给出证据化结论。

输出必须包含：

- `QUESTION`
- `SOURCES`
- `CONFIRMED FACTS`
- `UNKNOWN / NEEDS LOCAL VERIFICATION`
- `IMPLICATION FOR SYNABOOT`
- `RECOMMENDED NEXT STEP`
- `CONFIDENCE`

#### 21.6.2 project_decision_agent

Phase 3 方向决策 agent。

职责：

- 在 Phase 3 遇到路线选择时代表用户做决策。
- 将 `UEFI: PXE IPv4` 自动进入 SynaBoot 作为当前最高优先级目标。
- 根据 `research_agent` 的证据选择 TP-Link DHCP Boot Option、受控 ProxyDHCP、TFTP loader、HTTP chainload 等路径。
- 当 TP-Link 能力不足时，决定是否进入受控 ProxyDHCP 方案。
- 当 IPv6、HTTP Boot、Secure Boot、Windows 安装方式等内容影响范围过大时，决定是否延后。
- 批准 `git_audit_agent` 将审计通过的 Phase 3 阶段 commit push 到当前 GitHub 分支。

限制：

- 不得覆盖 `network_safety_agent` 或 `security_audit_agent` 的 `BLOCKED`。
- 不得批准影响现有 LAN DHCP、默认网关、DNS、路由、防火墙、内网通信或外网连接的方案。

#### 21.6.3 network_safety_agent

从“零侵入绝对禁止”调整为“生产网络变更门禁”。

职责：

- 审查 DHCP boot option、ProxyDHCP、TFTP、HTTP Boot、IPv6 Boot 方案。
- 审查 `research_agent` 的事实结论是否足以支撑网络变更。
- 确认主 DHCP 仍为 TP-Link，默认网关仍为 `192.168.1.4`。
- 确认 SynaBoot 不提供普通 DHCP 地址分配。
- 确认所有高风险服务默认关闭、显式启用、可回滚。
- 输出 `APPROVED`、`APPROVED_WITH_EXTERNAL_CHANGE` 或 `BLOCKED`。

#### 21.6.4 boot_entry_agent

建议将 `pxe_agent` 重塑为 `boot_entry_agent`。

职责：

- 设计 HTTP Boot、PXE Boot、iPXE chain 的完整引导链。
- 维护 `ipxe.efi`、`snponly.efi`、`undionly.kpxe`、`menu.ipxe` 等 boot assets。
- 区分 UEFI、Legacy BIOS、IPv4、IPv6、Secure Boot 场景。
- 不直接修改路由器或 OpenWrt 配置。
- 遇到设备兼容性、协议行为、loader 选择等外部事实不确定时，先请求 `research_agent` 调查。

#### 21.6.5 architecture_agent

职责新增：

- 设计 Phase 3 boot entry 配置模型。
- 定义 `/api/boot-entry`、`/api/network-safety` 扩展字段。
- 将 HTTP、TFTP、ProxyDHCP 设计为独立可开关模块。
- 保持 Phase 1/2 默认零侵入部署仍可运行。

#### 21.6.6 webui_agent

职责新增：

- 新增“启动入口集成”页面。
- 展示 HTTP IPv4、PXE IPv4、HTTP IPv6、PXE IPv6 的就绪状态。
- 展示应交给网络管理员的 boot URL、bootfile、next-server 参数。
- 明确标记哪些步骤需要在 TP-Link 或外部网络设备中手动配置。
- 复用当前固定 `webui_agent` 会话推进 Web UI/网页后端联动重构，不因小改动
  新建同职责 agent。
- 重构时应用本地个人 skills：
  `design-review`、`design-taste-frontend`、`frontend-design`、`shadcn-ui`、
  `tailwind-design-system`，并按 2026-06-16 的用户决策将管理后台迁移到
  React + TypeScript + Tailwind CSS 的现代主题；仍必须保持 SynaBoot
  管理后台属性、LAN 安全边界、免费核心能力和商业代码隔离。

#### 21.6.7 tutorial_docs_agent

职责新增：

- 编写 `docs/BOOT_ENTRY_INTEGRATION.md`。
- 给出安全边界、实施顺序、回滚步骤和验证方法。
- 允许描述配置目标和参数，不写未经验证的具体路由器点击路径。

#### 21.6.8 security_audit_agent

职责新增：

- 审查 TFTP/ProxyDHCP 服务是否默认关闭。
- 审查 bootfile 路径穿越、loader 替换、恶意镜像引导风险。
- 审查 Web UI 是否把高风险开关做成显式确认。

#### 21.6.9 git_audit_agent

Phase 3 阶段收口 agent。

职责新增：

- 每完成 Phase 3 的一个可验证步骤后审查 diff 和验证记录。
- 确认未把真实路由器账号、截图敏感信息、token、内网凭据写入仓库。
- 确认 TFTP/ProxyDHCP/DHCP boot option 相关变更已经经过 `network_safety_agent` 与 `security_audit_agent` 审查。
- 审计通过后可准备本地 commit。
- 记录 remote、branch、commit range、提交摘要和风险摘要。
- `project_decision_agent` 确认符合项目方向后，经用户二次确认后 push 到当前 GitHub 分支。

### 21.7 Phase 3 验证命令

本地服务验证：

```bash
bash scripts/preflight/check-network-safety.sh
bash scripts/preflight/check-compose-config-safe.sh
curl http://localhost:18080/boot/menu.ipxe
curl http://localhost:18080/boot/loaders/ipxe.efi
curl http://localhost:18080/api/boot-entry
```

网络验证：

```text
1. 普通终端重新获取 DHCP，确认网关仍为 192.168.1.4。
2. 普通终端访问内网和互联网。
3. 单台测试机选择 UEFI HTTP IPv4，确认进入 SynaBoot 菜单。
4. 单台测试机选择 UEFI PXE IPv4，确认进入 SynaBoot 菜单。
5. 如启用 IPv6，再分别验证 HTTP IPv6 和 PXE IPv6。
6. 失败时撤销 boot option 或关闭 ProxyDHCP/TFTP，再验证普通终端恢复。
```

---

## 22. 当前进度与后续开发队列

更新时间：`2026-06-12`

### 22.1 当前进度快照

当前项目状态：

- Phase 1/2 零侵入 HTTP/iPXE 平台已经具备基础代码与文档。
- 默认仍只开放 `18080/tcp` HTTP 服务。
- 当前没有启用 DHCP、ProxyDHCP、TFTP、Samba。
- 当前没有开放 UDP `67/68/69/4011`。
- `research_agent` 已加入前置调查流程。
- `project_decision_agent` 已加入方向决策流程，仅在重大取舍或路线冲突时触发。
- `boot_entry_agent` 已替代旧的 `pxe_agent` 概念，负责 HTTP Boot、PXE Boot、iPXE chainload。
- `git_audit_agent` 已加入阶段收口流程，负责功能/milestone 完成后的 diff 审计、本地 commit 和经用户二次确认后 push 当前 GitHub 分支。
- Phase 3 仍处于规划与前置调查阶段，尚未实现或启用自动 PXE 入口。
- Phase 3.0 前置调查已完成首轮公开资料研究，记录见
  `docs/BOOT_ENTRY_RESEARCH.md`。
- 当前公开证据不足以证明 TL-ER6120T/TL-ER6120 可可靠提供完整
  PXE/HTTP Boot metadata，后续必须先做本地只读确认和隔离抓包验证。

当前已知限制：

- 已根据管理员提供的只读截图确认 TP-Link 设备准确型号为 `TL-ER6120T`，
  硬件版本为 `TL-ER6120T 1.0`，当前软件版本为
  `1.2.2 Build 240829 Rel.84642n`，页面显示最新软件版本为
  `1.2.3 Build 250812 Rel.80372n`。
- 还未本地确认 TL-ER6120T 是否完整支持 Option 66、Option 67、
  next-server、Vendor Class 或 Client Architecture 区分；当前截图为软件升级页面，
  未显示 DHCP Option 或网络启动字段。
- 管理员当前未在 TL-ER6120T 管理界面中找到 DHCP Option 66/67
  或等价 boot option 配置入口，因此 Phase 3.3 默认不依赖主路由
  DHCP Option 66/67 路线；该判断作为运营假设记录，不等同于官方完整证明。
- `/api/boot-entry` 已实现 Phase 3.1 只读模型，所有启动入口与可选服务默认关闭。
- 还未实现 TFTP/ProxyDHCP 可选模块。
- Web UI 已新增“启动入口”只读展示页面。
- `docs/BOOT_ENTRY_INTEGRATION.md` 已创建，只记录只读确认清单、参数边界、回滚原则和验证顺序；不包含路由器实操配置步骤。
- `docs/BOOT_ENTRY_LOCAL_VERIFICATION.md` 已创建，作为管理员填写的本地只读设备能力确认模板；不包含路由器实操配置步骤。
- 已收敛 Nginx `/boot/` 静态服务：只允许访问 `menu.ipxe` 与固定白名单
  loader 文件，其它 `/boot/` 路径返回 404，并启用 `disable_symlinks on`。

### 22.2 下一阶段目标

下一阶段的根本目标：

```text
让局域网内测试主机选择 UEFI: PXE IPv4 后，
在不影响现有 DHCP、网关、DNS、路由、防火墙的前提下，
进入 SynaBoot 镜像选择菜单。
```

优先开发顺序：

1. Phase 3.0：前置调查
   - 由 `research_agent` 调查并记录 TL-ER6120T/TL-ER6120 能力。
   - 本地确认设备型号、硬件版本、固件版本。
   - 输出 DHCP Option 66/67、next-server、Vendor Class 支持结论。
   - 若证据不足或方案分歧，触发 `project_decision_agent` 决定继续调查、阻塞或进入备选路径。

2. Phase 3.1：启动入口配置模型
   - 由 `architecture_agent` 设计 boot entry 配置模型。
   - 定义 `/api/boot-entry` 返回结构。
   - 明确 HTTP Boot、PXE Boot、TFTP、ProxyDHCP 的启用状态和安全状态字段。
   - 当前状态：已实现只读模型与 Web UI 展示；未启用 DHCP、ProxyDHCP、
     TFTP，未修改 Compose 或路由器配置。

3. Phase 3.2：Boot assets 管理
   - 由 `boot_entry_agent` 设计 `ipxe.efi`、`snponly.efi`、`undionly.kpxe` 元数据。
   - 只允许 boot loader 位于 `./data/boot/loaders`。
   - 记录来源、校验值、架构、适用场景。
   - 当前状态：已完成，仅允许只读扫描固定白名单 loader 元数据，不下载、
     生成、上传、删除或启用 loader。
   - Nginx `/boot/` 已改为精确白名单 location，避免静态服务绕过
     API 的 boot asset 安全判断。
   - 已提交并推送：`6a288e7 Add readonly Phase 3.2 boot assets inventory`。
   - 验证记录：
     - `python3 -m py_compile apps/api/main.py apps/worker/scan_images.py`
     - `node --check apps/web/assets/app.js`
     - `bash scripts/preflight/check-network-safety.sh`
     - `bash scripts/preflight/check-compose-config-safe.sh`
     - `nginx -t` 使用本地 `nginx:1.27-alpine` 镜像通过。
     - `/api/boot-assets` loopback smoke test 覆盖：
       `usable`、`blocked_symlink`、`blocked_parent_symlink`。
     - Nginx loopback 静态测试覆盖：
       `/boot/menu.ipxe=200`、`/boot/loaders/ipxe.efi=200`、
       `/boot/loaders/=404`、非白名单 loader `404`、symlink loader `403`。

4. Phase 3.3：受控 Boot Metadata Proxy / TFTP 方案设计
   - 仅在 TP-Link DHCP boot option 能力不足或不可依赖时进入。
   - 是否进入该路径由 `project_decision_agent` 基于 `research_agent` 证据和安全审查结论决定。
   - 当前状态：ROUTER_OPTION_PATH_NOT_RECOMMENDED_BUT_BLOCKED，已由截图确认
     TP-Link 型号、硬件版本和软件版本；管理员已确认当前 TL-ER6120T
     不能下发本项目所需 PXE/HTTP Boot 启动元数据，因此默认不依赖
     主路由 DHCP Option 路线，下一步仅允许进入 Boot Metadata Proxy
     可行性评估。
   - 仍等待本地只读确认 next-server、Vendor Class、Client Architecture
     等 boot metadata 能力；这些缺口不会解除 Phase 3.3 门禁。
   - 本地确认记录模板：`docs/BOOT_ENTRY_LOCAL_VERIFICATION.md`。
   - Boot Metadata Proxy 可行性评估文档：`docs/PROXYDHCP_FEASIBILITY.md`。
     当前仅达到 `G0_DOCUMENTATION_ONLY`，不批准实现、启用或生产 LAN 测试。
   - Boot Metadata Proxy 报文字段与抓包判读清单：`docs/PROXYDHCP_PACKET_REVIEW.md`。
     当前仅用于未来隔离验证的判读标准，不包含抓包或启服务命令。
   - TFTP loader 文件范围：`docs/TFTP_LOADER_SCOPE.md`。
     当前仅定义未来隔离验证的固定 loader 白名单，不包含 TFTP 服务配置。
   - Phase 3 回滚清单：`docs/PHASE3_ROLLBACK_CHECKLIST.md`。
     当前仅定义未来验证的恢复证据与阻塞条件，不包含网络设备操作步骤。
   - Phase 3 审查模板：`docs/PHASE3_REVIEW_TEMPLATES.md`。
     当前仅定义 network_safety_agent 与 security_audit_agent 的审查记录格式。
   - 默认关闭。
   - 不得分配 IP。
   - 不得修改网关、DNS、路由、防火墙。
   - 不得实现或启用 ProxyDHCP/TFTP，不得开放 UDP `67/68/69/4011`，
     不得修改 TL-ER6120T、OpenWrt 或 Docker 网络模式。
   - TP-Link `192.168.1.1` 必须继续作为唯一 DHCP lease server；
     OpenWrt `192.168.1.4` 必须继续作为默认网关。
   - 必须先通过 `network_safety_agent` 和 `security_audit_agent`。

5. Phase 3.4：Web UI 启动入口集成页
   - 展示 HTTP IPv4、PXE IPv4、HTTP IPv6、PXE IPv6 状态。
   - 展示要交给网络管理员的 boot server、bootfile、URL 参数。
   - 明确风险、回滚步骤和验证步骤。
   - 当前状态：只读入口状态页已实现；后续如新增可操作配置，必须重新审查。
   - 本轮只读展示增强：`/api/boot-entry` 返回 `documentation`、
     `local_verification_template`、`phase3_3_gate` 和
     `phase3_3_feasibility`，Web UI 展示本地确认模板、受控 ProxyDHCP
     可行性评估、报文判读清单、TFTP loader 范围、回滚清单、审查模板、
     集成说明和 Phase 3.3 blocked 状态。
   - 本轮只读门禁增强：`phase3_3_gate` 增加已确认事实、仍缺事实、
     解除门禁前置条件和禁止推断列表，Web UI 展示“本地事实门禁”面板，
     用于防止后续接力误把 TL-ER6120T 型号或固件信息当成 Option 66/67
     可用证明。
   - 本轮 UI 状态文案同步：Web UI “启动入口”页面副标题已从 Phase 3.1
     只读模型更新为 Phase 3.4 只读启动入口与本地事实门禁，避免用户或
     后续 agent 误判页面能力边界。
   - 本轮 API/UI 摘要同步：`/api/boot-entry` 保留 `phase=3.1` 作为只读模型
     阶段，同时新增 `display_phase=3.4` 与 `display_status`；Web UI 摘要
     区分“模型阶段”和“展示阶段”，避免把 Phase 3.4 展示误读为运行时解锁。
   - 本轮网络安全页同步：`/api/network-safety` 增加只读 `phase3_gate`
     摘要，Web UI “网络安全”页展示 Phase 3.3 blocked 状态、启动入口展示
     阶段，以及实现、服务启用、生产 LAN 测试均不允许。
   - 本轮只读展示增强验证记录：
     - `python3 -m py_compile apps/api/main.py apps/worker/scan_images.py`
     - `node --check apps/web/assets/app.js`
     - `bash scripts/preflight/check-network-safety.sh`
     - `bash scripts/preflight/check-compose-config-safe.sh`
     - `ss -lntu | grep -E ':(67|68|69|4011)\b' || true`
     - `rg -n "network_mode: host|privileged: true|67:|68:|69:|4011:|dnsmasq|proxydhcp|tftp|dhcp" docker-compose.yml scripts apps config docs PLAN.md README.md`
     - `git diff --check`
     - `boot_entry_status()` smoke test 覆盖 `documentation`、
       `local_verification_template`、
       `phase3_3_gate.status=router_option_path_not_recommended_but_blocked`
       以及 DHCP/ProxyDHCP/TFTP 均为关闭。

6. Phase 3.5：文档与验证
   - 新增 `docs/BOOT_ENTRY_INTEGRATION.md`。
   - 新增 `docs/BOOT_ENTRY_LOCAL_VERIFICATION.md`。
   - 更新 `docs/ARCHITECTURE.md`，固化 Phase 3 只读启动入口模型、
     `/api/boot-entry`、`/api/boot-assets`、Nginx `/boot/` 精确白名单和
     Phase 3.3 blocked 门禁。
   - 已更新 README/ADMIN_GUIDE/NETWORK_SAFETY，记录 TL-ER6120T 当前不采用
     主路由 DHCP Option `66/67` 路线，并补充 Phase 3.3 只读文档导航。
   - 本轮文档同步：已更新 ARCHITECTURE、SECURITY_REVIEW、NETWORK_SAFETY
     和 ADMIN_GUIDE，明确 `/api/network-safety.phase3_gate` 与 Web UI
     “网络安全”页只同步展示 Phase 3.3 门禁，且不提供实现、服务启用或
     生产 LAN 测试授权。
   - 本轮只读门禁预检：新增 `scripts/preflight/check-phase3-gates.py`，
     可重复校验 `/api/boot-entry` 与 `/api/network-safety` 的 Phase 3
     门禁字段仍为只读 blocked 状态，且实现、服务启用、生产 LAN 测试均
     不允许。
   - 本轮只读预检补强：`check-phase3-gates.py` 加载 API 状态模型时禁止
     写入 Python bytecode，避免生成 `__pycache__` 并保持预检工作区只读。
   - 本轮隔离验证准备增强：`/api/boot-entry` 增加
     `isolated_validation_plan` 只读结构，Web UI “启动入口”页展示隔离
     验证目标链路、环境要求、允许准备、禁止动作、实验前证据、未来成功
     标准和退出条件；字段显式声明 `runtime_enabled=false`、
     `production_lan_allowed=false`、`udp_ports_allowed=[]`，不启用
     DHCP、ProxyDHCP、TFTP 或生产 LAN 测试。
   - 本轮 Phase 3.5 预检补强：`check-phase3-gates.py` 断言
     `isolated_validation_plan` 只能保持 `readonly_plan_only`，并校验
     主 DHCP `192.168.1.1`、默认网关 `192.168.1.4`、服务关闭和 UDP
     端口不开放等机器可读不变量。
   - 本轮 PXE IPv4 readiness 增强：`/api/boot-entry` 增加
     `pxe_ipv4_readiness` 只读结构，汇总 `menu.ipxe`、`snponly.efi`、
     `ipxe.efi`、镜像元数据、ready 菜单项和 Phase 3 门禁状态；字段显式
     声明 `operation_allowed=false`、`service_enablement_allowed=false`、
     `production_lan_testing_allowed=false`、`runtime_enabled=false`、
     `boot_tested=false`，并保留生产 LAN、DHCP、ProxyDHCP、TFTP、UDP
     端口、Docker host network/privileged、OpenWrt/TP-Link 变更等 false
     安全不变量。
   - 本轮 PXE IPv4 readiness 当前实测：本地 `data` 只读快照可识别
     `source_iso_count=4`，且 Ubuntu 22.04.3/24.04 启动依赖准备后
     `ready_menu_entry_count=6`；`snponly.efi` 与 `ipxe.efi` 仍为
     `missing`，因此 `lab_prerequisites_met=false`，真实 PXE IPv4 隔离
     实验仍不能开始。
   - 本轮 loader 缺口推进：新增 `scripts/boot-assets/import-loader.py`，
     管理员可导入本地已审核的 `ipxe.efi`、`snponly.efi`、`undionly.kpxe`
     或 `ipxe.iso`。脚本只接受本地文件，固定白名单文件名，使用
     `os.O_EXCL` 禁止覆盖，记录 provenance 到
     `data/boot/loader-metadata`，不下载、不生成、不执行 loader，不启用
     DHCP、ProxyDHCP、TFTP 或任何网络服务。
   - 本轮官方 iPXE 归档导入准备：新增
     `scripts/boot-assets/import-ipxe-archive.py`，可从管理员提供的本地
     `ipxeboot.tar.gz` 或等价归档中提取固定白名单成员，例如
     `ipxeboot/x86_64-sb/snponly.efi`、`ipxeboot/x86_64-sb/ipxe.efi`、
     `x86_64-efi/snponly.efi` 或 `x86_64-efi/ipxe.efi`，并复用单文件
     导入校验。该脚本不联网、不整包解压、不执行 loader，也不启用任何
     网络启动服务。
   - 新增 `docs/IPXE_LOADER_SOURCES.md`，记录 iPXE 官方来源、Secure Boot
     风险、本地文件导入和本地归档导入方式；该文档只作为来源和操作说明，
     不授权生产 LAN 启动集成。
   - `/api/boot-assets` 现在区分 loader 文件存在、provenance 是否存在、
     SHA256 是否匹配和 `reviewed_for_lab` 状态；`pxe_ipv4_readiness`
     只有在 `snponly.efi` 或 `ipxe.efi` 文件与 provenance 均满足时，才把
     UEFI PXE loader 视为隔离实验前置满足。
   - 本轮已在项目本机下载官方 iPXE release 归档到 ignored runtime 目录：
     `data/builds/loader-downloads/ipxeboot.tar.gz`，归档 SHA256 为
     `01a526d4cc791fc30362259c609d6c506cc64a7bdff51b9a5eb788354e17eee1`。
     已通过 `import-ipxe-archive.py` 导入：
     - `data/boot/loaders/snponly.efi`，
       SHA256 `b1e67c3e4a1e8708ddfd0079ad4505e3a02245acb55ee9a95437ab3c507be82a`。
     - `data/boot/loaders/ipxe.efi`，
       SHA256 `6558e37887516b246d6a97122e8d18bedfe4197b7ba7f67bf1bf102a16678d33`。
     两个 loader 均有 provenance，`reviewed_for_lab=true`，且真实二进制和
     metadata 均被 `.gitignore` 排除。
   - 当前 `pxe_ipv4_readiness.lab_prerequisites_met=true`，表示 HTTP 菜单、
     ready 镜像条目和 reviewed UEFI loader 这些文件级前置已满足；但
     `pxe_ipv4_readiness.status` 仍为 `blocked_by_phase3_gate`，不得据此
     启用生产 LAN DHCP、ProxyDHCP、TFTP 或 UDP `67/69/4011`。
   - 本轮 Phase 3.10/3.11/3.12/3.13/3.14 继续推进隔离实验前置链路，但仍保持只读：
     - `isolated_lab_boot_services_disabled_skeleton` 只表达未来隔离实验的
       ProxyDHCP metadata-only 与 TFTP loader-only 候选服务骨架，所有服务、
       配置生成、命令执行、Compose 变更和生产 LAN 字段均为 false。
     - `isolated_lab_evidence_package` 汇总 HTTP menu、reviewed loader、
       ready 镜像、UDP 端口只读证据、人工隔离实验声明、客户端证据模板和
       授权草案；`status=not_authorized`，不等于实验授权。
     - `isolated_lab_config_intent_package` 作为 Phase 3.12 只读配置意图包，
       仅展示未来单机隔离实验的 dry-run intent：候选服务意图、端口意图、
       candidate bootfile、reviewed loader allowlist、HTTP chain target、
       客户端验证清单、人工授权门禁和回滚触发；它不是配置生成器，不被
       任务系统消费，不启动服务，不开放 UDP 端口，不允许生产 LAN。
     - `isolated_lab_source_skeleton_package` 作为 Phase 3.13 只读源码骨架 /
       离线包模型，仅表达未来单机隔离实验的协议模型、boot metadata 模型、
       loader transfer scope、HTTP chain target、client evidence fixture 和
       授权门禁；它 `status=not_runnable`、`fixture_only=true`、
       `offline_package_only=true`，没有运行入口、Compose service、生成文件、
       opened ports、任务消费者或网络监听器。
     - `isolated_lab_manual_declaration_gate` 作为 Phase 3.14 只读手工声明
       门禁，仅表达进入真实隔离实验 runtime 前管理员必须人工确认的事实模板；
       它 `status=missing_facts`、`submission_status=not_submitted`、
       `authorization_status=not_authorized`，不收集、不保存、不回传真实
       客户端或实验环境值，不新增写 API，不解锁 runtime。
     - `isolated_lab_runtime_authorization_plan` 作为 Phase 3.15 只读 runtime
       授权前计划，仅表达未来进入 isolated lab runtime 前必须满足的审批、
       范围、证据、回滚和研究缺口；它
       `status=blocked_until_manual_facts_and_approvals`，不等于授权结果、
       配置源、服务启动入口或生产 LAN 许可。
   - 本轮 Phase 3.12 运行态证据：
     - `/api/boot-entry` 返回
       `schema=phase3-isolated-lab-config-intent-package.v1`、
       `phase=3.12`、`mode=readonly_config_intent_package`、
       `status=not_authorized`、`read_only=true`。
     - `enabled`、`authorized`、`runtime_enabled`、`config_files_generated`、
       `config_generation_allowed`、`command_execution_allowed`、
       `service_start_allowed`、`write_api_available`、`compose_change_allowed`、
       `router_config_generation_allowed`、`production_lan_allowed`、
       `production_lan_testing_allowed`、`packet_capture_started`、
       `network_probe_started`、`task_consumption_allowed`、`boot_tested`
       均为 false。
     - UDP `67/69/4011` 均为 `observed_listening=false`、
       `desired_listening=false`，`ss -lntu` 未显示这些端口监听。
     - `candidate_bootfile=snponly.efi`，loader allowlist 为
       `snponly.efi` 与 `ipxe.efi`；客户端验证清单全部未通过且无
       observed 值，表示尚未进入真实实验。
   - 本轮 Phase 3.12 收口审查：
     - `project_decision_agent`、`architecture_agent`、`boot_entry_agent`、
       `network_safety_agent`、`security_audit_agent` 预审均 APPROVED，
       批准范围仅限只读配置意图 / dry-run 展示。
     - 实现后 `network_safety_agent`、`security_audit_agent`、
       `git_audit_agent` 收口均 APPROVED。
     - 验证通过：`check-subagent-governance.sh`、`check-phase3-gates.py`、
       `check-network-safety.sh`、`collect-release-evidence.sh`、
       `node --check apps/web/assets/app.js`、`git diff --check`，且无
       `__pycache__`。
   - 本轮 Phase 3.13 运行态证据：
     - `/api/boot-entry` 返回
       `schema=phase3-isolated-lab-source-skeleton.v1`、`phase=3.13`、
       `mode=readonly_source_skeleton`、`status=not_runnable`、
       `read_only=true`、`fixture_only=true`、`offline_package_only=true`。
     - `runtime_enabled`、`runtime_available`、`service_start_allowed`、
       `service_started`、`command_execution_allowed`、`config_generation_allowed`、
       `write_api_available`、`compose_integration_allowed`、
       `production_lan_allowed`、`packet_send_allowed`、`packet_capture_allowed`、
       `active_probe_allowed`、`task_consumption_allowed`、`boot_tested`
       均为 false。
     - `runtime_entrypoints`、`compose_services`、`generated_files`、
       `opened_ports`、`task_consumers`、`network_listeners` 均为空数组。
     - UDP `67/69/4011` 均为 `observed_listening=false`、
       `desired_listening=false`，`ss -lntu` 未显示这些端口监听。
     - 新增 fixture
       `config/synaboot/phase3.13-isolated-lab-source-skeleton.disabled.json`，
       文件不可执行、无 shebang、`loaded_at_runtime=false`，只作为
       离线样例和预检对象。
   - 本轮 Phase 3.13 收口审查：
     - `research_agent`、`project_decision_agent`、`architecture_agent`、
       `boot_entry_agent`、`network_safety_agent`、`security_audit_agent`
       预审均 APPROVED，批准范围仅限不可运行的离线协议模型、fixture 和
       只读状态。
     - 实现后 `network_safety_agent`、`security_audit_agent`、
       `git_audit_agent` 收口均 APPROVED。
     - 验证通过：`check-subagent-governance.sh`、`check-phase3-gates.py`、
       `check-network-safety.sh`、`collect-release-evidence.sh`、
       `node --check apps/web/assets/app.js`、`git diff --check`，且无
       `__pycache__`。
   - 本轮 Phase 3.14 运行态证据：
     - `/api/boot-entry` 返回
       `schema=phase3-isolated-lab-manual-declaration-gate.v1`、
       `phase=3.14`、`mode=readonly_manual_declaration_gate`、
       `status=missing_facts`、`read_only=true`、`template_only=true`。
     - `required_manual_facts=9`、`missing_facts=9`，所有手工事实模板项
       均保持 `status=missing`、`stores_value=false`。
     - `collects_user_input`、`stores_user_input`、`write_api_available`、
       `database_write_allowed`、`config_generation_allowed`、
       `service_start_allowed`、`runtime_enabled`、`runtime_unlock_allowed`、
       `production_lan_allowed`、`production_lan_testing_allowed`、`boot_tested`
       均为 false。
     - `boot_path_checklist` 中客户端固件入口、loader 请求、HTTP menu 目标和
       ready image menu 均无 `observed` 值，且 `passed=false`。
     - UDP `67/69/4011` 在该 gate 的 `network_service_state` 中全部为
       open/opened/mapped/listening false；`ss -lntu` 未显示这些端口监听。
   - 本轮 Phase 3.14 验证记录：
     - `PYTHONDONTWRITEBYTECODE=1 python3 scripts/preflight/check-phase3-gates.py`
     - `node --check apps/web/assets/app.js`
     - `python3 -m py_compile apps/api/main.py` 后已清理生成的 `__pycache__`
     - `bash scripts/preflight/check-network-safety.sh`
     - `bash scripts/preflight/check-subagent-governance.sh`
     - `bash scripts/preflight/check-compose-config-safe.sh`
     - `bash scripts/preflight/collect-release-evidence.sh`
     - `git diff --check`
     - `docker compose up -d --build`
     - HTTP `/`、`/boot/menu.ipxe`、`/boot/loaders/snponly.efi`、
       `/boot/loaders/ipxe.efi` 和 `/api/boot-entry` 运行态 smoke 均通过。
   - 本轮 Phase 3.14 收口审查：
     - `network_safety_agent` 收口 APPROVED，无阻断项；确认未启用
       DHCP、ProxyDHCP、TFTP，未开放 UDP `67/69/4011`，未触碰 TP-Link、
       OpenWrt、路由、网关、防火墙或 DNS。
     - `security_audit_agent` 收口 APPROVED，无阻断项；确认 gate 只读、
       template-only，不收集/保存真实环境值，不新增写 API、raw command、
       配置片段、secret 或生产 LAN 测试入口。
     - `git_audit_agent` 审计 APPROVED for stage/commit preparation；免费版
       发布范围可整理提交，未发现商业源码、license 或混淆产物进入免费版
       push 范围；push 前仍需先完成本地提交并运行 push readiness。
   - 本轮免费版发布记录：
     - 本地提交：`f7eb891 Advance free SynaBoot boot integration gates`。
     - `check-free-push-readiness.sh` 通过，工作区 `clean_for_push`，当前分支
       `codex/synaboot-phase1`，upstream 为 `origin/codex/synaboot-phase1`。
     - `project_decision_agent` 已 APPROVED 当前免费版提交推送方向。
     - 已 push 到 GitHub 当前免费版分支：
       `a2eed9b..f7eb891 codex/synaboot-phase1 -> codex/synaboot-phase1`。
     - 商业版源码、license、混淆产物、真实 ISO、loader、SQLite、`.env`
       均未进入 GitHub 免费版发布范围。
   - 本轮 Phase 3.15 运行态证据：
     - `/api/boot-entry` 返回
       `schema=phase3-isolated-lab-runtime-authorization-plan.v1`、
       `phase=3.15`、`status=blocked_until_manual_facts_and_approvals`、
       `read_only=true`。
     - `missing_manual_facts=9`，继承 Phase 3.14 手工声明门禁的缺失事实；
       `required_approvals=5`，覆盖 research、network safety、security、
       project decision 和用户手工确认。
     - `runtime_enabled`、`runtime_start_allowed`、`service_start_allowed`、
       `config_generation_allowed`、`write_api_available`、
       `production_lan_allowed`、`production_lan_testing_allowed`、`boot_tested`
       均为 false。
     - `boot_evidence_requirements=5`，覆盖 UEFI PXE IPv4 固件入口、reviewed
       loader 请求、HTTP menu、ready image menu 和 SynaBoot 不分配普通租约；
       所有 evidence 项均无 `observed` 值且 `passed=false`。
     - UDP `67/69/4011` 在该 plan 的 `network_service_state` 中全部为
       open/listening/mapped false；`ss -lntu` 未显示这些端口监听。
   - 本轮 Phase 3.15 验证记录：
     - `PYTHONDONTWRITEBYTECODE=1 python3 scripts/preflight/check-phase3-gates.py`
     - `node --check apps/web/assets/app.js`
     - `bash scripts/preflight/check-network-safety.sh`
     - `bash scripts/preflight/check-subagent-governance.sh`
     - `bash scripts/preflight/check-compose-config-safe.sh`
     - `bash scripts/preflight/collect-release-evidence.sh`
     - `git diff --check`
     - `docker compose up -d --build`
     - HTTP `/`、`/boot/menu.ipxe` 和 `/api/boot-entry` 运行态 smoke 均通过。
   - 本轮 Phase 3.15 收口审查：
     - `research_agent`、`project_decision_agent`、`architecture_agent`、
       `boot_entry_agent`、`network_safety_agent`、`security_audit_agent`
       预审均 APPROVED，批准范围仅限只读 runtime 授权前计划。
     - 实现后 `network_safety_agent`、`security_audit_agent` 收口均
       APPROVED，无阻断项。
     - `git_audit_agent` 审计 APPROVED for free-edition stage/commit
       preparation；未发现商业代码、license、混淆产物或真实镜像误入
       push 范围。
   - 本轮 Phase 3.15 免费版发布记录：
     - 本地提交：`c8043c4 Add isolated lab runtime authorization plan`。
     - `check-free-push-readiness.sh` 通过，工作区 `clean_for_push`。
     - `project_decision_agent` 已 APPROVED 当前免费版提交推送方向。
     - 已 push 到 GitHub 当前免费版分支：
       `25088b1..c8043c4 codex/synaboot-phase1 -> codex/synaboot-phase1`。
     - 商业版源码、license、混淆产物、真实 ISO、loader、SQLite、`.env`
       均未进入 GitHub 免费版发布范围。
   - 本轮 Phase 3.16 运行态证据：
     - `/api/boot-entry` 返回
       `schema=phase3-isolated-lab-runtime-authorization-draft.v1`、
       `phase=3.16`、
       `status=draft_blocked_until_evidence_and_approvals`、
       `read_only=true`。
     - 该对象是 future runtime authorization object 的只读草案，不是授权
       结果、不是状态迁移事件、不是运行时配置源、不是服务启动入口。
     - `is_authorization_result`、`is_state_transition_event`、
       `is_runtime_config_source`、`authorized`、`runtime_enabled`、
       `runtime_start_allowed`、`service_start_allowed`、
       `config_generation_allowed`、`write_api_available`、
       `production_lan_allowed`、`boot_tested`、`host_network`、`privileged`、
       `tp_link_modified`、`openwrt_modified`、
       `normal_dhcp_leases_enabled` 均为 false。
     - `required_evidence=5`、`required_approvals=4`、
       `boot_evidence_collection_plan=5`；所有 boot evidence 均无 observed
       值且 `passed=false`。
     - UDP `67/69/4011` 在该 draft 的 `network_service_state` 中全部为
       false；`ss -lntu` 未显示这些端口监听。
   - 本轮 Phase 3.16 验证记录：
     - `PYTHONDONTWRITEBYTECODE=1 python3 scripts/preflight/check-phase3-gates.py`
     - `node --check apps/web/assets/app.js`
     - `git diff --check`
     - `find apps scripts -path '*/__pycache__*' -print`
     - `bash scripts/preflight/check-network-safety.sh`
     - `bash scripts/preflight/check-subagent-governance.sh`
     - `bash scripts/preflight/check-compose-config-safe.sh`
     - `bash scripts/preflight/collect-release-evidence.sh`
     - `docker compose up -d --build`
     - HTTP `/`、`/boot/menu.ipxe` 和 `/api/boot-entry` 运行态 smoke 均通过。
   - 本轮 Phase 3.16 收口审查：
     - `project_decision_agent`、`network_safety_agent`、
       `security_audit_agent`、`boot_entry_agent`、`architecture_agent`
       预审均 APPROVED，批准范围仅限只读 runtime authorization draft。
     - 实现后 `network_safety_agent` 收口 APPROVED，确认未启用 DHCP、
       ProxyDHCP、TFTP，未开放 UDP `67/69/4011`，未触碰 TP-Link、
       OpenWrt、路由、网关、防火墙或 DNS。
     - 实现后 `security_audit_agent` 收口 APPROVED，确认无写 API、无配置
       生成、无服务启动、无 secret/token/raw command、无真实 MAC/IP/
       customer/hostname，免费版/商业版边界未破坏。
     - `git_audit_agent` 审计 APPROVED for free-edition stage/commit
       preparation；未发现商业代码、license、混淆产物、真实 ISO、loader、
       SQLite、`.env`、secret 或 runtime ignored data 进入免费版提交范围。
   - 本轮 Web UI / HotPE 体验重构方向：
     - `webui_agent`、`architecture_agent`、`project_decision_agent` 已复用
       固定会话审查用户要求，结论一致：允许重构 Web UI、API 只读聚合层、
       页面结构、视觉系统、菜单预览和 HotPE 引导体验。
     - 2026-06-16 用户已放宽前端安全审计和技术栈边界：允许管理后台采用
       React + TypeScript + Tailwind CSS + shadcn 风格自有组件重构；这些
       本地 skills 作为设计、组件、响应式和审计约束：
       `design-review`、`design-taste-frontend`、`frontend-design`、
       `shadcn-ui`、`tailwind-design-system`。
     - HotPE / Win11 安装检查归入免费版基础装机能力；允许进入 GitHub 免费版
       的范围是基础装机、镜像展示、HotPE 检查、Win11 基础安装链路说明、
       只读门禁和静态 UI 美化。
     - 不得进入免费版发布线：商业代码、license、在线激活、混淆产物、
       商业端点、私有目录、生产 LAN 自动启动、未经授权的 UDP `67/69/4011`
       能力。
   - 本轮 HotPE / Win11 运行态检查：
     - 已发现 HotPE 源 ISO：
       `data/images/pe/hotpe/HotPE-V2.8.251018.iso`。
     - 已发现 Win11 源 ISO：
       `data/images/windows/win11/Win11_24H2_Pro_Chinese_Simplified_x64.iso`。
     - 新增只读 API：`GET /api/hotpe-readiness` 与
       `GET /api/windows-install-candidates`，只汇总现有扫描结果，不写配置、
       不生成菜单、不启动服务。
     - `/api/hotpe-readiness` 当前返回
       `status=blocked_missing_hotpe_artifacts`、
       `hotpe_source_iso_present=true`、`required_artifacts_present=false`、
       `hotpe_menu_ready=false`、`windows_iso_candidate_count=1`、
       `client_boot_test_status=not_tested`、
       `client_install_test_status=not_tested`。
     - 当前缺少 HotPE 启动组件：
       `pe/hotpe/wimboot`、`pe/hotpe/bootmgr`、`pe/hotpe/BCD`、
       `pe/hotpe/boot.sdi`、`pe/hotpe/boot.wim`。
     - `/api/windows-install-candidates` 当前返回 1 个候选：
       `windows/win11/Win11_24H2_Pro_Chinese_Simplified_x64.iso`，
       `direct_ipxe_supported=false`，必须通过 HotPE 辅助安装。
     - `menu.ipxe` 当前只显示两个 Ubuntu Linux ready 项；HotPE 段仍显示
       `HotPE files are not enabled or not ready.`，Windows via HotPE 菜单项
       尚未出现。
     - 结论：HotPE 当前不能判定可用；在 HotPE 中选择已上传 Win11 镜像安装
       的架构路径成立，但必须先补齐 HotPE 组件并进行真实客户端启动和安装
       验证。
   - 本轮 HotPE 启动组件准备收口（2026-06-15 后续）：
     - 已复用 `architecture_agent`、`boot_entry_agent`、`image_factory_agent`、
       `storage_agent`、`network_safety_agent`、`security_audit_agent`、
       `project_decision_agent` 协作；没有新增一次性 subagent。
     - 已新增只读 UDF 提取能力和 HotPE 本地准备脚本，可从当前 HotPE ISO
       提取 `bootmgr`、`BCD`、`boot.sdi`、`boot.wim`。
     - 已新增本地 `wimboot` 导入脚本，要求管理员提供已审核来源并在非公开
       `data/metadata/wimboot-provenance/` 记录 provenance；本轮运行态使用
       官方 iPXE/wimboot v2.9.0 发布物导入。
     - 当前运行态已具备：
       `pe/hotpe/wimboot`、`pe/hotpe/bootmgr`、`pe/hotpe/BCD`、
       `pe/hotpe/boot.sdi`、`pe/hotpe/boot.wim`。
     - `/api/hotpe-readiness` 当前返回
       `status=ready_for_client_test`、`required_artifacts_present=true`、
       `hotpe_menu_ready=true`、`windows_iso_candidate_count=1`、
       `windows_via_hotpe_candidate=true`。
     - `/boot/menu.ipxe` 当前已出现 `item hotpe` 与 `item windows_hotpe`，
       并通过 HTTP 引用 HotPE 五件套；Win11 ISO 仍保持 HotPE 辅助安装源，
       不生成 raw Windows ISO 直接启动项。
     - 已验证 HotPE 五件套和 Win11 ISO 的 HTTP `200 OK`、`Content-Length`
       与 `Accept-Ranges: bytes`；UDP `67/69/4011` 无监听。
     - 仍未完成真实客户端证据：
       `client_boot_test_status=not_tested`、
       `client_install_test_status=not_tested`。下一步必须在实体/虚拟客户端中
       手动 iPXE 启动 HotPE，并在 HotPE 内访问
       `http://192.168.1.168:18080/images/windows/` 选择 Win11 ISO，确认安装器
       能到达磁盘选择页。
   - 本轮 Web UI 第一轮改进：
     - Dashboard 新增“局域网装机状态一屏看清”和装机链路态势，展示 HTTP、
       iPXE 菜单、HotPE、Win11、Phase 3 门禁状态。
     - 菜单页新增 iPXE 菜单摘要，区分 HotPE、Windows via HotPE 和网络服务
       当前是否可用。
     - HotPE 页面改为 HotPE / Win11 安装链路检查，展示源 ISO、必需组件、
       Windows 候选镜像、HTTP 仓库地址和真实客户端验证清单。
     - CSS 统一为更清晰的运维管理台视觉系统，保留 8px radius、明确状态色、
       键盘 focus、移动端单列布局；已用 headless Chrome 截图检查桌面和移动端，
       并修复移动端横向滚动。
   - 本轮 Web UI / HotPE 收口审查：
     - `network_safety_agent` 收口 APPROVED；确认未启用 DHCP、ProxyDHCP、
       TFTP，未开放 UDP `67/69/4011`，未修改 TP-Link、OpenWrt、路由、
       网关、防火墙或 DNS，未把 HotPE/Win11 状态展示变成生产 LAN 启用授权。
     - `security_audit_agent` 收口 APPROVED；确认无 secret/token 泄漏、
       无 raw command 注入、无写 API 越权、无路径越界、无商业实现端点、
       无误导性 “HotPE 已可用 / Win11 已安装验证” 表述。
     - `git_audit_agent` 审计 APPROVED for free-edition stage/commit
       preparation；确认未发现商业代码、license、混淆产物、真实 ISO、
       loader、SQLite、`.env`、secret 或 runtime ignored data 进入免费版
       提交范围。
   - 本轮验证记录：
     - `node --check apps/web/assets/app.js`
     - `bash scripts/preflight/check-public-runtime-boundary.sh`
     - `PYTHONDONTWRITEBYTECODE=1 python3 scripts/preflight/check-phase3-gates.py`
     - `bash scripts/preflight/check-subagent-governance.sh`
     - `bash scripts/preflight/check-network-safety.sh`
     - `bash scripts/preflight/check-compose-config-safe.sh`
     - `bash scripts/preflight/collect-release-evidence.sh`
     - `git diff --check`
     - `docker compose up -d --build`
     - HTTP `/`、`/api/hotpe-readiness`、
       `/api/windows-install-candidates` 和 `/boot/menu.ipxe` smoke 均通过。
     - `ss -lntu` 未显示 UDP/TCP `67/69/4011` 监听。
     - `find apps scripts -path '*/__pycache__*' -print` 为空。
   - 单台测试机验证 UEFI PXE IPv4。
   - 验证普通终端 DHCP、网关、内网和互联网不受影响。
   - 当前状态：已创建只读文档草案；真实测试机验证等待 Phase 3.3 门禁解除。
   - 本轮 Phase 3.5 验证记录：
     - `python3` AST parse 检查 `apps/api/main.py` 与
       `scripts/preflight/check-phase3-gates.py`，不生成 `__pycache__`。
     - `node --check apps/web/assets/app.js`
     - `bash scripts/preflight/check-network-safety.sh`
     - `python3 scripts/preflight/check-phase3-gates.py`
     - `boot_entry_status()` smoke test 覆盖 `isolated_validation_plan.phase=3.5`、
       `runtime_enabled=false`、`production_lan_allowed=false`、
       `udp_ports_allowed=[]`。
     - `boot_entry_status()` smoke test 覆盖 `pxe_ipv4_readiness.status=blocked_by_phase3_gate`、
       `source_iso_count=4`、`ready_menu_entry_count=6`、
       `snponly.efi/ipxe.efi=missing`、`runtime_enabled=false`、
       `production_lan_allowed=false`、`boot_tested=false`。
     - 空 `data/metadata` 临时目录 smoke test 覆盖
       `pxe_ipv4_readiness` 只读降级，不创建 SQLite、不迁移 schema、不写
       metadata 文件。
     - root-owned 现有 SQLite smoke test 覆盖只读快照读取：
       `metadata_status=readonly_snapshot`、`source_iso_count=4`。
   - 本轮文档门禁同步验证记录：
     - `rm -rf apps/api/__pycache__ apps/worker/__pycache__ scripts/preflight/__pycache__ && python3 scripts/preflight/check-phase3-gates.py && test -z "$(find apps scripts -path '*/__pycache__*' -print)"`
     - `bash scripts/preflight/check-network-safety.sh`
     - `bash scripts/preflight/check-compose-config-safe.sh`
     - `ss -lntu | grep -E ':(67|68|69|4011)\b' || true`
     - `rg -n "network_mode: host|privileged: true|67:|68:|69:|4011:|dnsmasq|proxydhcp|tftp|dhcp" docker-compose.yml scripts apps config docs PLAN.md README.md`
     - `git diff --check`
   - 本轮架构文档同步验证记录：
     - `bash scripts/preflight/check-network-safety.sh`
     - `bash scripts/preflight/check-compose-config-safe.sh`
     - `ss -lntu | grep -E ':(67|68|69|4011)\b' || true`
     - `rg -n "network_mode: host|privileged: true|67:|68:|69:|4011:|dnsmasq|proxydhcp|tftp|dhcp" docker-compose.yml scripts apps config docs PLAN.md README.md`
     - `git diff --check`
   - 本轮本地只读确认模板验证记录：
     - `bash scripts/preflight/check-network-safety.sh`
     - `bash scripts/preflight/check-compose-config-safe.sh`
     - `ss -lntu | grep -E ':(67|68|69|4011)\b' || true`
     - `rg -n "network_mode: host|privileged: true|67:|68:|69:|4011:|dnsmasq|proxydhcp|tftp|dhcp" docker-compose.yml scripts apps config docs PLAN.md README.md`
     - `git diff --check`

7. Phase 3.6：阶段收口
   - `network_safety_agent` 复审。
   - `security_audit_agent` 复审。
   - `git_audit_agent` 审查 diff、验证记录和敏感信息。
   - 审计通过后创建本地 commit。
   - `project_decision_agent` 确认阶段方向后，由 `git_audit_agent` 经用户二次确认后 push 当前 GitHub 分支。
   - 本轮 Phase 3.6 收口补充：已将 Phase 3.4 “本地事实门禁”只读面板的
     审查结论、验证命令和禁止推断边界同步到 `docs/SECURITY_REVIEW.md`
     与 `docs/NETWORK_SAFETY.md`。

### 22.3 GitHub 推送策略

用户期望：

- `git_audit_agent` 审计确认无问题后，经用户二次确认后 push 到 GitHub 当前分支。

当前执行策略：

- 远程 push 降级为版本控制收口动作，不再按 LAN 高风险操作处理。
- `git_audit_agent` 审计 diff、secrets、危险脚本、无关文件和验证记录。
- 涉及网络、Compose、脚本、启动入口或安全边界的变更，必须先通过 `network_safety_agent` 和/或 `security_audit_agent`。
- `project_decision_agent` 确认阶段方向和推送范围后，`git_audit_agent` 经用户二次确认后 push 到 GitHub 当前分支。
- 不得 push secrets、`.env`、真实凭据、未审查网络影响变更或无关文件。

当前远程与分支：

```text
origin_remote: github
origin_host: github.com
branch: codex/synaboot-phase1
```

---

## 23. Subagents 协作模式与通信机制

### 23.0 Subagent 调用成本与会话治理

问题记录：

- `PLAN.md` 中定义的是 11 个长期角色，不代表每次遇到小问题都新建一个
  subagent 会话。
- 此前执行中，主控把多个小型补丁、复测和非阻断建议都当成独立审计点，
  反复新开 architecture/security/git 等 agent 会话，导致会话数量远超
  11 个角色定义，浪费 token。
- 根因不是角色职责错误，也不是 subagent 不该用，而是缺少“已有会话如何
  复用、何时合并审计、何时才新增会话”的调度规则。
- 2026-06-16 再次出现同类问题：主控把 `AGENTS.md` 中的 `spawn` 字面理解为
  每次实现后都创建新的 `security_audit_agent`，并且在同一轮 BLOCKED 修复后
  没有把修复回传给同一个审计会话，而是连续新建同职责审计会话。
  直接根因是 `AGENTS.md` 的措辞与本节“固定会话池复用”规则不一致，且台账
  没有把“completed 但仍可继续复审的会话应继续复用”写成硬规则。

修正原则：

- 11 个 subagents 是**角色池**，不是“每轮都要全部启动”的任务队列。
- `.codex/agents/*.toml` 是角色定义，右侧窗口是 UI 会话显示，`send_input`/
  `close_agent` 使用的是当前工具层 agent registry。三者不是同一个状态源：
  - UI 里仍显示的历史窗口，不代表当前工具层还能访问。
  - 工具层返回 `agent not found` 时，表示该 agent id 已不在当前 registry，
    必须标记为 stale，不得继续假装可复用。
  - 工具层返回子模型解析错误时，表示 spawn 没有成功创建会话；该失败不算
    已创建 agent，也不得反复重试刷屏。
- 每个 milestone 开始前必须执行“固定会话池启动协议”：
  - 先清点上轮登记的 role -> agent_id。
  - 对可恢复/可通信的会话继续复用。
  - 对 `agent not found`、无法恢复或答案已明显偏离角色职责的会话标记
    `stale`，不再发送任务。
  - 只在工具层可正常 spawn 时，为 11 个项目角色建立固定会话池。
  - 固定会话池建立后，本 milestone 只向登记会话发送任务，不临时新开同类角色。
  - 若固定会话池无法建立，应暂停并向用户报告工具层失败，而不是用一批临时
    agent 替代。
- 同一 milestone 内，同一角色优先复用同一个会话；需要补充信息、复测结果、
  新补丁或修复说明时，优先 `send_input` 回传给已有会话。
- `APPROVED`、`PASS`、`BLOCKED` 或 `completed` 只代表该次输入完成，不代表该
  角色会话必须废弃。特别是 `security_audit_agent` 返回 `BLOCKED` 后，主控
  应本地修复并把差异、验证命令和修复说明回传给**同一个 agent_id**复审；
  禁止因为修复了一处 BLOCKED 就新建同职责 reviewer。
- 主控必须维护当前 milestone 的会话登记：角色名、会话状态、最后一次输入
  摘要。只有确认没有可复用会话、原会话已经结束/失效，或任务范围已经跨越
  原角色职责边界时，才允许新建对应角色会话。
- 长期协作台账见 `docs/SUBAGENT_SESSION_POOL.md`。该文档必须记录角色岗位、
  agent id、状态、操作流水、可引用结论、完成进度和 stale/重建原因；
  不记录 token、商业源码、私有配置或镜像内容。上下文压缩或线程恢复后，
  主控必须先读取该台账，再声明 subagent 状态或引用其旧结论。
- `docs/SUBAGENT_SESSION_POOL.md` 中的“协作统计与压缩恢复快照”是恢复
  subagent 状态的主表，不是普通备注。每一行必须能回答岗位是谁、做过什么、
  当前进度、下次如何复用；否则压缩恢复后不得引用该 agent 的旧回复。
- `docs/SUBAGENT_SESSION_POOL.md` 必须保留协作统计与压缩恢复快照，至少记录
  `role`、`agent_id`、`status`、`operation_log`、`latest_topic`、
  `progress`、`reusable_conclusion` 和 `next_reuse_rule`。未登记在台账中的
  subagent 结论，压缩恢复后不得当作已批准事实引用。
- 压缩恢复后，`docs/SUBAGENT_SESSION_POOL.md` 是 subagent 协作结论的唯一长期
  记忆锚点。聊天摘要只能用于定位，不得单独作为 APPROVED、BLOCKED、完成进度
  或发布范围的证据。
- 恢复工作时必须先读取“协作统计与压缩恢复快照”和“结论与进度表”。只有同时
  具备 `agent_id`、操作流水、可复用结论和证据的记录，才允许被引用到最终回答
  或后续开发决策中。
- `completed=null`、空输出、spawn 失败、`agent not found` 或未登记回复不得
  被登记为 APPROVED。此类情况必须写入流水并标记为未确认、失败或 `stale`。
- 小型文档同步、预检脚本文案调整、无行为变化的错误信息整理，默认由主控
  本地完成并运行验证命令；如果已有相关 subagent 会话处于活跃状态，应将
  结果合并回传，而不是另开新会话。
- 多个相关小改动必须先合并成一个审计包，再统一交给必要 agent 复核。
- 非阻断建议由主控本地修复并重跑本地验证；只有触及架构边界、安全边界、
  网络边界、发布边界或 Git 范围时，才复用原审计会话或进入下一轮批量审计。
- 已经有 `collect-release-evidence.sh`、`check-release-scope.sh`、
  `check-edition-boundary.sh`、`check-public-runtime-boundary.sh` 等机器门禁时，
  不得新建 subagent 重复做同一层面的机械检查；机器结果应作为上下文发给
  已有会话，subagent 只做语义复核、例外判断和跨边界取舍。

调用预算：

- 普通小改动：主控本地验证即可；若已有相关活跃会话，复用该会话回传摘要，
  不为小改动单独新建 subagent。
- 单一低风险功能包：复用已有相关实现/架构 agent；如无可复用会话，最多新建
  1 个相关实现/架构 agent + 1 个必要审计 agent，并在该 milestone 内持续复用。
- 触及安全或发布边界的功能包：最多 3 个 agent：
  `architecture_agent`、`security_audit_agent`、`git_audit_agent`；优先复用
  已有会话，无法复用时才按角色各新建一次。
- 触及 LAN、Compose 网络、端口、DHCP/ProxyDHCP/TFTP、路由、防火墙时：
  必须包含 `network_safety_agent`，但仍应与其他审计合并为一次审计包。
- `research_agent` 仅在外部事实不确定时启动；不得用于本地代码中已可验证的问题。
- `project_decision_agent` 仅在版本边界、收费边界、阶段方向或重大取舍需要决策时启动。

禁止行为：

- 禁止每改一个文件就新开一组三个审计 agent。
- 禁止在已有固定会话池可用时，为同一职责另开新窗口。
- 禁止在 spawn 工具返回子模型解析错误或 registry 异常时反复重试创建大量
  agent；最多记录一次失败并暂停该类 agent 调用。
- 禁止为了重复确认已经由脚本证明的事实而新开 subagent；应把脚本输出摘要
  发给已有会话或纳入下一次批量审计包。
- 禁止在同一 milestone 内关闭 agent 后，因为小修复又立即新开同角色 agent；
  应保持原会话继续复用，或等到下一次批量审计。
- 禁止把“收到非阻断建议”自动升级为新一轮完整 subagent 审计。
- 禁止在未检查可复用会话的情况下继续启动新 subagent；当用户指出 token 浪费后，
  新建会话前必须先说明为什么已有会话不能复用。
- 禁止把 `AGENTS.md` 或旧计划中的“spawn/invoke reviewer”理解为无条件
  `spawn_agent`。项目内所有 agent 触发语义默认都是“复用登记会话优先”。

新的执行节奏：

```text
主控本地实现一批相关改动
  → 主控运行机器门禁和验证命令
  → 若只是普通小修，直接记录结果；已有相关会话则批量回传摘要
  → 若触及边界，汇总为一个审计包
  → 每个必要角色优先复用固定会话池；无可用会话且工具层正常才新建一次
  → BLOCKED 才修复并回传同一会话
  → PASS 后保留会话到该 milestone 收口，避免小修后重复新建
```

### 23.1 总体编排

当前工作流采用“主控编排 + 专责 agent + 审计门禁”的模式。

```text
用户目标
  → 主控 Codex 拆分任务与判断风险
  → research_agent 调查外部事实
  → project_decision_agent 仅在方向/优先级/重大取舍时决策
  → network_safety_agent 审查网络边界
  → architecture_agent 定义模型、接口、模块边界
  → boot_entry_agent / storage_agent / webui_agent / image_factory_agent 分工实现
  → tutorial_docs_agent 固化说明、图例、回滚和验证步骤
  → security_audit_agent 审查安全风险
  → git_audit_agent 审查 diff、创建本地 commit、经用户二次确认后 push 当前分支
```

### 23.2 通信机制

subagents 之间不直接修改彼此输出。

通信依赖以下共享工件：

- `PLAN.md`：任务阶段、状态、下一步、验收标准。
- `AGENTS.md`：最高安全边界和必需 agent 编排。
- `.codex/agents/*.toml`：每个 agent 的职责、约束和输出要求。
- `docs/*.md`：架构、安全、教程和验收结论。
- `git diff`：阶段收口时的真实变更边界。
- 审查结论：`APPROVED`、`BLOCKED`、`REQUIRES_DECISION`。
- 决策结论：`APPROVED`、`APPROVED_WITH_CONDITIONS`、`BLOCKED`、`NEEDS_RESEARCH`。
- 用户本地镜像事实：`data/images` 下的 ISO/WIM/ESD/镜像文件只作为运行数据和验收输入，
  不作为 Git 提交内容。

当某个 agent 遇到外部事实不确定时：

```text
对应 agent
  → 提出明确问题
  → research_agent 检索官方资料、文档、RFC、社区证据
  → 返回事实、未知项、影响和建议
  → 原 agent 基于证据继续设计
```

当某个 agent 遇到决策性问题时：

```text
对应 agent
  → 汇总可选方案、风险、收益、验证要求
  → 如有事实缺口，先交给 research_agent
  → 如涉及 LAN 风险，先交给 network_safety_agent / security_audit_agent
  → project_decision_agent 选择方向或标记 BLOCKED/NEEDS_RESEARCH
  → 对应 agent 按决策继续推进
```

当某个变更可能影响 LAN 时：

```text
对应 agent
  → 停止实施
  → network_safety_agent 审查
  → APPROVED 才能继续
  → BLOCKED 则回到方案修正
```

当某个阶段完成时：

```text
实现完成
  → 运行验证命令
  → 读取 docs/SUBAGENT_SESSION_POOL.md，优先复用登记的审计会话
  → security_audit_agent / network_safety_agent 按风险复审
  → 若 BLOCKED，主控本地修复并 send_input 回同一 agent_id 复审
  → git_audit_agent 审查 diff、敏感信息、真实镜像排除状态和验证记录
  → project_decision_agent 确认阶段方向和推送范围
  → 创建本地 commit
  → 经用户二次确认后 push 当前 GitHub 分支
```

当用户已经放入 ISO，但启动所需文件尚未提取时：

```text
用户放入 ISO
  → storage_agent 扫描并记录 source ISO 元数据
  → architecture_agent 确认 ISO 与派生启动文件的数据模型
  → image_factory_agent 设计幂等准备任务
  → boot_entry_agent 仅为已满足依赖的条目生成菜单
  → webui_agent 展示准备状态、缺失文件和下一步动作
  → security_audit_agent 审查提取路径、覆盖行为和命令风险
  → git_audit_agent 确认真实 ISO 与生成产物不会被提交
```

### 23.3 每个 Subagent 是否在工作流中工作

当前 11 个必需 subagents 都已经纳入整体工作流。

- `research_agent`：已纳入 Phase 3 前置调查门禁。
- `project_decision_agent`：已纳入方向、优先级、重大取舍和阶段推送决策。
- `network_safety_agent`：已纳入所有网络相关变更的前置和最终审查。
- `architecture_agent`：已纳入 API、配置模型、服务边界和 milestone 拆分。
- `boot_entry_agent`：已纳入 iPXE、HTTP Boot、PXE Boot、loader 和 chainload 设计。
- `storage_agent`：已纳入镜像仓库、元数据、HTTP 静态服务和可选 Samba 边界。
- `image_factory_agent`：已纳入 Ubuntu/Windows 镜像工厂任务框架。
- `webui_agent`：已纳入 Dashboard、镜像管理、菜单预览、启动入口集成页。
- `tutorial_docs_agent`：已纳入 README、架构图、Phase 3 集成文档和回滚教程。
- `security_audit_agent`：已纳入代码、路径、权限、Docker、TFTP/ProxyDHCP 安全审计。
- `git_audit_agent`：已纳入每个功能或 milestone 的阶段收口。

注意：

- 不是每个小改动都需要所有 subagents 同时参与。
- 每个 milestone 必须明确哪些 agent 是必需参与者。
- `project_decision_agent` 只在方向性、阶段性、冲突性、取舍性问题上触发。
- 涉及网络启动、Compose、脚本、端口、路由器参数、安全边界时，`research_agent`、`network_safety_agent`、`security_audit_agent`、`git_audit_agent` 必须参与。
- 普通 UI 或文档小修可以只经过相关实现 agent、必要审计 agent 和 `git_audit_agent`。

### 23.4 Subagent 超量调用复盘

本轮问题：

- 用户期望是启用 11 个项目角色，并按 PLAN 执行开发。
- 实际执行中，主控在每个小型发布护栏补丁后都重新启动
  `architecture_agent`、`security_audit_agent`、`git_audit_agent`，
  导致累计创建了远超 11 个的 subagent 会话。
- 这些会话大多审查的是同一类事实：
  - 免费发布线没有商业实现。
  - 没有 license/payment/activation 运行时入口。
  - `.env`、ISO、SQLite、混淆产物没有进入 Git。
  - 预检脚本只读且不生成 `__pycache__`。
- 这些事实已经逐步被机器门禁覆盖，后续不应继续用大量 subagent 重复确认。

具体根因：

1. 将“角色数量”误当成“可无限创建会话”。
2. 缺少每个 milestone 的 subagent 调用预算。
3. 对非阻断建议采用了“修一次、审一次”的低效循环。
4. 没有充分复用已有会话的 `send_input` 能力。
5. 没有把多项小修复合并成一个审计包。

已采取的解决措施：

- 在 23.0 中新增 subagent 调用成本与会话治理规则。
- 将发布线事实尽量沉淀到机器门禁：
  - `check-release-scope.sh`
  - `check-private-commercial-scope.sh`
  - `check-edition-boundary.sh`
  - `check-public-runtime-boundary.sh`
  - `check-token-disclosure.sh`
  - `collect-release-evidence.sh`
- 后续同一 milestone 内，同一角色优先复用同一个会话。
- 后续小型修复默认先跑本地验证；若已有相关活跃会话，则回传摘要继续复用，
  若没有活跃会话，不为小修单独新建。
- 后续只有在机器门禁无法判断语义、出现 BLOCKED、触及 LAN/安全/发布边界，
  或用户明确要求时，才复用或启动必要 subagent。

后续执行口径：

```text
能由脚本验证的事实 → 主控先跑脚本，再把结果发给已有 agent 或纳入审计包
普通小修 → 主控处理；已有相关会话则复用回传，无会话则不单独新建
同类小修累计 → 合并成一次审计包，发给已有会话
需要语义判断 → 复用对应 agent；无可复用会话才新建一次
需要安全/Git 收口 → 复用 security_audit_agent + git_audit_agent；无会话才各建一次
需要网络判断 → 才额外复用或启动 network_safety_agent
```

2026-06-16 SMB/CIFS livefs 事故修正规则：

```text
security_audit_agent 第一次 BLOCKED
  → 主控修复 ISO 提取大小上限
  → 必须 send_input 回同一 security_audit_agent
  → 第二次 BLOCKED
  → 主控继续修复目录 extent / symlink 校验
  → 必须继续 send_input 回同一 security_audit_agent
  → 只有同一 agent_id 不可恢复或明确 stale，才登记 stale 并替换一次
```

---

## 24. 下一步开发规划：ISO-first 验收闭环与 Phase 3.3 受控评估

更新时间：`2026-06-13`

### 24.1 当前新增事实

用户已经在以下目录放入对应 ISO：

```text
data/images/pe/hotpe/HotPE-V2.8.251018.iso
data/images/windows/win11/Win11_24H2_Pro_Chinese_Simplified_x64.iso
data/images/linux/ubuntu-22.04.3/ubuntu-22.04.3-desktop-amd64.iso
data/images/linux/ubuntu-24.04/ubuntu-24.04.3-desktop-amd64.iso
```

这些 ISO 是本地运行数据，不进入 Git，不上传第三方服务，不由 SynaBoot
删除或覆盖。

当前平台已有镜像扫描和菜单生成框架，但 raw ISO 与可启动条目之间仍有缺口：

- HotPE ISO 不能直接等价于 `wimboot` 启动目录，需要准备出
  `wimboot`、`bootmgr`、`BCD`、`boot.sdi`、`boot.wim`。当前运行态已通过
  UDF 提取和本地 wimboot 导入补齐，进入 `ready_for_client_test`。
- Ubuntu ISO 不能单独成为 iPXE Linux 启动项，需要同目录具备
  `casper/vmlinuz` 和 `casper/initrd`。
- Windows 11 ISO 保持 HotPE 辅助安装模式，不生成通用 iPXE 直接启动项。
- Ubuntu 24.04 也应纳入 Linux 镜像识别和准备流程，不能只写死
  Ubuntu 22.04.3。

### 24.2 下一阶段根本目标

下一阶段先完成 Phase 2 的真实镜像闭环：

```text
用户只负责把 ISO 放到 data/images
  → SynaBoot 扫描 ISO
  → SynaBoot 判断缺失的启动依赖
  → SynaBoot 生成安全、幂等的准备任务
  → 准备完成后自动生成 menu.ipxe
  → 用户通过 iPXE USB/ISO/EFI 或手动 HTTP Boot 进入菜单
```

Phase 3 的 `UEFI: PXE IPv4` 自动入口继续保持门禁状态。当前只允许进行
受控 ProxyDHCP/TFTP 可行性评估文档和隔离实验方案设计，不允许在生产 LAN
实现、启用或测试。

### 24.3 Phase 2.8：当前变更与本地镜像保护收口

参与 agent：

- `storage_agent`
- `security_audit_agent`
- `git_audit_agent`

目标：

- 保护用户已放入的 ISO，避免误提交。
- 收口当前计划、审查和门禁脚本变更。
- 确认 Phase 3 仍为只读 blocked。

必须实现：

- `.gitignore` 忽略 `data/images/**` 下的真实镜像，仅保留 README 和
  `.gitkeep`。
- `git_audit_agent` 明确禁止提交 ISO/WIM/ESD/IMG/VHD/VHDX/QCOW2 等镜像文件。
- `security_audit_agent` 审查 ISO 准备任务不得路径穿越、不得覆盖用户原始 ISO。

验收：

```bash
git status --short
python3 scripts/preflight/check-phase3-gates.py
bash scripts/preflight/check-network-safety.sh
bash scripts/preflight/check-compose-config-safe.sh
git diff --check
```

验收标准：

- 真实 ISO 不出现在可提交文件列表中。
- Phase 3 门禁仍为 readonly + blocked。
- 没有 DHCP、ProxyDHCP、TFTP、UDP `67/68/69/4011`、host network 或
  privileged 变更。

### 24.4 Phase 2.9：ISO 扫描语义增强

参与 agent：

- `architecture_agent`
- `storage_agent`
- `boot_entry_agent`
- `webui_agent`
- `security_audit_agent`

目标：

- 将 raw ISO 明确建模为 source media。
- 区分“已扫描到 ISO”和“可进入 iPXE 菜单”的状态。
- 避免把不可直接启动的 ISO 误展示为可启动。

必须实现：

- 为 ISO 增加准备状态，例如：
  - `source_only`
  - `needs_extraction`
  - `prepared`
  - `unsupported_direct_boot`
- HotPE ISO 在依赖缺失时被识别为 `needs_extraction`；依赖齐全后标记为
  `prepared/ready` 并生成 HotPE wimboot 菜单项。
- Ubuntu 22.04.3 和 Ubuntu 24.04 ISO 被识别为 Linux source ISO；
  缺少 `casper/vmlinuz` 或 `casper/initrd` 时标记为 `incomplete` 或
  `needs_extraction`。
- Windows 11 ISO 标记为 `needs_hotpe`，只在 HotPE ready 后生成
  Windows via HotPE 菜单说明入口。
- Web UI 展示缺失依赖，而不是只给出笼统 `incomplete`。

验收：

```bash
curl http://localhost:18080/api/images
curl http://localhost:18080/boot/menu.ipxe
```

验收标准：

- 4 个 ISO 均可被扫描并显示。
- Raw ISO 不会被误加入可直接启动菜单。
- UI 能说明每个 ISO 下一步需要准备什么。

当前实现记录：

- API 已新增并返回：
  - `source_role`
  - `preparation_status`
  - `missing_artifacts`
  - `next_action`
  - `readiness_detail`
- HotPE raw ISO 在缺失依赖时标记为 `source_iso` + `needs_extraction`，
  缺失依赖明确为 `wimboot`、`bootmgr`、`BCD`、`boot.sdi`、`boot.wim`；
  当前运行态已补齐并标记为 `source_iso` + `prepared` + `ready`。
- Ubuntu/Linux raw ISO 标记为 `source_iso` + `needs_extraction`，缺失依赖明确为
  `casper/vmlinuz` 和 `casper/initrd`。
- Windows ISO 标记为 `windows_source_iso` + `uses_hotpe`，不生成通用直接启动项。
- Web UI 镜像表和详情页已展示准备状态、缺失依赖、准备说明和下一步动作。
- 临时数据目录 smoke test 已覆盖 HotPE ISO、Windows ISO、Ubuntu ISO，确认 raw ISO
  不会误进入 `menu.ipxe` 启动菜单。

### 24.5 Phase 2.10：ISO 准备任务框架

参与 agent：

- `architecture_agent`
- `image_factory_agent`
- `storage_agent`
- `boot_entry_agent`
- `security_audit_agent`

目标：

- 让用户只放 ISO，其余由 SynaBoot 生成可审查、可重复执行的准备任务。
- 先实现任务框架和本地工具探测，不强行引入新依赖。

必须实现：

- 新增或扩展 Image Factory 任务类型：
  - `hotpe-iso-prepare`
  - `ubuntu-iso-extract-kernel-initrd`
- 任务必须幂等：
  - 原始 ISO 只读。
  - 输出只写入对应 `data/images/...` 子目录或 `data/builds/<job-id>/`。
  - 已存在文件不静默覆盖，必须记录状态或要求管理员确认。
- Ubuntu 准备任务提取：

```text
casper/vmlinuz
casper/initrd
```

- HotPE 准备任务目标输出：

```text
wimboot
bootmgr
BCD
boot.sdi
boot.wim
```

- 若宿主或容器缺少可用 ISO 解包工具，只生成任务说明和缺失工具提示，
  不自动安装新第三方依赖。

禁止：

- 不得 mount 宿主系统敏感目录。
- 不得使用 `privileged` 容器。
- 不得删除或改写用户 ISO。
- 不得执行磁盘分区、格式化、写真实块设备。

验收：

```bash
curl http://localhost:18080/api/jobs
curl http://localhost:18080/api/images
curl http://localhost:18080/boot/menu.ipxe
```

验收标准：

- Ubuntu 准备完成后，对应 Ubuntu 菜单项进入 `ready`。
- HotPE 依赖齐全后，HotPE 菜单项进入 `ready`。
- Windows via HotPE 只有在 HotPE ready 且 Windows ISO 存在时显示。

当前实现记录：

- API 已支持任务类型：
  - `hotpe-iso-prepare`
  - `ubuntu-iso-extract-kernel-initrd`
- Web UI 镜像详情页会在 raw HotPE/Ubuntu ISO `needs_extraction` 时显示
  “创建准备任务”按钮。
- 新任务创建时必须传入 `source_image_id`，后端会校验：
  - HotPE 准备任务只能绑定 `pe/hotpe/*.iso`。
  - Ubuntu/Linux 提取任务只能绑定 `linux/**/*.iso`。
  - 源文件必须仍为 `present`。
- 任务包写入 `data/builds/<job-id>/package/...`，包含：
  - `manifest.json`
  - `README.md`
  - `prepare.sh`
- `manifest.json` 明确记录：
  - 原始 ISO 只读。
  - 不覆盖已有目标文件。
  - 不写项目数据目录之外。
  - 不安装新依赖。
  - 不执行破坏性磁盘操作。
- `manifest.json` 已新增本机工具探测摘要，记录 `bsdtar` 与 `7z` 当前是否可用；
  该探测只读，不自动安装依赖。
- Ubuntu/Linux `prepare.sh` 优先使用本机已有 `bsdtar` 或 `7z` 提取
  `casper/vmlinuz` 和 `casper/initrd`；若没有外部工具，可使用项目内
  `extract-iso9660-file.py` 只读提取器作为 fallback。
- Ubuntu/Linux `prepare.sh` 已在复制前校验解包结果必须存在、必须是普通文件、
  不得是 symlink，避免异常 ISO 通过 symlink 暴露宿主敏感文件。
- 本轮新增 `scripts/image-factory/prepare-linux-boot-artifacts.sh`，用于管理员
  已放置 Linux ISO 后批量准备 `casper/vmlinuz` 与 `casper/initrd`；脚本只处理
  `data/images/linux/**/*.iso`，优先使用本机已有 `bsdtar` 或 `7z`，缺失时
  使用项目内 stdlib ISO9660 提取器；不安装依赖、不挂载 ISO、不覆盖已有文件、
  不写项目外路径、不处理 Windows/HotPE。
- 本机当前未发现 `bsdtar`、`7z`、`xorriso` 或 `isoinfo`，但项目内
  `extract-iso9660-file.py` 已成功从 Ubuntu 22.04.3/24.04 ISO 提取
  `casper/vmlinuz` 与 `casper/initrd`；真实 ISO smoke 当前显示
  `image_count=8`、`iso_count=4`、`ready_count=6`，PXE readiness 显示
  `ready_menu_entry_count=6`。
- 本轮 Git 审计指出脚本必须防止父路径 symlink 导致写入项目外。已补强：
  - 拒绝 `data/images`、`data/images/linux`、`data/builds`、`WORK_ROOT`
    任一父路径为 symlink。
  - 对 `WORK_ROOT` 和每个 hash work 目录做 canonical 校验。
  - 在 `rm -rf` 工作目录前确认路径非空、非 `/`、非 symlink，且仍位于
    `data/builds/linux-boot-artifacts` 下。
- 本轮 symlink 边界 smoke test 已覆盖：
  - `data/images` 为 symlink 时 BLOCKED。
  - `data/builds` 为 symlink 时 BLOCKED。
  - `data/builds/linux-boot-artifacts/<hash>` 为 symlink 时 BLOCKED。
- 本轮安全审计指出 ISO 提取器必须限制异常 ISO 的资源消耗。已补强：
  - `extract-iso9660-file.py` 限制只允许提取 `vmlinuz` 与 `initrd`。
  - 校验 `extent * 2048 + size` 不得超过 ISO 文件大小。
  - 对 `vmlinuz` 与 `initrd` 设置最大文件大小。
  - 使用 `os.O_EXCL` 不覆盖写入，并改为分块流式复制。
  - 写入失败时只清理本次创建的目标文件。
- 本轮新增 `scripts/preflight/check-iso-extractor-safety.sh`，并已接入
  `collect-release-evidence.sh`，用于固化 ISO 提取器和 Linux 准备脚本的
  安全不变量。
- HotPE `prepare.sh` 当前默认 fail-fast，只生成清单和人工确认说明，避免因
  HotPE ISO 内部布局差异误提取错误文件。
- `/api/jobs` 和任务详情页已展示任务包状态、源 ISO、目标输出、manifest
  路径、准备脚本路径、安全边界和本机工具探测结果，管理员不用进入容器
  或目录树即可先完成只读审查。
- 临时数据目录 smoke test 已覆盖 HotPE 与 Ubuntu 准备任务创建，确认任务包、
  manifest 和脚本生成位置符合边界。

### 24.6 Phase 2.11：真实启动前本地 smoke test

参与 agent：

- `boot_entry_agent`
- `webui_agent`
- `tutorial_docs_agent`
- `security_audit_agent`
- `git_audit_agent`

目标：

- 在不改 LAN 的前提下，完成服务级和菜单级验证。

验证命令：

```bash
bash scripts/preflight/check-network-safety.sh
bash scripts/preflight/check-compose-config-safe.sh
bash scripts/preflight/check-real-iso-smoke.sh
```

验收标准：

- Web UI 展示 4 个 ISO 的状态。
- `menu.ipxe` 只包含已准备完成的启动项。
- Windows 11 仍通过 HotPE 辅助安装。
- 验证后执行 `docker compose down`。

当前验证记录：

- 已运行：

```bash
bash scripts/preflight/check-network-safety.sh
bash scripts/preflight/check-release-scope.sh
bash scripts/preflight/check-compose-config-safe.sh
docker compose up -d --build
curl http://localhost:18080/
curl http://localhost:18080/images/
curl http://localhost:18080/api/network-safety
curl http://localhost:18080/api/boot-entry
curl http://localhost:18080/api/images
curl http://localhost:18080/boot/menu.ipxe
docker compose down
```

说明：本轮验证使用本机 `.env` 中已配置的管理员 token；验证记录不得在
命令行或文档中展示 token 值。

- 由于首轮真实 ISO 扫描会计算大文件 SHA256，通过 Nginx `POST /api/scan`
  触发时命中默认上游超时；已改用同一 Compose API 容器内直接调用
  `scan_images()` 完成验证。
- 4 个真实 ISO 均已被扫描并通过 HTTP API 展示：
  - Ubuntu 22.04.3 ISO：`source_iso` + `needs_extraction`。
  - Ubuntu 24.04 ISO：`source_iso` + `needs_extraction`。
  - HotPE ISO：`source_iso` + `needs_extraction`。
  - Windows 11 ISO：`windows_source_iso` + `uses_hotpe`。
- 当前 `menu.ipxe` 没有把 raw ISO 误加入可直接启动项，只保留工具入口。
- 验证后已执行 `docker compose down`，`18080/tcp` 已释放。
- 本轮验证未在文档或命令记录中保留管理员 token 值。
- 已新增 `scripts/preflight/check-real-iso-smoke.sh`，将以上服务级验证固化为
  显式 smoke test：
  - 先确认 4 个真实 ISO 存在且被 Git 忽略。
  - 先运行网络安全和安全 Compose 配置检查。
  - 启动 Compose 后在 API 容器内直接调用 `scan_images()`，避免首轮大文件
    SHA256 通过 Nginx 触发上游超时。
  - 检查 Web UI、`/api/images`、`/boot/menu.ipxe` 和 `/images/`。
  - 确认 raw ISO 名称不会出现在 `menu.ipxe` 启动项中。
  - 默认执行 `docker compose down`；如需保留服务，可设置
    `SYNABOOT_SMOKE_KEEP_RUNNING=1`。
- 本轮已实际运行更新后的 `bash scripts/preflight/check-real-iso-smoke.sh` 并通过：
  - 4 个真实 ISO 均存在且被 Git 忽略。
  - Compose 构建、启动、容器内扫描、Web/API/menu/images 检查均通过。
  - 扫描结果为 `image_count=8`、`iso_count=4`、`ready_count=6`，符合
    Ubuntu 22.04.3/24.04 启动依赖已准备完成的当前阶段预期。
  - `menu.ipxe` 未包含 HotPE、Windows 11 raw ISO 文件名；已准备的
    Ubuntu 22.04.3/24.04 ISO URL 允许进入 Linux 启动项。
  - 脚本结束后已执行 `docker compose down`。

### 24.7 Phase 3.3-A：受控 Boot Metadata Proxy 可行性评估继续保持文档阶段

参与 agent：

- `research_agent`
- `network_safety_agent`
- `security_audit_agent`
- `project_decision_agent`
- `boot_entry_agent`
- `tutorial_docs_agent`

目标：

- 为最终 `UEFI: PXE IPv4 -> SynaBoot 菜单` 做证据准备。
- 继续保持生产 LAN 零变更。
- 将类似 iVentoy ProxyNet 的能力抽象为 SynaBoot Boot Metadata Proxy：
  只补齐路由器无法下发的启动元数据，不接管 DHCP、DNS、网关或普通网络配置。

产品承诺：

```text
服务器可以补齐路由器做不到的 PXE/HTTP Boot 元数据能力；
服务器不得分配 IP，不得提供网关，不得提供 DNS，
只响应 PXEClient / HTTPClient，
只返回 bootfile / next-server / boot URL，
必须隔离实验通过，必须一键关闭，
生产 LAN 启用前必须二次确认。
```

当前允许：

- 文档化 Boot Metadata Proxy / ProxyDHCP metadata-only / ProxyNet-like 方案。
- 设计隔离实验输入、输出和报文字段判读标准。
- 明确 TFTP loader 白名单、回滚证据和审查模板。
- 设计 `off`、`lab`、`production-armed`、`production-enabled` 四种状态，
  其中 `production-enabled` 必须依赖隔离实验证据和用户二次确认。
- 设计一键关闭命令和回滚验收标准。

当前禁止：

- 不得实现 ProxyDHCP/TFTP 服务。
- 不得开放 UDP `67/68/69/4011`。
- 不得在生产 LAN 抓包测试或启服务。
- 不得修改 TL-ER6120T、OpenWrt、交换机、AP、VLAN、DNS、路由、防火墙。
- 不得把 Boot Metadata Proxy 描述成 DHCP Server 或让它发送普通 DHCP lease。

进入 Phase 3.3-B 的前置条件：

- 用户确认可用隔离测试网络或单机实验环境。
- `network_safety_agent` 和 `security_audit_agent` 输出允许隔离验证的结论。
- `project_decision_agent` 明确批准从文档阶段进入隔离验证阶段。
- 文档中必须列明抓包验收条件：
  - TP-Link 仍然分配 IP。
  - OpenWrt 仍然是默认网关 `192.168.1.4`。
  - SynaBoot 不发送 `yiaddr` 租约。
  - SynaBoot 不发送 router、DNS、lease time。
  - SynaBoot 对普通 DHCP 客户端静默。
  - SynaBoot 只对 `PXEClient` / `HTTPClient` 返回启动元数据。

### 24.8 当前 Subagents 职责校对结论

当前 11 个 subagents 总体保留，但职责边界做如下校正：

- `research_agent`：继续负责外部事实，不参与本地 ISO 解包实现；Phase 3
  网络启动疑问仍先走它。
- `project_decision_agent`：只处理方向取舍，例如是否引入新解包依赖、是否进入
  Phase 3 隔离实验；普通 ISO 扫描实现不需要它频繁介入。
- `network_safety_agent`：继续只读审查 LAN 风险；ISO 准备本身不触发网络审查，
  除非修改 Compose、端口、HTTP 暴露或启动入口网络能力。
- `architecture_agent`：负责 raw ISO、派生启动文件、任务状态和菜单生成之间的
  数据模型。
- `storage_agent`：负责扫描用户 ISO、SHA256、准备状态、缺失依赖提示；
  不删除、不覆盖用户 ISO。
- `image_factory_agent`：负责 HotPE/Ubuntu ISO 准备任务框架；不得执行破坏性磁盘操作。
- `boot_entry_agent`：只为准备完成的 HotPE/Ubuntu 生成菜单；Windows 继续走
  HotPE 辅助安装。
- `webui_agent`：展示 ISO 准备状态、缺失文件、任务入口和菜单预览；不得暗示 raw ISO
  可直接启动。
- `tutorial_docs_agent`：同步用户放 ISO、平台准备、菜单生成、iPXE 启动的教程。
- `security_audit_agent`：重点审查 ISO 解包路径穿越、命令注入、覆盖用户文件、
  镜像误提交和日志泄密。
- `git_audit_agent`：阶段收口前必须确认真实 ISO、生成数据库、日志、构建产物未被
  stage 或 push。

### 24.9 通信协作机制修正

原机制中“阶段完成后自动 push”的表述容易忽略本地镜像文件风险。修正后：

- 实现 agent 只修改代码、脚本、文档和配置。
- 用户放入的 ISO 只作为本地运行输入。
- `storage_agent` 可以读取并扫描 ISO，但不得把 ISO 纳入仓库变更。
- `image_factory_agent` 生成的派生文件默认属于运行产物，不进入 Git。
- `git_audit_agent` 必须在 commit/push 前检查：
  - 是否 stage 了 ISO/WIM/ESD/IMG/VHD/VHDX/QCOW2。
  - 是否 stage 了 SQLite 数据库、日志、构建产物。
  - 是否存在 `.env`、token、密码、私钥。
  - 是否存在未经审查的网络相关变更。
- 若发现真实镜像或敏感文件进入 Git 范围，必须 `BLOCKED`，先移出暂存或更新
  `.gitignore`。

---

## 25. 产品化路线：对标 iVentoy 后的免费版与商业版规划

更新时间：`2026-06-13`

### 25.1 iVentoy 公开文档学习结论

参考资料：

- iVentoy 自动安装文档：
  `https://www.iventoy.com/cn/doc_autoinstall.html`
- iVentoy 版本说明：
  `https://www.iventoy.com/cn/doc_edition.html`
- iVentoy 使用说明：
  `https://www.iventoy.com/cn/doc_start.html`
- iVentoy 操作系统全自动安装说明：
  `https://www.iventoy.com/cn/doc_unattend_install.html`
- iVentoy 文件注入说明：
  `https://www.iventoy.com/cn/doc_injection.html`

对 SynaBoot 有价值的设计点：

- 用户只放 ISO，平台负责展示、选择和启动。
- 自动安装脚本不必重制 ISO，可以为 ISO 绑定一个或多个脚本。
- 多个自动安装脚本可在启动时选择。
- 自动安装脚本支持变量扩展，但源文件不被修改，只在副本中展开。
- 全自动安装由默认镜像、菜单超时、默认脚本和脚本选择超时组合实现。
- 文件注入是独立框架，平台只负责注入机制，具体驱动/脚本内容由管理员维护。
- 免费版与专业版差异较少，基础能力仍可用；商业版主要覆盖商用权、规模和高级能力。

需要避开的设计点：

- 不照搬 iVentoy 的 DHCP/PXE 启动方式。SynaBoot 当前生产 LAN 有既有
  TP-Link DHCP 和 OpenWrt 网关，Phase 1/2 必须继续零侵入。
- 不要求用户手动理解过多底层启动文件。用户只放 ISO，平台应给出准备状态、
  一键准备任务和清晰错误提示。
- 不把基础装机能力做成收费门槛。
- 不允许自动安装模板默认包含破坏性磁盘分区配置。

### 25.2 SynaBoot 的产品目标

SynaBoot 要做得比 iVentoy 更适合本项目场景：

- 对使用者友好：
  - 开机进入菜单后能清楚看到可安装系统。
  - Windows 通过 HotPE 路径说明清晰。
  - Linux 启动项只在准备完成后出现，避免失败菜单。
  - 自动安装必须明确标注是否会清盘、分区、覆盖数据。

- 对管理员友好：
  - Docker Compose 一键部署。
  - `.env` 一键生成和检查。
  - `data/images` 放 ISO 后自动扫描。
  - Web UI 展示缺失依赖和准备按钮。
  - 一键生成/刷新 `menu.ipxe`。
  - 一键导出诊断包，但不得包含 token、ISO、私钥或敏感镜像内容。
  - 所有网络启动高级能力默认关闭，并有门禁状态。

- 对企业运维友好：
  - 支持镜像目录分类、标签、版本、架构、用途说明。
  - 支持自动安装脚本模板库和变量预览。
  - 支持任务日志、审计记录、回滚清单。
  - 支持后续授权模型，但本地基础部署不依赖公网。

### 25.3 免费版原则

免费版必须覆盖完整基础装机闭环：

- Docker Compose 部署。
- HTTP 镜像仓库。
- 本地 ISO 扫描。
- HotPE ISO 准备指引或本地准备任务。
- Ubuntu/Linux ISO kernel/initrd 准备指引或本地准备任务。
- Windows ISO 通过 HotPE 辅助安装。
- iPXE HTTP 菜单生成。
- 手动 iPXE USB/ISO/EFI 启动。
- 手动 UEFI HTTP Boot。
- Web UI 基础镜像管理。
- 基础 Image Factory 模板：
  - Ubuntu autoinstall 模板。
  - Windows ADK/DISM 外部任务包模板。
- 网络安全 preflight。
- Phase 3 只读启动入口状态展示。
- 基础文档、部署教程和故障排查。

免费版不得设置以下限制：

- 不限制基础镜像数量。
- 不限制基础菜单生成次数。
- 不限制手动 iPXE/HTTP Boot 使用。
- 不限制基础离线部署。
- 不因未联网激活而破坏基础功能。

### 25.4 商业版候选能力

商业版只覆盖高级效率、规模、治理和支持能力。

候选能力按优先级分层：

1. Professional 一次性买断或小团队订阅：
   - 自动安装脚本库管理。
   - 为单个 ISO 绑定多个自动安装方案。
   - 自动安装变量扩展预览。
   - 默认镜像、默认脚本、菜单超时、脚本选择超时策略。
   - 批量镜像标签、版本、生命周期管理。
   - 一键诊断包导出。
   - 更友好的 ISO 准备向导。

2. Enterprise 订阅：
   - 多管理员账号和角色权限。
   - 审计日志和操作追踪。
   - 多站点/多 SynaBoot 节点管理。
   - 镜像同步、校验、保留策略。
   - LDAP/OIDC/企业身份集成。
   - 高级报表：装机次数、成功率、机型、失败原因。
   - 商业支持、升级策略和长期维护。

3. Usage-based 或按次收费候选：
   - 大规模批量无人值守装机任务。
   - 企业级驱动包/脚本注入流水线。
   - 自动生成定制镜像任务。
   - 远程协助诊断或专家模板生成。

4. 不建议收费的能力：
   - 基础 ISO 扫描。
   - 基础菜单生成。
   - 基础手动启动。
   - HotPE 访问 Windows 镜像。
   - Ubuntu/Linux 基础启动准备。
   - 网络安全 preflight。

### 25.5 自动安装与文件注入路线

SynaBoot 后续应借鉴“绑定脚本而不重制 ISO”的思路，但必须更安全：

- 自动安装脚本作为独立资源管理：
  - Windows：`Autounattend.xml` / `unattend.xml`。
  - Ubuntu 20.04+：cloud-init `user-data` / `meta-data`。
  - Debian：preseed。
  - RHEL/CentOS/Rocky/Alma：Kickstart。
  - SUSE/openSUSE：AutoYaST。

- 一个 ISO 可绑定多个安装配置：
  - 手动选择。
  - 默认配置。
  - 超时自动选择。
  - 按 MAC、机型、标签匹配的策略留到商业版候选。

- 变量扩展必须安全：
  - 只支持白名单变量。
  - 在副本中展开，不修改源模板。
  - 展开前显示预览。
  - 涉及磁盘变量时强制高危提示。
  - 不记录密码、token、私钥。

- 文件注入必须安全：
  - 作为后续高级能力设计。
  - 注入包必须有清单、大小限制、hash 校验。
  - 解包必须防路径穿越和 symlink 越界。
  - 不默认执行注入脚本，除非管理员明确确认。

### 25.6 一键配置与部署目标

后续应新增一键部署体验，但不得绕过安全检查。

目标命令：

```bash
bash scripts/bootstrap-synaboot.sh
```

目标能力：

- 检查 Ubuntu 版本、Docker、Docker Compose。
- 生成 `.env`，提示管理员确认 `SERVER_IP`、HTTP 端口和 admin token。
- 初始化目录。
- 运行网络安全 preflight。
- 运行 `bash scripts/preflight/check-compose-config-safe.sh`。
- 可选启动 `docker compose up -d`。
- 输出 Web UI、镜像仓库和 iPXE 菜单 URL。

禁止：

- 不自动安装或启用 DHCP/ProxyDHCP/TFTP。
- 不修改防火墙、路由、DNS、网关。
- 不启用 host network 或 privileged。
- 不上传 ISO 到公网。

当前实现记录：

- 已新增：

```bash
bash scripts/bootstrap-synaboot.sh
```

- 支持参数：
  - `--server-ip <IP>`
  - `--http-bind <BIND>`
  - `--http-port <PORT>`
  - `--force-env`
  - `--start`
- 默认行为：
  - 生成或保留 `.env`。
  - 初始化项目数据目录。
  - 运行 `check-release-scope.sh`。
  - 运行 `check-private-commercial-scope.sh`。
  - 运行 `check-edition-boundary.sh`。
  - 运行 `check-public-runtime-boundary.sh`。
  - 运行 `check-autoinstall-boundary.sh`。
  - 运行 `check-subagent-governance.sh`。
  - 运行 `check-network-safety.sh`。
  - 运行 `bash scripts/preflight/check-compose-config-safe.sh`，不保存可能展开 token 的配置文件。
  - 不启动服务，除非显式传入 `--start`。
- 安全边界：
  - 不安装 Docker 或系统包。
  - 不修改现有网络设备、地址分配、解析、转发或安全策略。
  - 不启用任何自动网络启动服务或文件共享服务。
  - 不使用 host network 或 privileged。
- 本轮验证：

```bash
bash -n scripts/bootstrap-synaboot.sh
bash scripts/bootstrap-synaboot.sh --help
bash scripts/bootstrap-synaboot.sh --http-port nope
bash scripts/bootstrap-synaboot.sh --server-ip 192.168.1.168 --http-bind 18080 --http-port 18080
```

- `--http-port nope` 已按预期 `BLOCKED`。
- 默认 bootstrap 已通过发布范围预检、网络安全预检和 `bash scripts/preflight/check-compose-config-safe.sh`，
  且未启动服务。
- Web UI 新增只读部署状态：
  - API：

```text
GET /api/deployment-status
```

  - 展示数据目录、镜像目录、boot 目录、metadata/builds/logs 目录是否存在。
  - 展示免费版 manifest 与公开版本 catalog 是否存在；二者属于信息文件状态，
    API 仍有内置默认值，不作为服务启动硬门槛。
  - 只返回 `admin_configured` 布尔值，不读取或返回 `.env` 内容和
    `SYNABOOT_ADMIN_TOKEN`。
  - 不运行 Docker、网络、路由、防火墙或系统修改命令。
  - 不启用 DHCP、ProxyDHCP、TFTP、Samba、host network 或 privileged。
- 管理员教程 `docs/ADMIN_GUIDE.md` 已同步：
  - 推荐使用 `scripts/bootstrap-synaboot.sh`。
  - 发布前只读检查包含 release/private-commercial/network safety。
  - Web UI“网络安全”页说明部署就绪只读看板。
  - 自动安装只作为草稿、预览和只读绑定规划。
  - 免费发布线与私有商业流程只作为文档入口，不写敏感提交或商业实现教程。
  - 删除 shell 命令中直接携带管理员 token 的示例。

### 25.7 版本与商业化决策机制

`project_decision_agent` 扩展为产品版本与商业化决策者。

触发条件：

- 某个功能可能影响免费版/商业版边界。
- 某个高级功能可能收费、订阅、按次或买断。
- 某个能力会增加企业价值但扩大实现或维护成本。
- 某个收费设计可能损害基础装机体验。

决策原则：

- 基础装机全免费。
- 收费只覆盖高级自动化、规模化、治理、企业集成和商业支持。
- 免费版不应被人为做难。
- 商业版能力必须清晰解释价值。
- 离线基础部署不依赖联网授权。
- 任何收费能力都不得削弱网络安全门禁。

输出要求：

```text
DECISION: APPROVED / APPROVED_WITH_CONDITIONS / BLOCKED / NEEDS_RESEARCH
CHOSEN DIRECTION
EDITION / COMMERCIAL IMPACT
REASONS
REQUIRED CONDITIONS
AGENTS TO INVOLVE NEXT
VALIDATION REQUIRED
```

### 25.8 下一步落地顺序

短期先不实现 license 系统，先把产品边界写清楚。

优先顺序：

1. 完成 Phase 2.9 ISO 扫描语义增强。
2. 完成 Phase 2.10 ISO 准备任务框架。
3. 在 Web UI 增加“准备状态”和“下一步动作”。
4. 新增一键 bootstrap 脚本规划与安全审查。
5. 新增自动安装脚本资源模型草案。
6. 再由 `project_decision_agent` 决定免费版/商业版第一版边界。
7. 最后再实现 edition/capability flags，不急着接入支付或联网授权。

当前实现进度：

- 1-4 已完成并通过本地安全验证。
- 5 已进入 Phase 2.12：新增自动安装脚本资源模型草案，先覆盖免费版
  安全草稿管理，不实现商业策略、不执行无人值守安装、不默认生成清盘分区。

### 25.9 Phase 2.12：自动安装脚本资源模型草案

目标：

- 借鉴 iVentoy“ISO 绑定脚本而不重制 ISO”的方向，但当前阶段只建立
  SynaBoot 自己的资源模型。
- 免费版先提供基础自动安装草稿能力：
  - Ubuntu cloud-init/autoinstall 草稿。
  - Windows Autounattend 草稿。
  - 变量白名单展示。
  - 模板预览。
  - 高危策略标记为必须人工审查。
- `autoinstall_profiles` 只表示脚本草稿、模板类型、变量白名单和安全状态；
  不直接表达 ISO 绑定、默认策略、主机匹配或商业授权策略。
- 不在 Phase 2.12 做这些事情：
  - 不把自动安装 profile 接入启动菜单默认项。
  - 不在 profile 表中直接绑定 ISO。
  - 不自动选择磁盘、分区、格式化或清盘。
  - 不执行无人值守安装。
  - 不实现按 MAC、机型、标签匹配策略。
  - 不实现 license、支付、联网授权或商业代码混淆流水线。

当前实现记录：

- API 新增 `autoinstall_profiles` 元数据表。
- 该表为脚本草稿表，不作为 ISO 绑定表。
- API 新增：

```text
GET  /api/autoinstall-profiles
POST /api/autoinstall-profiles
GET  /api/autoinstall-binding-plan
```

- `GET /api/autoinstall-binding-plan` 是只读派生规划视图：
  - 数据来源为当前 `images`、`autoinstall_profiles` 和公开能力边界。
  - 不创建 `image_autoinstall_bindings` 表。
  - 不新增绑定写接口。
  - 不让 iPXE 菜单、任务系统或启动流程消费该规划数据。
  - 返回候选 ISO、兼容草稿数量、兼容 profile 预览、禁用原因和后续版本
    候选说明。
  - `/api/autoinstall-bindings/plan` 仅作为旧命名兼容别名，不作为真实绑定语义。
- Web UI 新增“自动安装”页面：
  - 创建 Ubuntu 草稿。
  - 创建 Windows 草稿。
  - 展示免费版边界、模板数量、执行状态和高危策略。
  - 展示 profile 的模板类型、变量白名单、破坏性策略和模板预览。
  - 展示“绑定规划”只读区块，说明 ISO/profile 真实绑定、默认脚本和菜单接入
    当前未启用。
  - 在“绑定规划”中展示同系统类型 profile 候选对，帮助管理员理解未来关系，
    但这些候选对不会保存为绑定记录。
- 免费版 capability manifest 已将基础自动安装草稿列入免费核心：

```text
basic_autoinstall_profile_drafts
autoinstall_template_variable_allowlist
```

安全边界：

- 新增 profile 只写入 metadata sqlite，不写入真实 ISO/WIM/磁盘。
- `template_preview` 中不生成密码、token、私钥。
- Ubuntu 草稿默认不生成 `storage` 自动分区配置。
- Windows 草稿默认不生成磁盘配置和产品密钥。
- 写操作仍需要 `SYNABOOT_ADMIN_TOKEN`。

后续扩展模型：

- `image_autoinstall_bindings`：
  - 表达 ISO 与 profile 的多对多绑定。
  - 表达默认项、排序、脚本选择超时。
  - 作为 Professional 候选能力的主要扩展点。
- `autoinstall_policies`：
  - 表达默认镜像、默认脚本、按 MAC/机型/标签匹配等策略。
  - 作为 Professional/Enterprise 候选能力，不进入当前 Phase 2.12 免费实现。
- 免费版继续不限基础自动安装草稿创建和预览数量；无 license、无联网时不得降级
  基础镜像扫描、菜单生成、手动启动和基础草稿管理。
- 新增自动安装边界专项预检：

```bash
bash scripts/preflight/check-autoinstall-boundary.sh
```

- 该脚本只读校验：
  - 不存在 `image_autoinstall_bindings` 或 `autoinstall_policies` 真实绑定/策略表。
  - 公开自动安装 API 只包含 profile 草稿与只读 binding plan。
  - `runtime_binding_enabled`、`menu_integration_enabled`、
    `policy_matching_enabled`、`write_api_available` 均保持 `false`。
  - Ubuntu/Windows 模板不默认包含 `storage:`、磁盘分区、产品密钥、
    自动登录、密码变量、token、secret 或私钥变量。
  - 免费版能力 manifest 保持基础自动安装草稿不限量。
  - 公开运行时白名单显式登记自动安装 API。
- 该脚本已接入 `collect-release-evidence.sh` 和 `bootstrap-synaboot.sh`，
  防止 Phase 2.12 在免费发布线中滑向商业绑定、默认策略或无人值守执行。

下一步：

1. 由 `project_decision_agent` 输出免费版/Professional/Enterprise 第一版边界。
2. 由 `architecture_agent` 复审 profile 与 binding/policy 分层是否清晰。
3. 由 `security_audit_agent` 审查模板预览、变量白名单和商业边界是否安全。
4. 通过验证后，继续只允许扩展绑定规划说明；真实 profile 与 ISO 绑定写接口、
   菜单接入和默认策略必须另由 `project_decision_agent` 决定是否进入商业候选
   或私有商业流程。

---

## 26. GitHub 免费版发布线与本机全功能策略

更新时间：`2026-06-13`

### 26.1 用户目标

当前版本策略必须同时满足：

- 用户本机部署版本永久全功能可用。
- GitHub 仓库当前分支只 push 免费版代码。
- 商业收费功能代码先不 push。
- 商业功能未来需要混淆后再进入私有商业发布流程。
- 基础装机功能永久免费。

### 26.2 发布线定义

当前 GitHub 分支：

```text
origin/codex/synaboot-phase1
```

定义为免费版发布线。

允许进入免费版 GitHub 分支：

- 基础 HTTP/iPXE Boot 平台。
- ISO 扫描与基础准备流程。
- HotPE 辅助 Windows 安装。
- Ubuntu/Linux 基础启动准备。
- 基础 Web UI。
- 基础 Image Factory 模板。
- 网络安全 preflight。
- 文档、教程、免费版能力说明。
- edition/capability flags 的公开骨架，但不得包含商业实现细节。

禁止进入免费版 GitHub 分支：

- 商业版专属源码。
- 私有 license 文件。
- 付费能力的完整实现代码。
- 混淆后的商业 bundle。
- 真实 ISO/WIM/ESD/IMG/VHD/VHDX/QCOW2 镜像。
- 生成数据库、日志、构建产物。
- `.env`、token、私钥、账号密码。

### 26.3 本机永久全功能策略

用户本机允许作为开发者/所有者环境保留永久全功能能力。

实现方向：

- 免费版公开代码提供稳定 open-core。
- 商业功能通过本机私有模块、私有配置或私有构建产物加载。
- 私有模块路径必须被 `.gitignore` 忽略。
- 本机全功能能力不得依赖公网授权才能使用。
- 商业功能代码在当前阶段不提交、不 push。

推荐私有路径：

```text
private-commercial/
commercial/
enterprise/
proprietary/
dist-commercial/
dist-obfuscated/
```

这些路径只作为本机私有工作区，不属于 GitHub 免费版发布范围。

### 26.4 商业版混淆策略

商业版代码未来进入发布前必须满足：

- 私有商业源码不进入免费版 GitHub 分支。
- 商业 bundle 经过混淆或打包后再发布给客户。
- 混淆产物不提交到当前免费版 GitHub 分支。
- license 验证不影响免费核心功能。
- 离线部署的免费功能不依赖在线激活。
- 本机 owner/developer 模式保留永久全功能能力。

当前阶段只做策略和发布防线，不实现支付、联网授权或商业混淆流水线。

补充执行边界：

- 当前免费版分支只保存混淆发布规则，不保存混淆工具、混淆配置、混淆产物
  或商业源码。
- 商业源码、license、客户包和混淆 bundle 只能位于 `.gitignore` 覆盖的
  私有目录。
- 本机 owner/developer 永久全功能能力不得成为 Docker Compose 默认挂载、
  API 默认依赖或 Web UI 默认入口。
  该规则由 `check-private-commercial-scope.sh` 检查 Compose、API 和 Web
  默认运行文件中的私有路径引用。
- 公开运行时代码不得新增 license、payment、billing、subscription、
  activation、professional、enterprise、usage-based、paid、commercial 或
  obfuscation 端点；该规则由
  `check-public-runtime-boundary.sh` 校验。

新增公开护栏文档：

```text
docs/PRIVATE_COMMERCIAL_FLOW.md
```

该文档只说明本机私有工作区、混淆产物隔离、免费核心不可降级、发布前检查
和 subagents 审查流程；不包含商业源码、license、支付、联网授权或混淆实现。

新增版本边界决策记录：

```text
docs/EDITION_BOUNDARY_DECISION.md
```

该文档固化 `project_decision_agent` 对 Free、Professional、Enterprise 和
Usage-based 第一版边界的 `APPROVED_WITH_CONDITIONS` 决策。当前只允许公开
文档、manifest、预检和只读展示，不实现 license、支付、联网授权、商业源码
或混淆流水线。

### 26.5 发布范围预检

新增预检脚本：

```bash
bash scripts/preflight/check-release-scope.sh
bash scripts/preflight/check-edition-boundary.sh
bash scripts/preflight/check-public-runtime-boundary.sh
bash scripts/preflight/check-subagent-governance.sh
```

用途：

- 默认校验 `SYNABOOT_RELEASE_CHANNEL=free`。
- 默认校验当前分支为 `codex/synaboot-phase1`。
- 默认校验当前上游为 `origin/codex/synaboot-phase1`。
- 拦截商业/私有路径进入 GitHub 免费版发布范围。
- 拦截真实镜像、license、混淆产物、数据库、日志、构建产物、`.env`、
  私钥等文件进入 Git。
- 校验 Free 核心能力不限量、公开 catalog 不作为 license gate、
  Professional/Enterprise/Usage-based 只作为候选层。
- 静态检查 API 和 Web 前端引用的 `/api/...` 运行时入口，阻断
  license、payment、billing、subscription、activation、professional、
  enterprise、usage-based、paid、commercial、obfuscation 等商业实现或
  收费层端点进入免费版公开代码。
- 校验 `.codex/agents` 仍然是 11 个项目角色，并确认 `PLAN.md` 包含
  subagent 调用预算、会话复用和超量调用复盘规则。
- commit/push 前必须由 `git_audit_agent` 执行。

当前禁止路径和产物包括：

```text
commercial/
private-commercial/
private/
enterprise/
proprietary/
paid/
dist-commercial/
dist-obfuscated/
*.obf.js
*.obf.py
*.min.private.js
*.license
*.lic
*.sqlite3
*.sqlite
*.db
data/logs/
data/builds/
data/metadata/*.sqlite3
```

### 26.6 Subagents 职责调整

- `project_decision_agent`：
  - 决定免费版、Professional、Enterprise、按次或买断的功能边界。
  - 确认基础装机能力永久免费。
  - 确认 GitHub 当前分支只作为免费版发布线。

- `architecture_agent`：
  - 设计 edition/capability flags。
  - 保持免费功能在无 license、无联网时仍可用。
  - 设计本机私有商业模块加载边界。

- `security_audit_agent`：
  - 审查商业代码是否误入免费版发布线。
  - 审查 license 逻辑是否破坏免费核心功能。
  - 审查混淆产物、授权文件和私有配置是否被误提交。

- `git_audit_agent`：
  - commit/push 前必须运行 `check-release-scope.sh`。
  - 禁止 push 商业源码、混淆产物、真实镜像和 secrets。
  - 只允许将免费版代码推送到当前 GitHub 分支。

### 26.7 下一步实现队列

1. 先完成 Phase 2.9 ISO 扫描语义增强。
2. 再完成 Phase 2.10 ISO 准备任务框架。
3. 同步实现免费版 capability manifest：

```text
config/synaboot/capabilities.free.json
```

4. Web UI 只展示免费版可用能力和未来商业能力说明，不阻断免费流程。
5. 等免费版稳定后，再由 `project_decision_agent` 决定商业版第一批功能。
6. 商业代码另走本机私有目录和私有打包流程，不进入当前 GitHub 免费版分支。

当前实现记录：

- 已新增只读能力端点：

```text
GET /api/capabilities
```

- API 优先读取：

```text
config/synaboot/capabilities.free.json
```

- Docker Compose 已将 `./config` 以只读方式挂载到 API 容器。
- Web UI 新增“版本能力”页面，展示：
  - 免费核心能力。
  - 免费版不限项。
  - 未来商业候选。
  - 禁止进入 GitHub 免费发布线的内容。
- 新增公开版本边界 catalog：

```text
config/synaboot/editions.public.json
```

- 新增商业关键词命中文件 allowlist：

```text
config/synaboot/commercial-indicators.allowlist.json
```

- `editions.public.json` 只展示 Free、Professional、Enterprise 和
  Usage-based 的第一版候选边界，不包含 license、支付、联网授权或商业实现代码。
- `GET /api/capabilities` 会同时返回 `edition_catalog`，并强制其有效输出为
  `commercial_code_included=false`、`online_activation_required=false`。
- 新增只读发布证据脚本：

```text
scripts/preflight/collect-release-evidence.sh
```

- 新增内联管理员 token 泄露专项预检：

```text
scripts/preflight/check-token-disclosure.sh
```

- 新增版本边界专项预检：

```text
scripts/preflight/check-edition-boundary.sh
```

- 新增公开运行时边界专项预检：

```text
scripts/preflight/check-public-runtime-boundary.sh
```

- 新增 subagent 治理专项预检：

```text
scripts/preflight/check-subagent-governance.sh
```

- 新增 loader 导入安全专项预检：

```text
scripts/preflight/check-loader-import-safety.sh
```

- 新增商业私有工作区专项预检：

```text
scripts/preflight/check-private-commercial-scope.sh
```

- 新增免费版发布检查清单：

```text
docs/FREE_RELEASE_CHECKLIST.md
```

- 该清单明确：
  - GitHub 当前分支只发布免费版代码。
  - 本机私有商业工作区允许存在，但不得进入 GitHub 免费发布线。
  - commit/push 前必须运行发布证据命令并经过 subagents 复核。
  - 推送远程属于高风险版本控制动作，执行前必须获得用户二次确认。

- 该脚本只读确认：
  - `commercial/`、`private-commercial/`、`private/`、`enterprise/`、
    `proprietary/`、`paid/`、`dist-commercial/`、`dist-obfuscated/`
    均被 `.gitignore` 覆盖。
  - 上述私有路径没有 tracked/staged/untracked public 文件。
  - license、混淆 bundle 和私有商业产物没有进入免费版发布范围。
  - 不创建私有目录，不读取商业代码内容，不写日志或构建产物。
- 该脚本用于 commit/push 前收集免费版发布线证据：
  - 当前分支、上游和 release channel。
  - tracked/staged/untracked/ignored 数量摘要。
  - `check-release-scope.sh`。
  - `check-private-commercial-scope.sh`。
  - `check-edition-boundary.sh`。
  - `check-public-runtime-boundary.sh`。
  - `check-autoinstall-boundary.sh`。
  - `check-subagent-governance.sh`。
  - `check-network-safety.sh`。
  - `check-phase3-gates.py`。
  - `bash scripts/preflight/check-compose-config-safe.sh`。
  - `git diff --check` 与 `git diff --cached --check`。
  - 免费版能力 manifest 与公开版本 catalog JSON 关键字段校验。
  - 商业相关关键词命中文件清单，供 `git_audit_agent` 人工复核是否仅为公开说明。
  - 商业关键词命中文件必须匹配
    `config/synaboot/commercial-indicators.allowlist.json`，新增命中文件先
    BLOCKED，再由主控更新 allowlist 并复核语义。
  - `check-token-disclosure.sh`，拦截内联管理员 token 命令示例。
  - `origin` remote 是否指向 GitHub，但不输出完整 remote URL，避免泄露凭据或私有路径。
  - `18080/tcp` 监听状态。
  - `apps/`、`scripts/` 下是否残留 Python bytecode cache。
- 新增 push 前只读就绪检查：

```bash
bash scripts/preflight/check-free-push-readiness.sh
```

- 该脚本只用于本地 commit 完成后、远程 push 前：
  - 先重新运行 `collect-release-evidence.sh`。
  - 再确认当前分支、upstream 和 origin 仍是免费版 GitHub 发布线。
  - 要求没有未提交 tracked 变更、暂存未提交变更或未跟踪 public 文件。
  - 不执行 commit，不执行 push，不输出完整 remote URL。
  - 当前开发态存在大量未提交变更时，该脚本按设计会 `BLOCKED`；
    等 `git_audit_agent` 完成审计和本地 commit 后再运行。
- 该脚本只读运行，不启动服务，不读取 `.env` 内容，不写日志或构建产物。
- `check-token-disclosure.sh` 可单独运行，也会被 `collect-release-evidence.sh`
  串联执行。它只扫描 Git 发布范围内的 tracked、staged 和 untracked public
  文件，拦截 `SYNABOOT_ADMIN_TOKEN=...` 直接拼接
  `bash/docker/curl/python/node/sh/compose` 的写法，以及历史 smoke token
  字面量；命中时只输出文件名和行号，不输出疑似 token 值。
- `check-edition-boundary.sh` 可单独运行，也会被 `collect-release-evidence.sh`
  串联执行。它校验 `capabilities.free.json` 和 `editions.public.json` 的
  免费发布线字段、Free 不限量边界、Usage-based 候选层和 no-license-gate
  展示用途，并用 AST 静态解析 `apps/api/main.py`，确认 API 内置默认
  capability/catalog 与公开 JSON 完全一致，避免配置缺失时展示边界漂移。
- `check-public-runtime-boundary.sh` 可单独运行，也会被
  `collect-release-evidence.sh` 串联执行。它只检查公开运行时代码中的
  API/前端入口，允许文档和 manifest 描述商业候选能力，但阻断商业授权、
  支付、订阅、联网激活、收费层或混淆相关实现端点进入免费分支。该脚本同时校验
  `config/synaboot/public-runtime.allowlist.json`，所有公开运行时 API
  必须显式登记；新增 API 路径前必须先经过 architecture/security/git 审计。
- `check-subagent-governance.sh` 可单独运行，也会被
  `collect-release-evidence.sh` 串联执行。它校验 `.codex/agents` 角色池
  必须保持 11 个项目角色，并确认 `PLAN.md` 中的 subagent 调用预算、
  会话复用规则和超量调用复盘没有被移除。
- 当前 `capabilities` 只是展示型 manifest：
  - 不实现 license。
  - 不实现支付。
  - 不接入联网授权。
  - 不阻断免费核心流程。
  - 不包含商业源码或混淆产物。

版本边界决策记录：

- Free：
  - 覆盖基础装机闭环。
  - 不限制基础镜像数量、基础菜单生成、手动 iPXE/HTTP Boot、基础自动安装
    草稿创建与预览。
  - 不因无 license、无联网而降级基础功能。
- Professional 候选：
  - 自动安装脚本库管理。
  - 一个 ISO 绑定多个自动安装方案。
  - 高级变量扩展预览。
  - 默认镜像、默认脚本、菜单超时、脚本选择超时。
  - 批量镜像标签、版本、生命周期管理。
  - 一键诊断包导出。
  - 更完整的 ISO 准备向导。
- Enterprise 候选：
  - 多管理员账号与 RBAC。
  - 审计日志和操作追踪。
  - 多节点/多站点管理。
  - 镜像同步、校验和保留策略。
  - LDAP/OIDC 企业身份集成。
  - 装机报表、成功率、失败原因和机型统计。
  - 企业支持、长期维护和升级策略。
