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

## 2026-07-02 HotPE 自动挂载 SMB 与自动加载模块规划

目标：在不影响 Ubuntu 启动链路、不停掉现有 SMB 服务的前提下，让通过
FlashPXE 启动的 HotPE 能自动访问 SynaBoot 镜像目录、Windows 安装目录和
HotPE 外置功能模块目录。

规划结论：

- HotPE 自动挂载 SMB 是可行方向，但执行点必须在 HotPE/WinPE 内部，而不是
  iPXE 阶段。iPXE/wimboot 只负责启动 `boot.wim`；进入 PE 后才执行
  `net use`、`PECMD`、`HotPE.INI` 或启动脚本。
- SMB 不必须使用独立 IP。生产环境可以复用 `SERVER_IP`，例如
  `\\<SERVER_IP>\synaboot-images`、`\\<SERVER_IP>\hotpe-mods`、
  `\\<SERVER_IP>\win11`。前提是 `445/tcp` 未被占用，且 Compose 只绑定
  指定 IP，不使用 `network_mode: host`，不使用特权容器。
- 现有 SMB 不能因为 HotPE 自动化改造而停掉或改为 Ubuntu livefs 通道。
  SMB 继续只服务 Windows/HotPE 的镜像和模块访问；Ubuntu Desktop 继续走
  `HTTP kernel/initrd + NFS casper livefs`。
- HotPE 自动加载模块应基于已提取的
  `data/images/pe/hotpe/runtime/HotProgMods` 和 `HotPE/Data`。如果 HotPE
  支持 `PECMD` 或模块管理器命令行，可在自动挂载后导入 `.HPM`；如果只支持
  GUI 模块管理，则先实现自动挂载和目录快捷方式，再保留人工导入。
- 自动挂载脚本不得把 SMB 密码写入 Git、公开 HTTP 目录、`data/images` 或
  `boot.wim` 的可公开审计文件。第一阶段可使用管理员显式配置的只读账号；
  后续再设计 token/临时凭据或仅实验环境凭据注入。

本轮实验实现：

1. 已新增 `scripts/image-factory/render-hotpe-automount-assets.py`，根据管理员
   显式提供的 SMB host/user/password/share 配置生成 HotPE 运行态脚本。
2. 含 SMB 密码的 `mount-synaboot-shares.cmd` 和 `load-hotpe-modules.cmd`
   只写入 `data/secrets/hotpe/automount/`，目录 `0700`、文件 `0600`，
   且被 `.gitignore` 覆盖。
3. 公开 HTTP 镜像目录只生成无密文标记：
   `data/images/pe/hotpe/runtime/AutoMount/manifest.json` 和 `README.txt`。
   这些文件只描述盘符、共享名、模块数量和 `boot.wim` hash，不包含密码。
4. 当前实验默认盘符：
   - `Z:` → `\\10.101.8.135\synaboot-images`
   - `M:` → `\\10.101.8.135\hotpe-mods`
   - `W:` → `\\10.101.8.135\win11`
5. 模块加载暂按 Level 1/1.5 执行：自动挂载 `M:`，并对白名单 HPM 执行
   `start "" "M:\*.HPM"`，再打开模块目录。若 HotPE 模块管理器不支持命令行
   直接导入，管理员仍可在已挂载目录中手动导入。
6. 已新增 `scripts/preflight/check-hotpe-automount-safety.sh`，验证：
   密码缺失 fail-closed、公开目录无密文、`boot.wim` 未被修改、主
   `docker-compose.yml` 不新增 SMB 服务、实验 SMB 仍只读、生成器/产物不包含
   Ubuntu casper/NFS 语义。

后续仍需：

1. 在真实 HotPE 桌面内确认 `PECMD`、`HotPE.INI`、桌面启动项或 `startnet.cmd`
   哪个入口最稳定，再决定是否自动注入或仅提供管理员手工复制步骤。
2. 若要把 Samba 从实验 IP 迁移到主机 `SERVER_IP`，必须先由
   `network_safety_agent` 审查端口绑定、生产 LAN 暴露范围和回滚方案。
3. 不得把该 SMB 自动挂载链路复用于 Ubuntu Desktop livefs；Ubuntu 继续走
   `HTTP kernel/initrd + NFS casper livefs`。

## 2026-06-18 ISO-first 管理后台与自动策略方向

当前方向从“展示仓库里的所有文件”调整为“管理员只管理源 ISO，系统自动准备启动环境”。

阶段目标：

- 镜像页只展示管理员上传的 ISO，隐藏 `vmlinuz`、`initrd`、`squashfs`、
  `BCD`、`boot.wim` 等派生启动文件。
- 总览页展示可安装 ISO 数量、系统名称、待准备/待研究镜像、当前 PXE/HTTP
  客户端会话和软件配置摘要。
- 上传新 ISO 后自动识别系统类型，再选择对应 Boot Strategy：
  - Windows ISO：通过 HotPE 辅助安装，不把 SMB 用作 Ubuntu livefs。
  - HotPE ISO：通过 `wimboot` 启动。
  - Ubuntu Desktop ISO：HTTP 加载 kernel/initrd，NFS 提供 casper livefs。
  - Proxmox VE / PVE：不得复用 Ubuntu casper/NFS；后续按官方
    `proxmox-auto-install-assistant prepare-iso --pxe` 策略实现。
  - Debian/RHEL/Anaconda 类：先进入 `research_required`，确认 netboot
    内核、initrd、安装源和 `.treeinfo` 后再生成 ready 菜单。
  - Unknown ISO：只保留源 ISO，不生成菜单。
- 客户端会话通过零侵入 HTTP 回调进入后台；不得通过生产 DHCP、ProxyDHCP 或
  TFTP 隐式启用来实现“在线客户端”统计。
- 软件安装先建立配置模型和分配模型，危险执行点必须独立安全审查。

实施记录见：`docs/ADMIN_ISO_FIRST_DEPLOYMENT_PLAN.md`。

## 2026-06-18 PXE 客户端等待室与后台任务分配方向

调研结论：通过 PXE/HTTP Boot 进入 FlashPXE 后，客户端可以被管理员后台识别，
并可停留在等待分配界面。可见性边界如下：

- 客户端仍停在固件 PXE / UEFI HTTP Boot 阶段时，Web 后台不能直接识别它；
  只有未来安全门禁下的 DHCP Boot Metadata、ProxyDHCP 或 TFTP 日志才可能看见
  更早阶段。
- 客户端进入 iPXE 并访问 FlashPXE HTTP 脚本后，可以通过 HTTP query 或
  iPXE request params 上报 MAC、UUID、serial、asset、platform、buildarch、
  IP 等字段。
- 这些字段只能用于会话识别和资产匹配，不能作为强身份认证。

目标链路：

