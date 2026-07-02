# HotPE 集成指南

SynaBoot Phase 2 推荐通过 HotPE 安装 Windows 镜像。

## 文件放置

请将 HotPE 组件放入：

```text
data/images/pe/hotpe/
├── wimboot
├── bootmgr
├── bootx64.efi
├── BCD
├── boot.sdi
└── boot.wim
```

文件齐全并扫描后，`boot_readiness=ready` 且 `menu_enabled=true` 的 HotPE 条目会进入 `menu.ipxe`。

## 从 ISO 准备启动组件

管理员已将 HotPE ISO 放入 `data/images/pe/hotpe/` 后，可以运行：

```bash
bash scripts/image-factory/prepare-hotpe-boot-artifacts.sh
```

脚本只从 HotPE ISO 的固定候选路径提取：

- `bootmgr`
- `bootx64.efi`
- `BCD`
- `boot.sdi`
- `boot.wim`

当前已支持常见 UDF 布局：`bootmgr`、`EFI/Microsoft/Boot/bootmgfw.efi`、
`EFI/Boot/bootx64.efi`、`Boot/bcd`、`Boot/boot.sdi`、`HotPE/Boot.wim`。
提取出的 UEFI boot manager 会统一以 `bootx64.efi` 暴露给 wimboot。

脚本不会覆盖已有目标文件，不会安装依赖，不会挂载 ISO，也不会执行分区、
格式化或网络配置。

`wimboot` 通常不在 HotPE ISO 内。若缺失，脚本会提示管理员从已审查的
iPXE/wimboot 发布包或本地可信构建产物导入，并在非公开
`data/metadata/wimboot-provenance/` 下记录来源、版本和 sha256。

导入本地已审核 `wimboot`：

```bash
python3 scripts/boot-assets/import-wimboot.py /path/to/wimboot \
  --reviewed-by local-admin \
  --source-label official-ipxe-wimboot \
  --source-version v2.9.0
```

如果 ISO 只暴露 `readme.txt` 或使用隐藏启动镜像布局，脚本会 fail-fast。
此时需要先人工确认 ISO 内部布局，不能按二进制偏移猜测提取文件。

`/images/` 是公开 HTTP 仓库，不应放置 provenance 或包含本机路径的审计文件。
Nginx 会拒绝访问 `*.provenance.json` 作为兜底保护。

## HotPE 外置工具模块

HotPE 的大量桌面工具不一定在 `boot.wim` 内。常见布局会把 WinNTSetup、
DiskGenius、Dism++、WIT 等工具放在 ISO 根目录的 `HotProgMods/*.HPM`
和 `HotPE/Data/` 中。

通过 wimboot 网络启动时，SynaBoot 默认只加载 `boot.wim`。这能进入 HotPE
桌面，但不会自动挂载原始 ISO，也不会自动加载外置 HPM 模块。因此客户端
桌面可能只显示少量核心工具。

管理员可以只读提取 HotPE 外置运行时模块：

```bash
python3 scripts/image-factory/extract-hotpe-runtime-assets.py
```

默认输出：

```text
data/images/pe/hotpe/runtime/
├── HotPE/
│   └── Data/
└── HotProgMods/
    ├── WinNTSetup_*.HPM
    ├── DiskGenius_*.HPM
    └── ...
```

该脚本不挂载 ISO、不执行 ISO 内文件，只允许提取 `HotProgMods/`、
`HotPE/Data/` 和 HotPE 运行时配置文件。

在 HotPE 内通过 SMB 映射镜像仓库后，可进入：

```text
Z:\pe\hotpe\runtime\HotProgMods
```

然后使用 HotPE 桌面的“模块管理”导入所需 `.HPM`。如果 HotPE 支持直接
双击 HPM，也可直接打开对应模块；是否自动生成桌面图标取决于 HotPE 自身
的模块管理器行为。

## Windows 镜像访问

Windows ISO 建议放入：

```text
data/images/windows/win11/Windows11_24H2.iso
```

进入 HotPE 后访问：

```text
http://192.168.1.168:18080/images/windows/
```

实验 SMB 共享启用后，可在 HotPE 中映射：

```cmd
net use Z: \\10.101.8.135\synaboot-images /user:synaboot synaboot-lab
```

Windows 11 24H2 ISO 当前路径示例：

```text
Z:\windows\win11\Win11_24H2_Pro_Chinese_Simplified_x64.iso
```

## Samba 说明

