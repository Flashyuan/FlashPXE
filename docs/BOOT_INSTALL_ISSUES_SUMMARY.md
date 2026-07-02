# FlashPXE 启动安装问题复盘

更新时间：2026-06-18

本文记录实验环境中 Windows 安装、HotPE 启动、Ubuntu Desktop 安装的主要问题、根因和最终处理方式。后续部署到真实环境前，必须按本文的检查项复核，避免重复踩坑。

## 实验结论

- Windows 安装入口应通过 `wimboot + Windows boot.wim` 启动，不直接让 iPXE 引导完整 Windows ISO。
- HotPE 启动入口应通过 `wimboot + bootmgfw.efi + BCD + boot.sdi + boot.wim` 启动，SMB 只用于进入 PE 后访问 Windows 镜像和模块目录。
- Ubuntu Desktop 不能使用 SMB/CIFS 作为 casper livefs 来源；最终可行路径是 `kernel/initrd via HTTP + casper livefs via NFS`。
- Ubuntu Desktop 的 HTTP ISO RAM fallback 只适合作为临时诊断路径，低内存客户端会失败，不应作为正式菜单入口。
- 实验环境的 NFS 应使用独立实验 IP，避免和 HTTP/SMB 服务复用同一地址导致 RPC、端口和客户端语义混乱。

## Windows 安装问题总结

### 问题表现

- 直接从 iPXE 菜单加载 Windows ISO 或错误的 BCD/boot 文件时，无法稳定进入安装器。
- Windows 安装器进入后仍需要访问安装镜像、驱动或模块目录。

### 根因

- iPXE 不适合直接把完整 Windows 安装 ISO 当成可启动内核链路处理。
- Windows 安装阶段需要 WinPE/HotPE 环境中的 Windows 工具链继续处理 `install.wim`、驱动和模块。
- SMB 在这里是安装介质访问通道，不是预启动 livefs 根文件系统。

### 最终方案

- 菜单中的 Windows 入口使用：

```text
wimboot
BCD
boot.sdi
boot.wim
```

- SMB 保留给 Windows/HotPE 使用：

```text
\\<SERVER_IP>\synaboot-images
\\<SERVER_IP>\hotpe-mods
\\<SERVER_IP>\win11
```

### 部署注意事项

- SMB 容器不能因为 Ubuntu 调试而停掉。
- Windows/HotPE SMB 配置和 Ubuntu NFS 配置必须分离管理。
- Windows 入口不应依赖 Ubuntu NFS 服务。
- 后续可实现 HotPE 启动后自动挂载 SMB，但必须在 HotPE 内部脚本中执行，
  不能把 SMB 重新引入 Ubuntu Desktop livefs，也不能停掉现有 Windows/HotPE
  SMB 共享。

## HotPE 启动问题总结

### 问题表现

- HotPE 早期存在不同 BCD/bootmgfw 组合的诊断入口。
- 实验完成后菜单中过多 Diagnostics 入口影响实际使用。

### 根因

- HotPE 对 `bootmgfw.efi`、BCD、`boot.sdi`、`boot.wim` 的组合较敏感，需要实验诊断。
- 一旦确认稳定链路，诊断入口应从正式菜单移除。

### 最终方案

- 正式 FlashPXE 菜单只保留一个 HotPE 入口：

```text
HotPE V2.8
```

- 入口内部仍使用已经验证的 `wimboot` 链路：

```text
wimboot pause
bootmgfw.efi
BCD
boot.sdi
boot.wim
```

### 部署注意事项

- Diagnostics 可以留在文档或调试脚本中，不应出现在正式菜单。
- HotPE 启动成功后，Windows 镜像和模块继续通过 SMB 访问。
- HotPE 自动 SMB 挂载已提供实验生成器：
  `scripts/image-factory/render-hotpe-automount-assets.py`。生成器只把含密脚本写入
  `data/secrets/hotpe/automount/`，公开 HTTP 目录只保留无密文 manifest。
- 当前自动加载模块采用保守方式：挂载 `M:` 后对白名单 `HotProgMods/*.HPM`
  执行打开动作，并打开模块目录作为人工兜底。如果 HotPE V2.8 只支持 GUI
  导入模块，该方案仍能减少手工寻找共享目录的步骤。