```text
iPXE 入口
  -> /api/ipxe/register 登记客户端
  -> 等待室脚本轮询 /api/ipxe/wait
  -> 管理后台分配系统镜像和软件配置
  -> 返回 Windows / HotPE / Ubuntu / PVE 等 OS-specific 启动脚本
  -> 安装器或安装后脚本继续回调状态
```

实施要求：

- Phase 2 只使用 HTTP 登记与轮询，不启用 DHCP、ProxyDHCP、TFTP 或 UDP
  `67/69/4011`。
- 等待室 endpoint 返回 `#!ipxe` 脚本，而不是 JSON。
- 轮询必须限速并有会话 TTL。
- 后台新增 `ClientInstallSession`、`DeploymentAssignment`、`ClientEvent`、
  `SoftwareProfile` 模型。
- Windows、HotPE、Ubuntu 先绑定已验证启动策略；PVE 和未知 ISO 必须先进入
  `research_required`。

详细规划见：`docs/PXE_CLIENT_WAITING_ROOM_PLAN.md`。

## 2026-06-19 软件市场与管理员按钮后端化计划

下一轮开发目标是把“软件”菜单做成面向管理员的软件市场，并修复当前后台按钮只有
前端占位、缺少真实后端语义的问题。

软件市场方向：

- 管理员看到的是软件名称，例如“飞书”，不是零散安装命令。
- 每个软件可以有多个系统变体，例如 Windows `.exe/.msi`、Ubuntu `.deb/apt`。
- 给客户端分配系统镜像后，后台只展示与该系统兼容的软件包版本。
- 每次进入被动安装都是新的 `ClientInstallSession`，每次后台分配都是新的
  `DeploymentAssignment`，同一台机器可以反复重装和重新分配软件。
- Windows 软件优先在完整 Windows 安装后执行，不默认在 WinPE 中运行普通业务
  安装器。
- Ubuntu 软件优先通过 autoinstall/cloud-init、late-commands 或首次启动服务
  执行。
- 软件市场必须采用“应用目录 + 官方来源安装编排”模式：SynaBoot 只保存软件
  metadata、官网/官方包源/批准企业镜像源 URL、安装模板、校验与审核状态；
  第三方软件安装包不得上传、缓存、镜像或通过 SynaBoot HTTP/SMB 静态目录代理
  分发。被选中的客户端应在系统安装后自行访问官方来源下载安装。

本轮按钮修复方向：

- “设置管理员 token”必须先调用后端验证，成功后才保存到浏览器。
- “客户端分配”必须打开可见分配面板，选择镜像和兼容软件配置后提交后端。
- “上传 ISO”必须触发后端导入/扫描流程；若大文件上传暂缓，也必须提供本地
  drop-folder 扫描动作，不能继续只是 `alert`。
- Web 管理后台自动刷新改为每 5 分钟一次；手动刷新按钮保持即时刷新。

详细事件契约见：`docs/SOFTWARE_MARKET_AND_ADMIN_ACTIONS_PLAN.md`。

## 2026-06-20 软件市场与客户端任务编排界面修正

当前 UI 信息架构需要继续收敛：

- `软件` 页面不是“软件配置统计页”，而应改造成类似 Windows Store / Apple
  App Store 的软件市场。
- 管理员在软件市场里看到应用卡片、分类、搜索、版本、适用系统和安装状态。
- 每个应用可以维护多个 OS-specific 版本。例如“飞书”可以同时存在 Windows
  `.exe/.msi` 版本和 Ubuntu `.deb/apt` 版本。
- 软件市场不应把第三方软件安装包存放在 SynaBoot 服务器上。SynaBoot 只保存
  官方下载地址、安装脚本模板、校验策略和审查状态；被选中的客户端在安装后自行
  从对应官网或官方源下载安装。
- 该限制不是临时实现细节，而是产品原则：SynaBoot 不做第三方软件仓库，不做
  离线安装包缓存，也不把 Windows/HotPE 使用的 SMB 镜像目录复用为普通软件分发
  目录。
- 软件市场的产品定位必须接近 Apple Store / Windows Store 的“应用目录与安装
  编排”：管理员看到可安装应用，SynaBoot 负责按目标 OS 选择正确变体、下发
  安装计划、收集状态；第三方安装包不得上传、缓存或通过本项目 HTTP 静态目录
  分发。
- 软件市场必须像 Apple Store 一样管理“应用条目”和“可信安装来源”，而不是像
  文件服务器一样保存安装包。即使管理员新增大量软件，本地也只保留应用 metadata、
  官方下载/官方包源链接、受审脚本模板、hash/signature 策略和审核记录。
- 软件市场的“可安装软件很多”不等于“本地存很多安装包”。本项目服务器不能保存、
  缓存、镜像或代理第三方软件安装包；被选中的软件必须由装好系统后的客户端
  自己访问对应官网、官方包仓库或管理员批准的企业镜像源下载安装。SynaBoot 只
  下发“去哪下载、用哪个受控安装动作、按什么校验策略确认”的任务计划。
- 硬性约束：FlashPXE/SynaBoot 服务器不能成为第三方软件仓库。创建安装任务时
  可以选择大量软件，但任务里保存的是应用声明和安装计划；真正的安装包必须由
  目标客户端在系统安装完成后从官网、官方包仓库或管理员批准的企业镜像源下载。
- 仅允许保存官方 URL、官方包仓库信息、企业批准镜像源 URL、hash/signature
  策略、静默安装参数和受审查的 runner 分支。若某软件只能通过手工下载或登录态
  下载，必须标记为 `manual_required` 或 `research_required`，不得伪装成可自动
  安装。
- 创建安装任务时，管理员先选择目标系统镜像，系统再自动过滤可选软件，只展示
  与该目标系统兼容的软件版本。
- `assignment-options` 必须由后端按 boot target 返回 `compatible_software_by_target`：
  Windows/HotPE 这类未开放 postinstall 的目标返回空软件集合，Ubuntu 只返回已审核、
  可分配且 runner 支持的 Ubuntu 变体；前端可以再做展示过滤，但不能作为唯一防线。
- 默认软件集合同样必须由后端按 boot target 返回
  `compatible_software_profiles_by_target`，避免 Windows/HotPE 未开放软件安装时仍展示
  Ubuntu 默认集合。
- 创建安装任务选择软件时必须打开软件市场式多选弹窗，支持搜索、分类/系统筛选、
  应用卡片勾选，并持续显示“已选软件”清单。
- 分配任务下发后，客户端先进入对应系统安装引导；系统安装完成后再进入对应 OS
  的软件安装阶段，自动安装管理员选中的软件版本。

## 2026-06-23 Windows 企业式统一装机调研与后续方向

调研结论：

- 企业 Windows 统一装机不是“一个万能 ISO 直接装完”，而是类似 MDT / MECM 的
  任务序列体系：

