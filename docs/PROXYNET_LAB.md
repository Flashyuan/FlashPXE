# Phase 3.3-B ProxyNet 隔离实验

更新时间：2026-06-15

本文只适用于 PVE 隔离网段 `10.101.8.0/24`。

当前实验边界：

- SynaBoot lab 网卡：`ens19`
- SynaBoot lab IP：`10.101.8.135`
- 生产 LAN 网卡：`ens18`
- 生产 LAN IP：`192.168.1.168`
- 默认路由仍在生产 LAN：`192.168.1.4`

强制规则：

- 只能绑定 `ens19` / `10.101.8.135`。
- 禁止绑定 `0.0.0.0`、`::`、`ens18` 或 `192.168.1.168`。
- 不得分配 IP。
- 不得提供 gateway/router。
- 不得提供 DNS。
- 不得提供 lease time。
- 只响应 `PXEClient` / `HTTPClient`。
- PXE 路径只给 UEFI x64 客户端下发 `snponly.efi`。
- Legacy BIOS / SeaBIOS 客户端不下发 EFI loader。
- 只返回 `bootfile` / `next-server` / HTTP boot URL。
- TFTP 只暴露 `snponly.efi` 和 `ipxe.efi` 的运行态副本。
- 必须一键关闭。

非 root 准备命令：

```bash
bash scripts/lab/render-proxynet-lab-assets.sh
```

该命令只生成运行态文件，不启动任何 UDP 服务：

- `data/boot/menu-lab.ipxe`
- `data/boot/lab-chain.ipxe`
- `data/builds/proxynet-lab/dnsmasq-proxynet-lab.conf`
- `/tmp/synaboot-proxynet-lab/tftp/snponly.efi`
- `/tmp/synaboot-proxynet-lab/tftp/ipxe.efi`

TFTP 运行态文件放在 `/tmp/synaboot-proxynet-lab/tftp`，避免 `dnsmasq`
降权后无法穿透管理员 home 目录读取 loader。

`menu-lab.ipxe` 使用 FlashPXE 文本菜单模板，风格接近专业 netboot ISO
列表：黑底、青色分割线、顶部品牌区、镜像大小列、工具区。该模板只用于
隔离实验菜单，不改变生产菜单或网络服务边界。

启动实验需要 root 权限。执行前必须由管理员确认：

```bash
sudo SYNABOOT_PROXYNET_LAB_CONFIRM=I_UNDERSTAND_PROXYNET_LAB_ONLY_10.101.8.135_ens19 \
  SYNABOOT_LAB_IFACE=ens19 SYNABOOT_LAB_IP=10.101.8.135 \
  bash scripts/lab/start-proxynet-lab.sh
```

停止实验：

```bash
sudo bash scripts/lab/stop-proxynet-lab.sh
```

启动前后必须检查：

```bash
ss -lntu | grep -E ':(67|69|4011)\b' || true
curl -fsS http://10.101.8.135:18080/boot/menu-lab.ipxe
curl -fsSI http://10.101.8.135:18080/boot/loaders/ipxe.efi
curl -fsSI http://10.101.8.135:18080/boot/loaders/snponly.efi
```

如果 UEFI HTTP Boot 或 PXE Boot 只进入 iPXE shell，而没有自动进入菜单，
说明当前官方 loader 未内嵌 lab chain 脚本。此时应优先使用二阶段 DHCP
返回 `http://10.101.8.135:18080/boot/menu-lab.ipxe`，或在后续阶段构建
内嵌 `lab-chain.ipxe` 的实验 loader。

如果 PVE 控制台显示 `SeaBIOS`，说明测试 VM 不是 UEFI 启动。此时不能使用
`snponly.efi`，需要把 VM 的 BIOS 改为 `OVMF (UEFI)` 并添加 EFI Disk，
或者另行导入并启用 Legacy BIOS 专用的 `undionly.kpxe`。