- 该能力不得影响 Ubuntu Desktop。Ubuntu 继续使用
  `HTTP kernel/initrd + NFS casper livefs`，不得回退到 SMB/CIFS livefs。
- 验证命令：`bash scripts/preflight/check-hotpe-automount-safety.sh`。

## Ubuntu Desktop 安装问题总结

### 问题一：HTTP ISO 下载到内存导致空间不足

表现：

```text
wget: short write: No space left on device
Unable to find a live file system on the network
```

根因：

- `url=http://...desktop.iso` 会让 casper 尝试下载完整 ISO 到客户端内存/临时空间。
- Ubuntu Desktop ISO 体积较大，普通测试 VM 或低内存客户端容易失败。

处理：

- HTTP ISO 仅作为诊断 fallback。
- 正式菜单移除 HTTP RAM fallback。

### 问题二：SMB/CIFS 不适合 Ubuntu Desktop casper livefs

表现：

```text
Trying mount.cifs ...
nfsmount: need a server
Unable to find a live file system on the network
```

根因：

- Ubuntu Desktop initramfs 的 casper 网络启动路径原生支持 NFS 和 URL ISO，不适合作为 CIFS livefs 根来源。
- SMB 匿名只读虽然可用于文件共享，但不能替代 casper 的 livefs 介质挂载语义。

处理：

- 清除 Ubuntu 安装中的 SMB/CIFS 方案。
- SMB 仅保留给 Windows/HotPE。

### 问题三：NFS 端口映射/桥接容器导致连接拒绝

表现：

```text
NFS over TCP not available
connect: Connection refused
```

根因：

- NFSv3 依赖 portmapper/mountd/nfs 多 RPC 服务。
- Docker bridge 端口映射容易让 initramfs 客户端看到不完整或不一致的 RPC 服务。

处理：

- 使用 macvlan 给 NFS 容器独立实验地址：

```text
10.101.8.136
```

- 不使用 host network。
- 不向宿主机发布 `111/2049/20048`。

### 问题四：Ganesha 容器缺少文件句柄能力

表现：

```text
mount: Operation not permitted
```

根因：

- `nfs-ganesha` 的 VFS FSAL 需要通过文件句柄读取只读导出内容。
- Docker 默认 seccomp 会阻断 `open_by_handle_at` 等路径。

处理：

```yaml
cap_add:
  - DAC_READ_SEARCH

security_opt:
  - no-new-privileges:true
  - seccomp=unconfined
```

安全边界：

- 仍不使用 `privileged: true`。
- 仍不使用 `network_mode: host`。
- 仍无 NFS 端口映射到宿主机。

### 问题五：casper UUID 元数据缺失

表现：

```text
nfsmount ... done
Unable to find a live file system on the network
```

根因：

- Ubuntu Desktop initrd 内置 `/conf/uuid.conf`。
- casper 挂载 NFS 后会检查：

```text
/cdrom/casper/*.squashfs
/cdrom/.disk/casper-uuid*
```

- 仅提取 `casper/vmlinuz`、`casper/initrd`、`casper/*.squashfs` 不够。
- 缺少 `.disk/casper-uuid-generic` 时，即使 NFS 已挂载成功，也会被 casper 判定为不是匹配的 live filesystem。

处理：

- Ubuntu NFS 导出目录必须包含：

```text
.disk/casper-uuid-generic
.disk/info
casper/vmlinuz
casper/initrd
casper/*.squashfs
```

- 文件权限必须至少为匿名只读可读：

```text
.disk/                 0755
.disk/casper-uuid-*    0644
.disk/info             0644
casper/*.squashfs      0644
```

### 问题六：Ubuntu 24.04 layered livefs 文件名不完整

表现：

```text
File system layers are missing:
"/cdrom/casper/minimal.standard.live.squashfs" doesn't exist.
```

或先进入图形层后出现：

```text
黑屏，只显示可移动的叉形鼠标
```

根因：

- Ubuntu 24.04 Desktop 使用 layered livefs。
- ISO 的 Rock Ridge 真实文件名是点号形式，例如：

```text
casper/minimal.standard.squashfs
casper/minimal.standard.live.squashfs
casper/minimal.standard.live.manifest
casper/minimal.standard.live.size
casper/minimal.standard.live.squashfs.gpg
casper/install-sources.yaml
```

- 早期 ISO9660 提取器只读取了 ISO9660 层文件名，把部分文件提取成
  下划线形式，例如：

