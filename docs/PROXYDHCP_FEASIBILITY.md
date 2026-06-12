# Phase 3.3 ProxyDHCP 可行性评估

更新时间：2026-06-12

## 评估状态与范围

```text
phase：3.3
evaluation_status：documentation_only
candidate：proxydhcp_metadata_only
runtime_status：BLOCKED
implementation_allowed：false
service_enablement_allowed：false
production_lan_testing_allowed：false
```

本文只记录受控 ProxyDHCP 路线的协议可行性、风险和后续门禁。

本文不是实施方案，不包含安装、配置、启动、端口开放、Compose 修改、
生产 LAN 测试或路由器配置教程。

## 硬性禁止事项

- 不实现 ProxyDHCP。
- 不启用 ProxyDHCP。
- 不启用 TFTP。
- 不启用任何 DHCP 服务。
- 不开放 UDP `67/68/69/4011`。
- 不修改 `docker-compose.yml`。
- 不使用 Docker `network_mode: host`。
- 不使用 Docker `privileged: true`。
- 不挂载宿主机 `/`、`/etc` 或 `/var/run/docker.sock`。
- 不修改 TP-Link `192.168.1.1` DHCP lease 行为。
- 不修改 OpenWrt `192.168.1.4` 网关、路由、NAT、防火墙、DNS、VLAN 或 AP。
- 不让 SynaBoot 成为普通 DHCP lease server。

## 现网不变量

- TP-Link `192.168.1.1` 继续作为唯一 DHCP lease server。
- OpenWrt `192.168.1.4` 继续作为默认网关。
- SynaBoot 不分配 IP 地址。
- SynaBoot 不下发 router、gateway、DNS、subnet、lease、NAT 或 route 选项。
- 普通客户端 DHCP、内网访问和外网访问不得受影响。

## 背景

管理员已通过只读截图确认主路由为 `TL-ER6120T`，硬件版本为
`TL-ER6120T 1.0`，当前软件版本为 `1.2.2 Build 240829 Rel.84642n`。

管理员当前未在 TL-ER6120T 管理界面中找到 DHCP Option `66/67` 或等价
boot option 配置入口。因此 Phase 3.3 默认不依赖主路由 DHCP Option 路线。

受控 ProxyDHCP 仅作为 metadata-only 候选方向。它的目标是补充 PXE boot
metadata，不是替代 DHCP，不是接管地址分配，也不是修改默认网关。

## 协议事实

- RFC 2132 定义 Option `66` 为 TFTP server name，Option `67` 为
  bootfile name。
- RFC 4578 定义 PXE / EFI 客户端使用的 Option `93`
  Client System Architecture，可用于识别不同预启动架构。
- dnsmasq 官方手册说明 PXE proxy-DHCP 模式中，另一台 DHCP server
  负责分配 IP，dnsmasq 只提供 PXE netboot 所需信息。
- iPXE 官方 chainloading 文档说明，PXE chainload 的典型路径是先通过
  TFTP 下载 iPXE binary，然后由 iPXE chain 到 HTTP 脚本或菜单。
- iPXE UEFI HTTP Boot 文档说明，UEFI HTTP Boot 可直接通过 HTTP
  chainload iPXE，但需要 DHCP 能识别 HTTP Boot client 并返回 HTTP URI。

参考资料：

- RFC 2132 DHCP Options：<https://datatracker.ietf.org/doc/html/rfc2132>
- RFC 4578 PXE / EFI DHCP Options：<https://www.rfc-editor.org/rfc/rfc4578.html>
- dnsmasq man page：<https://thekelleys.org.uk/dnsmasq/docs/dnsmasq-man.html>
- iPXE chainloading：<https://ipxe.org/howto/chainloading>
- iPXE UEFI HTTP chainloading：<https://ipxe.org/appnote/uefihttp>

## 候选链路

```text
测试机选择 UEFI: PXE IPv4
  -> 从 TP-Link TL-ER6120T 获取普通 DHCP lease
  -> 从 SynaBoot 受控 ProxyDHCP 获取 PXE boot metadata
  -> 通过 TFTP 下载已审查的 iPXE EFI loader
  -> iPXE 通过 HTTP chain 到 SynaBoot 菜单
  -> http://<SERVER_IP>:18080/boot/menu.ipxe
```

