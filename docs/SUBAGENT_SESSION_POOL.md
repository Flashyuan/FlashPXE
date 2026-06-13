# SynaBoot Subagent 固定会话池与协作台账

本文档用于记录当前 milestone 的 subagent 会话池、协作操作和长期记忆。

目标不是把 subagent 当一次性 reviewer，而是把 11 个角色当成可持续协作岗位。
上下文压缩、会话恢复或工具 registry 失效后，主控必须先读取本文档，再继续
协作，避免凭记忆复述旧结论。

## 0. 长期记忆字段要求

本文档是 subagent 协作的长期记忆源。上下文压缩、线程恢复、工具 registry
重置或主控切换后，不能只依赖聊天摘要判断 subagent 曾经说过什么。

每个 active subagent 至少必须长期记录以下字段：

- `role`：固定岗位名，必须对应 `.codex/agents/*.toml` 中的 11 个角色之一。
- `agent_id`：当前工具层可通信的会话 id；不可通信时必须标记为 `stale`。
- `status`：`pending`、`active`、`blocked`、`stale` 或 `closed`。
- `operation_log`：每次发送任务、收到结论、复审、超时、失败、关闭或重建的摘要。
- `latest_topic`：该角色最近处理的主题。
- `progress`：该角色对当前 milestone 的完成进度或阻断点。
- `reusable_conclusion`：压缩恢复后允许继续引用的结论，必须能在结论表中找到证据。
- `next_reuse_rule`：下一次何时复用该角色，防止遇到小问题就新开会话。

维护规则：

- 每次与 subagent 通信后，必须同步更新“操作流水表”和“协作统计与压缩恢复快照”。
- 每次某个结论会影响实现方向、网络安全、发布范围或用户承诺时，必须同步更新
  “结论与进度表”。
- 如果某条结论没有登记在本文档中，压缩恢复后只能视为未确认，不能当作
  subagent 已批准。
- 如需替换会话，必须在操作流水中记录旧 `agent_id` 失效原因和新 `agent_id`。

### 0.1 压缩恢复防幻觉规则

上下文压缩后，主控必须把本文档当成 subagent 结论的唯一长期记忆锚点。
聊天摘要只能作为定位线索，不能单独作为审计、批准、阻断或完成进度的证据。

恢复时必须按以下顺序执行：

1. 读取“协作统计与压缩恢复快照”，确认 11 个固定岗位的 `agent_id`、状态、
   最近主题、当前进度和后续复用规则。
2. 读取“结论与进度表”，只引用其中有 `reusable evidence` 的结论。
3. 如需继续调用某个角色，优先对登记的 `agent_id` 做轻量握手或继续
   `send_input`。
4. 若工具层返回 `agent not found`、超时、无法接收输入或输出明显偏离岗位，
   先在操作流水中记录 `stale`，再决定是否替换该角色。
5. 未登记在“操作流水表”和“结论与进度表”的 subagent 回复，只能视为
   未确认信息，不得写入最终结论、验收状态或 PLAN 进度。

禁止行为：

- 禁止凭压缩摘要声称某个 subagent 已经批准。
- 禁止把旧会话 UI 仍可见当成工具层仍可通信。
- 禁止把 `completed=null`、空输出或 spawn 失败登记为 APPROVED。
- 禁止为了找回缺失记忆而新建一批同职责 subagent。
- 禁止在未更新本文档的情况下结束包含 subagent 通信的 milestone。

## 1. 当前结论

- `.codex/agents/*.toml` 是 11 个长期角色定义。
- 右侧 UI 中显示的历史 agent 窗口，不等于当前工具层仍可访问的会话。
- 工具层返回 `agent not found` 时，该 agent id 视为 `stale`。
- 工具层返回子模型解析错误时，说明该次 `spawn_agent` 没有成功创建会话。
- 2026-06-13 已按用户要求再次关停上轮 11 个可访问旧会话，并重新初始化
  11 个固定岗位。
- `multi_agent_v1` 工具层当前可关停旧会话并创建 default 会话；项目 custom
  `agent_type` spawn 仍返回 child model 解析失败。本轮继续采用 default 会话
  显式绑定岗位的方式建立长期池，并在表中记录真实 `agent_id`。

## 2. 固定会话池启动协议

每个 milestone 开始时执行：

1. 读取上轮登记表。
2. 对已有 agent id 先尝试恢复或发送轻量握手。
3. 可通信的会话标记为 `active` 并继续复用。
4. `agent not found`、无法恢复或明显跑偏的会话标记为 `stale`。
5. 工具层 spawn 正常时，按 11 个项目角色建立固定会话池。
6. 固定会话池建立后，本 milestone 只向登记会话发送任务。
7. 若工具层无法建立固定会话池，暂停 subagent 调用并向用户报告。

## 3. 角色岗位总表

| role | 固定职责 | 触发条件 | 当前状态 | 当前 agent_id | 备注 |
| --- | --- | --- | --- | --- | --- |
| research_agent | 外部事实、协议、设备能力和资料证据 | 外部事实不确定、Phase 3 前置调查 | active | 019ec02f-abcd-70b2-9364-cdb120d3d2a4 | default 会话显式指定 research 岗位 |
| project_decision_agent | 方向、阶段、收费边界和取舍决策 | 影响路线、商业边界、发布方向 | active | 019ec02f-ac76-7863-899a-3af5498ce444 | 只处理方向、阶段、收费边界和重大取舍 |
| network_safety_agent | LAN 零侵入和网络启动安全边界 | Compose 网络、端口、DHCP/ProxyDHCP/TFTP、路由、防火墙 | active | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | Phase 3 网络安全强制门禁 |
| architecture_agent | 架构、数据模型、API 和阶段边界 | 模型/接口/阶段设计变化 | active | 019ec02f-adf7-7162-8721-3b127ac3e51f | 负责架构边界、服务拓扑和阶段划分 |
| boot_entry_agent | iPXE/HTTP Boot/PXE/启动菜单链路 | 启动菜单、boot assets、Phase 3 入口 | active | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | 负责 iPXE、loader、menu.ipxe 和 PXE/HTTP Boot 链路 |
| storage_agent | 镜像仓库、扫描、元数据、静态文件 | ISO/WIM/文件扫描和仓库状态 | active | 019ec02f-b120-7a92-9823-4e9f386c70ba | 保持镜像仓库和生成物边界 |
| image_factory_agent | 镜像准备任务、模板和任务包 | ISO 准备、autoinstall 模板、任务框架 | active | 019ec02f-b31a-7cb0-a544-314d1092e227 | 负责非破坏性镜像准备任务 |
| webui_agent | Web UI 和管理员体验 | 页面、交互、状态展示 | active | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | PXE 仅展示规划/待审核/只读状态 |
| tutorial_docs_agent | 文档、教程、操作说明和交接材料 | README/指南/验收记录 | active | 019ec02f-b887-7c11-bb50-825e065706cb | 文档覆盖隔离验证、回滚和用户流程 |
| security_audit_agent | 安全、路径、命令、Docker、secret 边界 | 安全/发布边界、脚本、输入输出 | active | 019ec02f-baba-7832-bc4a-ed9d8d696048 | 负责脚本、路径、loader、网络启动安全审计 |
| git_audit_agent | diff、发布范围、commit/push 就绪 | milestone 收口、commit/push 前 | active | 019ec02f-bd09-7520-88db-b57c0d35c296 | 免费版 commit/push readiness；商业代码绝不 push |

状态枚举：

- `pending`：本 milestone 尚未建立或握手。
- `active`：工具层可通信，可继续 `send_input`。
- `stale`：UI 可能仍显示，但工具层 `agent not found` 或不可恢复。
- `blocked`：agent 返回 BLOCKED，等待主控修复并回传同一会话。
- `closed`：milestone 收口后主动关闭。

## 4. 当前会话登记表

```text
milestone: Phase 3 UEFI PXE IPv4 Boot 受控规划与免费版发布线
started_at: 2026-06-13
last_verified_at: 2026-06-13

role                         agent_id  status   note
research_agent               019ec02f-abcd-70b2-9364-cdb120d3d2a4  active  READY
project_decision_agent        019ec02f-ac76-7863-899a-3af5498ce444  active  READY
network_safety_agent          019ec02f-ad02-7ae0-8c00-c7baeb46709e  active  READY
architecture_agent            019ec02f-adf7-7162-8721-3b127ac3e51f  active  READY
boot_entry_agent              019ec02f-aedd-78d0-b7ac-efb3f69b6791  active  READY
storage_agent                 019ec02f-b120-7a92-9823-4e9f386c70ba  active  READY
image_factory_agent           019ec02f-b31a-7cb0-a544-314d1092e227  active  READY
webui_agent                   019ec02f-b56a-7f83-aa03-0c45c88e8e4b  active  READY
tutorial_docs_agent           019ec02f-b887-7c11-bb50-825e065706cb  active  READY
security_audit_agent          019ec02f-baba-7832-bc4a-ed9d8d696048  active  READY
git_audit_agent               019ec02f-bd09-7520-88db-b57c0d35c296  active  READY
```

## 5. 操作流水表

每次向 subagent 发送任务、收到结论、标记 stale、重建会话或关闭会话，都必须
追加一条流水。流水只记录摘要，不记录 token、私有源码、ISO 内容、license
或客户数据。