```text
WinPE/Setup 启动入口
  -> 按设备/集合领取部署任务
  -> 选择系统镜像、驱动、Unattend、软件集合
  -> 安装后 bootstrap
  -> 软件检测、状态回报、失败重试或人工介入
```

- Microsoft Configuration Manager 的 OS task sequence 会引用 boot image、OS
  image、应用、软件更新，并部署到包含目标电脑的 collection。任务序列可包含
  分区格式化、应用 OS image、驱动、更新和应用安装等阶段。
- Configuration Manager / Intune 的应用模型不是“随便执行安装命令”，而是由
  deployment type、检测规则、需求规则、依赖、返回码、安装上下文共同决定是否
  安装、如何判断成功、失败后怎么处理。
- Windows `SetupComplete.cmd` 可作为安装后 bootstrap，以 Local System 权限执行，
  但 Microsoft 文档明确指出 Setup 不验证其退出码，且不应在其中重启。因此它适合
  拉起 SynaBoot runner，不适合作为复杂任务编排核心。
- Windows provisioning package `.ppkg` 适合中小规模配置、应用、证书、策略和账号
  初始化，可作为后续“配置包/脚本包”方向借鉴，但免费版不承诺替代 MDM。

SynaBoot 免费版下一阶段定位：

- 局域网 PXE/HTTP Boot + WinPE 辅助 Windows 安装 + 轻量任务序列 + 软件安装
  profile + 回调证据。
- 不承诺替代 MDT、MECM/SCCM、Intune、Autopilot、Entra ID 或 MDM。
- 不承诺没有客户端/回调脚本也能知道 Windows 内部安装状态。
- 不承诺任意 EXE 都能静默安装或自定义安装目录；每个软件变体必须声明自己的
  安装上下文、静默参数、检测规则、返回码和是否支持自定义目录。

下一轮 Windows 精准统一安装模型：

- `DeviceIdentity`
  - MAC、UUID、serial、asset、manufacturer、product、最近 IP、启动模式、标签。
  - 仅作为识别线索，不作为强认证。
- `DeviceCollection`
  - 静态集合：管理员手动选单台或多台电脑。
  - 动态集合：按 MAC 前缀、UUID、机型、厂商、标签、最近状态匹配。
  - 后续支持 include/exclude 规则，但免费版先做轻量表达式。
- `InstallPreset`
  - 当前阶段只保存目标 OS 镜像和默认软件组合。
  - 不保存清盘、格式化、磁盘设置或 Windows 预分区模板；不同机器硬盘数量、
    容量、启动模式和数据保留需求不同，当前阶段不能把磁盘策略作为统一口径下发。
- `WindowsTaskSequence`
  - 建议阶段：
    - `boot_winpe`
    - `collect_hardware`
    - `select_image`
    - `apply_windows`
    - `inject_drivers`
    - `apply_unattend`
    - `inject_bootstrap`
    - `first_boot`
    - `install_software`
    - `detect_software`
    - `report_result`
- `SoftwareDeploymentType`
  - 安装上下文：`winpe`、`system_first_boot`、`user_logon`。
  - 检测规则：MSI ProductCode、文件存在/版本、注册表键值、受控 PowerShell
    检测脚本。
  - 返回码分类：成功、成功需重启、软失败、硬失败。
  - 依赖关系和需求规则：OS family/version、arch、磁盘空间、前置软件、是否允许
    用户上下文。

安全边界：

- 当前阶段取消 Windows 预分区能力。分区、格式化、清盘不进入安装任务预设、
  客户端分配任务、postinstall plan 或 Windows runner。
- 未来如恢复磁盘策略，必须先具备 WinPE 侧目标磁盘识别证据、dry-run、管理员
  二次确认、审计记录和回滚方案，并重新经过 subagent 审查。
- Windows 软件“自定义安装路径”只能在该软件的 deployment type 明确支持时开放；
  Office ODT、Chrome、飞书等不支持或不稳定的安装路径能力必须显示为系统默认位置。
- 软件安装包仍不托管在 SynaBoot；继续使用官方来源、管理员批准的企业镜像源，
  或管理员审核过的 HTTPS 安装器直链。

2026-06-23 本轮落地结果：

- 经调研后撤回 `PartitionTemplate` 公开能力，只保留 `InstallPreset` 持久化模型。
  - 默认 Windows 预设：`windows-office-standard`，绑定 Windows 启动目标和默认
    Office 2021 ProPlus 软件包。
  - 老实验库中如存在 `partition_template_id` legacy 列，后端只写空值兼容，不再
    暴露 API、前端控件或任务计划字段。
- 已新增 `DeploymentAssignment.task_sequence_plan`，每次分配任务都会保存轻量任务序列：
  `boot_winpe -> collect_hardware -> apply_windows -> inject_bootstrap -> first_boot ->
  install_software -> detect_software -> report_result`。
- 软件变体已补齐企业 deployment type 风格元数据：
  `install_context`、`detection_rules`、`requirements`、`dependencies`、
  `return_codes`、`restart_behavior`、`install_location_policy`。
- 管理后台创建安装任务时，已经可以按目标系统选择安装预设和自动安装软件。
  其中 Windows 软件仍通过安装后的 `SetupComplete.cmd -> runner.ps1` 执行，不在
  WinPE 中直接安装普通业务软件。
- 管理后台新增“安装任务预设”菜单，用于创建、展示、归档和恢复可复用的系统
  + 软件组合。
- Windows 自动化安装深化：
  - Windows runner 允许的动作扩展为 `msi_install`、`exe_install`、
    `office_odt_install`。
  - Windows 不要求软件必须来自正式软件源；管理员可以维护
    `source_policy=admin_reviewed_download` 的 HTTPS 安装器直链。该模式可以不填写
    官方来源页，但仍必须经过审核、声明安装动作、安装器类型、静默参数和校验策略。
  - `exe_install` 必须有审核过的静默参数，否则后端拒绝保存该可执行动作。
  - MSI/EXE 安装均接受受控返回码模型，`3010` 可作为“成功但需要重启”处理。
  - HotPE/WinPE 注入 helper 优先使用管理员指定的 `-WindowsRoot`；未指定时只在
    唯一发现一个离线 Windows 目录时自动注入，找不到或多个候选都会 fail-fast。
  - 飞书 Windows 默认变体已从不可直接自动化的 EXE/下载页，改为飞书官方 MSI
    批量部署包：`feishu-windows-x64` 使用 `msi_install`、`/qn /norestart`、
    `source_policy=admin_reviewed_download`。客户端仍由安装后的 Windows
    `SetupComplete.cmd -> runner.ps1` 从飞书 CDN 直链下载并静默安装，SynaBoot
    不托管该安装包。
