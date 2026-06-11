# SynaBoot 项目开发计划（Codex Goal Mode）

> 项目目标：在 **保证现有局域网不断网、主 DHCP 仍由 TP-Link TL-ER6120T 承担、默认网关保持 192.168.1.4 OpenWrt** 的前提下，在一台 Ubuntu 22.04 服务器上部署一个局域网内部可访问的 iPXE/HTTP Boot 系统安装平台。用户可像 Ventoy 一样选择多个系统镜像进行安装，支持 HotPE、Windows 11、Ubuntu 22.04.3 等镜像，并支持后续制作/封装预装软件、驱动和配置的自定义镜像。

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
11. 每完成一个功能或 milestone 后，让 git_audit_agent 审查 diff；通过后自动创建本地 commit，并在 project_decision_agent 批准后 push 当前 GitHub 分支。

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
- 不引入新前端框架。
- 实现 Dashboard、镜像仓库、镜像详情、菜单预览、HotPE 指南、构建任务、网络安全页。
- 所有写操作必须通过 admin token。

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
- 审计通过后可自动 stage 并创建本地 commit。
- commit message 必须说明阶段目标、核心变更和安全边界。
- 若变更涉及网络、Compose、脚本、启动入口或安全边界，push 前必须有 `network_safety_agent` 和/或 `security_audit_agent` 的通过结论。
- push 到 GitHub 当前分支前必须记录 remote、branch、commit range、提交摘要和风险摘要。
- `project_decision_agent` 确认符合项目方向后，可自动 push 到 GitHub 当前分支。
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
- `git_audit_agent` 阶段收口审查、创建本地 commit，并在决策通过后 push 当前分支。

验收：

- 所有审查均为 `APPROVED`。
- 所有 BLOCKED 项已修复。
- 每个功能或 milestone 均有对应 git 审计记录和本地 commit。
- `git_audit_agent` 记录目标 remote/branch/commit range 和风险摘要。
- `project_decision_agent` 确认阶段方向后自动 push 当前 GitHub 分支。

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
  - `docker compose config`
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
docker compose config
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
11. git_audit_agent 在每个功能或 milestone 完成后审查 diff；通过后自动创建本地 commit，并在 project_decision_agent 批准后 push 当前 GitHub 分支。

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
   - ProxyDHCP 只回答 PXE/HTTP Boot 引导信息，不分配 IP。
   - 必须默认关闭，启用前双审查。

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
- 审计通过后自动创建本地 commit。
- 记录 remote、branch、commit range、提交摘要和风险摘要。
- `project_decision_agent` 确认符合项目方向后，自动 push 到当前 GitHub 分支。

### 21.7 Phase 3 验证命令

本地服务验证：

