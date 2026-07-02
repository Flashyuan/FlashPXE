# 管理后台 ISO-first 与客户端部署编排规划

本文档记录 SynaBoot 下一阶段管理后台和部署编排方向。目标是把管理员视角从
“底层启动文件清单”收敛为“我上传了哪些 ISO、哪些可启动、哪些机器正在安装、
哪些软件配置要下发”。

## 1. 设计依据

iVentoy 的公开使用路径对管理员很友好：把 ISO 放入指定目录，打开 Web GUI，
启动 PXE 服务后客户端即可选择镜像。SynaBoot 借鉴这种体验，但不照搬底层实现：

- 管理员默认只管理源 ISO。
- 平台自动识别 ISO 类型和版本。
- 平台按 OS family 选择启动策略。
- 派生启动文件只作为内部就绪证据和排错信息，不作为主列表对象。
- 任何自动 PXE、ProxyDHCP、TFTP 能力继续默认关闭并受安全门禁约束。

## 2. 当前已验证策略

已经在实验环境验证可用：

- Windows 11：通过 FlashPXE 进入 Windows 安装环境；SMB 继续提供 Windows 镜像
  和 HotPE 模块目录。
- HotPE V2.8：通过 `wimboot` 启动。
- Ubuntu 22.04.3 Desktop：HTTP 提供 kernel/initrd，NFS 提供 casper livefs。
- Ubuntu 24.04 Desktop：HTTP 提供 kernel/initrd，NFS 提供 casper livefs。

已验证不可作为正式路径：

- Ubuntu SMB/CIFS livefs。
- Ubuntu HTTP ISO RAM fallback。
- 正式菜单中的 Diagnostics 入口。

## 3. 后台信息架构

后台主导航建议收敛为：

- 总览：服务状态、镜像数量、ready 数量、客户端安装会话摘要。
- 镜像：只展示源 ISO，派生文件折叠到详情页。
- 启动菜单：展示最终会出现在 FlashPXE 的 ready 条目。
- 客户端：展示正在通过 FlashPXE/PXE 安装或启动的机器。
- 软件配置：管理安装后软件、脚本和配置包。
- 实验/安全：展示 Phase 3、NFS/SMB、网络端口和审计门禁。

镜像页默认列字段：

```text
ISO 名称
系统识别
版本/架构
启动策略
准备状态
菜单状态
最后扫描时间
操作
```

详情页默认只展示：

- 识别证据。
- 缺失依赖。
- 生成的菜单摘要。
- 当前策略的网络依赖。

以下内容只进入折叠技术信息或日志，不在主工作区展开：

- `vmlinuz`、`initrd`、`squashfs`、`BCD`、`boot.wim` 等派生启动文件。
- sha256、真实路径、策略内部证据。
- 排错信息。

## 4. 数据模型草案

### 4.1 SourceImage

管理员上传或放入的原始 ISO。

关键字段：

- `id`
- `path`
- `filename`
- `size`
- `sha256`
- `uploaded_at`
- `last_scanned_at`
- `detected_family`
- `detected_distro`
- `detected_version`
- `detected_arch`
- `detection_confidence`
- `strategy_key`
- `readiness`

### 4.2 BootStrategy

某类 ISO 的启动策略。

关键字段：

- `key`
- `family`
- `display_name`
- `required_artifacts`
- `required_protocols`
- `generator`
- `risk_level`
- `status`

初始策略：

- `windows_hotpe_assisted`
- `hotpe_wimboot`
- `ubuntu_desktop_nfs_livefs`
- `research_required`
- `unsupported_source_only`

### 4.3 DerivedBootArtifact

由 ISO 提取或准备出的启动工件。

示例：

- `casper/vmlinuz`
- `casper/initrd`
- `casper/*.squashfs`
- `.disk/casper-uuid-generic`
- `BCD`
- `boot.sdi`
- `boot.wim`
- `wimboot`

这些对象不进入管理员主列表。

### 4.4 ClientInstallSession

记录已经进入 FlashPXE/iPXE 的客户端。该模型不能代表固件 PXE 阶段已经被
后台看见，只能代表客户端已经访问过 FlashPXE HTTP 入口。

关键字段：

- `session_id`
- `session_token_hash`
- `mac`
- `ip`
- `uuid`
- `serial`
- `asset`
- `manufacturer`
- `product`
- `hostname`
- `platform`
- `buildarch`
- `boot_mode`
- `selected_image_id`
- `assignment_id`
- `state`
- `first_seen_at`
- `last_seen_at`
- `expires_at`
- `evidence`