| time | role | agent_id | action | input_summary | output_summary | status_after | evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-06-13 | security_audit_agent | 019ebd6c-9a18-7503-89b9-e075459c0898 | send_input/wait | ISO prepare symlink 风险复核 | 先 BLOCKED，修复后 PASS | stale | 后续 close/send 返回 `agent not found` |
| 2026-06-13 | security_audit_agent | 019ebd6c-9a18-7503-89b9-e075459c0898 | send_input/wait | real ISO smoke 脚本复核 | PASS | stale | 后续 registry 不再可访问 |
| 2026-06-13 | security_audit_agent | - | spawn_failed | 自动安装边界门禁复核 | 工具层子模型解析错误，未创建 agent | pending | 未产生新 agent_id |
| 2026-06-13 | research_agent | 019ebf4e-b6eb-71f1-91c6-2a600db9db7f | spawn/send_input | 固定会话池初始化，研究岗位 | READY | active | custom agent_type 失败后使用 default 会话显式指定岗位 |
| 2026-06-13 | project_decision_agent | 019ebf4f-2219-78e3-9945-2a3e4c6ff055 | spawn/wait | 固定会话池初始化，决策岗位 | READY，Phase 3 仅允许规划 | active | 不允许启用 DHCP/ProxyDHCP/TFTP |
| 2026-06-13 | network_safety_agent | 019ebf4f-50c5-7a13-bc04-597d2770f50a | spawn/wait | 固定会话池初始化，网络安全岗位 | READY，列出隔离验证前置条件 | active | 不替换主 DHCP，不改网关 |
| 2026-06-13 | architecture_agent | 019ebf4f-70d4-7983-a6ff-0cffafd8d089 | spawn/wait | 固定会话池初始化，架构岗位 | READY，提出 Phase 3 核心模型 | active | BootIntegrationProfile 等模型 |
| 2026-06-13 | boot_entry_agent | 019ebf4f-9737-73a2-8e50-84938632f09a | spawn/wait | 固定会话池初始化，启动链路岗位 | READY，提出 UEFI PXE IPv4 链路草案 | active | TFTP/ProxyDHCP 仍为规划 |
| 2026-06-13 | storage_agent | 019ebf4f-bd9f-72f2-956c-070b4fa73de7 | spawn/wait | 固定会话池初始化，存储岗位 | READY，镜像仓库边界确认 | active | HTTP 静态路径稳定 |
| 2026-06-13 | image_factory_agent | 019ebf4f-d9fa-7081-8203-51b3909abdc7 | spawn/wait | 固定会话池初始化，镜像工厂岗位 | READY，任务边界确认 | active | 不执行 PXE/ProxyDHCP/TFTP |
| 2026-06-13 | webui_agent | 019ebf4f-f8dc-7e83-9973-24bb53fc247c | spawn/wait | 固定会话池初始化，Web UI 岗位 | READY，PXE 只读状态字段 | active | 不提供启用按钮 |
| 2026-06-13 | tutorial_docs_agent | 019ebf50-1dac-7453-8297-5324a684c48c | spawn/wait | 固定会话池初始化，文档岗位 | READY，文档主题清单 | active | 不写 token/私有内容 |
| 2026-06-13 | security_audit_agent | 019ebf50-3be9-7d52-9285-41c5ee10eeb1 | spawn/wait | 固定会话池初始化，安全审计岗位 | READY，PXE 风险项清单 | active | 不开放 UDP 67/69/4011 |
| 2026-06-13 | git_audit_agent | 019ebf50-5a35-7ea0-b623-f384979bd853 | spawn/wait | 固定会话池初始化，Git 审计岗位 | READY，push 前检查清单 | active | 不 stage/commit/push |
| 2026-06-13 | research_agent | 019ebf4e-b6eb-71f1-91c6-2a600db9db7f | send_input/wait | Phase 3 PXE IPv4 外部事实清单 | 需确认 TL-ER6120T DHCP Options、PXE/HTTPClient 区分、UEFI TFTP/HTTP 能力、Secure Boot 兼容性 | active | 当前禁止启用 DHCP/ProxyDHCP/TFTP |
| 2026-06-13 | project_decision_agent | 019ebf4f-2219-78e3-9945-2a3e4c6ff055 | send_input/wait | Phase 3 项目方向决策 | 批准进入 PXE IPv4 只读规划与隔离验证准备，禁止生产 LAN 直接启用 | active | 需 network/security 审查后再授权生产集成 |
| 2026-06-13 | network_safety_agent | 019ebf4f-50c5-7a13-bc04-597d2770f50a | send_input/wait | Phase 3 网络安全门禁 | 生产 LAN 禁止 DHCP/ProxyDHCP/TFTP/UDP 67/69/4011；隔离环境可验证 | active | 不替换 192.168.1.1 DHCP，不改 192.168.1.4 网关 |
| 2026-06-13 | architecture_agent | 019ebf4f-70d4-7983-a6ff-0cffafd8d089 | send_input/wait | Phase 3 最小架构增量 | 只新增只读模型、状态展示、审查门禁和隔离验证描述；不新增运行时网络服务 | active | 建议 phase3 readonly/blocked 配置对象 |
| 2026-06-13 | boot_entry_agent | 019ebf4f-9737-73a2-8e50-84938632f09a | send_input/wait | UEFI PXE IPv4 启动链路 | 推荐固件 PXE -> DHCP 租约 -> TFTP iPXE loader -> HTTP menu.ipxe -> SynaBoot 菜单 | active | TFTP 仅限 loader，HTTP 承载菜单和镜像资源 |
| 2026-06-13 | security_audit_agent | 019ebf50-3be9-7d52-9285-41c5ee10eeb1 | send_input/wait | Phase 3 安全审查重点 | Docker 权限、命令执行、路径边界、loader allowlist、ISO 管理、免费/商业边界均需门禁 | active | 默认配置不得包含 PXE 网络服务启用入口 |
| 2026-06-13 | architecture_agent | 019ebf4f-70d4-7983-a6ff-0cffafd8d089 | send_input/wait | Phase 3.5 isolated_validation_plan 架构审查 | APPROVED，只读计划字段合理；必须显式包含 production_lan_allowed=false、服务关闭和门禁要求 | active | 不得变成实验授权或服务启用配置 |
| 2026-06-13 | network_safety_agent | 019ebf4f-50c5-7a13-bc04-597d2770f50a | send_input/wait | Phase 3.5 隔离验证计划网络安全审查 | APPROVED，只允许只读准备；禁止服务、端口、Docker host/privileged、生产 LAN 自动探测 | active | 预检需守住主 DHCP、网关、UDP 端口和服务关闭不变量 |
| 2026-06-13 | security_audit_agent | 019ebf50-3be9-7d52-9285-41c5ee10eeb1 | send_input/wait | Phase 3.5 隔离验证计划安全审计 | APPROVED，只读展示数据；不得新增启用接口、任务执行、真实网络配置或商业私有逻辑 | active | 要求 API 有 read_only/runtime_enabled 等明确状态 |
| 2026-06-13 | project_decision_agent | 019ebf4f-2219-78e3-9945-2a3e4c6ff055 | send_input/wait | Phase 3.5 下一步方向决策 | APPROVED，批准 API/UI/预检 readonly isolated_validation_plan；禁止生产 LAN 集成和 ProxyDHCP/TFTP 实现 | active | 后续真实 PXE 集成前需重新审核与授权 |
| 2026-06-13 | boot_entry_agent | 019ebf4f-9737-73a2-8e50-84938632f09a | send_input/wait | pxe_ipv4_readiness 启动链路审查 | APPROVED，字段适合汇总 menu.ipxe、ipxe.efi/snponly.efi、ready 镜像和 Phase 3 门禁 | active | 不得把 readiness=true 误写成 PXE 已可用；present/usable/boot_tested 必须分开 |
| 2026-06-13 | network_safety_agent | 019ebf4f-50c5-7a13-bc04-597d2770f50a | send_input/wait | pxe_ipv4_readiness 网络安全审查 | APPROVED，仅允许只读前置条件汇总；必须保留生产 LAN、DHCP、ProxyDHCP、TFTP、UDP 端口等 false 不变量 | active | 不得驱动服务启动或网络配置写入 |
| 2026-06-13 | storage_agent | 019ebf4f-bd9f-72f2-956c-070b4fa73de7 | send_input/wait | pxe_ipv4_readiness 镜像元数据边界审查 | APPROVED，可读取已有 image metadata；不得重新扫描、读取 ISO 内容、重算 SHA256 或修改 menu_enabled/boot_readiness | active | 使用只读 SQLite 快照降级，避免写 metadata |
| 2026-06-13 | security_audit_agent | 019ebf50-3be9-7d52-9285-41c5ee10eeb1 | send_input/wait | pxe_ipv4_readiness 安全审计 | APPROVED，只读 summary；必须 operation_allowed/service_enablement_allowed/production_lan_testing_allowed=false | active | 不得被执行器、任务队列、启动器或 Compose 生成器引用 |
| 2026-06-13 | git_audit_agent | 019ebf50-5a35-7ea0-b623-f384979bd853 | send_input/wait | pxe_ipv4_readiness Git 审计首轮 | BLOCKED，指出 readiness 先调用 `list_images()` 会写 metadata，不符合只读承诺 | active | 已改为只读 SQLite snapshot，并补空 metadata 不写入测试 |
| 2026-06-13 | git_audit_agent | 019ebf50-5a35-7ea0-b623-f384979bd853 | send_input/wait | pxe_ipv4_readiness Git 审计复审 | APPROVED，本轮只读修复通过；无新的本轮 BLOCKED 项 | active | 整仓 commit/push readiness 仍需单独发布范围审计和用户二次确认 |
| 2026-06-13 | image_factory_agent | 019ebf4f-d9fa-7081-8203-51b3909abdc7 | send_input/wait | Linux ISO 启动依赖批量准备脚本审查 | APPROVED，符合 Image Factory 职责；只能用已有 bsdtar/7z，不安装依赖、不 mount、不覆盖、不处理 Windows/HotPE | active | 本机缺少解包工具，脚本按预期 fail-fast |
| 2026-06-13 | git_audit_agent | 019ebf50-5a35-7ea0-b623-f384979bd853 | send_input/wait | Linux ISO 准备脚本 Git 审计首轮 | BLOCKED，指出 data/images、data/builds、WORK_ROOT/hash work 目录父路径 symlink 可导致写项目外 | active | 已补 canonical 校验和 symlink 边界 smoke |
| 2026-06-13 | git_audit_agent | 019ebf50-5a35-7ea0-b623-f384979bd853 | send_input/wait | Linux ISO 准备脚本 Git 审计复审 | APPROVED，本轮脚本 symlink 修复通过；无本轮强制补测项 | active | 成功路径 smoke 等安装 bsdtar/7z 后再补 |
| 2026-06-13 | image_factory_agent | 019ebf4f-d9fa-7081-8203-51b3909abdc7 | send_input/wait | ISO9660 fallback 与真实 Linux 提取审查 | APPROVED_WITH_FIXES，要求移除动态 `rm -rf` 并限制 ISO extent/size | active | 已改为 work 存在即 BLOCKED，提取器加大小/extent 上限和流式复制 |
| 2026-06-13 | security_audit_agent | 019ebf50-3be9-7d52-9285-41c5ee10eeb1 | send_input/wait | ISO9660 提取器安全审查 | APPROVED_WITH_RECOMMENDATIONS，建议固化异常 ISO、symlink、O_EXCL、allowed-root 门禁 | active | 已新增 `check-iso-extractor-safety.sh` 并接入 release evidence |
| 2026-06-13 | boot_entry_agent | 019ebf4f-9737-73a2-8e50-84938632f09a | send_input/wait | Ubuntu ready 菜单与 PXE 链路审查 | APPROVED，HTTP menu 与镜像入口层已推进；下一缺口是 UEFI iPXE loader | active | `ready_menu_entry_count=6`，但 `snponly.efi/ipxe.efi` 仍 missing |
| 2026-06-13 | git_audit_agent | 019ebf50-5a35-7ea0-b623-f384979bd853 | send_input/wait | ISO9660 fallback 与真实 Linux 提取 Git 审查 | APPROVED，本轮 fallback 和真实 Linux 提取无必须阻断项 | active | 建议修正文案，已更新 readiness next action |
| 2026-06-13 | git_audit_agent | 019ebf50-5a35-7ea0-b623-f384979bd853 | send_input/wait | ISO9660 fallback 最终补强复审 | APPROVED，readiness 文案、ISO extractor safety preflight、release evidence 接入均通过 | active | 生成物保持 ignored；整仓 push 前仍需完整发布范围审计 |
| 2026-06-13 | fixed_pool | 019ebf4f-2219-78e3-9945-2a3e4c6ff055 等 9 个旧会话 | close_agent | 按用户要求关闭当前 registry 可访问旧 subagents | 9 个旧会话成功关闭并返回 previous_status | closed | research/network 旧 id 另见 not_found 记录 |
| 2026-06-13 | research_agent | 019ebf4e-b6eb-71f1-91c6-2a600db9db7f | close_agent | 关闭旧 research 会话 | 工具层返回 not_found | stale | 不得继续向旧 id 发送任务 |
| 2026-06-13 | network_safety_agent | 019ebf4f-50c5-7a13-bc04-597d2770f50a | close_agent | 关闭旧 network_safety 会话 | 工具层返回 not_found | stale | 不得继续向旧 id 发送任务 |
| 2026-06-13 | research_agent | - | spawn_failed | 直接按 custom agent_type 初始化 research_agent | 工具层 child model 解析失败，未创建 agent | pending | 改用 default 会话显式绑定岗位 |
| 2026-06-13 | default_probe | 019ebf78-a150-7123-80b0-ac2de60cc32d | spawn/close | 测试 default 会话是否可创建 | default registry 可用，探测会话随后关闭 | closed | 证明失败集中在 custom agent_type spawn |
| 2026-06-13 | research_agent | 019ebf78-ca88-7d01-8bc3-f4e75a6b88bb | spawn/wait | 固定会话池重建，研究岗位 | READY，只在外部事实、协议、路由器/固件能力不确定时复用 | active | default 会话显式绑定岗位 |
| 2026-06-13 | project_decision_agent | 019ebf78-deee-7c03-bd79-9849fc63cb4c | spawn/wait | 固定会话池重建，决策岗位 | READY，只处理方向、阶段、收费边界和重大取舍 | active | 不得绕过安全审查授权生产 LAN 变更 |
| 2026-06-13 | network_safety_agent | 019ebf78-f355-7be3-9b27-3790107ac484 | spawn/wait | 固定会话池重建，网络安全岗位 | READY，触及 LAN、DHCP、ProxyDHCP、TFTP、端口、路由等必须复用 | active | 生产 DHCP 192.168.1.1、网关 192.168.1.4 不变 |
| 2026-06-13 | architecture_agent | 019ebf79-0d71-76b1-94eb-29c94f36b758 | spawn/wait | 固定会话池重建，架构岗位 | READY，负责架构边界、API、数据模型和阶段判断 | active | Phase 3 相关落地前需门禁 |
| 2026-06-13 | boot_entry_agent | 019ebf79-1dca-7082-9eb0-46fe219938f7 | spawn/wait | 固定会话池重建，启动链路岗位 | READY，负责 iPXE、menu.ipxe、loader、PXE/HTTP Boot 链路 | active | 未授权前只做只读排查和设计 |
| 2026-06-13 | storage_agent | 019ebf79-32de-76f1-a618-3057e7da6369 | spawn/wait | 固定会话池重建，存储岗位 | READY，负责镜像仓库、元数据、HTTP 静态路径和生成物边界 | active | 不删除、不覆盖用户 ISO |
| 2026-06-13 | image_factory_agent | 019ebf79-47cd-76c3-b0c6-b0c00e77e859 | spawn/wait | 固定会话池重建，镜像工厂岗位 | READY，负责非破坏性镜像准备任务和模板 | active | 不处理网络服务启用 |
| 2026-06-13 | webui_agent | 019ebf79-5b8d-7b41-b995-c86d2d5aacca | spawn/wait | 固定会话池重建，Web UI 岗位 | READY，负责管理后台体验和只读状态展示 | active | 不提供未授权 PXE 网络启用按钮 |
| 2026-06-13 | tutorial_docs_agent | 019ebf79-70aa-7753-b32c-291ac7b2de87 | spawn/wait | 固定会话池重建，文档岗位 | READY，负责 README、教程、回滚和验收记录 | active | 不把未授权能力写成生产可用 |
| 2026-06-13 | security_audit_agent | 019ebf79-83b2-7653-abbb-1542d83fb0ec | spawn/wait | 固定会话池重建，安全审计岗位 | READY，触及脚本、路径、loader、secret、Docker、网络启动时必须复用 | active | 发布前安全敏感 diff 需先审计 |
| 2026-06-13 | git_audit_agent | 019ebf79-9f3e-7163-8b1d-c69000c9e901 | spawn/wait | 固定会话池重建，Git 审计岗位 | READY，功能/里程碑收口、stage/commit/push 前必须复用 | active | 不自行 stage/commit/push |
| 2026-06-13 | boot_entry_agent | 019ebf79-1dca-7082-9eb0-46fe219938f7 | send_input/wait | loader 本地导入与 provenance 方案审查 | APPROVED，本地导入和校验属于 UEFI PXE loader 缺口准备；Phase 3 仍 blocked | active | 要求记录来源、SHA256、目标路径、loader 类型、Phase 3 blocked 和禁用网络服务证据 |
| 2026-06-13 | security_audit_agent | 019ebf79-83b2-7653-abbb-1542d83fb0ec | send_input/wait | loader 导入脚本和 API provenance 安全审查首轮 | BLOCKED，指出 reviewed_for_lab 信任过弱、源文件 TOCTOU、network safety 关键词误伤 | active | 已修复并回传同一会话复审 |
| 2026-06-13 | security_audit_agent | 019ebf79-83b2-7653-abbb-1542d83fb0ec | send_input/wait | loader 导入脚本和 API provenance 安全审查复审 | APPROVED，3 个 BLOCK 点已修复；无必须修复项 | active | `collect-release-evidence.sh`、loader safety、network safety、phase3 gates、UI syntax 均通过 |
| 2026-06-13 | git_audit_agent | 019ebf79-9f3e-7163-8b1d-c69000c9e901 | send_input/wait | loader 导入增量与固定会话池台账 Git 审计 | APPROVED，本轮发布范围审计通过；未 stage/commit/push | active | `collect-release-evidence.sh` PASS；真实 ISO/loader/metadata 被 ignored；Phase 3 仍 blocked |
| 2026-06-13 | research_agent | 019ebf78-ca88-7d01-8bc3-f4e75a6b88bb | send_input/wait | iPXE UEFI loader 官方来源与 Secure Boot 外部事实 | READY/证据返回，确认 boot.ipxe.org、GitHub release、Secure Boot shim 路线和 DHCP/ProxyDHCP first-stage 条件 | active | 官方来源记录到 `docs/IPXE_LOADER_SOURCES.md` |
| 2026-06-13 | network_safety_agent | 019ebf78-f355-7be3-9b27-3790107ac484 | send_input/wait_timeout | 官方 loader 归档导入方向网络安全审查 | 等待超时，未返回结论；未新建替代 agent | active | 本地 `check-network-safety.sh` PASS；不得把该项说成 network_safety 已批准 |
| 2026-06-13 | security_audit_agent | 019ebf79-83b2-7653-abbb-1542d83fb0ec | send_input/wait | 本地 iPXE 归档导入脚本安全审查首轮 | BLOCKED，指出归档文件 TOCTOU 和 `getmembers()` 全量 header 加载风险 | active | 已改为同 fd 打开 tar 和流式遍历成员 |
| 2026-06-13 | security_audit_agent | 019ebf79-83b2-7653-abbb-1542d83fb0ec | send_input/wait | 本地 iPXE 归档导入脚本安全审查复审 | APPROVED，归档 fd 校验、流式成员遍历、无 bytecode、无联网/执行均通过 | active | `check-loader-import-safety.sh`、`check-network-safety.sh`、`check-phase3-gates.py`、`git diff --check` 通过 |
| 2026-06-13 | git_audit_agent | 019ebf79-9f3e-7163-8b1d-c69000c9e901 | send_input/wait | iPXE 官方来源与本地归档导入 Git 审计首轮 | BLOCKED，因 network_safety_agent 审查等待超时，发布治理门禁不能通过 | active | 技术验证通过，但缺少 network_safety 明确结论 |
| 2026-06-13 | network_safety_agent | 019ebf78-f355-7be3-9b27-3790107ac484 | send_input/wait | 本地 iPXE 归档导入准备网络安全复审 | APPROVED，仅批准本地归档导入准备保留；仍禁止生产 LAN DHCP/ProxyDHCP/TFTP/UDP 启用 | active | `check-network-safety.sh`、`check-loader-import-safety.sh`、`collect-release-evidence.sh` PASS |
| 2026-06-13 | git_audit_agent | 019ebf79-9f3e-7163-8b1d-c69000c9e901 | send_input/wait | iPXE 官方来源与本地归档导入 Git 审计复审 | APPROVED，network_safety 结论补齐后发布范围审计通过；未 stage/commit/push | active | `collect-release-evidence.sh`、subagent governance、loader safety、network safety、diff check 均通过 |
| 2026-06-13 | project_decision_agent | 019ebf78-deee-7c03-bd79-9849fc63cb4c | send_input/wait | 官方 iPXE loader 下载与导入方向决策 | APPROVED，仅允许获取与 provenance 导入；不批准自动 PXE 集成或网络服务启用 | active | 下载落 ignored runtime，记录来源和 hash，不执行 loader |
| 2026-06-13 | security_audit_agent | 019ebf79-83b2-7653-abbb-1542d83fb0ec | send_input/wait | 官方 iPXE loader 下载与导入安全审查 | APPROVED，仅限本机 HTTPS 获取 + 已审脚本导入 + provenance 记录 | active | 不新增自动下载代码，不启 DHCP/ProxyDHCP/TFTP |
| 2026-06-13 | runtime | local | command | 下载官方 iPXE release 并导入 reviewed UEFI loader | 导入 `snponly.efi` 与 `ipxe.efi`，API `lab_prerequisites_met=true` | ready | 归档与 loader/metadata 均 ignored；Phase 3 status 仍 `blocked_by_phase3_gate` |
| 2026-06-13 | network_safety_agent | 019ebf78-f355-7be3-9b27-3790107ac484 | send_input/wait | 实际 iPXE loader 导入后的网络安全复核 | APPROVED，仅批准文件级前置满足和 HTTP 静态访问 | active | UDP 67/69/4011 未监听；不批准生产 LAN PXE/DHCP/ProxyDHCP/TFTP |
| 2026-06-13 | security_audit_agent | 019ebf79-83b2-7653-abbb-1542d83fb0ec | send_input/wait | 实际 iPXE loader 导入后的安全复核 | APPROVED，hash/provenance/ignored runtime/禁用网络服务字段均通过 | active | HTTP 证据随后由主控重新启动服务补充 |
| 2026-06-13 | git_audit_agent | 019ebf79-9f3e-7163-8b1d-c69000c9e901 | send_input/wait | 实际 iPXE loader 导入后的 Git/发布范围审计 | APPROVED，真实 loader/归档/metadata 均 ignored；未 stage/commit/push | active | HTTP 200、API reviewed loader、UDP 未监听、preflights PASS |
| 2026-06-13 | project_decision_agent | 019ebf78-deee-7c03-bd79-9849fc63cb4c | send_input/wait | Phase 3.9 PXE 隔离实验 Boot Metadata 只读规划方向 | APPROVED，仅允许实现 readonly metadata plan；不得生成配置、启服务或进入生产 LAN | active | 免费/商业方向不受影响；真实 PXE 集成仍需后续门禁 |
| 2026-06-13 | boot_entry_agent | 019ebf79-1dca-7082-9eb0-46fe219938f7 | send_input/wait | Phase 3.9 Boot Metadata 字段与启动链路审查 | APPROVED，建议 `snponly.efi` 为 bootfile、`ipxe.efi` 为 fallback，并记录 TFTP allowlist、HTTP menu URL、抓包证据和回滚检查 | active | TFTP 只作为未来隔离实验元数据，不提供启用入口 |
| 2026-06-13 | network_safety_agent | 019ebf78-f355-7be3-9b27-3790107ac484 | send_input/wait | Phase 3.9 PXE lab boot metadata 网络安全审查 | APPROVED，仅限只读计划；必须保持 `operation_allowed=false`、`service_enablement_allowed=false`、`runtime_enabled=false`、`production_lan_allowed=false` | active | 不监听 UDP 67/69/4011，不修改 TP-Link/OpenWrt，不启 ProxyDHCP/TFTP |
| 2026-06-13 | security_audit_agent | 019ebf79-83b2-7653-abbb-1542d83fb0ec | send_input/wait | Phase 3.9 PXE lab boot metadata 安全审计 | APPROVED，只读 API/UI 可展示候选元数据；必须禁止命令执行、配置生成、router/dnsmasq 示例和生产启用按钮 | active | 要求 `config_generation_allowed=false`、`command_execution_allowed=false` |
| 2026-06-13 | fixed_pool | 019ebf78-ca88-7d01-8bc3-f4e75a6b88bb 等 11 个上轮会话 | close_agent | 按用户要求检查并关停存续 subagents | 11 个上轮会话均可被工具层找到并关停，返回 previous_status | closed | 不再向这些旧 id 发送任务；旧结论仍按本文档结论表引用 |
| 2026-06-13 | fixed_pool | - | spawn_failed | 直接按 custom `agent_type` 初始化 11 个项目角色 | 11 次均返回 child model 解析失败，未创建 agent | pending | 按既定降级策略改用 default 会话显式绑定岗位 |
| 2026-06-13 | research_agent | 019ebfa9-a01e-7a43-bf2c-165de2a770dd | spawn/wait | 固定会话池重建，研究岗位 | READY，仅在外部事实、协议、TL-ER6120T、PXE/HTTP Boot 不确定时复用 | active | default 会话显式绑定岗位 |
| 2026-06-13 | project_decision_agent | 019ebfa9-a0c4-7fa0-aeb7-e09a757a8867 | spawn/wait | 固定会话池重建，决策岗位 | READY，仅在阶段、生产 LAN 授权、重大技术取舍、收费边界和发布确认时复用 | active | 未通过 network/security 审查前不授权生产 LAN 变更 |
| 2026-06-13 | network_safety_agent | 019ebfa9-a1af-75e0-95b5-e9c1d4dcccb2 | spawn/wait | 固定会话池重建，网络安全岗位 | READY，触及 DHCP、ProxyDHCP、TFTP、PXE、UDP 端口、TP-Link/OpenWrt、路由、防火墙、Docker 网络时必须复用 | active | 生产 DHCP 192.168.1.1、网关 192.168.1.4 不变 |
| 2026-06-13 | architecture_agent | 019ebfa9-a2df-7bb3-9865-14731d1f6293 | spawn/wait | 固定会话池重建，架构岗位 | READY，负责架构边界、API、数据模型、阶段边界、服务拓扑和跨模块影响 | active | Phase 3 网络相关设计前先由 research/network_safety 输入 |
| 2026-06-13 | boot_entry_agent | 019ebfa9-a4ec-74e3-ab22-5a592e797867 | spawn/wait | 固定会话池重建，启动链路岗位 | READY，负责 menu.ipxe、HTTP Boot、UEFI PXE IPv4 chainload、loader 和 boot metadata | active | 未获审查前不启 DHCP/ProxyDHCP/TFTP |
| 2026-06-13 | storage_agent | 019ebfa9-a783-7492-98a2-188e0f23a757 | spawn/wait | 固定会话池重建，存储岗位 | READY，负责 data/images、metadata、静态文件、生成物边界和用户镜像只读管理 | active | 不删除、不覆盖、不移动用户 ISO/镜像 |
| 2026-06-13 | image_factory_agent | 019ebfa9-aaa0-7080-834c-062793affe41 | spawn/wait | 固定会话池重建，镜像工厂岗位 | READY，负责 ISO 准备、autoinstall 草稿、Windows 外部任务包模板和非破坏性任务 | active | 不自动清盘、格式化或破坏磁盘数据 |
| 2026-06-13 | webui_agent | 019ebfa9-acae-71e1-8fae-ba9ca882c359 | spawn/wait | 固定会话池重建，Web UI 岗位 | READY，负责 UI、镜像管理体验、启动入口展示和未授权网络能力禁用态 | active | 不提供 DHCP/ProxyDHCP/TFTP 启用入口 |
| 2026-06-13 | tutorial_docs_agent | 019ebfa9-ae97-7a90-9383-b629ebbe9f20 | spawn/wait | 固定会话池重建，文档岗位 | READY，负责 README、教程、架构说明、安全边界、回滚和验收文档 | active | 未授权能力只能写为规划/实验/禁用状态 |
| 2026-06-13 | security_audit_agent | 019ebfa9-b1d0-72a2-a551-8530b7f5f838 | spawn/wait | 固定会话池重建，安全审计岗位 | READY，负责脚本、路径、Docker、secret、loader provenance 和网络启动安全边界 | active | 未授权不生成配置、执行命令或启用服务 |
| 2026-06-13 | git_audit_agent | 019ebfa9-b501-70d3-8eb1-953805d655dd | spawn/wait | 固定会话池重建，Git 审计岗位 | READY，负责 milestone 收口、diff、secrets、生成物、验证结果和发布范围审查 | active | 不 stage/commit/push |
| 2026-06-13 | architecture_agent | 019ebfa9-a2df-7bb3-9865-14731d1f6293 | send_input/wait | Phase 3.10 disabled skeleton 架构审查 | APPROVED，只建模、只校验、只展示；不生成配置、不注册服务、不启动服务、不开放 UDP | active | 建议名称固定为 `isolated-lab boot services disabled skeleton` |
| 2026-06-13 | boot_entry_agent | 019ebfa9-a4ec-74e3-ab22-5a592e797867 | send_input/wait | Phase 3.10 disabled skeleton 启动链路审查 | APPROVED，可表达 UEFI PXE IPv4 -> loader -> HTTP menu 目标模型、证据、失败模式和回滚；不得启用链路 | active | 不批准 TFTP、ProxyDHCP、DHCP boot option 或 PXE 自动入口 |
| 2026-06-13 | network_safety_agent | 019ebfa9-a1af-75e0-95b5-e9c1d4dcccb2 | send_input/wait | Phase 3.10 disabled skeleton 网络安全预审 | APPROVED，只允许 blueprint/manifest/API/UI 展示；UDP 67/69/4011、TP-Link/OpenWrt、Docker host/privileged 等继续 BLOCK | active | 必须由预检验证 DHCP、网关、端口、Docker 和运行态不变量 |
| 2026-06-13 | security_audit_agent | 019ebfa9-b1d0-72a2-a551-8530b7f5f838 | send_input/wait | Phase 3.10 disabled skeleton 安全预审 | APPROVED，只允许未来隔离实验声明式蓝图；禁止可执行配置、命令、服务启用、端口开放和生产 LAN 变更 | active | 要求 mode/scope/gates/forbidden_capabilities/loader_provenance/evidence 等安全字段 |
| 2026-06-13 | project_decision_agent | 019ebfa9-a0c4-7fa0-aeb7-e09a757a8867 | send_input/wait | Phase 3.10 方向决策 | APPROVED，批准作为隔离实验前置设计资产；不批准生产 LAN 启用或实验服务启动 | active | 蓝图不等于生产 LAN 启用授权、不等于实验环境实际启动授权 |
| 2026-06-13 | runtime | local | command | 实现 Phase 3.10 isolated-lab boot services disabled skeleton | API/UI/预检完成；HTTP/menu/loader/API smoke 通过；UDP 67/69/4011 无监听 | ready | `service_profiles` 仅含 disabled ProxyDHCP/TFTP 候选；HTTP menu 仅在 `reference_targets` |
| 2026-06-13 | network_safety_agent | 019ebfa9-a1af-75e0-95b5-e9c1d4dcccb2 | send_input/wait | Phase 3.10 实现后网络安全收口 | APPROVED，未修改 Compose、未启 DHCP/ProxyDHCP/TFTP、未开放 UDP、未改 TP-Link/OpenWrt/路由/网关/防火墙 | active | `check-network-safety.sh`、`check-phase3-gates.py`、`collect-release-evidence.sh`、UDP 无监听均通过 |
| 2026-06-13 | security_audit_agent | 019ebfa9-b1d0-72a2-a551-8530b7f5f838 | send_input/wait | Phase 3.10 实现后安全收口 | APPROVED，`http_menu_target` 已拆入 `reference_targets`，`service_profiles` 只保留两个 disabled 候选；无命令/配置/服务/端口启用 | active | 仍不批准配置生成、启动服务、开放端口或生产 LAN 测试 |
| 2026-06-13 | git_audit_agent | 019ebfa9-b501-70d3-8eb1-953805d655dd | send_input/wait | Phase 3.10 Git/发布范围审计 | 首轮因审计过程生成 `__pycache__` BLOCKED；清理并复跑证据后 APPROVED | active | `check-phase3-gates.py`、`collect-release-evidence.sh`、`git diff --check` PASS；`python_bytecode_cache=absent`；未 stage/commit/push |
| 2026-06-13 | project_decision_agent | 019ebfa9-a0c4-7fa0-aeb7-e09a757a8867 | send_input/wait | Phase 3.11 evidence package 方向决策 | APPROVED，允许作为证据准备和授权草案展示；不等于授权，不允许生产 LAN、配置生成或服务控制台 | active | 基础装机与只读证据准备继续推进，真实运行仍需 network/security/project/user gate |
| 2026-06-13 | boot_entry_agent | 019ebfa9-a4ec-74e3-ab22-5a592e797867 | send_input/wait | Phase 3.11 evidence package 启动链路预审 | APPROVED，可展示 reviewed loaders、candidate bootfile、HTTP menu URL、ready entries、客户端证据模板、期望观察和回滚；不得启 TFTP/ProxyDHCP | active | 证据包只表达未来隔离实验材料，不提供可执行网络入口 |
| 2026-06-13 | network_safety_agent | 019ebfa9-a1af-75e0-95b5-e9c1d4dcccb2 | send_input/wait | Phase 3.11 evidence package 网络安全预审 | APPROVED，只允许读取现有 API、本地文件状态和端口证据；禁止服务、抓包、主动探测和网络变更 | active | UDP 67/69/4011、DHCP、ProxyDHCP、TFTP、生产 LAN 继续 false |
| 2026-06-13 | security_audit_agent | 019ebfa9-b1d0-72a2-a551-8530b7f5f838 | send_input/wait | Phase 3.11 evidence package 安全预审 | APPROVED，只能展示只读证据、授权草案和人工清单；禁止 secrets、raw commands、配置、命令、服务和生产 LAN 字段为 true | active | 预检必须覆盖 secret、command、service、production LAN 不变量 |
| 2026-06-13 | architecture_agent | 019ebfa9-a2df-7bb3-9865-14731d1f6293 | send_input/wait | Phase 3.11 evidence package 架构预审 | APPROVED，允许新增只读模型：evidence、UDP port evidence、production LAN safety statement、authorization request、manual lab declaration 等 | active | 模型不得演变为执行器、配置生成器或服务启用 API |
| 2026-06-13 | runtime | local | command | 实现 Phase 3.11 isolated lab evidence package | API/UI/预检完成；`isolated_lab_evidence_package.status=not_authorized`；所有执行、secret、服务、生产 LAN、抓包和探测字段为 false | ready | HTTP `/`、`/boot/menu.ipxe`、两个 loader 均 200；ready_entries=6；UDP 67/69/4011 无监听 |
| 2026-06-13 | network_safety_agent | 019ebfa9-a1af-75e0-95b5-e9c1d4dcccb2 | send_input/wait | Phase 3.11 实现后网络安全收口 | APPROVED，未修改 Compose，未启 DHCP/ProxyDHCP/TFTP，未开放 UDP 67/69/4011，未抓包、未主动探测、未改 TP-Link/OpenWrt/路由/网关/防火墙 | active | `check-network-safety.sh`、`check-phase3-gates.py`、`collect-release-evidence.sh` PASS；HTTP/menu/loader/API smoke 通过 |
| 2026-06-13 | security_audit_agent | 019ebfa9-b1d0-72a2-a551-8530b7f5f838 | send_input/wait | Phase 3.11 实现后安全收口 | APPROVED，证据包为只读 `not_authorized`，授权请求仍是 `draft_not_authorized`，无新增写接口、secrets、raw command、服务或生产 LAN 启用 | active | 非阻断观察：`next_action` 为人工建议文案，不是 raw command 字段 |
| 2026-06-13 | git_audit_agent | 019ebfa9-b501-70d3-8eb1-953805d655dd | send_input/wait | Phase 3.11 Git/发布范围审计 | APPROVED，当前代码与发布范围通过；本轮未修改文件、未 stage、未 commit、未 push | active | 运行时 ISO、loader、archive、SQLite 均被 `.gitignore` 忽略；更新台账后需再做只读复审 |
| 2026-06-13 | git_audit_agent | 019ebfa9-b501-70d3-8eb1-953805d655dd | send_input/wait | Phase 3.11 台账更新后 Git 复审 | 工具返回 completed=null，无有效审计正文；不得登记为新 APPROVED | active | 已复用同一 agent；本地 `check-subagent-governance.sh`、`check-phase3-gates.py`、`check-network-safety.sh`、`collect-release-evidence.sh`、`git diff --check` 均 PASS |
| 2026-06-13 | project_decision_agent | 019ebfa9-a0c4-7fa0-aeb7-e09a757a8867 | send_input/wait | Phase 3.12 config intent 方向决策 | APPROVED，批准只读配置意图/干运行包；不批准真实配置生成、服务启动、端口开放或生产 LAN 变更 | active | 后续进入 isolated lab 执行、配置生成、服务启动、端口开放或生产 LAN 评估必须重新触发审查 |
| 2026-06-13 | architecture_agent | 019ebfa9-a2df-7bb3-9865-14731d1f6293 | send_input/wait | Phase 3.12 config intent 架构预审 | APPROVED，可挂在 `/api/boot-entry` 作为只读结构；必须不可生成、不可启动、不可消费、不可进入生产 LAN | active | 必须包含 `task_consumption_allowed=false`，不得被任务系统、Compose、脚本或服务消费 |
| 2026-06-13 | boot_entry_agent | 019ebfa9-a4ec-74e3-ab22-5a592e797867 | send_input/wait | Phase 3.12 config intent 启动链路预审 | APPROVED，可表达 PXE -> boot metadata -> loader -> HTTP menu -> ready image menu 的未来隔离实验意图；不得写 `boot_tested=true` | active | bootfile 只能是候选意图，loader allowlist 只引用 reviewed loader，HTTP menu 是 chain target |
| 2026-06-13 | network_safety_agent | 019ebfa9-a1af-75e0-95b5-e9c1d4dcccb2 | send_input/wait | Phase 3.12 config intent 网络安全预审 | APPROVED，仅展示 future isolated lab dry-run intent；所有 DHCP/ProxyDHCP/TFTP/UDP/Compose/host network/privileged/生产 LAN 字段必须 false | active | 预检需确认不生成配置、不启动服务、不开放 UDP 67/69/4011、不抓包、不主动探测 |
| 2026-06-13 | security_audit_agent | 019ebfa9-b1d0-72a2-a551-8530b7f5f838 | send_input/wait | Phase 3.12 config intent 安全预审 | APPROVED，仅限只读配置意图/干运行展示；禁止 secrets、raw command、可执行配置片段、服务启用入口和生产 LAN 操作指引 | active | 预检需递归禁止 command/config/service 语义键名和危险 value token |
| 2026-06-13 | runtime | local | command | 实现 Phase 3.12 isolated lab config intent package | API/UI/预检完成；`isolated_lab_config_intent_package.status=not_authorized`；所有执行、secret、配置、服务、写 API、Compose、router、生产 LAN、抓包、探测、任务消费和 boot tested 字段为 false | ready | HTTP `/`、`/boot/menu.ipxe`、两个 loader 均 200；ports 67/69/4011 observed=false desired=false；bootfile=snponly.efi；allowlist=snponly.efi/ipxe.efi |
| 2026-06-13 | network_safety_agent | 019ebfa9-a1af-75e0-95b5-e9c1d4dcccb2 | send_input/wait | Phase 3.12 实现后网络安全收口 | APPROVED，仍是只读配置意图包；未配置生成、未启动服务、未监听 UDP、未改 Compose、未改 TP-Link/OpenWrt/路由/网关/防火墙 | active | `check-phase3-gates.py`、`check-subagent-governance.sh`、`check-network-safety.sh`、`collect-release-evidence.sh`、`git diff --check` PASS；无 `__pycache__` |
| 2026-06-13 | security_audit_agent | 019ebfa9-b1d0-72a2-a551-8530b7f5f838 | send_input/wait | Phase 3.12 实现后安全收口 | APPROVED，包内无 raw command/config/service 入口；UI 仅转义展示；禁止键名与危险 value token 由预检递归覆盖 | active | 非阻断观察：旧功能里仍有 iPXE shell、菜单 enable/disable 等历史词，不属于 Phase 3.12 intent 包 |
| 2026-06-13 | git_audit_agent | 019ebfa9-b501-70d3-8eb1-953805d655dd | send_input/wait | Phase 3.12 Git/发布范围审计 | APPROVED，diff 与发布范围通过；未修改文件、未 stage、未 commit、未 push | active | 运行时 ISO、loader、archive、SQLite 仍 ignored；Phase 3.12 范围可进入后续人工选择 stage |
| 2026-06-13 | research_agent | 019ebfa9-a01e-7a43-bf2c-165de2a770dd | send_input/wait | Phase 3.13 source skeleton 协议事实预审 | APPROVED，可写不可运行离线协议模型；无需补充外部研究即可写草案，但真实服务、固件行为、TL-ER6120T 能力和生产接入前仍需再研究 | active | 只允许离线协议模型、fixture、安全断言和文档化禁用边界 |
| 2026-06-13 | project_decision_agent | 019ebfa9-a0c4-7fa0-aeb7-e09a757a8867 | send_input/wait | Phase 3.13 source skeleton 方向决策 | APPROVED，源码级默认不可运行 skeleton/offline package model 能推进最终 PXE 目标，但不授权运行、配置生成、端口开放或生产 LAN | active | 真实 isolated lab 执行、服务启动、抓包、端口开放或生产 LAN 评估必须用户手动确认并重新审查 |
| 2026-06-13 | architecture_agent | 019ebfa9-a2df-7bb3-9865-14731d1f6293 | send_input/wait | Phase 3.13 source skeleton 架构预审 | APPROVED，推荐最小源码占位、只读状态、预检断言、fixture 和文档；必须不可运行、不可生成、不可消费、不可进入生产 LAN | active | future service manifest 只能是文档化 manifest 或不可执行模型 |
| 2026-06-13 | boot_entry_agent | 019ebfa9-a4ec-74e3-ab22-5a592e797867 | send_input/wait | Phase 3.13 source skeleton 启动链路预审 | APPROVED，可表达 PXE metadata、loader scope、HTTP chain target 和 client evidence fixture；必须保持 offline、candidate、tested=false、enabled=false | active | 不得输出 DHCP/ProxyDHCP/TFTP 配置，不得声明生产 LAN 支持 |
| 2026-06-13 | network_safety_agent | 019ebfa9-a1af-75e0-95b5-e9c1d4dcccb2 | send_input/wait | Phase 3.13 source skeleton 网络安全预审 | APPROVED，仅限默认不可运行 source skeleton/offline package model；所有服务、端口、发包、抓包、探测、Compose、生产 LAN 字段必须 false | active | 预检必须保证无运行入口、无 UDP 67/69/4011、无 host network/privileged、无 TP-Link/OpenWrt 变更 |
| 2026-06-13 | security_audit_agent | 019ebfa9-b1d0-72a2-a551-8530b7f5f838 | send_input/wait | Phase 3.13 source skeleton 安全预审 | APPROVED，仅限源码草案结构、fixture、只读状态、离线包模型和审计字段展示；不得成为服务、配置生成器、命令模板或 Compose 模块 | active | 禁止 command/config/service/listener/socket/server 等语义键名和危险 value token |
| 2026-06-13 | runtime | local | command | 实现 Phase 3.13 isolated lab source skeleton package | API/UI/预检/fixture 完成；`isolated_lab_source_skeleton_package.status=not_runnable`；runtime entry arrays 均为空；所有运行、配置、服务、Compose、生产 LAN、发包、抓包、探测字段为 false | ready | HTTP `/`、`/boot/menu.ipxe`、两个 loader 均 200；ports 67/69/4011 observed=false desired=false；fixture 不可执行且无 shebang |
| 2026-06-13 | network_safety_agent | 019ebfa9-a1af-75e0-95b5-e9c1d4dcccb2 | send_input/wait | Phase 3.13 实现后网络安全收口 | APPROVED，仍是 readonly source skeleton/offline package model/fixture only；未形成运行入口、配置生成链路、服务启动链路或生产 LAN 变更路径 | active | `check-phase3-gates.py`、`check-network-safety.sh`、`collect-release-evidence.sh`、`check-subagent-governance.sh`、`git diff --check`、`node --check` PASS |
| 2026-06-13 | security_audit_agent | 019ebfa9-b1d0-72a2-a551-8530b7f5f838 | send_input/wait | Phase 3.13 实现后安全收口 | APPROVED，fixture 不可执行、无 shebang、`loaded_at_runtime=false`；没有新增写 API、服务片段、raw command、配置生成或生产 LAN 测试 | active | 非阻断观察：危险词只命中预检禁止列表、既有 API bind 默认值和历史禁止输出文案 |
| 2026-06-13 | git_audit_agent | 019ebfa9-b501-70d3-8eb1-953805d655dd | send_input/wait | Phase 3.13 Git/发布范围审计 | APPROVED，diff 与发布范围通过；未修改文件、未 stage、未 commit、未 push | active | fixture 权限 600、普通文件、不可执行；运行时 ISO/loader/archive/SQLite 仍 ignored |
| 2026-06-13 | fixed_pool | 019ebfa9-a01e-7a43-bf2c-165de2a770dd 等 11 个上轮会话 | close_agent | 按用户要求检查并关停存续 subagents | 11 个登记会话均可被工具层找到并关停，返回 previous_status；旧结论仍只能按本文档结论表引用 | closed | 不再向这些旧 id 发送任务 |
| 2026-06-13 | fixed_pool | - | spawn_failed | 尝试按 custom `agent_type` 初始化 11 个项目角色 | 11 次均返回 child model 解析失败，未产生 agent_id；不得登记为 READY 或 APPROVED | pending | 改用 default 会话显式绑定岗位 |
| 2026-06-13 | default_probe | 019ec02f-2ebe-7711-9ba9-c59fc0c7d4b3 | spawn/close | 测试 default 会话是否可创建 | default registry 可用，探测会话随后关闭 | closed | 证明失败集中在 custom `agent_type` spawn |
| 2026-06-13 | research_agent | 019ec02f-abcd-70b2-9364-cdb120d3d2a4 | spawn/wait | 固定会话池重建，研究岗位 | READY，负责外部事实、官方资料、协议、TL-ER6120T、iPXE/UEFI/PXE/HTTP Boot 研究 | active | default 会话显式绑定岗位 |
| 2026-06-13 | project_decision_agent | 019ec02f-ac76-7863-899a-3af5498ce444 | spawn/wait | 固定会话池重建，决策岗位 | READY，负责项目方向、阶段、免费/商业版边界、发布方向和重大取舍；商业代码不得进入 GitHub 免费版 push | active | default 会话显式绑定岗位 |
| 2026-06-13 | network_safety_agent | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | spawn/wait | 固定会话池重建，网络安全岗位 | READY，DHCP/ProxyDHCP/TFTP/UDP 67/69/4011、TP-Link/OpenWrt、路由、防火墙、Docker 网络变更前必须复用 | active | default 会话显式绑定岗位 |
| 2026-06-13 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | spawn/wait | 固定会话池重建，架构岗位 | READY，负责架构分层、API、数据模型、阶段边界和 PXE/HTTP Boot/ProxyDHCP/TFTP 受控集成结构 | active | default 会话显式绑定岗位 |
| 2026-06-13 | boot_entry_agent | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | spawn/wait | 固定会话池重建，启动链路岗位 | READY，负责 iPXE、menu.ipxe、UEFI HTTP/PXE IPv4、loader 和 chainload；区分 readiness 与 boot_tested | active | default 会话显式绑定岗位 |
| 2026-06-13 | storage_agent | 019ec02f-b120-7a92-9823-4e9f386c70ba | spawn/wait | 固定会话池重建，存储岗位 | READY，负责 data/images、metadata、静态 HTTP 暴露和生成物边界；避免污染用户 ISO | active | default 会话显式绑定岗位 |
| 2026-06-13 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | spawn/wait | 固定会话池重建，镜像工厂岗位 | READY，负责 ISO 准备、Ubuntu autoinstall、Windows 外部 ADK/DISM 任务模板和非破坏性镜像工厂 | active | default 会话显式绑定岗位 |
| 2026-06-13 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | spawn/wait | 固定会话池重建，Web UI 岗位 | READY，负责 Web UI、管理员体验、镜像管理、启动入口展示、只读/禁用态和未授权启动入口审查 | active | default 会话显式绑定岗位 |
| 2026-06-13 | tutorial_docs_agent | 019ec02f-b887-7c11-bb50-825e065706cb | spawn/wait | 固定会话池重建，文档岗位 | READY，负责 README、管理员教程、架构说明、安全边界、回滚、验收和未授权能力文档口径 | active | default 会话显式绑定岗位 |
| 2026-06-13 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | spawn/wait | 固定会话池重建，安全审计岗位 | READY，负责代码、脚本、Docker、Compose、路径、secret、loader provenance 和商业边界审计 | active | default 会话显式绑定岗位 |
| 2026-06-13 | git_audit_agent | 019ec02f-bd09-7520-88db-b57c0d35c296 | spawn/wait | 固定会话池重建，Git 审计岗位 | READY，负责 diff、发布范围、测试、secrets、真实镜像忽略、免费版 commit/push readiness；商业代码绝不 stage/commit/push | active | default 会话显式绑定岗位 |
| 2026-06-13 | network_safety_agent | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | send_input/wait | Phase 3.14 实现后网络安全收口 | APPROVED，无阻断项；只读手工声明门禁未启 DHCP/ProxyDHCP/TFTP，未开放 UDP 67/69/4011，未触碰 TP-Link/OpenWrt/路由/网关/防火墙/DNS | active | `check-phase3-gates.py`、`check-network-safety.sh`、`collect-release-evidence.sh`、HTTP/API smoke 和 UDP 无监听均通过 |
| 2026-06-13 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | Phase 3.14 实现后安全收口 | APPROVED，无阻断项；gate 只读、template-only，不收集/保存真实值，不新增写 API、raw command、配置片段、secret 或生产 LAN 测试入口 | active | 禁止 key/value token 由 `check-phase3-gates.py` 递归覆盖；`python_bytecode_cache=absent` |
| 2026-06-13 | git_audit_agent | 019ec02f-bd09-7520-88db-b57c0d35c296 | send_input/wait | Phase 3.14 Git/发布范围审计 | APPROVED for stage/commit preparation；免费版发布范围可整理提交；未发现商业源码、license、混淆产物进入免费版 push 范围；当前不应直接 push | active | `collect-release-evidence.sh` PASS；commercial_code_included=false；online_activation_required=false；private commercial files absent；push 前需提交并跑 push readiness |
| 2026-06-13 | runtime | local | command | 免费版整理提交 | 创建本地提交 `f7eb891 Advance free SynaBoot boot integration gates` | ready | 53 files changed；真实 ISO/loader/SQLite/.env 仍 ignored |
| 2026-06-13 | project_decision_agent | 019ec02f-ac76-7863-899a-3af5498ce444 | send_input/wait | 免费版提交 push 前方向确认 | APPROVED，允许将当前免费版提交推送到当前 GitHub 分支 | active | `check-free-push-readiness.sh` PASS；working_tree=clean_for_push；商业实现 absent |
| 2026-06-13 | runtime | local | command | 免费版 GitHub push | 成功 push `a2eed9b..f7eb891 codex/synaboot-phase1 -> codex/synaboot-phase1` | ready | remote `github.com:Flashyuan/FlashPXE.git`；商业代码未进入免费版发布范围 |
| 2026-06-13 | research_agent | 019ec02f-abcd-70b2-9364-cdb120d3d2a4 | send_input/wait | Phase 3.15 runtime authorization plan 研究预审 | APPROVED，只读授权前计划不需要新增外部研究；TL-ER6120T 能力、UEFI 行为、ProxyDHCP 边界、隔离证据和成功/失败判据保留为未来研究项 | active | 不授权 DHCP/ProxyDHCP/TFTP、UDP 67/69/4011、抓包、探测、真实配置或生产 LAN 接入 |
| 2026-06-13 | project_decision_agent | 019ec02f-ac76-7863-899a-3af5498ce444 | send_input/wait | Phase 3.15 runtime authorization plan 方向预审 | APPROVED，符合只读授权计划层方向，可进入 GitHub 免费版；不得包含商业实现、在线激活、商业端点或私有文件 | active | 基础装机免费方向保持不变 |
| 2026-06-13 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | send_input/wait | Phase 3.15 runtime authorization plan 架构预审 | APPROVED for architecture shape；仅限 `/api/boot-entry` 只读预审对象；BLOCKED for runtime/service/config/production LAN use | active | 必须保持 read model only，非授权对象，非运行时配置源 |
| 2026-06-13 | boot_entry_agent | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | send_input/wait | Phase 3.15 runtime authorization plan 启动链路预审 | APPROVED，只允许描述未来 boot path evidence 要求；不得写 observed、passed=true 或 boot_tested=true | active | evidence 覆盖 UEFI PXE IPv4、reviewed loader、HTTP menu、ready menu、无普通租约 |
| 2026-06-13 | network_safety_agent | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | send_input/wait | Phase 3.15 runtime authorization plan 网络安全预审 | APPROVED，必须保持 runtime、production LAN、DHCP/ProxyDHCP/TFTP、UDP 67/69/4011、host network、privileged、TP-Link/OpenWrt/路由/网关/防火墙/DNS 相关字段 false | active | 不触碰生产 LAN |
| 2026-06-13 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | Phase 3.15 runtime authorization plan 安全预审 | APPROVED，仅限只读模板说明；禁止真实身份、密钥凭据、原始执行、配置片段、运行启用和生产 LAN 值 | active | 预检需覆盖禁止 key/value token |
| 2026-06-13 | runtime | local | command | 实现 Phase 3.15 isolated lab runtime authorization plan | API/UI/预检完成；runtime plan `status=blocked_until_manual_facts_and_approvals`，runtime/service/config/write/production LAN/boot tested 全 false | ready | HTTP/API smoke PASS；UDP 67/69/4011 无监听；`collect-release-evidence.sh` PASS |
| 2026-06-13 | network_safety_agent | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | send_input/wait | Phase 3.15 实现后网络安全收口 | APPROVED，无阻断项 | active | `check-phase3-gates.py`、`check-network-safety.sh`、`collect-release-evidence.sh`、runtime smoke、UDP 无监听均通过 |
| 2026-06-13 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | Phase 3.15 实现后安全收口 | APPROVED，无阻断项 | active | 只读 static pre-review plan；无写 API、无配置生成、无服务启动、无 secret/raw command |
| 2026-06-13 | git_audit_agent | 019ec02f-bd09-7520-88db-b57c0d35c296 | send_input/wait | Phase 3.15 Git/发布范围审计 | APPROVED for free-edition stage/commit preparation；未发现商业代码、license、混淆产物或真实镜像误入 push 范围 | active | 4 个文件变更；`collect-release-evidence.sh` PASS；商业实现 absent |
| 2026-06-13 | runtime | local | command | Phase 3.15 免费版整理提交 | 创建本地提交 `c8043c4 Add isolated lab runtime authorization plan` | ready | 6 files changed；真实 ISO/loader/SQLite/.env 仍 ignored |
| 2026-06-13 | project_decision_agent | 019ec02f-ac76-7863-899a-3af5498ce444 | send_input/wait | Phase 3.15 免费版提交 push 前方向确认 | APPROVED，允许将当前免费版提交推送到当前 GitHub 分支 | active | `check-free-push-readiness.sh` PASS；working_tree=clean_for_push；商业实现 absent |
| 2026-06-13 | runtime | local | command | Phase 3.15 免费版 GitHub push | 成功 push `25088b1..c8043c4 codex/synaboot-phase1 -> codex/synaboot-phase1` | ready | 商业代码未进入免费版发布范围 |

