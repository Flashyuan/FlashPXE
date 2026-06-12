# SynaBoot 网络安全边界

SynaBoot Phase 2 是零侵入 HTTP/iPXE Boot 平台，默认只开放 `18080/tcp`。

## 已批准范围

- Web UI：`http://192.168.1.168:18080/`
- iPXE 菜单：`http://192.168.1.168:18080/boot/menu.ipxe`
- 镜像仓库：`http://192.168.1.168:18080/images/`
- Docker 使用默认 bridge 网络
- Nginx 反代内部 API，并静态提供 `/images/` 与 `/boot/`
- `/images/` 禁止跟随软链接，镜像路径限制在 `data/images`

## 禁止项

- 不启用 DHCP、ProxyDHCP、TFTP
- 不开放 UDP `67/68/69/4011`
- 不修改路由器、OpenWrt、TP-Link、交换机、AP、VLAN、网关、DNS、防火墙
- 不使用 Docker `network_mode: host`
- 不使用 `privileged: true`
- 不挂载宿主机 `/`、`/etc`、`/var/run/docker.sock`
- Samba 默认不启用；启用前必须重新审查

## 预检

部署前运行：

```bash
bash scripts/preflight/check-network-safety.sh
docker compose config
```

预检脚本只做只读检查，不会修改 LAN 配置。

## Phase 3 门禁

自动网络启动入口集成必须先完成 `BOOT_ENTRY_INTEGRATION.md` 中的
本地只读设备能力确认。

已通过管理员只读截图确认设备为 `TL-ER6120T`，硬件版本为
`TL-ER6120T 1.0`，当前固件为 `1.2.2 Build 240829 Rel.84642n`。
管理员当前未找到 DHCP Option `66/67` 或等价 boot option 配置入口，
因此默认不依赖主路由 DHCP Option 路线。

在完成新的研究、安全审查和项目决策前，不得进入 TFTP/ProxyDHCP
实施设计或实现。后续只允许受控 ProxyDHCP 可行性评估，且不得启用
DHCP、ProxyDHCP、TFTP 或 UDP `67/68/69/4011` 服务。

Web UI 的“本地事实门禁”面板只展示以下只读信息：

- 已确认事实。
- 仍缺事实。
- 解除门禁前置条件。
- 禁止推断。

该面板不包含配置提交按钮、路由器操作步骤、服务启用入口或生产 LAN
测试授权。它的目的只是防止后续误把设备型号、硬件版本或固件版本当成
DHCP Option `66/67`、next-server、Vendor Class 或 Client Architecture
可用证明。

Web UI 的“网络安全”页也会通过 `/api/network-safety.phase3_gate`
同步展示同一门禁状态：

- `status=router_option_path_not_recommended_but_blocked`。
- `allowed_next_step=controlled_proxydhcp_feasibility_evaluation_only`。
- `implementation_allowed=false`。
- `service_enablement_allowed=false`。
- `production_lan_testing_allowed=false`。

该展示只用于提醒当前禁止范围，不代表 Phase 3.3 运行时已解锁。

Phase 3.3 相关文档只作为门禁和审查材料：

- `BOOT_ENTRY_LOCAL_VERIFICATION.md`：本地设备能力确认记录。
- `PROXYDHCP_FEASIBILITY.md`：受控 ProxyDHCP 可行性评估。
- `PROXYDHCP_PACKET_REVIEW.md`：未来经审批隔离验证的报文字段判读标准。
- `TFTP_LOADER_SCOPE.md`：未来 TFTP loader 文件范围。
- `PHASE3_ROLLBACK_CHECKLIST.md`：Phase 3 回滚证据清单。
- `PHASE3_REVIEW_TEMPLATES.md`：网络安全与安全审计模板。
