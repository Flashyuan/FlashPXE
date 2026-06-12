# Phase 3 启动入口集成说明

更新时间：2026-06-12

## 当前结论

Phase 3 自动网络启动入口仍处于门禁状态。

当前只允许使用已经实现的只读能力：

- 查看 `/api/boot-entry` 启动入口模型。
- 查看 `/api/boot-assets` 固定白名单 loader 元数据。
- 通过 `http://<SERVER_IP>:18080/boot/menu.ipxe` 使用 HTTP/iPXE 菜单。
- 通过手动 iPXE USB/ISO/EFI 或手动 UEFI HTTP Boot 进入 SynaBoot。

当前不允许：

- 启用 DHCP Server。
- 启用 ProxyDHCP。
- 启用 TFTP。
- 写入 DHCP Option `66/67`。
- 写入 `next-server`、boot server 或 bootfile URL。
- 配置 Vendor Class 或 Client Architecture 分流。
- 修改 TP-Link、OpenWrt、交换机、AP、VLAN、DNS、路由或防火墙。
- 打开 UDP `67/68/69/4011`。
- 将 SynaBoot 配置成普通 DHCP 地址分配方。

## Phase 3.3 门禁状态

Phase 3.3 暂停，当前不得进入生产可启用设计。

管理员已通过只读截图确认设备为 `TL-ER6120T`，硬件版本为
`TL-ER6120T 1.0`，当前固件为 `1.2.2 Build 240829 Rel.84642n`。
但管理员当前未在管理界面中找到 DHCP Option `66/67` 或等价 boot option
配置入口，因此 Phase 3.3 默认不依赖主路由 DHCP Option 路线。

下一步只允许转入受控 ProxyDHCP 可行性评估，且不代表允许实现或启用
ProxyDHCP、TFTP 或任何 DHCP 服务。

必须先确认以下事实：

- DHCP 页面是否支持 Option `66`。
- DHCP 页面是否支持 Option `67` 或等价 Boot File 字段。
- 是否支持 `next-server`、boot server 或 `siaddr`。
- 是否支持按 Vendor Class 区分 `PXEClient` 与 `HTTPClient`。
- 是否支持按 Client Architecture 区分 BIOS PXE、UEFI PXE、UEFI HTTP Boot。

在完成新的研究、安全审查和项目决策前，不得设计或实现生产可启用的
TFTP/ProxyDHCP 路线。

## 管理员只读确认清单

管理员可以只读登录网络设备管理界面，记录以下信息。

不要保存配置，不要点击应用，不要修改 DHCP 地址池、DNS、网关或路由。

建议把完整记录填写到 `BOOT_ENTRY_LOCAL_VERIFICATION.md`。

```text
设备型号：
硬件版本：
固件版本：
当前 DHCP 服务器地址：
当前默认网关选项：
是否存在 Option 66：
是否存在 Option 67：
是否存在 next-server / boot server：
是否存在 bootfile URL：
是否存在 Vendor Class / Option 60 匹配：
是否存在 Client Architecture / Option 93 匹配：
是否支持按客户端类型下发不同启动参数：
备注：
```

建议同时保存脱敏截图或文字记录。

截图中不要包含管理员密码、公网账号、真实 token 或敏感备注。
本阶段不得填写、保存、应用或测试任何网络设备配置。

## 可交给网络管理员的目标参数

以下参数仅用于沟通目标，不代表当前已经批准配置。
管理员当前只确认设备是否存在对应能力，不写入这些参数。

```text
SynaBoot HTTP 服务：
http://<SERVER_IP>:18080/

iPXE 菜单：
http://<SERVER_IP>:18080/boot/menu.ipxe

UEFI HTTP Boot loader：
http://<SERVER_IP>:18080/boot/loaders/ipxe.efi

UEFI PXE loader 候选：
snponly.efi 或 ipxe.efi

Legacy BIOS PXE loader 候选：
undionly.kpxe
```

这些参数只有在 `network_safety_agent` 与 `security_audit_agent` 审查通过后，
才能进入隔离环境验证或维护窗口实施。

## 推荐验证顺序

1. 完成本地只读设备能力确认。
   记录模板见 `BOOT_ENTRY_LOCAL_VERIFICATION.md`。
2. 若设备能力足够，先由 `network_safety_agent` 审查 DHCP boot option 方案。
3. 若方案通过，只在隔离测试环境或单台测试机验证。
4. 抓包确认 DHCP Offer 中的 boot metadata 是否符合预期。
5. 验证普通终端仍能获取正确 IP、DNS 和默认网关 `192.168.1.4`。
6. 验证测试机进入 SynaBoot 菜单。
7. 若任一步失败，撤销 boot option 或保持相关能力关闭。

## 本地安全验证命令

以下命令只用于检查本仓库和本机服务状态。

```bash
git status --short
bash scripts/preflight/check-network-safety.sh
docker compose config
ss -lntu | grep -E ':(67|68|69|4011)\b' || true
rg -n "network_mode: host|privileged: true|67:|68:|69:|4011:|dnsmasq|proxydhcp|tftp|dhcp" docker-compose.yml scripts apps config docs PLAN.md
```

如果需要抓包，只能在隔离测试环境中执行，并且需要明确网络安全审批。

```bash
sudo tcpdump -i <isolated-iface> -nn -vvv -s0 \
  'udp and (port 67 or port 68 or port 69 or port 4011)'
```

## 回滚原则

任何 Phase 3 网络启动变更都必须可回滚。

回滚动作应满足：

- 恢复变更前的 DHCP boot option 状态。
- 保持主 DHCP 仍由 TP-Link 负责。
- 保持默认网关仍为 `192.168.1.4`。
- 关闭任何临时启用的 ProxyDHCP 或 TFTP。
- 再次验证普通终端可获取 IP、访问内网和访问互联网。

## 当前安全边界

SynaBoot 当前只提供 HTTP/iPXE 菜单与镜像仓库。

自动 PXE/HTTP Boot 入口集成必须等待本地设备能力确认、隔离验证方案、
网络安全审查和安全审计全部通过后，才能进入下一阶段。
