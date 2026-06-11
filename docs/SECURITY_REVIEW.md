# 安全审查记录

## 初始网络审查

`network_safety_agent` 已批准 Phase 1 范围：

- `SERVER_IP=192.168.1.168`
- 仅开放 `8080:8080/tcp`
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

当前宿主机 `8080/tcp` 已有其他服务监听。为避免影响现网服务，已先由
`network_safety_agent` 审查并批准 loopback 临时验证方案：

```bash
SYNABOOT_HTTP_BIND=127.0.0.1:18180 SYNABOOT_HTTP_PORT=18180 docker compose up -d --build
```

验证通过：

```bash
curl http://127.0.0.1:18180/
curl http://127.0.0.1:18180/boot/menu.ipxe
curl http://127.0.0.1:18180/images/
curl http://127.0.0.1:18180/api/images
```

验证后已执行：

```bash
SYNABOOT_HTTP_BIND=127.0.0.1:18180 SYNABOOT_HTTP_PORT=18180 docker compose down
```

默认部署仍为 `8080/tcp`。正式部署前需确认并释放当前宿主机 `8080/tcp`。

## Phase 1 实现后审查

当前状态：代码级审查通过。宿主机 `8080/tcp` 被现有非 SynaBoot 服务占用，
因此未替换该端口上的服务；已使用获批的 loopback 端口完成 Docker Compose
端到端验证。

审查范围：

- Docker Compose 网络与挂载配置。
- Nginx HTTP 静态服务和 API 反代。
- Python API 的路径和任务输出范围。
- Worker 内部扫描行为。
- 脚本中的网络变更命令。

审查结论：

- Compose 最终配置仅发布 `8080/tcp`。
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
SERVER_IP=192.168.1.168 docker compose config
SYNABOOT_HTTP_BIND=127.0.0.1:18180 SYNABOOT_HTTP_PORT=18180 docker compose up -d --build
curl http://127.0.0.1:18180/
curl http://127.0.0.1:18180/boot/menu.ipxe
curl http://127.0.0.1:18180/images/
curl http://127.0.0.1:18180/api/images
SYNABOOT_HTTP_BIND=127.0.0.1:18180 SYNABOOT_HTTP_PORT=18180 docker compose down
python3 -m py_compile apps/api/main.py apps/worker/scan_images.py
bash -n scripts/preflight/check-network-safety.sh scripts/generate-ipxe-menu.sh scripts/sync-metadata.sh scripts/create-ipxe-usb.sh scripts/image-factory/create-job-template.sh
```

环境限制：

- 当前宿主机已有服务监听 `8080/tcp`，且返回内容不是 SynaBoot。
- 未停止或修改该未知服务。
- 正式部署到默认端口前，需要管理员释放 `8080/tcp`，再执行 `docker compose up -d`。