- 本轮验证命令：
  - `python3 -m py_compile apps/api/main.py`
  - `bash scripts/preflight/check-software-assignment-flow.sh`
  - `npm run build`（`apps/web`）

参考来源：

- Microsoft Configuration Manager task sequence:
  `https://learn.microsoft.com/en-us/intune/configmgr/osd/deploy-use/create-a-task-sequence-to-install-an-operating-system`
- Microsoft Configuration Manager applications:
  `https://learn.microsoft.com/en-us/intune/configmgr/apps/deploy-use/create-applications`
- Windows Setup custom scripts:
  `https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/add-a-custom-script-to-windows-setup`
- Windows provisioning packages:
  `https://learn.microsoft.com/en-us/windows/configuration/provisioning-packages/provisioning-packages`

`客户端` 页面也需要重新定位：

- 该页面不是单纯展示在线客户端状态，而是“安装任务创建与分配”工作台。
- 管理员可以单选一个客户端，也可以多选一批客户端。
- 单机任务可以给某台机器设置独立系统镜像和软件选择。
- 批量任务可以给一批机器设置相同系统镜像和默认软件集合。
- 后续支持一批客户端中按条件拆分不同任务，例如按 MAC/UUID/型号/标签分配
  不同系统或不同软件组合。

下一轮实现顺序：

1. 先重做 `软件` 页信息架构：应用市场、应用详情、OS 版本、软件包来源、
   hash/manifest、审查状态。
2. 再重做 `客户端` 页信息架构：客户端选择、批量选择、创建安装任务、选择系统、
   打开软件多选弹窗、显示已选软件、确认分配。
3. 接入后端 `SoftwarePackage`、`SoftwareVariant`、`SoftwareProfile` 与
   `DeploymentAssignment` 关系。
4. 最后接入 Windows / Ubuntu 安装后的软件执行器。

2026-06-20 本轮实现收敛：

- 后端先接入 `SoftwarePackage` / `SoftwareVariant` 只读软件市场骨架。
- 默认软件目录只保存官网/官方源入口、安装阶段、来源策略和审查状态；不保存
  第三方安装包。
- 后续新增软件时也必须遵守“客户端从官网/官方源自下载”的边界：不得把飞书、
  Chrome、7-Zip 等第三方安装器放入 `data/images`、`data/boot`、Web 静态目录
  或 Git 仓库；SynaBoot 只保存 metadata、URL、校验和 OS-specific 安装动作。
- `DeploymentAssignment` 支持 `session_ids`，并保存 `resolved_software_plan`，
  使历史任务不依赖未来可变的软件目录。
- 任务提交时后端强制校验软件变体是否存在、是否与目标系统兼容、是否允许来源
  策略、是否通过审核、是否满足 hash/signature 策略。
- 未审核或缺校验策略的软件可以在市场展示，但不能进入自动安装任务。
- Web UI 从后端读取软件市场，创建任务的软件弹窗显示已选软件、兼容版本、
  官方来源、审查状态和不可选原因。
- 后端 `assignment-options` 已补齐目标级兼容软件 map，创建任务弹窗会优先读取
  当前目标的后端兼容目录，避免 Windows/HotPE 未开放软件安装时仍展示可选软件。
- 后端也已补齐目标级兼容软件集合 map，创建任务中的默认软件集合与单独软件选择
  使用同一 target 能力边界。
- 创建安装任务的软件选择已从“前端提交具体软件变体”推进为“管理员选择应用，
  后端按目标系统解析变体”：`DeploymentAssignment` 新增 `software_package_ids`，
  `resolved_software_plan` 会记录选中的应用并解析到对应 OS 的已审核变体。这样
  管理员选择“Chrome/飞书”等应用时，不需要理解 `.msi`、`.deb`、APT 变体细节。
- 同一应用同一系统存在多个可安装版本时，后端不再依赖偶然排序。`SoftwareVariant`
  新增 `default_for_os` 和 `selection_priority`；应用级选择优先解析默认版本，
  再按优先级选择。将某个变体设为默认时，同一应用同一 OS 下其它默认标记会被
  自动取消。
  - Ubuntu `apt_package` 已按官方源安装语义修正：管理员只需要维护官方来源页、
  包名、`official_package_repo` 和 `repo_signed` 策略，`download_url` 可以为空；
  但当前 runner 只支持 Ubuntu 默认 apt 源中可直接安装的包，不支持自动新增外部
  apt repo/keyring。需要 Google Chrome 这类外部源的软件必须先走 `download_deb`
  或等待后续实现受审的 apt repo 配置动作；只有 `download_deb`、`msi_install`
  这类需要独立安装器的动作才要求安装器下载 URL。
- 客户端页已从“观察列表”推进为“客户端安装任务”工作台：
  - 支持单台客户端创建安装任务。
  - 支持多选/选择在线客户端后创建批量安装任务。
  - 批量任务提交 `session_ids` 数组，目标系统和软件选择共用同一
    `DeploymentAssignment`。
  - 软件选择弹窗右侧持续显示已选软件，并明确说明客户端安装系统后从官方来源
    下载并执行。
- 后端批量 `DeploymentAssignment` 创建已修复一致性边界：先校验所有
  `session_ids` 存在，再在同一个 SQLite 事务里更新客户端 session 并写入
  assignment；任一 session 缺失或写入异常时不污染已有等待客户端状态。
- 软件市场的长期定位必须保持为 Apple Store / Windows Store 式“应用目录与
  安装编排器”，不是第三方软件包仓库。SynaBoot 只保存官方下载链接、官方软件源、
  安装模板、hash/signature 策略和审查状态；不得把第三方 `.exe`、`.msi`、`.deb`
  等安装包放入 `data/images`、`data/boot`、Web 静态目录、SMB 目录或 Git。
  被选中的软件应在目标 OS 安装后由客户端自行从官方来源或批准企业镜像源下载。
- 软件市场已新增最小管理员维护闭环：管理员可在软件市场页面对软件变体执行
  “批准自动安装 / 退回审核 / 启用 / 禁用”。后端只允许更新审核状态、启用状态、
  来源策略、官方 URL、hash/signature 策略和 notes，不接受上传安装包，不接受
  任意 shell 命令，也不允许把 SynaBoot 自己的 `/images`、`/boot` 或内网地址
  伪装成第三方软件下载源。
- 软件变体的 `assignable` 现在不仅检查审核和来源，也检查 OS runner 是否真的
  支持对应 `install_action`、`install_phase` 和安装器类型。官方页面下载但 runner
  尚不支持自动化的变体可以展示和批准审查状态，但不会进入自动安装任务。
- 软件变体表已补充 `package_name` 字段，用于 Ubuntu 官方 apt 仓库安装动作。
  默认软件市场新增 `curl-ubuntu-apt`：通过 Ubuntu 官方仓库和 repo 签名安装
  `curl`，默认 approved，可作为实验隔离环境中验证“被动 Ubuntu 安装任务 +
  自动安装软件”的安全样例；该样例不在 SynaBoot 服务器保存任何第三方安装包。