状态建议：

- `ipxe_menu_loaded`
- `waiting_assignment`
- `assignment_received`
- `booting`
- `installer_callback_required`
- `installer_started`
- `postinstall_started`
- `completed`
- `failed`
- `timed_out`

### 4.5 SoftwareProfile

安装后软件、脚本、配置包的声明式配置。

关键字段：

- `id`
- `name`
- `os_family`
- `execution_phase`
- `manifest_path`
- `hash`
- `risk_level`
- `review_status`

### 4.6 DeploymentAssignment

单机或批量分配关系。

关键字段：

- `id`
- `target_selector`
- `source_image_id`
- `software_profile_id`
- `mode`
- `status`
- `created_by`
- `created_at`

## 5. ISO 识别与策略矩阵

### Windows

识别依据：

- `sources/install.wim`
- `sources/install.esd`
- Windows boot media 结构

策略：

- `windows_hotpe_assisted`
- 不生成“原始 ISO 直接启动”菜单。
- 菜单名称使用镜像名，不附加实现后缀。

### HotPE

识别依据：

- HotPE 命名特征。
- Windows PE boot media 结构。

策略：

- `hotpe_wimboot`
- 依赖 `wimboot`、BCD、boot.sdi、boot.wim 等工件。

### Ubuntu Desktop

识别依据：

- `casper/vmlinuz`
- `casper/initrd`
- `.disk/info`
- casper livefs

策略：

- `ubuntu_desktop_nfs_livefs`
- HTTP 只负责 kernel/initrd。
- NFS 提供只读 casper livefs。
- 不再使用 SMB/CIFS livefs。

说明：

- casper 官方支持 `netboot=nfs`、`nfsroot=`，也支持 `url=` 下载 ISO。
- SynaBoot 已在实验环境验证 NFS livefs 可进入 Ubuntu Desktop 安装/启动流程。
- `url=` / HTTP ISO RAM 只保留为诊断或条件路径，不作为长期正式路径。

资料：

- <https://manpages.ubuntu.com/manpages/focal/man7/casper.7.html>

### Proxmox VE / PVE

官方资料结论：

- Proxmox VE 自动安装支持网络启动，但需要使用
  `proxmox-auto-install-assistant prepare-iso --pxe` 将准备后的 ISO 拆分为
  `vmlinuz` 和 `initrd.img`。
- `--pxe-loader ipxe` 可生成 iPXE 配置片段。
- answer file 可通过 HTTP 获取，适合后续按 MAC/IP 生成单机配置。
- PVE ISO 内还存在 `boot/linux26`、`boot/initrd.img` 等安装器启动文件，但不能
  因此把普通 PVE ISO 直接标记为 ready；自动安装涉及目标磁盘和 answer 文件，
  必须单独安全审查。

初始实现策略：

- `research_required`

处理规则：

- 不套用 Ubuntu casper/NFS 逻辑。
- 第一阶段识别为 PVE 后标记 `research_required`，避免误生成菜单。
- 后续新增 `proxmox_auto_install_pxe` 策略：
  - 生成/校验 answer file。
  - 调用官方 assistant 在隔离任务中输出 `vmlinuz`、`initrd.img` 和 iPXE 片段。
  - 只有任务成功后才将源 ISO 置为 ready。

资料：

- <https://pve.proxmox.com/wiki/Automated_Installation>
- <https://pve.proxmox.com/pve-docs/chapter-pve-installation.html>

### Debian / RHEL / Anaconda 类

初始策略：

- `research_required`

处理规则：

- Debian netboot 与完整 ISO 的目录/内核形态不同，需按 Debian 官方 netboot 机制
  单独确认，不从普通 ISO 直接推断 ready。
- Debian 稳定网络启动路径应优先使用官方 netboot 文件，例如 `linux`、`initrd.gz`
  和对应 UEFI loader；普通 ISO 可作为安装源候选，但不等于已具备网络启动入口。
- RHEL/Anaconda 类安装器通常需要从 ISO 提取
  `images/pxeboot/vmlinuz` 和 `images/pxeboot/initrd.img`，并通过
  `inst.repo=` 或 `inst.stage2=` 指向包含 `.treeinfo` 的安装源。
