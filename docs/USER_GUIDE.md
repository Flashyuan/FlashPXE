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

- ISO 是否已放入 `data/images/linux/...`。
- `casper/vmlinuz` 是否存在。
- `casper/initrd` 是否存在。
- Web UI 中 `boot_readiness` 是否为 `ready`。

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

菜单里没有我要的系统？

请联系管理员检查镜像是否已放入、扫描、启用菜单，并且 `boot_readiness=ready`。

Windows 镜像为什么不能直接启动？

Windows 网络安装更适合通过 HotPE 访问 ISO/WIM/ESD。请先启动 HotPE。

Linux 启动很慢？

安装器会通过 HTTP 拉取 ISO，速度取决于局域网、磁盘和镜像大小。

需要输入管理员 token 吗？

普通用户不需要。扫描镜像、生成菜单、创建任务等管理操作才需要管理员 token。
