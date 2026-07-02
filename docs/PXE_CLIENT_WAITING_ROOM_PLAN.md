# PXE 客户端等待室与装机任务分配规划

> 日期：2026-06-18
>
> 目标：让已经进入 FlashPXE/iPXE 的客户端自动登记到管理员后台，并停留在
> 等待界面，等待管理员分配系统安装和软件安装任务。

## 1. 结论

该方向真实可行，但必须区分两个阶段：

- **固件 PXE / UEFI HTTP Boot 阶段**：如果客户端还没有访问 FlashPXE 的
  HTTP 脚本，Web 后台不能直接识别它。只有未来在安全门禁下启用
  DHCP Boot Metadata、ProxyDHCP 或 TFTP 日志时，才可能看到更早阶段。
- **进入 iPXE 后**：客户端访问 FlashPXE HTTP 脚本时，可以通过 URL
  query 或 iPXE request params 主动上报 MAC、UUID、序列号、架构、平台、
  IP 等字段。后台可以据此创建“等待分配”的客户端会话。

因此 Phase 2/当前可落地方案是：

```text
客户端进入 iPXE
  -> 访问 FlashPXE 动态入口
  -> 后台为本次进入创建新的 ClientInstallSession
  -> iPXE 显示等待分配页面并定时轮询
  -> 管理员在后台分配镜像和兼容软件配置
  -> 下一次轮询返回 OS-specific boot script
  -> 进入 Windows / HotPE / Ubuntu / 后续 PVE 安装流程
```

该方案不需要启用 DHCP、ProxyDHCP 或 TFTP，不改变生产 LAN 的主 DHCP 和网关。

## 2. 可识别字段

进入 iPXE 后建议上报以下字段：

- `mac=${net0/mac}`：当前启动网卡 MAC，一阶会话线索。
- `uuid=${uuid}`：SMBIOS UUID，适合辅助资产匹配，但现实中可能缺失或重复。
- `serial=${serial}`：SMBIOS 序列号。
- `asset=${asset}`：资产标签。
- `manufacturer=${manufacturer}`：厂商。
- `product=${product}`：产品型号。
- `platform=${platform}`：固件平台，例如 `efi` 或 `pcbios`。
- `buildarch=${buildarch}`：iPXE 构建架构，例如 `x86_64`。
- `ip=${net0/ip}`：当前 DHCP 获得的客户端 IP。
- `gateway=${gateway}`、`dns=${dns}`：当前网络上下文证据。
- `filename=${filename}`、`next-server=${next-server}`：启动元数据来源证据。
- `user-class=${user-class}`：可辅助判断是否已进入 iPXE 二阶段。

这些字段只能作为“会话识别和资产线索”，不能当作强身份认证。

## 3. 等待室 iPXE 入口形态

优先让服务端返回 iPXE 脚本，而不是 JSON。iPXE 擅长 `chain` 另一个脚本，
不适合在客户端解析复杂业务响应。

推荐入口：

```ipxe
#!ipxe

set server-ip 10.101.8.135
set base-url http://${server-ip}:18080
isset ${platform} || set platform unknown
isset ${buildarch} || set buildarch unknown

:register
chain --autofree ${base-url}/api/ipxe/register?mac=${net0/mac}&uuid=${uuid}&serial=${serial}&asset=${asset}&manufacturer=${manufacturer}&product=${product}&platform=${platform}&buildarch=${buildarch}&ip=${net0/ip} || goto wait

:wait
echo Waiting for deployment assignment from FlashPXE admin console...
echo MAC: ${net0/mac}
echo UUID: ${uuid}
sleep 5
chain --replace ${base-url}/api/ipxe/wait?mac=${net0/mac}&uuid=${uuid}&platform=${platform}&buildarch=${buildarch} || goto wait
goto wait
```

说明：

- URL query 是默认兼容方案，避免依赖 iPXE 是否启用 `PARAM_CMD`。
- 如果确认当前 iPXE 构建支持 `params` / `param`，可切换为 POST 风格参数。
- 轮询间隔建议 5-15 秒，后台必须设置会话 TTL 和限流。
- 服务端未分配任务时返回继续等待的 `#!ipxe` 脚本。
- 服务端已分配任务时返回对应系统的启动脚本。
- 每次客户端选择被动安装都创建新的 session。即使 MAC/UUID 相同，也不能复用
  上一次已分配或已完成的 session，因为同一台机器可能需要多次重装。

## 4. 后台数据模型

### 4.1 ClientInstallSession

记录“已经进入 FlashPXE/iPXE”的客户端会话。

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
- `platform`
- `buildarch`
- `boot_mode`
- `state`
- `selected_image_id`
- `assignment_id`
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

### 4.2 DeploymentAssignment

管理员给单机或批量客户端分配装机任务。

关键字段：

- `id`
- `target_selector`
- `session_ids`
- `source_image_id`
- `software_profile_ids`
- `software_variant_ids`
- `mode`
- `status`
- `approval_state`
- `created_by`
- `created_at`
- `expires_at`

### 4.3 ClientEvent

记录客户端生命周期事件，供总览页和审计使用。

事件建议：

- `ipxe_register`
- `ipxe_poll`
- `assignment_created`
- `assignment_delivered`
- `boot_script_delivered`
- `installer_callback`
- `postinstall_callback`
- `failed`
- `timed_out`

