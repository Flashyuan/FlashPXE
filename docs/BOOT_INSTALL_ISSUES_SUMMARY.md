# FlashPXE 启动安装问题复盘

更新时间：2026-06-17

本文记录实验环境中 Windows 安装、HotPE 启动、Ubuntu Desktop 安装的主要问题、根因和最终处理方式。后续部署到真实环境前，必须按本文的检查项复核，避免重复踩坑。

## 实验结论

- Windows 安装入口应通过 `wimboot + Windows boot.wim` 启动，不直接让 iPXE 引导完整 Windows ISO。
- HotPE 启动入口应通过 `wimboot + bootmgfw.efi + BCD + boot.sdi + boot.wim` 启动，SMB 只用于进入 PE 后访问 Windows 镜像和模块目录。
- Ubuntu Desktop 不能使用 SMB/CIFS 作为 casper livefs 来源；最终可行路径是 `kernel/initrd via HTTP + casper livefs via NFS`。
- Ubuntu Desktop 的 HTTP ISO RAM fallback 只适合作为临时诊断路径，低内存客户端会失败，不应作为正式菜单入口。
- 实验环境的 NFS 应使用独立实验 IP，避免和 HTTP/SMB 服务复用同一地址导致 RPC、端口和客户端语义混乱。

## Windows 安装问题总结

### 问题表现

- 直接从 iPXE 菜单加载 Windows ISO 或错误的 BCD/boot 文件时，无法稳定进入安装器。
- Windows 安装器进入后仍需要访问安装镜像、驱动或模块目录。

### 根因

- iPXE 不适合直接把完整 Windows 安装 ISO 当成可启动内核链路处理。
- Windows 安装阶段需要 WinPE/HotPE 环境中的 Windows 工具链继续处理 `install.wim`、驱动和模块。
- SMB 在这里是安装介质访问通道，不是预启动 livefs 根文件系统。

### 最终方案

- 菜单中的 Windows 入口使用：

```text
wimboot
BCD
boot.sdi
boot.wim
```

- SMB 保留给 Windows/HotPE 使用：

```text
\\<SERVER_IP>\synaboot-images
\\<SERVER_IP>\hotpe-mods
\\<SERVER_IP>\win11
```

### 部署注意事项

- SMB 容器不能因为 Ubuntu 调试而停掉。
- Windows/HotPE SMB 配置和 Ubuntu NFS 配置必须分离管理。
- Windows 入口不应依赖 Ubuntu NFS 服务。

## HotPE 启动问题总结

### 问题表现

- HotPE 早期存在不同 BCD/bootmgfw 组合的诊断入口。
- 实验完成后菜单中过多 Diagnostics 入口影响实际使用。

### 根因

- HotPE 对 `bootmgfw.efi`、BCD、`boot.sdi`、`boot.wim` 的组合较敏感，需要实验诊断。
- 一旦确认稳定链路，诊断入口应从正式菜单移除。

### 最终方案

- 正式 FlashPXE 菜单只保留一个 HotPE 入口：

```text
HotPE V2.8
```

- 入口内部仍使用已经验证的 `wimboot` 链路：

```text
wimboot pause
bootmgfw.efi
BCD
boot.sdi
boot.wim
```

### 部署注意事项

- Diagnostics 可以留在文档或调试脚本中，不应出现在正式菜单。
- HotPE 启动成功后，Windows 镜像和模块继续通过 SMB 访问。

## Ubuntu Desktop 安装问题总结

### 问题一：HTTP ISO 下载到内存导致空间不足

表现：

```text
wget: short write: No space left on device
Unable to find a live file system on the network
```

根因：

- `url=http://...desktop.iso` 会让 casper 尝试下载完整 ISO 到客户端内存/临时空间。
- Ubuntu Desktop ISO 体积较大，普通测试 VM 或低内存客户端容易失败。

处理：

- HTTP ISO 仅作为诊断 fallback。
- 正式菜单移除 HTTP RAM fallback。

### 问题二：SMB/CIFS 不适合 Ubuntu Desktop casper livefs

表现：

```text
Trying mount.cifs ...
nfsmount: need a server
Unable to find a live file system on the network
```

根因：

- Ubuntu Desktop initramfs 的 casper 网络启动路径原生支持 NFS 和 URL ISO，不适合作为 CIFS livefs 根来源。
- SMB 匿名只读虽然可用于文件共享，但不能替代 casper 的 livefs 介质挂载语义。

处理：

- 清除 Ubuntu 安装中的 SMB/CIFS 方案。
- SMB 仅保留给 Windows/HotPE。

### 问题三：NFS 端口映射/桥接容器导致连接拒绝

表现：