```text
minimal_standard_live.squashfs
install_sources.yaml
```

- casper 和 Ubuntu Desktop installer 按 Rock Ridge / YAML 声明的点号路径
  查找文件，因此 NFS 已挂载成功后仍可能缺 layer、卡图形层或黑屏。

处理：

- 修复 `scripts/image-factory/extract-iso9660-file.py`：
  - 解析 Rock Ridge `NM` 字段。
  - 保留点号、连字符等真实文件名。
  - 允许提取 `install-sources.yaml`、`*.manifest`、`*.size`、`*.gpg` 等
    casper companion 文件。
- 修复 `scripts/image-factory/prepare-linux-boot-artifacts.sh`：
  - 提取 `casper/*.squashfs` 的同时提取对应 `*.manifest`、`*.size`、
    `*.gpg`。
  - 为旧目录补 `install-sources.yaml` 兼容入口。
  - 对已经存在的旧下划线 squashfs 文件创建点号 hardlink 兼容名。
  - 不使用 symlink，避免重新引入 livefs symlink 安全风险。
- 对当前实验目录补齐文件后，容器内 NFS 导出可见：

```text
install-sources.yaml
minimal.standard.live.manifest
minimal.standard.live.size
minimal.standard.live.squashfs.gpg
minimal.standard.live.squashfs
```

验证：

```bash
docker exec synaboot-nfs-lab sh -lc \
  'for f in install-sources.yaml minimal.standard.live.manifest minimal.standard.live.size minimal.standard.live.squashfs.gpg minimal.standard.live.squashfs; do test -f /srv/synaboot/images/linux/ubuntu-24.04/casper/$f && echo ok:$f || echo missing:$f; done'

find data/images/linux/ubuntu-24.04/casper -maxdepth 1 -type l -print -quit | wc -l
bash scripts/preflight/check-iso-extractor-safety.sh
```

期望：

```text
所有关键文件输出 ok
symlink 数量为 0
ISO extractor safety preflight APPROVED
```

### 问题七：Ubuntu 24.04 图形启动黑屏

表现：

```text
能进入图形模式，但屏幕全黑，只能看到可移动的叉形鼠标。
```

根因：

- 24.04 已经成功越过 initramfs 和 NFS livefs 挂载阶段。
- 黑屏发生在图形驱动 / desktop installer 阶段。
- Ubuntu 24.04 ISO 自带 `Ubuntu (safe graphics)` 菜单项，其 kernel 参数
  相比默认入口增加 `nomodeset`。

处理：

- FlashPXE 的 Ubuntu 24.04 NFS livefs 入口默认追加 `nomodeset`，等价采用
  Ubuntu 官方 safe graphics 路径。
- 当前菜单参数形态：

```text
kernel ${base-url}/images/linux/ubuntu-24.04/casper/vmlinuz ip=dhcp boot=casper netboot=nfs nfsroot=<NFS_IP>:/ubuntu-24.04 nomodeset --- quiet splash
initrd ${base-url}/images/linux/ubuntu-24.04/casper/initrd
boot
```

验证：

```bash
curl -fsS http://<SERVER_IP>:18080/boot/menu.ipxe | sed -n '/ubuntu_24_04/,/boot ||/p'
```

期望：

```text
Ubuntu 24.04 kernel 行包含 nomodeset
客户端不再停留在黑屏叉形鼠标界面
```

## 当前正式 FlashPXE 菜单策略

正式实验菜单只保留四个镜像入口：

```text
Windows 11 24H2 Pro Chinese x64
HotPE V2.8
Ubuntu 22.04.3 desktop amd64
Ubuntu 24.04 desktop amd64
```

不显示：

- HTTP RAM fallback
- Diagnostics
- Windows explicit bootmgfw diagnostic
- HotPE native BCD diagnostic
- HotPE raw BCD diagnostic

## 真实环境部署前检查清单

### 网络安全

- 主 DHCP 仍由现网路由器提供。
- 默认网关不变。
- 不启用 SynaBoot DHCP 地址分配。
- ProxyDHCP/TFTP/HTTP Boot 自动集成必须单独审批。
- NFS 服务必须确认不暴露到生产接口。

检查命令：

```bash
ss -lntu | rg ':(111|2049|20048|445)\b'
docker exec synaboot-nfs-lab showmount -e <NFS_IP>
docker exec synaboot-nfs-lab rpcinfo -t <NFS_IP> nfs 3
```