- 软件 profile 已进入第一阶段真实任务链路：新增默认 `Ubuntu 基础工具` 集合，
  指向已审核的 `curl-ubuntu-apt`。创建安装任务时，前端可选择兼容 profile，
  后端会展开为具体软件变体并写入 `resolved_software_plan`，不再静默忽略
  `software_profile_ids`。
- 软件市场已新增应用目录维护入口：管理员可新增应用 metadata，并为应用新增
  Windows / Ubuntu 系统版本 metadata。新增版本默认 `needs_review`，必须经过
  来源、签名/hash、runner 支持和人工审核后才可能进入自动安装任务；该流程不上传
  第三方安装包，不接受任意 shell 命令，也不把 SynaBoot 静态目录作为下载源。
- 软件市场新增“软件集合”维护入口：管理员可以把多个已审核、可分配、同一目标
  OS 的软件版本组合成默认集合，用于创建安装任务时快速选择。集合本身只保存
  `variant_ids` 等 metadata，不保存 URL、脚本命令或第三方安装包；未审核或
  不可执行的软件版本不能被加入集合。
- 软件市场已新增应用和软件集合的归档/恢复能力。归档不是硬删除，不破坏历史
  `DeploymentAssignment` 的 `resolved_software_plan`；但被归档的应用不会进入
  应用级软件选择，被归档的软件集合不会进入创建安装任务的默认集合。
- 软件市场已补齐受控执行元数据维护：管理员可以把某个软件版本从“仅记录官方
  下载页”维护为 runner 已支持的 `apt_package`、`download_deb` 或 `msi_install`
  动作，并维护安装器类型、包名、官方下载 URL、静默参数和审核状态；后端会继续
  拒绝本机/内网/SynaBoot 静态目录来源、任意命令和未受支持的 runner 动作。
- 软件市场的长期体验应对齐 Apple Store / Windows Store：本地维护应用目录、
  官方来源和安装编排，客户端安装系统后直接从软件官网、官方包仓库或批准企业
  镜像源下载。SynaBoot 项目服务器不得变成第三方软件二进制仓库、缓存代理或
  “先下载再转发”的中间层。
- 后续开发软件市场时，默认假设“可分配软件很多，但本地只保存链接和脚本策略”：
  管理后台维护的是应用条目、官方下载/官方源、企业批准镜像源、校验策略、默认
  版本和安装动作；目标客户端在安装完成后自行访问对应官网或官方源下载安装。
  不得新增服务端下载缓存任务、安装包上传入口或把 SynaBoot HTTP/SMB 目录当作
  普通软件分发源。
- 后台任务可见性已补齐：`/api/deployment-assignments` 会返回每个任务最近的
  postinstall events 和 `event_summary`，客户端安装任务页会展示最近安装任务、
  已选软件和 runner 最新状态。这样管理员能看到软件安装 runner 是否已开始、
  完成、失败或被阻断。
- postinstall 生命周期已明确分层：`runner started/failed/completed` 表示本次
  安装后软件执行器整体状态，只有 runner 级事件可以推进
  `DeploymentAssignment.status`；`variant started/failed/completed` 只表示单个
  软件变体的明细进度，不能把整次装机任务提前标记为完成或失败。
- 事件读取已按 `created_at DESC, rowid DESC` 排序，避免 runner 和 variant 在同一
  秒连续回调时后台最近状态不稳定。
- 预检已覆盖 `variant completed` 不会把 assignment 误标为
  `postinstall_completed`，`variant failed` 不会把 assignment 误标为
  `postinstall_failed`；只有 `runner completed/failed` 才能推进全局生命周期。
- 创建安装任务提交语义已收敛为“提交管理员实际勾选的应用/集合 ID，后端最终
  解析和校验”。前端不再把当前可见 catalog 派生结果当作唯一提交来源，避免
  catalog 刷新或目标切换造成用户已选软件被静默漏提交；后端仍负责按目标系统
  解析默认/高优先级变体，并执行 OS 兼容、审核、assignable、官方来源和
  Windows fail-closed 校验。
- 软件选择支持“单独应用 + 默认软件集合”组合提交。同一任务中如果应用选择和
  软件集合引用到同一个变体，后端会在 `resolved_software_plan.variants` 中
  去重，同时保留 `package_ids`、`profile_ids` 和 `packages[].selected_variant_id`
  作为审计记录，避免重复安装又能追踪管理员实际选择。
- 已补齐真实 HTTP API 级回归验证：预检会通过 `/api/assignment-options` 获取
  目标系统兼容软件，通过 `/api/deployment-assignments` 提交带应用和软件集合的
  安装任务，并通过 `/api/deployment-assignments/<id>` 回读持久化结果；无管理员
  token 的创建请求必须返回 403，合法请求需遵守后端写限流后成功创建。
- HTTP 创建的安装任务已继续接入被动等待室验证：预检会让同一客户端 session
  访问 `/api/ipxe/wait`，确认返回的 iPXE 脚本领取的是同一个
  `DeploymentAssignment`，并包含 Ubuntu NoCloud seed、postinstall plan URL 和
  runner URL；领取后客户端 session 状态必须推进为 `booting`。这条链路用于保证
  管理后台按钮创建的任务能被被动模式客户端实际接走，而不是只停留在数据库里。
- 管理后台最近安装任务卡已细化到软件变体级：每个被选软件会显示等待回调、
  执行中、已完成、失败、已阻断等状态，并展示最近 runner/variant 回调，避免
  管理员只能看到 assignment 全局状态而不知道具体软件卡在哪一步。
- 批量任务 token 模型已修复：新增 `assignment_boot_tokens`，按
  `assignment_id + session_id` 保存 boot token。旧的 assignment 级单 token
  会导致同一批多台客户端互相覆盖 token，也会被单台 `postinstall_completed`
  状态阻断；现在每台客户端独立校验，适合批量被动安装任务。
- 批量任务状态展示必须区分“任务整体事件”和“单台客户端会话事件”。客户端列表
  上的 `latest_assignment.event_summary` 只统计当前 `session_id` 的
  postinstall events，避免一台机器已完成导致同批其它等待机器误显示完成。
