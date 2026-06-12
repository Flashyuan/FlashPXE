const titles = {
  dashboard: ["Dashboard", "Phase 2 零侵入 HTTP/iPXE Boot 控制台"],
  images: ["镜像仓库", "从 data/images 扫描得到的本地镜像元数据"],
  menu: ["菜单预览", "当前生成的 iPXE HTTP Boot 菜单"],
  hotpe: ["HotPE 指南", "通过 HotPE 访问 Windows 镜像仓库"],
  "boot-entry": ["启动入口", "Phase 3.4 只读启动入口与本地事实门禁"],
  jobs: ["构建任务", "只生成模板与任务目录，不执行破坏性操作"],
  safety: ["网络安全", "已批准范围：仅 HTTP 18080/tcp"],
};

let images = [];
let jobs = [];
let safety = {};
let bootEntry = {};

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} ${response.status}`);
  return response.json();
}

async function refresh() {
  const [imageData, jobData, safetyData, bootEntryData, menuText] = await Promise.all([
    fetchJson("/api/images"),
    fetchJson("/api/jobs"),
    fetchJson("/api/network-safety"),
    fetchJson("/api/boot-entry"),
    fetch("/api/menu", { cache: "no-store" }).then((response) => response.text()),
  ]);
  images = imageData.images || [];
  jobs = jobData.jobs || [];
  safety = safetyData || {};
  bootEntry = bootEntryData || {};
  document.querySelector("#menu-preview").textContent = menuText;
  applyAdminState();
  renderDashboard();
  renderRuntimeUrls();
  renderImages();
  renderJobs();
  renderBootEntry();
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
      .join("") || `<tr><td colspan="8">未发现镜像。请将文件放入 data/images 后扫描。</td></tr>`;
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
    </article>`;
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
  applyAdminState();
}

function statusClass(value) {
  if (["ready", "present"].includes(value)) return "ok";
  if (["missing", "incomplete", "needs_hotpe"].includes(value)) return "warn";
  return "";
}

function renderJobs() {
  document.querySelector("#jobs-list").innerHTML =
    jobs
      .map(
        (job) => `<article>
          <h3>${escapeHtml(job.title)}</h3>
          <p><span class="badge">${escapeHtml(job.kind)}</span> <span class="badge">${escapeHtml(job.status)}</span></p>
          <p>${escapeHtml(job.note)}</p>
          <p class="mono">${escapeHtml(job.output_dir)}</p>
          <button class="small job-detail-open" data-id="${escapeAttr(job.id)}">详情</button>
          ${job.status === "draft" ? `<button class="small job-submit admin-action" data-id="${escapeAttr(job.id)}">提交待执行</button>` : ""}
          ${["draft", "pending"].includes(job.status) ? `<button class="small job-cancel admin-action" data-id="${escapeAttr(job.id)}">取消</button>` : ""}
        </article>`,
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
  document.querySelector("#job-detail").innerHTML = `
    <div class="detail-grid">
      <article><span>任务 ID</span><strong>${escapeHtml(job.id)}</strong></article>
      <article><span>类型</span><strong>${escapeHtml(job.kind)}</strong></article>
      <article><span>状态</span><strong>${escapeHtml(job.status)}</strong></article>
      <article><span>输出目录</span><strong>${escapeHtml(job.output_dir)}</strong></article>
      <article><span>说明</span><strong>${escapeHtml(job.note)}</strong></article>
    </div>
    <h3>事件日志</h3>
    <pre>${escapeHtml(events.map((event) => JSON.stringify(event)).join("\n") || "暂无事件。")}</pre>
  `;
}

function renderBootEntry() {
  const documentation = bootEntry.documentation || {};
  const phaseGate = bootEntry.phase3_3_gate || {};
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
      (loader) => `<article>
        <h3>${escapeHtml(loader.filename)}</h3>
        <p><span class="badge ${loader.usable ? "ok" : "warn"}">${escapeHtml(loader.status || "missing")}</span> <span class="badge">${escapeHtml(loader.architecture)}</span></p>
        <p>${escapeHtml(loader.purpose)}</p>
        <p>${escapeHtml(loader.source_recommendation?.note || "")}</p>
        <p class="mono">${escapeHtml(loader.usable ? loader.url : loader.path)}</p>
        <p><small>${formatSize(loader.size_bytes || 0)} · ${escapeHtml(loader.mtime || "mtime unavailable")}</small></p>
        <p><small>${escapeHtml(loader.sha256 || "sha256 unavailable")}</small></p>
        <p><small>${escapeHtml(loader.secure_boot_risk?.reason || "")}</small></p>
      </article>`,
    )
    .join("");
  document.querySelector("#boot-entry-verification").innerHTML = (bootEntry.local_verification_required || [])
    .map((item) => `<article><p>${escapeHtml(item)}</p></article>`)
    .join("");
}

function renderSafety() {
  const items = [
    ["状态", safety.status],
    ["SERVER_IP", safety.server_ip],
    ["HTTP 端口", safety.http_port],
    ["管理 token", adminConfigured() ? "已配置" : "未配置，写操作不可用"],
    ["允许范围", (safety.allowed || []).join(", ")],
    ["禁止项", (safety.forbidden || []).join(", ")],
  ];
  document.querySelector("#safety-status").innerHTML = items
    .map(([label, value]) => `<article><span>${label}</span><strong>${escapeHtml(String(value || ""))}</strong></article>`)
    .join("");
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