### Windows/HotPE

- SMB 容器必须保持运行。
- SMB share 至少包含 Windows/HotPE 所需目录。
- HotPE 启动链路使用已验证的 `wimboot` 参数。

### Ubuntu Desktop

- Ubuntu 不走 SMB/CIFS。
- Ubuntu 不使用 HTTP ISO RAM fallback 作为正式入口。
- NFS 使用独立地址。
- NFS 导出目录包含 `.disk/casper-uuid-generic` 和 `.disk/info`。
- 匿名只读用户可读取 `.disk` 和 `casper` 下的必要文件。
- Ubuntu 24.04 layered livefs 必须包含 Rock Ridge 真实文件名：
  - `casper/install-sources.yaml`
  - `casper/minimal.standard*.squashfs`
  - `casper/minimal.standard*.manifest`
  - `casper/minimal.standard*.size`
  - `casper/minimal.standard*.squashfs.gpg`
- Ubuntu 24.04 在实验 VM 或兼容性未知显卡上优先使用 `nomodeset`。
- livefs 兼容文件不得使用 symlink；如需兼容旧下划线文件名，使用普通文件或
  hardlink，并用 `find ... -type l` 验证为 0。

### 菜单发布

- 修改菜单模板后必须重新生成：

```bash
bash scripts/lab/render-proxynet-lab-assets.sh
SERVER_IP=<SERVER_IP> bash scripts/generate-ipxe-menu.sh
```

如生成脚本需要管理员 token，请在本机 shell 中预先导出环境变量，不要把 token
值写入文档、Git、命令历史或发布证据。

- 通过 HTTP 验证客户端实际拿到的菜单：

```bash
curl -fsS http://<SERVER_IP>:18080/boot/menu-lab.ipxe
curl -fsS http://<SERVER_IP>:18080/boot/menu.ipxe
```

## 最终原则

- Windows/HotPE：HTTP 引导 PE，SMB 提供安装介质和模块。
- Ubuntu Desktop：HTTP 提供 kernel/initrd，NFS 提供 casper livefs。
- SMB 和 NFS 的职责不要混用。
- 诊断入口不要进入正式菜单。
- HTTP RAM fallback 只用于临时排错，不作为真实部署方案。

## 2026-06-21 Windows 自动软件安装、Office 与 KMS 边界

### 问题现象

- 管理后台可以创建系统安装任务，但 Windows 目标此前只允许 OS-only。
- 即使后台选择了软件，Windows 安装阶段也不会自动消费 iPXE 变量。
- Office 办公套件需要安装后自动部署，并希望支持 Windows/Office 激活。

### 根因

- Windows Setup、WinPE 和已安装 Windows 不会自动读取 iPXE 环境变量。
- Windows 软件安装必须落在真实的安装后执行点，例如
  `Windows\Setup\Scripts\SetupComplete.cmd`。
- Office 现代部署不应把安装包放到 SynaBoot；应使用 Microsoft Office
  Deployment Tool，让客户端从官方来源下载安装。
- KMS 是企业批量授权机制，必须使用管理员自有 KMS 主机；不能内置公共 KMS、
  KMS 模拟器、破解脚本或产品密钥。

### 修复方案

- Windows 启动目标开放受控软件任务：
  - `postinstall_status=setupcomplete_helper_ready`
  - `software_assignment_enabled=true`
- 保留 HotPE/WinPE 显式注入 helper：
  - 管理员必须传入目标 Windows 根目录。
  - 只写入 `Windows\Setup\Scripts\SetupComplete.cmd`。
  - 不猜盘、不分区、不格式化、不改网络。
- Windows runner 支持：
  - `msi_install`：客户端下载审核通过的 MSI，校验后静默安装，结束后清理临时文件。
  - `office_odt_install`：客户端下载 Microsoft Office Deployment Tool，用受控
    Office 产品 ID 生成固定 `configuration.xml` 后执行 `/configure`。
- 激活支持：
  - 默认关闭。
  - 仅在管理员配置 `SYNABOOT_KMS_HOST` 后，通过 `slmgr.vbs` 和 `ospp.vbs`
    调用自有 KMS。
  - 不保存产品密钥，不内置任何公共 KMS 地址。

### 验证