- 在没有实现安装源展开和 `.treeinfo` 校验前，不生成 ready 菜单。

资料：

- <https://wiki.debian.org/PXEBootInstall>
- <https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/automatically_installing_rhel/preparing-for-a-network-install_rhel-installer>

### Unknown ISO

策略：

- `unsupported_source_only`
- 只展示源 ISO 和识别失败原因。
- 不生成菜单。

## 6. 客户端会话追踪

Phase 2 只使用零侵入信号：

- iPXE 菜单加载 HTTP 回调。
- 镜像选择 HTTP 回调。
- 启动前 HTTP 回调。
- 安装器或 postinstall 脚本可选回调。

禁止：

- 不通过 DHCP 分配 IP。
- 不监听 UDP 67/69/4011。
- 不改变网关、DNS、路由或防火墙。
- 不把客户端追踪做成生产 LAN ProxyDHCP 的隐式启用入口。

## 7. 软件市场、软件安装与批量分配

下一轮软件菜单不再只是“软件配置”占位页，而是管理员可维护的软件市场。
管理员管理的是软件包族，例如“飞书”，平台再按目标系统选择 Windows 或 Ubuntu
等不同安装变体。

软件市场必须保持轻量目录模型：

- SynaBoot 不存放第三方软件安装包，只保存官方 URL、官方包源、企业批准镜像源、
  校验策略、安装动作和审核状态。
- 客户端完成 OS 安装后自行从软件官网或官方源下载对应版本；Windows 和 Ubuntu
  分别执行自己的 runner 分支。
- 即使后续软件市场收录大量常用软件，本项目服务器也只保存目录 metadata、官方
  来源链接和受审安装脚本，不保存、缓存、镜像或代理第三方安装包。
- 镜像仓库只管理 ISO/WIM/ESD 和启动派生工件，不承载第三方软件包分发职责。
- 如果某软件没有可验证的官方下载链路或校验策略，后台可以展示，但不能加入
  自动安装任务。

软件页目标体验：

- 像 Windows Store / Apple App Store 一样展示应用市场。
- 首页展示应用卡片、分类、搜索、适用系统、最近更新和常用软件。
- 应用详情展示 Windows/Ubuntu/PVE 等不同系统版本、安装方式、hash、manifest
  和审查状态。
- 软件市场不托管第三方安装包。平台只保存官方下载安装链接、官方仓库信息、
  安装脚本模板、hash/signature 校验策略和审查状态。
- 被分配安装的软件由目标系统在安装后访问官网、官方软件源或管理员批准的企业
  镜像源下载安装。
- 创建安装任务时，管理员选择应用，平台自动选择目标系统对应的
  `SoftwareVariant`。
- 目标系统没有兼容变体时，该应用不可选，并显示缺失原因。

- 创建 `SoftwarePackage`，表示管理员看到的软件，例如飞书、浏览器、驱动工具。
- 创建 `SoftwareVariant`，表示该软件面向某个 OS family 的安装包，例如
  Windows `.msi/.exe`、Ubuntu `.deb/apt`。
- 创建 `SoftwareProfile`，表示一组默认软件选择。
- 绑定到单台客户端或批量选择。
- 分配系统镜像后，只展示兼容该系统的软件变体。
- 展示风险、适用 OS、安装阶段和审查状态。
- 不自动执行危险脚本。

第二阶段按 OS 接入执行点：

- Windows：HotPE 辅助流程只负责进入安装路径，普通业务软件优先通过
  `SetupComplete.cmd`、首次登录脚本或安装后 runner 执行。
- Ubuntu：autoinstall/cloud-init/late-commands 或首次启动 systemd 服务。
- PVE：待官方启动和安装机制研究后再决定。

安全要求：

- 所有软件包和脚本必须有 manifest。
- 必须限制大小、hash、来源域名、下载 URL、签名策略和执行阶段。
- 第三方安装包默认不得存放在 SynaBoot 服务器上。
- 默认不包含清盘、分区、格式化、改网络、改防火墙等危险动作。
- 密码、token、私钥不得进入日志、Git 或前端明文。

按钮事件要求：

- “设置管理员 token”必须调用 `GET /api/admin/session` 验证，成功后才保存。
- “客户端分配”必须进入分配面板，提交 `POST /api/deployment-assignments`；
  短期可兼容 `POST /api/client-sessions/<id>/assign`。
