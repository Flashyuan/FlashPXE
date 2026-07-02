# iPXE Loader 来源与导入说明

更新时间：2026-06-13

## 当前结论

SynaBoot 不在仓库中保存真实 iPXE loader 二进制，也不在运行时自动下载、
生成或执行 loader。

管理员如需推进 UEFI PXE IPv4 隔离验证，应先从可信来源取得 loader，再通过
本地导入脚本写入 `data/boot/loaders` 并记录 provenance。

## 官方来源

可复核的官方来源包括：

- iPXE 下载页：`https://ipxe.org/download`
- iPXE 文件索引：`https://boot.ipxe.org/`
- iPXE build targets：`https://ipxe.org/appnote/buildtargets`
- iPXE UEFI Secure Boot：`https://ipxe.org/secboot`
- iPXE GitHub releases：`https://github.com/ipxe/ipxe/releases/latest`

当前常见 x86_64 UEFI loader 路径：

```text
https://boot.ipxe.org/x86_64-efi/ipxe.efi
https://boot.ipxe.org/x86_64-efi/snponly.efi
https://github.com/ipxe/ipxe/releases/latest/download/ipxeboot.tar.gz
```

说明：

- `ipxe.efi` 使用 iPXE native drivers，适合不一定从固件 PXE 栈 chainload 的场景。
- `snponly.efi` 类似 BIOS 下的 `undionly.kpxe`，使用 EFI SNP/NII，通常适合
  从 UEFI PXE 固件 chainload。
- Secure Boot 场景应优先查阅 iPXE Secure Boot 文档和官方 signed release。
  普通未签名 EFI loader 在 Secure Boot 开启时可能被固件拒绝。

## 本地导入

导入单个本地文件：

```bash
python3 scripts/boot-assets/import-loader.py <本地源文件> snponly.efi \
  --source-label official-ipxe-local-file \
  --source-url https://boot.ipxe.org/x86_64-efi/snponly.efi
```

从本地 iPXE 归档导入：

```bash
python3 scripts/boot-assets/import-ipxe-archive.py <本地 ipxeboot.tar.gz> snponly.efi \
  --source-version <release-or-commit>
```

脚本行为：

- 只读取本地文件或本地归档。
- 只允许固定白名单文件名。
- 不联网、不下载、不执行 loader。
- 不启用 DHCP、ProxyDHCP、TFTP。
- 不开放 UDP `67`、`69`、`4011`。
- 不修改 TP-Link、OpenWrt、网关、DNS、路由、防火墙或 VLAN。
- 使用 `O_EXCL` 禁止覆盖已有 loader 和 metadata。
- 写入 `data/boot/loader-metadata/<filename>.json` 作为 provenance。

## Phase 3 边界

导入 loader 只代表 first-stage 文件准备完成，不代表生产 LAN PXE 已可用。

## 本机导入记录

2026-06-13 已在本机从官方 iPXE GitHub release 归档导入：

```text
source_url:
  https://github.com/ipxe/ipxe/releases/latest/download/ipxeboot.tar.gz

archive_sha256:
  01a526d4cc791fc30362259c609d6c506cc64a7bdff51b9a5eb788354e17eee1

snponly.efi_sha256:
  b1e67c3e4a1e8708ddfd0079ad4505e3a02245acb55ee9a95437ab3c507be82a

ipxe.efi_sha256:
  6558e37887516b246d6a97122e8d18bedfe4197b7ba7f67bf1bf102a16678d33
```

这些文件位于 ignored runtime 路径下，不进入 Git：

```text
data/builds/loader-downloads/ipxeboot.tar.gz
data/boot/loaders/snponly.efi
data/boot/loaders/ipxe.efi
data/boot/loader-metadata/snponly.efi.json
data/boot/loader-metadata/ipxe.efi.json
```

后续进入真实 UEFI PXE IPv4 前仍需：

- `research_agent` 补齐 TL-ER6120T DHCP/PXE 能力证据。
- `network_safety_agent` 审查 DHCP boot options、ProxyDHCP、TFTP 和端口风险。
- `security_audit_agent` 审查 loader、路径、服务、Docker 和脚本边界。
- `project_decision_agent` 授权从只读准备进入隔离实验。
- 在隔离网络完成抓包和回滚验证。

生产 LAN 中仍必须保持：

- TP-Link `192.168.1.1` 是唯一普通 DHCP lease server。
- OpenWrt `192.168.1.4` 是默认网关。
- SynaBoot 不分配普通 DHCP 租约。
- 未获授权前不启用 ProxyDHCP、TFTP 或 UDP `67/69/4011`。