## 6. 协作统计与压缩恢复快照

该表是上下文压缩后的第一恢复入口。主控恢复工作时必须先看本表，再根据
“操作流水表”和“结论与进度表”核对细节；不得只凭压缩摘要声称某个 agent
曾经批准、阻断或完成过某项工作。

| role | agent_id | 当前状态 | 流水记录数 | 最近主题 | 当前进度 | 后续复用规则 |
| --- | --- | --- | --- | --- | --- | --- |
| research_agent | 019ec02f-abcd-70b2-9364-cdb120d3d2a4 | active | 2 | Phase 3.15 runtime authorization plan 研究预审 | APPROVED，只读授权前计划不需要新增外部研究；真实 runtime 前仍需研究 TL-ER6120T、UEFI、ProxyDHCP、隔离证据和成功/失败判据 | 仅在 TL-ER6120T、iPXE/UEFI、协议或外部资料不确定时复用 |
| project_decision_agent | 019ec02f-ac76-7863-899a-3af5498ce444 | active | 4 | Phase 3.15 免费版提交 push 前方向确认 | APPROVED，允许将当前免费版提交推送到当前 GitHub 分支；商业代码仍不得进入 GitHub 免费版 push | 仅在阶段、收费边界、发布方向、商业边界或重大取舍时复用 |
| network_safety_agent | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | active | 4 | Phase 3.15 实现后网络安全收口 | APPROVED，无阻断项；runtime authorization plan 未启 DHCP/ProxyDHCP/TFTP、未开放 UDP、未触碰 TP-Link/OpenWrt/路由/网关/防火墙/DNS | 触及 Compose 网络、端口、DHCP、ProxyDHCP、TFTP、路由或网关时必须复用 |
| architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | active | 2 | Phase 3.15 runtime authorization plan 架构预审 | APPROVED for architecture shape；只读预审对象，不是授权对象、运行时配置源或服务入口 | 改 API、数据模型、阶段边界或受控 PXE 集成结构时复用 |
| boot_entry_agent | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | active | 2 | Phase 3.15 runtime authorization plan 启动链路预审 | APPROVED，只允许描述未来 boot path evidence 要求；不得写 observed、passed=true 或 boot_tested=true | 改 menu.ipxe、boot assets、loader、PXE/HTTP Boot 链路时复用 |
| storage_agent | 019ec02f-b120-7a92-9823-4e9f386c70ba | active | 1 | 固定会话池重建 | READY，负责 data/images、metadata、静态 HTTP 暴露和生成物边界；避免污染用户 ISO | 改镜像扫描、元数据、静态路径、ISO 派生文件边界时复用 |
| image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | active | 1 | 固定会话池重建 | READY，负责 ISO 准备、Ubuntu autoinstall、Windows 外部 ADK/DISM 任务模板和非破坏性镜像工厂 | 改 ISO 准备、autoinstall、任务包或镜像制作流程时复用 |
| webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | active | 1 | 固定会话池重建 | READY，负责 Web UI、管理员体验、镜像管理、启动入口展示、只读/禁用态和未授权启动入口审查 | 改管理员 UI、镜像管理体验、状态展示时复用 |
| tutorial_docs_agent | 019ec02f-b887-7c11-bb50-825e065706cb | active | 1 | 固定会话池重建 | READY，负责 README、管理员教程、架构说明、安全边界、回滚、验收和未授权能力文档口径 | 改教程、交接说明、验收记录时复用 |
| security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | active | 4 | Phase 3.15 实现后安全收口 | APPROVED，无阻断项；只读 static pre-review plan，无写 API、无配置生成、无服务启动、无 secret/raw command | 改路径、权限、脚本执行、Docker、安全边界或商业边界时复用 |
| git_audit_agent | 019ec02f-bd09-7520-88db-b57c0d35c296 | active | 3 | Phase 3.15 Git/发布范围审计 | APPROVED for free-edition stage/commit preparation；未发现商业代码、license、混淆产物或真实镜像误入 push 范围 | milestone 收口、stage/commit/push 前必须复用 |

