# 软件市场与管理员按钮事件规划

> 日期：2026-06-19
>
> 目标：把“软件”菜单从占位页升级为类似软件市场的装机软件库，并把客户端
> 分配、管理员 token、上传 ISO、刷新等按钮全部改造成有明确后端语义、错误反馈
> 和审计边界的真实操作。

## 1. 使用者视角目标

管理员希望完成的是一条完整装机链路，而不是管理底层启动文件：

```text
上传 ISO
  -> 系统自动识别并准备启动环境
  -> 客户端进入被动安装等待室
  -> 管理员给客户端选择系统镜像
  -> 管理员选择该系统可用的软件包
  -> 客户端自动进入对应系统安装
  -> 系统安装后自动安装对应软件
  -> 后台看到执行状态和结果
```

例如“飞书”不是一个单独的安装命令，而是一个软件包族：

- Windows 目标系统使用 Windows 安装器，例如 `.exe` 或 `.msi`。
- Ubuntu 目标系统使用 Linux 安装器，例如 `.deb`、APT 源或受控脚本。
- 管理员选择 Windows 镜像时，只显示 Windows 兼容版本。
- 管理员选择 Ubuntu 镜像时，只显示 Ubuntu 兼容版本。

## 1.1 软件页产品定位

`软件` 页面应改造成类似 Windows Store / Apple App Store 的软件市场，而不是
当前的“软件配置”占位统计页。

管理员默认看到：

- 应用市场首页：搜索框、分类、推荐/常用、最近更新、适用系统筛选。
- 应用卡片：应用名、厂商、图标、分类、支持系统、默认安装状态。
- 应用详情：说明、版本列表、Windows 版本、Ubuntu 版本、安装方式、hash、
  manifest、审查状态。
- 选择状态：在创建安装任务时，可以把某些应用加入“本次任务的软件清单”。

关键原则：

- 一个应用是管理员视角的主对象，例如“飞书”。
- 软件变体是执行层对象，例如“飞书 Windows x64 MSI”和“飞书 Ubuntu amd64 deb”。
- 任务创建时只让管理员选应用；系统根据目标 OS 自动落到正确变体。
- 当目标 OS 没有兼容变体时，该应用必须显示为不可选并说明原因。
- 软件市场不托管第三方软件安装包。SynaBoot 是“应用目录与安装编排器”，不是
  “第三方软件仓库”。
- SynaBoot 只保存官方下载安装来源、官方包仓库信息、管理员批准企业镜像源 URL、
  OS-specific 安装动作、静默参数、校验规则和审查状态。
- SynaBoot 不缓存、不镜像、不代理第三方软件安装包；即使安装包来源是官网，也
  只能保存可审计 URL、包名、仓库配置或安装模板，不能把二进制文件落到项目
  服务器上再分发。
- 软件市场按 Apple Store 式目录设计：本地保存应用 metadata、可信来源链接、
  OS-specific 安装模板、校验策略和审核状态；客户端下载动作发生在目标系统内，
  直接访问官网、官方包源或批准企业镜像源。
- 即使未来软件市场收录大量软件，也不能让 SynaBoot 服务器代替客户端去下载、
  缓存、镜像或转发这些软件。SynaBoot 只负责告诉目标系统“去哪里、用什么受控
  动作、按什么校验策略安装”，真正的软件下载必须发生在目标客户端安装后的系统
  环境中。
- 软件市场允许维护很多可选应用，但每个应用在本地只保存目录信息、官方来源 URL、
  官方包仓库说明、受审安装动作和校验策略。管理员给客户端勾选软件后，目标系统
  完成安装并进入 postinstall 阶段时，必须由客户端直接访问官网、官方仓库或批准
  企业镜像源下载安装；SynaBoot 服务端不得保存、缓存、镜像或代理第三方安装包。
- 软件市场的本地持久化对象只能是“指向外部可信来源的链接、官方包源声明、受审
  runner 分支、安装参数白名单、hash/signature/manifest 策略和审核记录”。即使
  某个软件很常用，也不得把安装包下载到 SynaBoot 项目服务器、容器卷、SMB 目录
  或 Web 静态目录中再分发。
- 客户端完成系统安装后，由目标系统自己访问软件官网、官方包仓库或管理员批准的
  官方镜像源下载安装。FlashPXE/SynaBoot HTTP 静态目录不得作为第三方软件
  安装器下载源。
- 若软件官方不提供可自动化下载入口、需要登录态下载、或校验策略无法建立，软件
  只能展示为 `manual_required` / `research_required`，不得进入自动安装任务。

明确禁止：

- 不把第三方 `.exe`、`.msi`、`.deb`、`.pkg`、压缩包或离线安装器上传到
  SynaBoot 服务器作为软件市场内容。
- 不把第三方软件安装器放入 `data/images`、`data/boot`、Web 静态目录或 Git
  仓库。
- 不通过 `/images`、`/boot`、`/api/package` 等本项目 URL 向客户端分发第三方
  软件安装包。
- 不把本地 SMB/HTTP 镜像目录复用为第三方软件下载仓库；SMB 仅保留 Windows /
  HotPE 既有镜像和组件挂载用途。
- 不实现“先由 SynaBoot 服务端下载官方安装包，再由客户端从 SynaBoot 下载”的
  缓存代理流程，除非后续有单独的企业镜像源设计、审计和明确启用开关。
- 不把“软件市场”实现成离线安装包库、缓存服务或下载中转站；它必须保持为
  Apple Store / Windows Store 式的应用目录和安装编排入口。

允许保存：

- 软件名称、厂商、分类、说明、图标 key、官网 URL。
- 官方下载 URL、官方包仓库配置说明、管理员批准的企业镜像源 URL。
- OS/架构/版本约束、安装阶段、安装动作类型、静默参数、期望退出码。
- hash、签名策略、manifest 摘要、风险等级、审核状态。
- 自动安装 runner 所需的受控分支配置，但不得保存任意命令模板作为直接执行内容。

## 1.2 客户端页产品定位

`客户端` 页面应改造成“安装任务创建与分配”工作台，而不是普通在线状态列表。

管理员默认操作路径：

```text
进入客户端页
  -> 查看正在等待任务的客户端
  -> 单选一台或多选一批客户端
  -> 点击创建安装任务
  -> 选择目标系统镜像
  -> 打开软件市场式多选弹窗
  -> 软件弹窗按目标系统过滤可安装应用
  -> 勾选默认软件或额外软件
  -> 界面持续显示已选软件清单
  -> 确认后生成 DeploymentAssignment
  -> 被选客户端自动从等待室进入对应系统引导
```

客户端页需要支持两类任务：

- 单机任务：给某一台机器设置独立系统镜像、独立软件清单和后续覆盖策略。
- 批量任务：给多台机器设置相同系统镜像和相同默认软件集合。

后续可以扩展：

- 按 MAC、UUID、厂商、型号、资产标签、客户端标签批量选择。
- 对同一批客户端分组下发不同系统或不同软件组合。
- 展示每台客户端的任务状态、最后心跳、安装阶段和失败原因。

## 2. 软件市场数据模型

2026-06-20 实现状态：

- 已新增后端只读软件市场骨架：`SoftwarePackage` 和 `SoftwareVariant`。
- 已新增 `/api/software-packages`、`/api/software-packages/<id>`、
  `/api/software-variants`。
- 已将任务分配改为保存 `session_ids` 和 `resolved_software_plan`。
- 已阻断未审核、来源不合规、OS 不兼容、缺少必要 hash/signature 策略的软件变体
  进入 `DeploymentAssignment`。
