# Phase 3 网络启动回滚清单

更新时间：2026-06-12

## 状态与范围

```text
phase：3.3
checklist_status：documentation_only
runtime_status：BLOCKED
implementation_allowed：false
service_enablement_allowed：false
production_lan_change_allowed：false
```

本文只定义未来经审批后进行隔离验证或单客户端灰度时，必须准备和核对的
回滚证据。

本文不是操作教程，不包含路由器、OpenWrt、Docker、TFTP、ProxyDHCP、
DHCP、抓包或防火墙命令，不批准任何生产 LAN 变更。

## 硬性不变量

- TP-Link `192.168.1.1` 继续作为唯一 DHCP lease server。
- OpenWrt `192.168.1.4` 继续作为默认网关。
- SynaBoot 不分配 IP 地址。
- SynaBoot 不下发 DNS、gateway、route、subnet 或 lease。
- 普通客户端 DHCP、内网访问和外网访问不得受影响。
- 未经后续审查，不启用 DHCP、ProxyDHCP、TFTP 或 UDP `67/68/69/4011`。
- 未经后续审查，不修改 TP-Link、OpenWrt、交换机、AP、VLAN、防火墙、
  NAT、DNS 或路由。

## 回滚前证据

未来任何隔离验证或灰度前，必须先保存以下只读证据：

- 当前 DHCP lease server 是 TP-Link `192.168.1.1`。
- 当前默认网关是 OpenWrt `192.168.1.4`。
- 普通客户端可获取 IP。
- 普通客户端可访问内网。
- 普通客户端可访问互联网。
- SynaBoot 未启用 DHCP、ProxyDHCP 或 TFTP。
- UDP `67/68/69/4011` 未由 SynaBoot 监听。
- 若未来存在受审查的启动元数据变更，必须记录变更前状态和审批编号。

证据不得包含真实密码、token、私钥、公网账号、客户信息或敏感拓扑。

## 回滚触发条件

出现任一情况，未来验证必须停止并进入回滚判定：

- 普通客户端无法续租或获取 IP。
- 普通客户端默认网关不是 `192.168.1.4`。
- 普通客户端 DNS、route、subnet 或 lease 来源异常。
- 普通客户端无法访问内网或互联网。
- SynaBoot 被普通客户端选择为 DHCP server。
- SynaBoot 分配 IP 或下发 gateway、DNS、route、subnet、lease。
- 非测试客户端收到 ProxyDHCP 或 TFTP 响应。
- TFTP 请求越出 `./data/boot/loaders`。
- 需要临时开放未审批端口、host network 或 privileged 才能继续。
- 无法明确区分测试客户端和生产客户端。

## 回滚完成判据

未来只有同时满足以下条件，才能记录为回滚完成：

- 普通客户端 DHCP lease server 恢复为 TP-Link `192.168.1.1`。
- 普通客户端默认网关恢复为 OpenWrt `192.168.1.4`。
- 普通客户端 DNS、route、subnet 和 lease 行为恢复到变更前状态。
- 普通客户端可访问内网。
- 普通客户端可访问互联网。
- SynaBoot 不分配 IP。
- SynaBoot 不下发 gateway、DNS、route、subnet、lease。
- SynaBoot 不向非测试客户端提供 boot metadata。
- SynaBoot 不提供 TFTP 响应。
- UDP `67/68/69/4011` 没有未审批监听。
- 变更记录、触发条件、恢复证据和审查结论已归档。

## 回滚记录模板

```text
回滚编号：
关联 Phase 3 变更：
回滚原因：
维护窗口：
负责人：

回滚前证据：
- DHCP lease server：
- 默认网关：
- 普通终端网络状态：
- 测试启动终端状态：
- boot metadata 状态：
- ProxyDHCP 状态：
- TFTP 状态：

回滚期间记录：
- 开始时间：
- 影响对象类别：
- 回滚前状态：
- 回滚后状态：
- 异常观察：
- 是否中止后续 Phase 3 验证：

回滚后证据：
- DHCP lease server：
- 默认网关：
- 普通终端 IP 获取：
- 普通终端内网访问：
- 普通终端互联网访问：
- SynaBoot DHCP lease 分配状态：
- boot metadata 状态：
- ProxyDHCP 状态：
- TFTP 状态：
- 异常是否消失：

审查结论：
- network_safety_agent：
- security_audit_agent：
- project_decision_agent：
- Phase 3 状态：
```

该模板只用于记录证据，不用于记录具体命令、点击路径或网络设备操作步骤。

## 失败分级

```text
P0_LAN_IMPACT
  普通客户端 DHCP、网关、内网或互联网受影响。

P1_WRONG_DHCP_AUTHORITY
  SynaBoot 或其它非 TP-Link 设备被普通客户端选为 DHCP server。

P2_BOOT_METADATA_LEAK
  非测试客户端收到 ProxyDHCP/TFTP boot metadata。

P3_TEST_CLIENT_ONLY_FAILURE
  仅测试客户端未进入 SynaBoot 菜单，普通客户端不受影响。

P4_EVIDENCE_INCOMPLETE
  证据不足，不能证明影响范围或恢复状态。
```

任何 `P0`、`P1` 或 `P2` 都必须保持 Phase 3.3 `BLOCKED`。

## 后续审批要求

回滚完成不代表可以继续推进。

未来若要再次进入隔离验证，必须重新经过：

- `research_agent` 复核事实和失败原因。
- `network_safety_agent` 审查新的隔离验证方案。
- `security_audit_agent` 审查服务、端口、路径、loader 和证据风险。
- `project_decision_agent` 决定是否继续、降级或停止 Phase 3.3。

任一安全 agent 输出 `BLOCKED` 时，相关工作必须停止。

## 当前结论

当前只完成回滚判据文档。

Phase 3.3 仍为 `BLOCKED`。本文不批准启用 DHCP、ProxyDHCP、TFTP，
不批准开放 UDP `67/68/69/4011`，不批准修改生产 LAN，也不批准执行
任何路由器、OpenWrt、Docker 或防火墙变更。
