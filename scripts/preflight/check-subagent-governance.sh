#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

info() {
  printf 'INFO: %s\n' "$1"
}

info "SynaBoot subagent governance preflight"

expected_agents=(
  "research-agent.toml:research_agent"
  "project-decision-agent.toml:project_decision_agent"
  "network-safety-agent.toml:network_safety_agent"
  "architecture-agent.toml:architecture_agent"
  "boot-entry-agent.toml:boot_entry_agent"
  "storage-agent.toml:storage_agent"
  "image-factory-agent.toml:image_factory_agent"
  "webui-agent.toml:webui_agent"
  "tutorial-docs-agent.toml:tutorial_docs_agent"
  "security-audit-agent.toml:security_audit_agent"
  "git-audit-agent.toml:git_audit_agent"
)

actual_count="$(find .codex/agents -maxdepth 1 -type f -name '*.toml' | wc -l | tr -d ' ')"
if [[ "$actual_count" != "${#expected_agents[@]}" ]]; then
  find .codex/agents -maxdepth 1 -type f -name '*.toml' -printf '%f\n' | sort >&2
  fail "subagent 角色文件数量必须为 ${#expected_agents[@]}，当前为 ${actual_count}"
fi

for entry in "${expected_agents[@]}"; do
  file="${entry%%:*}"
  name="${entry#*:}"
  path=".codex/agents/${file}"
  [[ -f "$path" ]] || fail "缺少 subagent 角色文件: ${path}"
  if ! grep -Eq "^name[[:space:]]*=[[:space:]]*\"${name}\"[[:space:]]*$" "$path"; then
    fail "${path} 的 name 字段必须为 ${name}"
  fi
done

required_plan_markers=(
  "### 23.0 Subagent 调用成本与会话治理"
  "11 个 subagents 是**角色池**"
  "每个 milestone 开始前必须执行“固定会话池启动协议”"
  "工具层返回 \`agent not found\` 时"
  "固定会话池建立后，本 milestone 只向登记会话发送任务"
  "同一 milestone 内，同一角色优先复用同一个会话"
  "主控必须维护当前 milestone 的会话登记"
  "优先 \`send_input\` 回传给已有会话"
  "或 \`completed\` 只代表该次输入完成"
  "同一个 agent_id"
  "禁止把 \`AGENTS.md\` 或旧计划中的“spawn/invoke reviewer”理解为无条件"
  "禁止在已有固定会话池可用时，为同一职责另开新窗口"
  "长期协作台账见 \`docs/SUBAGENT_SESSION_POOL.md\`"
  "协作统计与压缩恢复快照”是恢复"
  "岗位是谁、做过什么"
  "\`operation_log\`"
  "\`reusable_conclusion\`"
  "\`next_reuse_rule\`"
  "未登记在台账中的"
  "唯一长期"
  "聊天摘要只能用于定位"
  "completed=null"
  "被登记为 APPROVED"
  "### 23.4 Subagent 超量调用复盘"
  "能由脚本验证的事实 → 主控先跑脚本，再把结果发给已有 agent"
  "需要语义判断 → 复用对应 agent；无可复用会话才新建一次"
  "2026-06-16 SMB/CIFS livefs 事故修正规则"
)

for marker in "${required_plan_markers[@]}"; do
  if ! grep -Fq "$marker" PLAN.md; then
    fail "PLAN.md 缺少 subagent 治理标记: ${marker}"
  fi
done

required_pool_markers=(
  "## 0. 长期记忆字段要求"
  "### 0.0 协作统计表契约"
  "恢复 subagent 状态的主表"
  "每一行必须能回答 4 个问题"
  "它做过什么"
  "它现在推进到哪里"
  "下次怎么复用"
  "统计表更新规则"
  "## 3. 角色岗位总表"
  "## 4. 当前会话登记表"
  "## 5. 操作流水表"
  "## 6. 协作统计与压缩恢复快照"
  "\`operation_log\`"
  "\`latest_topic\`"
  "\`progress\`"
  "\`reusable_conclusion\`"
  "\`next_reuse_rule\`"
  "### 0.1 压缩恢复防幻觉规则"
  "唯一长期记忆锚点"
  "聊天摘要只能作为定位线索"
  "未确认信息"
  "禁止凭压缩摘要声称某个 subagent 已经批准"
  "流水记录数"
  "后续复用规则"
  "## 7. 结论与进度表"
  "## 8. 上下文压缩交接规则"
  "agent not found"
  "spawn_failed"
  "2026-06-16 security_audit_agent 重复创建事故"
  "completed_not_pool"
  "不代表废弃会话"
)

for marker in "${required_pool_markers[@]}"; do
  if ! grep -Fq "$marker" docs/SUBAGENT_SESSION_POOL.md; then
    fail "docs/SUBAGENT_SESSION_POOL.md 缺少长期协作台账标记: ${marker}"
  fi
done

required_agents_markers=(
  "invoke \`network_safety_agent\`"
  "invoke \`network_safety_agent\` and \`security_audit_agent\`"
  "first read \`docs/SUBAGENT_SESSION_POOL.md\`"
  "reuse the registered role session"
  "not create a new same-role subagent merely because"
  "because a BLOCKED finding was fixed"
  "send the fix back to the same reviewer"
)

for marker in "${required_agents_markers[@]}"; do
  if ! grep -Fq "$marker" AGENTS.md; then
    fail "AGENTS.md 缺少 subagent 复用标记: ${marker}"
  fi
done

if grep -Fq "spawn both network_safety_agent and security_audit_agent" AGENTS.md; then
  fail "AGENTS.md 仍包含会误导重复创建审计 agent 的旧 spawn both 文案"
fi

info "subagent_role_files=${actual_count}"
info "subagent_role_pool=11"
info "subagent_session_governance=present"
info "APPROVED: subagent 角色池与调用治理规则有效"