- 已明确默认目录中的第三方软件只作为“官方来源声明”展示；未通过审核前不可作为
  自动安装项。

### 2.1 SoftwarePackage

表示管理员看到的一个软件，例如“飞书”。

关键字段：

- `id`
- `name`
- `vendor`
- `category`
- `description`
- `homepage`
- `icon_path`
- `status`
- `created_at`
- `updated_at`

### 2.2 SoftwareVariant

表示某个软件在某类系统上的具体安装包。

关键字段：

- `id`
- `package_id`
- `os_family`：`windows`、`ubuntu`、`linux`、`pve` 等。
- `os_version_constraint`：例如 `>=22.04`、`windows_11`。
- `arch`：例如 `x86_64`。
- `version`
- `installer_type`：`exe`、`msi`、`deb`、`apt`、`script`、`zip`。
- `download_url`
- `official_source_url`
- `source_policy`：`official_vendor`、`official_package_repo`、
  `approved_enterprise_mirror`、`admin_reviewed_download`。
- `sha256`
- `signature_policy`
- `size_bytes`
- `install_phase`：`winpe_stage`、`windows_first_boot`、`ubuntu_late_command`、
  `linux_first_boot`。
- `install_command_template`
- `uninstall_command_template`
- `silent_args`
- `default_for_os`：同一应用、同一目标系统下的首选可安装版本。
- `selection_priority`：当存在多个可安装版本时的确定性排序权重。
- `requires_network`
- `risk_level`
- `review_status`

字段边界：

- `download_url` 只能指向官网、官方包仓库、管理员批准的企业镜像源，或管理员
  审核过的 HTTPS 安装器直链。
- `apt_package` 代表目标系统通过官方/批准的 APT 仓库安装包名，`download_url`
  可以为空；此时执行依据是 `official_source_url`、`package_name`、
  `source_policy=official_package_repo` 和 `signature_policy=repo_signed`。
- `download_deb`、`msi_install` 等需要下载独立安装器的动作必须提供
  `download_url`，并继续走 HTTPS、本机/内网/SynaBoot 静态目录拦截和 hash/签名
  策略校验。
- `admin_reviewed_download` 适合 Windows 这类没有统一正式软件源的安装器场景：
  管理员只保存审核过的 HTTPS 安装器直链、静默参数、校验策略和返回码，不要求
  填写官方来源页，但仍不允许把安装包放在 SynaBoot 的 `/images` 或 `/boot` 下。
- `download_url` 不得指向 localhost、loopback、private/link-local/reserved IP、
  当前 SynaBoot 服务地址、`/images`、`/boot` 或其它项目静态目录。
- `sha256` / `signature_policy` 是客户端下载安装前后的校验策略，不代表本项目
  保存该安装包。
- 管理员可以维护 `install_action`、`installer_type`、`package_name`、
  `download_url`、`silent_args` 等受控执行元数据，把一个“仅记录官方下载页”的
  软件版本转换为 runner 已支持的自动安装版本；这只是更新客户端 postinstall
  计划，不得引入安装包上传、服务端缓存或任意命令执行。
- `install_command_template` 只能作为审查说明或未来模板来源；runner 不得直接
  执行前端或数据库里的任意命令字符串。
- 当管理员把某个变体设为 `default_for_os=true` 时，后端必须自动取消同一
  `package_id + os_family` 下其它变体的默认标记，避免一个应用在同一系统上出现
  多个“默认版本”。
- 应用级选择解析时，后端必须按 `default_for_os DESC`、
  `selection_priority DESC`、`updated_at DESC`、`id` 的确定性顺序选择变体，
  不能依赖数据库偶然返回顺序。

### 2.3 SoftwareProfile

表示一组默认软件选择，可绑定到镜像、客户端或批量任务。

关键字段：

- `id`
- `name`
- `os_family`
- `variant_ids`
- `default_for_image_ids`
- `risk_level`
- `review_status`

说明：

- `SoftwareProfile` 不是软件市场首页的主对象，而是任务模板或默认软件集合。
- 软件市场首页主对象是 `SoftwarePackage`。
- 创建安装任务时可以选择“应用列表”，也可以套用一个 `SoftwareProfile`。

### 2.4 DeploymentAssignment

表示一次独立装机会话的系统和软件分配。

关键字段：

- `id`
- `session_id`
- `source_image_id`
- `boot_target`
- `software_profile_ids`
- `software_variant_ids`
- `status`
- `created_by`
- `created_at`
- `expires_at`

说明：

- 同一台机器可以多次进入被动安装，每次进入都创建新的
  `ClientInstallSession`。
- 每次分配都是一次独立的 `DeploymentAssignment`，支持重装系统。
- 当前实现中 `software_variant_ids` 已进入真实任务解析和
  `resolved_software_plan` 持久化。
- `software_profile_ids` 已进入第一阶段真实解析：后端会读取已审核 profile，
  展开其中的 OS-specific `variant_ids`，再统一进入兼容性、来源、审核状态和
  runner 支持校验。
- `assignment-options` 已新增 `compatible_software_by_target`。后端会按每个
  boot target 输出真正可分配的软件目录：Windows/HotPE 这类尚无 postinstall
  注入闭环的目标返回空集合，Ubuntu 目标只返回已审核、来源合规、runner 支持的
  Ubuntu 变体。
- `assignment-options` 同时新增 `compatible_software_profiles_by_target`。默认
  软件集合也必须按 boot target 输出，不能只靠前端从全量 profile 里筛选。
- `DeploymentAssignment` 已新增 `software_package_ids`。创建安装任务时，前端
  默认提交管理员选择的应用 ID，后端再按 `boot_target` 解析到对应 OS 的
  已审核、可分配 `SoftwareVariant`。这避免管理员必须理解具体 `.msi` / `.deb`
  / APT 变体，也避免前端成为唯一的 OS 变体选择防线。
- 前端创建安装任务时可以选择与目标系统兼容且可分配的默认软件集合，也可以继续
  单独多选已通过审核的软件变体。
- 当前默认提供 `Ubuntu 基础工具` profile，包含已验证的 `curl-ubuntu-apt`；
  profile 编辑器已进入第一阶段：管理员可以创建新的软件集合，集合只能引用
  已审核、可分配、同一 OS 的 `SoftwareVariant`。
- `SoftwareProfile` 只保存集合 metadata 和 `variant_ids`，不能携带下载 URL、
  原始安装命令或安装包文件。它是 Apple Store 式“默认安装清单”，不是新的
  本地软件仓库。

### 2.4.1 应用级选择解析

当前任务创建链路同时支持三种输入：

- `software_package_ids`：管理员选择的应用，例如 Chrome、飞书、curl。
- `software_profile_ids`：管理员选择的默认软件集合。
- `software_variant_ids`：兼容旧接口或调试场景的显式变体选择。

推荐 UI 使用 `software_package_ids`。后端解析规则如下：

1. 根据 `boot_target` 判断目标 OS family。
2. 对每个应用 ID 查找该 OS family 下已审核、来源合规、runner 支持的变体。
3. 如果同一应用同一 OS 下存在多个可安装变体，优先选择 `default_for_os=true`
   的变体；没有默认版本时按 `selection_priority` 和稳定字段排序选择。
4. 将解析出的变体与 profile 展开的变体、显式变体去重后进入统一校验。
5. 将原始应用选择写入 `DeploymentAssignment.software_package_ids`，并在
   `resolved_software_plan.packages` 中记录最终选中的变体。

