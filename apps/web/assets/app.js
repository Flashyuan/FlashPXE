const titles = {
  dashboard: ["Dashboard", "Phase 1 零侵入 HTTP Boot 控制台"],
  images: ["镜像仓库", "从 data/images 扫描得到的本地镜像元数据"],
  menu: ["菜单预览", "当前生成的 iPXE HTTP Boot 菜单"],
  hotpe: ["HotPE 指南", "通过 HotPE 访问 Windows 镜像仓库"],
  jobs: ["构建任务", "只生成模板与任务目录，不执行破坏性操作"],
  safety: ["网络安全", "已批准范围：仅 HTTP 8080/tcp"],
};

let images = [];
let jobs = [];
let safety = {};

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} ${response.status}`);
  return response.json();
}

async function refresh() {
  const [imageData, jobData, safetyData, menuText] = await Promise.all([
    fetchJson("/api/images"),
    fetchJson("/api/jobs"),
    fetchJson("/api/network-safety"),
    fetch("/api/menu", { cache: "no-store" }).then((response) => response.text()),
  ]);
  images = imageData.images || [];
  jobs = jobData.jobs || [];
  safety = safetyData || {};
  document.querySelector("#menu-preview").textContent = menuText;
  renderDashboard();
  renderImages();
  renderJobs();
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
  const summary = document.querySelector("#category-summary");
  summary.innerHTML = categories
    .map((category) => {
      const count = images.filter((image) => image.category === category).length;
      return `<article><span>${category}</span><strong>${count}</strong></article>`;
    })
    .join("");
}

function renderImages() {
  const query = document.querySelector("#image-search").value.trim().toLowerCase();
  const category = document.querySelector("#category-filter").value;
  const rows = images.filter((image) => {
    const text = `${image.name} ${image.rel_path}`.toLowerCase();
    return (!category || image.category === category) && (!query || text.includes(query));
  });
  document.querySelector("#images-table").innerHTML =
    rows
      .map(
        (image) => `<tr>
          <td><strong>${escapeHtml(image.name)}</strong><br><span class="badge">${escapeHtml(image.kind)}</span></td>
          <td>${escapeHtml(image.category)}</td>
          <td>${escapeHtml(image.kind)}</td>
          <td>${formatSize(image.size_bytes)}</td>
          <td>${escapeHtml(image.boot_method)}</td>
          <td><a href="/images/${encodeURI(image.rel_path)}">${escapeHtml(image.rel_path)}</a><br><small>${escapeHtml(image.sha256 || "")}</small></td>
          <td>
            <span class="badge">${image.menu_enabled ? "启用" : "禁用"}</span>
            <button class="small menu-toggle" data-id="${escapeHtml(image.id)}" data-enabled="${image.menu_enabled ? "1" : "0"}">
              ${image.menu_enabled ? "禁用" : "启用"}
            </button>
          </td>
        </tr>`,
      )
      .join("") || `<tr><td colspan="7">未发现镜像。请将文件放入 data/images 后刷新。</td></tr>`;
  document.querySelectorAll(".menu-toggle").forEach((button) =>
    button.addEventListener("click", async () => {
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
        </article>`,
      )
      .join("") || "<p>暂无任务。</p>";
}

function renderSafety() {
  const items = [
    ["状态", safety.status],
    ["SERVER_IP", safety.server_ip],
    ["HTTP 端口", safety.http_port],
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

document.querySelectorAll("nav button").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
document.querySelector("#refresh-button").addEventListener("click", refresh);
document.querySelector("#image-search").addEventListener("input", renderImages);
document.querySelector("#category-filter").addEventListener("change", renderImages);
document.querySelectorAll(".job-create").forEach((button) =>
  button.addEventListener("click", async () => {
    const token = window.prompt("请输入管理员 token。未配置 SYNABOOT_ADMIN_TOKEN 时写操作默认禁用。");
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

refresh().catch((error) => {
  console.error(error);
  document.querySelector("#category-summary").innerHTML = `<article><span>API</span><strong class="warn">暂不可用</strong></article>`;
});
