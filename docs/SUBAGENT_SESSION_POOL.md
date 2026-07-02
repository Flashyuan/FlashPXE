# SynaBoot Subagent 固定会话池与协作台账

本文档用于记录当前 milestone 的 subagent 会话池、协作操作和长期记忆。

目标不是把 subagent 当一次性 reviewer，而是把 11 个角色当成可持续协作岗位。
上下文压缩、会话恢复或工具 registry 失效后，主控必须先读取本文档，再继续
协作，避免凭记忆复述旧结论。

## 0. 长期记忆字段要求

本文档是 subagent 协作的长期记忆源。上下文压缩、线程恢复、工具 registry
重置或主控切换后，不能只依赖聊天摘要判断 subagent 曾经说过什么。

### 0.0 协作统计表契约

“协作统计与压缩恢复快照”是恢复 subagent 状态的主表，必须长期保留并持续
更新。该表不是普通说明文字，而是上下文压缩后的恢复契约。

每一行必须能回答 4 个问题：

- 这个岗位是谁：`role`、`agent_id`、`status`。
- 它做过什么：`operation_log` 对应的流水记录数和最近主题。
- 它现在推进到哪里：`progress` 和仍然存在的阻断点。
- 下次怎么复用：`reusable_conclusion` 和 `next_reuse_rule`。

如果某个 subagent 回复没有进入“操作流水表”和“协作统计与压缩恢复快照”，
压缩恢复后不得把它当作已批准、已完成、已阻断或已复用的事实。

统计表更新规则：

- 每次 `send_input`、`wait`、超时、空输出、`agent not found`、重建、关闭、
  审计批准或审计阻断后，都必须更新对应行。
- “流水记录数”必须与当前 active `agent_id` 的有效登记记录相匹配。
- `progress` 必须写清楚当前阶段结论，不能只写 `READY`、`OK` 或 `DONE`。
- `reusable_conclusion` 只能引用“结论与进度表”中有证据的内容。
- `next_reuse_rule` 必须说明下次触发条件，用来防止遇到小问题就新开会话。

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
- 2026-06-16 SMB/CIFS livefs 任务中，主控没有按本文档先复用登记的
  `security_audit_agent`，而是连续创建多个 default 安全审计会话处理同一轮
  BLOCKED 修复。这些会话的结论可以作为本次任务证据，但不得成为新的固定池
  会话；下次同职责审计必须先对登记会话做握手/恢复，失败后只替换一次。

## 2. 固定会话池启动协议

每个 milestone 开始时执行：

1. 读取上轮登记表。
2. 读取对应 `.codex/agents/<role>.toml`，确认岗位职责仍匹配本次任务。
3. 对已有 agent id 先尝试恢复或发送轻量握手。
4. 可通信的会话标记为 `active` 并继续复用。
5. `agent not found`、无法恢复或明显跑偏的会话标记为 `stale`。
6. 工具层 spawn 正常时，按 11 个项目角色建立固定会话池。
7. 固定会话池建立后，本 milestone 只向登记会话发送任务。
8. 若工具层无法建立固定会话池，暂停 subagent 调用并向用户报告。

### 2.1 固定岗位与旧会话确认协议

每次调用 subagent 前必须先构造岗位信封：

```text
role: <固定岗位名>
agent_id: <登记会话 id>
topic: <本次主题>
scope: <希望该岗位审查/设计的边界>
non_goals: <明确不让该岗位处理的内容>
expected_output: <需要的结论格式>
source_docs: <PLAN.md/docs/代码路径/验证结果>
```

岗位信封必须满足：

- `role` 必须与 `.codex/agents/<role>.toml` 中的 `name` 一致。
- 不得把 `security_audit_agent` 会话当作 `network_safety_agent` 使用。
- 不得把 `webui_agent` 会话当作 `architecture_agent` 使用。
- 不得因为旧会话已经返回过 `APPROVED`、`PASS`、`BLOCKED` 或 `completed`
  就把它视为一次性会话丢弃。
- 若发现岗位串位，该次回复不得作为有效结论引用，必须在流水中标记
  `invalid_role_context`。

旧会话恢复必须至少经过三步确认，除非工具层直接返回明确的不可恢复错误：

1. `resume_agent` 或等价恢复动作。
2. 发送轻量握手，确认对方仍按登记岗位回答。
3. 发送带岗位信封的实际任务。

如果第 1 步或第 2 步超时，应记录流水并至少再尝试一次轻量恢复；连续失败后才可
标记 `stale`。如果工具层明确返回 `agent not found`，可立即标记 `stale`，但仍
必须记录旧 `agent_id`、失败原因和替换理由。

替换规则：

- 每个岗位同一 milestone 内最多替换一次。
- 替换后的新会话必须继承同一 `role`，不得改变岗位职责。
- 替换前必须在操作流水中记录旧会话不可用证据。
- 替换后必须更新“角色岗位总表”“当前会话登记表”和“协作统计与压缩恢复快照”。

BLOCKED 复审规则：

```text
同一 agent_id 返回 BLOCKED
  → 主控修复
  → 汇总 diff、验证命令、修复说明
  → send_input 回同一 agent_id
  → 只有旧会话确认 stale，才按同岗位替换一次
```

这条规则优先级高于“完成后关闭 reviewer”的旧习惯。

## 3. 角色岗位总表

| role | 固定职责 | 触发条件 | 当前状态 | 当前 agent_id | 备注 |
| --- | --- | --- | --- | --- | --- |
| research_agent | 外部事实、协议、设备能力和资料证据 | 外部事实不确定、Phase 3 前置调查 | active | 019ec02f-abcd-70b2-9364-cdb120d3d2a4 | 2026-06-23 Windows 企业统一装机/软件部署模型调研 PASS |
| project_decision_agent | 方向、阶段、收费边界和取舍决策 | 影响路线、商业边界、发布方向 | active | 019ec02f-ac76-7863-899a-3af5498ce444 | 只处理方向、阶段、收费边界和重大取舍 |
| network_safety_agent | LAN 零侵入和网络启动安全边界 | Compose 网络、端口、DHCP/ProxyDHCP/TFTP、路由、防火墙 | active | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | 2026-07-02 HotPE AutoMount 本身可接受；宿主 UDP 67/69/4011 监听阻断 release 级网络门禁 |
| architecture_agent | 架构、数据模型、API 和阶段边界 | 模型/接口/阶段设计变化 | active | 019ec02f-adf7-7162-8721-3b127ac3e51f | 2026-06-23 Windows 默认 Office 2021 与 Feishu env-gated deb 架构复审 PASS |
| boot_entry_agent | iPXE/HTTP Boot/PXE/启动菜单链路 | 启动菜单、boot assets、Phase 3 入口 | active | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | 2026-06-20 passive wait postinstall 计划领取启动链路复审 PASS |
| storage_agent | 镜像仓库、扫描、元数据、静态文件 | ISO/WIM/文件扫描和仓库状态 | active | 019ec02f-b120-7a92-9823-4e9f386c70ba | 保持镜像仓库和生成物边界 |
| image_factory_agent | 镜像准备任务、模板和任务包 | ISO 准备、autoinstall 模板、任务框架 | active | 019ec02f-b31a-7cb0-a544-314d1092e227 | 2026-07-02 HotPE AutoMount 镜像工厂复审 PASS |
| webui_agent | Web UI 和管理员体验 | 页面、交互、状态展示；应用 design-review、design-taste-frontend、frontend-design、shadcn-ui、tailwind-design-system 作为 UI 重构检查框架 | active | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | 2026-06-20 软件市场受控静默参数与软件选择 UI 复审 PASS |
| tutorial_docs_agent | 文档、教程、操作说明和交接材料 | README/指南/验收记录 | active | 019ec02f-b887-7c11-bb50-825e065706cb | 文档覆盖隔离验证、回滚和用户流程 |
| security_audit_agent | 安全、路径、命令、Docker、secret 边界 | 安全/发布边界、脚本、输入输出 | active | 019ec02f-baba-7832-bc4a-ed9d8d696048 | 2026-07-02 HotPE AutoMount CMD 密码字符修复后复审 PASS |
| git_audit_agent | diff、发布范围、commit/push 就绪 | milestone 收口、commit/push 前 | active | 019ec02f-bd09-7520-88db-b57c0d35c296 | 免费版 commit/push readiness；商业代码绝不 push |

状态枚举：

- `pending`：本 milestone 尚未建立或握手。
- `active`：工具层可通信，可继续 `send_input`。
- `needs_recheck`：台账登记的固定会话仍是优先复用对象，但下次发送任务前
  必须先 `resume_agent`/握手确认；若不可达，再登记 stale 并只替换一次。
- `stale`：UI 可能仍显示，但工具层 `agent not found` 或不可恢复。
- `blocked`：agent 返回 BLOCKED，等待主控修复并回传同一会话。
- `closed`：milestone 收口后主动关闭。

## 4. 当前会话登记表

```text
milestone: Phase 3 UEFI PXE IPv4 Boot 受控规划与免费版发布线
started_at: 2026-06-13
last_verified_at: 2026-06-13

role                         agent_id  status   note
research_agent               019ec02f-abcd-70b2-9364-cdb120d3d2a4  active  2026-06-23 Windows 企业统一装机/软件部署模型调研 PASS
project_decision_agent        019ec02f-ac76-7863-899a-3af5498ce444  active  READY
network_safety_agent          019ec02f-ad02-7ae0-8c00-c7baeb46709e  active  2026-07-03 dnsmasq 停止后 release 网络门禁 APPROVED
architecture_agent            019ec02f-adf7-7162-8721-3b127ac3e51f  active  2026-07-03 install automation 整合包架构复审 APPROVED
boot_entry_agent              019ec02f-aedd-78d0-b7ac-efb3f69b6791  active  2026-06-20 passive wait postinstall 计划领取启动链路复审 PASS
storage_agent                 019ec02f-b120-7a92-9823-4e9f386c70ba  active  READY
image_factory_agent           019ec02f-b31a-7cb0-a544-314d1092e227  active  2026-07-02 HotPE AutoMount 镜像工厂复审 PASS
webui_agent                   019ec02f-b56a-7f83-aa03-0c45c88e8e4b  active  2026-06-20 软件市场受控静默参数与软件选择 UI 复审 PASS
tutorial_docs_agent           019ec02f-b887-7c11-bb50-825e065706cb  active  READY
security_audit_agent          019ec02f-baba-7832-bc4a-ed9d8d696048  active  2026-07-03 release evidence 通过后安全复审 APPROVED
git_audit_agent               019ec02f-bd09-7520-88db-b57c0d35c296  active  2026-07-03 install automation 整合 commit/push 审计 APPROVED
```

## 5. 操作流水表

每次向 subagent 发送任务、收到结论、标记 stale、重建会话或关闭会话，都必须
追加一条流水。流水只记录摘要，不记录 token、私有源码、ISO 内容、license
或客户数据。

