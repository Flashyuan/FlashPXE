# Phase 3.3 ProxyDHCP 报文字段与抓包判读清单

更新时间：2026-06-12

## 状态与范围

```text
phase：3.3
review_status：documentation_only
runtime_status：BLOCKED
implementation_allowed：false
service_enablement_allowed：false
production_lan_capture_allowed：false
```

本文只定义未来隔离验证时的报文字段判读标准。

本文不是抓包教程，不包含命令，不包含 ProxyDHCP、TFTP、DHCP 或
docker-compose 的配置步骤，也不批准在生产 LAN 启动、监听或抓包。

## 资料依据

- RFC 2131 定义 DHCP 用于传递配置参数和分配网络地址，并明确主机不应在
  未经管理员显式配置时充当 DHCP server。
- RFC 2132 定义 DHCP options，其中 Option `66` 为 TFTP server name，
  Option `67` 为 bootfile name。
- RFC 4578 定义 PXE / EFI 客户端使用的 Option `93`
  Client System Architecture。
- TianoCore PXE 说明将 IPv4 PXE 流程拆为 DHCP 扩展选项阶段、
  Boot Server 请求阶段和 TFTP 下载 NBP 阶段。
- iPXE 资料记录了 iPXE / Etherboot 相关 DHCP option tag，可作为未来
  判读 iPXE 专用 boot metadata 的参考。

参考：

- RFC 2131 DHCP：<https://datatracker.ietf.org/doc/html/rfc2131>
- RFC 2132 DHCP Options：<https://datatracker.ietf.org/doc/html/rfc2132>
- RFC 4578 PXE / EFI DHCP Options：<https://www.rfc-editor.org/rfc/rfc4578.html>
- TianoCore PXE notes：<https://github.com/tianocore/tianocore.github.io/wiki/PXE>
- iPXE DHCP option tags：<https://dox.ipxe.org/group__dhcpopts.html>

## 现网不变量

- TP-Link `192.168.1.1` 必须继续作为唯一 DHCP lease server。
- OpenWrt `192.168.1.4` 必须继续作为默认网关。
- SynaBoot 不得分配 IP。
- SynaBoot 不得下发 subnet、router、gateway、DNS、lease、NAT、route 等
  普通客户端网络配置。
- SynaBoot 不得影响普通客户端 DHCP、内网访问或外网访问。

## 未来隔离验证的观察对象

未来如果进入隔离验证，只允许观察以下对象：

- 测试机发出的 PXE/UEFI DHCP Discover / Request。
- TP-Link 或隔离 DHCP server 发出的普通 DHCP lease Offer / Ack。
- SynaBoot 候选 ProxyDHCP 仅用于 boot metadata 的响应。
- 测试机向 Boot Server 发出的后续 PXE 请求。
- 测试机下载已审查 boot loader 的 TFTP 请求。
- iPXE 后续访问 SynaBoot HTTP 菜单的请求。

当前生产 LAN 中不得启用这些验证行为。

## 允许出现的 SynaBoot ProxyDHCP 语义

未来隔离验证中，SynaBoot 候选 ProxyDHCP 响应只能表达 boot metadata：

- 响应对象是 PXE/UEFI boot client。
- 响应内容只帮助测试机找到 boot server 和 bootfile。
- DHCP/BOOTP header 中 `xid` 和 `chaddr` 与客户端请求匹配。
- `yiaddr` 必须为 `0.0.0.0`，不得表现为地址分配。
- 可包含 PXE/EFI 识别相关信息，例如 Vendor Class、Client Architecture
  或 boot server / bootfile 相关 metadata。
- 可指向已审查的 iPXE EFI loader。
- 可将后续链路收敛到
  `http://<SERVER_IP>:18080/boot/menu.ipxe`。
- 可观察 Option `60`、`66`、`67`、`93`、`94`、`97`、PXE vendor option
  或 iPXE 专用 boot metadata，但不得承载普通网络配置。

## 禁止出现的 SynaBoot 字段或语义

只要未来隔离抓包中看到以下任一项来自 SynaBoot，必须判定为 `BLOCKED`：