```bash
bash scripts/preflight/check-network-safety.sh
docker compose config
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
- `git_audit_agent` 已加入阶段收口流程，负责功能/milestone 完成后的 diff 审计、本地 commit 和自动 push 当前 GitHub 分支。
- Phase 3 仍处于规划与前置调查阶段，尚未实现或启用自动 PXE 入口。
- Phase 3.0 前置调查已完成首轮公开资料研究，记录见
  `docs/BOOT_ENTRY_RESEARCH.md`。
- 当前公开证据不足以证明 TL-ER6120T/TL-ER6120 可可靠提供完整
  PXE/HTTP Boot metadata，后续必须先做本地只读确认和隔离抓包验证。

当前已知限制：

- 还未本地确认 TP-Link 设备准确型号、硬件版本和固件版本。
- 还未本地确认 TL-ER6120T/TL-ER6120 是否完整支持 Option 66、Option 67、next-server、Vendor Class 或 Client Architecture 区分。
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
     - `docker compose config`
     - `nginx -t` 使用本地 `nginx:1.27-alpine` 镜像通过。
     - `/api/boot-assets` loopback smoke test 覆盖：
       `usable`、`blocked_symlink`、`blocked_parent_symlink`。
     - Nginx loopback 静态测试覆盖：
       `/boot/menu.ipxe=200`、`/boot/loaders/ipxe.efi=200`、
       `/boot/loaders/=404`、非白名单 loader `404`、symlink loader `403`。

4. Phase 3.3：受控 TFTP/ProxyDHCP 方案设计
   - 仅在 TP-Link DHCP boot option 能力不足时进入。
   - 是否进入该路径由 `project_decision_agent` 基于 `research_agent` 证据和安全审查结论决定。
   - 当前状态：BLOCKED，等待本地只读确认 TP-Link 准确型号、硬件版本、
     固件版本、Option 66/67、next-server、Vendor Class 和 Client
     Architecture 能力。
   - 本地确认记录模板：`docs/BOOT_ENTRY_LOCAL_VERIFICATION.md`。
   - 默认关闭。
   - 不得分配 IP。
   - 不得修改网关、DNS、路由、防火墙。
   - 必须先通过 `network_safety_agent` 和 `security_audit_agent`。

5. Phase 3.4：Web UI 启动入口集成页
   - 展示 HTTP IPv4、PXE IPv4、HTTP IPv6、PXE IPv6 状态。
   - 展示要交给网络管理员的 boot server、bootfile、URL 参数。
   - 明确风险、回滚步骤和验证步骤。
   - 当前状态：只读入口状态页已实现；后续如新增可操作配置，必须重新审查。
   - 本轮只读展示增强：`/api/boot-entry` 返回 `documentation`、
     `local_verification_template` 和 `phase3_3_gate`，Web UI 展示本地确认模板、
     集成说明和 Phase 3.3 blocked 状态。
   - 本轮只读展示增强验证记录：
     - `python3 -m py_compile apps/api/main.py apps/worker/scan_images.py`
     - `node --check apps/web/assets/app.js`
     - `bash scripts/preflight/check-network-safety.sh`
     - `docker compose config`
     - `ss -lntu | grep -E ':(67|68|69|4011)\b' || true`
     - `rg -n "network_mode: host|privileged: true|67:|68:|69:|4011:|dnsmasq|proxydhcp|tftp|dhcp" docker-compose.yml scripts apps config docs PLAN.md README.md`
     - `git diff --check`
     - `boot_entry_status()` smoke test 覆盖 `documentation`、
       `local_verification_template`、`phase3_3_gate.status=blocked_until_local_verification`
       以及 DHCP/ProxyDHCP/TFTP 均为关闭。

6. Phase 3.5：文档与验证
   - 新增 `docs/BOOT_ENTRY_INTEGRATION.md`。
   - 新增 `docs/BOOT_ENTRY_LOCAL_VERIFICATION.md`。
   - 更新 README/ADMIN_GUIDE/NETWORK_SAFETY。
   - 单台测试机验证 UEFI PXE IPv4。
   - 验证普通终端 DHCP、网关、内网和互联网不受影响。
   - 当前状态：已创建只读文档草案；真实测试机验证等待 Phase 3.3 门禁解除。
   - 本轮文档门禁同步验证记录：
     - `bash scripts/preflight/check-network-safety.sh`
     - `docker compose config`
     - `ss -lntu | grep -E ':(67|68|69|4011)\b' || true`
     - `rg -n "network_mode: host|privileged: true|67:|68:|69:|4011:|dnsmasq|proxydhcp|tftp|dhcp" docker-compose.yml scripts apps config docs PLAN.md README.md`
     - `git diff --check`
   - 本轮本地只读确认模板验证记录：
     - `bash scripts/preflight/check-network-safety.sh`
     - `docker compose config`
     - `ss -lntu | grep -E ':(67|68|69|4011)\b' || true`
     - `rg -n "network_mode: host|privileged: true|67:|68:|69:|4011:|dnsmasq|proxydhcp|tftp|dhcp" docker-compose.yml scripts apps config docs PLAN.md README.md`
     - `git diff --check`

7. Phase 3.6：阶段收口
   - `network_safety_agent` 复审。
   - `security_audit_agent` 复审。
   - `git_audit_agent` 审查 diff、验证记录和敏感信息。
   - 审计通过后创建本地 commit。
   - `project_decision_agent` 确认阶段方向后，由 `git_audit_agent` 自动 push 当前 GitHub 分支。

### 22.3 GitHub 推送策略

用户期望：

- `git_audit_agent` 审计确认无问题后，自动 push 到 GitHub 当前分支。

当前执行策略：

- 远程 push 降级为版本控制收口动作，不再按 LAN 高风险操作处理。
- `git_audit_agent` 审计 diff、secrets、危险脚本、无关文件和验证记录。
- 涉及网络、Compose、脚本、启动入口或安全边界的变更，必须先通过 `network_safety_agent` 和/或 `security_audit_agent`。
- `project_decision_agent` 确认阶段方向和推送范围后，`git_audit_agent` 自动 push 到 GitHub 当前分支。
- 不得 push secrets、`.env`、真实凭据、未审查网络影响变更或无关文件。

当前远程与分支：

```text
remote: origin git@github.com:Flashyuan/FlashPXE.git
branch: codex/synaboot-phase1
```

---

## 23. Subagents 协作模式与通信机制

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
  → git_audit_agent 审查 diff、创建本地 commit、自动 push 当前分支
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
  → security_audit_agent / network_safety_agent 按风险复审
  → git_audit_agent 审查 diff、敏感信息和验证记录
  → project_decision_agent 确认阶段方向和推送范围
  → 创建本地 commit
  → 自动 push 当前 GitHub 分支
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
