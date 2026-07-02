# Phase 3 本地只读设备能力确认记录

更新时间：2026-06-12

## 使用边界

本文是 Phase 3.3 解除阻塞前的本地事实收集模板。

只允许管理员人工只读查看并记录结果。

禁止事项：

- 不保存、应用、提交或重启任何网络设备配置。
- 不修改 DHCP 地址池、租约、DNS、默认网关、路由、防火墙、VLAN、NAT。
- 不启用 DHCP Server、ProxyDHCP、TFTP 或 DHCPv6 Boot。
- 不写入 DHCP Option `66/67`。
- 不写入 `next-server`、boot server、bootfile 或 bootfile URL。
- 不配置 Vendor Class 或 Client Architecture 分流。
- 不打开 UDP `67/68/69/4011`。
- 不把真实密码、token、私钥、完整公网账号或敏感截图提交到仓库。

本记录只证明“管理员看到了什么字段或能力”，不代表批准配置。

## 基础信息

```text
记录日期：2026-06-12
记录人：管理员提供截图，Codex 只读整理
确认方式：脱敏截图，页面为 TL-ER6120T 系统工具 / 软件升级 / 设备管理
是否保存或应用过任何配置：否。本次仅基于截图记录，未保存、应用或修改配置
是否重启过网络设备：否。本次仅基于截图记录，未执行重启
```

## 设备身份

```text
设备厂商：TP-LINK / 普联技术有限公司
设备准确型号：TL-ER6120T
硬件版本：TL-ER6120T 1.0
固件版本：当前软件版本 1.2.2 Build 240829 Rel.84642n；页面显示最新软件版本 1.2.3 Build 250812 Rel.80372n
管理界面语言：中文
当前主 DHCP 服务器地址：未由该截图确认；项目既有网络模型记录为 TP-Link 192.168.1.1
当前默认网关选项：未由该截图确认；项目安全边界要求保持 OpenWrt 192.168.1.4
当前 DNS 选项：未由该截图确认
SynaBoot 服务器 IP：未由该截图确认；项目默认示例为 192.168.1.168
```

## DHCP 启动字段只读观察

只记录字段是否存在，不填写字段值，不保存配置。

```text
是否看到 Option 66：未由该截图确认
字段名称或说明：当前截图为软件升级页面，不是 DHCP Option 页面；需继续只读查看 DHCP / 高级 DHCP / Option 配置页面

是否看到 Option 67：未由该截图确认
字段名称或说明：当前截图为软件升级页面，不是 DHCP Option 页面；需继续只读查看 DHCP / 高级 DHCP / Option 配置页面

是否看到 next-server / boot server / siaddr：未由该截图确认
字段名称或说明：当前截图未显示网络启动服务器、next-server 或 siaddr 字段

是否看到 bootfile name：未由该截图确认
字段名称或说明：当前截图未显示 bootfile name / boot file 字段

是否看到 bootfile URL / HTTP Boot URL：未由该截图确认
字段名称或说明：当前截图未显示 HTTP Boot URL 字段

是否看到 Vendor Class / Option 60：未由该截图确认
字段名称或说明：当前截图未显示 Vendor Class / Option 60 策略字段

是否看到 Client Architecture / Option 93：未由该截图确认
字段名称或说明：当前截图未显示 Client Architecture / Option 93 策略字段

是否看到可区分 PXEClient 与 HTTPClient 的策略：未由该截图确认
字段名称或说明：当前截图未显示按 PXEClient / HTTPClient 分流的策略字段

是否看到可区分 BIOS PXE、UEFI PXE、UEFI HTTP Boot 的策略：未由该截图确认
字段名称或说明：当前截图未显示按客户端架构区分启动参数的策略字段
```

## 现网安全状态只读记录

```text
普通客户端当前是否能获取 DHCP 地址：未由该截图确认
普通客户端默认网关是否仍为 192.168.1.4：未由该截图确认
普通客户端是否能访问内网：未由该截图确认
普通客户端是否能访问互联网：未由该截图确认
SynaBoot 是否参与普通 DHCP 租约分配：否。本次未修改 SynaBoot 或路由器配置
是否发现新的 UDP 67/68/69/4011 监听：未由该截图确认；需以本机 `ss` 和 preflight 结果为准
```

## 证据附件记录

只记录脱敏附件名称或说明。

不要提交包含管理员账号、密码、token、公网账号、公网 IP、客户信息或敏感备注的截图。