Samba 默认未启用，默认也不会开放 `445/139/137/138`。

如后续需要 Samba，共享必须只读、只指向 `data/images`，并先通过
`network_safety_agent` 审查与 preflight 检查。

## HotPE 自动挂载与模块自动加载

目标是在 HotPE 启动完成后自动挂载 SynaBoot 的 SMB 共享，并尽量自动加载
HotPE 外置功能模块。该能力只面向 Windows/HotPE 辅助安装，不改变 Ubuntu
Desktop 的启动方式。

边界：

- 不停掉现有 SMB 容器或共享。
- 不把 SMB 用作 Ubuntu casper livefs；Ubuntu 继续使用 NFS livefs。
- 不把第三方软件安装包放入 SMB 作为软件市场缓存。
- 不在 iPXE 阶段尝试挂载 SMB；自动挂载必须发生在 HotPE 内部。
- 不把 SMB 密码写入 Git、公开 HTTP 目录或可下载的 provenance 文件。

推荐共享：

```text
\\<SERVER_IP>\synaboot-images
\\<SERVER_IP>\hotpe-mods
\\<SERVER_IP>\win11
```

推荐盘符：

```text
Z:  SynaBoot 镜像仓库
M:  HotPE 外置功能模块
W:  Windows 安装镜像目录
```

第一阶段可提供 HotPE 内部启动脚本模板：

```cmd
net use Z: \\<SERVER_IP>\synaboot-images /user:synaboot <只读密码>
net use M: \\<SERVER_IP>\hotpe-mods /user:synaboot <只读密码>
net use W: \\<SERVER_IP>\win11 /user:synaboot <只读密码>
```

脚本可以通过 HotPE 支持的启动机制调用，例如 `PECMD`、`HotPE.INI`、
桌面启动项或 `startnet.cmd`。具体入口需要先确认当前 HotPE V2.8 的
启动配置结构。

### 实验实现状态

当前已提供可重复生成的实验资产：

```bash
SYNABOOT_HOTPE_SMB_HOST=10.101.8.135 \
SYNABOOT_HOTPE_SMB_USER=synaboot \
SYNABOOT_HOTPE_SMB_PASSWORD="<只读 SMB 密码>" \
python3 scripts/image-factory/render-hotpe-automount-assets.py
```

生成结果：

- 含密运行态脚本：
  `data/secrets/hotpe/automount/mount-synaboot-shares.cmd`
  `data/secrets/hotpe/automount/load-hotpe-modules.cmd`
- 公开无密文标记：
  `data/images/pe/hotpe/runtime/AutoMount/manifest.json`
  `data/images/pe/hotpe/runtime/AutoMount/README.txt`

含密脚本目录必须保持 `0700`，脚本文件必须保持 `0600`，并且必须被
`.gitignore` 覆盖。公开目录只允许存放无密文 manifest 和说明文件。

实验脚本当前会映射：

```text
Z:  \\<SMB_HOST>\synaboot-images
M:  \\<SMB_HOST>\hotpe-mods
W:  \\<SMB_HOST>\win11
```

其中 `M:` 会指向 HotPE 外置模块共享。脚本会对白名单 `.HPM` 执行
`start "" "M:\xxx.HPM"`，然后打开 `M:\` 作为人工兜底入口。

验证命令：

```bash
bash scripts/preflight/check-hotpe-automount-safety.sh
```

该预检会确认：

- 未设置 `SYNABOOT_HOTPE_SMB_PASSWORD` 时生成器 fail-closed。
- 公开 AutoMount 目录不包含 SMB 密码。
- `boot.wim` hash 在生成前后不变。
- 主 `docker-compose.yml` 不新增 SMB 服务。
- 实验 SMB Compose 仍只读挂载 `data/images`。
- HotPE AutoMount 生成器和产物不包含 Ubuntu casper/NFS/livefs 语义。

模块自动加载分两级：

- Level 1：自动挂载 `M:` 并创建模块目录入口，管理员或用户手动从 HotPE
  模块管理器导入 `.HPM`。
- Level 2：如果 HotPE 模块管理器或 `PECMD` 支持命令行导入，则在挂载后
  自动导入 `M:\*.HPM` 或指定白名单模块。

SMB 可以使用主机 `SERVER_IP`，不强制独立 IP。独立 IP 只适合实验隔离。
生产环境复用 `SERVER_IP` 前，必须确认 `445/tcp` 未被占用，并通过网络安全
预检和 `network_safety_agent` 审查。
