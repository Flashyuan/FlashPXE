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

在确认 TL-ER6120T/TL-ER6120 的型号、硬件版本、固件版本、Option
`66/67`、`next-server`、Vendor Class 和 Client Architecture 能力前，
不得进入 TFTP/ProxyDHCP 设计或实现。
