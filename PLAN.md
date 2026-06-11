# SynaBoot 项目开发计划（Codex Goal Mode）

> 项目目标：在 **不影响现有局域网网络架构、DHCP、网关、路由、DNS、防火墙、OpenWrt、TP-Link 主路由/交换机配置** 的前提下，在一台 Ubuntu 22.04 服务器上部署一个局域网内部可访问的 iPXE/HTTP Boot 系统安装平台。用户可像 Ventoy 一样选择多个系统镜像进行安装，支持 HotPE、Windows 11、Ubuntu 22.04.3 等镜像，并支持后续制作/封装预装软件、驱动和配置的自定义镜像。

---

## 0. 最高优先级安全原则

本项目运行在生产办公局域网内，任何可能影响现有网络通信的行为都必须默认禁止。

### 0.1 绝对禁止

任何 agent、脚本、服务、Docker Compose、安装命令，都不得执行以下操作：

- 不得安装、启动、启用 DHCP Server。
- 不得启用 ProxyDHCP。
- 不得运行 dnsmasq 的 DHCP/ProxyDHCP 模式。
- 不得修改主路由 DHCP 配置。
- 不得修改 TP-Link 企业路由器配置。
- 不得修改 OpenWrt 配置。
- 不得修改默认网关。
- 不得修改主机 DNS。
- 不得修改交换机、AP、VLAN、STP、端口隔离、ACL 配置。
- 不得执行 `iptables`、`nft`、`ufw`、`firewalld`、`route`、`ip route add/change/del`、`nmcli connection modify` 等会改变现有网络路径/防火墙/路由的命令。
- 不得让 Docker 容器使用 `network_mode: host`，除非 NetworkSafetyAgent 明确批准。
- 不得占用 UDP 67/68/69/4011。
- 不得监听 DHCP/TFTP 相关端口。
- 不得以“为了方便 PXE”作为理由修改现网 DHCP Option 66/67。
- 不得让任何服务成为默认网关、DNS 或 DHCP。

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
iPXE 自动访问 http://<SYNABOOT_SERVER_IP>:8080/boot/menu.ipxe
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
输入或选择 http://<SYNABOOT_SERVER_IP>:8080/boot/ipxe.efi 或 menu.ipxe
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
  - Web UI：`http://<SERVER_IP>:8080`
  - 镜像 HTTP 仓库：`http://<SERVER_IP>:8080/images/`
  - iPXE 菜单：`http://<SERVER_IP>:8080/boot/menu.ipxe`
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
│       ├── pxe-agent.toml
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
set base-url http://192.168.1.168:8080

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
echo Boot HotPE, then open \\192.168.1.168\images or http://192.168.1.168:8080/images/windows/
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
http://192.168.1.168:8080/images/windows/
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
  - `8080:8080/tcp` Web/HTTP 镜像服务
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
- 是否已有服务占用 8080。
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

### 8.1 network_safety_agent

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

### 8.2 architecture_agent

职责：

- 设计整体架构。
- 设计目录结构。
- 设计 API。
- 设计数据库模型。
- 拆分 milestone。
- 不得修改网络配置。

### 8.3 pxe_agent

职责：

- 设计 iPXE menu。
- 设计 HotPE 启动项。
- 设计 Ubuntu 启动项。
- 设计 iPXE ISO/EFI 生成脚本。
- 不得实现 DHCP/ProxyDHCP/TFTP。

### 8.4 storage_agent

职责：

- 设计镜像目录。
- 设计 HTTP 静态文件服务。
- 设计可选 Samba 共享。
- 实现镜像扫描、hash、元数据。
- Samba 变更必须先让 network_safety_agent 审查。

### 8.5 image_factory_agent

职责：

- 设计镜像制作任务系统。
- 设计 Ubuntu autoinstall 镜像制作流程。
- 设计 Windows ADK/DISM 外部构建流程。
- 不得在 Ubuntu 上假装可以完整无风险封装所有 Windows 镜像。
- 必须明确哪些任务需要 Windows 构建机。

### 8.6 webui_agent

职责：

- 实现 Web UI。
- 实现镜像管理页面。
- 实现启动菜单预览。
- 实现任务管理页面。
- 不得引入公网依赖。
- 不得上传镜像到第三方。

### 8.7 security_audit_agent

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
- 只开放 8080 TCP。
- 映射 `./data/images` 为 HTTP 静态目录。
- 提供 `/images/` 浏览。
- 提供 `/boot/menu.ipxe` 静态样例。

验收：

```bash
curl http://localhost:8080/
curl http://localhost:8080/boot/menu.ipxe
curl http://localhost:8080/images/
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
curl http://localhost:8080/api/images
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
curl http://localhost:8080/boot/menu.ipxe
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

- 浏览器访问 `http://<SERVER_IP>:8080` 可用。
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
1. 先让 network_safety_agent 审查 PLAN.md、AGENTS.md、docker-compose.yml、所有脚本的网络安全边界。
2. 让 architecture_agent 设计最小可用架构和目录。
3. 让 pxe_agent 实现 iPXE HTTP Boot 菜单生成，严禁 DHCP/ProxyDHCP/TFTP。
4. 让 storage_agent 实现 data/images 镜像仓库扫描和 HTTP 静态访问。
5. 让 webui_agent 实现最小 Web UI。
6. 让 image_factory_agent 只实现镜像制作任务框架和 Ubuntu autoinstall 模板，不要承诺 Linux 上完整封装 Windows ISO。
7. 最后让 security_audit_agent 和 network_safety_agent 共同审查所有变更。

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
