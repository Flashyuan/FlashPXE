const titles = {
  dashboard: ["Dashboard", "Phase 2 零侵入 HTTP/iPXE Boot 控制台"],
  images: ["镜像仓库", "从 data/images 扫描得到的本地镜像元数据"],
  capabilities: ["版本能力", "免费版核心能力与未来商业候选边界"],
  autoinstall: ["自动安装", "安全管理自动安装脚本草稿和变量预览"],
  menu: ["菜单预览", "当前生成的 iPXE HTTP Boot 菜单"],
  hotpe: ["HotPE 指南", "通过 HotPE 访问 Windows 镜像仓库"],
  "boot-entry": ["启动入口", "Phase 3.4 只读启动入口与本地事实门禁"],
  jobs: ["构建任务", "只生成模板与任务目录，不执行破坏性操作"],
  safety: ["网络安全", "已批准范围：仅 HTTP 18080/tcp"],
};

let images = [];
let jobs = [];
let autoinstallProfiles = [];
let autoinstallBindingPlan = {};
let capabilities = {};
let safety = {};
let deployment = {};
let bootEntry = {};

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} ${response.status}`);
  return response.json();
}

async function refresh() {
  const [imageData, jobData, profileData, bindingPlanData, capabilityData, safetyData, deploymentData, bootEntryData, menuText] = await Promise.all([
    fetchJson("/api/images"),
    fetchJson("/api/jobs"),
    fetchJson("/api/autoinstall-profiles"),
    fetchJson("/api/autoinstall-binding-plan"),
    fetchJson("/api/capabilities"),
    fetchJson("/api/network-safety"),
    fetchJson("/api/deployment-status"),
    fetchJson("/api/boot-entry"),
    fetch("/api/menu", { cache: "no-store" }).then((response) => response.text()),
  ]);
  images = imageData.images || [];
  jobs = jobData.jobs || [];
  autoinstallProfiles = profileData.profiles || [];
  autoinstallBindingPlan = bindingPlanData || {};
  capabilities = capabilityData || {};
  safety = safetyData || {};
  deployment = deploymentData || {};
  bootEntry = bootEntryData || {};
  document.querySelector("#menu-preview").textContent = menuText;
  applyAdminState();
  renderDashboard();
  renderRuntimeUrls();
  renderImages();
  renderCapabilities();
  renderAutoinstallProfiles();
  renderAutoinstallBindingPlan();
  renderJobs();
  renderBootEntry();
  renderDeployment();
  renderSafety();
}

function setView(name) {
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === name));
  document.querySelectorAll("nav button").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  document.querySelector("#page-title").textContent = titles[name][0];
  document.querySelector("#page-subtitle").textContent = titles[name][1];
}

function formatSize(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

function renderDashboard() {
  const categories = ["pe", "windows", "linux", "tools", "custom"];
  document.querySelector("#ready-count").textContent = images.filter(
    (image) => image.scan_status === "present" && image.boot_readiness === "ready",
  ).length;
  const summary = document.querySelector("#category-summary");
  summary.innerHTML = categories
    .map((category) => {
      const count = images.filter((image) => image.category === category).length;
      return `<article><span>${category}</span><strong>${count}</strong></article>`;
    })
    .join("");
}

function renderRuntimeUrls() {
  const webUrl = safety.web_url || "/";
  const menuUrl = safety.menu_url || "/boot/menu.ipxe";
  const imagesUrl = safety.images_url || "/images/";
  document.querySelector("#web-url").textContent = webUrl;
  document.querySelector("#menu-url").textContent = menuUrl;
  document.querySelector("#images-url").textContent = imagesUrl;
  document.querySelector("#chain-command").textContent = `chain ${menuUrl}`;
  document.querySelector("#windows-images-url").textContent = `${imagesUrl.replace(/\/$/, "")}/windows/`;
}

function renderImages() {
  const query = document.querySelector("#image-search").value.trim().toLowerCase();
  const category = document.querySelector("#category-filter").value;
  const rows = images.filter((image) => {
    const text = `${image.display_name || image.name} ${image.relative_path || image.rel_path}`.toLowerCase();
    return (!category || image.category === category) && (!query || text.includes(query));
  });
  document.querySelector("#images-table").innerHTML =
    rows
      .map(
        (image) => `<tr>
          <td><strong>${escapeHtml(image.display_name || image.name)}</strong><br><span class="badge">${escapeHtml(image.kind)}</span></td>
          <td>${escapeHtml(image.category)}</td>
          <td>${escapeHtml(image.kind)}</td>
          <td>${formatSize(image.size_bytes)}</td>
          <td>
            <span class="badge ${statusClass(image.scan_status)}">${escapeHtml(image.scan_status || "")}</span>
            <span class="badge ${statusClass(image.boot_readiness)}">${escapeHtml(image.boot_readiness || "")}</span>
          </td>
          <td>
            <span class="badge ${statusClass(image.preparation_status)}">${escapeHtml(image.preparation_status || "")}</span>
            <br><small>${escapeHtml(image.readiness_detail || "")}</small>
            <br><small>${escapeHtml(image.next_action || "")}</small>
          </td>
          <td>${escapeHtml(image.boot_method)}</td>
          <td>
            <a href="/images/${encodeURI(image.relative_path || image.rel_path)}">${escapeHtml(image.relative_path || image.rel_path)}</a>
            <br><small>${escapeHtml(image.sha256 || "")}</small>
            <br><small>${image.sha256_cached ? "SHA256 已复用缓存" : "SHA256 已计算"}</small>
          </td>
          <td>
            <span class="badge">${image.menu_enabled ? "启用" : "禁用"}</span>
            <button class="small detail-open" data-id="${escapeHtml(image.id)}">详情</button>
            <button class="small menu-toggle admin-action" data-id="${escapeHtml(image.id)}" data-enabled="${image.menu_enabled ? "1" : "0"}">
              ${image.menu_enabled ? "禁用" : "启用"}
            </button>
          </td>
        </tr>`,
      )
      .join("") || `<tr><td colspan="9">未发现镜像。请将文件放入 data/images 后扫描。</td></tr>`;
  document.querySelectorAll(".detail-open").forEach((button) =>
    button.addEventListener("click", async () => {
      try {
        const image = await fetchJson(`/api/images/${encodeURIComponent(button.dataset.id)}`);
        renderImageDetail(image);
      } catch (error) {
        window.alert(`读取详情失败：${error.message}`);
      }
    }),
  );
  document.querySelectorAll(".menu-toggle").forEach((button) =>
    button.addEventListener("click", async () => {
      if (!adminConfigured()) {
        window.alert("未配置 SYNABOOT_ADMIN_TOKEN，写操作不可用。");
        return;
      }
      const token = window.prompt("请输入管理员 token。");
      if (!token) return;
      const action = button.dataset.enabled === "1" ? "disable" : "enable";
      try {
        await postAdmin(`/api/images/${encodeURIComponent(button.dataset.id)}/${action}`, {}, token);
        await refresh();
      } catch (error) {
        window.alert(`更新失败：${error.message}`);
      }
    }),
  );
  applyAdminState();
}

function renderImageDetail(image) {
  const prepareKind = prepareKindForImage(image);
  const fields = [
    ["显示名", image.display_name || image.name],
    ["版本", image.version || ""],
    ["架构", image.architecture || ""],
    ["描述", image.description || ""],
    ["相对路径", image.relative_path || image.rel_path],
    ["大小", formatSize(image.size_bytes)],
    ["SHA256", image.sha256 || ""],
    ["mtime_ns", image.mtime_ns || ""],
    ["扫描状态", image.scan_status || ""],
    ["启动就绪", image.boot_readiness || ""],
    ["来源角色", image.source_role || ""],
    ["准备状态", image.preparation_status || ""],
    ["缺失依赖", (image.missing_artifacts || []).join("，")],
    ["准备说明", image.readiness_detail || ""],
    ["下一步", image.next_action || ""],
    ["启动方式", image.boot_method || ""],
    ["菜单启用", image.menu_enabled ? "是" : "否"],
    ["首次缺失时间", image.missing_since || ""],
  ];
  document.querySelector("#image-detail").innerHTML =
    fields
    .map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></article>`)
      .join("") +
    `<article class="metadata-editor">
      <span>编辑元数据</span>
      <label>显示名<input id="meta-display-name" value="${escapeAttr(image.display_name || image.name)}" /></label>
      <label>版本<input id="meta-version" value="${escapeAttr(image.version || "")}" /></label>
      <label>架构<input id="meta-architecture" value="${escapeAttr(image.architecture || "")}" /></label>
      <label>描述<textarea id="meta-description" rows="4">${escapeHtml(image.description || "")}</textarea></label>
      <button id="metadata-save-button" class="primary admin-action" data-id="${escapeAttr(image.id)}">保存元数据</button>
    </article>` +
    (prepareKind
      ? `<article>
          <span>准备任务</span>
          <strong>${escapeHtml(image.next_action || "创建 ISO 准备任务。")}</strong>
          <button id="prepare-job-button" class="primary admin-action" data-id="${escapeAttr(image.id)}" data-kind="${escapeAttr(prepareKind)}">创建准备任务</button>
        </article>`
      : "");
  document.querySelector("#metadata-save-button").addEventListener("click", async (event) => {
    if (!adminConfigured()) {
      window.alert("未配置 SYNABOOT_ADMIN_TOKEN，元数据保存不可用。");
      return;
    }
    const token = window.prompt("请输入管理员 token。");
    if (!token) return;
    const imageId = event.currentTarget.dataset.id;
    const payload = {
      display_name: document.querySelector("#meta-display-name").value,
      version: document.querySelector("#meta-version").value,
      architecture: document.querySelector("#meta-architecture").value,
      description: document.querySelector("#meta-description").value,
    };
    try {
      const updated = await postAdmin(`/api/images/${encodeURIComponent(imageId)}/metadata`, payload, token);
      await refresh();
      renderImageDetail(updated);
    } catch (error) {
      window.alert(`保存失败：${error.message}`);
    }
  });
  const prepareButton = document.querySelector("#prepare-job-button");
  if (prepareButton) {
    prepareButton.addEventListener("click", async (event) => {
      if (!adminConfigured()) {
        window.alert("未配置 SYNABOOT_ADMIN_TOKEN，任务创建不可用。");
        return;
      }
      const token = window.prompt("请输入管理员 token。");
      if (!token) return;
      const payload = {
        kind: event.currentTarget.dataset.kind,
        source_image_id: event.currentTarget.dataset.id,
      };
      try {
        const job = await postAdmin("/api/jobs", payload, token);
        await refresh();
        setView("jobs");
        await renderJobDetail(job.id);
      } catch (error) {
        window.alert(`创建准备任务失败：${error.message}`);
      }
    });
  }
  applyAdminState();
}

