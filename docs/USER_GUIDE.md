# SynaBoot 用户实用教程

本文面向需要通过 SynaBoot 安装或维护系统的使用者。

你需要记住的地址：

```text
SynaBoot 菜单：http://192.168.1.168:18080/boot/menu.ipxe
镜像仓库：http://192.168.1.168:18080/images/
```

## 1. 启动前确认

请先向管理员确认：

- SynaBoot 服务已经启动。
- 你的电脑和 SynaBoot 服务器在同一局域网。
- 目标系统镜像已经放入平台并扫描完成。
- 菜单中已有可启动条目。

普通“网卡 PXE 启动”不一定会自动进入 SynaBoot。SynaBoot 不接管 DHCP，也不提供 TFTP。

当前 Phase 3 自动网络启动入口仍处于门禁状态。管理员已确认主路由为
TP-Link `TL-ER6120T`，但当前没有找到 DHCP Option `66/67` 或等价 boot
option 配置入口，因此默认不依赖主路由 DHCP Option 路线。普通用户不要
自行修改路由器、DHCP、ProxyDHCP、TFTP、网关、DNS 或防火墙设置。

Web UI 的“启动入口”页面只是只读状态页，用来显示当前门禁、文档和
禁止项。普通用户不能在这里启用 PXE、ProxyDHCP、TFTP 或 DHCP boot
option。

## 2. 进入 SynaBoot 菜单

方式 A：iPXE 启动介质

1. 插入管理员准备好的 iPXE USB/ISO/EFI 启动介质。
2. 开机按启动菜单键，常见是 `F12`、`F11`、`Esc`。
3. 选择 iPXE 启动项。
4. 如果进入 iPXE Shell，执行：

```ipxe
chain http://192.168.1.168:18080/boot/menu.ipxe
```

方式 B：手动 UEFI HTTP Boot

如果 BIOS 支持手动 HTTP Boot URL，输入：

```text
http://192.168.1.168:18080/boot/menu.ipxe
```

方式 C：管理员已准备好的外部 chain 入口

如果管理员明确告知某台测试机或隔离环境已经配置好外部启动入口，可以按
管理员给出的启动项进入。未收到管理员确认时，不要把普通 PXE 启动失败
当成故障。

只有管理员明确指定的设备、启动项或隔离环境可以使用外部 chain 入口；
不要把 BIOS 里的 `UEFI: PXE IPv4` 当成必然可用入口。

## 3. 选择系统

进入菜单后：

1. 使用方向键选择条目。
2. 按 Enter 确认。
3. 如果启动失败，菜单会回到 `boot_failed` 提示，再返回主菜单。

常见条目含义：

- `HotPE via wimboot`：进入 PE 环境，适合安装或维护 Windows。
- `Linux installer`：启动 Linux 安装器。
- `Windows installation via HotPE`：提示先进入 HotPE，再访问 Windows 镜像。
- `iPXE shell`：进入 iPXE 命令行。
- `Reboot`：重启。
- `Power off`：关机。

## 4. 安装 Linux

当菜单中出现 Linux installer：

1. 选择对应 Linux 条目。
2. SynaBoot 会通过 HTTP 加载 kernel、initrd 和 ISO。
3. 进入安装器后按正常流程安装。

如果没有看到 Linux 条目，请联系管理员检查：

- 镜像是否已上传并扫描完成。
- 菜单条目是否已启用。
- 镜像可启动状态是否为 `ready`。

## 5. 安装 Windows

Windows 推荐通过 HotPE 安装：

1. 在 SynaBoot 菜单中选择 HotPE。
2. 进入 PE 桌面后打开浏览器或工具。
3. 访问：

```text
http://192.168.1.168:18080/images/windows/
```

4. 找到 Windows ISO/WIM/ESD。
5. 按 PE 内工具或 Windows 安装程序完成安装。

说明：Windows ISO/WIM/ESD 不作为通用 iPXE 直接启动项，这是正常设计。

## 6. 常见问题

开机选 PXE 后没有进入 SynaBoot？

这是正常情况。SynaBoot 不接管 DHCP，也不启用 ProxyDHCP/TFTP。请使用 iPXE 启动介质或手动 UEFI HTTP Boot URL。

我能自己设置路由器或 DHCP 让 PXE 自动进入吗？

不能。当前 Phase 3.3 仍为 `BLOCKED`，主路由 DHCP Option `66/67` 路线
默认不依赖。任何 ProxyDHCP、TFTP、DHCP boot option 或路由器变更都必须
由管理员按项目审查流程处理。

Web UI 里看到 ProxyDHCP/TFTP/启动入口文档，是否代表我可以启用？

不能。这些内容当前只是 documentation-only 或 blocked 状态说明。任何启用
都必须由管理员走项目审查流程。

菜单里没有我要的系统？

请联系管理员检查镜像是否已放入、扫描、启用菜单，并且 `boot_readiness=ready`。

Windows 镜像为什么不能直接启动？

Windows 网络安装更适合通过 HotPE 访问 ISO/WIM/ESD。请先启动 HotPE。

Linux 启动很慢？

安装器会通过 HTTP 拉取 ISO，速度取决于局域网、磁盘和镜像大小。

需要输入管理员 token 吗？

普通用户不需要。扫描镜像、生成菜单、创建任务等管理操作才需要管理员 token。
