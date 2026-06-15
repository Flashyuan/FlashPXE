# HotPE 集成指南

SynaBoot Phase 2 推荐通过 HotPE 安装 Windows 镜像。

## 文件放置

请将 HotPE 组件放入：

```text
data/images/pe/hotpe/
├── wimboot
├── bootmgr
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
- `BCD`
- `boot.sdi`
- `boot.wim`

当前已支持常见 UDF 布局：`bootmgr`、`Boot/bcd`、`Boot/boot.sdi`、
`HotPE/Boot.wim`。

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

## Windows 镜像访问

Windows ISO 建议放入：

```text
data/images/windows/win11/Windows11_24H2.iso
```

进入 HotPE 后访问：

```text
http://192.168.1.168:18080/images/windows/
```

## Samba 说明

Samba 默认未启用，默认也不会开放 `445/139/137/138`。

如后续需要 Samba，共享必须只读、只指向 `data/images`，并先通过
`network_safety_agent` 审查与 preflight 检查。