统计规则：

- “流水记录数”只统计当前 active agent_id 的已登记通信，不把 stale 历史会话混入。
- 若后续追加操作流水，必须同步更新本表的最近主题、当前进度和流水记录数。
- 如果工具层恢复失败，先把对应状态改为 `stale` 并记录流水，再决定是否替换该角色。
- 对未在本表或“结论与进度表”出现的结论，不得在压缩恢复后当成已验证事实引用。

## 7. 结论与进度表

该表用于压缩上下文后快速恢复“哪些结论可引用、哪些不能引用”。

| milestone / topic | roles involved | latest conclusion | reusable evidence | remaining risk |
| --- | --- | --- | --- | --- |
| Phase 2.10 ISO 准备任务 | security_audit_agent | Ubuntu 解包 symlink 风险已修复并 PASS | `prepare.sh` 校验存在、非 symlink、普通文件；`collect-release-evidence.sh` 通过 | 真实执行 prepare.sh 前仍需管理员审查任务包 |
| Phase 2.11 真实 ISO smoke | security_audit_agent | smoke 脚本 PASS；Ubuntu 启动依赖准备后 Linux ISO 已进入菜单，HotPE/Windows raw ISO 仍未直接进菜单 | `check-real-iso-smoke.sh` 实测 `image_count=8`、`iso_count=4`、`ready_count=6` | 保留服务需显式 `SYNABOOT_SMOKE_KEEP_RUNNING=1` |
| Phase 2.12 自动安装边界 | 本地机器门禁 | 已新增只读边界门禁，subagent 复核因工具层失败未完成 | `check-autoinstall-boundary.sh` 与 `collect-release-evidence.sh` 通过 | 下一次固定会话池可用后应补 security/git 语义复核 |
| Phase 3 UEFI PXE IPv4 固定会话池 | 11 个固定岗位 | 已按用户要求关停上轮 11 个存续会话；直接按 custom `agent_type` 重建仍因 child model 解析失败未创建会话；default 探测成功后已重建 11 个 active default 会话并显式绑定岗位 | 本文档当前会话登记表；11 个新岗位 READY；旧会话 `close_agent` 均返回 previous_status；custom `agent_type` 失败无 agent_id，不登记为 READY | 后续必须复用当前 default role sessions；不得再向上轮旧 id 发送任务；不得把 custom `agent_type` 失败说成成功 |
| Phase 3 PXE IPv4 只读规划门禁 | research_agent、project_decision_agent、network_safety_agent、architecture_agent、boot_entry_agent、security_audit_agent | 批准只读规划与隔离验证准备；禁止直接在生产 LAN 启用 DHCP/ProxyDHCP/TFTP 或开放 UDP 67/69/4011 | 6 个固定岗位本轮 `send_input/wait` 结论；`check-subagent-governance.sh` 与 `collect-release-evidence.sh` 通过 | TL-ER6120T 能力、UEFI 客户端兼容性、Secure Boot、隔离抓包验证尚未完成 |
| Phase 3.5 隔离验证计划只读化 | architecture_agent、network_safety_agent、security_audit_agent、project_decision_agent | 批准实现 `isolated_validation_plan` API/UI/预检只读字段；字段必须证明 runtime 未启用、生产 LAN 禁止、UDP 端口未开放、主 DHCP/网关不变量不变 | 4 个固定岗位本轮 `send_input/wait` 结论；`check-phase3-gates.py`、`check-network-safety.sh` 通过 | 仍未进行隔离实验；真实 ProxyDHCP/TFTP 实现和生产 PXE 接入仍 blocked |
| Phase 3.5 PXE IPv4 readiness 只读证据 | boot_entry_agent、network_safety_agent、storage_agent、security_audit_agent | 批准实现 `pxe_ipv4_readiness` API/UI/预检只读字段；当前本地快照显示 source ISO=4、ready 菜单项=6、snponly.efi/ipxe.efi 均 missing | 4 个固定岗位本轮 `send_input/wait` 结论；本地 `boot_entry_status()` smoke；`check-phase3-gates.py` 通过 | 需补齐受审查 loader 后才可能进入隔离实验评审；Phase 3 门禁仍 blocked |
| Phase 3.5 PXE IPv4 readiness Git 审计修复 | git_audit_agent | 首轮 BLOCKED 的 metadata 写入风险已修复并通过复审：readiness 不再调用 `list_images()`，只用 SQLite readonly snapshot，缺失时安全返回 unavailable | 空 metadata 临时目录 smoke 未创建 SQLite；root-owned DB readonly snapshot 读取 source ISO=4；`check-phase3-gates.py` 与 `collect-release-evidence.sh` 通过；git_audit_agent 复审 APPROVED | 仍需全量 diff 发布范围审计；当前工作区包含多轮历史改动 |
| Phase 2/3 Linux ISO 启动依赖准备 | image_factory_agent、security_audit_agent、boot_entry_agent、git_audit_agent | 已新增 stdlib `extract-iso9660-file.py` 并接入 `prepare-linux-boot-artifacts.sh` fallback；Ubuntu 22.04.3/24.04 已成功提取 `casper/vmlinuz` 与 `casper/initrd`；首轮 Git 审计发现父路径 symlink 风险，已补强 canonical 校验和 rm 前边界检查并通过复审；安全审计建议已固化为 `check-iso-extractor-safety.sh` 并通过最终 Git 复审 | `bash -n` 通过；单文件提取 smoke 通过；真实批量提取完成；symlink smoke 覆盖 data/images、data/builds、hash work 目录均 BLOCKED；`check-real-iso-smoke.sh` 实测 `ready_count=6`；`collect-release-evidence.sh` 包含 ISO extractor safety preflight 并通过；git_audit_agent 最终复审 APPROVED | 仍需补齐受审查 `snponly.efi` 或 `ipxe.efi`；Phase 3 生产 LAN/PXE 服务启用仍 blocked；后续可增强目录 extent 大小上限 |
| Phase 3.6 loader 本地导入与 provenance | boot_entry_agent、security_audit_agent、git_audit_agent | 已新增本地 loader 导入脚本和 provenance 读取逻辑；导入必须固定白名单、同 fd 校验、`O_EXCL` 不覆盖、记录 SHA256/来源/Phase 3 blocked/网络服务禁用状态；API 只有 provenance 完整且 SHA256 匹配时才标记 `reviewed_for_lab`；Git 审计通过但未提交 | `check-loader-import-safety.sh` 通过并接入 `collect-release-evidence.sh`；`check-network-safety.sh` 通过；`check-phase3-gates.py` 通过；`collect-release-evidence.sh` 通过；假 EFI 导入被 BLOCKED；API 当前 `reviewed_for_lab=[]`、`lab_prerequisites_met=false`；git_audit_agent APPROVED | 真实 `snponly.efi` 或 `ipxe.efi` 尚未由管理员导入；导入后仍需隔离实验和 Phase 3 门禁授权 |
| Phase 3.7 iPXE 官方来源与本地归档导入 | research_agent、network_safety_agent、security_audit_agent、git_audit_agent | 已记录官方 iPXE 来源和 Secure Boot 风险；新增 `import-ipxe-archive.py`，只从本地 `ipxeboot.tar.gz` 或等价归档中流式读取固定白名单成员，复用单文件导入校验和 provenance；脚本不联网、不下载、不执行、不整包解压、不启网络服务；network_safety 仅批准本地准备保留；Git 审计复审通过但未提交 | `docs/IPXE_LOADER_SOURCES.md`；`check-loader-import-safety.sh` PASS；`check-network-safety.sh` PASS；坏 tar 缺少 `snponly.efi` 时 BLOCKED；security_audit_agent 复审 APPROVED；network_safety_agent APPROVED；git_audit_agent APPROVED；`collect-release-evidence.sh` PASS | 真实 loader 导入已在 Phase 3.8 完成；生产 LAN DHCP/ProxyDHCP/TFTP/UDP 启用仍禁止；TL-ER6120T DHCP/PXE 能力仍需确认 |
| Phase 3.8 reviewed UEFI loader 已导入 | project_decision_agent、network_safety_agent、security_audit_agent、git_audit_agent | 已从官方 iPXE GitHub release 下载 `ipxeboot.tar.gz` 到 ignored runtime，并导入 `snponly.efi` 与 `ipxe.efi`；两个 loader 均 `usable=true`、`reviewed_for_lab=true`、`sha256_matches=true`；HTTP `/boot/menu.ipxe`、`/boot/loaders/snponly.efi`、`/boot/loaders/ipxe.efi` 均 200；API `lab_prerequisites_met=true`；Git 审计通过但未提交 | archive SHA256 `01a526d4cc791fc30362259c609d6c506cc64a7bdff51b9a5eb788354e17eee1`；`snponly.efi` SHA256 `b1e67c3e4a1e8708ddfd0079ad4505e3a02245acb55ee9a95437ab3c507be82a`；`ipxe.efi` SHA256 `6558e37887516b246d6a97122e8d18bedfe4197b7ba7f67bf1bf102a16678d33`；UDP 67/69/4011 未监听；security/network/git 复核 APPROVED | `pxe_ipv4_readiness.status=blocked_by_phase3_gate`；`runtime_enabled=false`；`boot_tested=false`；尚未启用或验证生产 LAN UEFI PXE IPv4 自动启动 |
| Phase 3.9 PXE 隔离实验 Boot Metadata 只读规划 | project_decision_agent、boot_entry_agent、network_safety_agent、security_audit_agent | 批准实现 `pxe_lab_boot_metadata_plan` 只读结构；可展示未来隔离实验候选 bootfile、fallback、TFTP root、HTTP menu URL、allowed/forbidden TFTP 文件、ProxyDHCP 元数据边界、禁止 DHCP 字段、抓包证据和回滚检查；不得生成配置、执行命令、启动服务或进入生产 LAN | 4 个固定岗位本轮 `send_input/wait` 结论；`check-phase3-gates.py`、`check-network-safety.sh`、`collect-release-evidence.sh`、HTTP 200 smoke 均通过；API 字段保持 `operation_allowed=false`、`service_enablement_allowed=false`、`runtime_enabled=false`、`production_lan_allowed=false`、`config_generation_allowed=false`、`command_execution_allowed=false` | 仍缺真实隔离实验、抓包证据和 UEFI 客户端启动验证；生产 LAN DHCP/ProxyDHCP/TFTP/UDP 启用仍 blocked；还需 `git_audit_agent` 对本轮最终 diff 做发布范围审计 |
| Phase 3.10 isolated-lab boot services disabled skeleton | architecture_agent、boot_entry_agent、network_safety_agent、security_audit_agent、project_decision_agent、git_audit_agent | 已实现 `isolated_lab_boot_services_disabled_skeleton` API/UI/预检禁用骨架；它只表达未来隔离实验服务候选、loader allowlist、HTTP menu reference target、客户端证据模板、失败模式、回滚计划和 gates；`service_profiles` 只包含 disabled `proxy_dhcp_metadata_only` 与 `tftp_loader_only`，HTTP menu 仅在 `reference_targets`；未修改 Compose，未启动服务，未开放 UDP，未生成配置 | 5 个固定岗位预审 APPROVED；network_safety/security/git 收口 APPROVED；`check-phase3-gates.py` PASS；`collect-release-evidence.sh` PASS；`git diff --check` PASS；HTTP `/`、`/boot/menu.ipxe`、`/boot/loaders/snponly.efi`、`/boot/loaders/ipxe.efi` 均 200；API skeleton 所有执行/服务/生产 LAN gate 为 false；UDP 67/69/4011 无监听；`python_bytecode_cache=absent` | 真实 UEFI PXE IPv4 自动启动仍未完成；下一阶段若进入隔离实验服务实现或运行，必须重新触发 research/network_safety/security/project_decision；生产 LAN DHCP/ProxyDHCP/TFTP/UDP 启用仍 blocked |
| Phase 3.11 isolated lab evidence package | project_decision_agent、architecture_agent、boot_entry_agent、network_safety_agent、security_audit_agent、git_audit_agent | 已实现 `isolated_lab_evidence_package` API/UI/预检只读证据包；它只汇总 HTTP menu、reviewed loader、ready images、UDP 端口只读证据、disabled skeleton gate、人工隔离实验声明、客户端证据模板和授权草案；`status=not_authorized`，`authorization_request.status=draft_not_authorized`，所有执行、secret、配置、服务、生产 LAN、抓包和探测字段为 false | 5 个固定岗位预审 APPROVED；network_safety/security 收口 APPROVED；git_audit_agent 对代码与发布范围曾 APPROVED，台账更新后的追加复审返回空输出，不能登记为新批准；`check-subagent-governance.sh` PASS；`check-phase3-gates.py` PASS；`check-network-safety.sh` PASS；`collect-release-evidence.sh` PASS；`git diff --check` PASS；HTTP `/`、`/boot/menu.ipxe`、`/boot/loaders/snponly.efi`、`/boot/loaders/ipxe.efi` 均 200；API `evidence_checks` 全 passed，ready_entries=6，UDP 67/69/4011 无监听，`python_bytecode_cache=absent` | 真实 UEFI PXE IPv4 自动启动仍未完成；证据包不是实验授权或生产 LAN 授权；下一阶段若进入隔离实验服务实现、运行、抓包或生产 LAN 接入，必须重新触发 research/network_safety/security/project_decision 并取得用户手动确认；发布前需复用 git_audit_agent 获取明确 APPROVED/BLOCKED |
| Phase 3.12 isolated lab config intent package | project_decision_agent、architecture_agent、boot_entry_agent、network_safety_agent、security_audit_agent、git_audit_agent | 已实现 `isolated_lab_config_intent_package` API/UI/预检只读配置意图包；它只表达未来单机隔离实验的 dry-run intent：候选服务意图、端口意图、candidate bootfile、reviewed loader allowlist、HTTP chain target、客户端验证清单、人工授权门禁和回滚触发；`status=not_authorized`，`request_is_authorization=false`，所有执行、secret、配置生成、命令执行、服务启动、写 API、Compose、router、生产 LAN、抓包、探测、任务消费和 boot tested 字段为 false | 5 个固定岗位预审 APPROVED；network_safety/security/git 收口 APPROVED；`check-subagent-governance.sh` PASS；`check-phase3-gates.py` PASS；`check-network-safety.sh` PASS；`collect-release-evidence.sh` PASS；`git diff --check` PASS；`node --check apps/web/assets/app.js` PASS；HTTP `/`、`/boot/menu.ipxe`、`/boot/loaders/snponly.efi`、`/boot/loaders/ipxe.efi` 均 200；API `ports=67:False:False,69:False:False,4011:False:False`，`bootfile=snponly.efi`，allowlist 为 `snponly.efi,ipxe.efi`；UDP 67/69/4011 无监听；`python_bytecode_cache=absent` | 真实 UEFI PXE IPv4 自动启动仍未完成；配置意图包不是实验授权、配置生成器或生产 LAN 授权；下一阶段若进入真实 isolated lab runtime、抓包、服务实现、端口开放或生产 LAN 接入，必须重新触发 research/network_safety/security/project_decision 并取得用户手动确认 |
| Phase 3.13 isolated lab source skeleton package | research_agent、project_decision_agent、architecture_agent、boot_entry_agent、network_safety_agent、security_audit_agent、git_audit_agent | 已实现 `isolated_lab_source_skeleton_package` API/UI/预检只读源码骨架与离线 fixture 模型；它只表达未来单机隔离实验的协议模型、boot metadata 模型、loader transfer scope、HTTP chain target、client evidence fixture 和授权门禁；`status=not_runnable`、`fixture_only=true`、`offline_package_only=true`，runtime entry arrays 均为空，所有运行、配置、服务、Compose、生产 LAN、发包、抓包、探测字段为 false | 6 个固定岗位预审 APPROVED；network_safety/security/git 收口 APPROVED；`check-subagent-governance.sh` PASS；`check-phase3-gates.py` PASS；`check-network-safety.sh` PASS；`collect-release-evidence.sh` PASS；`git diff --check` PASS；`node --check apps/web/assets/app.js` PASS；HTTP `/`、`/boot/menu.ipxe`、`/boot/loaders/snponly.efi`、`/boot/loaders/ipxe.efi` 均 200；API `status=not_runnable`、empty runtime arrays、`ports=67:False:False,69:False:False,4011:False:False`；fixture `config/synaboot/phase3.13-isolated-lab-source-skeleton.disabled.json` 不可执行、无 shebang、`loaded_at_runtime=false`；UDP 67/69/4011 无监听；`python_bytecode_cache=absent` | 真实 UEFI PXE IPv4 自动启动仍未完成；source skeleton 不是可运行服务、配置生成器、Compose 模块或生产 LAN 授权；下一阶段若进入 runtime 设计、真实 isolated lab 客户端交互、抓包、服务启动、端口开放或生产 LAN 接入，必须重新触发 research/network_safety/security/project_decision 并取得用户手动确认 |
| Phase 3.14 isolated lab manual declaration gate | network_safety_agent、security_audit_agent、git_audit_agent、project_decision_agent | 已实现 `isolated_lab_manual_declaration_gate` API/UI/预检只读手工声明门禁；它只表达进入真实 isolated lab runtime 前必须人工确认的事实模板；`status=missing_facts`、`submission_status=not_submitted`、`authorization_status=not_authorized`、`read_only=true`、`template_only=true`，不收集、不保存真实客户端或实验环境值，不新增写 API，不解锁 runtime | network_safety/security 收口 APPROVED；git_audit_agent APPROVED for stage/commit preparation；project_decision_agent APPROVED push；`check-free-push-readiness.sh` PASS；本地提交 `f7eb891` 已 push 到 GitHub 免费版分支；`check-phase3-gates.py`、`check-network-safety.sh`、`check-subagent-governance.sh`、`check-compose-config-safe.sh`、`collect-release-evidence.sh`、`node --check`、HTTP/API smoke 均 PASS；UDP 67/69/4011 无监听；`python_bytecode_cache=absent` | 真实 UEFI PXE IPv4 自动启动仍未完成；manual declaration gate 不是用户提交、实验授权、配置生成器、服务启动入口或生产 LAN 授权；下一阶段仍需 isolated lab runtime 设计与人工实验确认 |
| Phase 3.15 isolated lab runtime authorization plan | research_agent、project_decision_agent、architecture_agent、boot_entry_agent、network_safety_agent、security_audit_agent、git_audit_agent | 已实现 `isolated_lab_runtime_authorization_plan` API/UI/预检只读 runtime 授权前计划；它只表达未来进入 isolated lab runtime 前必须满足的审批、范围、证据、回滚和研究缺口；`status=blocked_until_manual_facts_and_approvals`、`read_only=true`，runtime/service/config/write/production LAN/boot tested 均为 false | 6 个固定岗位预审 APPROVED；network_safety/security/git 收口 APPROVED；project_decision_agent APPROVED push；`check-free-push-readiness.sh` PASS；本地提交 `c8043c4` 已 push 到 GitHub 免费版分支；`check-phase3-gates.py`、`check-network-safety.sh`、`check-subagent-governance.sh`、`check-compose-config-safe.sh`、`collect-release-evidence.sh`、`node --check`、HTTP/API smoke 均 PASS；API `missing=9`、`approvals=5`、`evidence=5`；UDP 67/69/4011 无监听；`python_bytecode_cache=absent` | 真实 UEFI PXE IPv4 自动启动仍未完成；runtime authorization plan 不是授权结果、配置源、服务启动入口或生产 LAN 许可；下一阶段若进入真实授权对象或服务实现，必须重新触发 research/network_safety/security/project_decision 并取得用户手动确认 |

## 8. 上下文压缩交接规则

发生上下文压缩、线程恢复或工具状态变化后，主控必须：

1. 先读取本文件。
2. 先看“协作统计与压缩恢复快照”，确认每个 role 的 agent_id、状态、
   最近主题和当前进度。
3. 不凭记忆声称某个 subagent 仍然 active。
4. 对需要继续使用的 agent_id 执行轻量握手或恢复。
5. 成功后把状态改为 `active`；失败后改为 `stale` 并记录流水。
6. 只引用“结论与进度表”中有 evidence 的结论。
7. 对标记为“subagent 复核未完成”的事项，不得说成已完成审计。
8. 每次新增或复用 subagent 通信后，必须同步更新“操作流水表”和
   “协作统计与压缩恢复快照”。

## 9. 重建条件

只有以下情况允许替换某个角色会话：

- 工具层明确返回 `agent not found`。
- 会话无法恢复或无法接收 `send_input`。
- 该 agent 的回答明显偏离角色职责或不具备参考意义。
- 用户明确要求重建。

替换时只替换对应角色，不批量新开无关角色。