function prepareKindForImage(image) {
  if (image.preparation_status !== "needs_extraction") return "";
  if (image.category === "pe" && image.kind === "iso") return "hotpe-iso-prepare";
  if (image.category === "linux" && image.kind === "iso") return "ubuntu-iso-extract-kernel-initrd";
  return "";
}

function statusClass(value) {
  if (["ready", "present", "prepared"].includes(value)) return "ok";
  if ([
    "missing",
    "incomplete",
    "needs_hotpe",
    "needs_extraction",
    "waiting_for_source",
    "uses_hotpe",
    "draft_review_required",
    "planning_only_disabled",
  ].includes(value)) return "warn";
  return "";
}

function renderCapabilities() {
  const summary = document.querySelector("#capability-summary");
  if (!summary) return;
  const freeLimits = capabilities.free_limits || {};
  const summaryItems = [
    ["版本", capabilities.edition || "free"],
    ["发布线", capabilities.release_channel || "free"],
    ["GitHub 发布", capabilities.github_public_release ? "免费版公开线" : "未声明"],
    ["商业代码", capabilities.commercial_code_included ? "包含" : "不包含"],
    ["在线激活", capabilities.online_activation_required ? "需要" : "不需要"],
    ["运行策略", capabilities.runtime_enforcement || ""],
  ];
  summary.innerHTML = summaryItems
    .map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></article>`)
    .join("");
  renderList("#capability-free-list", capabilities.core_free_guarantees || []);
  renderList(
    "#capability-limits-list",
    Object.entries(freeLimits).map(([key, value]) => `${key}: ${value ? "limited" : "unlimited"}`),
  );
  renderList("#capability-paid-list", capabilities.paid_feature_placeholders || []);
  renderList("#capability-blocked-list", capabilities.blocked_from_public_release || []);
  const note = document.querySelector("#capability-note");
  note.textContent = capabilities.owner_local_full_feature_note || "";
  renderEditionCatalog();
}

function renderList(selector, items) {
  const target = document.querySelector(selector);
  if (!target) return;
  target.innerHTML = (items || []).map((item) => `<li>${escapeHtml(String(item))}</li>`).join("") || "<li>无</li>";
}

function renderEditionCatalog() {
  const target = document.querySelector("#edition-catalog");
  if (!target) return;
  const catalog = capabilities.edition_catalog || {};
  target.innerHTML = (catalog.tiers || [])
    .map((tier) => {
      const features = tier.included || tier.candidate_features || [];
      return `<article>
        <h3>${escapeHtml(tier.name || tier.id || "")}</h3>
        <p><span class="badge">${escapeHtml(tier.billing || "")}</span></p>
        <p>${escapeHtml(tier.summary || "")}</p>
        <ul>${features.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>
      </article>`;
    })
    .join("") || "<p>暂无版本边界。</p>";
  renderList("#edition-guardrails", catalog.guardrails || []);
}

function renderAutoinstallProfiles() {
  const count = document.querySelector("#autoinstall-count");
  if (count) count.textContent = autoinstallProfiles.length;
  const list = document.querySelector("#autoinstall-list");
  if (!list) return;
  list.innerHTML =
    autoinstallProfiles
      .map(
        (profile) => `<article>
          <h3>${escapeHtml(profile.name)}</h3>
          <p>
            <span class="badge">${escapeHtml(profile.os_family)}</span>
            <span class="badge">${escapeHtml(profile.template_kind)}</span>
            <span class="badge ${statusClass(profile.status)}">${escapeHtml(profile.status)}</span>
          </p>
          <p>${escapeHtml(profile.note || "")}</p>
          <p><small>变量白名单：${escapeHtml((profile.variables || []).join("，") || "无")}</small></p>
          <p><small>破坏性策略：${escapeHtml(profile.destructive_policy || "")}</small></p>
          <pre>${escapeHtml(profile.template_preview || "")}</pre>
        </article>`,
      )
      .join("") || "<p>暂无自动安装草稿。可先创建 Ubuntu 或 Windows 安全模板。</p>";
}

function renderAutoinstallBindingPlan() {
  const target = document.querySelector("#autoinstall-binding-plan");
  if (!target) return;
  const candidates = autoinstallBindingPlan.candidates || [];
  const summary = [
    ["绑定状态", autoinstallBindingPlan.runtime_binding_enabled ? "已启用" : "规划中"],
    ["菜单接入", autoinstallBindingPlan.menu_integration_enabled ? "已启用" : "未接入"],
    ["候选 ISO", autoinstallBindingPlan.candidate_images_total || 0],
    ["草稿数量", autoinstallBindingPlan.profiles_total || 0],
  ];
  const candidateHtml = candidates
    .map(
      (candidate) => {
        const profileItems = (candidate.compatible_profiles || [])
          .map(
            (profile) => `<li>
              <strong>${escapeHtml(profile.profile_name || profile.profile_id || "")}</strong>
              <small>${escapeHtml(profile.template_kind || "")} / ${escapeHtml(profile.status || "")}</small>
            </li>`,
          )
          .join("");
        return `<article>
          <h3>${escapeHtml(candidate.image_name || candidate.relative_path)}</h3>
          <p>
            <span class="badge">${escapeHtml(candidate.os_family || "")}</span>
            <span class="badge ${statusClass(candidate.status)}">${escapeHtml(candidate.planning_state || candidate.status || "")}</span>
            <span class="badge">${escapeHtml(candidate.required_edition || "")}</span>
            <span class="badge">${escapeHtml(candidate.preparation_status || "")}</span>
          </p>
          <p><small>${escapeHtml(candidate.relative_path || "")}</small></p>
          <p>兼容草稿：${escapeHtml(String(candidate.compatible_profile_count || 0))}</p>
          <ul>${profileItems || "<li>暂无同系统类型草稿。</li>"}</ul>
          <p>${escapeHtml(candidate.disabled_reason_text || "")}</p>
          <p>${escapeHtml(candidate.next_action || "")}</p>
        </article>`;
      },
    )
    .join("");
  target.innerHTML = `<div class="summary-grid">
      ${summary
        .map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></article>`)
        .join("")}
    </div>
    <p>${escapeHtml(autoinstallBindingPlan.reason || "")}</p>
    <div class="split">
      <div>
        <h3>免费版当前范围</h3>
        <ul>${(autoinstallBindingPlan.free_scope || []).map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>
      </div>
      <div>
        <h3>后续商业候选</h3>
        <ul>${(autoinstallBindingPlan.commercial_candidate_scope || []).map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>
      </div>
    </div>
    <h3>候选 ISO</h3>
    <div class="cards">${candidateHtml || "<p>暂无可规划绑定的 Windows/Linux ISO。请先扫描镜像仓库。</p>"}</div>`;
}

function renderJobs() {
  document.querySelector("#jobs-list").innerHTML =
    jobs
      .map(
        (job) => {
          const packageInfo = job.package || {};
          return `<article>
          <h3>${escapeHtml(job.title)}</h3>
          <p><span class="badge">${escapeHtml(job.kind)}</span> <span class="badge">${escapeHtml(job.status)}</span></p>
          <p>${escapeHtml(job.note)}</p>
          <p class="mono">${escapeHtml(job.output_dir)}</p>
          <p><span class="badge ${statusClass(packageInfo.status)}">${escapeHtml(packageInfo.status || "no_package")}</span></p>
          <button class="small job-detail-open" data-id="${escapeAttr(job.id)}">详情</button>
          ${job.status === "draft" ? `<button class="small job-submit admin-action" data-id="${escapeAttr(job.id)}">提交待执行</button>` : ""}
          ${["draft", "pending"].includes(job.status) ? `<button class="small job-cancel admin-action" data-id="${escapeAttr(job.id)}">取消</button>` : ""}
        </article>`;
        },
      )
      .join("") || "<p>暂无任务。</p>";
  document.querySelectorAll(".job-detail-open").forEach((button) =>
    button.addEventListener("click", async () => {
      try {
        await renderJobDetail(button.dataset.id);
      } catch (error) {
        window.alert(`读取任务失败：${error.message}`);
      }
    }),
  );
  document.querySelectorAll(".job-submit, .job-cancel").forEach((button) =>
    button.addEventListener("click", async () => {
      if (!adminConfigured()) {
        window.alert("未配置 SYNABOOT_ADMIN_TOKEN，任务状态变更不可用。");
        return;
      }
      const token = window.prompt("请输入管理员 token。");
      if (!token) return;
      const action = button.classList.contains("job-submit") ? "submit" : "cancel";
      try {
        const job = await postAdmin(`/api/jobs/${encodeURIComponent(button.dataset.id)}/${action}`, {}, token);
        await refresh();
        await renderJobDetail(job.id);
      } catch (error) {
        window.alert(`任务更新失败：${error.message}`);
      }
    }),
  );
  applyAdminState();
}

async function renderJobDetail(jobId) {
  const [job, eventsData] = await Promise.all([
    fetchJson(`/api/jobs/${encodeURIComponent(jobId)}`),
    fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/events`),
  ]);
  const events = eventsData.events || [];
  const packageInfo = job.package || {};
  const source = packageInfo.source || {};
  const toolRows = (packageInfo.tool_status || [])
    .map((tool) => `${tool.name}: ${tool.available ? "available" : "missing"}`)
    .join("\n");
  const safetyRows = Object.entries(packageInfo.safety || {})
    .map(([key, value]) => `${key}: ${value}`)
    .join("\n");
  document.querySelector("#job-detail").innerHTML = `
    <div class="detail-grid">
      <article><span>任务 ID</span><strong>${escapeHtml(job.id)}</strong></article>
      <article><span>类型</span><strong>${escapeHtml(job.kind)}</strong></article>
      <article><span>状态</span><strong>${escapeHtml(job.status)}</strong></article>
      <article><span>输出目录</span><strong>${escapeHtml(job.output_dir)}</strong></article>
      <article><span>说明</span><strong>${escapeHtml(job.note)}</strong></article>
      <article><span>任务包</span><strong>${escapeHtml(packageInfo.status || "")}</strong></article>
      <article><span>源 ISO</span><strong>${escapeHtml(source.relative_path || "无")}</strong></article>
      <article><span>Manifest</span><strong>${escapeHtml(packageInfo.manifest_path || "无")}</strong></article>
      <article><span>准备脚本</span><strong>${escapeHtml(packageInfo.prepare_script || "无")}</strong></article>
    </div>
    <h3>目标输出</h3>
    <pre>${escapeHtml((packageInfo.required_outputs || []).join("\n") || "无")}</pre>
    <h3>本机工具探测</h3>
    <pre>${escapeHtml(toolRows || "无")}</pre>
    <h3>安全边界</h3>
    <pre>${escapeHtml(safetyRows || "无")}</pre>
    <h3>任务包文档</h3>
    <pre>${escapeHtml((packageInfo.readme_files || []).join("\n") || "无")}</pre>
    <h3>事件日志</h3>
    <pre>${escapeHtml(events.map((event) => JSON.stringify(event)).join("\n") || "暂无事件。")}</pre>
  `;
}

function renderBootEntry() {
  const documentation = bootEntry.documentation || {};
  const phaseGate = bootEntry.phase3_3_gate || {};
  const pxeReadiness = bootEntry.pxe_ipv4_readiness || {};
  const pxeLabPlan = bootEntry.pxe_lab_boot_metadata_plan || {};
  const disabledSkeleton = bootEntry.isolated_lab_boot_services_disabled_skeleton || {};
  const evidencePackage = bootEntry.isolated_lab_evidence_package || {};
  const configIntentPackage = bootEntry.isolated_lab_config_intent_package || {};
  const sourceSkeletonPackage = bootEntry.isolated_lab_source_skeleton_package || {};
  const manualDeclarationGate = bootEntry.isolated_lab_manual_declaration_gate || {};
  const runtimeAuthorizationPlan = bootEntry.isolated_lab_runtime_authorization_plan || {};
  const isolatedPlan = bootEntry.isolated_validation_plan || {};
  const docItems = [
    documentation.local_verification_template,
    documentation.proxydhcp_feasibility,
    documentation.proxydhcp_packet_review,
    documentation.tftp_loader_scope,
    documentation.phase3_rollback_checklist,
    documentation.phase3_review_templates,
    documentation.integration_guide,
  ].filter(Boolean);
  const summary = [
    ["模型阶段", bootEntry.phase || ""],
    ["展示阶段", bootEntry.display_phase || ""],
    ["展示状态", bootEntry.display_status || ""],
    ["模式", bootEntry.mode || ""],
    ["状态", bootEntry.status || ""],
    ["Phase 3.3", bootEntry.phase3_3_gate?.status || ""],
    ["启用", bootEntry.enabled ? "是" : "否"],
    ["菜单 URL", bootEntry.server?.menu_url || ""],
    ["HTTP Loader", bootEntry.server?.http_boot_loader_url || ""],
  ];
  document.querySelector("#boot-entry-summary").innerHTML = summary
    .map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></article>`)
    .join("");
  document.querySelector("#boot-entry-docs").innerHTML = docItems
    .map(
      (doc) => `<article>
        <h3>${escapeHtml(doc.label || "")}</h3>
        <p class="mono">${escapeHtml(doc.path || "")}</p>
        <p>${escapeHtml(doc.purpose || "")}</p>
      </article>`,
    )
    .join("");
  const gateItems = [
    ["已确认事实", phaseGate.confirmed_evidence || []],
    ["仍缺事实", phaseGate.missing_local_facts || []],
    ["解除门禁前置条件", phaseGate.blocked_until || []],
    ["禁止推断", phaseGate.do_not_infer || []],
  ];
  document.querySelector("#boot-entry-gate").innerHTML = gateItems
    .map(
      ([label, items]) => `<article>
        <h3>${escapeHtml(label)}</h3>
        <p>${escapeHtml((items || []).join("；") || "无")}</p>
      </article>`,
    )
    .join("");
  const isolatedPlanItems = [
    ["计划状态", [isolatedPlan.status || ""]],
    ["运行状态", [isolatedPlan.runtime_enabled ? "已启用" : "未启用"]],
    ["生产 LAN", [isolatedPlan.production_lan_allowed ? "允许" : "禁止"]],
    ["目标链路", isolatedPlan.target_chain || []],
    ["环境要求", isolatedPlan.environment_requirements || []],
    ["允许准备", isolatedPlan.allowed_preparation || []],
    ["禁止动作", isolatedPlan.forbidden_actions || []],
    ["实验前证据", isolatedPlan.required_evidence_before_lab || []],
    ["未来实验成功标准", isolatedPlan.success_criteria_for_future_lab || []],
    ["退出条件", isolatedPlan.exit_conditions || []],
  ];
  document.querySelector("#boot-entry-isolated-plan").innerHTML = isolatedPlanItems
    .map(
      ([label, items]) => `<article>
        <h3>${escapeHtml(label)}</h3>
        <p>${escapeHtml((items || []).filter(Boolean).join("；") || "无")}</p>
      </article>`,
    )
    .join("");
  const loaderRows = (pxeReadiness.preferred_loaders || [])
    .map((loader) => `${loader.filename}: ${loader.usable ? "usable" : loader.status}`)
    .join("；");
  const readyEntries = pxeReadiness.image_menu?.ready_entries || [];
  const pxeReadinessItems = [
    ["状态", [pxeReadiness.status || ""]],
    ["运行状态", [pxeReadiness.runtime_enabled ? "已启用" : "未启用"]],
    ["生产 LAN 测试", [pxeReadiness.production_lan_testing_allowed ? "允许" : "禁止"]],
    ["启动实测", [pxeReadiness.boot_tested ? "已实测" : "未实测"]],
    ["菜单", [`${pxeReadiness.menu?.present ? "present" : "missing"} ${pxeReadiness.menu?.url || ""}`]],
    ["UEFI Loader", [loaderRows || "无可用 loader"]],
    ["镜像菜单", [`ready=${pxeReadiness.image_menu?.ready_menu_entry_count || 0}；source_iso=${pxeReadiness.image_menu?.source_iso_count || 0}；windows_hotpe=${pxeReadiness.image_menu?.windows_hotpe_candidate_count || 0}`]],
    ["Ready 条目", readyEntries.map((entry) => `${entry.name} (${entry.boot_method})`)],
    ["阻塞项", pxeReadiness.blocking_items || []],
    ["下一步", pxeReadiness.next_actions || []],
  ];
  document.querySelector("#boot-entry-pxe-readiness").innerHTML = pxeReadinessItems
    .map(
      ([label, items]) => `<article>
        <h3>${escapeHtml(label)}</h3>
        <p>${escapeHtml((items || []).filter(Boolean).join("；") || "无")}</p>
      </article>`,
    )
    .join("");
  const metadata = pxeLabPlan.candidate_boot_metadata || {};
  const labLoaderRows = (pxeLabPlan.loader_evidence || [])
    .map((loader) => `${loader.filename}: ${loader.reviewed_for_lab ? "reviewed" : "not reviewed"} ${loader.sha256 || ""}`)
    .join("；");
  const pxeLabPlanItems = [
    ["状态", [pxeLabPlan.status || ""]],
    ["运行状态", [pxeLabPlan.runtime_enabled ? "已启用" : "未启用"]],
    ["生产 LAN", [pxeLabPlan.production_lan_allowed ? "允许" : "禁止"]],
    ["候选 bootfile", [`${metadata.bootfile || "无"}${metadata.fallback_bootfile ? `；fallback=${metadata.fallback_bootfile}` : ""}`]],
    ["TFTP root", [metadata.tftp_root || ""]],
    ["菜单 URL", [metadata.menu_url || ""]],
    ["允许 TFTP 文件", metadata.allowed_tftp_files || []],
    ["禁止 TFTP 文件", metadata.forbidden_tftp_files || []],
    ["Loader 证据", [labLoaderRows || "无"]],
    ["ProxyDHCP 元数据边界", pxeLabPlan.proxy_dhcp_metadata_fields || []],
    ["禁止 DHCP 字段", pxeLabPlan.forbidden_dhcp_fields || []],
    ["抓包证据", pxeLabPlan.required_packet_evidence || []],
    ["回滚检查", pxeLabPlan.rollback_checks || []],
    ["阻塞项", pxeLabPlan.blocking_items || []],
    ["下一门禁", pxeLabPlan.next_gate || []],
  ];
  document.querySelector("#boot-entry-pxe-lab-plan").innerHTML = pxeLabPlanItems
    .map(
      ([label, items]) => `<article>
        <h3>${escapeHtml(label)}</h3>
        <p>${escapeHtml((items || []).filter(Boolean).join("；") || "无")}</p>
      </article>`,
    )
    .join("");
  const skeletonServices = (disabledSkeleton.service_profiles || [])
    .map((service) => `${service.id}: ${service.service_enabled ? "active" : "disabled"} / ${service.allowed_scope || service.url || ""}`)
    .join("；");
  const skeletonReferences = (disabledSkeleton.reference_targets || [])
    .map((target) => `${target.id}: ${target.url || ""}`)
    .join("；");
  const skeletonLoaders = (disabledSkeleton.bootfile_candidates || [])
    .map((loader) => `${loader.filename}: ${loader.reviewed_for_lab ? "reviewed" : "not reviewed"} ${loader.sha256 || ""}`)
    .join("；");
  const skeletonGateRows = Object.entries(disabledSkeleton.gates || {})
    .map(([key, value]) => `${key}: ${value}`);
  const disabledSkeletonItems = [
    ["状态", [disabledSkeleton.status || ""]],
    ["模式", [disabledSkeleton.mode || ""]],
    ["范围", [disabledSkeleton.environment_scope || ""]],
    ["运行状态", [disabledSkeleton.runtime_enabled ? "已运行" : "未运行"]],
    ["服务启动", [disabledSkeleton.service_start_allowed ? "允许" : "禁止"]],
    ["配置生成", [disabledSkeleton.config_generation_allowed ? "允许" : "禁止"]],
    ["生产 LAN", [disabledSkeleton.production_lan_allowed ? "允许" : "禁止"]],
    ["目标链路模型", disabledSkeleton.target_chain_model || []],
    ["服务候选", [skeletonServices || "无"]],
    ["引用目标", [skeletonReferences || "无"]],
    ["候选 Loader", [skeletonLoaders || "无"]],
    ["Loader 白名单", disabledSkeleton.tftp_loader_allowlist || []],
    ["禁止传输范围", disabledSkeleton.forbidden_transfer_scope || []],
    ["HTTP 菜单目标", [disabledSkeleton.http_menu_target?.url || ""]],
    ["客户端证据模板", disabledSkeleton.client_evidence_template || []],
    ["失败模式", disabledSkeleton.failure_modes || []],
    ["回滚计划", disabledSkeleton.rollback_plan || []],
    ["门禁", skeletonGateRows],
    ["阻断动作", disabledSkeleton.blocked_actions || []],
    ["下一门禁", disabledSkeleton.next_gate || []],
  ];
  document.querySelector("#boot-entry-disabled-skeleton").innerHTML = disabledSkeletonItems
    .map(
      ([label, items]) => `<article>
        <h3>${escapeHtml(label)}</h3>
        <p>${escapeHtml((items || []).filter(Boolean).join("；") || "无")}</p>
      </article>`,
    )
    .join("");
  const evidenceCheckRows = (evidencePackage.evidence_checks || [])
    .map((item) => `${item.id}: ${item.status}${item.summary ? ` / ${item.summary}` : ""}`);
  const udpEvidenceRows = (evidencePackage.udp_port_evidence || [])
    .map((item) => `${item.protocol}/${item.port}: ${item.observed_in_api_namespace ? "observed" : "not observed"}`);
  const approvalRows = Object.entries(evidencePackage.authorization_request?.approval_state || {})
    .map(([key, value]) => `${key}: ${value}`);
  const reviewedLoaderRows = (evidencePackage.boot_readiness_evidence?.reviewed_loaders || [])
    .map((loader) => `${loader.filename}: ${loader.sha256 || ""}`);
  const readyImageRows = (evidencePackage.boot_readiness_evidence?.ready_image_entries || [])
    .map((entry) => `${entry.name} (${entry.boot_method})`);
  const evidencePackageItems = [
    ["状态", [evidencePackage.status || ""]],
    ["模式", [evidencePackage.mode || ""]],
    ["请求范围", [evidencePackage.requested_scope || ""]],
    ["只读", [evidencePackage.read_only ? "是" : "否"]],
    ["执行边界", [
      `secrets=${evidencePackage.secrets_included ? "included" : "absent"}`,
      `raw_commands=${evidencePackage.raw_commands_included ? "included" : "absent"}`,
      `config_generation=${evidencePackage.config_generation_allowed ? "allowed" : "forbidden"}`,
      `service_start=${evidencePackage.service_start_allowed ? "allowed" : "forbidden"}`,
      `production_lan=${evidencePackage.production_lan_allowed ? "allowed" : "forbidden"}`,
    ]],
    ["授权请求", [evidencePackage.authorization_request?.status || ""]],
    ["审批状态", approvalRows],
    ["证据检查", evidenceCheckRows],
    ["UDP 端口证据", udpEvidenceRows],
    ["Reviewed Loader", reviewedLoaderRows],
    ["Ready 镜像", readyImageRows],
    ["人工确认清单", evidencePackage.manual_lab_declaration_required || []],
    ["客户端证据模板", evidencePackage.client_evidence_template || []],
    ["预期观测", evidencePackage.expected_observations || []],
    ["禁止输出", evidencePackage.forbidden_outputs || []],
    ["阻塞项", evidencePackage.blocking_items || []],
    ["下一门禁", evidencePackage.next_gate || []],
  ];
  document.querySelector("#boot-entry-evidence-package").innerHTML = evidencePackageItems
    .map(
      ([label, items]) => `<article>
        <h3>${escapeHtml(label)}</h3>
        <p>${escapeHtml((items || []).filter(Boolean).join("；") || "无")}</p>
      </article>`,
    )
    .join("");
  const intendedServiceRows = Object.entries(configIntentPackage.intended_services || {})
    .map(([key, value]) => `${key}: ${value}`);
  const intendedPortRows = (configIntentPackage.intended_ports || [])
    .map((item) => `${item.protocol}/${item.port}: observed=${item.observed_listening ? "yes" : "no"} desired=${item.desired_listening ? "yes" : "no"}`);
  const allowlistRows = (configIntentPackage.loader_allowlist || [])
    .map((loader) => `${loader.name}: ${loader.reviewed ? "reviewed" : "not reviewed"} ${loader.sha256 || ""}`);
  const validationRows = (configIntentPackage.client_validation_checklist || [])
    .map((item) => `${item.id}: expected=${item.expected || item.expected_url || item.expected_ready_entry_count || (item.expected_one_of || []).join(",")} observed=${item.observed || "pending"} passed=${item.passed ? "yes" : "no"}`);
  const configIntentItems = [
    ["状态", [configIntentPackage.status || ""]],
    ["模式", [configIntentPackage.mode || ""]],
    ["范围", [configIntentPackage.environment_scope || ""]],
    ["只读", [configIntentPackage.read_only ? "是" : "否"]],
    ["授权请求", [configIntentPackage.request_is_authorization ? "是" : "否"]],
    ["运行边界", [
      `runtime=${configIntentPackage.runtime_enabled ? "yes" : "no"}`,
      `config_generation=${configIntentPackage.config_generation_allowed ? "yes" : "no"}`,
      `service_start=${configIntentPackage.service_start_allowed ? "yes" : "no"}`,
      `task_consumption=${configIntentPackage.task_consumption_allowed ? "yes" : "no"}`,
      `production_lan=${configIntentPackage.production_lan_allowed ? "yes" : "no"}`,
    ]],
    ["服务意图", intendedServiceRows],
    ["端口意图", intendedPortRows],
    ["候选 Bootfile", [`${configIntentPackage.candidate_bootfile?.value || "无"} / ${configIntentPackage.candidate_bootfile?.status || ""}`]],
    ["Loader 白名单", allowlistRows],
    ["HTTP 链接目标", [configIntentPackage.http_chain_target?.menu_url || ""]],
    ["意图链路", configIntentPackage.intent_chain || []],
    ["客户端验证清单", validationRows],
    ["人工授权门禁", configIntentPackage.manual_authorization_gates || []],
    ["回滚触发", configIntentPackage.rollback_triggers || []],
    ["阻断动作", configIntentPackage.blocked_actions || []],
    ["下一门禁", configIntentPackage.next_gate || []],
  ];
  document.querySelector("#boot-entry-config-intent-package").innerHTML = configIntentItems
    .map(
      ([label, items]) => `<article>
        <h3>${escapeHtml(label)}</h3>
        <p>${escapeHtml((items || []).filter(Boolean).join("；") || "无")}</p>
      </article>`,
    )
    .join("");
  const sourceServiceRows = Object.entries(sourceSkeletonPackage.intended_services || {})
    .map(([key, value]) => `${key}: ${value.state || ""} enabled=${value.enabled ? "yes" : "no"} startable=${value.startable ? "yes" : "no"}`);
  const sourcePortRows = (sourceSkeletonPackage.intended_ports || [])
    .map((item) => `${item.protocol}/${item.port}: observed=${item.observed_listening ? "yes" : "no"} desired=${item.desired_listening ? "yes" : "no"}`);
  const sourceEmptyRows = [
    `runtime_targets=${(sourceSkeletonPackage.runtime_entrypoints || []).length}`,
    `compose_services=${(sourceSkeletonPackage.compose_services || []).length}`,
    `generated_files=${(sourceSkeletonPackage.generated_files || []).length}`,
    `opened_ports=${(sourceSkeletonPackage.opened_ports || []).length}`,
    `task_consumers=${(sourceSkeletonPackage.task_consumers || []).length}`,
    `network_listeners=${(sourceSkeletonPackage.network_listeners || []).length}`,
  ];
  const sourceProtocol = sourceSkeletonPackage.offline_protocol_model || {};
  const metadataIntent = sourceProtocol.boot_metadata_intent || {};
  const transferScope = sourceProtocol.loader_transfer_scope || {};
  const sourceAllowlistRows = (transferScope.allowlist || [])
    .map((item) => `${item.name}: reviewed=${item.reviewed ? "yes" : "no"} served=${item.served ? "yes" : "no"}`);
  const sourceFixtureRows = (sourceSkeletonPackage.client_evidence_fixture || [])
    .map((item) => `${item.id}: observed=${item.observed || "pending"} passed=${item.passed ? "yes" : "no"}`);
  const sourceItems = [
    ["状态", [sourceSkeletonPackage.status || ""]],
    ["模式", [sourceSkeletonPackage.mode || ""]],
    ["包类型", [sourceSkeletonPackage.package_kind || ""]],
    ["只读", [sourceSkeletonPackage.read_only ? "是" : "否"]],
    ["离线边界", [
      `fixture_only=${sourceSkeletonPackage.fixture_only ? "yes" : "no"}`,
      `offline_package_only=${sourceSkeletonPackage.offline_package_only ? "yes" : "no"}`,
      `runtime_available=${sourceSkeletonPackage.runtime_available ? "yes" : "no"}`,
      `production_lan=${sourceSkeletonPackage.production_lan_allowed ? "yes" : "no"}`,
    ]],
    ["服务骨架", sourceServiceRows],
    ["端口模型", sourcePortRows],
    ["空运行入口", sourceEmptyRows],
    ["Boot Metadata 模型", [
      `candidate=${metadataIntent.candidate_bootfile || "无"}`,
      `lease=${metadataIntent.assigns_lease ? "yes" : "no"}`,
      `gateway=${metadataIntent.includes_gateway ? "yes" : "no"}`,
      `dns=${metadataIntent.includes_dns ? "yes" : "no"}`,
      `subnet=${metadataIntent.includes_subnet ? "yes" : "no"}`,
    ]],
    ["Loader 离线白名单", sourceAllowlistRows],
    ["HTTP 后续目标", [sourceProtocol.http_chain_target?.menu_url || ""]],
    ["Fixture 引用", [sourceSkeletonPackage.offline_fixture_reference?.path || ""]],
    ["客户端证据 Fixture", sourceFixtureRows],
    ["授权门禁", sourceSkeletonPackage.authorization_gates || []],
    ["阻断动作", sourceSkeletonPackage.blocked_actions || []],
    ["下一门禁", sourceSkeletonPackage.next_gate || []],
  ];
  document.querySelector("#boot-entry-source-skeleton-package").innerHTML = sourceItems
    .map(
      ([label, items]) => `<article>
        <h3>${escapeHtml(label)}</h3>
        <p>${escapeHtml((items || []).filter(Boolean).join("；") || "无")}</p>
      </article>`,
    )
    .join("");
  const manualFactRows = (manualDeclarationGate.required_manual_facts || [])
    .map((item) => `${item.key}: ${item.status || "missing"} / stores=${item.stores_value ? "yes" : "no"}`);
  const manualChecklistRows = (manualDeclarationGate.boot_path_checklist || [])
    .map((item) => {
      const expected = item.expected || (item.expected_one_of || []).join(",");
      return `${item.id}: expected=${expected} observed=${item.observed || "pending"} passed=${item.passed ? "yes" : "no"}`;
    });
  const manualServiceStateRows = Object.entries(manualDeclarationGate.network_service_state || {})
    .map(([key, value]) => `${key}: ${value ? "yes" : "no"}`);
  const manualGateItems = [
    ["状态", [manualDeclarationGate.status || ""]],
    ["模式", [manualDeclarationGate.mode || ""]],
    ["提交状态", [manualDeclarationGate.submission_status || ""]],
    ["授权状态", [manualDeclarationGate.authorization_status || ""]],
    ["只读模板", [
      `read_only=${manualDeclarationGate.read_only ? "yes" : "no"}`,
      `template_only=${manualDeclarationGate.template_only ? "yes" : "no"}`,
      `collects_user_input=${manualDeclarationGate.collects_user_input ? "yes" : "no"}`,
      `stores_user_input=${manualDeclarationGate.stores_user_input ? "yes" : "no"}`,
    ]],
    ["运行边界", [
      `runtime=${manualDeclarationGate.runtime_enabled ? "yes" : "no"}`,
      `runtime_unlock=${manualDeclarationGate.runtime_unlock_allowed ? "yes" : "no"}`,
      `config_generation=${manualDeclarationGate.config_generation_allowed ? "yes" : "no"}`,
      `service_start=${manualDeclarationGate.service_start_allowed ? "yes" : "no"}`,
      `production_lan=${manualDeclarationGate.production_lan_allowed ? "yes" : "no"}`,
      `boot_tested=${manualDeclarationGate.boot_tested ? "yes" : "no"}`,
    ]],
    ["服务状态", manualServiceStateRows],
    ["缺失事实", manualDeclarationGate.missing_facts || []],
    ["手工事实模板", manualFactRows],
    ["启动路径检查", manualChecklistRows],
    ["授权门禁", manualDeclarationGate.authorization_gates || []],
    ["阻断动作", manualDeclarationGate.blocked_actions || []],
    ["下一门禁", manualDeclarationGate.next_gate || []],
  ];
  document.querySelector("#boot-entry-manual-declaration-gate").innerHTML = manualGateItems
    .map(
      ([label, items]) => `<article>
        <h3>${escapeHtml(label)}</h3>
        <p>${escapeHtml((items || []).filter(Boolean).join("；") || "无")}</p>
      </article>`,
    )
    .join("");
  const runtimeApprovalRows = (runtimeAuthorizationPlan.required_approvals || [])
    .map((item) => `${item.role}: ${item.status || "required"} / stores=${item.stores_value ? "yes" : "no"}`);
  const runtimeScopeRows = (runtimeAuthorizationPlan.runtime_scope_candidates || [])
    .map((item) => `${item.id}: ${item.status || ""} execute=${item.allowed_to_execute ? "yes" : "no"}`);
  const runtimeEvidenceRows = (runtimeAuthorizationPlan.boot_evidence_requirements || [])
    .map((item) => {
      const expected = item.expected || (item.expected_one_of || []).join(",");
      return `${item.id}: expected=${expected} observed=${item.observed || "pending"} passed=${item.passed ? "yes" : "no"}`;
    });
  const runtimeServiceStateRows = Object.entries(runtimeAuthorizationPlan.network_service_state || {})
    .map(([key, value]) => `${key}: ${value ? "yes" : "no"}`);
  const runtimePlanItems = [
    ["状态", [runtimeAuthorizationPlan.status || ""]],
    ["阶段", [runtimeAuthorizationPlan.phase || ""]],
    ["来源", [runtimeAuthorizationPlan.source || ""]],
    ["依赖门禁", [`manual_gate=${runtimeAuthorizationPlan.depends_on_manual_gate_phase || ""}`]],
    ["只读", [runtimeAuthorizationPlan.read_only ? "是" : "否"]],
    ["运行边界", [
      `runtime=${runtimeAuthorizationPlan.runtime_enabled ? "yes" : "no"}`,
      `runtime_start=${runtimeAuthorizationPlan.runtime_start_allowed ? "yes" : "no"}`,
      `service_start=${runtimeAuthorizationPlan.service_start_allowed ? "yes" : "no"}`,
      `config_generation=${runtimeAuthorizationPlan.config_generation_allowed ? "yes" : "no"}`,
      `production_lan=${runtimeAuthorizationPlan.production_lan_allowed ? "yes" : "no"}`,
      `boot_tested=${runtimeAuthorizationPlan.boot_tested ? "yes" : "no"}`,
    ]],
    ["服务状态", runtimeServiceStateRows],
    ["缺失手工事实", runtimeAuthorizationPlan.missing_manual_facts || []],
    ["必要审批", runtimeApprovalRows],
    ["候选范围", runtimeScopeRows],
    ["非目标", runtimeAuthorizationPlan.explicit_non_goals || []],
    ["转换要求", runtimeAuthorizationPlan.transition_requirements || []],
    ["回滚条件", runtimeAuthorizationPlan.rollback_conditions || []],
    ["启动证据要求", runtimeEvidenceRows],
    ["未来研究项", runtimeAuthorizationPlan.future_research_items || []],
    ["下一门禁", runtimeAuthorizationPlan.next_gate || []],
  ];
  document.querySelector("#boot-entry-runtime-authorization-plan").innerHTML = runtimePlanItems
    .map(
      ([label, items]) => `<article>
        <h3>${escapeHtml(label)}</h3>
        <p>${escapeHtml((items || []).filter(Boolean).join("；") || "无")}</p>
      </article>`,
    )
    .join("");
  document.querySelector("#boot-entry-list").innerHTML = (bootEntry.entries || [])
    .map(
      (entry) => `<article>
        <h3>${escapeHtml(entry.label)}</h3>
        <p><span class="badge ${statusClass(entry.status)}">${escapeHtml(entry.status)}</span> <span class="badge">${entry.enabled ? "启用" : "关闭"}</span></p>
        <p class="mono">${escapeHtml(entry.target || entry.bootfile || "")}</p>
        <p>${escapeHtml((entry.blocked_by || []).join("；"))}</p>
      </article>`,
    )
    .join("");
  document.querySelector("#boot-loader-list").innerHTML = (bootEntry.loaders || [])
    .map(
      (loader) => {
        const provenance = loader.provenance || {};
        return `<article>
        <h3>${escapeHtml(loader.filename)}</h3>
        <p><span class="badge ${loader.usable ? "ok" : "warn"}">${escapeHtml(loader.status || "missing")}</span> <span class="badge ${loader.reviewed_for_lab ? "ok" : "warn"}">${loader.reviewed_for_lab ? "已记录来源" : "待记录来源"}</span> <span class="badge">${escapeHtml(loader.architecture)}</span></p>
        <p>${escapeHtml(loader.purpose)}</p>
        <p>${escapeHtml(loader.source_recommendation?.note || "")}</p>
        <p class="mono">${escapeHtml(loader.usable ? loader.url : loader.path)}</p>
        <p><small>${formatSize(loader.size_bytes || 0)} · ${escapeHtml(loader.mtime || "mtime unavailable")}</small></p>
        <p><small>${escapeHtml(loader.sha256 || "sha256 unavailable")}</small></p>
        <p><small>${escapeHtml(loader.review_status || provenance.status || "provenance missing")} · ${escapeHtml(provenance.source_label || "source unavailable")}</small></p>
        <p><small>${escapeHtml(loader.secure_boot_risk?.reason || "")}</small></p>
      </article>`;
      },
    )
    .join("");
  document.querySelector("#boot-entry-verification").innerHTML = (bootEntry.local_verification_required || [])
    .map((item) => `<article><p>${escapeHtml(item)}</p></article>`)
    .join("");
}

function renderSafety() {
  const phase3Gate = safety.phase3_gate || {};
  const phase3ActionAllowed = [
    phase3Gate.implementation_allowed,
    phase3Gate.service_enablement_allowed,
    phase3Gate.production_lan_testing_allowed,
  ].some(Boolean);
  const items = [
    ["状态", safety.status],
    ["SERVER_IP", safety.server_ip],
    ["HTTP 端口", safety.http_port],
    ["管理 token", adminConfigured() ? "已配置" : "未配置，写操作不可用"],
    ["Phase 3.3", phase3Gate.status || ""],
    ["启动入口展示阶段", phase3Gate.display_phase || ""],
    ["允许实现/启用/生产 LAN 测试", phase3ActionAllowed ? "是" : "否"],
    ["允许范围", (safety.allowed || []).join(", ")],
    ["禁止项", (safety.forbidden || []).join(", ")],
  ];
  document.querySelector("#safety-status").innerHTML = items
    .map(([label, value]) => `<article><span>${label}</span><strong>${escapeHtml(String(value || ""))}</strong></article>`)
    .join("");
}

function renderDeployment() {
  const summaryTarget = document.querySelector("#deployment-status");
  if (!summaryTarget) return;
  const summary = [
    ["状态", deployment.status || ""],
    ["Web UI", deployment.web_url || ""],
    ["iPXE 菜单", deployment.menu_url || ""],
    ["镜像仓库", deployment.images_url || ""],
    ["管理 token", deployment.admin_configured ? "已配置" : "未配置"],
    [".env 内容", deployment.env_contents_exposed ? "已暴露" : "不展示"],
    ["就绪含义", deployment.readiness_scope || ""],
  ];
  summaryTarget.innerHTML = summary
    .map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value || ""))}</strong></article>`)
    .join("");
  const pathsTarget = document.querySelector("#deployment-paths");
  if (pathsTarget) {
    pathsTarget.innerHTML = (deployment.paths || [])
      .map(
        (item) => `<article>
          <h3>${escapeHtml(item.label || "")}</h3>
          <p><span class="badge ${item.exists && item.is_dir ? "ok" : "warn"}">${escapeHtml(item.exists && item.is_dir ? "ready" : "missing")}</span></p>
          <p class="mono">${escapeHtml(item.path || "")}</p>
        </article>`,
      )
      .join("");
  }
  renderList("#deployment-config-files", (deployment.config_files || []).map((item) => `${item.path}: ${item.exists ? "ready" : "missing"}`));
  renderList("#deployment-runtime-checks", deployment.runtime_checks || []);
  renderList("#deployment-next-actions", deployment.next_actions || []);
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}

function escapeAttr(value) {
  return escapeHtml(String(value));
}

function adminConfigured() {
  return Boolean(safety.admin_configured);
}

function applyAdminState() {
  const disabled = !adminConfigured();
  document.querySelectorAll(".admin-action").forEach((button) => {
    button.disabled = disabled;
    button.title = disabled ? "未配置 SYNABOOT_ADMIN_TOKEN，写操作不可用" : "";
  });
}

document.querySelectorAll("nav button").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
document.querySelector("#refresh-button").addEventListener("click", refresh);
document.querySelector("#scan-button").addEventListener("click", async () => {
  if (!adminConfigured()) {
    window.alert("未配置 SYNABOOT_ADMIN_TOKEN，扫描不可用。");
    return;
  }
  const token = window.prompt("请输入管理员 token。未配置 SYNABOOT_ADMIN_TOKEN 时扫描默认禁用。");
  if (!token) return;
  try {
    await postAdmin("/api/scan", {}, token);
    await refresh();
  } catch (error) {
    window.alert(`扫描失败：${error.message}`);
  }
});
document.querySelector("#generate-menu-button").addEventListener("click", async () => {
  if (!adminConfigured()) {
    window.alert("未配置 SYNABOOT_ADMIN_TOKEN，菜单生成不可用。");
    return;
  }
  const token = window.prompt("请输入管理员 token。");
  if (!token) return;
  try {
    await postAdminText("/api/menu/generate", token);
    await refresh();
  } catch (error) {
    window.alert(`生成失败：${error.message}`);
  }
});
document.querySelector("#image-search").addEventListener("input", renderImages);
document.querySelector("#category-filter").addEventListener("change", renderImages);
document.querySelectorAll(".autoinstall-create").forEach((button) =>
  button.addEventListener("click", async () => {
    if (!adminConfigured()) {
      window.alert("未配置 SYNABOOT_ADMIN_TOKEN，自动安装草稿创建不可用。");
      return;
    }
    const token = window.prompt("请输入管理员 token。");
    if (!token) return;
    try {
      await postAdmin("/api/autoinstall-profiles", { os_family: button.dataset.osFamily }, token);
      await refresh();
    } catch (error) {
      window.alert(`创建自动安装草稿失败：${error.message}`);
    }
  }),
);
document.querySelectorAll(".job-create").forEach((button) =>
  button.addEventListener("click", async () => {
    if (!adminConfigured()) {
      window.alert("未配置 SYNABOOT_ADMIN_TOKEN，任务创建不可用。");
      return;
    }
    const token = window.prompt("请输入管理员 token。");
    if (!token) return;
    try {
      await postAdmin("/api/jobs", { kind: button.dataset.kind }, token);
      await refresh();
    } catch (error) {
      window.alert(`创建失败：${error.message}`);
    }
  }),
);

async function postAdmin(url, payload, token) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-SynaBoot-Admin-Token": token },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`${url} ${response.status}`);
  return response.json();
}

async function postAdminText(url, token) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "X-SynaBoot-Admin-Token": token },
  });
  if (!response.ok) throw new Error(`${url} ${response.status}`);
  return response.text();
}

refresh().catch((error) => {
  console.error(error);
  document.querySelector("#category-summary").innerHTML = `<article><span>API</span><strong class="warn">暂不可用</strong></article>`;
});
