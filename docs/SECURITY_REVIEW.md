# 安全审查记录

## 网络审查

`network_safety_agent` 已批准 Phase 2 零侵入范围：

- `SERVER_IP=192.168.1.168`
- 仅开放 `18080:8080/tcp`
- Nginx 仅提供 HTTP 静态文件与 API 反代
- 不启用 DHCP / ProxyDHCP / TFTP / Samba
- 不使用 host network
- 不使用 privileged
- 不挂载 `/`、`/etc`、`/var/run/docker.sock`
- 不开放 UDP `67/68/69/4011`

后续新增端口、Samba、HTTPS、上传大文件、系统命令或 Compose 网络行为变化时，
必须重新审查。

## 应用安全修正

- 公开 `GET /api/images` 只读取缓存，不触发全量 SHA256 扫描。
- `POST /api/scan`、`POST /api/menu/generate`、`POST /api/jobs` 需要
  `X-SynaBoot-Admin-Token`。
- 镜像启用/禁用接口同样需要 `X-SynaBoot-Admin-Token`，成功后会同步重生成
  `menu.ipxe`。
- 未设置 `SYNABOOT_ADMIN_TOKEN` 时，写接口默认禁用。
- Ubuntu autoinstall 默认模板不包含 `storage:` 自动分区配置。
- 构建任务标题会被限制为安全字符，且不会拼入 autoinstall shell 命令。
- `.env` 与 `.env.*` 已忽略，避免管理员 token 被误提交；`.env.example`
  保持可追踪。
- 已删除未使用的旧前端脚本，避免 DOM XSS 回归点。

## 端到端验证

当前宿主机 `8080/tcp` 已有其他服务监听。为避免影响现网服务，默认对外端口已迁移到
`18080/tcp`，并已由 `network_safety_agent` 审查批准。

```bash
docker compose up -d --build
```

验证通过：

```bash
curl http://localhost:18080/
curl http://localhost:18080/boot/menu.ipxe
curl http://localhost:18080/images/
curl http://localhost:18080/api/network-safety
```

验证后已执行：

```bash
docker compose down
```

默认部署为 `18080/tcp`。本轮验证前预检显示 `18080/tcp` 未监听。

## Phase 2 实现后审查

当前状态：代码级审查通过。宿主机 `8080/tcp` 被现有非 SynaBoot 服务占用，
因此未替换该端口上的服务；已使用获批的默认 `18080/tcp` 端口完成 Docker Compose
端到端验证，并在验证后执行 `docker compose down`。

审查范围：

- Docker Compose 网络与挂载配置。
- Nginx HTTP 静态服务和 API 反代。
- Python API 的路径和任务输出范围。
- Worker 内部扫描行为。
- 脚本中的网络变更命令。

审查结论：

- Compose 最终配置仅发布 `18080/tcp`。
- API 仅通过 Compose 内部 `expose: 8000` 暴露给 Nginx 和 Worker。
- Worker 不发布端口，只请求内部 API 触发镜像扫描。
- 未使用 `network_mode: host`。
- 未使用 `privileged: true`。
- 未挂载宿主机 `/`、`/etc`、`/var/run/docker.sock`。
- 未开放 UDP `67/68/69/4011`。
- 未启用 DHCP、ProxyDHCP、TFTP、Samba。
- 未发现脚本执行路由、DNS、网关、防火墙修改命令。

验证命令：

```bash
SERVER_IP=192.168.1.168 bash scripts/preflight/check-network-safety.sh
SERVER_IP=192.168.1.168 bash scripts/preflight/check-compose-config-safe.sh
docker compose up -d --build
curl http://localhost:18080/
curl http://localhost:18080/boot/menu.ipxe
curl http://localhost:18080/images/
curl http://localhost:18080/api/network-safety
docker compose down
python3 -m py_compile apps/api/main.py apps/worker/scan_images.py
bash -n scripts/preflight/check-network-safety.sh scripts/generate-ipxe-menu.sh scripts/sync-metadata.sh scripts/create-ipxe-usb.sh scripts/image-factory/create-job-template.sh
```

环境限制：

- 当前宿主机已有服务监听 `8080/tcp`，且返回内容不是 SynaBoot。
- 未停止或修改该未知服务。
- 默认端口已迁移到 `18080/tcp`，正式部署前需要管理员确认该端口未被占用，再执行 `docker compose up -d`。

## Phase 3 只读启动入口审查

当前状态：只读模型审查通过；TL-ER6120T 设备身份已由截图确认，
管理员已确认当前设备不能下发本项目所需 PXE/HTTP Boot 启动元数据；
主路由 DHCP Option `66/67` 路线当前不推荐依赖；Phase 3.3
继续保持 `BLOCKED`，仅允许 Boot Metadata Proxy 可行性评估。

审查范围：

- `/api/boot-entry` 只读启动入口状态模型。
- `/api/boot-assets` 固定白名单 boot loader 元数据清单。
- `/api/network-safety.phase3_gate` 只读网络安全门禁摘要。
- Web UI “启动入口”只读展示页。
- Web UI “本地事实门禁”只读展示面板。
- Web UI “网络安全”只读门禁展示。
- Nginx `/boot/` 静态服务白名单。
- `BOOT_ENTRY_RESEARCH.md`、`BOOT_ENTRY_INTEGRATION.md`、
  `BOOT_ENTRY_LOCAL_VERIFICATION.md`。

