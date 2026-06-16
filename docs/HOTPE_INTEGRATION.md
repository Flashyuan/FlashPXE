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
