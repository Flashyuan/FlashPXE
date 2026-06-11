# Samba 配置占位

SynaBoot Phase 1 默认不启用 Samba，也不会开放 `445/139/137/138`。

如后续需要 Samba，必须先完成：

- 重新由 `network_safety_agent` 审查
- 运行 `scripts/preflight/check-network-safety.sh`
- 确认只读共享 `data/images`
- 禁止匿名写入
- 禁止 `network_mode: host`
- 禁止 `privileged: true`

本目录当前只用于保留配置位置，不会被 Docker Compose 自动加载。
