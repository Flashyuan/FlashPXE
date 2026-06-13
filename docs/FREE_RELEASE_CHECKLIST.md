# SynaBoot 免费版发布检查清单

本清单用于当前 GitHub 免费版发布线：

```text
origin/codex/synaboot-phase1
```

当前目标：

- GitHub 只发布免费版代码。
- 本机 owner/developer 可以保留私有全功能工作区。
- 商业源码、私有 license、混淆 bundle 和真实镜像不进入免费版 GitHub 分支。
- 基础装机能力不因无 license、无联网而降级。

## 1. 发布前必须确认

必须确认以下事实：

- 当前分支是 `codex/synaboot-phase1`。
- 当前 upstream 是 `origin/codex/synaboot-phase1`。
- `origin` 指向 GitHub，但发布证据不得输出完整 remote URL。
- `.env`、token、私钥、账号密码不进入 Git。
- 真实 ISO/WIM/ESD/IMG/VHD/VHDX/QCOW2 不进入 Git。
- `data/metadata/*.sqlite3`、日志和构建产物不进入 Git。
- `commercial/`、`private-commercial/`、`private/`、`enterprise/`、
  `proprietary/`、`paid/`、`dist-commercial/`、`dist-obfuscated/`
  只作为本机私有工作区。
- Docker Compose、API 和 Web UI 默认运行路径不得引用上述私有商业目录。
- `.obf.js`、`.obf.py`、`.min.private.js`、`.license`、`.lic`
  不进入免费版发布线。

## 2. 必跑命令

提交或推送前至少运行：

```bash
bash scripts/preflight/check-release-scope.sh
bash scripts/preflight/check-private-commercial-scope.sh
bash scripts/preflight/check-edition-boundary.sh
bash scripts/preflight/check-public-runtime-boundary.sh
bash scripts/preflight/check-autoinstall-boundary.sh
bash scripts/preflight/check-subagent-governance.sh
bash scripts/preflight/check-token-disclosure.sh
bash scripts/preflight/collect-release-evidence.sh
```

如果本轮变更涉及 Compose、网络、启动入口、脚本或安全边界，还必须运行：

```bash
bash scripts/preflight/check-network-safety.sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/preflight/check-phase3-gates.py
bash scripts/preflight/check-compose-config-safe.sh
git diff --check
git diff --cached --check
```

## 3. Subagents 复核

发布前必须至少完成：

- `git_audit_agent`：
  - 复核 diff。
  - 复核 `collect-release-evidence.sh` 输出。
  - 复核 `docs/SUBAGENT_SESSION_POOL.md` 中 stale/active 状态没有掩盖缺失审计。
  - 复核商业关键词命中文件仅为公开说明、manifest、UI 展示或审计规则。
  - 复核 staged 文件不包含 forbidden scope。

- `security_audit_agent`：
  - 复核 secrets、license、混淆 bundle、路径越界、危险脚本、Docker 边界。
  - 如果涉及网络、Compose 或启动入口，复核 Phase 1/2 零侵入边界。

- `project_decision_agent`：
  - 复核本次发布仍属于免费版发布线。
  - 复核 Professional/Enterprise 内容仅为公开候选说明，不包含实现。

## 4. Commit 与 Push 规则

本仓库允许在审计通过后准备本地 commit。

推送远程属于高风险版本控制动作，必须在执行前获得用户二次确认。

本地 commit 完成后、远程 push 前，运行：

```bash
bash scripts/preflight/check-free-push-readiness.sh
```

该脚本会重新运行免费版发布证据链，并要求当前免费版分支没有未提交、
未暂存或未跟踪 public 文件。它只读检查，不执行 commit 或 push。

不得自动推送以下内容：

- 商业源码。
- 私有 license。
- 混淆 bundle。
- 真实系统镜像。
- `.env` 或 secrets。
- 数据库、日志、构建产物。
- 未审查的网络影响变更。

## 5. 允许发布的商业化内容

免费版 GitHub 分支只允许包含公开说明：

- Free / Professional / Enterprise 候选边界。
- 免费核心能力说明。
- 未来商业候选能力说明。
- 发布防线和审计规则。
- capability flags 的公开骨架。

不得包含：

- 付费功能完整实现。
- license 验证实现。
- 支付或联网授权实现。
- 混淆后的商业 bundle。
- 本机私有商业模块源码。

## 6. 当前推荐发布证据命令

```bash
bash scripts/preflight/collect-release-evidence.sh
```

该命令只读运行：

- 不启动服务。
- 不读取项目 `.env`。
- 不输出完整 remote URL。
- 不写日志或构建产物。
- 不扫描 `.gitignore` 覆盖的私有商业目录内容。

它会输出商业关键词命中文件清单。该清单不能自动放行，必须由
`git_audit_agent` 复核语义。

`check-token-disclosure.sh` 会拦截文档或脚本中的内联管理员 token 命令示例，例如把
`SYNABOOT_ADMIN_TOKEN=...` 直接拼接到 `bash`、`docker`、`curl`、
`python`、`node`、`sh` 或 `compose` 命令前。管理员 token 只能保存在
本机 `.env` 或受控会话中，不得进入 Git、工单、聊天或截图。

`check-edition-boundary.sh` 会校验免费版 capability manifest 和公开版本
catalog：Free 核心能力不得限量，Professional、Enterprise 和 Usage-based
只能作为候选说明，公开 catalog 不能变成 license gate。它还会用 AST
静态解析 `apps/api/main.py`，确认 API 内置默认能力和公开 JSON 完全一致，
避免配置文件缺失时默认展示边界漂移。

`check-public-runtime-boundary.sh` 会静态检查 API 和 Web 前端引用的
`/api/...` 运行时入口，阻断 license、payment、billing、subscription、
activation、professional、enterprise、usage-based、paid、commercial、
obfuscation 等商业实现或收费层端点进入免费版公开代码。
文档和 manifest 可以描述商业候选能力，但公开运行时不能包含对应实现入口。
该脚本还会校验 `config/synaboot/public-runtime.allowlist.json`，新增公开
API 路径必须先登记白名单并完成 subagents 复核。

`check-autoinstall-boundary.sh` 会静态检查 Phase 2.12 自动安装草稿边界：
免费版只允许 profile 草稿和只读 binding plan，不得创建真实 ISO 绑定表、
策略表、绑定写接口、菜单接入、默认策略或清盘模板。

`check-subagent-governance.sh` 会校验 `.codex/agents` 仍然只有 11 个
项目角色，且 `PLAN.md` 包含 subagent 调用预算、会话复用和超量调用复盘规则。
这用于防止把长期角色池误用成无限新建的审计会话。

`collect-release-evidence.sh` 会校验
`config/synaboot/commercial-indicators.allowlist.json`。商业关键词只能出现在
已登记的公开说明、manifest、UI 展示、agent 规则和发布护栏文件中；新增
命中文件必须先登记 allowlist 并复核语义。