```bash
python3 -m py_compile apps/api/main.py
bash scripts/preflight/check-software-assignment-flow.sh
npm run build  # apps/web
git diff --check
```

预检覆盖：

- Windows 软件任务可创建。
- Windows plan 暴露 `msi_install` / `exe_install` / `office_odt_install`。
- `activation.kms.enabled=false` 为默认状态。
- `activation.kms.public_kms_embedded=false`。
- Windows runner 包含 MSI、Office ODT、Windows KMS、Office KMS 受控分支。

### 后续真实环境注意事项

- Windows 自动软件安装必须确认 `SetupComplete.cmd` 已注入目标系统。
- Office 产品 ID 必须与客户自己的批量授权或订阅策略一致。
- 如需激活，必须使用客户自有 KMS/MAK/ADBA 等合法授权路径。
- 不要把 Office、Chrome、飞书等第三方安装包上传到 SynaBoot 镜像仓库。

## 2026-06-23 Windows 默认 Office 2021 与 Ubuntu 飞书来源修复

### 问题现象

- 管理后台给 Windows 客户端创建安装任务时，软件选择区域仍显示“Windows 目前只支持
  分配系统启动任务”，无法选择自动安装软件。
- Ubuntu 软件市场里“飞书”显示为当前系统不可用，不能加入安装任务。
- Windows 安装后需要默认安装 Office 2021 ProPlus，并在客户自有授权环境中自动激活
  Windows 与 Office。

### 根因

- Windows postinstall runner 的代码能力已经存在，但旧数据库种子和未刷新运行容器会让
  前端继续拿到旧的 `software_assignment_enabled=false` 语义。
- 飞书官网的下载页是 HTML 页面，不是可直接传给 runner 的 `.deb` 安装包地址。平台不能
  把“官方下载页”当成“自动安装直链”，否则客户端只会下载网页而不是安装包。
- Office 自动安装需要走 Microsoft Office Deployment Tool。SynaBoot 不能托管 Office
  安装包，也不能内置公共 KMS、产品密钥、KMS 模拟器或破解脚本。

### 修复方案

- Windows 启动目标保持 `software_assignment_enabled=true`，创建 Windows 安装任务时
  默认加入 `microsoft-office` 软件包。
- Office 默认变体更新为：
  - `install_action=office_odt_install`
  - `installer_type=office_odt`
  - `package_name=ProPlus2021Volume`
  - ODT 下载地址使用 Microsoft 官方 `go.microsoft.com` 链接。
- 对既有 SQLite 数据做幂等迁移，避免旧 `office-windows-odt` 记录继续停留在旧产品 ID
  或不可执行状态。
- KMS 仍默认关闭，仅在管理员配置以下变量后启用：

```bash
SYNABOOT_KMS_HOST=<客户自有 KMS 主机>
SYNABOOT_KMS_PORT=1688
SYNABOOT_WINDOWS_KMS_ACTIVATE=1
SYNABOOT_OFFICE_KMS_ACTIVATE=1
```

- Ubuntu 飞书改为显式来源策略：
  - 未配置 `SYNABOOT_FEISHU_UBUNTU_DEB_URL` 时，只展示为待补官方 deb 直链，不能自动安装。
  - 配置该变量为官方 Linux amd64 `.deb` 直链后，才迁移为 `download_deb` 并进入可分配集合。
  - 仍不把飞书安装包保存到 SynaBoot、SMB、HTTP 镜像目录或 Git。

### 验证

```bash
python3 -m py_compile apps/api/main.py
bash scripts/preflight/check-software-assignment-flow.sh
npm run build  # apps/web
docker compose config
git diff --check
docker compose up -d --build
```

运行容器内已确认：

- Windows target 返回 `software_assignment_enabled=true`。
- Windows target 的可分配软件包含 `microsoft-office -> office-windows-odt`。
- Windows assignment 即使未显式选择软件，也会默认解析出 Office 2021 ProPlus ODT 计划。
- 未设置 `SYNABOOT_FEISHU_UBUNTU_DEB_URL` 的运行环境中，飞书不会误入 Ubuntu 可执行软件列表。

### 真实环境注意事项

- 如果后台仍显示 Windows 不能选择软件，优先确认容器已经重新构建并重启，且数据库迁移已执行。
- 如果要让 Ubuntu 自动安装飞书，必须先由管理员提供并审核飞书官方 Linux amd64 deb 直链；
  仅填写 `https://www.feishu.cn/download` 不会生效。