- Windows / Ubuntu 的真实 postinstall runner 已进入第一阶段落地：
  - `DeploymentAssignment` 持久化 `resolved_software_plan`，runner 只消费该计划。
  - `plan`、`runner.sh`、`runner.ps1`、`events` 均使用客户端 session token 校验。
  - postinstall plan 的 `execution_model.allowed_install_actions` 按目标 OS 暴露
    真实 runner 能力：Ubuntu 只声明 `apt_package` / `download_deb`，Windows 只
    声明 `msi_install` / `exe_install` / `office_odt_install`；`official_download`
    仍只是未自动化的 metadata 语义，不会被声明为可执行动作。
  - Ubuntu runner 仅允许 `linux_first_boot` 的 `apt_package` / `download_deb`。
  - `apt_package` 仅代表目标系统已有 Ubuntu 默认 apt 源中的包；外部 apt 源安装
    当前不会自动添加 repo/keyring，必须保持不可分配，避免后台显示“可安装”但
    真实客户端安装失败。
  - Windows runner 仅允许 `windows_first_boot` 的 `msi_install` /
    `exe_install` / `office_odt_install`。
  - Windows EXE 自动安装必须配置经过审核的静默参数；未配置静默参数时后端直接拒绝
    保存 `exe_install` 动作，避免首次启动卡在安装器交互界面。
  - runner 不执行前端传入命令、不执行 `install_command_template`、不从 SynaBoot
    下载第三方软件包。
  - Ubuntu runner 已补齐状态回传：整体 runner 会上报 started/failed/completed，
    每个软件变体会上报 started/completed/failed，后台可按单台客户端 session
    观察具体软件是否安装成功。
  - Ubuntu NoCloud first-boot bootstrap 已补强真实客户端可靠性：首次启动时下载
    token 保护的 `runner.sh` 会做有限重试，systemd 服务失败后会按有界策略重试；
    runner 成功执行后会删除本地 `runner.sh` 并禁用服务，减少 token-bearing 脚本
    在目标系统上的长期残留。
  - 自动软件安装的下载来源必须是 HTTPS 官网、官方源或已批准企业镜像；本机、
    内网、`/images`、`/boot` 等来源不得作为第三方软件下载源。
  - Windows 当前通过 HotPE/WinPE 显式注入 `SetupComplete.cmd` 承载首次启动
    runner。管理员给 Windows 分配软件后，仍需在 HotPE/WinPE 中确认目标
    Windows 根目录并执行注入 helper；真正的软件安装发生在已安装 Windows
    首次启动阶段。
  - 2026-06-20 已新增 Windows HotPE/WinPE 注入准备件：
    `windows-hotpe-inject.ps1`。该脚本优先使用管理员明确传入的目标 Windows
    根目录；未传入时只在唯一发现一个离线 Windows 目录时自动注入。找不到或发现多个
    候选目录都会 fail-fast；脚本不清盘、不格式化、不托管第三方软件安装包。
  - 2026-06-21 已开放 Windows 带软件任务的受控链路：
    - `msi_install`：客户端下载官方/批准企业镜像 MSI，按受控静默参数安装，
      校验失败或安装失败会上报 variant failed，并删除临时 MSI。
    - `exe_install`：客户端下载官方/批准企业镜像 EXE，必须使用审核过的静默参数，
      校验失败、无静默参数或安装返回码不符合策略都会 fail-fast。
    - `office_odt_install`：客户端下载 Microsoft Office Deployment Tool，
      用受控 Office 产品 ID 生成固定 `configuration.xml` 后执行 `/configure`。
      Office 安装包不存放在 SynaBoot 服务器。
    - Windows/Office 激活只支持管理员配置的自有 KMS：
      `SYNABOOT_KMS_HOST`、`SYNABOOT_KMS_PORT`、
      `SYNABOOT_WINDOWS_KMS_ACTIVATE`、`SYNABOOT_OFFICE_KMS_ACTIVATE`。
      默认关闭，不内置公共 KMS、不保存产品密钥、不提供绕过授权能力。
  - 2026-06-23 已将 Windows 默认办公套件收敛为 Office 2021 ProPlus：
    - Windows 安装任务默认追加 `microsoft-office`，解析为 `office-windows-odt`。
    - Office ODT 产品 ID 为 `ProPlus2021Volume`，通过 Microsoft 官方 ODT 链接由
      客户端下载执行，SynaBoot 不托管 Office 安装包。
    - 既有 SQLite 种子通过幂等迁移修正，避免旧运行环境继续显示 Windows 无法选择
      自动安装软件。
  - 2026-06-23 已明确 Ubuntu 飞书自动安装边界：
    - 飞书下载页不是 `.deb` 直链，不能作为 `download_deb` 自动安装源。
    - 管理员必须提供并审核 `SYNABOOT_FEISHU_UBUNTU_DEB_URL` 官方 Linux amd64 deb
      直链后，飞书才进入 Ubuntu 可分配软件集合。
    - 未配置该变量时，飞书只作为待维护软件来源显示，不会误导后台创建不可执行任务。
  - 当前阶段已验证 API 与脚本生成安全边界、批量 assignment 创建、缺失 session
    rollback、`/api/ipxe/wait` 被动等待室轮询返回 Ubuntu NoCloud 启动脚本、
    Windows SetupComplete helper/runner 生成、Office ODT/KMS 受控配置、
    Ubuntu NoCloud/postinstall 注入烟测，以及 first-boot runner 下载失败时的
    有界重试模板；真实客户端端到端安装仍需下一阶段继续在实验隔离环境验证。

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

## 22. 当前实施进度与后续开发队列

更新时间：`2026-06-17`

### 22.1 已完成并验证的事实

当前已经从实验环境得到可复用结论：

- Windows 11 安装已经通过 FlashPXE 进入安装流程；正式路径为 `wimboot`
  启动 Windows 安装环境，进入 PE/安装器后再使用 SMB 访问 Windows 镜像目录。
- HotPE V2.8 已经通过 FlashPXE 启动；SMB 继续作为 Windows/HotPE 的镜像和
  模块组件共享，不得因为 Ubuntu 调整而停用。
- Ubuntu 22.04.3 Desktop 和 Ubuntu 24.04 Desktop 已经通过 FlashPXE 进入安装
  引导；正式路径为 HTTP 加载 `casper/vmlinuz`、`casper/initrd`，NFS 提供
  casper livefs。
- Ubuntu Desktop 不再使用 SMB/CIFS 作为 livefs 来源，不再使用 HTTP ISO RAM
  fallback 作为正式方案。
- 正式 FlashPXE 菜单只保留四个镜像入口：Windows 11、HotPE、Ubuntu 22.04.3、
  Ubuntu 24.04；Diagnostics 和 HTTP RAM fallback 只保留在排错记录中。
- 详细问题复盘和真实环境避坑清单见 `docs/BOOT_INSTALL_ISSUES_SUMMARY.md`。

### 22.2 已移出当前主计划的旧方向

以下内容不再作为当前 `PLAN.md` 的实施依据：

- 把派生启动文件作为管理员后台主列表。管理员默认只应看到上传的 ISO，
  `vmlinuz`、`initrd`、`*.squashfs`、BCD、boot.wim 等派生物只能进入详情页或
  调试视图。