这样管理员在界面里看到和选择的是应用，执行层拿到的是对应系统的受审变体。
如果目标系统没有可用变体，后端必须拒绝任务，而不是让前端静默降级。

### 2.3.1 SoftwareProfile 创建边界

已新增后端接口：

- `GET /api/software-profiles`
- `POST /api/software-profiles`

创建规则：

- `variant_ids` 必须非空。
- 所有软件变体必须存在、已审核、`assignable=true`。
- 所有软件变体必须与 profile 的 `os_family` 一致。
- profile 默认 `approved`，因为它只组合已审核变体，不新增执行能力。
- profile 不能保存 URL、二进制、任意 shell 命令或静默参数。

前端规则：

- 软件市场页面新增“新增软件集合”。
- 可勾选项只显示当前系统下已审核且可自动安装的软件版本。
- 创建后的集合会出现在客户端创建安装任务面板中，作为默认软件集合使用。

## 3. OS-specific 软件执行点

### Windows

短期策略：

- iPXE/HotPE 只负责进入 Windows 安装路径。
- 软件包安装计划写入 Windows 安装后阶段。
- 优先使用 `SetupComplete.cmd`、首次登录脚本或后续轻量 postinstall runner。
- 不默认在 WinPE 中执行普通业务软件安装器，因为很多安装器依赖完整 Windows
  用户态环境。
- Windows postinstall runner 从软件官网或官方企业下载链接获取安装器，不从
  SynaBoot 服务器下载第三方安装包。

### Ubuntu Desktop

短期策略：

- Ubuntu 安装器启动仍使用已验证的 HTTP kernel/initrd + NFS casper livefs。
- 软件安装计划通过 autoinstall/cloud-init、late-commands 或首次启动 systemd
  服务执行。
- `.deb`、APT、受控 shell 脚本必须有官方来源、hash/signature 策略和 manifest。
- Ubuntu 优先使用官方 APT 源、软件厂商官方 APT 源或管理员批准的企业镜像源。
- `apt_package` 不要求填写安装器直链；runner 在目标系统内执行
  `apt-get update && apt-get install -y <package_name>`，依赖仓库签名校验。
  当前阶段它只表示 Ubuntu 默认 apt 源中可直接安装的包，不表示“自动添加任意
  第三方 apt repo/keyring”。需要新增外部 apt 源的软件必须先走 `download_deb`
  或等待后续受审的 apt repo 配置动作。
  只有 `download_deb` 这类动作才会从 `download_url` 下载独立安装器。

### PVE / 其它 Linux

短期策略：

- 在对应 OS 启动策略没有验证前，软件变体只能进入 `research_required`。
- 不把 Ubuntu 的 late-command 逻辑直接套给 PVE、Debian、RHEL 或 ESXi。

## 4. 管理员按钮事件契约

### 4.1 设置管理员 token

当前问题：

- 前端只把 token 写入 `localStorage`。
- 没有向后端验证 token 是否有效。
- 失败时管理员看不出是 token 错、后端未配置，还是请求失败。

目标点击流程：

```text
点击“设置管理员 token”
  -> 打开 token 输入弹窗或侧边抽屉
  -> 调用 GET /api/admin/session，携带 X-SynaBoot-Admin-Token
  -> 后端返回 authenticated/admin_configured
  -> 成功后写入 localStorage 并刷新受保护数据
  -> 失败时显示明确错误，不保存无效 token
```

后端契约：

- `GET /api/admin/session`
  - 未配置 token：`200 {"admin_configured": false, "authenticated": false}`
  - token 正确：`200 {"admin_configured": true, "authenticated": true}`
  - token 错误：`403 {"error": "invalid_admin_token"}`

### 4.2 客户端任务创建与分配

当前问题：

- 只用 `prompt` 选择编号。
- 只能提交单个 boot target。
- 没有展示镜像兼容的软件包。
- 失败时缺少可操作反馈。
- 客户端页语义不准确，看起来像状态页，而不是安装任务创建页。

目标点击流程：

```text
选择一个或多个客户端
  -> 点击“创建安装任务”
  -> 拉取 GET /api/assignment-options?session_ids=<ids>
  -> 管理员选择目标系统镜像
  -> 管理员点击“选择软件”
  -> 打开软件市场式多选弹窗
  -> UI 按目标系统过滤软件市场应用
  -> 管理员多选默认软件或额外软件
  -> 弹窗右侧持续显示“已选软件”
  -> 任务面板中也显示已选软件标签
  -> 管理员确认
  -> POST /api/deployment-assignments
  -> 后端为单机或批量客户端写入 assignment
  -> 客户端下一次 /api/ipxe/wait 自动拿到启动脚本
  -> 前端刷新客户端状态并显示成功/失败
```

短期兼容实现：

- 保留 `POST /api/client-sessions/<session_id>/assign` 作为简单 boot target 分配。
- 新增 `POST /api/deployment-assignments` 后，前端优先使用新接口。
- 在软件市场未完成前，任务面板先允许选择系统镜像，软件区域显示
  “该 OS 暂无可用软件包”。
- 客户端页必须有单选/多选能力，为批量任务预留数据结构。

后端契约：

- `GET /api/assignment-options?session_id=<id>`
  - 返回可安装镜像、boot target、兼容软件 profile、当前 session 摘要。
- `GET /api/assignment-options?session_ids=<id1,id2>`
  - 返回批量任务可用的公共启动目标、公共兼容软件集合和冲突提示。
- `POST /api/deployment-assignments`
  - 输入：`session_ids`、`source_image_id`、`boot_target`、
    `software_profile_ids`、`software_variant_ids`。
  - 输出：assignment 对象。

### 4.3 上传 ISO

当前问题：

- 按钮只是前端 alert。
- 管理员不知道应该放到哪个目录，也不会触发扫描或准备任务。

目标点击流程：

```text
点击“上传 ISO”
  -> 打开上传面板
  -> 选择 .iso 文件
  -> POST /api/uploads/iso multipart
  -> 后端写入 data/uploads/staging
  -> 校验扩展名、大小、路径、hash
  -> 原子移动到 data/images
  -> 创建 ISO 扫描和准备任务
  -> 前端显示任务状态并刷新镜像列表
```

短期可落地方案：

- 若浏览器大文件上传暂时不实现，按钮必须改成“导入本地 ISO”面板。
- 面板展示安全 drop-folder，例如 `data/images/`，并提供
  `POST /api/scan` 触发重新扫描。
- 不能继续保持无后端动作的 alert。

后端契约：

- `POST /api/uploads/iso`
  - 接收 ISO 文件并创建准备任务。
- `POST /api/scan`
  - 重新扫描本地 `data/images`，作为短期导入路径。
- `GET /api/jobs`
  - 展示上传、扫描、准备任务。

### 4.4 刷新

当前问题：

- 自动刷新太频繁，管理员页面有明显打扰。

目标行为：

- 手动“刷新”按钮立即刷新。
- 自动刷新改为每 5 分钟一次，即 `300000ms`。
- 客户端等待室轮询仍可保持 5-15 秒，因为那是 iPXE 启动脚本的装机链路，
  不是管理员 Web UI 的刷新频率。

## 5. API 与 UI 实施顺序

1. 补齐文档和计划，明确按钮事件契约。
2. 将 Web UI 自动刷新改为 5 分钟，手动刷新保持即时。
3. 新增 `GET /api/admin/session`，让 token 按钮先验证再保存。
4. 将客户端分配从 `prompt` 升级为面板：
   - 第一阶段只分配镜像/boot target。
   - 第二阶段接入软件 profile 选择。