- Windows/Office 自动激活只适用于客户自有合法 KMS、MAK、ADBA 或订阅授权体系。没有 KMS
  主机时，runner 会保持激活步骤关闭。
- Office 2021 ProPlus 的产品 ID、通道和授权模型必须与客户的批量授权协议匹配。

## 2026-06-23 Windows 分区预设撤回与安装任务预设保留

### 问题现象

- 管理后台已经能给客户端分配 Windows/Ubuntu 安装任务和自动软件，但还缺少“常用安装任务
  预设”。
- 曾尝试把 Windows 分区模板放入安装任务预设，但批量装机场景中，目标机器可能存在不同
  硬盘数量、容量、启动模式、现有数据保留策略和厂商恢复分区。
- 如果后台给所有机器统一下发分区模板，容易让管理员误以为这是安全的通用能力。

### 根因

- 原有 `DeploymentAssignment` 只保存启动目标和软件清单，没有任务序列语义。
- 软件变体缺少企业 deployment type 常用字段，例如安装上下文、检测规则、依赖、返回码和
  重启策略。
- Microsoft 的企业部署模型可以做分区，但通常依赖任务序列、条件、变量和 WinPE 侧硬件/
  磁盘探测，而不是一个静态“万能分区预设”。
- 当前 FlashPXE 尚未具备目标磁盘识别、数据保留确认、dry-run、回滚和审计闭环，因此不应
  在后台保留可选分区模板入口。

### 修复方案

- 撤回 `PartitionTemplate` 公开能力：
  - 删除 `/api/partition-templates` 读写入口。
  - 删除管理后台创建任务时的分区模板选择。
  - 删除 `assignment-options`、`DeploymentAssignment` 和 postinstall plan 中的分区模板字段。
  - 老实验库中如果已经存在 `partition_template_id` legacy 列，仅写入空值兼容，不再暴露。
- 保留 `InstallPreset`：
  - 默认预设 `windows-office-standard`。
  - 绑定 Windows 启动目标和默认 `microsoft-office` 软件包。
- 新增 `DeploymentAssignment.task_sequence_plan`：
  - Windows 任务记录 `boot_winpe`、`collect_hardware`、`apply_windows`、
    `inject_bootstrap`、`first_boot`、`install_software`、
    `detect_software`、`report_result`。
- 管理后台创建安装任务面板新增：
  - 安装任务预设选择。
  - 软件市场多选软件和软件集合。
- 管理后台新增“安装任务预设”菜单，用于查看可复用的系统 + 软件组合。
- 2026-06-24 追加修复：
  - Windows runner 增加 `exe_install` 受控动作，适合官方 EXE 静默安装器。
  - `exe_install` 必须填写审核过的静默参数，否则后端拒绝保存，避免首次启动进入
    需要人工点击的安装器界面。
  - MSI/EXE 使用受控返回码模型，`0` 和 `3010` 可作为成功路径。
  - HotPE/WinPE 注入 helper 支持 `-WindowsRoot` 精确指定；未指定时只在唯一发现
    一个离线 Windows 目录时自动注入，找不到或多个候选都会 fail-fast。
  - 安装任务预设支持归档/恢复，归档预设不会进入新的可分配任务列表。

### 验证

```bash
python3 -m py_compile apps/api/main.py
bash scripts/preflight/check-software-assignment-flow.sh
npm run build  # apps/web
```

预检脚本已覆盖：

- `assignment-options` 返回 Windows 默认安装任务预设。
- Windows assignment 继承 `windows-office-standard`。
- postinstall plan 保留安装预设 ID，且不再暴露分区模板 ID。
- task sequence 不再包含分区模板字段。
- HTTP API 可读取 `/api/install-presets`。
- Windows EXE 无静默参数会被拒绝，审核后的 EXE 静默安装器可进入 Windows
  postinstall plan。
- 预设归档/恢复状态可被后端持久化。

## 2026-06-24 Windows 管理员审核直链自动安装深化

### 问题

- Windows 软件不像 Ubuntu apt 那样天然有统一软件源；很多企业场景只有厂商安装器
  直链、管理员审核下载链接或企业软件下载入口。
