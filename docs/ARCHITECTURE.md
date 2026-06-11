# SynaBoot 架构说明

本文说明 SynaBoot Phase 2 的零侵入 HTTP/iPXE Boot 架构。

## 目标与非目标

目标：

- 提供 Web UI。
- 提供 HTTP 镜像仓库。
- 提供元数据驱动的 iPXE 菜单。
- 扫描 `data/images` 并维护 SHA256 与启动就绪状态。
- 提供安全的镜像工厂任务模板。

非目标：

- 不做 DHCP。
- 不做 ProxyDHCP。
- 不做 TFTP。
- 不修改路由器、交换机、AP、VLAN、DNS、路由、防火墙。
- 不自动格式化或分区客户机磁盘。

## 服务拓扑

```text
[Client iPXE/UEFI HTTP Boot]
          |
          | HTTP 18080/tcp
          v
[synaboot-nginx]
   |      |       |
   |      |       +--> /api/*  -> [synaboot-api:8000]
   |      +----------> /boot/  -> data/boot
   +-----------------> /images/ -> data/images

[synaboot-worker] -> POST /api/scan -> [synaboot-api]

[SQLite metadata] -> data/metadata/synaboot.sqlite3
```

网络边界：

- 只有 `synaboot-nginx` 发布 HTTP TCP 端口。
- API 只在 Docker bridge 内部暴露。
- Worker 不发布端口。
- Samba 默认不启用。

## 数据目录

```text
data/
├── images/      # 用户放置 ISO/WIM/ESD/kernel/initrd/HotPE 文件
├── boot/        # 生成的 menu.ipxe
├── metadata/    # SQLite 元数据
├── builds/      # Image Factory 任务输出
└── logs/        # 日志
```

## 零侵入启动链路

```text
[用户开机]
    |
    v
[iPXE USB/ISO/EFI 或手动 UEFI HTTP Boot]
    |
    | chain http://192.168.1.168:18080/boot/menu.ipxe
    v
[SynaBoot menu.ipxe]
    |
    +--> [HotPE] ----HTTP----> /images/pe/hotpe/*
    |
    +--> [Linux] ----HTTP----> /images/linux/<发行版>/casper/vmlinuz
    |                    |---> /images/linux/<发行版>/casper/initrd
    |                    '---> /images/linux/<发行版>/<installer>.iso
    |
    '--> [Windows via HotPE]
             |
             '--HTTP----> /images/windows/
```

这条链路只使用 HTTP。SynaBoot 不参与客户端获取 IP 的过程，不提供 DHCP、ProxyDHCP 或 TFTP。

## 镜像扫描流程

```text
[管理员放入文件到 data/images]
          |
          v
[POST /api/scan]
          |
          v
[扫描文件]
  ├── 跳过软链接、隐藏文件、临时文件
  ├── 计算 relative_path、size_bytes、mtime_ns
  ├── 复用或计算 SHA256
  ├── 判断 scan_status
  └── 判断 boot_readiness
          |
          v
[写入 SQLite]
          |
          v
[重新生成 data/boot/menu.ipxe]
```

关键状态：

- `scan_status=present`：文件存在。
- `scan_status=missing`：元数据存在但文件已不在。
- `boot_readiness=ready`：可进入菜单。
- `boot_readiness=incomplete`：缺少启动依赖。
- `boot_readiness=needs_hotpe`：需要 HotPE 辅助安装。
- `boot_readiness=unsupported`：可存储但不生成启动项。

## 菜单生成流程

```text
[SQLite images]
      |
      v
过滤：
scan_status=present
menu_enabled=true
boot_readiness=ready
      |
      v
分组：
PE / Recovery
Linux
Windows via HotPE
System
      |
      v
data/boot/menu.ipxe
```

Windows ISO/WIM/ESD 不生成通用直接启动项。若 HotPE 已就绪且存在 Windows 镜像，菜单只提供 Windows via HotPE 说明入口。

## Image Factory 状态

```text
draft -> pending -> running -> success
draft -> pending -> running -> failed
draft -> pending -> canceled
```

二期任务只生成安全模板和任务包：

- Ubuntu autoinstall 模板。
- Ubuntu xorriso ISO 任务说明。
- Windows ADK/DISM 外部构建包。

## Subagents 协作

```text
network_safety_agent
        |
        v
architecture_agent
        |
        v
storage_agent + boot_entry_agent + webui_agent + image_factory_agent
        |
        v
tutorial_docs_agent
        |
        v
security_audit_agent + network_safety_agent
        |
        v
git_audit_agent
```

冲突规则：

- `network_safety_agent` 和 `security_audit_agent` 优先级最高。
- 网络相关变更必须先审查。
- 任一安全 agent 输出 `BLOCKED` 时，相关开发停止。