5. 将上传 ISO 按钮改为真实导入动作：
   - 第一阶段支持本地 drop-folder + `POST /api/scan`。
   - 第二阶段支持 multipart 上传和任务进度。
6. 新增软件市场只读骨架：
   - 软件包列表。
   - OS 变体列表。
   - 软件 profile 列表。
7. 重做客户端页为安装任务创建页：
   - 客户端单选/多选。
   - 创建单机任务。
   - 创建批量任务。
   - 系统镜像选择。
   - 兼容软件选择。
8. 再接入 Windows 和 Ubuntu 的安装后执行计划。

## 5.3 2026-06-20 postinstall runner 第一阶段落地状态

已完成：

- `DeploymentAssignment` 保存 `resolved_software_plan`，后续执行不再实时信任
  前端传入的软件 ID、URL、参数或 action。
- 新增 token 保护的 postinstall 接口：
  - `GET /api/postinstall/assignments/<id>/plan`
  - `GET /api/postinstall/assignments/<id>/runner.sh`
  - `GET /api/postinstall/assignments/<id>/runner.ps1`
  - `POST /api/postinstall/assignments/<id>/events`
- plan/runner/event 都要求 `session_id` 属于该 assignment，且 session token
  匹配 `client_sessions.session_token_hash`。
- Ubuntu runner 第一阶段只支持 `linux_first_boot` 的 `apt_package` 和
  `download_deb`。
- Windows runner 第一阶段支持 `windows_first_boot` 的 `msi_install`、
  `exe_install` 和 `office_odt_install`。
- Windows 通过 HotPE/WinPE 显式注入 `SetupComplete.cmd` 进入首次启动 runner：
  仅设置 iPXE 变量或提供 endpoint 仍不会被 Windows Setup/WinPE/安装后 Windows
  自动消费；管理员必须在确认目标 Windows 根目录后使用 helper 写入
  `Windows\Setup\Scripts\SetupComplete.cmd`。
- 新增 `windows-hotpe-inject.ps1` 作为 HotPE/WinPE 半自动注入准备件：
  - 必须由管理员明确传入目标 Windows 根目录。
  - 只写入 `Windows\Setup\Scripts\SetupComplete.cmd`。
  - 不自动识别磁盘，不执行分区/格式化/清盘，不改网络。
  - 不下载或托管第三方软件安装包。
  - 真正的软件安装在已安装 Windows 首次启动后执行，不在 WinPE 内安装业务软件。
- Windows runner 安装动作边界：
  - `msi_install`：只安装审核通过的 MSI，下载地址必须是 HTTPS 官方来源或批准
    企业镜像；可选 sha256 校验；安装结束后清理临时 MSI。
  - `office_odt_install`：只下载 Microsoft Office Deployment Tool，并用受控
    Office 产品 ID 生成固定 `configuration.xml`；不接受 raw XML、不拼接任意
    PowerShell 命令、不把 Office 安装包保存到 SynaBoot。
  - Office 产品 ID 存在 `package_name` 字段，例如 `ProPlus2021Volume`；管理员
    需要确认它与自己的批量授权/订阅策略匹配后再批准变体。
- Windows/Office 激活边界：
  - 只支持管理员配置的自有 KMS 主机：
    `SYNABOOT_KMS_HOST`、`SYNABOOT_KMS_PORT`、
    `SYNABOOT_WINDOWS_KMS_ACTIVATE`、`SYNABOOT_OFFICE_KMS_ACTIVATE`。
  - 默认关闭；不内置公共 KMS，不保存产品密钥，不实现 KMS 模拟器、破解或绕过授权。
  - Windows 激活使用 Microsoft `slmgr.vbs`；Office 激活使用已安装 Office 的
    `ospp.vbs`。
- Ubuntu runner 会回传 runner 和软件变体两级状态：
  - `runner started/failed/completed` 表示安装后 runner 的整体生命周期。
  - `variant started/completed/failed` 表示某个软件变体的安装进度和结果。
  - 事件走 token 保护的 `POST /api/postinstall/assignments/<id>/events`。
  - 后台客户端列表按 `assignment_id + session_id` 统计，避免批量任务互相污染。
- `DeploymentAssignment.status` 只能由 `runner` 级事件推进为
  `postinstall_started`、`postinstall_completed` 或 `postinstall_failed`；
  `variant` 级事件只进入 `recent_events` 和 `event_summary`，不能把整次装机任务
  提前标记为完成或失败。否则单个软件完成会让后台误判系统安装和全部软件安装已经
  结束。
- runner 只按 allowlist 分支执行，不拼接 shell/PowerShell raw command，不执行
  `install_command_template`。
- runner 在客户端下载 plan 后仍会二次校验，不只依赖服务端生成 runner 时的校验：
  - OS family 必须匹配 runner 类型。
  - install phase 必须匹配首次启动阶段。
  - `review_status` 必须为 `approved`。
  - `install_action` 必须在对应 OS allowlist 内。
  - `download_url` 必须 HTTPS 且不得指向本机、内网或 SynaBoot 静态目录。
  - `sha256_required` 时必须提供 sha256。
  - Ubuntu `apt_package` 必须使用受控 `package_name`，不能回退到 variant id。
  - Windows `msi_install` 必须使用 `installer_type=msi`。
  - Windows `exe_install` 必须使用 `installer_type=exe`，且必须有审核过的
    `silent_args`。
  - Windows `office_odt_install` 必须使用 `installer_type=office_odt` 和受控
    Office 产品 ID。
- postinstall plan 的 `execution_model.allowed_install_actions` 必须按目标 OS 暴露
  当前 runner 真实支持的动作：Ubuntu 只声明 `apt_package` / `download_deb`，
  Windows 只声明 `msi_install` / `exe_install` / `office_odt_install`。
  `official_download` 这类仅表示“官方页面来源”的
  metadata 不能出现在可执行动作列表中，避免后台或未来客户端误以为已经支持自动
  操作任意官网页面。
- event 上报只保存有限枚举状态和白名单 payload 字段，不保存安装日志、命令输出、
  环境变量、token 或 secret。
- event message 入库前会对 token、password、secret、api key、authorization 等
  敏感模式脱敏；`exit_code` 和 `duration_seconds` 必须为受限数字。
- HTTP 访问日志会对 `token=` 和 `session_token=` query 值脱敏。

软件市场来源原则：

- SynaBoot 不保存第三方软件安装包。
- 本地只保存软件声明、官网/官方源下载链接、安装阶段、签名或 hash 策略、审核状态。
- 被选中的客户端在系统安装完成后，从对应官网、官方包源或已批准企业镜像下载。
- SynaBoot 不作为软件下载代理；runner 脚本应让客户端直接访问官方来源，或访问
  管理员显式批准的企业镜像源。
- 禁止实现“服务端先下载官方安装器，再让客户端从 SynaBoot 下载”的快捷路径；
  这会把 SynaBoot 变成事实上的第三方软件仓库，必须作为单独企业镜像源能力重新
  设计、审计和显式启用。
- 下载地址必须是 HTTPS，且不得指向 localhost、loopback、private/link-local/
  reserved IP、当前 SynaBoot 服务器、`/images` 或 `/boot` 这类本项目静态目录。
- 这个原则适用于所有未来新增软件，包括飞书、浏览器、压缩工具、驱动工具、
  安全软件和企业内部常用软件；新增软件时只能新增 metadata、官方 URL 和安装
  策略，不能新增安装包文件。

隔离验证：

```bash
python3 -m py_compile apps/api/main.py
npm run build  # 在 apps/web 下执行
```

