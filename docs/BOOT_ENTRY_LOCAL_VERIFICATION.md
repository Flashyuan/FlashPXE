# Phase 3 本地只读设备能力确认记录

更新时间：2026-06-12

## 使用边界

本文是 Phase 3.3 解除阻塞前的本地事实收集模板。

只允许管理员人工只读查看并记录结果。

禁止事项：

- 不保存、应用、提交或重启任何网络设备配置。
- 不修改 DHCP 地址池、租约、DNS、默认网关、路由、防火墙、VLAN、NAT。
- 不启用 DHCP Server、ProxyDHCP、TFTP 或 DHCPv6 Boot。
- 不写入 DHCP Option `66/67`。
- 不写入 `next-server`、boot server、bootfile 或 bootfile URL。
- 不配置 Vendor Class 或 Client Architecture 分流。
- 不打开 UDP `67/68/69/4011`。
- 不把真实密码、token、私钥、完整公网账号或敏感截图提交到仓库。

本记录只证明“管理员看到了什么字段或能力”，不代表批准配置。

## 基础信息

```text
记录日期：
记录人：
确认方式：只读查看 / 脱敏截图 / 设备文档 / 其他
是否保存或应用过任何配置：否 / 是（若为是，立即停止并走恢复流程）
是否重启过网络设备：否 / 是
```

## 设备身份

```text
设备厂商：
设备准确型号：
硬件版本：
固件版本：
管理界面语言：
当前主 DHCP 服务器地址：
当前默认网关选项：
当前 DNS 选项：
SynaBoot 服务器 IP：
```

## DHCP 启动字段只读观察

只记录字段是否存在，不填写字段值，不保存配置。

```text
是否看到 Option 66：
字段名称或说明：

是否看到 Option 67：
字段名称或说明：

是否看到 next-server / boot server / siaddr：
字段名称或说明：

是否看到 bootfile name：
字段名称或说明：

是否看到 bootfile URL / HTTP Boot URL：
字段名称或说明：

是否看到 Vendor Class / Option 60：
字段名称或说明：

是否看到 Client Architecture / Option 93：
字段名称或说明：

是否看到可区分 PXEClient 与 HTTPClient 的策略：
字段名称或说明：

是否看到可区分 BIOS PXE、UEFI PXE、UEFI HTTP Boot 的策略：
字段名称或说明：
```

## 现网安全状态只读记录

```text
普通客户端当前是否能获取 DHCP 地址：
普通客户端默认网关是否仍为 192.168.1.4：
普通客户端是否能访问内网：
普通客户端是否能访问互联网：
SynaBoot 是否参与普通 DHCP 租约分配：否 / 是
是否发现新的 UDP 67/68/69/4011 监听：否 / 是
```

## 证据附件记录

只记录脱敏附件名称或说明。

不要提交包含管理员账号、密码、token、公网账号、公网 IP、客户信息或敏感备注的截图。

```text
脱敏截图 1：
脱敏截图 2：
设备文档或固件说明引用：
备注：
```

## 本地结论

以下结论由管理员根据只读观察填写。

```text
Option 66 能力：已确认存在 / 未看到 / 不确定
Option 67 能力：已确认存在 / 未看到 / 不确定
next-server 能力：已确认存在 / 未看到 / 不确定
bootfile URL 能力：已确认存在 / 未看到 / 不确定
Vendor Class 分流能力：已确认存在 / 未看到 / 不确定
Client Architecture 分流能力：已确认存在 / 未看到 / 不确定
是否足以进入隔离环境抓包验证：否 / 是 / 不确定
```

## 后续门禁

本记录完成后，仍不能直接进入生产 LAN 写入配置。

下一步必须重新交由以下 subagents 审查：

- `research_agent`：核对本地事实和外部资料是否一致。
- `network_safety_agent`：判断是否允许进入隔离验证方案。
- `security_audit_agent`：审查文档、证据和风险边界。
- `project_decision_agent`：决定是否继续 TP-Link DHCP Boot Option 路线、继续阻塞或评估受控 ProxyDHCP。

在这些审查完成前，Phase 3.3 继续保持 `BLOCKED`。