- `yiaddr` 表示给客户端分配普通 IP lease。
- DHCP Option `1` Subnet Mask。
- DHCP Option `3` Router / Default Gateway。
- DHCP Option `6` DNS Server。
- DHCP Option `15` Domain Name。
- DHCP Option `28` Broadcast Address。
- DHCP Option `51` IP Address Lease Time。
- DHCP Option `54` Server Identifier 使普通客户端选择 SynaBoot 作为 lease server。
- DHCP Option `58/59` Renewal / Rebinding Time。
- DHCP Option `121` Classless Static Route。
- DHCP Option `249` Microsoft Classless Static Route。
- DHCPNAK。
- 可被客户端用于完成地址租约的 DHCPACK。
- 任何网关、DNS、NAT、route、lease、地址池或普通客户端网络配置。
- 对非 PXE/UEFI boot client 的响应。
- 对生产 LAN 广播域内普通客户端的响应。
- 客户端 DHCPREQUEST 选择 SynaBoot 作为普通 lease server。

## 应由主 DHCP 提供的字段

以下字段必须只由 TP-Link `192.168.1.1` 或未来隔离 DHCP server 提供：

- 普通客户端 IP lease。
- Subnet Mask。
- Default Gateway，且生产 LAN 必须保持 OpenWrt `192.168.1.4`。
- DNS Server。
- Lease Time。
- Renewal / Rebinding Time。
- DHCP Server Identifier。

SynaBoot 不得提供这些字段。

## PXE/UEFI 客户端识别

未来隔离验证必须证明 SynaBoot 候选 ProxyDHCP 至少能区分：

- PXE/UEFI boot client。
- 普通 DHCP client。
- BIOS PXE、UEFI PXE 或其它架构差异。

可观察依据包括：

- Vendor Class / Option `60`。
- Client System Architecture / Option `93`。
- PXE 相关扩展选项。
- 客户端后续是否请求 bootfile / NBP。

如果无法限制响应对象，Phase 3.3 必须继续 `BLOCKED`。

## 判读结果

### APPROVED_FOR_NEXT_GATE

仅当所有条件同时满足，才可进入下一门禁：

- SynaBoot 没有分配 IP。
- SynaBoot 没有下发 router、gateway、DNS、subnet、lease 或 route。
- 普通客户端只接受主 DHCP 的 lease。
- 测试 PXE/UEFI client 可被精确识别。
- SynaBoot 报文中 `yiaddr` 保持 `0.0.0.0`。
- boot metadata 只指向已审查 loader 和 SynaBoot HTTP 菜单。
- 没有生产 LAN 客户端参与验证。

### BLOCKED

出现任一情况必须阻塞：

- SynaBoot 抢答普通 DHCP。
- SynaBoot 被普通客户端选为 DHCP server。
- SynaBoot 发送可完成普通地址租约的 DHCPACK 或 DHCPNAK。
- SynaBoot 下发网关、DNS、subnet、lease 或 route。
- ProxyDHCP 响应对象无法限制。
- TFTP 请求越出 `./data/boot/loaders` 范围。
- 需要 host network、privileged 或生产 LAN 试跑才能继续。

### INCONCLUSIVE

证据不足时不得升级门禁：

- 抓包缺少完整 Discover / Offer / Request / Ack 链路。
- 看不到 Option `60`、Option `93` 或 PXE 扩展选项。
- 无法区分主 DHCP 与 SynaBoot 响应来源。
- 未同时验证普通客户端 DHCP 行为。
- 未验证默认网关仍为 `192.168.1.4`。

## 证据保存要求

未来如进入隔离验证，只能保存脱敏证据：

- 不保存真实公网账号、token、密码或私钥。
- 不提交完整 MAC 清单、客户信息或敏感网段拓扑。
- 可记录字段存在性、来源 IP、是否违反禁止项和判读结论。
- 证据必须附带验证环境说明，明确不是生产 LAN。

## 当前结论

当前只完成报文字段判读标准。

Phase 3.3 仍为 `BLOCKED`。本文不批准启用 DHCP、ProxyDHCP、TFTP，
不批准开放 UDP `67/68/69/4011`，不批准修改 TP-Link、OpenWrt 或
Docker 网络配置，也不批准生产 LAN 测试。
