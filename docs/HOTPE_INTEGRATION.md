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
