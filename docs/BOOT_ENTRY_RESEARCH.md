# Phase 3 Boot Entry Research

更新时间：2026-06-12

## 研究问题

TP-Link `TL-ER6120T / TL-ER6120` 是否能通过 DHCP Option `66/67`、
`next-server`、bootfile URL、Vendor Class 或 Client Architecture 区分，
让 UEFI PXE IPv4 / HTTP Boot 自动进入 SynaBoot。

## 资料来源

- TP-Link TL-ER6120 V3 下载页 / 固件说明：
  <https://www.vigi.com/us/support/download/tl-er6120/>
- TP-Link TL-ER6120 V3+ 网络配置指南：
  <https://www.tp-link.com/us/configuration-guides/configuring_network/>
- TP-Link TL-ER6120 V1 用户手册：
  <https://static.tp-link.com/res/down/doc/TL-ER6120_V1_UG.pdf>
- TP-Link TL-ER6120T 产品 / 下载页：
  <http://www.tp-link.com.cn/product_2749.html?v=download>
- TP-Link Omada DHCP Options 文档：
  <https://support.omadanetworks.com/au/document/13251/>
- RFC 2132 DHCP Options：
  <https://datatracker.ietf.org/doc/html/rfc2132>
- RFC 4578 PXE / EFI DHCP Options：
  <https://datatracker.ietf.org/doc/html/rfc4578>
- SUSE UEFI HTTP Boot 文档：
  <https://documentation.suse.com/sles/15-SP6/html/SLES-all/cha-deployment-prep-uefi-httpboot.html>
- iPXE DHCP option tags：
  <https://dox.ipxe.org/group__dhcpopts.html>

## 已确认事实

- TL-ER6120 V3 固件说明确认新增 DHCP Option `66`、`150`、`159`、
  `160`、`176`、`242` 支持。
- 同一官方固件说明未确认 Option `67`、`next-server`、bootfile URL、
  Vendor Class 策略匹配或 Client Architecture 区分能力。
- TL-ER6120 V3+ 官方配置指南公开列出的 DHCP 页面能力包含 Option `60`
  和 Option `138`，未明确列出 Option `66/67` 或 Network Boot。
- TL-ER6120T 官方页面确认具备 DHCP 服务器功能，但公开资料未确认
  Option `66/67`、bootfile URL、`next-server` 或客户端类型分流能力。
- RFC 2132 定义 Option `66` 为 TFTP server name，Option `67` 为
  bootfile name，Option `60` 为 Vendor Class Identifier。
- RFC 4578 定义 PXE / EFI 客户端架构 Option `93`。
- UEFI HTTP Boot 的 DHCPv4 典型路径需要识别 `HTTPClient`，并返回
  HTTP bootfile URL。

## 未确认项

以下内容必须在本地只读确认，不能从公开资料直接假设：

- TL-ER6120T V1.0 固件是否支持自定义 DHCP Option `66/67`。
- TL-ER6120T 是否支持 bootfile URL、`next-server` 或 `siaddr`。
- TL-ER6120T / TL-ER6120 V3 是否能按 `PXEClient` / `HTTPClient`
  Vendor Class 返回不同启动参数。
- TL-ER6120T / TL-ER6120 V3 是否能按 Client Architecture Option `93`
  区分 BIOS PXE、UEFI PXE、UEFI HTTP Boot。
- 仅配置 Option `66` 时，PXE 客户端能否获得正确 boot server 和
  bootfile。该项需要隔离环境抓包验证。

## 对 SynaBoot 的影响

- 当前不能把 TL-ER6120T / TL-ER6120 视为可靠的 Phase 3 自动引导入口。
- UEFI HTTP Boot IPv4 需要 `HTTPClient` 与 HTTP bootfile URL，公开证据不足。
- UEFI PXE IPv4 可能具备部分基础，但缺少 Option `67`、`next-server`
  和架构分流证据。
- 不应更换主 DHCP，也不应让 SynaBoot 分配普通 DHCP 租约。
- Phase 3 应继续保持 TFTP / ProxyDHCP 默认关闭、显式启用、可回滚、
  经 network_safety_agent 与 security_audit_agent 双审查。

## 下一步

1. 管理员只读登录 TL-ER6120T Web UI，确认 DHCP 页面是否存在：
   - Option `66`
   - Option `67`
   - Network Boot / Boot File
   - Next Server / boot server
   - Vendor Class / Option `60` 策略
   - Client Architecture / Option `93` 策略
2. 若 UI 显示可配置，不直接接入生产客户端。
3. 后续验证应在隔离测试 VLAN 或单机直连环境抓包确认 DHCP Offer。
4. 若 TP-Link 无法可靠提供完整 boot metadata，进入受控 ProxyDHCP
   方案评估；ProxyDHCP 只允许提供 boot metadata，不分配 IP。