已用临时 DB 和临时 HTTP 服务验证：

- 创建 ready Ubuntu target。
- 临时批准一个 Ubuntu 软件变体。
- 创建 `DeploymentAssignment`。
- `plan` 返回 200。
- `runner.sh` 返回 200。
- 错误 token 返回 403。
- `events` 返回 201。
- 非法数字 event payload 返回 400。
- 日志不出现真实 session token，只显示 `token=<redacted>`。
- `runner.sh` 包含 runner failure trap 和 per-variant
  started/completed/failed 事件回传逻辑。
- `variant completed/failed` 事件不会改变 assignment 全局生命周期；
  只有 `runner completed/failed` 才会把 assignment 状态推进到
  `postinstall_completed` 或 `postinstall_failed`。
- postinstall plan 的 execution model 已收敛为 OS-specific runner 能力声明：
  Ubuntu plan 只包含 `apt_package` / `download_deb`，Windows plan 只包含
  `msi_install` / `exe_install` / `office_odt_install`，不再把尚未支持的 `official_download`
  暴露为可执行动作。
- Windows plan 默认包含 `activation.kms.enabled=false`，只有管理员显式配置自有
  KMS 后才会在 runner 中执行 Windows/Office 激活。
- Windows 安装任务默认追加 `microsoft-office`，后端解析为 `office-windows-odt`；
  这样管理员即使只选择 Windows 系统镜像，也会得到 Office 2021 ProPlus 的受控
  ODT 安装计划。该默认项仍受软件来源、runner allowlist 和授权边界保护。
- `office-windows-odt` 的默认产品 ID 是 `ProPlus2021Volume`，面向客户自有批量
  授权场景；如客户授权模型不同，必须在软件市场维护入口调整产品 ID/通道并重新
  审核。
- 飞书 Ubuntu 不能使用 `https://www.feishu.cn/download` 这类下载页作为自动安装
  源。只有管理员配置并审核 `SYNABOOT_FEISHU_UBUNTU_DEB_URL` 官方 Linux amd64
  `.deb` 直链后，`feishu-ubuntu-amd64` 才会从 metadata 变成可执行的
  `download_deb` 变体。
- NoCloud `user-data` 注入的 first-boot bootstrap 已覆盖真实客户端网络抖动场景：
  下载 token 保护的 `runner.sh` 最多重试 20 次，每次间隔 15 秒；systemd 服务使用
  `Restart=on-failure`、`RestartSec=30s`、`StartLimitBurst=20` 和
  `StartLimitIntervalSec=15min` 做有界重试；runner 成功后删除本地 `runner.sh`
  并禁用服务，避免 token-bearing 脚本长期留在目标系统。

仍未完成：

- 把 runner 注入真实 Windows first-boot / Ubuntu first-boot 的完整 OS 安装链路。
- 软件审核/批准后台。
- 软件版本、hash、签名策略的持续维护工作流。
- 真实客户端完成 OS 安装后自动执行软件安装的端到端实验验收。
- Windows Office ODT 在真实 Windows 客户端中的下载、安装、KMS 激活端到端验收。

## 5.4 2026-06-20 软件市场来源与目标能力保护

本轮新增硬约束：

- 软件市场继续按 Apple Store / Windows Store 式应用目录设计。SynaBoot 只保存
  metadata、官方下载链接、官方软件源、安装模板、hash/signature 策略和审核状态。
- 不把第三方安装包放入项目服务器、镜像仓库、启动目录、Web 静态目录、SMB 共享
  或 Git。
- 被选中的软件必须在目标 OS 安装后，由客户端从官方来源或批准企业镜像源下载。
- 后端启动目标新增 `software_assignment_enabled` 和 `postinstall_status`：
  - Ubuntu/Linux：当前允许创建附带软件的任务，走 NoCloud first-boot runner。
  - Windows：当前允许创建附带软件的任务，但依赖 HotPE/WinPE 显式注入
    `SetupComplete.cmd`，首次启动后由 Windows runner 执行。
  - HotPE：作为维护/安装辅助环境，不作为普通业务软件自动安装目标。
- 前端根据目标能力禁用软件选择按钮，并在目标不支持时清空已选软件。
- `check-software-assignment-flow.sh` 已覆盖：
  - Ubuntu 批量任务附带软件计划。
  - 缺失 session 的事务回滚。
  - Windows 附带软件任务可创建，并生成 `runner.ps1` / `setupcomplete.cmd` /
    `windows-hotpe-inject.ps1`。
  - Windows runner 包含 MSI、Office ODT、Windows KMS、Office KMS 受控分支；
    默认 KMS disabled，且 `activation.kms.public_kms_embedded=false`。
  - 临时 localhost API server 拉取 postinstall `plan`、`runner.sh`、
    NoCloud `user-data` 并上报 event，验证真实 HTTP endpoint 行为。
  - 同一批任务中不同客户端的 boot token 不能跨 session 访问 HTTP endpoint。

## 5.4.1 2026-06-23 Windows 企业式软件部署模型补充

调研结论：

- Windows 企业统一装机通常采用 MDT / MECM / Intune 风格的应用部署模型，而不是
  简单把安装器复制到某个目录执行。
- Configuration Manager 的应用由 application + deployment type 组成；deployment
  type 包含安装内容、安装命令、检测规则、需求规则、返回码、依赖和用户体验设置。
- Windows OSD 任务序列会把 boot image、OS image、软件更新和应用安装组合起来，
  再部署到包含目标电脑的 collection。
- `SetupComplete.cmd` 可作为 Windows 安装后 bootstrap，但它不检查退出码，也不
  应在其中重启，因此只能负责拉起 SynaBoot runner，不能作为复杂任务序列本身。

对 SynaBoot 软件市场的模型调整：

- `SoftwarePackage` 继续表示管理员看到的应用，例如飞书、Chrome、Office。
- `SoftwareVariant` 需要逐步演进为类似 deployment type 的执行声明：
  - `install_context`：`winpe`、`system_first_boot`、`user_logon`。
  - `install_command`：仍必须来自受控模板，不允许任意 raw command。
  - `detection_rules`：用于判断软件是否已安装或安装是否成功。
  - `requirements`：OS 版本、架构、磁盘空间、前置软件、是否需要用户登录。
  - `dependencies`：安装前必须完成的软件变体。
  - `return_codes`：成功、成功需重启、软失败、硬失败。
  - `restart_behavior`：禁止、允许、需要管理员确认、需要排队到任务末尾。
  - `install_location_policy`：`system_default`、`installer_supported_path`、
    `portable_folder`、`not_supported`。
- Windows 软件安装路径不能作为通用能力承诺：
  - MSI 有些支持 `INSTALLDIR`，有些不支持。
  - EXE 完全取决于厂商静默参数。
  - Office ODT 不应承诺任意安装目录。
  - 不支持自定义目录的软件必须显示“系统默认位置”。

对客户端任务的模型调整：

- 后续 `DeploymentAssignment` 应升级为轻量 task sequence：

```text
boot_winpe
collect_hardware
select_image
apply_windows
inject_drivers
apply_unattend
inject_bootstrap
first_boot
install_software
detect_software
report_result
```

- 软件安装阶段必须先检测再安装：
  - 检测规则已满足时跳过并回报 `already_installed`。
  - 安装后重新检测，检测通过才算 `variant completed`。
  - 安装命令退出码和检测结果冲突时，检测结果优先。
- 支持的首批检测规则：
  - MSI ProductCode。
  - 文件存在和文件版本。
  - 注册表键和值。
  - 受控 PowerShell 检测脚本。