该链路仅是未来隔离验证目标，不是当前批准的运行时行为。

## 关键问题清单

- ProxyDHCP 是否能只响应 PXE/UEFI boot client。
- 是否能可靠识别 `PXEClient`、`HTTPClient`、Option `93` 架构值。
- 普通 DHCP 客户端是否会忽略 ProxyDHCP metadata。
- UEFI PXE IPv4 是否需要 UDP `4011` boot service request。
- 目标机器是否只接受 TFTP first-stage NBP。
- `ipxe.efi`、`snponly.efi` 与目标 NIC 固件是否兼容。
- Secure Boot 是否会阻止未签名 iPXE loader。
- 未来若需要 TFTP，是否能严格限制 root 为 `./data/boot/loaders`。

## 风险登记

- 抢答 DHCP 或误发 lease，导致双 DHCP 竞争。
- 下发 gateway、DNS、subnet 或 lease 相关选项，污染普通客户端网络配置。
- UDP `67/4011` 与主 DHCP 或生产广播域发生冲突。
- ProxyDHCP 响应对象无法限制到 PXE/UEFI boot client。
- TFTP root 越界或 loader 来源不可验证。
- Secure Boot、NIC 驱动或固件实现差异导致启动失败。
- 广播域扩散到非测试客户端。
- 需要 Docker host network 或 privileged 才能工作。

## 通过标准

只有未来隔离验证同时满足以下条件，才可进入下一决策门禁：

- TP-Link `192.168.1.1` 仍是唯一 DHCP lease server。
- OpenWrt `192.168.1.4` 仍是默认网关。
- ProxyDHCP 不分配 IP。
- ProxyDHCP 不下发 router、DNS、subnet、lease、NAT、route 或 gateway 变更。
- 普通客户端 DHCP 行为不变。
- 测试客户端可被精确识别。
- TFTP 只服务已审查 loader，且路径限制在 `./data/boot/loaders`。
- HTTP chain 只进入 SynaBoot 菜单。

## 阻塞标准

出现任一情况，Phase 3.3 必须继续 `BLOCKED`：

- 无法限制 ProxyDHCP 响应对象。
- 需要让 SynaBoot 分配普通 DHCP lease。
- 需要修改 TP-Link DHCP lease、DNS、网关或地址池。
- 需要修改 OpenWrt 网关、路由、NAT、防火墙、DNS、VLAN 或 AP。
- 需要在未审批情况下开放 UDP `67/68/69/4011`。
- 需要 Docker `network_mode: host` 或 `privileged: true` 才能工作。
- 无法证明普通客户端 DHCP、内网访问和外网访问不受影响。

## 决策门禁

```text
G0_DOCUMENTATION_ONLY
  当前允许。只写评估结构、证据、风险和问题清单。

G1_RESEARCH_CONFIRMED
  research_agent 确认协议与设备事实。

G2_SAFETY_LAB_APPROVED
  network_safety_agent 只批准隔离验证方案，不批准生产 LAN。

G3_SECURITY_APPROVED
  security_audit_agent 审查服务、端口、loader、路径和权限。

G4_PROJECT_DECISION_APPROVED
  project_decision_agent 决定是否进入隔离验证。

G5_ISOLATED_VALIDATED
  隔离环境抓包证明不发 lease、gateway、DNS 或其它网络污染选项。

G6_PRODUCTION_PILOT_APPROVED
  仍需维护窗口、回滚方案和单客户端灰度。
```

当前只达到 `G0_DOCUMENTATION_ONLY`。

## 后续可交付物

这些交付物仍必须保持只读或离线，不得启用服务：

- ProxyDHCP 报文字段白名单。
- TFTP loader 文件白名单。
- 隔离验证观测清单。
- 抓包判读清单。
- 回滚清单。
- network_safety_agent / security_audit_agent 审查模板。

## 当前结论

受控 ProxyDHCP 在协议上可作为候选方向继续研究。

但 Phase 3.3 运行时仍为 `BLOCKED`。没有隔离验证、网络安全审查、
安全审计和项目决策授权前，SynaBoot 不得启用 ProxyDHCP、TFTP 或任何
UDP `67/68/69/4011` 服务，也不得触碰生产 LAN 的 DHCP、网关或路由配置。