## 5. API 规划

公开给 iPXE 客户端的 endpoint：

- `GET /api/ipxe/register`
  - 登记或更新客户端会话。
  - 返回等待室脚本，并嵌入短期 `session_id` / `token`。
- `GET /api/ipxe/wait`
  - 客户端轮询是否有任务。
  - 未分配时返回等待脚本。
  - 已分配时返回 OS-specific boot script。
- `POST /api/client-events`
  - 供 WinPE、Linux initramfs、安装器或安装后脚本上报状态。

管理员 API：

- `GET /api/client-sessions`
  - 展示当前在线、等待、已分配、超时的客户端，供任务创建时单选或多选。
- `GET /api/assignment-options?session_id=<id>`
  - 返回该会话可分配的系统镜像、boot target 和兼容软件配置。
- `GET /api/assignment-options?session_ids=<id1,id2>`
  - 返回批量任务可用的公共系统镜像、公共兼容软件配置和冲突提示。
- `POST /api/deployment-assignments`
  - 创建单机或批量装机任务。批量任务必须能表达多个 `session_id`。
- `POST /api/deployment-assignments/<id>/cancel`
  - 取消尚未执行的任务。
- `GET /api/software-profiles`
  - 查看可分配的软件配置。
- `GET /api/software-packages`
  - 查看软件市场应用。
- `GET /api/software-packages/<id>/variants`
  - 查看某个应用的 OS-specific 安装变体。

## 6. OS-specific 分配策略

后台只负责把分配结果转换成对应启动脚本：

- Windows：返回已验证的 `wimboot + Windows boot.wim` 安装脚本；进入 PE 后再用
  SMB 访问 Windows ISO 和模块目录。普通业务软件优先在完整 Windows 安装后执行。
- HotPE：返回已验证的 HotPE `wimboot` 启动脚本。
- Ubuntu Desktop：返回 HTTP kernel/initrd + NFS casper livefs 脚本。软件安装计划
  后续通过 autoinstall/cloud-init、late-commands 或首次启动服务执行。
- PVE：先保持 `research_required`，后续按官方 PXE/answer 文件机制进入
  OS-specific strategy。
- Unknown：不返回自动启动脚本，只允许管理员查看源 ISO。

任务创建 UI 要求：

- 客户端页是安装任务创建工作台，不是单纯状态页。
- 管理员可单选一个客户端创建单机任务。
- 管理员可多选多个客户端创建批量任务。
- 创建任务时先选择目标系统镜像，再选择兼容软件。
- 软件选择来自软件市场；应用按目标 OS 自动落到对应 `SoftwareVariant`。

## 7. 安全边界

- MAC、UUID、serial 都可被伪造或缺失，不能作为认证凭据。
- iPXE 公共 endpoint 只能返回当前会话允许的启动脚本，不能暴露任意文件路径。
- `session_token` 必须短期有效，并绑定 MAC/IP/UUID 组合与服务端观察到的来源 IP。
- 管理员分配任务必须走后台鉴权和审计。
- 默认不得自动清盘、分区、格式化或执行危险脚本。
- 软件安装 profile 必须有 manifest、hash、大小限制、执行阶段和风险等级。
- 进入安装器后 iPXE 已不再控制流程，后续状态必须由 WinPE/Linux/installer
  回调补充。
- 生产 LAN 中不得因该功能启用 DHCP、ProxyDHCP、TFTP 或 UDP `67/69/4011`。

## 8. 实施顺序

1. 增加只读模型和 API 草案：`ClientInstallSession`、`DeploymentAssignment`、
   `ClientEvent`、`SoftwareProfile`。
2. 增加 iPXE 动态登记入口，但先不替换正式菜单。
3. 在隔离环境中验证等待室脚本可登记、轮询和返回静态等待页。
4. 后台总览页展示“等待分配客户端”和“可安装 ISO”。
5. 后台客户端页支持选择单机并分配 Windows/HotPE/Ubuntu 已验证策略。
6. 客户端分配面板接入软件 profile 选择；未实现软件市场前先显示兼容空态。
7. 把正式 `menu.ipxe` 入口切换为“登记 -> 等待室 -> 分配启动脚本”。
8. 增加 WinPE / Ubuntu 安装阶段回调草案。
9. 完成 network_safety_agent、security_audit_agent、git_audit_agent 复审后，
   才进入真实环境部署。

软件市场和管理员按钮事件详细规划见：
`docs/SOFTWARE_MARKET_AND_ADMIN_ACTIONS_PLAN.md`。

## 9. 官方依据

- iPXE Settings Reference：<https://ipxe.org/cfg>
- iPXE `chain` command：<https://ipxe.org/cmd/chain>
- iPXE `params` command：<https://ipxe.org/cmd/params>
- iPXE `mac` setting：<https://ipxe.org/cfg/mac>
- iPXE `uuid` setting：<https://ipxe.org/cfg/uuid>
- iPXE `serial` setting：<https://ipxe.org/cfg/serial>
- iPXE `platform` setting：<https://ipxe.org/cfg/platform>
- iPXE `buildarch` setting：<https://ipxe.org/cfg/buildarch>
- iPXE `sleep` command：<https://ipxe.org/cmd/sleep>