```text
脱敏截图 1：用户提供 TL-ER6120T 系统工具 / 软件升级 / 设备管理截图，文件名 acd3e89588c7ed35cf748fb79d465528.png
脱敏截图 2：
设备文档或固件说明引用：本记录未新增外部资料引用
备注：截图确认设备型号、硬件版本、当前软件版本和可升级软件版本；截图未显示 DHCP Option 或网络启动字段
```

## 本地结论

以下结论由管理员根据只读观察填写。

```text
Option 66 能力：不确定。该截图未显示 DHCP Option 页面
Option 67 能力：不确定。该截图未显示 DHCP Option 页面
next-server 能力：不确定。该截图未显示 next-server / boot server 字段
bootfile URL 能力：不确定。该截图未显示 HTTP Boot URL 字段
Vendor Class 分流能力：不确定。该截图未显示 Vendor Class / Option 60 策略
Client Architecture 分流能力：不确定。该截图未显示 Client Architecture / Option 93 策略
是否足以进入隔离环境抓包验证：否。仍需 Boot Metadata Proxy 隔离实验边界和审批
运营假设：管理员已确认当前 TL-ER6120T 不能下发本项目所需的 PXE/HTTP Boot 启动元数据，因此 Phase 3.3 默认不依赖主路由 DHCP Option 66/67 路线
后续方向：仅允许转入 Boot Metadata Proxy 可行性评估；该方向仍不得实现、启用或测试任何 ProxyDHCP/TFTP/DHCP 服务
```

该运营假设不等同于官方完整证明，也不代表已经完成隔离环境验证。
它只用于避免继续把 Phase 3.3 规划建立在当前不能满足需求的
主路由 DHCP Option 路线上。

## 仍需补充的只读截图

当前截图只能确认设备身份和软件版本，仍不足以解除 Phase 3.3 门禁。

请继续只读截图以下页面。不要填写、保存、应用或重启任何配置。

```text
1. 网络设置 / DHCP服务器 或等价 DHCP 主页面：
   用于确认 DHCP 页面结构、当前 DHCP 状态、地址池、网关、DNS 字段。

2. DHCP服务器 / 高级设置：
   用于寻找 Option、启动文件、启动服务器、PXE、TFTP、HTTP Boot 相关字段。

3. DHCP Option / 自定义 Option / Option 配置页面：
   用于确认是否支持 Option 66、Option 67，以及是否能新增或选择 Option 编号。

4. 地址池 / LAN DHCP 编辑页：
   只截图字段，不保存；用于确认是否有 per-pool boot option、next-server、bootfile、vendor class 绑定能力。

5. DHCP 客户端 / 地址保留页面：
   用于确认是否只是普通地址保留，还是带有启动参数或策略绑定能力。

6. 策略 / 规则 / 条件匹配 / Vendor Class 相关页面：
   用于确认是否能按 PXEClient、HTTPClient 或 Option 60 分流。

7. Client Architecture / Option 93 / 终端类型相关页面：
   用于确认是否能区分 BIOS PXE、UEFI PXE、UEFI HTTP Boot。

8. 软件版本说明：
   若页面可展开 1.2.3 Build 250812 的本地更新说明，只截图是否提到 DHCP Option / PXE / HTTP Boot；不建议为了研究直接升级。
```

## 后续门禁

本记录完成后，仍不能直接进入生产 LAN 写入配置。

下一步必须重新交由以下 subagents 审查：

- `research_agent`：核对本地事实和外部资料是否一致。
- `network_safety_agent`：判断是否允许进入隔离验证方案。
- `security_audit_agent`：审查文档、证据和风险边界。
- `project_decision_agent`：决定是否继续 TP-Link DHCP Boot Option 路线、继续阻塞或评估受控 ProxyDHCP。

在这些审查完成前，Phase 3.3 继续保持 `BLOCKED`。

即使后续进入 Boot Metadata Proxy 可行性评估，也必须继续满足以下条件：

- 不实现 ProxyDHCP。
- 不启用 TFTP。
- 不启用任何 DHCP 服务。
- 不修改 TL-ER6120T 配置。
- 不修改 OpenWrt 网关、路由、NAT、防火墙、DNS、VLAN 或 AP。
- 不开放 UDP `67/68/69/4011`。
- 不使用 Docker `network_mode: host`。
- 不使用 Docker `privileged: true`。
- TP-Link `192.168.1.1` 继续作为唯一 DHCP lease server。
- OpenWrt `192.168.1.4` 继续作为默认网关。