边界：

- 免费版借鉴 MDT/MECM 的轻量任务序列与软件检测模型，不承诺替代 MECM/SCCM、
  Intune、Autopilot、Entra ID 或 MDM。
- 设备 MAC/UUID/serial 只能作为匹配线索，不作为强身份认证。
- 没有 Windows 安装后 runner 回调时，后台不能假装知道软件安装结果。

2026-06-23 本轮实现状态：

- 后端已保留安装任务预设接口，并撤回分区模板公开能力：
  - `GET /api/install-presets`
  - `POST /api/install-presets`
- `assignment-options` 已按 boot target 返回：
  - `install_presets_by_target`
  - `compatible_software_by_target`
  - `compatible_software_profiles_by_target`
- 默认 Windows 预设 `windows-office-standard` 会把 `microsoft-office` 合并到任务
  软件清单。
- Windows 分区预设经调研后从当前阶段撤回：
  - 批量机器硬盘数量、容量、启动模式和保留数据需求无法用一个统一模板覆盖。
  - 企业级分区应在 WinPE 采集磁盘证据后，通过任务序列条件和变量决定。
  - 当前代码不生成 `diskpart`、`format`、`Clear-Disk` 或自动清盘脚本。
- 创建安装任务的前端面板已支持选择：
  - 系统镜像/启动目标
  - 安装任务预设
  - 软件市场多选软件和软件集合
- 管理后台新增“安装任务预设”菜单，用于查看可复用的系统 + 软件组合。
- Windows 软件安装仍只落在完整 Windows 首次启动后：
  `SetupComplete.cmd` 下载 token 绑定的 `runner.ps1`，runner 再按审核后的
  software plan 从官方来源或管理员批准来源下载并安装。
- 2026-06-24 Windows 自动化安装深化：
  - Windows runner 支持 `msi_install`、`exe_install`、`office_odt_install`。
  - Windows 新增 `admin_reviewed_download` 来源策略：不要求正式软件源或官方来源页，
    只要求管理员审核 HTTPS 安装器直链、安装动作、安装器类型、静默参数和校验策略。
  - `exe_install` 必须配置审核过的静默参数；未配置时后端拒绝保存，避免客户端
    首次启动卡在安装器交互界面。
  - HotPE/WinPE 注入 helper 可以接收 `-WindowsRoot`；未指定时只在唯一发现一个
    离线 Windows 目录时自动注入，多个候选或找不到都会 fail-fast。
  - 安装任务预设页面支持创建、归档和恢复预设；预设只保存系统目标和默认软件组合，
    不包含清盘、格式化或磁盘设置。
- 当前阶段尚未实现 Windows OS apply 自动化；自动分区能力已从公开计划中移除，
  未来如恢复，必须先完成 WinPE 磁盘证据、二次确认、dry-run、审计、回滚和
  subagent 审查。

## 5.5 2026-06-20 软件变体审核维护入口

新增最小可用的软件市场维护闭环：

- 后端新增 `POST /api/software-variants/<variant_id>/review`。
- 管理员可更新：
  - `review_status`
  - `enabled`
  - `signature_policy`
  - `sha256`
  - `official_source_url`
  - `download_url`
  - `source_policy`
  - `risk_level`
  - `notes`
- 后端拒绝：
  - 非 HTTPS 官方链接。
  - 指向 SynaBoot 自身 `/images`、`/boot` 的第三方软件 URL。
  - localhost、内网、link-local、reserved IP 下载源。
  - 非 allowlist 的来源策略、签名策略和审核状态。
  - 非 64 位 hex 的 sha256。
- 前端软件市场页面为每个变体提供：
  - 批准自动安装
  - 退回审核
  - 启用
  - 禁用

`assignable` 的含义同步收紧：

- 通过审核只是前置条件。
- 变体还必须具备当前 OS runner 真实支持的 `install_action`、`install_phase` 和
  `installer_type`。
- 例如官方页面下载但 runner 尚未支持自动化安装的变体，仍会展示在软件市场，
  但不会出现在创建安装任务的可选软件中。

## 5.6 2026-06-20 默认官方源验证软件

为避免软件市场只能靠临时改库验证，本轮新增一个安全的默认可安装样例：

- 软件包：`curl`
- 变体：`curl-ubuntu-apt`
- 系统：Ubuntu
- 安装动作：`apt_package`
- `package_name`：`curl`
- 来源策略：`official_package_repo`
- 签名策略：`repo_signed`
- 默认审核状态：`approved`

该样例不托管任何安装包。客户端在 Ubuntu 首次启动 runner 中执行：

```text
apt-get update
apt-get install -y curl
```

用途：

- 作为实验隔离环境中验证“被动模式分配 Ubuntu + 自动安装软件”的最小闭环。
- 作为后续新增飞书、Chrome、VS Code 等第三方官方来源软件时的行为基线。

配套结构变更：

- `software_variants` 新增 `package_name` 字段。
- 旧数据库会自动迁移该字段，默认值为空字符串。
- 管理员维护接口允许更新 `package_name`，但必须符合 apt 包名 allowlist 正则，
  不能塞入 shell 命令。
- 当前 `apt_package` 只支持 Ubuntu 默认 apt 源中已有的软件包。即使某个外部 apt
  源版本被管理员标为默认版本，只要 runner 尚未实现 repo/keyring 配置，它也会
  因 `apt_repo_not_supported` 保持不可分配；应用级选择会回落到同系统下真正
  `assignable` 的变体。

## 5.7 2026-06-20 官方来源 URL 边界补强

软件市场的两个来源字段都必须遵守“不由 SynaBoot 托管或伪装托管”的原则：

- `download_url`：客户端实际下载软件安装器或访问官方包源的地址。
- `official_source_url`：管理员审查时看到的官方来源或官方说明页面。

本轮补强：

- `download_url` 继续拒绝 localhost、loopback、private/link-local/reserved IP、
  当前 SynaBoot 服务器、`/images`、`/boot` 等项目静态路径。
- `official_source_url` 也使用同一套本机/内网/项目静态路径拦截规则。
- 管理员不能把 `https://<SynaBoot>/boot/...` 或
  `https://<SynaBoot>/images/...` 伪装成软件官网来源。
- UI 已补充 runner 未支持、安装阶段不支持、安装器类型不支持、包名非法等
  阻断原因中文文案。
- `check-software-assignment-flow.sh` 已覆盖 SynaBoot-hosted `official_source_url`
  被拒绝的回归用例。

## 5.8 2026-06-20 任务事件可见性与批量 token 修复

为让管理员确认“被动客户端安装系统后是否真的执行软件安装”，本轮补齐任务事件
可见性：

- `record_postinstall_event()` 继续写入 `client_events`。
- `GET /api/deployment-assignments` 和单任务详情现在返回：
  - `recent_events`
  - `event_summary`
- 客户端安装任务页在管理员视图下显示最近安装任务：
  - 系统/启动目标。
  - 分配客户端数量。
  - 自动安装软件清单。
  - 最近 runner 状态和消息。

同时修复一个批量任务真实缺陷：

- 旧模型在 `deployment_assignments` 上只保存一个 `boot_token_hash`。
- 同一个批量任务中多台客户端依次轮询时，后一个客户端会覆盖前一个客户端的
  boot token。
- 如果其中一台先回传 `postinstall_completed`，其它同批客户端还可能被全局状态
  阻断。
- 旧事件汇总只按秒级 `created_at` 判断最新事件；runner 和 variant 在同一秒内
  连续回调时，后台可能展示旧事件，导致最近状态不稳定。