| time | role | agent_id | action | input_summary | output_summary | status_after | evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-07-02 | network_safety_agent | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | resume/send_input/wait | HotPE AutoMount 实验实现最终网络安全复审 | BLOCKED；本轮实现未新增 LAN、DHCP、ProxyDHCP、TFTP、路由、防火墙或主 Compose SMB 风险，但宿主当前仍有 UDP `67/69/4011` 监听，release 级网络安全门禁不能完整通过 | active | `check-hotpe-automount-safety.sh` PASS；`check-network-safety.sh` 因宿主 UDP 监听 BLOCKED |
| 2026-07-02 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | resume/send_input/wait | HotPE AutoMount 生成器、运行态脚本和 HPM 白名单加载复审 | PASS；含密产物不进 `data/images/**`，不改 `boot.wim`/BCD/wimboot/源 ISO，不触碰 Ubuntu/NFS，不把 SMB 当软件市场分发源；真实 HotPE 仍需验证 HPM 双击/打开行为 | active | `check-hotpe-automount-safety.sh`、`py_compile`、`git diff --check` PASS；manifest `module_count=9` |
| 2026-07-02 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | HotPE AutoMount 安全复审，检查 secret、路径、危险命令和 CMD 注入 | 初审 BLOCKED：SMB 密码未拒绝 `%`、`!`、`"`；已修复 `SAFE_PASSWORD_RE` 并加入 bad password fail-closed 预检；复审 APPROVED，无剩余必须修复项 | active | `check-hotpe-automount-safety.sh`、`py_compile`、`git diff --check` PASS；公开 AutoMount 目录无密码泄漏 |
| 2026-07-02 | git_audit_agent | 019ec02f-bd09-7520-88db-b57c0d35c296 | resume/send_input/wait | HotPE AutoMount 实验实现发布范围审计 | PASS for scoped local commit；不得 `git add -A`，只允许纳入 HotPE AutoMount 指定路径；未发现 secrets、真实 ISO/images、boot.wim、SQLite、商业源码或危险网络变更混入；push/release 因 network_safety_agent release BLOCKED 继续 deferred | active | `check-hotpe-automount-safety.sh`、`py_compile`、`git diff --check` PASS；宿主 UDP `67/69/4011` 监听仍阻断完整 release evidence |
| 2026-07-03 | network_safety_agent | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | resume/send_input/wait | 用户停掉 proxynet-lab dnsmasq 后的 release 网络门禁复审 | APPROVED；`dnsmasq` 已停止，UDP `67/69/4011` 无监听，主 Compose 未引入 DHCP/ProxyDHCP/TFTP、host network 或 privileged；push 后恢复实验 dnsmasq 只能恢复到 `ens19/10.101.8.135` 隔离边界 | active | `check-network-safety.sh` PASS；`collect-release-evidence.sh` PASS |
| 2026-07-03 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | install automation、ISO-first、等待室、软件市场、postinstall runner、HotPE AutoMount 整合包架构复审 | APPROVED；此前唯一阻断是 network release gate，停掉 dnsmasq 并复验后已闭合；允许工程化 commit/push 收口 | active | network/public/software/HotPE/build/py_compile/diff 验证均 PASS |
| 2026-07-03 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | release evidence 通过后的安全复审 | APPROVED；真实 ISO/WIM/SQLite/.env/含密脚本未进入 Git 待提交范围；未发现公共 KMS、产品密钥、第三方安装包托管、商业源码、license 或危险网络变更 | active | `collect-release-evidence.sh`、`check-network-safety.sh`、`check-token-disclosure.sh` PASS |
| 2026-07-03 | git_audit_agent | 019ec02f-bd09-7520-88db-b57c0d35c296 | resume/send_input/wait | 最终 git commit/push 收口审计 | APPROVED；建议一个整合 commit，因 API/UI/菜单/脚本/文档/preflight/evidence 互相引用；允许 push；必须精确 stage tracked diff 和列出的 untracked public 文件，排除 ignored runtime、真实镜像、SQLite、dist 和含密脚本 | active | `collect-release-evidence.sh` PASS；UDP `67/69/4011` 无监听；release 网络门禁已解除 |
| 2026-06-23 | project_decision_agent | 019ec02f-ac76-7863-899a-3af5498ce444 | resume/send_input/wait | Windows 分区预设是否保留，以及安装任务预设菜单方向 | PASS；撤回公开 `PartitionTemplate` 能力正确，保留 `InstallPreset=系统+软件组合` 符合当前基础装机阶段安全边界；legacy `partition_template_id` 空字段兼容风险可控 | active | 固定会话复用；Microsoft Learn DiskConfiguration 与 ConfigMgr task sequence 证据；本轮预检和构建通过 |
| 2026-06-23 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | 撤回 PartitionTemplate 后的 API/数据模型一致性复审 | PASS；公开入口、assignment-options、DeploymentAssignment、postinstall plan、task_sequence_plan 均不再暴露分区模板；legacy SQLite 列仅兼容空值 | active | 固定会话复用；预检覆盖 Windows assignment/postinstall plan 不得泄漏 partition 字段 |
| 2026-06-23 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | resume/send_input/wait | 管理后台移除分区模板控件并新增安装任务预设菜单 | PASS；预设页与客户端任务面板主流程成立；建议预设摘要展示具体软件名并说明手选软件在预设基础上追加，已修复 | active | `apps/web/src/main.tsx` 已补充默认软件名和追加说明；`npm run build` 通过 |
| 2026-06-23 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | 撤回分区预设后的安全边界复审 | PASS；公开 API、前端、任务计划、postinstall plan 均不再暴露分区模板；legacy DB 列只写空值；软件安装仍走官方来源与 runner allowlist | active | `check-software-assignment-flow.sh`、`check-public-runtime-boundary.sh`、`git diff --check` 通过 |
| 2026-06-23 | tutorial_docs_agent | 019ec02f-b887-7c11-bb50-825e065706cb | resume/send_input/wait | 分区预设撤回与安装任务预设文档复审 | PASS；要求移除 `SOFTWARE_MARKET_AND_ADMIN_ACTIONS_PLAN.md` 旧 `partition_confirmed` 示例并补充 dry-run，已修复 | active | `PLAN.md`、`docs/SOFTWARE_MARKET_AND_ADMIN_ACTIONS_PLAN.md`、`docs/BOOT_INSTALL_ISSUES_SUMMARY.md` 已同步 |
| 2026-06-23 | git_audit_agent | 019ec02f-bd09-7520-88db-b57c0d35c296 | resume/send_input/wait | 当前 diff 预审，暂不 commit/push | PASS；当前 diff 未发现不能进入下一步的代码/发布范围问题；完整 release evidence 仍因宿主 UDP 67/69/4011 监听外部阻断，用户确认前不建议 commit/push | active | 固定会话复用；`check-public-runtime-boundary.sh`、`check-software-assignment-flow.sh`、`git diff --check` PASS |
| 2026-06-24 | git_audit_agent | 019ec02f-bd09-7520-88db-b57c0d35c296 | resume/send_input/wait | Windows 预分区取消、Windows postinstall EXE 静默安装、安装任务预设归档/恢复 diff 审查 | PASS；`PartitionTemplate` 未对外暴露；`InstallPreset` 归档/恢复与 assignment/postinstall plan 自洽；Windows EXE 静默安装有 silent args 与测试保护；无 secret、商业代码、磁盘执行或网络服务变更风险；完整 release evidence 前 commit/push deferred | active | `python3 -m py_compile apps/api/main.py`、`npm run build`、`check-software-assignment-flow.sh`、`check-public-runtime-boundary.sh`、`git diff --check`、docker compose rebuild、HTTP asset/API checks PASS |
| 2026-06-24 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | `admin_reviewed_download` 来源策略与 Windows/Ubuntu 自动软件安装架构复审 | PASS；`admin_reviewed_download` 未改变不托管安装包边界；assignment、postinstall plan、runner allowlist 三层一致；Windows 扩展为受控 MSI/EXE/Office ODT first-boot runner，Ubuntu 保持 `apt_package`/`download_deb` | active | `py_compile`、`check-software-assignment-flow.sh`、`check-public-runtime-boundary.sh`、`npm run build`、`git diff --check` PASS |
| 2026-06-24 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | resume/send_input/wait | `admin_reviewed_download` Windows runner 执行链路复审 | PASS；Windows 仍是 HotPE/WinPE 注入 `SetupComplete.cmd` 后 first-boot runner 执行；EXE/MSI/ODT 客户端临时下载、可选 sha256、执行后清理；EXE 保存/生成/执行三层要求静默参数；Ubuntu apt/deb 未被破坏 | active | `corp-tool-windows-x64` 从未审核不可分配到审核后进入 Windows postinstall plan；核心验证命令 PASS |
| 2026-06-24 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | `admin_reviewed_download` 安全边界复审 | PASS；未引入安装包上传、服务端缓存、代理或静态目录分发；仅允许独立安装器动作；仍要求 HTTPS、非本机/内网、非 SynaBoot `/images`/`/boot`、runner allowlist、EXE silent args；无 raw command/secret/商业端点新增风险 | active | `check-software-assignment-flow.sh`、`check-public-runtime-boundary.sh`、`npm run build`、`git diff --check` PASS |
| 2026-06-24 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | 飞书 Windows MSI 默认软件变体配置复核 | PASS；无必须修复项；`feishu-windows-x64` 默认与旧 DB 迁移均收敛到 HTTPS CDN 直链、`msi_install`、`installer_type=msi`、`/qn /norestart`；未发现第三方安装包由 SynaBoot 托管、缓存、代理或写入 `/images`、`/boot`、SMB、Git 的回归 | active | 固定会话复用；`py_compile`、`check-software-assignment-flow.sh`、`check-public-runtime-boundary.sh`、`npm run build`、`git diff --check` PASS；实验环境重建后 live API 确认 `assignable=true` |
| 2026-06-23 | research_agent | 019ec02f-abcd-70b2-9364-cdb120d3d2a4 | resume/send_input/wait | 调研企业 Windows 系统镜像、软件对单台/批量电脑实现精准统一安装和统一环境的主流做法 | PASS；企业主流是 WinPE/Setup 入口 + task sequence / profile + 设备集合 + 软件 deployment type / detection rules + 安装后回调；SynaBoot 免费版适合借鉴 MDT/MECM 的轻量任务序列、设备集合、软件检测规则，不承诺替代 Intune/Autopilot/MECM | active | 已同步 `PLAN.md` 和 `docs/SOFTWARE_MARKET_AND_ADMIN_ACTIONS_PLAN.md`；参考 Microsoft Learn task sequence、applications、SetupComplete、provisioning packages |
| 2026-06-23 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | Windows 默认追加 Office 2021、KMS env 边界、Feishu Ubuntu 官方 deb 直链门控架构复审 | PASS；Windows 默认 `microsoft-office` 仍写入 assignment 并解析到持久化 `resolved_software_plan`，未绕过任务模型；Office ODT 保持 Microsoft 官方来源和受控 `ProPlus2021Volume`；KMS 仍默认关闭且只用管理员自有 `SYNABOOT_KMS_*`；Feishu 未配置官方 deb 直链时不伪装可安装 | active | 复用同一 architecture_agent；`check-software-assignment-flow.sh`、`npm run build`、`docker compose config`、`git diff --check` PASS |
| 2026-06-23 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | resume/send_input/wait | Windows Office 2021 默认计划、ODT/KMS first-boot runner、Feishu env-enabled download_deb 执行链路复审 | PASS；Windows/Ubuntu 都仍由客户端 first-boot runner 从官方来源下载；Office ODT/KMS 执行链路可实验闭环但需真机验证 SetupComplete、ODT 下载、KMS 返回码；Feishu env 示例只证明门控，不证明真实飞书源可安装 | active | 复用同一 image_factory_agent；`check-software-assignment-flow.sh`、`npm run build`、`docker compose config`、`git diff --check` PASS |
| 2026-06-23 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | Office 2021 ODT、合法 KMS、Feishu 官方 deb 来源安全复审 | PASS；未内置公共 KMS、产品密钥、KMS 模拟器或破解/绕过授权；Feishu env 仍受 HTTPS、非本机/内网、非 SynaBoot `/images`/`/boot` 来源边界约束；未放宽第三方安装包托管/缓存/代理边界 | active | 复用同一 security_audit_agent；`check-software-assignment-flow.sh`、`npm run build`、`docker compose config`、`git diff --check` PASS |
| 2026-06-21 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | Windows 自动软件安装、Office ODT、合法 KMS 激活链路架构复审 | PASS；Windows 带软件任务现在是 `setupcomplete_helper_ready` 下的受控 postinstall 链路，不是直接放开 WinPE/安装阶段执行；Office ODT 保持 metadata + Microsoft 官方来源 + 客户端下载执行；KMS 以管理员自有 `SYNABOOT_KMS_*` 配置为边界，默认关闭，不内置公共 KMS、不保存产品密钥 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 architecture_agent |
| 2026-06-21 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | resume/send_input/wait | Windows first-boot runner、Office ODT 安装、KMS 激活执行链路复审 | PASS；链路可按 SetupComplete 注入、first-boot `runner.ps1`、MSI/ODT/KMS 做实验闭环；MSI 有下载、hash、临时文件清理和 per-variant 事件；Office ODT 使用审核后的 Microsoft 官方 URL、合法产品 ID/Channel/授权模型；KMS 默认关闭且不内置公共 KMS 或产品密钥 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 image_factory_agent |
| 2026-06-21 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | Windows 自动软件安装、Office ODT、KMS 合法授权与安全边界复审 | PASS；未发现内置公共 KMS、产品密钥、破解/绕过授权能力；KMS 默认关闭，仅管理员显式配置 env 且 host/port 校验通过时使用；Office ODT 走 Microsoft 官方来源和受控产品 ID；Windows runner 仍只执行白名单分支，禁止 raw command，继续阻断 `/images`、`/boot`、localhost/private 来源；第三方安装包仍不由 SynaBoot 托管、缓存或代理 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | resume/send_input/wait | Ubuntu download_deb postinstall runner 临时文件清理与流式 hash 校验复审 | PASS；`download_deb` 分支使用 1MiB chunk 流式 sha256 校验，并在 finally 中删除临时 deb，增强真实客户端执行可靠性，不改变 runner allowlist 或 OS-specific 边界 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 image_factory_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | Ubuntu download_deb postinstall runner 安全复审 | PASS；未新增安装包托管/缓存/代理、任意命令或 URL 边界放宽；失败时尽量清理临时第三方 deb，hash 校验不再一次性读完整文件 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | 软件市场官方来源执行元数据维护架构复审 | PASS；受控更新 `install_action`、`installer_type`、`silent_args` 仍保持 SoftwarePackage/SoftwareVariant/DeploymentAssignment 分层，`official_download` 不伪装成自动安装能力，只有 OS runner 支持且来源合规的动作进入分配 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 architecture_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | 软件市场官方来源执行元数据安全复审 | PASS；未新增安装包上传、缓存、代理或任意命令；下载 URL 仍限制 HTTPS 且禁止 localhost/private/SynaBoot `/images`/`/boot`；静默参数受长度和安全字符校验 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | resume/send_input/wait/send_input/wait | 软件市场受控静默参数与软件选择 UI 复审 | 首轮 BLOCKED：专题文档旧文案仍称不提供 silent args 编辑入口；修复后 PASS。当前 UI 可维护安装动作、安装器类型、受控静默参数，创建任务弹窗保留搜索/分类/卡片勾选与已选软件清单 | active | `npm run build`、`check-software-assignment-flow.sh`、`git diff --check` PASS；旧文案 `rg` 无匹配；复用同一 webui_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | postinstall execution_model 按 OS 声明真实 runner 能力复审 | PASS；execution model 按 OS family 暴露真实 runner 动作，符合只声明可执行能力、不把 metadata 伪装成自动安装能力的架构边界；Windows 仍未开放带软件自动安装 | active | `check-software-assignment-flow.sh`、`py_compile`、`npm run build`、`git diff --check` PASS；复用同一 architecture_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | postinstall execution_model 能力声明安全复审 | PASS；`official_download` 不再作为可执行动作暴露，未新增第三方安装包托管/缓存/代理、Windows 带软件开放或网络服务 | active | `check-software-assignment-flow.sh`、`py_compile`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | 软件市场 postinstall 任务生命周期与事件排序复审 | PASS；runner 事件推进全局、variant 事件只做软件明细的分层正确；同秒事件用 `created_at DESC, rowid DESC` 保持最近状态稳定 | active | `check-software-assignment-flow.sh`、`py_compile`、`npm run build`、`git diff --check` PASS；复用同一 architecture_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | 软件市场来源边界与 postinstall 事件状态修复安全复审 | PASS；未破坏第三方安装包不托管、不缓存、不代理边界；variant 事件不能伪造整体任务完成/失败；未开放 Windows/HotPE 带软件任务或网络服务 | active | `check-software-assignment-flow.sh`、`py_compile`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | apt_package 外部 repo fail-closed 架构复审 | PASS；`apt_package` 收紧为 Ubuntu 默认 apt 源可直接安装的软件包，外部 apt repo/keyring 未实现时通过 `apt_repo_not_supported` 保持不可分配；应用级选择跳过不可分配默认变体，选择同 OS 下真正 assignable 的变体，符合真实可执行优先方向 | active | `check-software-assignment-flow.sh`、`py_compile`、`npm run build`、`git diff --check` PASS；复用同一 architecture_agent |
| 2026-06-20 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | resume/send_input/wait | Ubuntu apt_package runner 能力边界复审 | PASS；runner 当前只执行 `apt-get update && apt-get install -y <package_name>`，不配置外部 repo/keyring，因此外部 apt 源变体必须 fail-closed，避免真实客户端 apt 找不到包 | active | `check-software-assignment-flow.sh`、`py_compile`、`npm run build`、`git diff --check` PASS；复用同一 image_factory_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | apt_package 外部 repo fail-closed 安全复审 | PASS；不把第三方 repo 添加伪装成已有能力，不绕过审核/来源策略，不新增任意命令、第三方包托管、Windows/HotPE 带软件开放或网络服务 | active | `check-software-assignment-flow.sh`、`py_compile`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | resume/send_input/wait | Ubuntu NoCloud first-boot postinstall bootstrap 可靠性复审 | PASS；first-boot bootstrap 增加 runner 下载有限重试、systemd 失败重启和成功后删除 token-bearing runner，提升真实客户端网络刚启动时的软件安装成功率，不改变 NoCloud/autoinstall/postinstall 模板边界 | active | `check-software-assignment-flow.sh`、`py_compile`、`npm run build`、`git diff --check` PASS；复用同一 image_factory_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | Ubuntu NoCloud first-boot postinstall bootstrap 安全复审 | PASS；重试次数有界，成功后清理 token-bearing runner.sh；未新增服务端缓存/代理第三方安装包、任意命令、Windows/HotPE 带软件开放或生产网络服务 | active | `check-software-assignment-flow.sh`、`py_compile`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | HTTP 创建任务到 passive wait 领取架构复审 | PASS；HTTP-created assignment 继续经 `/api/ipxe/wait` 被同一 session 领取，返回包含同一 assignment id、NoCloud seed、postinstall plan URL 与 runner URL 的 iPXE 脚本，并把客户端状态推进为 `booting`，覆盖管理员后台按钮到被动客户端领取的关键链路 | active | `software_http_assignment=ok`、`check-software-assignment-flow.sh`、`npm run build`、`py_compile`、`git diff --check` PASS；复用同一 architecture_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | HTTP 创建任务到 passive wait 领取安全复审 | PASS；增量 smoke 未弱化 admin token、session token、per-session boot token、软件官方来源/客户端自下载、Windows/HotPE 带软件 fail-closed 或日志脱敏边界；localhost 验证不涉及生产网络服务 | active | `software_http_assignment=ok`、`check-software-assignment-flow.sh`、`npm run build`、`py_compile`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | 软件市场官方来源红线与 passive wait 计划领取验证架构复审 | PASS；软件市场仍是 Apple Store 式目录/编排器而非安装包仓库，任务链路仍以 `DeploymentAssignment.resolved_software_plan` 为中心；新增预检覆盖层级正确 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 architecture_agent |
| 2026-06-20 | boot_entry_agent | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | resume/send_input/wait | passive wait postinstall 计划领取启动链路复审 | PASS；新增检查只验证 assignment plan/runner URL 与 iPXE 变量，不代表 PXE 阶段下载安装包；主动/被动菜单和等待室链路未被破坏 | active | 复用同一 boot_entry_agent；无新建同职责 subagent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | 软件市场不托管安装包与 passive wait URL 绑定安全复审 | PASS；SynaBoot 不存储、缓存、镜像或代理第三方安装包边界清晰；预检覆盖等待室领取脚本绑定 assignment plan/runner URL；未发现绕过 `/images`、`/boot`、本机/内网 URL 拦截风险 | active | 复用同一 security_audit_agent；无新建同职责 subagent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | resume/send_input/wait | 创建任务提交真实勾选软件 ID UI 复审 | PASS；提交 `selectedSoftwarePackageIds` / `selectedSoftwareProfileIds` 更符合管理员勾选应用/集合、后端按目标系统解析变体的模型，并避免 catalog 派生视图不完整导致漏提交 | active | `npm run build`、`check-software-assignment-flow.sh`、`py_compile`、`git diff --check` PASS；复用同一 webui_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | 创建任务提交真实勾选软件 ID 安全复审 | PASS；前端提交勾选 ID 没有弱化后端边界，最终仍由 `create_deployment_assignment` / `resolve_software_plan` 执行 OS 兼容、审核、assignable、官方来源和 Windows fail-closed 校验 | active | 复用同一 security_audit_agent；无新建同职责 subagent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | 应用+集合组合软件选择架构复审 | PASS；同一任务同时提交应用和集合时，保留 `package_ids` / `profile_ids` 审计字段，并在最终执行变体层去重，符合后端统一解析到 `resolved_software_plan` 的架构 | active | `software_combined_selection=ok`、`npm run build`、`py_compile`、`git diff --check` PASS；复用同一 architecture_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | 应用+集合组合软件选择安全复审 | PASS；组合选择没有绕过审核、OS 兼容、assignable、官方来源或 runner action 校验，也没有引入重复执行危险、第三方包托管或 Windows fail-open 风险 | active | 复用同一 security_audit_agent；无新建同职责 subagent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | HTTP 创建软件安装任务架构复审 | PASS；HTTP smoke 覆盖 `assignment-options -> deployment-assignments -> assignment readback`，更贴近管理员后台按钮路径，并验证 admin token、写限流、目标兼容软件集合和持久化 `resolved_software_plan` | active | `software_http_assignment=ok`、`npm run build`、`py_compile`、`git diff --check` PASS；复用同一 architecture_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | HTTP 创建软件安装任务安全复审 | PASS；localhost HTTP smoke 未弱化 admin token、写限流、软件来源/审核、Windows fail-closed 或 token 日志脱敏边界 | active | 复用同一 security_audit_agent；无新建同职责 subagent |
| 2026-06-20 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | resume/send_input/wait | postinstall runner 实现复审 | APPROVED_WITH_FIXES；要求 runner 客户端二次校验 plan、apt_package 必须使用 package_name、Windows MSI 校验 installer_type、Ubuntu 等待 apt/dpkg lock、events 数字字段做范围校验 | active | 已复用原 image_factory_agent 会话，未新建同职责 subagent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | postinstall runner 安全复审 | APPROVED_WITH_FIXES；要求 events message 脱敏 token/secret，URL `/images`/`/boot` 路径拦截对域名形式也生效 | active | 已复用原 security_audit_agent 会话，未新建同职责 subagent |
| 2026-06-20 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | send_input/wait | postinstall runner 修复复审 | PASS；客户端二次校验、package_name fail-closed、apt lock 等待、events 数字范围校验通过 | active | `py_compile` 与临时 HTTP 烟测通过；同一 image_factory_agent 会话复审 PASS |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | postinstall runner 安全修复复审 | PASS；message 敏感信息脱敏、`/images`/`/boot` 域名路径拦截、token 鉴权与日志脱敏通过 | active | 临时 HTTP 烟测确认真实 token 不入日志和 event message；同一 security_audit_agent 会话复审 PASS |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | 软件市场安全 BLOCKED 修复复审 | APPROVED_WITH_FIXES；核心 BLOCKED 已解除，但要求先校验软件计划再写 client session，并加强 SynaBoot 本机/内网下载地址拦截 | active | 已复用同一 security_audit_agent 会话，未新建 reviewer |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | 软件市场安全二次修复复审 | PASS；无效软件选择不再污染 client session，localhost/loopback/private/SERVER_IP 下载源已拦截 | active | 回归 smoke 与 py_compile 通过；同一安全会话复审 PASS |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | postinstall per-session boot token 隔离复审 | PASS；legacy assignment 级 token fallback 仅在没有 per-session token row 时启用；同批两个 session 的 plan/runner/events 交叉 token 访问已被 preflight 覆盖 | active | `py_compile`、`git diff --check`、`check-software-assignment-flow.sh`、`npm run build` PASS；复用同一安全会话，未新建 reviewer |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | 软件市场官方来源 URL 边界补强复审 | PASS；`official_source_url` 与 `download_url` 均禁止指向 SynaBoot 本机、内网和 `/images`/`/boot` 等项目静态目录；保留 `download_url` 旧错误码兼容 | active | `py_compile`、`git diff --check`、`check-software-assignment-flow.sh`、`npm run build` PASS；复用同一安全会话，未新建 reviewer |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | send_input_failed/resume/send_input/wait | 客户端列表展示最近安装任务与软件进度复审 | PASS；客户端列表能直接看到最近安装任务、软件选择和 runner/event 进度，信息粒度适合管理员观察任务状态，且未暴露 token/hash | active | 初次 send_input 返回 not found，resume 后同一 agent_id 复用成功；未新建同职责 subagent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input_failed/resume/send_input/wait | client session latest_assignment payload 信息泄漏复审 | PASS；admin client session payload 增加 latest_assignment 摘要未泄露 token/hash/secret，redacted 视图不返回该字段 | active | 初次 send_input 返回 not found，resume 后同一 agent_id 复用成功；未新建同职责 subagent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | send_input/wait | 软件市场维护来源表单 UI 复审 | PASS；维护入口在软件变体层级，字段覆盖官方来源、下载地址、来源策略、签名/hash、包名、风险和备注，保存后能反馈 assignable/blocked 状态 | active | `npm run build`、软件分配 preflight、py_compile、diff check 均 PASS |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | 软件市场维护来源表单安全复审 | PASS；未新增安装包上传、任意命令、silent args 或 raw command 编辑入口，仍复用后端 URL/hash/package 校验 | active | `npm run build`、软件分配 preflight、py_compile、diff check 均 PASS |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | software_profile_ids fail-fast 与官方来源边界复审 | PASS；非空 profile 未实现时已 fail-fast，未引入托管/缓存第三方安装包、任意命令、token 泄漏、跨 session token 复用或 Windows 软件误开放风险 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | resume/send_input/wait | 软件市场与创建安装任务 UI 来源边界复审 | PASS；软件市场未暴露第三方安装包上传/托管入口，软件选择弹窗按目标系统匹配并持续显示已选软件，profile 未实现时前端不暴露选择入口 | active | `npm run build` PASS；复用同一 webui_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | SoftwareProfile 第一阶段接入架构复审 | PASS；默认 Ubuntu profile 指向已审核变体并进入 `resolved_software_plan`，profile 与显式 variant 去重后统一校验，Windows 带软件保持 fail-closed | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 architecture_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | SoftwareProfile 第一阶段安全复审 | PASS；profile 不托管/缓存/代理第三方安装包，展开后仍统一校验变体 assignable、官方来源、runner action 和 OS 兼容，不能绕过 Windows fail-closed | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | resume/send_input/wait | 创建安装任务默认软件集合 UI 复审 | PASS；仅在支持 postinstall 的目标显示兼容 assignable profile，profile 绿色标签与单独软件蓝色标签区分清晰，目标变化会清理不兼容集合 | active | `npm run build` PASS；复用同一 webui_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | 软件市场新增应用/系统版本 metadata 架构复审 | PASS；新增应用/变体仍是 metadata 目录能力，变体默认 `needs_review`，模型层次保持 SoftwarePackage/SoftwareVariant/SoftwareProfile/DeploymentAssignment 分离 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 architecture_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | 软件市场新增应用/系统版本 metadata 安全复审 | PASS；新增接口未引入安装包上传、服务端缓存、反向代理、本机静态目录分发、任意命令或 Windows 软件误开放风险 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | resume/send_input/wait | 软件市场新增应用/系统版本表单 UI 复审 | PASS；入口文案明确是应用目录 metadata/官方来源/安装元数据，未提供文件上传、托管安装包、任意 shell 或 silent args 编辑，且不干扰任务软件选择 | active | `npm run build` PASS；复用同一 webui_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | 软件市场 SoftwareProfile 创建能力架构复审 | PASS；`/api/software-profiles` 只保存集合 metadata 和 `variant_ids`，只组合已审核 assignable 变体，不绕过 `DeploymentAssignment/resolved_software_plan` | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 architecture_agent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | resume/send_input/wait | 软件市场新增“软件集合”前端体验复审 | PASS；新增集合表单文案明确只引用已审核可安装版本，调用真实 `POST /api/software-profiles`，未提供上传/托管安装包或任意命令入口 | active | `npm run build` PASS；复用同一 webui_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | 软件市场 SoftwareProfile 创建能力安全复审 | PASS；profile 创建不能绕过 variant assignable/OS 校验，未引入托管/缓存/代理第三方安装包、任意命令、路径写入、secret 泄漏或 Windows 软件误开放 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | send_input/wait | 软件选择弹窗优先可安装变体 UI 修复复审 | PASS；`variantForTarget()` 优先返回当前 OS 下 `assignable=true` 的版本，避免同一应用被不可安装 variant 误挡 | active | `npm run build`、`check-software-assignment-flow.sh` PASS；复用同一 webui_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | postinstall HTTP endpoint 预检与跨 session token 覆盖复审 | PASS；临时 localhost API smoke 覆盖 plan/runner/NoCloud/event 与跨 session 403，不涉及生产网络/DHCP/ProxyDHCP/TFTP | active | `check-software-assignment-flow.sh`、`py_compile`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | 软件市场官方来源硬约束与客户端事件 session 隔离复审 | PASS；确认软件市场保持 metadata/官方来源/官方源/批准企业镜像源模式，不托管第三方安装包；客户端 `latest_assignment.event_summary` 按当前 session 统计，不把同批其它客户端完成事件误显示到本机 | active | `py_compile`、`git diff --check`、`check-software-assignment-flow.sh`、`npm run build` PASS；复用同一 security_audit_agent，未新建 reviewer |
| 2026-06-20 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | resume/send_input/wait | Ubuntu postinstall runner 软件变体事件上报复审 | PASS；runner failure trap 与每个软件变体 started/completed/failed 事件符合 OS-specific postinstall 设计，仍只消费已审核 plan，不托管第三方包，不执行 raw command | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 image_factory_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | Ubuntu postinstall runner per-variant event 安全复审 | PASS；新增事件只通过 token 保护 endpoint 回传白名单 payload，不扩大执行 allowlist，不泄露 token，不开放 Windows 带软件任务，不启用网络启动服务 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | wait | 最近安装任务软件变体级事件展示 UI 复审 | PASS；最近安装任务卡片按 `resolved_software_plan.variants` 展示每个软件，并用 `recent_events[].payload.variant_id` 显示等待、执行中、完成、失败、阻断等状态；保留最近 runner/variant 回调 | active | 复用同一 webui_agent；无新建 reviewer |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | wait | 最近安装任务 recent_events 前端展示安全复审 | PASS | active | 复用同一 security_audit_agent；无新建 reviewer |
| 2026-06-20 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | send_input | Windows postinstall 注入缺口复审 | pending | active | 已复用原 image_factory_agent 会话，等待复核返回 |
| 2026-06-20 | boot_entry_agent | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | send_input_failed/resume/send_input | Windows/HotPE 启动链路是否能承载被动软件安装注入 | 首次发送返回 `agent not found`，随后 resume 成功并已重新发送任务；等待复核返回，不登记为 APPROVED | active | 按固定会话池协议恢复同一 boot_entry_agent，未新建同职责 subagent |
| 2026-06-20 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | wait | Windows postinstall 注入缺口复审 | APPROVED_WITH_FIXES；当前 `runner.ps1` / `setupcomplete.cmd` 只是可下载模板，不会自动进入安装后的 Windows；Windows 带软件任务必须继续 fail-closed；推荐 HotPE 手动/半自动注入或外部 ADK/DISM/Autounattend 任务包路径 | active | 复用同一 image_factory_agent；无新建同职责 subagent |
| 2026-06-20 | boot_entry_agent | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | wait | Windows/HotPE 启动链路是否能承载被动软件安装注入 | BLOCKED；iPXE 变量不会被 Windows Setup/WinPE/installed OS 自动消费；必须新增真实 Autounattend/SetupComplete/HotPE helper 注入链路后才能开放 Windows 带软件任务 | active | 复用恢复后的同一 boot_entry_agent；本结论是阻断，不是批准 |
| 2026-06-20 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | send_input/wait | Windows HotPE 注入准备件实现复审 | PASS；`windows-hotpe-inject.ps1` 可作为下一步实验准备件，要求显式 `WindowsRoot`，只写 `Windows\Setup\Scripts\SetupComplete.cmd`，不猜盘、不分区、不格式化、不托管第三方包；Windows 带软件仍必须 fail-closed | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | Windows HotPE 注入准备件安全复审 | PASS | active | 复用同一 security_audit_agent；无新建同职责 subagent |
| 2026-06-20 | boot_entry_agent | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | send_input/wait | Windows HotPE 注入准备件与启动链路边界复审 | PASS；helper 不改现有 `:windows_setup`/`:hotpe`，不把 Windows target 标记为可装软件；后续需独立 `windows_setup_passive` 等链路验证后才能开放 | active | 复用同一 boot_entry_agent；无新建同职责 subagent |
| 2026-06-20 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | send_input/wait | Ubuntu 被动等待室到 NoCloud 启动脚本预检覆盖复审 | PASS；preflight 覆盖 `/api/ipxe/wait` 领取 assignment、返回带 NoCloud seed/postinstall URL 的 iPXE 脚本，并确认 session 状态切到 `booting` | active | `check-software-assignment-flow.sh` 输出 `passive_wait_assignment_flow=ok`；复用同一 image_factory_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | 被动等待室软件任务 HTTP smoke 安全复审 | PASS | active | `check-software-assignment-flow.sh` PASS 且 HTTP 日志 token 脱敏；复用同一 security_audit_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | send_input/wait | assignment-options 目标级兼容软件目录架构复审 | PASS；`compatible_software_by_target` 让 API 从全局软件目录收敛为按 boot target 给出真实可分配目录；Windows/HotPE fail-closed，Ubuntu 只暴露 assignable Ubuntu 变体 | active | `check-software-assignment-flow.sh`、`py_compile`、`npm run build`、`git diff --check` PASS |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | send_input/wait | 软件选择弹窗使用后端目标级兼容目录 UI 复审 | PASS；创建任务弹窗优先使用 `compatible_software_by_target[selectedTarget]`，符合只展示对应系统可自动安装软件的体验；Windows/HotPE 仍禁用选择软件 | active | `npm run build`、`check-software-assignment-flow.sh` PASS |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | assignment-options 兼容软件目录安全复审 | PASS | active | preflight 覆盖 Windows 不暴露软件、Ubuntu 不暴露 blocked/非 Ubuntu/非 assignable 变体；复用同一 security_audit_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | wait | assignment-options 目标级兼容软件集合 profile 架构复审 | PASS；`compatible_software_profiles_by_target` 让默认软件集合也按 boot target 收敛；Windows/HotPE 返回空集合，Ubuntu 只返回 assignable 且 OS 兼容的 profile；profile 仍需进入后端 `resolve_software_plan()` 统一校验 | active | 复用同一 architecture_agent；无新建同职责 subagent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | wait | 默认软件集合使用后端目标级兼容 profile UI 复审 | PASS；前端优先读取 `compatible_software_profiles_by_target[selectedTarget]`，未开放 postinstall 的目标禁用软件选择并清理已选 profile；目标变化时不兼容 profile 会被移除 | active | 复用同一 webui_agent；无新建同职责 subagent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | wait | assignment-options 兼容软件集合 profile 安全复审 | PASS；目标级 profile map 不开放 Windows/HotPE 软件任务，不引入托管第三方包、任意命令、token/secret 泄漏或绕过变体审核的路径 | active | 复用同一 security_audit_agent；无新建同职责 subagent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | send_input/wait | software_package_ids 应用级选择进入 DeploymentAssignment 架构复审 | PASS；管理员选择 `SoftwarePackage`，后端按 `boot_target` 解析到已审核、可分配、目标 OS 兼容的 `SoftwareVariant`，并在 `resolved_software_plan` 记录 package/profile/variant；Windows 带软件仍 fail-closed | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build` PASS；新增 `software_package_selection=ok` |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | send_input/wait | 创建安装任务软件弹窗改为应用级选择 UI 复审 | PASS；前端从 `selectedSoftwareVariantIds` 切到 `selectedSoftwarePackageIds`，弹窗展示应用卡片和目标系统匹配变体，提交 `software_package_ids`，避免前端成为唯一变体解析方 | active | `npm run build`、`check-software-assignment-flow.sh` PASS；新增应用级选择路径 |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | software_package_ids 应用级选择安全复审 | PASS；应用级选择未绕过变体审核、OS 兼容、来源 URL、runner action、Windows fail-closed 或第三方包不托管边界 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build` PASS；复用同一 security_audit_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | send_input/wait | 软件应用多版本默认/优先级解析架构复审 | PASS；`default_for_os` + `selection_priority` 让应用级选择从偶然排序变为确定性 OS 变体解析；同一应用同一 OS 设置默认会清除其它默认；仍只保存 metadata 和官方来源计划 | active | `py_compile`、`check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS；未新建同职责 agent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | send_input/wait | 软件版本默认/优先级管理 UI 复审 | PASS；软件市场维护入口展示并可编辑默认版本和优先级，创建安装任务仍按应用选择并提交 `software_package_ids`，文案未把 SynaBoot 表达成第三方安装包仓库 | active | `npm run build`、`check-software-assignment-flow.sh` PASS；未新建同职责 agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | 软件默认版本/优先级选择安全复审 | PASS；默认/优先级只影响 metadata 排序，不绕过审核、OS 兼容、runner allowlist、来源 URL、hash/signature 或 Windows fail-closed；确认 SynaBoot 不代下载、缓存、代理或静态分发第三方安装包 | active | `software_market_policy=official-source-client-download`、`software_package_selection=ok`；复用同一 security_audit_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | APT 官方源安装 download_url 可空安全复审 | PASS；`apt_package` 可不填 `download_url`，但仍需官方来源、包名、审核和签名策略；`download_deb`/`msi_install` 仍强制 HTTPS download_url 并拦截 SynaBoot/内网/静态目录 | active | `check-software-assignment-flow.sh` 覆盖空 download_url 的 htop/chrome apt 变体；复用同一 security_audit_agent |
| 2026-06-20 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | send_input/wait | Ubuntu postinstall runner APT 官方源语义复审 | PASS；`apt_package` runner 使用 apt-get update/install package_name，不读取 download_url；`download_deb` 才下载独立安装器；符合 Ubuntu 被动安装后软件安装第一阶段闭环 | active | HTTP runner.sh/NoCloud smoke PASS；未新建同职责 agent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | send_input/wait | 软件市场安装器下载 URL 文案复审 | PASS；新增/维护软件版本提示 `download_deb / msi_install 必填；apt_package 可留空`，避免管理员误填伪下载地址 | active | `npm run build` PASS；未新建同职责 agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | send_input/wait | 软件市场应用/集合归档恢复架构复审 | PASS；归档/恢复是软删除状态，不改写历史 assignment；归档应用退出 `compatible_software_by_target` 和应用级解析，归档集合退出 compatible profile | active | `software_catalog_archive=ok`、`npm run build`、`git diff --check` PASS；未新建同职责 agent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | send_input/wait/send_input/wait | 软件市场归档恢复 UI 复审 | PASS；首轮要求补可见文案“归档不是删除，不影响历史任务”，修复后 PASS；应用/集合卡支持归档和恢复 | active | `npm run build`、`git diff --check` PASS；复用同一 webui_agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | 软件市场归档恢复安全复审 | PASS；归档/恢复为 admin-token 保护的 POST 写操作，不引入硬删除、任意命令、安装包托管、缓存代理或网络服务能力；归档项不进入新自动安装计划 | active | `software_catalog_archive=ok`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | send_input/wait | 归档应用阻断 profile/显式 variant 绕过架构复审 | PASS；`package_status` 下沉到 `SoftwareVariant` assignable，显式 `software_variant_ids` 和引用归档应用的 profile 都不能绕过应用归档进入任务 | active | `check-software-assignment-flow.sh` 覆盖 profile/explicit variant bypass；未新建同职责 agent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | 归档应用阻断 profile/显式 variant 绕过安全复审 | PASS；归档应用后应用级选择、显式 variant id、引用该应用的 profile 均不能进入新自动安装计划；不影响历史 assignment 审计 | active | `software_catalog_archive=ok`、`py_compile`、`npm run build`、`git diff --check` PASS；复用同一 security_audit_agent |
| 2026-06-20 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/completed | 软件市场与被动装机任务的软件选择/安装链路架构审查 | APPROVED_WITH_FIXES；批准官方来源目录 + 安装模板 + 审查状态方向；要求新增 SoftwarePackage/SoftwareVariant/SoftwareProfile、批量 session_ids、resolved_software_plan、assignment 变体兼容和审核校验 | active | 已复用原 architecture_agent 会话，未新建同职责 subagent |
| 2026-06-20 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | resume/send_input/completed | 软件市场页面与创建安装任务时的软件多选弹窗 UI 审查 | APPROVED_WITH_FIXES；要求软件页像市场、客户端页作为安装任务工作台、软件多选弹窗显示已选软件、兼容/不兼容原因、token/提交错误反馈 | active | 已复用原 webui_agent 会话，未新建同职责 subagent |
| 2026-06-20 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/completed | 软件市场外部下载来源与安装任务安全边界握手/复审 | role_confirmed；BLOCKED 当前未校验 variant 存在性、审核、兼容、官方来源、hash/signature；禁止任意 shell 模板、任意 URL、本机托管第三方包和 raw command 下发 | active | 旧登记 security_audit_agent 恢复成功，事故后未新建同职责 subagent；本轮代码按该 BLOCKED 项补校验 |
| 2026-06-20 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | resume/send_input/completed | Windows/Ubuntu 安装后自动安装所选软件的执行点规划 | 建议短期只生成 OS-specific postinstall 计划包；Windows 首次启动/SetupComplete 或 runner，Ubuntu cloud-init/late-commands 只引导、首次启动 systemd 执行；不托管第三方包、不在 WinPE/late-commands 强装业务软件 | active | 已复用原 image_factory_agent 会话，未新建同职责 subagent |
| 2026-06-18 | research_agent | 019ec02f-abcd-70b2-9364-cdb120d3d2a4 | resume/handshake/send_input/wait | ISO-first 后台未来支持 PVE、Debian、RHEL 等系统的官方网络启动策略研究 | 结论返回：Ubuntu casper 支持 NFS/url；Windows 应走 HotPE/WinPE；PVE 需官方 assistant/answer 流程；Debian 优先官方 netboot；RHEL 类需完整安装树和 `.treeinfo`；未知系统不得自动 ready | active | 已复用原 research_agent 会话，未新建同职责 subagent |
| 2026-06-18 | research_agent | 019ec02f-abcd-70b2-9364-cdb120d3d2a4 | resume/send_input/wait | PXE/iPXE 客户端是否能被 FlashPXE 后台识别并进入等待分配界面 | APPROVED_RESEARCH；只有进入 iPXE 并访问 FlashPXE HTTP 脚本后后台才能可靠登记；可上报 MAC、UUID、serial、asset、platform、buildarch、IP 等字段；固件 PXE/DHCP 阶段对 Web 后台不可见；等待室应返回 iPXE 脚本并 5-15 秒限速轮询 | active | 已复用原 research_agent 会话，未新建同职责 subagent；规划落入 `docs/PXE_CLIENT_WAITING_ROOM_PLAN.md` |
| 2026-06-18 | boot_entry_agent | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | resume/send_input | PXE 一级菜单新增主动/被动装机模式与被动等待室脚本复核 | pending | active | 已复用原 boot_entry_agent 会话，等待复核返回 |
| 2026-06-18 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input | PXE 被动等待室公开接口与后台分配接口安全复核 | pending | active | 已复用原 security_audit_agent 会话，等待复核返回 |
| 2026-06-19 | boot_entry_agent | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | send_input_failed/resume_attempted | 主动/被动菜单、HotPE target、实验 menu-lab 转发修复后复审 | `agent not found`，已尝试 resume；不得登记为 APPROVED | stale | 后续提交前需按固定池协议替换同岗位会话复审 |
| 2026-06-19 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input_failed/resume_attempted | client-sessions 脱敏、token 日志脱敏、被动 session 每次新建修复后复审 | `agent not found`，已尝试 resume；不得登记为 APPROVED | stale | 后续提交前需按固定池协议替换同岗位会话复审 |
| 2026-06-18 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | ISO-first `/api/images` 与后台主列表侧审 | APPROVED_WITH_FIXES；要求保留 `images` 兼容字段，新增 `source_images`/derived artifacts，明确 SourceImage、BootStrategy、DerivedBootArtifact 分层 | active | 已复用原岗位会话，未新建同职责 subagent |
| 2026-06-18 | storage_agent | 019ec02f-b120-7a92-9823-4e9f386c70ba | resume/send_input/wait | ISO-first 存储扫描与派生物可见性侧审 | APPROVED_WITH_FIXES；要求扫描层保留派生物，库存层只展示源 ISO，菜单层继续使用完整 rows 聚合 | active | 已复用原岗位会话，未新建同职责 subagent |
| 2026-06-18 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | resume/send_input/wait | ISO-first 管理后台 UI 侧审 | APPROVED_WITH_FIXES；要求主列表只展示源 ISO，派生工件进详情折叠区，移动端避免路径/SHA 横向溢出 | active | 旧会话从 stale 恢复并握手成功，继续登记为原 webui_agent 岗位 |
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
| 2026-06-15 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | resume/send_input/wait | 加载本地个人 skills 到 Web UI 岗位职责 | READY；确认后续重构 Web UI/网页后端联动时会使用 design-review、design-taste-frontend、frontend-design、shadcn-ui、tailwind-design-system 作为检查框架；保持管理后台属性和轻量静态 UI 架构，未经审批不引入新依赖 | active | 初次 send_input 返回 `agent not found`，resume 后同一 agent_id 成功接收并回复；复用当前固定会话，不新建同职责 agent |
| 2026-06-15 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | send_input/wait | Web UI/PXE/HotPE 体验重构建议 | APPROVED first round，建议保留轻量静态 Web UI，重构 Dashboard、镜像页、菜单页、HotPE 页；使用本地个人 skills 做检查框架，不引入 React/Tailwind/shadcn | active | HotPE 页面应展示源 ISO、必需组件、Windows 候选、HTTP URL、真实客户端测试项；禁止 DHCP/ProxyDHCP/TFTP/路由/网关/防火墙/DNS 操作 |
| 2026-06-16 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait/close | 误投递 Web UI 重构约束到安全审计会话 | 输出内容可作为 security 边界建议参考，但不得登记为 webui_agent 结论；随后关闭释放线程 | closed | 误投递原因：工具环境简表与长期台账不一致；已按台账纠正 |
| 2026-06-16 | webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | send_input/resume | Web UI modern admin rebuild 复用尝试 | `agent not found`，resume 受线程上限阻塞；本轮未获得 webui_agent 新结论 | stale | 后续若仍需 UI 专岗复核，必须先按重建条件替换会话并登记 |
| 2026-06-16 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | React/Tailwind 管理后台重构安全审计 | APPROVED；商业关键词仅用于公开版本边界展示或依赖许可证元数据；未发现 CDN runtime、secret、第三方上传、商业授权端点或 license gate | closed | `collect-release-evidence.sh` PASS；`npm audit` 0 vulnerabilities；`check-public-runtime-boundary.sh` PASS |
| 2026-06-16 | security_audit_agent | 019ecff1-105d-7652-801d-34a918baa206 | spawn/wait | SMB/CIFS livefs 初次安全审计 | BLOCKED；指出 Linux ISO 准备脚本优先 `bsdtar/7z` 绕过项目内提取器大小上限 | completed_not_pool | 主控违反复用规则新建；本应复用登记会话或把修复回传同一会话 |
| 2026-06-16 | network_safety_agent | 019ecff1-4eff-7750-b1b5-4ac5a1231d76 | spawn/wait | SMB/CIFS livefs 网络安全审查 | BLOCKED；SMB 本身在实验网边界内，但当前 ProxyNet lab 已监听 UDP 67/69/4011 | completed_not_pool | 主控违反复用规则新建；本应复用登记会话；需用户手动停止 ProxyNet lab 后再复验 |
| 2026-06-16 | security_audit_agent | 019ecff6-71e9-7d93-ba84-4aeaf80538cc | spawn/wait | SMB/CIFS livefs 安全复审 1 | BLOCKED；确认 `bsdtar/7z` 问题解除，但目录 extent 和既存 `*.squashfs` symlink 校验仍不足 | completed_not_pool | 主控再次新建同职责 reviewer；本应 send_input 回 019ecff1-105d... |
| 2026-06-16 | security_audit_agent | 019ecff9-0adb-74d0-80d2-22f7486f34ce | spawn/wait | SMB/CIFS livefs 安全复审 2 | PASS；目录 extent 大小/边界校验、既存 livefs 普通文件非 symlink 校验已闭环 | completed_not_pool | 主控第三次新建同职责 reviewer；结论可作为本任务证据，但不登记为固定池 |
| 2026-06-15 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | resume/send_input/wait | Web UI/PXE/HotPE 架构审查 | APPROVED with gates；允许 Web UI、API 只读聚合层、页面结构、视觉系统、菜单预览和 HotPE 引导体验重构；当前引入 React/Tailwind/shadcn 先 BLOCK；HotPE 当前可用性 BLOCKED until 组件提取和真实客户端验证 | active | 初次 send_input 返回 `agent not found`，resume 后同一 agent_id 成功接收并回复；建议新增只读 `/api/hotpe-readiness` 与 `/api/windows-install-candidates` |
| 2026-06-15 | project_decision_agent | 019ec02f-ac76-7863-899a-3af5498ce444 | resume/send_input/wait | Web UI/PXE/HotPE 方向决策 | APPROVED，批准在现有轻量静态架构内做免费版体验重构；暂不批准引入 React/Tailwind/shadcn；HotPE/Win11 安装检查属于免费版基础装机能力 | active | 商业代码、license、在线激活、混淆产物、商业端点、私有目录、生产 LAN 自动启动和未授权 UDP 67/69/4011 能力不得进入 GitHub 免费版 |
| 2026-06-15 | runtime | local | command | HotPE/Win11 运行态检查与第一轮 UI/API 实现 | 新增只读 `/api/hotpe-readiness`、`/api/windows-install-candidates`；Dashboard、菜单页和 HotPE 页完成第一轮静态 UI 信息架构重构；运行态显示 HotPE blocked、Win11 候选 1 个 | ready | HotPE 缺 `wimboot`、`bootmgr`、`BCD`、`boot.sdi`、`boot.wim`；`menu.ipxe` 仅显示 Ubuntu ready 项；UDP 67/69/4011 无监听；桌面/移动端截图已检查并修复横向滚动 |
| 2026-06-15 | network_safety_agent | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | resume/send_input/wait | Web UI/HotPE readiness first pass 网络安全收口 | APPROVED | active | 未启 DHCP/ProxyDHCP/TFTP；未开放 UDP 67/69/4011；未修改 TP-Link/OpenWrt/路由/网关/防火墙/DNS；未把 HotPE/Win11 状态展示变成生产 LAN 启用授权 |
| 2026-06-15 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | Web UI/HotPE readiness first pass 安全审计 | APPROVED | active | 无 secret/token 泄漏、无 raw command 注入、无写 API 越权、无路径越界、无商业实现端点、无误导性 HotPE 已可用或 Win11 已安装验证表述 |
| 2026-06-15 | git_audit_agent | 019ec02f-bd09-7520-88db-b57c0d35c296 | resume/send_input/wait | Web UI/HotPE readiness first pass Git/发布范围审计 | APPROVED for free-edition stage/commit preparation | active | 8 个 tracked 文件；`collect-release-evidence.sh` PASS；未发现商业代码、license、混淆产物、真实 ISO/loader/SQLite/.env/secret/runtime ignored data 进入免费版提交范围 |
| 2026-06-15 | network_safety_agent | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | resume/send_input/wait | Ubuntu 长期网络启动方案安全评审 | CONDITIONAL/APPROVED；当前双网卡宿主机运行 `nfs-ganesha` 仅在确认 `111/2049` 不暴露到 `ens18/192.168.1.168` 时可实验；推荐单独 PVE VM 仅接入 `10.101.8.0/24` 运行只读 NFS；HTTP `url=` 仅作为高内存 fallback | active | 禁止 `nfs-kernel-server/rpcbind` 直接暴露生产网；必须验证 `ss`、`rpcinfo`、`showmount`、一键关闭和默认路由不变 |
| 2026-06-15 | image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | resume/send_input/close | 误投启动链路诊断任务 | INVALID；主控误把 Windows/HotPE wimboot 诊断发给 image_factory_agent，随后关闭 pending 任务释放线程；该条不得作为启动链路结论引用 | needs_recheck | 下次需要 image_factory_agent 时必须先恢复验证该固定 ID；若工具返回 not_found，按固定池协议登记 stale 后再处理 |
| 2026-06-15 | boot_entry_agent | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | resume/send_input/wait | Windows/HotPE wimboot 与 0xc000000f 启动链路诊断 | APPROVED；`0xc000000f` 更像 BCD ramdisk 指向或 boot manager 链路不匹配，不像缺目标硬盘；建议先测试 wimboot auto，再用 explicit `bootmgfw.efi` 诊断，避免同一项同时传 `bootx64.efi`/`bootmgfw.efi`/`bootmgr` | active | HotPE minimal 只传 `boot.wim` 不合理；`BCD`、`boot.sdi`、`boot.wim` alias 必须精确；临时保留 `pause` 观察 wimboot 文件映射 |
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
| 2026-06-15 | architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | send_input/wait | Phase 3.3-A Boot Metadata Proxy 产品承诺与只读边界 | APPROVED，允许文档、只读 API、只读 UI、只读预检；BLOCKED for ProxyDHCP/TFTP runtime、UDP 67/69/4011、TP-Link/OpenWrt/路由/网关/防火墙/DNS/Docker 网络变更 | active | 建议对象名 `phase3_3a_boot_metadata_proxy_feasibility`；必须包含 implementation/runtime/service/config/write/production LAN false 字段和产品承诺 |
| 2026-06-15 | network_safety_agent | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | send_input/wait | Phase 3.3-A Boot Metadata Proxy 产品承诺网络安全收口 | APPROVED；未发现生产 LAN、DHCP 接管、ProxyDHCP/TFTP runtime、UDP 67/69/4011、TP-Link/OpenWrt、路由/网关/防火墙/DNS、host network 或 privileged 风险 | active | 仅批准本轮只读产品承诺落地；不批准启用任何网络服务 |
| 2026-06-15 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | resume/send_input/wait | Phase 3.3-A Boot Metadata Proxy 安全审计收口 | APPROVED；Phase 3.3-A 保持 documentation_only_blocked/read_only，未新增 DHCP/ProxyDHCP/TFTP runtime、写 API、配置生成、命令执行或服务启动入口；生产 LAN/UDP 字段仍 false | active | `collect-release-evidence.sh` PASS；公开免费版边界未发现商业私有实现端点或 secret/token 泄漏 |
| 2026-06-15 | git_audit_agent | 019ec02f-bd09-7520-88db-b57c0d35c296 | resume/send_input/wait | Phase 3.3-A Boot Metadata Proxy 发布范围审计 | APPROVED；本轮 diff scope 为 14 个 tracked 文件，暂存区为空，未执行 commit/push；未发现真实 ISO/WIM/EFI/wimboot/SQLite/.env/runtime ignored data 进入提交范围 | active | 当前验证足够支撑免费版 stage/commit 准备；若提交仍需主控执行 stage/commit |
| 2026-06-15 | project_decision_agent | 019ec02f-ac76-7863-899a-3af5498ce444 | resume/send_input/wait | Phase 3.3-A Boot Metadata Proxy 方向收口 | APPROVED；批准当前本轮作为 Phase 3.3-A 文档/只读 API/只读 UI/只读预检交付完成并允许本地 commit；不批准进入 Phase 3.3-B/runtime/服务启用/UDP 端口开放/生产 LAN 测试 | active | 下一阶段必须继续要求隔离实验边界、抓包证据、重新审批和生产 LAN 二次确认 |
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
| 2026-06-13 | runtime | local | command | Phase 3.16 实现和运行态验证 | 新增 `isolated_lab_runtime_authorization_draft` API/UI/预检；HTTP `/`、`/boot/menu.ipxe`、`/api/boot-entry` smoke 均通过 | ready | draft `phase=3.16`、`read_only=true`、`status=draft_blocked_until_evidence_and_approvals`；runtime/network/service/production LAN 字段均 false；UDP 67/69/4011 无监听 |
| 2026-06-13 | network_safety_agent | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | send_input/wait | Phase 3.16 实现后网络安全收口 | APPROVED | active | 未启 DHCP/ProxyDHCP/TFTP；未开放 UDP 67/69/4011；未修改 TP-Link/OpenWrt/路由/网关/防火墙/DNS；草案不是生产 LAN 授权 |
| 2026-06-13 | security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | send_input/wait | Phase 3.16 实现后安全收口 | APPROVED | active | 无写 API、无配置生成、无服务启动、无 secret/token/raw command、无真实 MAC/IP/customer/hostname；免费版/商业版边界未破坏 |
| 2026-06-13 | git_audit_agent | 019ec02f-bd09-7520-88db-b57c0d35c296 | send_input/wait | Phase 3.16 Git/发布范围审计 | APPROVED for free-edition stage/commit preparation | active | `collect-release-evidence.sh` PASS；tracked_changed_count=7；未发现商业代码、license、混淆产物、真实 ISO/loader/SQLite/.env/secret/runtime ignored data 进入免费版 commit 范围 |

## 6. 协作统计与压缩恢复快照

该表是上下文压缩后的第一恢复入口。主控恢复工作时必须先看本表，再根据
“操作流水表”和“结论与进度表”核对细节；不得只凭压缩摘要声称某个 agent
曾经批准、阻断或完成过某项工作。

| role | agent_id | 当前状态 | 流水记录数 | 最近主题 | 当前进度 | 后续复用规则 |
| --- | --- | --- | --- | --- | --- | --- |
| research_agent | 019ec02f-abcd-70b2-9364-cdb120d3d2a4 | active | 4 | PXE/iPXE 客户端等待室可行性研究 | 已返回客户端等待室研究结论：进入 iPXE 并访问 FlashPXE HTTP 脚本后可登记 MAC、UUID、serial、asset、platform、buildarch、IP；固件 PXE/DHCP 阶段对 Web 后台不可见；等待室应返回 iPXE 脚本并限速轮询 | 仅在 TL-ER6120T、iPXE/UEFI、协议或外部资料不确定时复用；同一研究主题继续 send_input/wait，不得新建 research_agent |
| project_decision_agent | 019ec02f-ac76-7863-899a-3af5498ce444 | active | 6 | Phase 3.3-A Boot Metadata Proxy 方向收口 | APPROVED；当前本轮可作为 Phase 3.3-A 文档/只读 API/只读 UI/只读预检交付完成并允许本地 commit；不批准进入 Phase 3.3-B/runtime/服务启用/UDP 端口开放/生产 LAN 测试 | 仅在阶段、收费边界、发布方向、商业边界或重大取舍时复用 |
| network_safety_agent | 019ec02f-ad02-7ae0-8c00-c7baeb46709e | active | 8 | Ubuntu 长期网络启动方案安全评审 | CONDITIONAL/APPROVED；推荐单独 PVE VM 仅接入 `10.101.8.0/24` 提供只读 NFS；当前双网卡宿主机仅可在 `nfs-ganesha` 硬绑定实验网且 `111/2049` 不暴露到 `ens18` 时继续；HTTP `url=` 仅作高内存 fallback | 触及 Compose 网络、端口、DHCP、ProxyDHCP、TFTP、NFS/RPC、路由或网关时必须复用 |
| architecture_agent | 019ec02f-adf7-7162-8721-3b127ac3e51f | active | 25 | admin_reviewed_download 自动安装架构复审 | PASS；`admin_reviewed_download` 未改变不托管安装包边界；Windows 可用受控 MSI/EXE/Office ODT first-boot runner，Ubuntu 仍为 `apt_package`/`download_deb` | 改 API、数据模型、阶段边界或受控 PXE 集成结构时复用 |
| boot_entry_agent | 019ec02f-aedd-78d0-b7ac-efb3f69b6791 | active | 7 | passive wait postinstall 计划领取启动链路复审 | PASS；新增检查验证的是 assignment plan/runner URL、`synaboot-plan-url`、`synaboot-runner-url` 和 NoCloud seed 绑定，不要求 PXE 阶段从 SynaBoot 下载第三方安装包；主动/被动菜单和等待室链路未被破坏 | 改 menu.ipxe、boot assets、loader、PXE/HTTP Boot 链路时复用 |
| storage_agent | 019ec02f-b120-7a92-9823-4e9f386c70ba | active | 2 | ISO-first 存储扫描与派生物可见性侧审 | APPROVED_WITH_FIXES；扫描层保留派生物，库存层只展示源 ISO，菜单层继续使用完整 rows 聚合 | 改镜像扫描、元数据、静态路径、ISO 派生文件边界时复用 |
| image_factory_agent | 019ec02f-b31a-7cb0-a544-314d1092e227 | active | 16 | admin_reviewed_download Windows runner 执行链路复审 | PASS；管理员审核直链可进入 Windows postinstall plan；EXE/MSI/ODT 仍由客户端临时下载、可选 sha256、执行后清理；EXE 三层要求静默参数 | 改 ISO 准备、OS-specific 任务包、autoinstall/postinstall 模板时复用 |
| webui_agent | 019ec02f-b56a-7f83-aa03-0c45c88e8e4b | active | 26 | 软件市场受控静默参数与软件选择 UI 复审 | PASS；新增/维护软件版本表单可编辑安装动作、安装器类型和受控静默参数；创建任务弹窗保留软件市场式多选和已选软件清单；旧文档冲突已修复 | 改 Web UI、镜像页、客户端会话或软件分配体验时复用 |
| tutorial_docs_agent | 019ec02f-b887-7c11-bb50-825e065706cb | active | 1 | 固定会话池重建 | READY，负责 README、管理员教程、架构说明、安全边界、回滚、验收和未授权能力文档口径 | 改教程、交接说明、验收记录时复用 |
| security_audit_agent | 019ec02f-baba-7832-bc4a-ed9d8d696048 | active | 50 | 飞书 Windows MSI 默认软件变体配置复核 | PASS；`feishu-windows-x64` 收敛到 HTTPS CDN 直链、`msi_install`、`installer_type=msi`、`/qn /norestart`；未发现第三方安装包托管、缓存、代理、写入 `/images`、`/boot`、SMB 或 Git 的回归；高完整性场景建议后续维护 `sha256_required` | 下次改路径、权限、脚本执行、Docker、安全边界或商业边界时，继续复用此 agent_id |
| git_audit_agent | 019ec02f-bd09-7520-88db-b57c0d35c296 | active | 7 | Windows EXE 静默安装、预分区取消与安装任务预设增强 diff 审计 | PASS；`PartitionTemplate` 未对外暴露；Windows `exe_install`/MSI/Office ODT 受控 postinstall 与预设归档/恢复通过 diff 审计；完整 release evidence 前 deferred commit/push | milestone 收口、stage/commit/push 前必须复用 |

统计规则：

- “流水记录数”只统计当前 active agent_id 的已登记通信，不把 stale 历史会话混入。
- 若后续追加操作流水，必须同步更新本表的最近主题、当前进度和流水记录数。
- 如果工具层恢复失败，先把对应状态改为 `stale` 并记录流水，再决定是否替换该角色。
- 对未在本表或“结论与进度表”出现的结论，不得在压缩恢复后当成已验证事实引用。

## 7. 结论与进度表

该表用于压缩上下文后快速恢复“哪些结论可引用、哪些不能引用”。

| milestone / topic | roles involved | latest conclusion | reusable evidence | remaining risk |
| --- | --- | --- | --- | --- |
| 飞书 Windows MSI 默认软件变体配置 | security_audit_agent | PASS；飞书 Windows 默认变体可作为已审核 MSI 自动安装项进入 Windows postinstall plan：`feishu-windows-x64` 使用 HTTPS 飞书 CDN 直链、`source_policy=admin_reviewed_download`、`installer_type=msi`、`install_action=msi_install`、`silent_args=/qn /norestart`，且不由 SynaBoot 托管、缓存、代理或写入 `/images`、`/boot`、SMB、Git | 2026-06-24 复用固定 security_audit_agent 返回 PASS；`python3 -m py_compile apps/api/main.py`、`bash scripts/preflight/check-software-assignment-flow.sh`、`bash scripts/preflight/check-public-runtime-boundary.sh`、`npm run build`、`git diff --check` PASS；实验环境 `docker compose up -d --build synaboot-api synaboot-nginx` 后 live API 确认 `feishu-windows-x64 assignable=true` | 飞书 CDN 直链未来可能失效或版本变化；真实自动安装仍依赖 Windows `SetupComplete.cmd -> runner.ps1` 已注入；如需更强完整性，后续应将该变体改为 `sha256_required` 并维护 hash；仍需真实 Windows 客户端验证退出码、重启行为和企业策略 |
| Windows/Ubuntu 自动软件安装深化与管理员审核直链 | architecture_agent、image_factory_agent、security_audit_agent | PASS；Windows 不要求软件必须来自正式软件源，新增 `source_policy=admin_reviewed_download` 支持管理员审核 HTTPS 安装器直链；该策略只适用于独立安装器动作，仍禁止 SynaBoot 托管、缓存或代理第三方安装包。Windows postinstall runner 继续只执行 `msi_install`、`exe_install`、`office_odt_install`，EXE 必须有审核过的静默参数；Ubuntu 仍保持 `apt_package` 和 `download_deb` 边界 | 2026-06-24 固定 architecture_agent、image_factory_agent、security_audit_agent 均 PASS；`corp-tool-windows-x64` 预检覆盖未审核不可分配、审核后可分配、进入 Windows 目标软件目录、创建 assignment、进入 postinstall plan 并保留 `admin_reviewed_download`；`python3 -m py_compile apps/api/main.py`、`bash scripts/preflight/check-software-assignment-flow.sh`、`bash scripts/preflight/check-public-runtime-boundary.sh`、`npm run build`、`git diff --check` PASS | `admin_reviewed_download` 信任管理员审核结果，系统不能自动证明直链属于真实厂商；高风险软件应使用 `sha256_required`；每个 EXE/MSI 仍需真实客户端验证静默参数、退出码、重启行为和是否需要交互桌面；`client_downloads_from_official_source` 字段名后续可演进为更准确的 trusted source 命名 |
| Windows 自动软件安装、Office ODT 与合法 KMS 激活链路 | architecture_agent、image_factory_agent、security_audit_agent | PASS；Windows 带软件任务已从旧的 fail-closed 调整为 `setupcomplete_helper_ready` 下的受控 first-boot postinstall 链路：管理员通过 HotPE/WinPE 显式注入 `SetupComplete.cmd`，安装后的 Windows 首次启动下载 token 保护的 `runner.ps1`，只执行 `msi_install` 与 `office_odt_install` 白名单分支。Office 通过 Microsoft Office Deployment Tool 和受控 Office 产品 ID 安装，不在 SynaBoot 托管 Office 安装包。Windows/Office 激活仅支持管理员自有 KMS 环境变量配置，默认关闭，不内置公共 KMS、不保存产品密钥、不提供破解或绕过授权能力 | 2026-06-21 复用固定 architecture_agent、image_factory_agent、security_audit_agent；三者均 PASS；`check-software-assignment-flow.sh` 覆盖 Windows 软件任务可创建、plan 暴露 `msi_install`/`office_odt_install`、默认 KMS disabled、`public_kms_embedded=false`、runner 包含 MSI/Office ODT/Windows KMS/Office KMS 受控分支、临时文件清理和 per-variant event；`python3 -m py_compile apps/api/main.py`、`bash scripts/preflight/check-software-assignment-flow.sh`、`npm run build`、`git diff --check` PASS | 仍需在真实 Windows 客户端验证 `SetupComplete.cmd` 是否按预期以 SYSTEM 执行；Office ODT 需客户合法授权、管理员审核的 ODT URL、产品 ID/Channel；KMS 需客户自有合法 KMS 并验证 `slmgr.vbs`/`ospp.vbs` 返回码；不同 MSI 的静默参数和重启行为需逐个软件验收 |
| Ubuntu download_deb postinstall runner 可靠性补强 | image_factory_agent、security_audit_agent | PASS；Ubuntu `download_deb` runner 仍只从官方/批准 HTTPS 来源由客户端自行下载，不经过 SynaBoot 托管或代理；下载后使用 1MiB chunk 流式 sha256 校验，安装后或失败时在 finally 中删除临时 `.deb`，降低真实客户端磁盘残留和大文件内存压力 | 2026-06-20 复用固定 image_factory_agent 与 security_audit_agent；两者均 PASS；`check-software-assignment-flow.sh` 增加 runner/HTTP runner 包含流式校验与 `os.remove(path)` 的断言；`py_compile`、`npm run build`、`git diff --check` PASS | 真实客户端端到端执行仍需隔离实验确认；外部 apt repo/keyring、更多软件官方来源解析和 Windows 注入链路仍待后续实现 |
| 软件市场官方来源执行元数据维护 | architecture_agent、security_audit_agent、webui_agent | PASS；软件市场继续是 Apple Store / Windows Store 式应用目录和安装编排器，不托管、不缓存、不代理第三方安装包。管理员可维护 `install_action`、`installer_type`、`package_name`、`download_url`、`silent_args` 等受控元数据；`official_download` 仍只是展示/来源声明，不可自动安装；只有 OS runner 支持、来源合规、审核通过的 `apt_package`、`download_deb`、`msi_install` 才能进入创建安装任务的软件选择和 `resolved_software_plan`。前端新增/维护表单与创建任务弹窗均保留“只保存官方来源链接与受控策略，客户端安装后自行下载”的口径 | 2026-06-20 复用固定 architecture/security/webui 会话；architecture PASS，security PASS，webui 首轮 BLOCKED 文档旧文案后修复并 PASS；`check-software-assignment-flow.sh` 新增 `software_variant_execution_metadata_update=ok`，覆盖官方链接页不可自动安装、维护为官方 deb 后可分配；`py_compile`、`npm run build`、`git diff --check` PASS | Windows 带软件自动安装仍未开放；真实客户端从官方来源下载并安装软件仍需端到端实验；外部 apt repo/keyring、hash/signature 自动维护和更多软件官方来源解析仍待后续实现 |
| postinstall execution_model OS-specific 能力声明 | architecture_agent、security_audit_agent | PASS；postinstall plan 的 `execution_model.allowed_install_actions` 只按目标 OS 暴露当前 runner 真实支持动作：Ubuntu/Linux 为 `apt_package`、`download_deb`，Windows 为 `msi_install`，未知 OS 为空数组；`official_download` 只保留为软件市场 metadata，不作为可执行动作暴露 | 2026-06-20 复用原 architecture_agent 与 security_audit_agent，无新建同职责 subagent；`check-software-assignment-flow.sh` 新增 Ubuntu/Windows plan 断言；`py_compile`、`npm run build`、`git diff --check` 均通过 | Windows 带软件自动安装仍未开放；未来新增 runner action 时必须同步 runner allowlist、plan execution model、预检和安全复审 |
| postinstall 任务生命周期与软件来源边界 | architecture_agent、security_audit_agent | PASS；`DeploymentAssignment.status` 只能由 runner 级 started/completed/failed 推进，variant 级事件只作为单个软件明细和 summary 证据；事件读取使用 `created_at DESC, rowid DESC`，同秒连续回调也能稳定显示最新事件；软件市场仍是 App Store 式应用目录和安装编排器，本地只保存官方来源链接、官方包源/批准企业镜像源、策略和审核记录，不托管、缓存、镜像或代理第三方安装包 | 2026-06-20 复用原 architecture_agent 与 security_audit_agent，无新建同职责 subagent；`check-software-assignment-flow.sh` 覆盖 variant completed/failed 不推进全局状态，runner completed/failed 才推进全局生命周期；`py_compile`、`npm run build`、`git diff --check` 均通过 | Windows 带软件仍需真实 first-boot 注入闭环后才能开放；外部 apt repo/keyring 配置仍未实现，相关软件继续 fail-closed；真实客户端端到端软件安装仍需实验验收 |
| 软件市场与被动装机任务软件选择链路 | architecture_agent、webui_agent、security_audit_agent、image_factory_agent、boot_entry_agent | 方向批准且 postinstall runner 第一阶段复审 PASS：软件市场是类 App Store 的应用目录和安装编排器，只保存官方来源链接、官方包源/批准企业镜像源、安装策略、校验/签名策略和审查状态，不托管、缓存或通过 SynaBoot 静态目录分发第三方安装包；assignment 校验 package/profile/variant 存在性、OS 兼容、审核状态、官方来源策略、本机/内网下载源，并保存 resolved_software_plan；`assignment-options` 已按 boot target 返回 `compatible_software_by_target` 和 `compatible_software_profiles_by_target`，Windows/HotPE 不暴露软件或默认集合，Ubuntu 只暴露 assignable Ubuntu 变体和兼容 profile；创建任务 UI 已改为管理员选择应用，后端通过 `software_package_ids` 按目标 OS 解析到具体可分配变体；同一应用同一 OS 的多可分配版本已通过 `default_for_os` 和 `selection_priority` 确定性选择；`apt_package` 已收紧为 Ubuntu 默认 apt 源中可直接安装的软件，外部 apt repo/keyring 未实现时保持 `apt_repo_not_supported` 不可分配；客户端页已支持单台/批量创建安装任务，runner 通过受控 token 拉取 plan，并在客户端二次校验后执行 OS-specific allowlist action；Ubuntu runner 已补齐 runner 和每个软件变体的 started/completed/failed 事件；Ubuntu NoCloud first-boot bootstrap 已补强 runner 下载有限重试、systemd 失败重启和成功后 token-bearing runner 清理；`/api/ipxe/wait` 被动等待室 HTTP smoke 已覆盖领取 assignment、返回 NoCloud/postinstall iPXE 脚本和 session 状态切到 booting；最近安装任务已按软件变体显示事件状态；Windows 已新增 HotPE helper 注入准备件，但 Windows 带软件仍必须 fail-closed | 2026-06-20 固定岗位均复用原会话；architecture/webui APPROVED_WITH_FIXES；security 同一会话从 BLOCKED 到 PASS；image_factory 和 security 对 postinstall runner 修复复审均 PASS；本轮新增同步 webui/security/image_factory 对“客户端从官方来源自下载，服务器不存包”边界均已接收；批量 assignment 事务、per-session boot token、HTTP endpoint、客户端 session event_summary 隔离、Ubuntu per-variant event、Ubuntu first-boot bootstrap 重试与清理、apt_package 外部 repo fail-closed、被动等待室 HTTP smoke、目标级兼容软件目录、目标级兼容 profile、应用级选择 `software_package_ids`、应用多版本默认/优先级解析、最近任务 UI 变体级展示、Windows HotPE helper 准备件均经对应岗位 PASS；`py_compile`、`npm run build`、`check-software-assignment-flow.sh`、`git diff --check` 通过 | Windows 自动注入到完整安装流程、Ubuntu/Windows 真实客户端端到端安装、hash/signature 自动维护、外部 apt repo/keyring 自动配置仍未完成；Windows 带软件任务在 HotPE helper、Autounattend 或其它注入链路经隔离实验验证前不得开放；未审核、无官方自动化下载链路或缺校验策略的软件不得进入自动安装任务 |
| 软件市场目标能力保护 | boot_entry_agent、image_factory_agent、security_audit_agent、webui_agent | 按固定岗位反馈补齐保护：Windows 当前仅允许 OS-only 安装任务；因 SetupComplete/Unattend/HotPE helper 注入链路尚未真实端到端验证，带软件的 Windows 任务必须 fail-closed；Ubuntu/Linux 可先走 NoCloud first-boot runner；HotPE 不作为普通业务软件自动安装目标；软件市场仍只保存官方来源链接、脚本和校验策略，不存第三方安装包 | 2026-06-20 未新建同职责 subagent；本轮代码将 `software_assignment_enabled` / `postinstall_status` 暴露给 UI 和 API，并在 `create_deployment_assignment` 阻断不支持目标的软件选择；preflight 覆盖 Windows OS-only 可创建、Windows 带软件被拒绝、Ubuntu 软件任务可创建，以及 `windows-hotpe-inject.ps1` 只作为显式 WindowsRoot 的安全准备件；boot_entry_agent/image_factory_agent/security_audit_agent/webui_agent 对相关边界均 PASS 或 BLOCKED 后保持 fail-closed；运行态 HTTP smoke 确认 policy 与 target 能力字段生效 | Windows first-boot 注入链路、Ubuntu 真实客户端端到端软件安装、hash/signature 维护仍需后续隔离验证 |
| 软件市场审核维护闭环 | security_audit_agent、webui_agent、image_factory_agent | 新增最小可用软件变体维护入口：管理员可批准自动安装、退回审核、启用、禁用；后端只维护官方 URL、下载 URL、source/signature/hash/review/enabled/notes 等 metadata，不上传第三方安装包；`assignable` 已收紧为审核通过、来源合规且当前 OS runner 支持 | 2026-06-20 security_audit_agent PASS、webui_agent APPROVED、image_factory_agent PASS；`check-software-assignment-flow.sh` 覆盖 SynaBoot-hosted URL 拒绝、runner 不支持动作不可选、Ubuntu deb approved 后可选；运行态 HTTP smoke 确认 `POST /api/software-variants/chrome-ubuntu-amd64/review` 批准后 assignable=true，恢复 needs_review 后 assignable=false | 仍需软件详情编辑 UI、软件包新增 UI、hash/signature 自动维护和真实 Ubuntu 客户端端到端安装验证 |
| 默认 Ubuntu 官方源软件样例 | security_audit_agent、image_factory_agent、webui_agent | 新增 `curl-ubuntu-apt` 作为默认 approved 的最小验证软件：通过 Ubuntu 官方 apt 仓库安装 `curl`，使用 `official_package_repo` + `repo_signed`，不托管安装包；`software_variants` 新增 `package_name` 字段并自动迁移旧库；APT 官方源安装不再要求 `download_url`，runner 只用 apt 包名和仓库签名策略，下载独立安装器的动作才要求 URL | 2026-06-20 security_audit_agent PASS、image_factory_agent PASS、webui_agent PASS；`check-software-assignment-flow.sh` 覆盖默认 `curl-ubuntu-apt` 创建 Ubuntu 软件任务、空 `download_url` 的 htop/chrome apt 变体、HTTP runner.sh/NoCloud endpoint smoke；运行态 HTTP smoke 确认 `curl-ubuntu-apt approved True curl official_package_repo repo_signed []`，`include_blocked=false` 当前返回 `['curl-ubuntu-apt']` | 还需真实 Ubuntu 客户端完成安装后确认 `curl` 已在目标系统内安装，并把 postinstall events 显示到后台 |
| PXE 客户端等待室与后台任务分配方向 | research_agent | 可行，但只在客户端进入 iPXE 并访问 FlashPXE HTTP 脚本后可被后台登记；固件 PXE/DHCP 阶段对 Web 后台不可见；等待室应通过动态 `#!ipxe` 脚本登记和轮询，管理员分配后返回 OS-specific boot script | `docs/PXE_CLIENT_WAITING_ROOM_PLAN.md`；research_agent 对 iPXE settings、chain、params、sleep 和 PXE 可见性边界给出 APPROVED_RESEARCH | 还未实现 API、数据库模型、后台客户端页、安装器后续回调和任务分配安全审计 |
| ISO-first 管理后台与 OS Boot Strategy 方向 | architecture_agent、storage_agent、webui_agent、research_agent | 管理后台主列表必须只展示源 ISO；派生启动文件仅作为内部就绪证据；未知/PVE/Debian/RHEL 类 ISO 不得误标 ready；PVE 后续需按官方 assistant/answer/pxe 方式单独策略推进 | `docs/ADMIN_ISO_FIRST_DEPLOYMENT_PLAN.md`；architecture/storage/webui 均为 APPROVED_WITH_FIXES；research_agent 返回 Ubuntu casper、Windows WinPE、PVE assistant、Debian netboot、RHEL Anaconda 官方资料结论 | 真实客户端会话回调、软件分配执行、安全上传/删除、PVE 策略实现和 Debian/RHEL 策略实现尚未完成 |
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
| Phase 3.16 isolated lab runtime authorization draft | project_decision_agent、architecture_agent、boot_entry_agent、network_safety_agent、security_audit_agent、git_audit_agent | 已实现 `isolated_lab_runtime_authorization_draft` API/UI/预检只读授权草案；它只描述未来授权对象结构，不是授权结果、状态迁移、运行时配置源、服务启动入口或生产 LAN 许可；`status=draft_blocked_until_evidence_and_approvals`、`read_only=true`，runtime/service/config/write/production LAN/boot tested 均为 false | project_decision/network_safety/security/boot_entry/architecture 预审 APPROVED；network_safety/security/git 收口 APPROVED；`check-phase3-gates.py`、`check-network-safety.sh`、`check-subagent-governance.sh`、`check-compose-config-safe.sh`、`collect-release-evidence.sh`、`node --check`、`git diff --check`、HTTP/API smoke 均 PASS；API `required_evidence=5`、`required_approvals=4`、`boot_evidence_count=5`；UDP 67/69/4011 无监听；`python_bytecode_cache=absent` | 真实 UEFI PXE IPv4 自动启动仍未完成；draft 不是真实授权对象、不是服务实现、不是配置生成器；下一阶段若进入真实授权对象、服务实现、端口开放、抓包、探测或生产 LAN 接入，必须重新触发 research/network_safety/security/project_decision 并取得用户手动确认 |
| Web UI/PXE/HotPE first visual and readiness pass | webui_agent、architecture_agent、project_decision_agent | 已批准并实现第一轮静态 Web UI 信息架构重构与只读 HotPE 聚合 API；Dashboard、菜单页、HotPE 页更清楚展示 HTTP/iPXE、HotPE、Win11 候选、Phase 3 blocked 和真实客户端测试状态；未引入 React/Tailwind/shadcn | `/api/hotpe-readiness` 返回 `blocked_missing_hotpe_artifacts`、HotPE source ISO=true、required_artifacts_present=false、missing 5 项、windows_iso_candidate_count=1；`/api/windows-install-candidates` 返回 Win11 ISO 1 个、direct_ipxe_supported=false；`/boot/menu.ipxe` 只显示 Ubuntu ready 项且 HotPE not ready；public runtime boundary、network safety、compose config、collect release evidence PASS；桌面/移动截图已检查 | HotPE 当前不能判定可用；在 HotPE 中选择上传的 Win11 镜像安装的路径成立但未验证；必须补齐 HotPE 组件并完成真实客户端启动/安装验证 |
| HotPE boot artifact preparation and Windows via HotPE readiness | architecture_agent、boot_entry_agent、image_factory_agent、storage_agent、network_safety_agent、security_audit_agent、project_decision_agent | 已复用固定 agent 协作；新增 UDF 只读提取器、HotPE 本地准备脚本、wimboot 本地导入脚本；从当前 HotPE ISO 提取 `bootmgr`、`BCD`、`boot.sdi`、`boot.wim`，并导入官方 iPXE/wimboot v2.9.0 到运行态；基础 HotPE + Windows ISO 辅助安装被 project_decision_agent 确认为免费版基础装机能力；security_audit_agent 首轮 BLOCKED 公开 `/images/` 下 provenance 泄露风险，已改为非公开 `data/metadata/wimboot-provenance/` 并由 nginx 拒绝 `*.provenance.json` 兜底 | `/api/hotpe-readiness` 返回 `ready_for_client_test`、required artifacts 全 present、`hotpe_menu_ready=true`、`windows_iso_candidate_count=1`、`windows_via_hotpe_candidate=true`；`/boot/menu.ipxe` 已出现 `item hotpe` 与 `item windows_hotpe`；HotPE 五件套和 Win11 ISO HTTP `200 OK` 且 `Accept-Ranges: bytes`；`/images/pe/hotpe/wimboot.provenance.json` 返回 404；UDP `67/69/4011` 无监听 | 真实客户端仍未验证，`client_boot_test_status=not_tested`、`client_install_test_status=not_tested`；下一步必须手动 iPXE/HTTP Boot 进入 HotPE，并在 HotPE 内访问 `http://192.168.1.168:18080/images/windows/` 选择 Win11 ISO，确认 Windows 安装器到达磁盘选择页 |
| Phase 3.3-A Boot Metadata Proxy 产品承诺 | architecture_agent、network_safety_agent、security_audit_agent、git_audit_agent、project_decision_agent | 已完成产品承诺落地：architecture_agent 批准文档/只读 API/只读 UI/只读预检；network_safety_agent 确认无生产 LAN、DHCP 接管、ProxyDHCP/TFTP runtime、UDP 67/69/4011 或网络设备修改风险；security_audit_agent 确认无写 API、配置生成、命令执行、服务启动或 secret/commercial 泄漏；git_audit_agent 确认免费版发布范围可 stage/commit；project_decision_agent 批准作为 Phase 3.3-A 交付完成并允许本地 commit | `phase3_3a_boot_metadata_proxy_feasibility` 只读对象；`PROXYDHCP_FEASIBILITY.md` 和 `PROXYDHCP_PACKET_REVIEW.md` 更新为 Boot Metadata Proxy 边界；`check-phase3-gates.py` 增加产品承诺与 false gate 断言；`collect-release-evidence.sh` PASS；五个固定岗位结论已登记 | 未 push；Phase 3.3-B 仍需用户确认隔离实验环境、抓包证据、重新审批和生产 LAN 二次确认 |
| Web UI modern admin rebuild | security_audit_agent、project_decision_agent、git_audit_agent；webui_agent stale | 2026-06-16 用户明确放宽前端安全审计和技术栈边界，批准管理后台采用 React + TypeScript + Tailwind CSS + shadcn 风格自有组件重构；webui_agent 旧会话 `agent not found`，本轮不登记为新批准；安全边界从“禁止新构建链”调整为“允许前端构建链但继续禁止 CDN runtime、secret 泄漏、商业实现端点和生产 LAN 网络开关” | `apps/web` 迁移到 Vite React；`docker-compose.yml` 改为构建 Web 镜像；`check-public-runtime-boundary.sh` 改为扫描 `apps/web/src`；`npm audit` 0 vulnerabilities；`npm run typecheck` 与 `npm run build` 通过；`collect-release-evidence.sh` PASS；security_audit_agent APPROVED；Figma 文件 `https://www.figma.com/design/0avKsWSSy9LIklnO2tiZy0` 已创建用于现代主题设计 | 仍需完成 Git 审计、本地 commit 和 push；不得把真实镜像、secrets、构建产物或截图混入免费版发布提交 |
| Windows 分区预设撤回与安装任务预设保留 | research_agent、project_decision_agent、webui_agent、security_audit_agent、tutorial_docs_agent、git_audit_agent | 2026-06-24 经调研和固定岗位复审，撤回公开 `PartitionTemplate` 能力，只保留 `InstallPreset = 系统 + 软件组合`；新增“安装任务预设”菜单并支持归档/恢复；旧 SQLite `partition_template_id` 仅作为 legacy 空字段兼容，不暴露 API/UI/任务计划/postinstall plan；Windows 自动安装深化到 `msi_install`、`exe_install`、`office_odt_install` 白名单，EXE 必须配置受控静默参数 | Microsoft Learn 证据：Windows `DiskConfiguration` 因 BIOS/UEFI 配置不同而变化；ConfigMgr `Format and Partition Disk` 支持任务序列变量和自定义脚本动态选择磁盘；project_decision_agent PASS、webui_agent PASS、security_audit_agent PASS、tutorial_docs_agent PASS；git_audit_agent 对 Windows EXE 静默安装、预分区取消与安装任务预设增强 diff 审计 PASS；`python3 -m py_compile apps/api/main.py`、`check-software-assignment-flow.sh`、`npm run build`、`check-public-runtime-boundary.sh`、`docker compose config`、`git diff --check`、docker compose rebuild、HTTP asset/API checks 通过 | 完整 release evidence 仍受宿主 UDP 67/69/4011 监听阻断；未获用户确认前不得停服务或发布；Windows SetupComplete/runner、Office ODT 和各 EXE 静默参数仍需真实客户端逐项验收 |
| HotPE AutoMount 实验运行态资产 | network_safety_agent、image_factory_agent、security_audit_agent | 已实现 HotPE 启动后自动挂载 SMB 与自动加载/打开 SMB 盘 HotPE 功能模块的实验资产生成链路；生成器从 env 读取 SMB 配置，含密脚本只写 `data/secrets/hotpe/automount/`，公开 AutoMount 目录只写无密 manifest/README；映射 `Z:` 镜像仓库、`M:` HotPE 模块、`W:` Windows 镜像目录；白名单 HPM 以 `start` 打开并保留 `M:` 目录兜底 | `check-hotpe-automount-safety.sh` PASS；`py_compile` PASS；`git diff --check` PASS；`docker compose config` PASS；`docker-compose.smb-lab.yml config` PASS；manifest `module_count=9` 且 `boot_wim_sha256_before == boot_wim_sha256_after`；image_factory_agent APPROVED；security_audit_agent 修复 CMD 密码敏感字符后 APPROVED | network_safety_agent 因宿主已有 UDP `67/69/4011` 监听给出 release 级 BLOCKED；本轮代码本身未新增 LAN/DHCP/ProxyDHCP/TFTP/路由/防火墙风险；真实 HotPE 仍需验证 `start \"\" \"M:\\*.HPM\"` 是否等价于模块导入，否则保持自动挂载 + 人工导入 |

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

