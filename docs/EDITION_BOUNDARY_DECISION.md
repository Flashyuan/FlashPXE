# SynaBoot 版本边界决策记录

更新时间：2026-06-13

本文档记录 `project_decision_agent` 对 Free、Professional、Enterprise 和
Usage-based 第一版边界的条件批准结论。

当前 GitHub 分支只发布 Free 免费版代码。Professional、Enterprise 和
Usage-based 只作为公开候选说明，不包含 license、支付、联网授权、商业源码
或混淆 bundle。

## 1. 决策结论

```text
DECISION: APPROVED_WITH_CONDITIONS
```

批准方向：

- GitHub 当前分支只发布 Free 免费版代码。
- 本机 owner/developer 可永久全功能使用。
- Professional、Enterprise 和 Usage-based 仅作为公开候选边界。
- 当前不实现 license、支付、联网授权、商业源码或混淆流水线。
- 无 license、离线、未联网状态不得影响免费核心装机能力。
- 任何网络高风险能力不得默认开启。

## 2. Free：永久免费基础装机闭环

以下能力必须永久免费，不得限量，不得因离线或无 license 降级：

- Docker Compose 本地部署。
- HTTP 镜像仓库。
- 本地 ISO 扫描。
- HotPE 辅助 Windows 安装。
- Ubuntu/Linux 基础启动准备。
- iPXE HTTP 菜单生成。
- 手动 iPXE USB/ISO/EFI 启动。
- 手动 UEFI HTTP Boot。
- 基础 Web UI 镜像管理。
- 基础 Image Factory 模板。
- Ubuntu autoinstall / Windows Autounattend 安全草稿。
- 模板预览与变量白名单展示。
- 网络安全 preflight。
- Phase 3 只读启动入口状态。
- 基础文档、教程和故障排查。

## 3. Professional：高级效率候选

Professional 适合小团队或高频装机管理员，未来可采用订阅或一次性买断。

候选能力：

- 自动安装脚本库管理。
- 一个 ISO 绑定多个自动安装方案。
- 高级变量扩展预览。
- 默认镜像、默认脚本、菜单超时和脚本选择超时。
- 批量镜像标签、版本和生命周期管理。
- 一键诊断包导出。
- 更完整的 ISO 准备向导。

## 4. Enterprise：企业治理候选

Enterprise 适合企业长期运维、审计和多节点治理。

候选能力：

- 多管理员账号与 RBAC。
- 审计日志和操作追踪。
- 多节点/多站点管理。
- 镜像同步、校验和保留策略。
- LDAP/OIDC 企业身份集成。
- 装机报表、成功率、失败原因和机型统计。
- 企业支持、长期维护和升级策略。

## 5. Usage-based：按次或项目制候选

Usage-based 只适合高价值、重服务或大规模任务。

候选能力：

- 大规模批量无人值守装机任务。
- 企业级驱动包/脚本注入流水线。
- 自动生成定制镜像任务。
- 远程协助诊断。
- 专家模板生成。

## 6. 公开落地边界

允许进入当前免费版 GitHub 分支：

- `config/synaboot/capabilities.free.json`
- `config/synaboot/editions.public.json`
- `docs/FREE_RELEASE_CHECKLIST.md`
- `docs/PRIVATE_COMMERCIAL_FLOW.md`
- `docs/EDITION_BOUNDARY_DECISION.md`
- 发布范围、私有商业范围、token 泄露和版本边界预检脚本
- Web UI 对 Free 能力和商业候选的只读展示

禁止进入当前免费版 GitHub 分支：

- license、支付、联网授权实现。
- 商业功能完整源码。
- 混淆后的商业 bundle。
- 私有 license 文件。
- 会让 Free 核心能力变成受控功能的 gate 逻辑。

## 7. 发布前验证

提交或推送免费版前必须运行：

```bash
bash scripts/preflight/check-edition-boundary.sh
bash scripts/preflight/check-public-runtime-boundary.sh
bash scripts/preflight/collect-release-evidence.sh
```

`check-edition-boundary.sh` 必须证明：

- Free 发布线字段未被改成商业发布。
- Free 基础能力不限量。
- Free 核心能力没有 license gate。
- Professional、Enterprise 和 Usage-based 只声明为候选层。
- 公开 catalog 仍是展示用途，不是授权执行逻辑。
- API 内置默认 capability/catalog 与公开 JSON 完全一致，避免配置缺失时
  展示边界漂移。
- API 和 Web 前端没有 license、payment、billing、subscription、
  activation、professional、enterprise、usage-based、paid、commercial 或
  obfuscation 等商业实现或收费层运行时入口。
- 所有公开运行时 API 均登记在
  `config/synaboot/public-runtime.allowlist.json`，新增 API 前必须先完成
  架构、安全和 Git 审计。