- 把 HTTP RAM fallback 做成正式菜单项。该路径已经验证会在低内存客户端出现
  `No space left on device`，只允许临时排错。
- 把 Diagnostics 入口放在正式菜单中。诊断入口只保留在文档、脚本或人工排错
  流程中。
- 继续累积 Phase 3 只读骨架、意图包、声明门禁等历史流水作为当前待办。Phase 3
  自动网络启动仍保留安全门禁，但不是下一阶段后台体验主线。
- 把 iVentoy 对标直接理解成“任意 ISO 都能通用启动”。SynaBoot 要借鉴的是
  “管理员只管理 ISO、平台识别和适配”的体验；真实启动仍必须按 OS 类型使用
  对应策略。

### 22.3 当前主线

下一阶段主线切换为：

```text
管理员只上传/放置 ISO
  → SynaBoot 扫描源 ISO
  → 自动识别 OS family/version/arch
  → 选择对应 Boot Strategy
  → 准备或校验派生启动工件
  → FlashPXE 菜单只展示可真实启动的系统镜像
  → 后台展示正在 PXE/安装的客户端
  → 管理员按单机或批量分配软件安装配置
```

### 22.4 后续开发队列

1. ISO-first 管理后台
   - 镜像仓库默认按“源 ISO”展示。
   - 每行显示镜像名、识别结果、启动策略、准备状态、菜单状态和最后扫描时间。
   - 派生文件折叠在详情页的“启动工件/调试信息”中。

2. OS 自动识别与 Boot Strategy Registry
   - Windows ISO：走 HotPE/Windows 安装辅助路径。
   - HotPE ISO：准备并使用 `wimboot` 启动链路。
   - Ubuntu Desktop ISO：HTTP kernel/initrd + NFS casper livefs。
   - Proxmox VE/PVE ISO：先由 `research_agent` 调查官方启动方式，再新增策略；
     在证据不足前标记为 `research_required`，不得伪装为 ready。
   - Unknown ISO：只展示为源文件，不生成菜单项。

3. 客户端安装会话追踪
   - 记录菜单加载、镜像选择、启动开始、安装器回调或超时状态。
   - 最小识别字段为 MAC、IP、固件架构、选择镜像、当前阶段、最后心跳。
   - Phase 2 只能通过 HTTP/iPXE 回调和安装器侧回调收集，不引入 DHCP 接管。

4. 软件安装配置与批量分配
   - 建立 `SoftwareProfile` 与 `DeploymentAssignment` 模型。
   - Windows 优先通过 HotPE/安装后脚本或 Windows 安装流程接入。
   - Ubuntu 优先通过 autoinstall/cloud-init/late-commands 或安装后 agent 接入。
   - 所有会执行脚本的能力必须经过 `security_audit_agent` 审查；默认不得清盘、
     不得静默执行危险命令。

5. Phase 3 自动 PXE 入口
   - 仍保持默认关闭和安全门禁。
   - 在生产 LAN 启用前必须单独经过 `research_agent`、`network_safety_agent`、
     `security_audit_agent`、`project_decision_agent` 审批。
   - 不得改变 TP-Link `192.168.1.1` 的 DHCP lease 职责，不得改变 OpenWrt
     `192.168.1.4` 默认网关。

### 22.5 本轮文档任务验收标准

本轮只做方向校准与规划落地，验收标准为：

- `PLAN.md` 不再把旧实验流水当成当前待办。
- `docs/SUBAGENT_SESSION_POOL.md` 明确固定岗位、旧会话多次确认、禁止岗位串位。
- `.codex/agents/*.toml` 中对应岗位职责反映 ISO-first、OS 策略识别、客户端会话、
  软件分配这条新主线。
- 新增设计文档说明后台目标体验、数据模型、阶段拆分和 subagent 分工。

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

## 24. 下一阶段主线：ISO-first 管理后台与客户端部署编排

更新时间：`2026-06-17`

### 24.1 设计依据

SynaBoot 借鉴 iVentoy 的管理员体验：管理员把 ISO 放入指定目录，Web 管理端以
ISO 为核心对象展示，底层启动细节由平台处理。但 SynaBoot 不假设任意 ISO 都能用
同一种网络启动方式；每个 OS family 必须由明确的 Boot Strategy 适配。

当前已经验证的策略：

- Windows：FlashPXE 进入 Windows 安装环境，后续通过 HotPE/SMB 获取安装介质。
- HotPE：`wimboot` 启动链路。
- Ubuntu Desktop：HTTP kernel/initrd + NFS casper livefs。

未来新增 PVE、Debian、Rocky、ESXi、工具盘等 ISO 时，必须先识别类型，再进入
对应策略；没有策略就只显示 ISO，不生成启动菜单项。

### 24.2 管理后台目标体验

后台“镜像仓库”默认只展示管理员上传或放入的 ISO：

```text
ISO 名称 | 系统识别 | 版本/架构 | 启动策略 | 准备状态 | 菜单状态 | 操作
```

默认不展示：

- `initrd`
- `vmlinuz`
- `*.squashfs`
- `.disk/*`
- `BCD`
- `boot.sdi`
- `boot.wim`
- `wimboot`

这些派生文件只在 ISO 详情页的“启动工件”折叠区展示，用于排错和审计。

### 24.3 数据模型草案

核心对象：

- `SourceImage`：管理员上传/放入的原始 ISO。
- `ImageDetection`：识别出的 OS family、发行版、版本、架构、置信度。
- `BootStrategy`：针对某类 ISO 的启动策略，例如 `windows_hotpe_assisted`、
  `hotpe_wimboot`、`ubuntu_desktop_nfs_livefs`。
- `DerivedBootArtifact`：从 ISO 提取或准备出的启动工件。
- `BootMenuEntry`：最终进入 FlashPXE 菜单的可启动条目。
- `ClientInstallSession`：正在通过 FlashPXE/PXE 安装或启动的客户端会话。
- `SoftwareProfile`：安装后软件、脚本、配置包的声明式配置。
- `DeploymentAssignment`：单台或批量客户端与镜像、软件配置之间的分配关系。

### 24.4 Boot Strategy 初始矩阵

- Windows ISO
  - 识别依据：ISO 内存在 Windows 安装介质结构，例如 `sources/install.wim` 或
    `sources/install.esd`。
  - 启动策略：`windows_hotpe_assisted`。
  - 菜单策略：显示 Windows 镜像名，但说明需要 HotPE/Windows 安装环境访问介质。

- HotPE ISO
  - 识别依据：PE/Windows boot media 结构和 HotPE 命名特征。
  - 启动策略：`hotpe_wimboot`。
  - 菜单策略：准备完成后直接显示 HotPE 镜像名。

