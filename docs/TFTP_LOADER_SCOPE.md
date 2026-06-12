# Phase 3.3 TFTP Loader 文件范围

更新时间：2026-06-12

## 状态与范围

```text
phase：3.3
scope_status：documentation_only
runtime_status：BLOCKED
implementation_allowed：false
tftp_service_enablement_allowed：false
udp_69_allowed：false
```

本文只定义未来如进入隔离验证时，TFTP 可服务的 boot loader 文件范围。

本文不是 TFTP 实施方案，不包含安装、配置、启动、端口开放、Compose
修改、生产 LAN 测试或下载 loader 的步骤。

## 硬性禁止事项

- 不实现 TFTP。
- 不启用 TFTP。
- 不开放 UDP `69`。
- 不启用 ProxyDHCP 或 DHCP。
- 不修改 `docker-compose.yml`。
- 不使用 Docker `network_mode: host`。
- 不使用 Docker `privileged: true`。
- 不下载、生成、替换、删除或执行 boot loader。
- 不通过 TFTP 服务 ISO、WIM、ESD、IMG、VHD、VHDX、QCOW2 或镜像目录。
- 不通过 TFTP 服务 `menu.ipxe` 或动态脚本。
- 不允许 symlink 或父目录 symlink 参与 TFTP 范围。

## 固定根目录

未来候选 TFTP root 只能是：

```text
./data/boot/loaders
```

该路径必须继续和 `/api/boot-assets` 的只读扫描模型一致。

## TFTP 候选文件白名单

以下文件名来自当前 `LOADER_CATALOG`，且具备 `future-tftp` transport 标记。

```text
ipxe.efi
snponly.efi
undionly.kpxe
```

白名单含义：

- `ipxe.efi`：UEFI HTTP Boot / UEFI PXE chainload 候选。
- `snponly.efi`：UEFI PXE chainload 候选，使用固件 SNP driver。
- `undionly.kpxe`：Legacy BIOS PXE chainload 候选。

## 明确排除项

以下内容不得进入未来 TFTP scope：

- `ipxe.iso`。它在当前 catalog 中属于 removable-media，不属于 TFTP 候选。
- `menu.ipxe`。iPXE 菜单继续通过 HTTP 提供。
- `data/images/**` 下的任何镜像。
- `data/boot/loaders/` 之外的任何路径。
- 目录列表、通配符路径、相对上级路径或隐藏文件。
- symlink 文件。
- 父目录包含 symlink 的文件。
- 未记录来源、hash、大小和 mtime 的 loader。
- Secure Boot 风险未标注的 UEFI loader。

## Loader 证据要求

未来进入隔离验证前，每个候选 loader 必须至少具备：

- 固定白名单文件名。
- catalog id。
- 位于 `./data/boot/loaders`。
- relative path 不包含目录跳转。
- 是 regular file。
- 文件和父目录均不是 symlink。
- SHA256。
- size bytes。
- mtime。
- 来源说明。
- source commit、版本或可复核引用。
- 适用架构。
- Secure Boot 风险说明。
- review status。
- reviewed by / reviewed at。
- `tftp_allowed=true`。
- `symlink_allowed=false`。

当前这些字段由 `/api/boot-assets` 只读模型提供。

## 路径与扩展名 Denylist

未来 TFTP scope 必须拒绝：

```text
../
/
\
*
?
~
.env
*.iso
*.img
*.wim
*.esd
*.vhd
*.vhdx
*.sh
*.py
*.ps1
*.exe
*.msi
*.dll
*.conf
*.cfg
*.yaml
*.yml
*.json
*.key
*.pem
*.crt
*.token
README*
```

该 denylist 不是可执行配置，只是未来安全审查时的判读标准。

## TFTP 判读要求

未来如果进入隔离验证，TFTP 请求只能满足以下语义：

- 请求文件名精确匹配白名单。
- 请求来源是已经隔离的测试 PXE/UEFI client。
- 响应内容只包含已审查 loader。
- 成功后由 iPXE 继续通过 HTTP 访问
  `http://<SERVER_IP>:18080/boot/menu.ipxe`。

出现以下任一情况必须 `BLOCKED`：

- 请求非白名单文件。
- 请求 `menu.ipxe`、ISO、WIM、ESD、IMG 或镜像目录。
- 请求路径包含 `..`、绝对路径、隐藏文件或通配符。
- 请求文件是 symlink 或父目录 symlink 下的文件。
- 普通生产 LAN 客户端请求 TFTP。
- 需要开放生产 LAN UDP `69` 才能继续。
- 需要 Docker host network 或 privileged 才能继续。

## 与 HTTP 白名单的关系

当前 Nginx `/boot/` HTTP 静态服务只允许精确访问：

```text
/boot/menu.ipxe
/boot/loaders/ipxe.efi
/boot/loaders/snponly.efi
/boot/loaders/undionly.kpxe
/boot/loaders/ipxe.iso
```

未来 TFTP scope 比 HTTP scope 更窄：

- TFTP 不包含 `/boot/menu.ipxe`。
- TFTP 不包含 `ipxe.iso`。
- TFTP 不包含目录列表。
- TFTP 只面向隔离测试中的 first-stage PXE loader 下载。

## 当前结论

当前只完成 TFTP loader 文件范围定义。

Phase 3.3 仍为 `BLOCKED`。本文不批准启用 TFTP，不批准开放 UDP `69`，
不批准实现 ProxyDHCP/DHCP，也不批准修改 TP-Link、OpenWrt、Docker 网络
或生产 LAN 配置。
