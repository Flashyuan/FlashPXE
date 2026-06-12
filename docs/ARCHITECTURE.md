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

## Phase 3 只读启动入口模型

Phase 3 的目标是后续支持 UEFI HTTP/PXE 启动入口，但当前只实现只读模型和门禁展示。

当前只读链路：

```text
[Web UI 启动入口页]
        |
        v
GET /api/boot-entry
        |
        +--> 模型阶段：phase=3.1
        +--> 展示阶段：display_phase=3.4
        +--> 展示状态：readonly_boot_entry_with_local_fact_gate
        +--> 启动入口状态：HTTP IPv4 / PXE IPv4 / HTTP IPv6 / PXE IPv6
        +--> 文档入口：BOOT_ENTRY_INTEGRATION.md
        +--> 本地确认模板：BOOT_ENTRY_LOCAL_VERIFICATION.md
        +--> ProxyDHCP 可行性评估：PROXYDHCP_FEASIBILITY.md
        +--> ProxyDHCP 报文判读：PROXYDHCP_PACKET_REVIEW.md
        +--> TFTP loader 范围：TFTP_LOADER_SCOPE.md
        +--> Phase 3 回滚清单：PHASE3_ROLLBACK_CHECKLIST.md
        +--> Phase 3 审查模板：PHASE3_REVIEW_TEMPLATES.md
        +--> Phase 3.3 gate：router_option_path_not_recommended_but_blocked
        |       |--> confirmed_evidence：已确认事实
        |       |--> missing_local_facts：仍缺事实
        |       |--> blocked_until：解除门禁前置条件
        |       '--> do_not_infer：禁止推断
        '--> Web UI 本地事实门禁面板

GET /api/boot-assets
        |
        +--> 固定白名单 loader 元数据
        +--> ipxe.efi / snponly.efi / undionly.kpxe / ipxe.iso
        +--> symlink 与父目录 symlink 均不标记为可用

GET /api/network-safety
        |
        +--> phase3_gate：同步展示 Phase 3.3 门禁
        +--> status=router_option_path_not_recommended_but_blocked
        +--> allowed_next_step=controlled_proxydhcp_feasibility_evaluation_only
        +--> implementation_allowed=false
        +--> service_enablement_allowed=false
        '--> production_lan_testing_allowed=false
```

`/api/boot-entry` 不写入配置，不启用服务，不修改网络设备。
其中 `phase=3.1` 表示后端只读模型阶段，`display_phase=3.4` 和
`display_status=readonly_boot_entry_with_local_fact_gate` 只表示 Web UI
当前展示层已经包含本地事实门禁，不代表 Phase 3.3 运行时已解锁。

`/api/network-safety` 的 `phase3_gate` 只把同一门禁状态同步到网络安全页。
它不提供写接口，不启用 DHCP、ProxyDHCP、TFTP，也不批准生产 LAN 测试。

`/api/boot-assets` 只扫描 `data/boot/loaders` 下固定白名单文件名，不下载、生成、上传、替换、删除或执行 boot loader。

Nginx `/boot/` 只允许精确访问：

```text
/boot/menu.ipxe
/boot/loaders/ipxe.efi
/boot/loaders/snponly.efi
/boot/loaders/undionly.kpxe
/boot/loaders/ipxe.iso
```

其它 `/boot/` 路径返回 404，并启用 `disable_symlinks on`。

管理员已通过只读截图确认 TL-ER6120T 设备身份、硬件版本和固件版本，
但当前未在管理界面中找到 DHCP Option `66/67` 或等价 boot option
配置入口。因此 Phase 3.3 默认不依赖主路由 DHCP Option 路线，
只允许继续受控 ProxyDHCP 可行性评估。
`phase3_3_gate` 将这些事实拆成已确认事实、仍缺事实、解除门禁前置
条件和禁止推断四类，只用于 Web UI 只读展示，防止后续把设备型号、
硬件版本或固件版本误当成 DHCP Option `66/67`、next-server、
Vendor Class 或 Client Architecture 可用证明。
评估记录见 `docs/PROXYDHCP_FEASIBILITY.md`，该文档只定义问题清单、
风险和门禁，不包含可执行服务配置。
未来隔离验证的报文字段判读标准见 `docs/PROXYDHCP_PACKET_REVIEW.md`，
该文档只定义允许/禁止字段和判读结论。
TFTP loader 文件范围见 `docs/TFTP_LOADER_SCOPE.md`，该文档只定义未来
隔离验证的固定 loader 白名单，不包含 TFTP 服务配置。
回滚判据见 `docs/PHASE3_ROLLBACK_CHECKLIST.md`，该文档只定义未来验证的
恢复证据和阻塞条件，不包含网络设备操作步骤。
审查模板见 `docs/PHASE3_REVIEW_TEMPLATES.md`，该文档只定义未来
network_safety_agent 与 security_audit_agent 的结论记录格式。

Phase 3.3 继续保持 `BLOCKED`。任何 TFTP/ProxyDHCP 设计、实验或实现前，
都必须重新通过 `research_agent`、`network_safety_agent`、
`security_audit_agent` 和 `project_decision_agent` 审查。

当前架构仍不提供 DHCP、ProxyDHCP、TFTP，也不开放 UDP `67/68/69/4011`。

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