- Ubuntu Desktop ISO
  - 识别依据：`casper/vmlinuz`、`casper/initrd`、`.disk/info`、casper livefs。
  - 启动策略：`ubuntu_desktop_nfs_livefs`。
  - 菜单策略：准备完成后显示 Ubuntu 镜像名；不显示 NFS/HTTP 后缀。

- Proxmox VE/PVE ISO
  - 初始状态：`research_required`。
  - 处理规则：先由 `research_agent` 收集官方/项目文档，确认 kernel/initrd、rootfs、
    squashfs、ISO loop 或 HTTP/NFS 支持方式，再由 `boot_entry_agent` 和
    `image_factory_agent` 设计策略。
  - 菜单策略：证据不足前不得生成可启动条目。

- Unknown ISO
  - 初始状态：`unsupported_source_only`。
  - 菜单策略：不生成启动条目，只展示识别失败原因和需要新增策略。

### 24.5 客户端安装会话追踪

目标是在后台看到“哪些机器正在通过 FlashPXE 安装系统”。第一版不依赖 DHCP 接管，
只使用零侵入信号：

- iPXE 菜单加载时调用 HTTP 记录端点。
- 用户选择镜像时记录 `selected_image_id`。
- 启动脚本在进入安装器前记录 `booting`。
- 支持 OS 安装器或 postinstall 脚本回调 `installer_started`、`postinstall_started`、
  `completed`、`failed`。
- 客户端长期身份优先使用 MAC；没有 MAC 时使用 IP、固件架构、时间窗口和一次性
  session id 组合。

该能力不得要求 SynaBoot 分配 IP，不得监听 DHCP 端口，不得改变网关/DNS。

### 24.6 软件安装与批量分配

软件安装能力分阶段实现：

1. 第一阶段只建模和展示
   - 创建 `SoftwareProfile`。
   - 创建 `DeploymentAssignment`。
   - 绑定到单台客户端、客户端标签或批量选择。
   - 不自动执行危险脚本。

2. 第二阶段接入 OS 特定执行点
   - Windows：HotPE 辅助脚本、Windows Setup 后置脚本或企业软件安装器。
   - Ubuntu：autoinstall/cloud-init/late-commands 或安装后 agent。
   - PVE：待研究确认后再决定，不凭经验硬接。

3. 安全门禁
   - 所有脚本、包、文件注入必须有 manifest、hash、大小限制和路径边界。
   - 涉及清盘、分区、格式化、加域、改网络、执行任意命令时必须高危提示和审查。
   - 不记录密码、token、私钥；不得把客户软件包或内部脚本提交到 Git。

### 24.7 Subagents 职责调整

- `architecture_agent`：定义 SourceImage、BootStrategy、ClientInstallSession、
  SoftwareProfile、DeploymentAssignment 的模型边界。
- `storage_agent`：只把源 ISO 作为管理员主清单；负责扫描、hash、识别证据和派生
  工件边界。
- `image_factory_agent`：负责 OS-specific 准备任务和软件配置任务包，不破坏原 ISO。
- `boot_entry_agent`：负责把 ready 的 BootStrategy 变成 FlashPXE 菜单和客户端
  事件回调。
- `webui_agent`：负责 iVentoy-like ISO 清单、镜像详情、客户端会话、软件分配体验。
- `research_agent`：负责 PVE 等未知 ISO 的官方启动方式调查。
- `network_safety_agent`：审查客户端会话追踪、PXE/ProxyDHCP/TFTP、端口暴露和
  生产 LAN 风险。
- `security_audit_agent`：审查 ISO 解析、脚本执行、软件包注入、路径和密钥安全。
- `tutorial_docs_agent`：把管理员使用路径、真实环境避坑、策略矩阵和回滚方式写成
  文档。
- `project_decision_agent`：决定策略优先级、免费/商业边界和是否进入 Phase 3。
- `git_audit_agent`：确保 ISO、软件包、日志、SQLite、客户脚本和敏感信息不进入 Git。

### 24.8 下一步实施顺序

1. 设计并实现 ISO-first `/api/images` 返回结构与后台列表。
2. 加入 Boot Strategy Registry，不再让 UI 直接消费派生文件作为镜像主对象。
3. 为当前四个已验证镜像补齐策略映射和菜单显示名规则。
4. 新增 PVE/未知 ISO 的 `research_required` 状态，不生成菜单。
5. 新增客户端安装会话只读模型和 iPXE HTTP 回调规划。
6. 新增软件配置与分配模型草案，暂不执行危险脚本。
7. 在真实环境部署前重新运行网络安全、发布范围和 Git 审计。

### 24.9 2026-06-18 实施记录：ISO-first API/UI 第一阶段

已完成第一阶段实现：

- `/api/images` 保留旧 `images` 全量扫描数组，用于兼容现有 smoke test 和菜单聚合。
- `/api/images` 新增 `source_images`、`artifacts`、`derived_artifacts`、`summary`。
- 每条镜像新增 ISO-first 视图字段：
  - `object_type`
  - `inventory_role`
  - `visibility`
  - `artifact_role`
  - `parent_relative_path`
  - `os_family`
  - `os_distribution`
  - `detection_status`
  - `detection_strategy`
  - `detection_evidence`
  - `strategy_key`
  - `strategy_display_name`
  - `strategy_status`
- 管理后台镜像页默认消费 `source_images`，不再把 `vmlinuz`、`initrd`、
  `*.squashfs`、`BCD`、`boot.sdi`、`boot.wim`、`wimboot` 等派生工件作为主列表项。
- 镜像详情页展示启动策略、识别依据、缺失工件和“启动工件 / 调试信息”折叠区。
- PVE/Proxmox VE ISO 初始识别为 `research_required`，不会生成 ready 菜单。

验证记录：

```bash
python3 -m py_compile apps/api/main.py apps/worker/scan_images.py
npm --prefix apps/web run build
bash scripts/preflight/check-subagent-governance.sh
bash scripts/preflight/check-compose-config-safe.sh
bash scripts/preflight/check-release-scope.sh
bash scripts/preflight/check-public-runtime-boundary.sh
git diff --check
```

补充说明：

- 已用临时 `SYNABOOT_DATA_DIR` 做隔离扫描验证，不使用真实 ISO，不改当前运行数据：
  4 个源镜像进入 `source_images`，9 个派生工件进入 `artifacts`，PVE 为
  `research_required`。
- `bash scripts/preflight/check-network-safety.sh` 当前被既有实验隔离环境监听阻塞：
  `ens19` 上存在 UDP `67/4011`，`10.101.8.135` 上存在 UDP `69`。本轮代码未新增
  DHCP、ProxyDHCP、TFTP、路由、网关、防火墙或 Docker 网络变更；该阻塞记录为
  现有实验服务状态，后续真实环境验证前必须清理或隔离确认。

---