- “上传 ISO”必须接入 `POST /api/uploads/iso` 或本地 drop-folder + `POST /api/scan`，
  不允许继续停留在纯前端 alert。
- Web UI 自动刷新改为 5 分钟，手动刷新保持即时。

详细规划见：`docs/SOFTWARE_MARKET_AND_ADMIN_ACTIONS_PLAN.md`。

客户端页修正：

- `客户端` 页面不是普通状态页，而是安装任务创建与分配工作台。
- 支持单选一台客户端创建单机任务。
- 支持多选一批客户端创建批量任务。
- 批量任务默认给所有选中客户端下发相同系统镜像和相同软件集合。
- 后续支持按 MAC/UUID/型号/标签拆分不同任务。
- `DeploymentAssignment` 需要支持 `session_ids`，以表达批量任务。

## 8. Subagents 分工

- `architecture_agent`：数据模型、API 边界、阶段拆分。
- `storage_agent`：源 ISO 清单、扫描、hash、识别证据、派生物边界。
- `image_factory_agent`：OS-specific 准备任务和软件配置任务包。
- `boot_entry_agent`：Boot Strategy 到 FlashPXE 菜单和客户端回调的映射。
- `webui_agent`：ISO-first 后台、客户端会话、软件分配体验。
- `research_agent`：PVE 和未知 OS 的官方启动方式调查。
- `network_safety_agent`：端口、NFS/SMB、PXE/ProxyDHCP/TFTP 与生产 LAN 风险。
- `security_audit_agent`：ISO 解析、脚本执行、软件包注入、路径和密钥安全。
- `tutorial_docs_agent`：管理员路径、真实环境避坑、策略矩阵和回滚文档。
- `project_decision_agent`：优先级、阶段边界、免费/商业边界。
- `git_audit_agent`：防止 ISO、客户脚本、软件包、日志和敏感信息进入 Git。

## 9. 实施顺序

1. 更新 `/api/images` 和后台镜像页，让源 ISO 成为主对象。
2. 新增 Boot Strategy Registry。
3. 为 Windows、HotPE、Ubuntu Desktop 绑定已验证策略。
4. 为 PVE/Unknown ISO 返回 `research_required` 或 `unsupported_source_only`。
5. 增加客户端会话只读模型和 iPXE 回调规划。
6. 增加软件市场、软件变体、软件配置与分配模型草案。
7. 修复管理员按钮后端事件：token 验证、客户端分配、ISO 导入/扫描。
8. 进入实现前重新做安全、网络和 Git 审计。

客户端等待室详细规划见：`docs/PXE_CLIENT_WAITING_ROOM_PLAN.md`。

## 10. 2026-06-18 第一阶段进展

已完成：

- `/api/images` 返回 ISO-first payload，同时保留旧 `images` 全量数组。
- 新增 `source_images` 作为管理员后台主列表数据源。
- 新增 `artifacts` / `derived_artifacts`，用于详情页展示派生启动工件。
- 镜像行新增 `object_type`、`visibility`、`strategy_key`、`strategy_status`、
  `detection_*` 等字段。
- Linux ISO 保守识别扩展到 PVE、Debian、RHEL/Rocky/Alma/CentOS 命名特征；
  除已验证的 Ubuntu Desktop 外，默认保持 `research_required`。
- 管理后台镜像页默认只展示源 ISO。
- 派生启动工件不进入管理员主列表，仅作为内部就绪证据。
- 镜像详情把路径、sha256 等信息折叠到技术信息。
- 总览页改为可安装 ISO、待准备/研究、当前客户端、软件配置四类摘要。
- 新增客户端和软件配置导航骨架，为后续批量装机和批量软件分配预留入口。
- PVE/未知 Linux ISO 不再被误认为 ready，初始进入 `research_required`。

尚未实现：

- 客户端安装会话真实回调。
- 软件市场、OS-specific 软件变体和安装后执行计划。
- 管理员 token 验证、客户端分配面板、上传 ISO 后端动作。
- PVE/Proxmox VE 的真实启动策略。
- Phase 3 自动 PXE 入口运行时能力。

当前验证：

- Python 编译通过。
- Web 前端构建通过。
- subagent 治理、Compose 配置、免费发布范围、公开运行时边界通过。
- 网络安全预检被既有实验隔离监听阻塞；本轮代码没有新增 UDP 67/69/4011 监听。