- 旧文档和 UI 文案容易让管理员误以为 Windows 软件必须来自“正式软件源”或
  “官方来源页”，导致实际可静默安装的 EXE/MSI 也不敢配置到自动安装任务中。

### 处理

- 新增 `source_policy=admin_reviewed_download`：
  - 适用于 `msi_install`、`exe_install`、`download_deb`、`office_odt_install`
    这类独立安装器动作。
  - 可以不填写 `official_source_url`。
  - 必须填写 HTTPS `download_url`，且不得指向 SynaBoot 自身、`/images`、`/boot`
    或本机/内网保留地址。
  - Windows `exe_install` 仍必须填写审核过的静默参数。
- 管理后台软件市场新增“管理员审核直链”来源策略选项。
- 创建安装任务时，管理员审核直链的 Windows EXE 可以像 WinSCP、Office 一样进入
  Windows postinstall plan，由安装后的 Windows runner 自动下载并静默安装。

### 验证

```bash
python3 -m py_compile apps/api/main.py
bash scripts/preflight/check-software-assignment-flow.sh
npm run build  # apps/web
```

预检脚本新增覆盖：

- 新建 `corp-tool-windows-x64`，不填写官方来源页，只填写管理员审核 HTTPS 安装器直链。
- 未审核时不可分配，审核通过后可分配。
- Windows 目标软件目录能看到该软件。
- 创建 Windows 安装任务时，该软件与默认 Office 一起进入 `resolved_software_plan`。
- postinstall plan 保留 `admin_reviewed_download` 来源策略，并通过 Windows runner 校验。

### 后续真实环境注意事项

- 自动分区不能作为当前阶段统一预设开放；未来如恢复，必须先完成目标磁盘识别、
  管理员二次确认、审计日志、dry-run 和回滚策略。
- 当前 Windows 自动软件仍依赖完整 Windows 首次启动后的 runner；WinPE 阶段只负责确认
  目标 Windows 根目录并注入 `SetupComplete.cmd`。
- 任何新增软件的自定义安装路径必须由该软件变体显式声明支持，不能作为通用 Windows 能力。

## 2026-06-24 飞书 Windows MSI 自动安装配置

### 问题

- 之前飞书 Windows 变体使用的是 EXE/下载页形态，无法可靠判断静默安装参数，
  也不能作为 Windows 首次启动后自动安装的稳定输入。
- 管理员已确认飞书官方提供 MSI 批量部署教程，并提供可直接下载的 MSI 链接。

### 处理

- 将默认软件市场中的 `feishu-windows-x64` 改为飞书官方 MSI 批量部署包：
  - `version=7.68.6`
  - `installer_type=msi`
  - `install_action=msi_install`
  - `source_policy=admin_reviewed_download`
  - `signature_policy=vendor_signed`
  - `silent_args=/qn /norestart`
  - `review_status=approved`
  - `enabled=true`
- 增加数据库迁移逻辑：旧实验环境启动后会自动把已有 `feishu-windows-x64`
  更新为 MSI 配置。
- 保持软件市场边界：SynaBoot 不保存、不缓存、不转发飞书安装包；Windows 客户端
  在首次启动 runner 中直接从飞书 CDN 下载并执行 MSI 静默安装。

### 验证

```bash
python3 -m py_compile apps/api/main.py
bash scripts/preflight/check-software-assignment-flow.sh
bash scripts/preflight/check-public-runtime-boundary.sh
npm run build  # apps/web
git diff --check
```

预检脚本新增覆盖：

- Windows 目标软件目录中 `feishu-windows-x64` 必须是 `msi_install` / `msi`。
- 飞书 Windows MSI 的下载 URL 必须等于管理员提供的飞书 CDN 直链。
- 创建 Windows 安装任务选择“飞书”时，`resolved_software_plan` 必须包含
  `feishu-windows-x64`，并与默认 Office 变体共同进入 Windows postinstall plan。
- Windows runner 校验飞书 MSI 的静默参数为 `/qn /norestart`。

### 后续真实环境注意事项

- 真实安装仍取决于 Windows 镜像是否已经注入 `SetupComplete.cmd -> runner.ps1`
  链路；未完成注入时，飞书 MSI 只会出现在任务计划中，不会在系统首次启动后执行。
- 飞书 CDN 直链如果未来失效，需要在软件市场维护同一变体的 `download_url`
  并重新审核；不应把 MSI 上传到 SynaBoot 服务器作为替代。