审查结论：

- 未启用 DHCP Server。
- 未启用 ProxyDHCP。
- 未启用 TFTP。
- 未开放 UDP `67/68/69/4011`。
- 未修改 TP-Link、OpenWrt、交换机、AP、VLAN、DNS、路由、防火墙或网关。
- `/api/boot-entry` 只返回只读状态、文档入口、待确认项和安全门禁。
- `/api/boot-entry` 保留 `phase=3.1` 作为后端只读模型阶段，仅新增
  `display_phase=3.4` 和 `display_status` 作为 Web UI 展示层元数据。
- `/api/boot-entry` 的 `phase3_3_gate` 只新增已确认事实、仍缺事实、
  解除门禁前置条件和禁止推断列表，不新增写接口或启用入口。
- `/api/boot-assets` 只扫描固定白名单 loader 文件名，不下载、生成、替换、删除或执行 loader。
- Boot loader 文件和父目录 symlink 不会被标记为可用。
- Nginx `/boot/` 仅允许精确访问 `menu.ipxe` 和固定白名单 loader，其它路径返回 404，并启用 `disable_symlinks on`。
- Web UI 仅展示门禁状态、文档路径、loader 元数据和本地事实门禁，
  没有配置提交按钮或网络操作按钮；所有新增门禁文本经前端转义后渲染。
- `/api/network-safety` 仅新增只读 `phase3_gate`，同步展示 Phase 3.3
  门禁状态、下一步范围和三个禁止标志，不新增写接口或服务启用入口。
- Web UI “网络安全”页只展示 `phase3_gate`，其中允许实现、允许启用服务、
  允许生产 LAN 测试均为 `False`。
- 已通过管理员只读截图确认 TP-Link 设备为 `TL-ER6120T`，硬件版本为
  `TL-ER6120T 1.0`，当前固件为 `1.2.2 Build 240829 Rel.84642n`。
- 管理员当前未找到 DHCP Option `66/67` 或等价 boot option 配置入口，
  因此 Phase 3.3 默认不依赖主路由 DHCP Option 路线。
- 不能仅凭 TL-ER6120T 型号或固件版本推断 Option `66/67`、next-server、
  Vendor Class 或 Client Architecture 可用。
- Phase 3.3 只允许继续 Boot Metadata Proxy 可行性评估；不得实现、启用或测试
  DHCP、ProxyDHCP、TFTP 或任何 UDP `67/68/69/4011` 服务。

验证命令：

```bash
python3 -m py_compile apps/api/main.py apps/worker/scan_images.py
rm -rf apps/api/__pycache__ apps/worker/__pycache__ scripts/preflight/__pycache__ && python3 scripts/preflight/check-phase3-gates.py && test -z "$(find apps scripts -path '*/__pycache__*' -print)"
node --check apps/web/assets/app.js
bash scripts/preflight/check-network-safety.sh
bash scripts/preflight/check-compose-config-safe.sh
ss -lntu | grep -E ':(67|68|69|4011)\b' || true
rg -n "network_mode: host|privileged: true|67:|68:|69:|4011:|dnsmasq|proxydhcp|tftp|dhcp" docker-compose.yml scripts apps config docs PLAN.md README.md
git diff --check
```

Phase 3.6 收口补充验证，覆盖 Phase 3.4 本地事实门禁面板：

```bash
python3 -m py_compile apps/api/main.py apps/worker/scan_images.py
rm -rf apps/api/__pycache__ apps/worker/__pycache__ scripts/preflight/__pycache__ && python3 scripts/preflight/check-phase3-gates.py && test -z "$(find apps scripts -path '*/__pycache__*' -print)"
node --check apps/web/assets/app.js
bash scripts/preflight/check-network-safety.sh
bash scripts/preflight/check-compose-config-safe.sh
ss -lntu | grep -E ':(67|68|69|4011)\b' || true
git diff --check
```

补充 smoke test 覆盖：

- `scripts/preflight/check-phase3-gates.py` 可重复校验以下只读门禁条件。
- `check-phase3-gates.py` 加载 API 状态模型时不生成 `__pycache__`。
- `phase=3.1` 仍表示后端只读模型阶段。
- `display_phase=3.4` 和 `display_status` 仅表示 Web UI 只读展示阶段。
- `phase3_3_gate.status=router_option_path_not_recommended_but_blocked`。
- `/api/network-safety.phase3_gate.status=router_option_path_not_recommended_but_blocked`。
- `confirmed_evidence`、`missing_local_facts`、`blocked_until`、
  `do_not_infer` 均存在。
- DHCP、ProxyDHCP、TFTP 状态仍为关闭。
- `implementation_allowed`、`service_enablement_allowed`、
  `production_lan_testing_allowed` 仍为 `False`。

后续门禁：

- Phase 3.3 继续保持 `BLOCKED`；不得进入实现、启用或生产 LAN 测试。
  当前下一步仅限 Boot Metadata Proxy 可行性评估。
- 任何 DHCP boot option、ProxyDHCP、TFTP、UDP `67/68/69/4011`、端口、Compose、路由器或网关相关变更，必须重新经过 `research_agent`、`network_safety_agent`、`security_audit_agent` 和 `project_decision_agent` 审查。
- 本记录不批准生产 LAN 自动网络启动集成。
