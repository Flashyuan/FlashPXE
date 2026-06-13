# SynaBoot 私有商业流程边界

本文档说明未来商业功能的私有开发、混淆打包和发布护栏。

当前 GitHub 分支仍然只作为免费版发布线。本文档不是商业功能实现，
不包含 license、支付、联网授权、混淆算法或商业源码。

## 1. 基本原则

- 基础装机闭环永久免费。
- 免费版离线部署不依赖公网授权。
- 本机 owner/developer 环境可以保留永久全功能能力。
- 商业源码不得进入当前 GitHub 免费版分支。
- 私有 license、授权规则、混淆 bundle 和客户交付包不得进入当前免费版分支。
- 商业能力不得削弱 Phase 1/2 零侵入网络安全边界。

## 2. 免费版公开线

允许进入当前 GitHub 分支：

- 基础 HTTP/iPXE Boot 平台。
- ISO 扫描、准备状态和基础准备任务框架。
- HotPE 辅助 Windows 安装。
- Ubuntu/Linux 基础启动准备。
- 基础 Web UI。
- 基础自动安装草稿和只读绑定规划。
- 免费版 capability manifest。
- Free / Professional / Enterprise 的公开候选边界说明。
- 发布检查脚本和审计规则。

不得进入当前 GitHub 分支：

- 商业版专属源码。
- 私有 license 文件。
- 支付、计费、联网激活或授权校验实现。
- 混淆后的商业 bundle。
- 客户交付包。
- 真实 ISO/WIM/ESD/IMG/VHD/VHDX/QCOW2。
- `.env`、token、私钥、账号密码。
- 生成数据库、日志和构建产物。

## 3. 本机私有工作区

未来商业功能只能在 `.gitignore` 覆盖的本机私有路径中开发或打包。

推荐路径：

```text
private-commercial/
commercial/
enterprise/
proprietary/
paid/
dist-commercial/
dist-obfuscated/
```

约束：

- 私有路径不得被 Git 跟踪。
- 私有路径不得被 stage。
- 免费发布证据脚本不得读取这些路径内容。
- 私有路径中的源码、license、bundle 和客户包不得复制到公开目录。

## 4. 私有商业发布阶段

商业能力必须另走私有发布流程，不与当前免费版 GitHub push 混合。

建议阶段：

1. `project_decision_agent` 决定功能是否属于 Professional / Enterprise。
2. `architecture_agent` 确认免费核心不依赖商业模块。
3. `security_audit_agent` 审查 license、授权、secret 和路径隔离风险。
4. 私有工作区实现商业功能。
5. 私有打包流程生成商业 bundle。
6. 商业 bundle 在私有目录中混淆或打包。
7. `git_audit_agent` 确认商业源码、license 和混淆产物没有进入免费版 Git 范围。
8. 免费版 GitHub 分支只发布公开说明、免费代码和发布护栏。

当前阶段只允许完成 1、2、3、7、8 的公开护栏部分。
不实现商业模块加载、license、支付、联网授权或混淆流水线。

## 5. 商业混淆发布门槛

未来商业功能只有在进入私有商业发布流程时，才允许设计混淆或打包流水线。
当前免费版 GitHub 分支只允许保存本节规则，不允许保存混淆工具、混淆配置、
混淆产物或商业源码。

商业发布前必须满足：

- 商业源码位于 `.gitignore` 覆盖的私有工作区。
- 商业 bundle 输出到 `dist-commercial/` 或 `dist-obfuscated/` 等私有路径。
- 混淆或打包前后都不得复制到免费版公开目录。
- 混淆流程不得读取或上传真实 ISO、客户镜像、token、私钥或内网凭据。
- 混淆产物必须经过 `security_audit_agent` 和 `git_audit_agent` 审查，
  确认没有进入当前免费版 Git 范围。
- 若未来引入 license 校验，必须证明 Free 核心路径无 license 依赖，
  且离线基础装机能力不降级。

当前明确禁止：

- 在当前免费版分支实现混淆算法或混淆构建脚本。
- 在当前免费版分支保存 `.obf.js`、`.obf.py`、`.min.private.js`、
  `.license`、`.lic` 或客户交付包。
- 在公开 API 或 Web UI 中加入 license、billing、payment、subscription、
  activation、professional、enterprise、usage-based、paid、commercial 或
  obfuscation 运行时端点。
- 用“隐藏完整商业实现但 UI 不展示”的方式伪装成免费版代码。

## 6. 本机 owner/developer 全功能边界

用户本机允许保留永久全功能能力，但该能力必须与 GitHub 免费发布线隔离。

允许：

- 在 `.gitignore` 覆盖的私有目录中保存商业源码、实验配置和本机调试产物。
- 本机 owner/developer 模式不依赖公网授权。
- 免费版公开代码通过 capability 和 edition catalog 说明未来商业候选能力。

不允许：

- 把本机私有商业源码、license、混淆产物或客户包 stage、commit 或 push。
- 让免费核心功能依赖本机私有商业模块才能运行。
- 为了本机全功能体验，在公开分支加入商业实现入口。
- 让本机私有路径成为 Docker Compose 默认挂载或运行依赖。

## 7. 免费核心不可降级

以下能力不能因为没有 license、没有联网或未加载商业模块而降级：

- Docker Compose 本地部署。
- HTTP 镜像仓库。
- 本地 ISO 扫描。
- iPXE HTTP 菜单生成。
- 手动 iPXE/HTTP Boot。
- HotPE 辅助 Windows 安装。
- Ubuntu/Linux 基础启动准备。
- 基础 Web UI 镜像管理。
- 基础自动安装草稿和模板预览。
- 网络安全 preflight。

## 8. 发布前检查

提交或推送免费版前必须运行：

```bash
bash scripts/preflight/check-release-scope.sh
bash scripts/preflight/check-private-commercial-scope.sh
bash scripts/preflight/check-public-runtime-boundary.sh
bash scripts/preflight/collect-release-evidence.sh
```

必须确认：

- 当前分支仍是免费版发布线。
- 私有商业路径被 `.gitignore` 覆盖。
- 私有商业路径没有 tracked/staged/untracked public 文件。
- Docker Compose、API 和 Web UI 默认运行路径没有引用私有商业目录。
- `.license`、`.lic`、`.obf.js`、`.obf.py`、`.min.private.js` 未进入 Git 范围。
- 公开运行时代码没有 license、payment、billing、subscription、activation、
  professional、enterprise、usage-based、paid、commercial 或 obfuscation
  端点。
- 商业关键词命中文件只包含公开说明、manifest、UI 展示或审计规则。

远程 push 前还必须经过：

- `git_audit_agent` 审查。
- `project_decision_agent` 确认发布方向。
- 用户二次确认。

## 9. 禁止事项

- 不得把商业源码提交到当前 GitHub 免费分支。
- 不得把混淆 bundle 提交到当前 GitHub 免费分支。
- 不得把私有 license 或客户交付包提交到当前 GitHub 免费分支。
- 不得让 license 校验阻断免费核心功能。
- 不得在免费版中隐藏完整商业实现，只用 UI 禁用。
- 不得为了商业功能启用 DHCP、ProxyDHCP、TFTP、host network 或 privileged。
