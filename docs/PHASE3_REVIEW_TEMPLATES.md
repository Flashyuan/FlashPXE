# Phase 3.3 审查模板

更新时间：2026-06-12

## 状态与范围

```text
phase：3.3
template_status：documentation_only
runtime_status：BLOCKED
implementation_allowed：false
service_enablement_allowed：false
production_lan_change_allowed：false
```

本文只定义未来 Phase 3.3 隔离验证或灰度前，`network_safety_agent` 与
`security_audit_agent` 应如何记录审查结论。

本文不是实施方案，不包含路由器、OpenWrt、Docker、TFTP、ProxyDHCP、
DHCP、抓包、防火墙或端口配置命令，不批准任何生产 LAN 变更。

## 共用输入材料

每次审查前，必须提供以下材料。缺任一项时，结论应为 `BLOCKED`
或 `NEEDS_RESEARCH`：

- 关联 Phase 3 变更说明。
- 目标环境：文档、隔离验证、单客户端灰度或生产候选。
- 当前 DHCP lease server 证据。
- 当前默认网关证据。
- `BOOT_ENTRY_LOCAL_VERIFICATION.md` 的本地只读事实。
- `PROXYDHCP_FEASIBILITY.md` 的当前门禁状态。
- `PROXYDHCP_PACKET_REVIEW.md` 的报文字段判读结论。
- `TFTP_LOADER_SCOPE.md` 的 loader 范围判读结论。
- `PHASE3_ROLLBACK_CHECKLIST.md` 的回滚证据准备状态。
- 变更 diff 或设计文档。
- 已知失败模式和回滚触发条件。

## network_safety_agent 审查模板

```text
审查编号：
审查日期：
审查对象：
审查范围：
结论：APPROVED_DOCUMENTATION_ONLY / APPROVED_FOR_ISOLATED_REVIEW / APPROVED_WITH_EXTERNAL_CHANGE / BLOCKED / NEEDS_RESEARCH

LAN 不变量：
- TP-Link 192.168.1.1 是否仍为唯一 DHCP lease server：
- OpenWrt 192.168.1.4 是否仍为默认网关：
- 普通客户端 DHCP 是否不受影响：
- 普通客户端内网访问是否不受影响：
- 普通客户端互联网访问是否不受影响：

禁止项核对：
- 是否启用 DHCP：
- 是否启用 ProxyDHCP：
- 是否启用 TFTP：
- 是否开放 UDP 67/68/69/4011：
- 是否修改 TL-ER6120T：
- 是否修改 OpenWrt：
- 是否修改 DNS、路由、NAT、防火墙、VLAN、AP：
- 是否使用 host network：
- 是否使用 privileged：
- 是否让 SynaBoot 分配普通 DHCP lease：

隔离边界：
- 是否仅限隔离 VLAN 或单客户端实验网：
- 是否禁止生产 LAN 测试：
- 是否有普通客户端对照证据：
- 是否有回滚证据清单：

审查理由：

阻塞原因：

后续条件：
```

### network_safety_agent BLOCKED 条件

出现任一情况必须 `BLOCKED`：

- 无法证明主 DHCP 仍为 TP-Link `192.168.1.1`。
- 无法证明默认网关仍为 OpenWrt `192.168.1.4`。
- 需要 SynaBoot 分配普通 DHCP lease。
- 需要修改 TL-ER6120T DHCP lease、DNS、网关或地址池。
- 需要修改 OpenWrt 网关、路由、NAT、防火墙、DNS、VLAN 或 AP。
- 需要未审批开放 UDP `67/68/69/4011`。
- 需要 Docker `network_mode: host` 或 `privileged: true` 才能继续。
- 无法限制 ProxyDHCP/TFTP 响应对象。
- 缺少回滚证据。

## security_audit_agent 审查模板

```text
审查编号：
审查日期：
审查对象：
审查范围：
结论：APPROVED_DOCUMENTATION_ONLY / APPROVED_FOR_ISOLATED_REVIEW / BLOCKED / NEEDS_RESEARCH

服务与端口：
- 是否新增服务：
- 是否新增端口：
- 是否新增 UDP 67/68/69/4011：
- 是否仍默认关闭：

路径与文件：
- TFTP root 是否限制在 ./data/boot/loaders：
- loader 是否固定白名单：
- 是否排除 symlink 和父目录 symlink：
- 是否排除目录遍历、绝对路径、通配符和隐藏文件：
- 是否排除 ISO/WIM/ESD/IMG/VHD/VHDX 和镜像目录：

loader 证据：
- 是否有 SHA256：
- 是否有大小和 mtime：
- 是否有来源说明：
- 是否有 Secure Boot 风险说明：
- 是否有人工审查记录：

API / UI：
- 是否只读：
- 是否新增高风险按钮：
- 是否需要 admin token：
- 是否存在 XSS、路径穿越或命令注入风险：

敏感信息：
- 是否包含 token、密码、私钥或真实账号：
- 是否包含敏感截图或客户信息：
- 是否包含完整 MAC 清单或敏感拓扑：

审查理由：

阻塞原因：

后续条件：
```

### security_audit_agent BLOCKED 条件

出现任一情况必须 `BLOCKED`：

- 文档或代码包含可复制执行的 TFTP/ProxyDHCP/DHCP 启用步骤。
- 新增服务默认开启。
- loader 可由未审查来源下载、生成、替换或执行。
- TFTP 可访问白名单外路径。
- symlink、目录遍历或绝对路径可进入 boot loader 范围。
- Web UI 暴露未经确认的高风险开关。
- 提交包含真实 token、密码、私钥、路由器账号或敏感截图。
- 绕过 `network_safety_agent` 或 `project_decision_agent` 授权。

## 允许的结论语义

```text
APPROVED_DOCUMENTATION_ONLY
  当前材料只满足文档门禁要求；不代表批准隔离验证、服务启用或生产 LAN。

APPROVED_FOR_ISOLATED_REVIEW
  当前材料可进入下一轮隔离验证方案审查；不代表批准执行隔离验证。

APPROVED_WITH_EXTERNAL_CHANGE
  仅表示存在需要外部管理员在未来审批窗口处理的事项；
  SynaBoot 当前仓库不得自动执行这些事项。

NEEDS_RESEARCH
  事实不足，必须回到 research_agent 或本地只读确认。

BLOCKED
  存在安全、网络或证据缺口。相关实现、验证或灰度必须停止。
```

## 禁止写入审查模板的内容

- 路由器后台菜单路径。
- OpenWrt 配置步骤。
- Docker Compose 服务配置。
- TFTP、ProxyDHCP、DHCP 启停命令。
- UDP `67/68/69/4011` 开放步骤。
- Option `66/67` 实操教程。
- 真实 token、账号、密码、私钥、客户信息或敏感截图。

## 当前结论

当前只完成审查模板。

Phase 3.3 仍为 `BLOCKED`。本文不批准启用 DHCP、ProxyDHCP、TFTP，
不批准开放 UDP `67/68/69/4011`，不批准修改生产 LAN，也不批准执行
任何路由器、OpenWrt、Docker 或防火墙变更。