修复方式：

- 新增 `assignment_boot_tokens` 表。
- 按 `assignment_id + session_id` 独立保存 boot token。
- postinstall 鉴权优先使用 per-session token。
- 保留旧字段作为兼容回退，但新签发路径不再互相覆盖。
- 客户端列表中的 `latest_assignment.event_summary` 也必须按当前
  `assignment_id + session_id` 查询事件，不能直接复用 assignment 全局
  `event_summary`。否则批量任务中 `session-0` 完成软件安装后，`session-1`
  会被误显示为已完成。
- 事件读取统一按 `created_at DESC, rowid DESC` 排序，同一秒内的连续回调也能稳定
  显示最新事件。
- assignment 全局状态只接受 `runner` 级事件推进；`variant` 级事件只作为软件明细
  和 summary 证据，避免单个软件完成或失败提前结束整次任务。

验证：

- `check-software-assignment-flow.sh` 已覆盖同一批两个 session 的 token 签发、
  runner/NoCloud 访问、事件回传和 assignment list 的 `event_summary` 可见性。
- `check-software-assignment-flow.sh` 已覆盖 `session-0` 回传 completed 后，
  `session-1` 的客户端摘要仍不能出现其它 session 的 postinstall 状态。
- `check-software-assignment-flow.sh` 已覆盖 `variant completed` 不会把 assignment
  标记为 `postinstall_completed`，`variant failed` 不会把 assignment 标记为
  `postinstall_failed`；只有 `runner completed/failed` 才能推进全局生命周期。

## 5.9 2026-06-20 客户端任务摘要可见性

为减少管理员在“客户端列表”和“最近安装任务”之间来回对照，本轮把最近任务摘要
挂到管理员视图的客户端会话上：

- `client_session_payload` 增加 `latest_assignment` 摘要。
- 摘要只包含 assignment id、启动目标、状态、软件数量、软件标签和当前客户端
  session 的 event summary。
- 摘要不包含 session token、boot token、token hash、下载密钥或完整脚本。
- 脱敏客户端列表继续不返回 `latest_assignment`。
- 前端客户端列表新增“软件/进度”列，直接显示本次安装任务选择的软件和最近
  runner/event 状态。
- `check-software-assignment-flow.sh` 已覆盖客户端会话能暴露最近任务、软件标签和
  postinstall 最新状态。
- 管理后台“最近安装任务”卡片已经展示软件变体级进度：
  - 每个被选软件根据 `recent_events[].payload.variant_id` 取最新 variant 事件。
  - 状态显示为等待回调、执行中、已完成、失败、已阻断或已跳过。
  - 卡片底部展示最近 runner/variant 回调，方便管理员判断具体卡在哪个阶段。
  - 该展示只消费后端脱敏后的 `recent_events`，不显示 token、脚本或安装日志。

复审结论：

- `webui_agent`：PASS，认为客户端页更符合“创建安装任务工作台”的定位。
- `security_audit_agent`：PASS，确认新增摘要未扩大 token/hash/secret 暴露面。

## 5.10 2026-06-20 软件变体来源维护入口

软件市场需要能维护大量应用的官方来源和安装元数据，不能只依赖默认硬编码目录。
本轮在前端补齐最小可用的“维护来源”入口：

- 每个软件变体新增“维护来源”按钮。
- 管理员可以维护：
  - `official_source_url`
  - `download_url`
  - `source_policy`
  - `signature_policy`
  - `sha256`
  - `package_name`
  - `install_action`
  - `installer_type`
  - `silent_args`
  - `risk_level`
  - `notes`
- 保存仍走 `POST /api/software-variants/<variant_id>/review`，复用后端已有校验。
- 前端不提供安装包上传入口。
- 前端提供受控静默参数字段，由后端校验长度和安全字符；不提供任意 shell 命令、
  raw command 或安装包上传入口。
- 后端继续拒绝非 HTTPS、本机/内网/SynaBoot `/images`/`/boot`、非法 sha256 和
  非法 apt 包名，并继续按 OS runner 白名单校验 `install_action`。

这一步让软件市场从“只能看和批准默认条目”推进到“可以维护官方来源 metadata”，
但仍不把 SynaBoot 变成第三方软件仓库。

## 5.11 2026-06-20 软件市场来源边界再确认

后续软件市场可以扩展大量应用，但扩展对象必须是“应用声明”和“可信来源”，不是
安装包文件。

- 软件市场按 Apple Store 式目录理解：管理员选择应用，FlashPXE/SynaBoot 下发
  受控安装计划，目标客户端在安装后的 Windows/Ubuntu 环境中自行访问官网、官方
  包仓库或管理员批准的企业镜像源下载安装。
- 本地允许保存：软件名称、厂商、分类、官网、官方下载 URL、官方包源说明、
  企业批准镜像源 URL、安装动作类型、受审 runner 模板、hash/signature 策略。
- 本地禁止保存：第三方 `.exe`、`.msi`、`.deb`、`.pkg`、压缩包、离线安装器。
- 本地也禁止通过 HTTP 静态目录、SMB 共享、反向代理、透明缓存或“临时下载后再
  分发”的方式间接托管第三方安装包。
- 任务分配时保存的是 `resolved_software_plan`，客户端在目标 OS 完成安装后按
  计划访问官方来源下载安装。
- 若官方来源无法自动下载、需要登录态或无法建立校验策略，则只能展示为
  `manual_required` / `research_required`，不得进入自动安装任务。

## 5.12 2026-06-20 软件目录新增能力

软件市场第一阶段已支持管理员维护“应用目录”和“系统版本” metadata：

- `POST /api/software-packages` 新增应用，只保存应用 ID、名称、厂商、分类、说明、
  官网 URL 和图标 key。
- `POST /api/software-packages/<package_id>/variants` 新增 OS-specific 系统版本，
  只保存官方来源、下载 URL/官方包源说明页、来源策略、签名策略、安装动作、包名
  和风险等级。
- 新增版本默认 `needs_review`，不能直接进入自动安装任务。
- 审核仍走现有 `POST /api/software-variants/<variant_id>/review`；只有通过审核、
  runner 支持且来源/签名策略满足要求的版本才会变为 `assignable`。
- 前端软件市场新增“新增应用”和“新增系统版本”表单；表单不包含文件选择器、
  上传按钮或任意 shell 命令。静默安装参数只作为受控字段提交，必须通过后端
  安全字符和长度校验。
- `check-software-assignment-flow.sh` 已覆盖新增应用、拒绝 SynaBoot-hosted 来源、
  新增版本默认不可分配、审核后可进入 Ubuntu apt 自动安装计划。

## 5.12.1 2026-06-20 软件目录归档/恢复能力

软件市场新增软删除式维护能力，用于处理管理员误建或暂时不想分配的软件条目：

- `POST /api/software-packages/<id>/archive`：归档应用。
- `POST /api/software-packages/<id>/restore`：恢复应用。
- `POST /api/software-profiles/<id>/archive`：归档软件集合。
- `POST /api/software-profiles/<id>/restore`：恢复软件集合。

归档原则：

- 不做数据库硬删除，避免破坏历史安装任务、审计证据和
  `DeploymentAssignment.resolved_software_plan`。
- 归档应用仍可在软件市场中查看和恢复，但不会出现在创建安装任务的应用级软件选择
  中。
- 如果软件集合引用了已归档应用下的变体，该集合会变为不可分配；显式提交
  `software_variant_ids` 也不能绕过应用归档状态。