## 10. 2026-06-16 security_audit_agent 重复创建事故

事故现象：

- SMB/CIFS livefs 任务中，同一安全审计链路连续创建了
  `019ecff1-105d-7652-801d-34a918baa206`、
  `019ecff6-71e9-7d93-ba84-4aeaf80538cc`、
  `019ecff9-0adb-74d0-80d2-22f7486f34ce` 三个
  `security_audit_agent` 会话。
- 三个会话审查的是同一个 diff 的连续修复，属于应复用同一 reviewer 的场景。

根因：

- 主控没有先读取本台账并恢复登记的 `security_audit_agent`。
- `AGENTS.md` 旧措辞使用 `spawn`，容易被误读成每次都新建。
- 主控把 `completed` 当成“会话结束不可继续”，而不是“本次输入完成，可继续
  send_input 复审”。

已修复规则：

- `AGENTS.md` 中的 agent 触发语义已改为 `invoke`，并明确先复用登记会话。
- `PLAN.md` 已补充：`PASS`、`BLOCKED`、`completed` 不代表废弃会话。
- 后续同一轮 BLOCKED 修复必须 `send_input` 回同一个 `agent_id`。
- 只有原会话 `agent not found`、无法恢复、无法接收输入、明显跑偏或用户要求
  重建时，才允许替换一次，并必须先登记 `stale`。