```text
NFS over TCP not available
connect: Connection refused
```

根因：

- NFSv3 依赖 portmapper/mountd/nfs 多 RPC 服务。
- Docker bridge 端口映射容易让 initramfs 客户端看到不完整或不一致的 RPC 服务。

处理：

- 使用 macvlan 给 NFS 容器独立实验地址：

```text
10.101.8.136
```

- 不使用 host network。
- 不向宿主机发布 `111/2049/20048`。

### 问题四：Ganesha 容器缺少文件句柄能力

表现：

```text
mount: Operation not permitted
```

根因：

- `nfs-ganesha` 的 VFS FSAL 需要通过文件句柄读取只读导出内容。
- Docker 默认 seccomp 会阻断 `open_by_handle_at` 等路径。

处理：

```yaml
cap_add:
  - DAC_READ_SEARCH

security_opt:
  - no-new-privileges:true
  - seccomp=unconfined
```

安全边界：

- 仍不使用 `privileged: true`。
- 仍不使用 `network_mode: host`。
- 仍无 NFS 端口映射到宿主机。

### 问题五：casper UUID 元数据缺失

表现：

```text
nfsmount ... done
Unable to find a live file system on the network
```

根因：

- Ubuntu Desktop initrd 内置 `/conf/uuid.conf`。
- casper 挂载 NFS 后会检查：

```text
/cdrom/casper/*.squashfs
/cdrom/.disk/casper-uuid*
```

- 仅提取 `casper/vmlinuz`、`casper/initrd`、`casper/*.squashfs` 不够。
- 缺少 `.disk/casper-uuid-generic` 时，即使 NFS 已挂载成功，也会被 casper 判定为不是匹配的 live filesystem。

处理：

- Ubuntu NFS 导出目录必须包含：

```text
.disk/casper-uuid-generic
.disk/info
casper/vmlinuz
casper/initrd
casper/*.squashfs
```

- 文件权限必须至少为匿名只读可读：

```text
.disk/                 0755
.disk/casper-uuid-*    0644
.disk/info             0644
casper/*.squashfs      0644
```

## 当前正式 FlashPXE 菜单策略

正式实验菜单只保留四个镜像入口：

```text
Windows 11 24H2 Pro Chinese x64
HotPE V2.8
Ubuntu 22.04.3 desktop amd64
Ubuntu 24.04 desktop amd64
```

不显示：

- HTTP RAM fallback
- Diagnostics
- Windows explicit bootmgfw diagnostic
- HotPE native BCD diagnostic
- HotPE raw BCD diagnostic

## 真实环境部署前检查清单

### 网络安全

- 主 DHCP 仍由现网路由器提供。
- 默认网关不变。
- 不启用 SynaBoot DHCP 地址分配。
- ProxyDHCP/TFTP/HTTP Boot 自动集成必须单独审批。
- NFS 服务必须确认不暴露到生产接口。

检查命令：

```bash
ss -lntu | rg ':(111|2049|20048|445)\b'
docker exec synaboot-nfs-lab showmount -e <NFS_IP>
docker exec synaboot-nfs-lab rpcinfo -t <NFS_IP> nfs 3
```

### Windows/HotPE

- SMB 容器必须保持运行。
- SMB share 至少包含 Windows/HotPE 所需目录。
- HotPE 启动链路使用已验证的 `wimboot` 参数。

### Ubuntu Desktop

- Ubuntu 不走 SMB/CIFS。
- Ubuntu 不使用 HTTP ISO RAM fallback 作为正式入口。
- NFS 使用独立地址。
- NFS 导出目录包含 `.disk/casper-uuid-generic` 和 `.disk/info`。
- 匿名只读用户可读取 `.disk` 和 `casper` 下的必要文件。

### 菜单发布

- 修改菜单模板后必须重新生成：

```bash
bash scripts/lab/render-proxynet-lab-assets.sh
SERVER_IP=<SERVER_IP> SYNABOOT_ADMIN_TOKEN=<TOKEN> bash scripts/generate-ipxe-menu.sh
```

- 通过 HTTP 验证客户端实际拿到的菜单：

```bash
curl -fsS http://<SERVER_IP>:18080/boot/menu-lab.ipxe
curl -fsS http://<SERVER_IP>:18080/boot/menu.ipxe
```

## 最终原则

- Windows/HotPE：HTTP 引导 PE，SMB 提供安装介质和模块。
- Ubuntu Desktop：HTTP 提供 kernel/initrd，NFS 提供 casper livefs。
- SMB 和 NFS 的职责不要混用。
- 诊断入口不要进入正式菜单。
- HTTP RAM fallback 只用于临时排错，不作为真实部署方案。