- 归档软件集合仍保留 metadata，但不会出现在创建安装任务的默认软件集合中。
- 归档不改变第三方安装包边界：仍然不上传、不缓存、不代理、不分发第三方安装器。

验证：

- `check-software-assignment-flow.sh` 已覆盖应用归档后无法通过
  `software_package_ids` 进入计划、引用已归档应用的 profile 不可分配、显式
  `software_variant_ids` 不能绕过应用归档、恢复后重新可用；也覆盖软件集合归档后
  不再是 compatible profile，恢复后重新可分配。

## 5.13 2026-06-20 应用多版本默认选择规则

为让管理员在创建任务时只选择“应用”，而不是理解每个系统版本的安装细节，本轮
补齐同一应用、同一系统下多个可安装版本的确定性选择规则：

- `SoftwareVariant` 新增 `default_for_os` 和 `selection_priority`。
- 同一 `package_id + os_family` 只能有一个默认版本。管理员把某个变体设为默认时，
  后端会自动取消其它同系统变体的默认标记。
- `software_package_ids` 解析时优先选默认版本；没有默认版本时按优先级和稳定字段
  选择。
- 前端软件市场可维护“默认版本”和“优先级”，应用卡片会标明默认版本，便于管理员
  理解任务实际会落到哪个 OS-specific 变体。
- 该规则不改变软件来源边界：默认版本仍然只是 metadata 和安装计划，不意味着
  SynaBoot 保存、缓存或转发该软件的安装包。

验证：

- `check-software-assignment-flow.sh` 已覆盖 Chrome Ubuntu 两个可安装变体时，
  新默认版本覆盖旧默认标记，并且应用级选择最终解析到新默认变体。

## 5.14 2026-06-20 APT 官方源安装 URL 语义修正

为避免管理员为了 APT 官方源软件填写一个“伪下载地址”，本轮把
`apt_package` 与独立安装器下载动作分开：

- `apt_package` 只要求 `official_source_url`、`package_name`、官方/批准包源策略
  和仓库签名策略；`download_url` 可以为空。
- `download_deb`、`msi_install`、`official_download` 等下载安装器的动作仍必须
  提供 HTTPS `download_url`，且不得指向 SynaBoot 自身、内网、`/images`、`/boot`
  或其它项目静态目录。
- Ubuntu runner 对 `apt_package` 不读取 `download_url`，只在目标系统中通过
  apt 官方源安装包名；对 `download_deb` 才校验并下载 `download_url`。
- 前端新增/维护软件版本时，安装器下载 URL 提示改为“download_deb / msi_install
  必填；apt_package 可留空”。

验证：

- `check-software-assignment-flow.sh` 已覆盖 `htop-ubuntu-apt` 与
  `chrome-ubuntu-default-apt` 在 `download_url` 为空时仍可经审核进入 Ubuntu
  软件计划。

## 5.15 2026-06-24 飞书 Windows MSI 批量部署配置

管理员提供飞书官方 MSI 批量部署教程和 MSI 直链后，默认软件市场已将
`feishu-windows-x64` 调整为可执行的 Windows 自动安装变体：

- `installer_type=msi`
- `install_action=msi_install`
- `install_phase=windows_first_boot`
- `download_url=https://sf3-cn.feishucdn.com/obj/hera-cn/download/Feishu-win32_x64-7.68.6-signed.msi`
- `source_policy=admin_reviewed_download`
- `signature_policy=vendor_signed`
- `silent_args=/qn /norestart`
- `review_status=approved`
- `enabled=true`

这条配置符合软件市场“不托管第三方安装包”的原则：

- SynaBoot 只保存飞书 MSI 的官方来源声明、下载 URL、静默参数和审核状态。
- Windows 客户端完成系统安装并进入首次启动后，由
  `SetupComplete.cmd -> runner.ps1` 按安装任务的 `resolved_software_plan`
  从飞书 CDN 下载 MSI 并静默安装。
- 旧实验数据库启动时会自动迁移 `feishu-windows-x64`，避免前端继续看到旧的
  EXE/下载页配置。

验证：

- `check-software-assignment-flow.sh` 已覆盖 Windows 目标中飞书变体必须解析为
  `msi_install`，且下载 URL 必须是管理员提供的飞书 MSI 直链。
- 创建 Windows 安装任务选择“飞书”时，后端会把 `feishu-windows-x64` 与默认
  Office 变体一起写入 `resolved_software_plan`。
- Windows postinstall plan 会保留 `/qn /norestart` 静默参数并通过 runner 校验。

## 5.2 2026-06-20 下一轮 UI 修正

需要调整：

- `软件` 页从“软件配置”改名和改造为“软件市场”。
- 软件市场使用应用卡片、分类、搜索、系统筛选和应用详情，而不是统计卡片。
- `客户端` 页从“客户端列表”改造成“安装任务”工作台。
- 客户端页支持单选、多选、批量选择，并以“创建安装任务”为主按钮。
- 创建任务时先选系统镜像，再进入软件市场选择；软件市场根据目标系统自动过滤
  可安装应用和 OS-specific 变体。
- 创建任务选择软件必须使用弹窗式多选体验；弹窗内部布局与软件市场一致，并在
  右侧或底部明确显示所有已勾选软件。
- `DeploymentAssignment` 需要支持 `session_ids`，而不只是一条 `session_id`。
- 前端文案中避免让管理员误解“客户端页只是观察在线状态”。

## 5.1 2026-06-19 本轮落地状态

已完成：

- 新增 `GET /api/admin/session`，管理员 token 会先经后端验证，再保存到浏览器。
- 新增 `GET /api/assignment-options?session_id=<id>`，为客户端分配面板提供会话、
  可分配启动目标和软件配置占位数据。
- 新增 `POST /api/deployment-assignments`，当前会创建一次独立分配记录，并兼容
  已验证的启动目标分配。
- 新增 `deployment_assignments` SQLite 表，用于记录每次被动安装会话的分配结果。
- 管理后台自动刷新改为 5 分钟一次，手动刷新仍立即执行。
- 镜像页“上传 ISO”按钮改为本地 ISO 导入面板，可用管理员 token 触发
  `POST /api/scan` 重新扫描 `data/images`。
- 客户端页“分配”按钮改为页面内分配面板，不再依赖编号 prompt。

暂未完成：

- 浏览器 multipart 大文件上传。
- 软件市场“新增应用 / 新增系统变体”的管理界面和软件 profile 编辑。
- Windows / Ubuntu 安装后的软件执行器。

## 6. 安全边界

- 软件包、脚本、ISO 不得上传到公网 SaaS。
- 第三方软件安装包默认不存放在 SynaBoot 服务器上。
- 第三方软件安装包不得通过 SynaBoot 进行透明缓存、反向代理或二次分发。
- SynaBoot 只存放软件安装声明、官方下载链接、安装脚本模板、hash/signature
  校验规则和审查结果。
- 下载域名必须进入 allowlist，并标记来源类型：官方厂商、官方包仓库或批准的
  企业镜像。
- 无 hash、无签名、来源不明或跳转链不可审计的软件不得标记为 ready。
- UI 不允许管理员直接输入任意 shell 命令作为软件安装命令。
- 安装命令只能来自已审查 manifest 和 allowlist 模板。
- hash 不匹配的软件包不得进入 ready。
- token、密码、私钥不得写入日志、Git、前端 payload 或客户端脚本。
- 批量安装软件不得默认包含清盘、分区、格式化、改网络、改防火墙动作。
- Phase 2 不因软件分发启用 DHCP、ProxyDHCP、TFTP 或改网关/DNS。
