import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Boxes,
  Check,
  ChevronRight,
  ClipboardList,
  Disc3,
  Gauge,
  PackagePlus,
  RefreshCw,
  Rocket,
  Search,
  ShieldCheck,
  Upload,
  TerminalSquare,
  Users,
  X,
} from "lucide-react";
import "./index.css";
import { Badge, Button, Card, EmptyState, SectionTitle } from "./components/ui";
import { cn, fetchJson, formatSize, postAdmin, statusTone } from "./lib/utils";
import type { AdminSession, AppData, AssignmentOptions, BootEntry, Capabilities, ClientEvent, ClientSessionsResponse, Deployment, DeploymentAssignmentsResponse, HotpeReadiness, ImageItem, ImagesResponse, InstallPreset, InstallPresetsResponse, JobItem, Safety, SoftwarePackage, SoftwarePackagesResponse, SoftwareProfile, SoftwareProfilesResponse, SoftwareVariant } from "./types";

const WEB_AUTO_REFRESH_MS = 5 * 60 * 1000;

const navItems = [
  { id: "overview", label: "总览", icon: Gauge },
  { id: "images", label: "镜像", icon: Disc3 },
  { id: "clients", label: "客户端", icon: Users },
  { id: "software", label: "软件", icon: PackagePlus },
  { id: "presets", label: "安装预设", icon: ClipboardList },
  { id: "boot", label: "启动菜单", icon: TerminalSquare },
  { id: "safety", label: "实验 / 安全", icon: ShieldCheck },
] as const;

type ViewId = (typeof navItems)[number]["id"];

const emptyData: AppData = {
  images: [],
  software: [],
  softwareProfiles: [],
  installPresets: [],
  clients: {},
  assignments: [],
  jobs: [],
  capabilities: {},
  safety: {},
  deployment: {},
  hotpe: {},
  bootEntry: {},
  menuText: "",
};

function App() {
  const [activeView, setActiveView] = useState<ViewId>("overview");
  const [data, setData] = useState<AppData>(emptyData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedImageId, setSelectedImageId] = useState<string>("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [adminToken, setAdminToken] = useState(() => window.localStorage.getItem("synaboot_admin_token") || "");

  async function refresh() {
    setError("");
    setLoading(true);
    try {
      const clientHeaders = adminToken ? { "X-SynaBoot-Admin-Token": adminToken } : undefined;
      const assignmentsRequest = adminToken
        ? fetch("/api/deployment-assignments", { cache: "no-store", headers: clientHeaders }).then((response) => {
          if (!response.ok) throw new Error(`/api/deployment-assignments ${response.status}`);
          return response.json() as Promise<DeploymentAssignmentsResponse>;
        })
        : Promise.resolve({ assignments: [] } as DeploymentAssignmentsResponse);
      const [images, clients, software, softwareProfiles, installPresets, assignments, jobs, capabilities, safety, deployment, hotpe, bootEntry, menuText] = await Promise.all([
        fetchJson<ImagesResponse>("/api/images"),
        fetch("/api/client-sessions", { cache: "no-store", headers: clientHeaders }).then((response) => {
          if (!response.ok) throw new Error(`/api/client-sessions ${response.status}`);
          return response.json() as Promise<ClientSessionsResponse>;
        }),
        fetchJson<SoftwarePackagesResponse>("/api/software-packages"),
        fetchJson<SoftwareProfilesResponse>("/api/software-profiles"),
        fetchJson<InstallPresetsResponse>("/api/install-presets"),
        assignmentsRequest,
        fetchJson<{ jobs: JobItem[] }>("/api/jobs"),
        fetchJson<Capabilities>("/api/capabilities"),
        fetchJson<Safety>("/api/network-safety"),
        fetchJson<Deployment>("/api/deployment-status"),
        fetchJson<HotpeReadiness>("/api/hotpe-readiness"),
        fetchJson<BootEntry>("/api/boot-entry"),
        fetch("/api/menu", { cache: "no-store" }).then((response) => response.text()),
      ]);
      const nextData = {
        images: images.source_images?.length ? images.source_images : images.images || [],
        software: software.packages || [],
        softwareProfiles: softwareProfiles.profiles || [],
        installPresets: installPresets.presets || [],
        clients,
        assignments: assignments.assignments || [],
        jobs: jobs.jobs || [],
        capabilities,
        safety,
        deployment,
        hotpe,
        bootEntry,
        menuText,
      };
      setData(nextData);
      setSelectedImageId((current) => current || nextData.images[0]?.id || "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, [adminToken]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refresh();
    }, WEB_AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [adminToken]);

  const selectedImage = data.images.find((item) => item.id === selectedImageId);
  const filteredImages = useMemo(() => {
    const query = search.trim().toLowerCase();
    return data.images.filter((image) => {
      const text = `${image.display_name || image.name || ""} ${image.relative_path || image.rel_path || ""} ${image.detected_distro || ""} ${image.strategy_key || ""}`.toLowerCase();
      return (!category || image.category === category) && (!query || text.includes(query));
    });
  }, [category, data.images, search]);

  return (
    <div className="min-h-dvh">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-zinc-200 bg-white/90 px-4 py-5 backdrop-blur lg:block">
        <Brand />
        <nav className="mt-8 grid gap-1">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={cn(
                "flex min-h-11 items-center gap-3 rounded-md px-3 text-left text-sm font-medium text-zinc-600 transition-colors",
                activeView === item.id ? "bg-zinc-950 text-white" : "hover:bg-zinc-100 hover:text-zinc-950",
              )}
              onClick={() => setActiveView(item.id)}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-10 border-b border-zinc-200 bg-white/82 px-4 py-3 backdrop-blur md:px-8">
          <div className="mx-auto flex max-w-7xl flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-700">FlashPXE Admin Console</p>
              <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-950 md:text-3xl">{pageTitle(activeView)}</h1>
            </div>
            <div className="flex items-center gap-2 overflow-x-auto pb-1 lg:hidden">
              {navItems.map((item) => (
                <Button key={item.id} variant={activeView === item.id ? "default" : "outline"} size="sm" onClick={() => setActiveView(item.id)}>
                  {item.label}
                </Button>
              ))}
            </div>
            <Button variant="accent" onClick={refresh} disabled={loading}>
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
              刷新
            </Button>
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-4 py-6 md:px-8">
          {error ? <Notice tone="danger" title="读取数据失败" detail={error} /> : null}
          {activeView === "overview" ? <Overview data={data} loading={loading} onNavigate={setActiveView} /> : null}
          {activeView === "images" ? (
            <ImagesView
              data={data}
              filteredImages={filteredImages}
              selectedImage={selectedImage}
              search={search}
              category={category}
              setSearch={setSearch}
              setCategory={setCategory}
              setSelectedImageId={setSelectedImageId}
              onRefresh={refresh}
              adminToken={adminToken}
              setAdminToken={setAdminToken}
            />
          ) : null}
          {activeView === "clients" ? <ClientsView data={data} adminToken={adminToken} setAdminToken={setAdminToken} onRefresh={refresh} /> : null}
          {activeView === "software" ? <SoftwareView packages={data.software} profiles={data.softwareProfiles} adminToken={adminToken} setAdminToken={setAdminToken} onRefresh={refresh} /> : null}
          {activeView === "presets" ? <PresetsView data={data} adminToken={adminToken} setAdminToken={setAdminToken} onRefresh={refresh} /> : null}
          {activeView === "boot" ? <BootView data={data} onRefresh={refresh} /> : null}
          {activeView === "safety" ? <SafetyView data={data} /> : null}
        </main>
      </div>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div className="grid h-11 w-11 place-items-center rounded-lg bg-zinc-950 text-sm font-black text-cyan-300 shadow-sm">FP</div>
      <div>
        <p className="text-base font-semibold text-zinc-950">FlashPXE</p>
        <p className="text-xs text-zinc-500">SynaBoot control plane</p>
      </div>
    </div>
  );
}

function pageTitle(view: ViewId) {
  return {
    overview: "装机控制台",
    images: "镜像仓库",
    clients: "客户端安装任务",
    software: "软件市场",
    presets: "安装任务预设",
    boot: "启动菜单",
    safety: "实验与安全边界",
  }[view];
}

function Overview({ data, loading, onNavigate }: { data: AppData; loading: boolean; onNavigate: (view: ViewId) => void }) {
  const installableImages = data.images.filter((image) => image.scan_status === "present" && ["ready", "needs_hotpe"].includes(image.strategy_status || image.boot_readiness || ""));
  const pendingImages = data.images.filter((image) => image.strategy_status === "research_required" || image.boot_readiness === "incomplete");
  const connectedClients = data.clients.sessions || [];
  const metrics = [
    { label: "可安装 ISO", value: installableImages.length, detail: `${data.images.length} 个源镜像` },
    { label: "待准备/研究", value: pendingImages.length, detail: "需要自动准备或新增策略" },
    { label: "已连接客户端", value: data.clients.summary?.online || 0, detail: `${data.clients.summary?.waiting || 0} 台等待分配` },
    { label: "软件市场", value: data.software.length, detail: `${data.software.reduce((count, item) => count + (item.variants?.length || 0), 0)} 个系统版本` },
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-4">
        {metrics.map((metric) => (
          <Card key={metric.label}>
            <p className="text-sm text-zinc-500">{metric.label}</p>
            <strong className="mt-2 block text-2xl font-semibold text-zinc-950">{loading ? "..." : metric.value}</strong>
            <p className="mt-2 text-xs text-zinc-500">{metric.detail}</p>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_0.9fr]">
        <Card>
          <SectionTitle eyebrow="available systems" title="可安装系统">已具备可用启动策略的 ISO。</SectionTitle>
          <div className="grid gap-2">
            {installableImages.map((image) => (
              <button key={image.id} className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 text-left hover:border-cyan-300" onClick={() => onNavigate("images")}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-zinc-950">{image.display_name || image.name}</span>
                  <Badge tone="ok">{image.strategy_display_name || image.strategy_key || image.boot_method}</Badge>
                </div>
              </button>
            ))}
            {!installableImages.length ? <EmptyState title="暂无可安装 ISO" /> : null}
          </div>
        </Card>
        <Card>
          <SectionTitle eyebrow="connected clients" title="当前 PXE/HTTP 客户端" />
          <div className="space-y-3">
            {connectedClients.map((client) => (
              <Step key={client.session_id} label={client.mac || client.uuid || client.session_id} value={client.selected_label || "未选择镜像"} detail={client.state || "waiting"} tone={client.online ? "ok" : "warn"} />
            ))}
            {!connectedClients.length ? <EmptyState title="暂无已连接客户端">等待客户端会话回调接入。</EmptyState> : null}
          </div>
        </Card>
      </div>
    </div>
  );
}

async function validateAdminToken(token: string): Promise<AdminSession> {
  const response = await fetch("/api/admin/session", {
    cache: "no-store",
    headers: token ? { "X-SynaBoot-Admin-Token": token } : undefined,
  });
  const payload = (await response.json().catch(() => ({}))) as AdminSession;
  if (!response.ok) {
    throw new Error(payload.error || `/api/admin/session ${response.status}`);
  }
  return payload;
}

function storeAdminToken(token: string, setAdminToken: (token: string) => void) {
  if (token) {
    window.localStorage.setItem("synaboot_admin_token", token);
  } else {
    window.localStorage.removeItem("synaboot_admin_token");
  }
  setAdminToken(token);
}

function slugifyId(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

function osFamilyForTarget(target: string): "windows" | "ubuntu" | "linux" | "" {
  const value = target.toLowerCase();
  if (value.includes("windows")) return "windows";
  if (value.includes("ubuntu")) return "ubuntu";
  if (value.includes("linux")) return "linux";
  return "";
}

function variantForTarget(item: SoftwarePackage, target: string): SoftwareVariant | undefined {
  const osFamily = osFamilyForTarget(target);
  if (!osFamily) return undefined;
  const compatible = (item.variants || []).filter((variant) => variant.os_family === osFamily || (osFamily === "linux" && variant.os_family === "ubuntu"));
  return compatible.find((variant) => variant.assignable) || compatible[0];
}

function installerTypeForAction(action: string) {
  const map: Record<string, string> = {
    apt_package: "apt",
    download_deb: "deb",
    msi_install: "msi",
    exe_install: "exe",
    office_odt_install: "office_odt",
    official_download: "installer",
  };
  return map[action] || "installer";
}

function variantLabel(variant?: SoftwareVariant) {
  if (!variant) return "无兼容版本";
  const os = variant.os_family === "ubuntu" ? "Ubuntu" : variant.os_family === "windows" ? "Windows" : variant.os_family;
  return [os, variant.arch, variant.version].filter(Boolean).join(" ");
}

function installSourceLabel(variant?: SoftwareVariant) {
  if (!variant) return "不可用";
  const source = variant.source_policy === "official_package_repo"
    ? "官方软件源"
    : variant.source_policy === "approved_enterprise_mirror"
      ? "企业批准镜像源"
      : variant.source_policy === "admin_reviewed_download"
        ? "管理员审核直链"
        : "官方来源";
  return `${source} · ${variant.installer_type || "installer"}`;
}

function eventTone(status?: string): "ok" | "warn" | "danger" | "muted" {
  if (status === "completed") return "ok";
  if (status === "failed" || status === "blocked") return "danger";
  if (status === "started" || status === "requested") return "warn";
  if (status === "skipped") return "muted";
  return "muted";
}

function eventLabel(status?: string) {
  const labels: Record<string, string> = {
    requested: "已请求",
    started: "执行中",
    completed: "已完成",
    failed: "失败",
    blocked: "已阻断",
    skipped: "已跳过",
  };
  return labels[status || ""] || "等待回调";
}

function eventVariantId(event?: ClientEvent) {
  const raw = event?.payload?.variant_id;
  return typeof raw === "string" ? raw : "";
}

function latestVariantEvent(events: ClientEvent[], variantId: string) {
  return events.find((event) => event.stage === "variant" && eventVariantId(event) === variantId);
}

function blockedReasonText(reasons?: string[]) {
  if (!reasons?.length) return "";
  const labels: Record<string, string> = {
    disabled: "已禁用",
    review_required: "需要审核",
    source_policy_not_allowed: "来源策略未批准",
    signature_policy_not_allowed: "签名策略未批准",
    official_source_url_must_be_https: "官方来源必须是 HTTPS",
    download_url_must_be_https: "下载地址必须是 HTTPS",
    official_source_must_not_be_hosted_by_synaboot: "官方来源不得指向 SynaBoot 本机或内网静态目录",
    sha256_required: "缺少 sha256",
    third_party_binary_must_not_be_hosted_by_synaboot: "不得由 SynaBoot 托管第三方安装包",
    install_action_not_allowlisted: "安装动作未在白名单内",
    runner_action_not_ready: "当前系统的安装执行器尚未支持该动作",
    install_phase_not_supported: "安装阶段暂不支持",
    installer_type_not_supported: "安装器类型暂不支持",
    package_name_invalid: "软件包名不符合 allowlist",
    office_product_id_invalid: "Office 产品 ID 不合法",
    invalid_office_product_id: "Office 产品 ID 不合法",
    office_product_id_required: "Office ODT 需要填写产品 ID",
    apt_repo_not_supported: "当前 runner 只支持 Ubuntu 默认 apt 源，暂不支持自动添加外部 apt 源",
  };
  return reasons.map((item) => labels[item] || item).join("，");
}

function ImagesView({
  data,
  filteredImages,
  selectedImage,
  search,
  category,
  setSearch,
  setCategory,
  setSelectedImageId,
  onRefresh,
  adminToken,
  setAdminToken,
}: {
  data: AppData;
  filteredImages: ImageItem[];
  selectedImage?: ImageItem;
  search: string;
  category: string;
  setSearch: (value: string) => void;
  setCategory: (value: string) => void;
  setSelectedImageId: (value: string) => void;
  onRefresh: () => Promise<void>;
  adminToken: string;
  setAdminToken: (token: string) => void;
}) {
  const [importOpen, setImportOpen] = useState(false);
  return (
    <div className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
      <section className="space-y-4">
        <Card>
          <SectionTitle eyebrow="iso repository" title="ISO 镜像">只展示管理员上传的 ISO。</SectionTitle>
          <div className="grid gap-3 md:grid-cols-[1fr_180px_auto]">
            <input className="min-h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索镜像名称或路径" />
            <select className="min-h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">全部分类</option>
              <option value="windows">Windows</option>
              <option value="pe">HotPE / PE</option>
              <option value="linux">Linux</option>
              <option value="tools">Tools</option>
              <option value="custom">Custom</option>
            </select>
            <Button variant="accent" onClick={() => setImportOpen((value) => !value)}>
              <Upload className="h-4 w-4" />
              上传 ISO
            </Button>
          </div>
          {importOpen ? <IsoImportPanel adminToken={adminToken} setAdminToken={setAdminToken} onRefresh={onRefresh} /> : null}
        </Card>
        <div className="grid gap-3">
          {filteredImages.map((image) => (
            <button
              key={image.id}
              className={cn(
                "rounded-lg border bg-white p-4 text-left shadow-sm transition-colors hover:border-cyan-300",
                selectedImage?.id === image.id ? "border-cyan-400 ring-2 ring-cyan-100" : "border-zinc-200",
              )}
              onClick={() => setSelectedImageId(image.id)}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-semibold text-zinc-950">{image.display_name || image.name}</p>
                  <p className="mt-1 text-xs text-zinc-500">{image.relative_path || image.rel_path}</p>
                </div>
                <ChevronRight className="mt-1 h-4 w-4 text-zinc-400" />
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <Badge tone={statusTone(image.strategy_status || image.boot_readiness)}>{image.strategy_status || image.boot_readiness || "unknown"}</Badge>
                <Badge tone={statusTone(image.preparation_status)}>{image.preparation_status || "unknown"}</Badge>
                <Badge>{image.strategy_display_name || image.strategy_key || image.boot_method || "strategy"}</Badge>
                <Badge>{formatSize(image.size_bytes)}</Badge>
              </div>
            </button>
          ))}
          {!filteredImages.length ? <EmptyState title="没有匹配的镜像" /> : null}
        </div>
      </section>

      <section className="space-y-4">
        <ImageDetail image={selectedImage} onRefresh={onRefresh} />
      </section>
    </div>
  );
}

function IsoImportPanel({
  adminToken,
  setAdminToken,
  onRefresh,
}: {
  adminToken: string;
  setAdminToken: (token: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [dropFolder, setDropFolder] = useState("data/images/");

  async function scanLocalImages() {
    setBusy(true);
    setMessage("");
    try {
      let token = adminToken;
      if (!token) {
        token = window.prompt("请输入管理员 token")?.trim() || "";
      }
      if (!token) {
        setMessage("已取消：需要管理员 token 才能触发扫描。");
        return;
      }
      const session = await validateAdminToken(token);
      if (!session.authenticated) {
        setMessage(session.admin_configured ? "管理员 token 无效。" : "后端尚未配置 SYNABOOT_ADMIN_TOKEN。");
        return;
      }
      storeAdminToken(token, setAdminToken);
      setDropFolder(session.image_drop_folder || "data/images/");
      const result = await postAdmin<{ count?: number }>("/api/scan", {}, token);
      setMessage(`扫描完成，发现 ${result.count ?? 0} 个可识别镜像/启动文件。`);
      await onRefresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-cyan-200 bg-cyan-50/60 p-4">
      <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
        <div>
          <p className="font-medium text-zinc-950">本地 ISO 导入</p>
          <p className="mt-1 text-sm leading-6 text-zinc-600">
            先把 ISO 放入 <code className="rounded bg-white px-1.5 py-0.5 font-mono text-xs">{dropFolder}</code>，
            然后触发后端扫描。浏览器大文件上传会在后续作为任务化能力接入。
          </p>
        </div>
        <Button variant="accent" onClick={scanLocalImages} disabled={busy}>
          <RefreshCw className="h-4 w-4" />
          {busy ? "扫描中" : "扫描本地 ISO"}
        </Button>
      </div>
      {message ? <p className="mt-3 rounded-md bg-white px-3 py-2 text-sm text-zinc-700">{message}</p> : null}
    </div>
  );
}

function ImageDetail({ image, onRefresh }: { image?: ImageItem; onRefresh: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  if (!image) return <EmptyState title="请选择一个镜像" />;

  async function createPrepareJob() {
    if (!image) return;
    const token = window.prompt("请输入管理员 token");
    if (!token) return;
    const kind = image.strategy_key === "hotpe_wimboot" ? "hotpe-iso-prepare" : image.strategy_key === "ubuntu_desktop_nfs_livefs" ? "ubuntu-iso-extract-kernel-initrd" : "";
    if (!kind) {
      window.alert("当前镜像不需要准备任务。");
      return;
    }
    setBusy(true);
    try {
      await postAdmin("/api/jobs", { kind, source_image_id: image.id }, token);
      await onRefresh();
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  const fields = [
    ["分类", image.category],
    ["系统", [image.os_family, image.detected_distro, image.detected_version, image.detected_arch].filter(Boolean).join(" ")],
    ["启动策略", image.strategy_display_name || image.strategy_key || image.boot_method],
    ["策略状态", image.strategy_status || image.boot_readiness],
    ["准备", image.preparation_status],
    ["引导环境", (image.artifact_count || image.artifacts?.length || 0) > 0 ? "已检查" : "待准备"],
    ["大小", formatSize(image.size_bytes)],
  ];
  return (
    <Card>
      <SectionTitle eyebrow="image detail" title={image.display_name || image.name || "镜像详情"}>{image.next_action || "检查启动状态和准备动作。"}</SectionTitle>
      <div className="grid gap-3 sm:grid-cols-2">
        {fields.map(([label, value]) => (
          <div key={label} className="rounded-md border border-zinc-200 bg-zinc-50 p-3">
            <p className="text-xs text-zinc-500">{label}</p>
            <p className="mt-1 break-words text-sm font-medium text-zinc-900">{value || "-"}</p>
          </div>
        ))}
      </div>
      <details className="mt-4 rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm">
        <summary className="cursor-pointer font-medium text-zinc-800">技术信息</summary>
        <div className="mt-3 rounded-md bg-zinc-950 p-3 font-mono text-xs text-zinc-100">
          <p>{image.relative_path || image.rel_path}</p>
          <p className="mt-1 text-zinc-400">{image.sha256 || "sha256 not calculated"}</p>
        </div>
      </details>
      {image.missing_artifacts?.length ? (
        <Notice tone="warn" title="引导环境未完整" detail={`缺少 ${image.missing_artifacts.length} 个必要组件，准备任务接入后会自动处理。`} />
      ) : null}
      {image.detection_evidence?.length ? (
        <div className="mt-4 rounded-md border border-zinc-200 bg-zinc-50 p-3">
          <p className="text-xs text-zinc-500">识别依据</p>
          <p className="mt-1 break-words text-sm text-zinc-700">{image.detection_evidence.join("，")}</p>
        </div>
      ) : null}
      {image.strategy_status === "research_required" ? (
        <Notice tone="warn" title="需要先补充启动策略" detail="该系统镜像需要先确认官方网络启动方式，当前不会生成菜单项。" />
      ) : null}
      {image.artifact_count || image.artifacts?.length ? (
        <div className="mt-4 rounded-md border border-zinc-200 bg-zinc-50 p-3">
          <p className="text-xs text-zinc-500">引导环境</p>
          <p className="mt-1 text-sm font-medium text-zinc-900">已确认 {image.artifact_count || image.artifacts?.length || 0} 个必要引导文件存在</p>
        </div>
      ) : null}
      {image.preparation_status === "needs_extraction" && image.strategy_status !== "research_required" ? (
        <div className="mt-4">
          <Button variant="accent" onClick={createPrepareJob} disabled={busy}>
            <Boxes className="h-4 w-4" />
            创建准备任务
          </Button>
        </div>
      ) : null}
    </Card>
  );
}

function HotpeQuickCard({ hotpe }: { hotpe: HotpeReadiness }) {
  return (
    <Card>
      <SectionTitle eyebrow="HotPE" title="HotPE / Windows 操作提示">HotPE 可以启动后，Windows ISO 仍需要在 PE 内挂载后选择 `sources/install.wim` 或 `install.esd`。</SectionTitle>
      <div className="grid gap-3">
        <Step label="HotPE 菜单" value={hotpe.hotpe_menu_ready ? "已就绪" : hotpe.status || "未知"} tone={hotpe.hotpe_menu_ready ? "ok" : "warn"} />
        <Step label="Windows 候选" value={`${hotpe.windows_iso_candidate_count || 0} 个`} tone={hotpe.windows_iso_candidate_count ? "ok" : "warn"} />
        <Step label="客户端验证" value={hotpe.client_install_test_status || "not_tested"} tone="warn" />
      </div>
    </Card>
  );
}

function PresetsView({
  data,
  adminToken,
  setAdminToken,
  onRefresh,
}: {
  data: AppData;
  adminToken: string;
  setAdminToken: (token: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const presets = data.installPresets;
  const software = data.software;
  const targets = data.clients.assignable_targets || [];
  const softwareById = new Map(software.map((item) => [item.id, item]));
  const activePresets = presets.filter((preset) => preset.status !== "archived");
  const grouped = activePresets.reduce<Record<string, InstallPreset[]>>((acc, preset) => {
    const key = preset.os_family || "other";
    acc[key] = [...(acc[key] || []), preset];
    return acc;
  }, {});
  const [createOpen, setCreateOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [softwarePickerOpen, setSoftwarePickerOpen] = useState(false);
  const [form, setForm] = useState({
    id: "",
    name: "",
    description: "",
    boot_target: targets[0]?.target || "",
  });
  const selectedTargetInfo = targets.find((target) => target.target === form.boot_target);
  const osFamily = osFamilyForTarget(form.boot_target);
  const softwareAssignmentEnabled = Boolean(selectedTargetInfo?.software_assignment_enabled);
  const softwareCatalog = software.filter((item) => Boolean(variantForTarget(item, form.boot_target)));
  const [selectedPackageIds, setSelectedPackageIds] = useState<string[]>([]);

  async function presetAdminToken() {
    let token = adminToken;
    if (!token) {
      token = window.prompt("请输入管理员 token")?.trim() || "";
    }
    if (!token) throw new Error("已取消：保存安装任务预设需要管理员 token。");
    const session = await validateAdminToken(token);
    if (!session.authenticated) {
      throw new Error(session.admin_configured ? "管理员 token 无效。" : "后端尚未配置 SYNABOOT_ADMIN_TOKEN。");
    }
    storeAdminToken(token, setAdminToken);
    return token;
  }

  async function savePreset() {
    setBusy(true);
    setMessage("");
    try {
      const token = await presetAdminToken();
      const name = form.name.trim();
      const presetId = (form.id || slugifyId(name)).trim();
      if (!name) throw new Error("请填写预设名称。");
      if (!presetId) throw new Error("请填写英文/数字预设 ID，例如 windows-office-standard。");
      if (!form.boot_target || !osFamily) throw new Error("请选择系统镜像/启动目标。");
      if (selectedPackageIds.length && !softwareAssignmentEnabled) {
        throw new Error("当前启动目标没有可验证的软件自动安装通道，不能保存带软件的预设。");
      }
      await postAdmin<InstallPreset>(
        "/api/install-presets",
        {
          id: presetId,
          name,
          description: form.description.trim(),
          os_family: osFamily === "linux" ? "ubuntu" : osFamily,
          boot_target: form.boot_target,
          software_package_ids: selectedPackageIds,
          software_profile_ids: [],
          settings: { schema_version: "synaboot.install-preset-settings.v1" },
        },
        token,
      );
      setMessage(`预设 ${name} 已保存，可在客户端创建安装任务时选择。`);
      setCreateOpen(false);
      setForm({ id: "", name: "", description: "", boot_target: targets[0]?.target || "" });
      setSelectedPackageIds([]);
      await onRefresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function updatePresetStatus(preset: InstallPreset, action: "archive" | "restore") {
    setBusy(true);
    setMessage("");
    try {
      const token = await presetAdminToken();
      const updated = await postAdmin<InstallPreset>(`/api/install-presets/${encodeURIComponent(preset.id)}/${action}`, {}, token);
      setMessage(`${updated.name} 已${action === "archive" ? "归档" : "恢复"}。`);
      await onRefresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <SectionTitle eyebrow="presets" title="可用预设" />
          <strong className="text-3xl font-semibold text-zinc-950">{activePresets.length}</strong>
          <p className="mt-2 text-sm text-zinc-500">系统 + 软件组合</p>
        </Card>
        <Card>
          <SectionTitle eyebrow="windows" title="Windows 预设" />
          <strong className="text-3xl font-semibold text-zinc-950">{grouped.windows?.length || 0}</strong>
          <p className="mt-2 text-sm text-zinc-500">适用于 WinPE/Windows 安装目标</p>
        </Card>
        <Card>
          <SectionTitle eyebrow="linux" title="Linux 预设" />
          <strong className="text-3xl font-semibold text-zinc-950">{(grouped.ubuntu?.length || 0) + (grouped.linux?.length || 0)}</strong>
          <p className="mt-2 text-sm text-zinc-500">适用于 Ubuntu 等 Linux 安装目标</p>
        </Card>
      </div>

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <SectionTitle eyebrow="install task presets" title="安装任务预设">
            预设只保存系统启动目标和自动安装软件，不包含磁盘设置。批量装机时在客户端页面直接套用。
          </SectionTitle>
          <Button variant="accent" onClick={() => setCreateOpen((current) => !current)}>
            <PackagePlus className="h-4 w-4" />
            {createOpen ? "关闭配置" : "新建预设"}
          </Button>
        </div>
        {message ? <p className="mb-3 rounded-md bg-zinc-50 px-3 py-2 text-sm text-zinc-700">{message}</p> : null}
        {createOpen ? (
          <div className="mb-4 rounded-lg border border-cyan-200 bg-cyan-50/60 p-4">
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">预设名称</span>
                <input
                  className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300"
                  value={form.name}
                  onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="例如 Windows 办公标准套件"
                />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">预设 ID</span>
                <input
                  className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300"
                  value={form.id}
                  onChange={(event) => setForm((current) => ({ ...current, id: event.target.value }))}
                  placeholder={slugifyId(form.name) || "windows-office-standard"}
                />
              </label>
              <label className="grid gap-1 text-sm md:col-span-2">
                <span className="font-medium text-zinc-800">说明</span>
                <input
                  className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300"
                  value={form.description}
                  onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                  placeholder="说明这个预设适合哪些电脑或装机场景"
                />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">系统镜像/启动目标</span>
                <select
                  className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300"
                  value={form.boot_target}
                  onChange={(event) => {
                    setForm((current) => ({ ...current, boot_target: event.target.value }));
                    setSelectedPackageIds([]);
                  }}
                >
                  <option value="">请选择</option>
                  {targets.map((target) => (
                    <option key={target.target} value={target.target}>{target.label}</option>
                  ))}
                </select>
              </label>
              <div className="rounded-md border border-zinc-200 bg-white p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-zinc-800">预装软件</p>
                    <p className="mt-1 text-sm text-zinc-500">
                      {softwareAssignmentEnabled ? "从软件市场选择本预设默认安装的软件。" : "当前目标暂不支持自动安装软件。"}
                    </p>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => setSoftwarePickerOpen(true)} disabled={!form.boot_target || !softwareAssignmentEnabled}>
                    <PackagePlus className="h-4 w-4" />
                    选择软件
                  </Button>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {selectedPackageIds.map((id) => {
                    const item = softwareById.get(id);
                    return <Badge key={id} tone="ok">{item?.name || id}</Badge>;
                  })}
                  {!selectedPackageIds.length ? <p className="text-sm text-zinc-500">尚未选择默认软件。</p> : null}
                </div>
              </div>
            </div>
            <p className="mt-3 text-sm text-zinc-500">保存后会立即出现在客户端安装任务的“安装任务预设”下拉框中；预设不会包含清盘、格式化或磁盘设置。</p>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button variant="accent" onClick={savePreset} disabled={busy || !form.boot_target}>
                {busy ? "保存中" : "保存预设"}
              </Button>
              <Button variant="ghost" onClick={() => setCreateOpen(false)} disabled={busy}>取消</Button>
            </div>
            {softwarePickerOpen ? (
              <SoftwarePickerDialog
                selectedTarget={form.boot_target}
                softwareCatalog={softwareCatalog}
                selectedPackageIds={selectedPackageIds}
                onChange={setSelectedPackageIds}
                onClose={() => setSoftwarePickerOpen(false)}
              />
            ) : null}
          </div>
        ) : null}
        <div className="grid gap-3 lg:grid-cols-2">
          {presets.map((preset) => {
            const packages = (preset.software_package_ids || []).map((id) => softwareById.get(id)?.name || id);
            return (
              <div key={preset.id} className="rounded-lg border border-zinc-200 bg-zinc-50 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-zinc-950">{preset.name}</p>
                    <p className="mt-1 text-sm text-zinc-500">{preset.description || "未填写描述"}</p>
                  </div>
                  <Badge tone={preset.status === "archived" ? "warn" : preset.assignable ? "ok" : "warn"}>{preset.status === "archived" ? "已归档" : preset.assignable ? "可分配" : preset.review_status || "待审核"}</Badge>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Badge>{preset.os_family || "unknown"}</Badge>
                  <Badge>{preset.boot_target || "no target"}</Badge>
                  {(preset.software_profile_ids || []).map((id) => <Badge key={id} tone="ok">{id}</Badge>)}
                  {packages.map((name) => <Badge key={name} tone="ok">{name}</Badge>)}
                  {!packages.length && !(preset.software_profile_ids || []).length ? <Badge>无默认软件</Badge> : null}
                </div>
                <div className="mt-3 flex flex-wrap gap-2 border-t border-zinc-100 pt-3">
                  {preset.status === "archived" ? (
                    <Button size="sm" variant="outline" onClick={() => void updatePresetStatus(preset, "restore")} disabled={busy}>
                      恢复预设
                    </Button>
                  ) : (
                    <Button size="sm" variant="ghost" onClick={() => void updatePresetStatus(preset, "archive")} disabled={busy}>
                      归档预设
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
          {!presets.length ? <EmptyState title="暂无安装任务预设">后续在这里保存常用的系统和软件组合。</EmptyState> : null}
        </div>
      </Card>
    </div>
  );
}

function ClientsView({
  data,
  adminToken,
  setAdminToken,
  onRefresh,
}: {
  data: AppData;
  adminToken: string;
  setAdminToken: (token: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const clients = data.clients.sessions || [];
  const assignments = data.assignments || [];
  const softwareAssignmentCount = assignments.filter((assignment) => (assignment.resolved_software_plan?.variants || []).length > 0).length;
  const [tokenMessage, setTokenMessage] = useState("");
  const [assigningSessionId, setAssigningSessionId] = useState("");
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>([]);
  const [assignmentSessionIds, setAssignmentSessionIds] = useState<string[]>([]);
  const [assignmentOptions, setAssignmentOptions] = useState<AssignmentOptions | null>(null);
  const [selectedTarget, setSelectedTarget] = useState("");
  const [selectedInstallPresetId, setSelectedInstallPresetId] = useState("");
  const [selectedSoftwareProfileIds, setSelectedSoftwareProfileIds] = useState<string[]>([]);
  const [selectedSoftwarePackageIds, setSelectedSoftwarePackageIds] = useState<string[]>([]);
  const [softwarePickerOpen, setSoftwarePickerOpen] = useState(false);
  const [assignmentToken, setAssignmentToken] = useState("");
  const [assignBusy, setAssignBusy] = useState(false);
  const [assignMessage, setAssignMessage] = useState("");
  const targets = assignmentOptions?.boot_targets || data.clients.assignable_targets || [];
  const selectedTargetInfo = targets.find((target) => target.target === selectedTarget);
  const softwareAssignmentEnabled = Boolean(selectedTargetInfo?.software_assignment_enabled);
  const installPresets = selectedTarget ? assignmentOptions?.install_presets_by_target?.[selectedTarget] || [] : [];
  const selectedInstallPreset = installPresets.find((preset) => preset.id === selectedInstallPresetId);
  const selectedInstallPresetPackageNames = (selectedInstallPreset?.software_package_ids || [])
    .map((id) => data.software.find((item) => item.id === id)?.name || id);
  const assignmentClients = assignmentSessionIds.map((sessionId) => clients.find((client) => client.session_id === sessionId)).filter(Boolean);
  const targetSoftwareCatalog = selectedTarget ? assignmentOptions?.compatible_software_by_target?.[selectedTarget] : undefined;
  const softwareCatalog = targetSoftwareCatalog ?? (assignmentOptions?.compatible_software_packages?.length ? assignmentOptions.compatible_software_packages : data.software);
  const targetSoftwareProfiles = selectedTarget ? assignmentOptions?.compatible_software_profiles_by_target?.[selectedTarget] : undefined;
  const softwareProfiles = targetSoftwareProfiles ?? (assignmentOptions?.software_profiles || []);
  const compatibleProfiles = softwareProfiles.filter((profile) => {
    const targetFamily = osFamilyForTarget(selectedTarget);
    if (!targetFamily || !profile.assignable) return false;
    return profile.os_family === targetFamily || (targetFamily === "linux" && profile.os_family === "ubuntu");
  });
  const selectedProfiles = compatibleProfiles.filter((profile) => selectedSoftwareProfileIds.includes(profile.id));
  const selectedSoftware = softwareCatalog
    .filter((item) => selectedSoftwarePackageIds.includes(item.id))
    .map((item) => ({ item, variant: variantForTarget(item, selectedTarget) }))
    .filter((entry): entry is { item: SoftwarePackage; variant: SoftwareVariant } => Boolean(entry.variant));

  useEffect(() => {
    if (selectedTarget && !softwareAssignmentEnabled && softwarePickerOpen) {
      setSoftwarePickerOpen(false);
    }
    if (selectedTarget && !softwareAssignmentEnabled && selectedSoftwarePackageIds.length) {
      setSelectedSoftwarePackageIds([]);
      setSelectedSoftwareProfileIds([]);
      setSoftwarePickerOpen(false);
      setAssignMessage("当前启动目标还没有可验证的软件自动安装通道，已清空软件选择。");
      return;
    }
    if (selectedTarget && !softwareAssignmentEnabled && selectedSoftwareProfileIds.length) {
      setSelectedSoftwareProfileIds([]);
      return;
    }
    if (!selectedTarget) return;
    const targetFamily = osFamilyForTarget(selectedTarget);
    if (selectedSoftwareProfileIds.length) {
      const compatibleProfileIds = new Set(
        softwareProfiles
          .filter((profile) => profile.assignable && (profile.os_family === targetFamily || (targetFamily === "linux" && profile.os_family === "ubuntu")))
          .map((profile) => profile.id),
      );
      const nextProfileIds = selectedSoftwareProfileIds.filter((id) => compatibleProfileIds.has(id));
      if (nextProfileIds.length !== selectedSoftwareProfileIds.length) {
        setSelectedSoftwareProfileIds(nextProfileIds);
        setAssignMessage("目标系统已变化，已移除不兼容的软件集合。");
      }
    }
    if (!selectedSoftwarePackageIds.length) return;
    const compatiblePackageIds = new Set(
      softwareCatalog
        .filter((item) => {
          const variant = variantForTarget(item, selectedTarget);
          return Boolean(variant?.assignable);
        })
        .map((item) => item.id),
    );
    const nextPackageIds = selectedSoftwarePackageIds.filter((id) => compatiblePackageIds.has(id));
    if (nextPackageIds.length !== selectedSoftwarePackageIds.length) {
      setSelectedSoftwarePackageIds(nextPackageIds);
      setAssignMessage("目标系统已变化，已移除不兼容的软件选择。");
    }
  }, [selectedTarget, softwareAssignmentEnabled, softwarePickerOpen, selectedSoftwarePackageIds, selectedSoftwareProfileIds, softwareCatalog, softwareProfiles]);

  async function updateAdminToken() {
    setTokenMessage("");
    const token = window.prompt("请输入管理员 token", adminToken);
    if (token === null) return;
    const nextToken = token.trim();
    if (!nextToken) {
      storeAdminToken("", setAdminToken);
      setTokenMessage("已清除本地管理员 token。");
      await onRefresh();
      return;
    }
    try {
      const session = await validateAdminToken(nextToken);
      if (!session.authenticated) {
        setTokenMessage(session.admin_configured ? "管理员 token 无效。" : "后端尚未配置 SYNABOOT_ADMIN_TOKEN。");
        return;
      }
      storeAdminToken(nextToken, setAdminToken);
      setTokenMessage("管理员 token 已验证并保存到本机浏览器。");
      await onRefresh();
    } catch (cause) {
      setTokenMessage(cause instanceof Error ? cause.message : String(cause));
    }
  }

  function toggleSelectedSession(sessionId: string) {
    setSelectedSessionIds((current) => (current.includes(sessionId) ? current.filter((id) => id !== sessionId) : [...current, sessionId]));
  }

  function setAllOnlineSessions(checked: boolean) {
    setSelectedSessionIds(checked ? clients.filter((client) => client.online !== false).map((client) => client.session_id) : []);
  }

  async function openAssignmentPanel(sessionIds: string[]) {
    const normalizedSessionIds = Array.from(new Set(sessionIds.map((item) => item.trim()).filter(Boolean)));
    if (!normalizedSessionIds.length) {
      setAssignMessage("请先选择要分配安装任务的客户端。");
      return;
    }
    setAssigningSessionId(normalizedSessionIds[0]);
    setAssignmentSessionIds(normalizedSessionIds);
    setAssignmentOptions(null);
    setSelectedTarget("");
    setSelectedInstallPresetId("");
    setSelectedSoftwareProfileIds([]);
    setSelectedSoftwarePackageIds([]);
    setSoftwarePickerOpen(false);
    setAssignmentToken("");
    setAssignMessage("");
    let token = adminToken;
    if (!token) {
      token = window.prompt("请输入管理员 token")?.trim() || "";
    }
    if (!token) {
      setAssignMessage("已取消：分配客户端需要管理员 token。");
      return;
    }
    setAssignBusy(true);
    try {
      const session = await validateAdminToken(token);
      if (!session.authenticated) {
        setAssignMessage(session.admin_configured ? "管理员 token 无效。" : "后端尚未配置 SYNABOOT_ADMIN_TOKEN。");
        return;
      }
      storeAdminToken(token, setAdminToken);
      setAssignmentToken(token);
      const query = normalizedSessionIds.length === 1
        ? `session_id=${encodeURIComponent(normalizedSessionIds[0])}`
        : `session_ids=${encodeURIComponent(normalizedSessionIds.join(","))}`;
      const response = await fetch(`/api/assignment-options?${query}`, {
        cache: "no-store",
        headers: { "X-SynaBoot-Admin-Token": token },
      });
      const payload = (await response.json().catch(() => ({}))) as AssignmentOptions & { error?: string };
      if (!response.ok) throw new Error(payload.error || `/api/assignment-options ${response.status}`);
      setAssignmentOptions(payload);
      const defaultTarget = payload.boot_targets?.[0]?.target || "";
      setSelectedTarget(defaultTarget);
      const defaultPreset = defaultTarget ? payload.install_presets_by_target?.[defaultTarget]?.[0] : undefined;
      setSelectedInstallPresetId(defaultPreset?.id || "");
      if (!(payload.boot_targets?.length)) {
        setAssignMessage("当前没有可分配的启动目标，请先确认镜像已准备就绪。");
      }
    } catch (cause) {
      setAssignMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAssignBusy(false);
    }
  }

  async function submitAssignment() {
    if (!assignmentSessionIds.length || !selectedTarget) {
      setAssignMessage("请选择要分配的启动目标。");
      return;
    }
    if (!softwareAssignmentEnabled && (selectedSoftwarePackageIds.length || selectedSoftwareProfileIds.length)) {
      setAssignMessage("当前启动目标没有可验证的软件自动安装通道，请先清空软件选择或更换目标系统。");
      return;
    }
    setAssignBusy(true);
    setAssignMessage("");
    try {
      const token = assignmentToken || adminToken || window.localStorage.getItem("synaboot_admin_token") || "";
      await postAdmin(
        "/api/deployment-assignments",
        {
          session_id: assignmentSessionIds[0],
          session_ids: assignmentSessionIds,
          boot_target: selectedTarget,
          install_preset_id: selectedInstallPresetId,
          software_package_ids: selectedSoftwarePackageIds,
          software_profile_ids: selectedSoftwareProfileIds,
          software_variant_ids: [],
        },
        token,
      );
      setAssignMessage("分配已写入，客户端下一次等待室轮询会自动进入对应启动项。");
      setSelectedSessionIds((current) => current.filter((id) => !assignmentSessionIds.includes(id)));
      await onRefresh();
    } catch (cause) {
      setAssignMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAssignBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <SectionTitle eyebrow="clients" title="当前连接" />
          <strong className="text-3xl font-semibold text-zinc-950">{data.clients.summary?.online || 0}</strong>
          <p className="mt-2 text-sm text-zinc-500">PXE/HTTP 会话</p>
        </Card>
        <Card>
          <SectionTitle eyebrow="install" title="系统安装" />
          <strong className="text-3xl font-semibold text-zinc-950">{data.clients.summary?.assigned || 0}</strong>
          <p className="mt-2 text-sm text-zinc-500">已分配</p>
        </Card>
        <Card>
          <SectionTitle eyebrow="software" title="软件安装" />
          <strong className="text-3xl font-semibold text-zinc-950">{softwareAssignmentCount}</strong>
          <p className="mt-2 text-sm text-zinc-500">含软件计划的任务</p>
        </Card>
      </div>
      {adminToken ? (
        <Card>
          <SectionTitle eyebrow="deployment assignments" title="最近安装任务">
            展示后台已分配的系统和软件计划，以及客户端安装后 runner 回传的最新状态。
          </SectionTitle>
          <div className="grid gap-3">
            {assignments.slice(0, 6).map((assignment) => {
              const variants = assignment.resolved_software_plan?.variants || [];
              const events = assignment.recent_events || [];
              const summary = assignment.event_summary || {};
              return (
                <div key={assignment.id} className="rounded-lg border border-zinc-200 bg-white p-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-zinc-950">{assignment.boot_label || assignment.boot_target || "未命名任务"}</p>
                      <p className="mt-1 font-mono text-xs text-zinc-500">{assignment.id} · {(assignment.session_ids || [assignment.session_id]).filter(Boolean).length} 台客户端</p>
                    </div>
                    <Badge tone={summary.failed || summary.blocked ? "danger" : summary.completed ? "ok" : statusTone(assignment.status)}>{summary.last_status || assignment.status || "unknown"}</Badge>
                  </div>
                  {variants.length ? (
                    <div className="mt-3 grid gap-2">
                      {variants.map((variant) => {
                        const event = latestVariantEvent(events, variant.id);
                        return (
                          <div key={variant.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-zinc-100 bg-zinc-50 px-2.5 py-2">
                            <div>
                              <p className="text-sm font-medium text-zinc-900">{variant.package_name || variant.id}</p>
                              <p className="text-xs text-zinc-500">{variant.install_action || variant.installer_type || "installer"} · {installSourceLabel(variant)}</p>
                            </div>
                            <Badge tone={eventTone(event?.status)}>{eventLabel(event?.status)}</Badge>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="mt-2"><Badge>未选择自动安装软件</Badge></div>
                  )}
                  {summary.last_message ? (
                    <p className="mt-2 text-xs text-zinc-600">
                      {summary.last_stage || "event"} · {summary.last_message} · {formatTimestamp(summary.last_event_at)}
                    </p>
                  ) : (
                    <p className="mt-2 text-xs text-zinc-500">尚未收到安装后软件 runner 回调。</p>
                  )}
                  {events.length ? (
                    <div className="mt-3 border-t border-zinc-100 pt-2">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">最近回调</p>
                      <div className="mt-2 grid gap-1.5">
                        {events.slice(0, 4).map((event) => (
                          <div key={event.id} className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-600">
                            <span>{event.stage || "event"} · {eventLabel(event.status)} · {event.message || "-"}</span>
                            <span className="text-zinc-400">{formatTimestamp(event.created_at)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
            {!assignments.length ? <EmptyState title="暂无安装任务">给被动模式客户端创建安装任务后，这里会显示系统、软件和执行反馈。</EmptyState> : null}
          </div>
        </Card>
      ) : null}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <SectionTitle eyebrow="client sessions" title="客户端列表">
            {data.clients.access === "admin" ? "当前为管理员视图，显示完整客户端标识。" : "当前为脱敏视图，设置管理员 token 后显示完整客户端标识。"}
          </SectionTitle>
          <Button variant="outline" onClick={updateAdminToken}>{adminToken ? "更新管理员 token" : "设置管理员 token"}</Button>
        </div>
        {tokenMessage ? <p className="mb-3 rounded-md bg-zinc-50 px-3 py-2 text-sm text-zinc-700">{tokenMessage}</p> : null}
        {assigningSessionId ? (
          <div className="mb-4 rounded-lg border border-cyan-200 bg-cyan-50/60 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-medium text-zinc-950">分配本次安装任务</p>
                <p className="mt-1 text-sm text-zinc-600">
                  {assignmentSessionIds.length === 1
                    ? `${assignmentClients[0]?.mac || assignmentClients[0]?.uuid || assigningSessionId} · ${assignmentClients[0]?.ip || "no ip"}`
                    : `已选择 ${assignmentSessionIds.length} 台客户端，将创建同一批安装任务`}
                </p>
              </div>
              <Button size="sm" variant="ghost" onClick={() => { setAssigningSessionId(""); setAssignmentSessionIds([]); }}>关闭</Button>
            </div>
            {assignmentSessionIds.length > 1 ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {assignmentClients.map((client) => (
                  <Badge key={client?.session_id} tone="ok">{client?.mac || client?.uuid || client?.session_id}</Badge>
                ))}
              </div>
            ) : null}
            <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr]">
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">系统镜像/启动目标</span>
                <select
                  className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300"
                  value={selectedTarget}
                  onChange={(event) => {
                    const nextTarget = event.target.value;
                    const nextPreset = assignmentOptions?.install_presets_by_target?.[nextTarget]?.[0];
                    setSelectedTarget(nextTarget);
                    setSelectedInstallPresetId(nextPreset?.id || "");
                    setSelectedSoftwarePackageIds([]);
                    setSelectedSoftwareProfileIds([]);
                  }}
                  disabled={assignBusy}
                >
                  <option value="">请选择</option>
                  {targets.map((target) => (
                    <option key={target.target} value={target.target}>{target.label}</option>
                  ))}
                </select>
              </label>
              <div className="grid gap-3 rounded-md border border-zinc-200 bg-white p-3">
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-zinc-800">安装任务预设</span>
                  <select
                    className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300"
                    value={selectedInstallPresetId}
                    onChange={(event) => {
                      const presetId = event.target.value;
                      setSelectedInstallPresetId(presetId);
                    }}
                    disabled={assignBusy || !selectedTarget}
                  >
                    <option value="">不使用预设</option>
                    {installPresets.map((preset) => (
                      <option key={preset.id} value={preset.id}>{preset.name}</option>
                    ))}
                  </select>
                </label>
                {selectedInstallPreset ? (
                  <div className="rounded-md border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm text-cyan-900">
                    <p className="font-medium">{selectedInstallPreset.description || "该预设会带入默认任务组合。"}</p>
                    <p className="mt-1 text-xs">
                      软件 {selectedInstallPreset.software_package_ids?.length || 0} 个 · 软件集合 {selectedInstallPreset.software_profile_ids?.length || 0} 个
                    </p>
                    {selectedInstallPresetPackageNames.length ? (
                      <p className="mt-1 text-xs">默认软件：{selectedInstallPresetPackageNames.join("、")}</p>
                    ) : null}
                  </div>
                ) : null}
                <p className="text-sm text-zinc-500">安装预设只保存系统和软件组合；手动选择的软件会在预设基础上追加，不包含磁盘设置。</p>
              </div>
              <div className="rounded-md border border-zinc-200 bg-white p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-zinc-800">自动安装软件</p>
                    <p className="mt-1 text-sm text-zinc-500">
                      {softwareAssignmentEnabled ? "按目标系统匹配官方下载或官方软件源。" : (selectedTargetInfo?.postinstall_detail || "当前目标暂不支持自动软件安装。")}
                    </p>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => setSoftwarePickerOpen(true)} disabled={!selectedTarget || !softwareAssignmentEnabled}>
                    <PackagePlus className="h-4 w-4" />
                    选择软件
                  </Button>
                </div>
                {softwareAssignmentEnabled && compatibleProfiles.length ? (
                  <div className="mt-3 grid gap-2">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-700">默认软件集合</p>
                    {compatibleProfiles.map((profile) => {
                      const checked = selectedSoftwareProfileIds.includes(profile.id);
                      return (
                        <label key={profile.id} className={cn("flex cursor-pointer items-start gap-2 rounded-md border p-2 text-sm", checked ? "border-cyan-300 bg-cyan-50" : "border-zinc-200 bg-zinc-50")}>
                          <input
                            type="checkbox"
                            className="mt-1"
                            checked={checked}
                            onChange={(event) => {
                              setSelectedSoftwareProfileIds((current) =>
                                event.target.checked ? Array.from(new Set([...current, profile.id])) : current.filter((id) => id !== profile.id),
                              );
                            }}
                          />
                          <span>
                            <span className="font-medium text-zinc-900">{profile.name}</span>
                            <span className="mt-1 block text-xs text-zinc-500">{profile.description || "管理员预设的软件集合。"}</span>
                            <span className="mt-1 flex flex-wrap gap-1">
                              {(profile.variants || []).map((variant) => (
                                <Badge key={variant.id} tone={variant.assignable ? "ok" : "warn"}>{variant.package_name || variant.id}</Badge>
                              ))}
                            </span>
                          </span>
                        </label>
                      );
                    })}
                  </div>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {selectedProfiles.map((profile) => (
                    <span key={profile.id} className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800">
                      {profile.name}
                      <button className="ml-1 text-emerald-700 hover:text-zinc-950" onClick={() => setSelectedSoftwareProfileIds((current) => current.filter((id) => id !== profile.id))} type="button">
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                  {selectedSoftware.map(({ item, variant }) => {
                    return (
                      <span key={variant.id} className="inline-flex items-center gap-1 rounded-full border border-cyan-200 bg-cyan-50 px-2.5 py-1 text-xs font-medium text-cyan-800">
                        {item.name}
                        <span className="text-cyan-600">· {variantLabel(variant)}</span>
                        <button className="ml-1 text-cyan-700 hover:text-zinc-950" onClick={() => setSelectedSoftwarePackageIds((current) => current.filter((id) => id !== item.id))} type="button">
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    );
                  })}
                  {!selectedSoftware.length && !selectedProfiles.length ? <p className="text-sm text-zinc-500">{softwareAssignmentEnabled ? "尚未选择自动安装软件。" : "该目标仅创建系统启动/安装任务，不附带软件安装。"}</p> : null}
                </div>
              </div>
            </div>
            {softwarePickerOpen ? (
              <SoftwarePickerDialog
                selectedTarget={selectedTarget}
                softwareCatalog={softwareCatalog}
                selectedPackageIds={selectedSoftwarePackageIds}
                onChange={setSelectedSoftwarePackageIds}
                onClose={() => setSoftwarePickerOpen(false)}
              />
            ) : null}
            {assignmentOptions?.notes?.length ? (
              <div className="mt-3 grid gap-1 text-xs text-zinc-500">
                {assignmentOptions.notes.map((note) => <p key={note}>{note}</p>)}
              </div>
            ) : null}
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button variant="accent" onClick={submitAssignment} disabled={assignBusy || !selectedTarget}>
                {assignBusy ? "处理中" : "确认分配"}
              </Button>
              {assignMessage ? <p className="text-sm text-zinc-700">{assignMessage}</p> : null}
            </div>
          </div>
        ) : null}
        {clients.length ? (
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2">
            <p className="text-sm text-zinc-600">
              已选择 <span className="font-semibold text-zinc-950">{selectedSessionIds.length}</span> 台客户端用于批量装机任务。
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" onClick={() => setAllOnlineSessions(selectedSessionIds.length === 0)}>
                {selectedSessionIds.length ? "清空选择" : "选择在线客户端"}
              </Button>
              <Button size="sm" variant="accent" onClick={() => void openAssignmentPanel(selectedSessionIds)} disabled={!selectedSessionIds.length}>
                创建批量安装任务
              </Button>
            </div>
          </div>
        ) : null}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs uppercase text-zinc-500">
              <tr>
                <th className="py-2 pr-3 font-medium">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-zinc-300 text-cyan-600"
                    checked={clients.length > 0 && selectedSessionIds.length === clients.filter((client) => client.online !== false).length}
                    onChange={(event) => setAllOnlineSessions(event.target.checked)}
                    aria-label="选择全部在线客户端"
                  />
                </th>
                <th className="py-2 pr-3 font-medium">MAC</th>
                <th className="py-2 pr-3 font-medium">IP</th>
                <th className="py-2 pr-3 font-medium">分配目标</th>
                <th className="py-2 pr-3 font-medium">软件/进度</th>
                <th className="py-2 pr-3 font-medium">阶段</th>
                <th className="py-2 pr-3 font-medium">最后心跳</th>
                <th className="py-2 pr-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((client) => (
                <tr key={client.session_id} className="border-b border-zinc-100">
                  <td className="py-3 pr-3">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-zinc-300 text-cyan-600"
                      checked={selectedSessionIds.includes(client.session_id)}
                      onChange={() => toggleSelectedSession(client.session_id)}
                      aria-label={`选择客户端 ${client.mac || client.uuid || client.session_id}`}
                    />
                  </td>
                  <td className="py-3 pr-3 font-mono">{client.mac || "unknown"}</td>
                  <td className="py-3 pr-3 font-mono">{client.ip || "-"}</td>
                  <td className="py-3 pr-3">{client.selected_label || "等待分配"}</td>
                  <td className="py-3 pr-3">
                    {client.latest_assignment ? (
                      <div className="grid gap-1">
                        <div className="flex flex-wrap gap-1">
                          {(client.latest_assignment.software_labels || []).slice(0, 3).map((label) => (
                            <Badge key={label} tone="ok">{label}</Badge>
                          ))}
                          {client.latest_assignment.software_count ? null : <Badge>无自动软件</Badge>}
                        </div>
                        <p className="text-xs text-zinc-500">
                          {client.latest_assignment.event_summary?.last_status || client.latest_assignment.status || "assignment_received"}
                          {client.latest_assignment.event_summary?.last_message ? ` · ${client.latest_assignment.event_summary.last_message}` : ""}
                        </p>
                      </div>
                    ) : (
                      <span className="text-zinc-400">暂无任务</span>
                    )}
                  </td>
                  <td className="py-3 pr-3"><Badge tone={client.online ? "ok" : "warn"}>{client.state || "unknown"}</Badge></td>
                  <td className="py-3 pr-3">{formatTimestamp(client.last_seen_at)}</td>
                  <td className="py-3 pr-3">
                    <Button size="sm" variant="outline" onClick={() => void openAssignmentPanel([client.session_id])}>创建安装任务</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!clients.length ? <EmptyState title="暂无客户端会话">让客户机在 PXE 首屏选择被动安装后，这里会出现等待分配的会话。</EmptyState> : null}
      </Card>
    </div>
  );
}

function formatTimestamp(value?: number) {
  if (!value) return "-";
  return new Date(value * 1000).toLocaleString();
}

function SoftwarePickerDialog({
  selectedTarget,
  softwareCatalog,
  selectedPackageIds,
  onChange,
  onClose,
}: {
  selectedTarget: string;
  softwareCatalog: SoftwarePackage[];
  selectedPackageIds: string[];
  onChange: (ids: string[]) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const targetFamily = osFamilyForTarget(selectedTarget);
  const selectedItems = softwareCatalog
    .filter((item) => selectedPackageIds.includes(item.id))
    .map((item) => ({ item, variant: variantForTarget(item, selectedTarget) }))
    .filter((entry): entry is { item: SoftwarePackage; variant: SoftwareVariant } => Boolean(entry.variant));
  const filtered = softwareCatalog.filter((item) => {
    const text = `${item.name} ${item.vendor || ""} ${item.category || ""} ${item.description || ""}`.toLowerCase();
    const matchesText = !query.trim() || text.includes(query.trim().toLowerCase());
    const matchesCategory = !categoryFilter || item.category === categoryFilter;
    return matchesText && matchesCategory;
  });
  const categories = Array.from(new Set(softwareCatalog.map((item) => item.category).filter(Boolean)));

  function toggleSoftware(item: SoftwarePackage) {
    const variant = variantForTarget(item, selectedTarget);
    if (!variant?.assignable) return;
    onChange(selectedPackageIds.includes(item.id) ? selectedPackageIds.filter((id) => id !== item.id) : [...selectedPackageIds, item.id]);
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/40 px-4 py-6 backdrop-blur-sm">
      <div className="grid max-h-[88dvh] w-full max-w-7xl overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-2xl lg:grid-cols-[1fr_340px]">
        <section className="min-h-0 overflow-auto p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <SectionTitle eyebrow="software market" title="选择自动安装软件">
              当前目标系统：{targetFamily || "未识别"}。只允许勾选与目标系统兼容的软件版本。
            </SectionTitle>
            <Button variant="ghost" onClick={onClose}>
              <X className="h-4 w-4" />
              关闭
            </Button>
          </div>
          <div className="mb-4 grid gap-3 md:grid-cols-[1fr_180px_auto]">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
              <input
                className="min-h-10 w-full rounded-md border border-zinc-200 pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索软件、厂商或分类"
              />
            </label>
            <select className="min-h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
              <option value="">全部分类</option>
              {categories.map((category) => <option key={category} value={category}>{category}</option>)}
            </select>
            <Badge tone={selectedPackageIds.length ? "ok" : "muted"}>{selectedPackageIds.length} 个已选择</Badge>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map((item) => {
              const variant = variantForTarget(item, selectedTarget);
              const selected = selectedPackageIds.includes(item.id);
              const disabledReason = variant ? blockedReasonText(variant.blocked_reasons) : "当前系统没有兼容版本";
              return (
                <div
                  key={item.id}
                  className={cn(
                    "rounded-lg border bg-white p-4 shadow-sm transition-colors",
                    selected ? "border-cyan-400 ring-2 ring-cyan-100" : "border-zinc-200",
                    variant?.assignable ? "hover:border-cyan-300" : "opacity-60",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-zinc-950">{item.name}</p>
                      <p className="mt-0.5 text-xs text-zinc-500">{item.vendor} · {item.category}</p>
                    </div>
                    <button
                      type="button"
                      className={cn(
                        "grid h-8 w-8 shrink-0 place-items-center rounded-md border text-sm transition-colors",
                        selected ? "border-cyan-500 bg-cyan-500 text-zinc-950" : "border-zinc-200 bg-zinc-50 text-zinc-500",
                      )}
                      disabled={!variant?.assignable}
                      onClick={() => toggleSoftware(item)}
                      aria-label={selected ? `取消选择 ${item.name}` : `选择 ${item.name}`}
                    >
                      {selected ? <Check className="h-4 w-4" /> : null}
                    </button>
                  </div>
                  <p className="mt-3 min-h-10 text-sm leading-5 text-zinc-600">{item.description}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {variant ? (
                      <>
                        <Badge tone={variant.assignable ? "ok" : "warn"}>{variantLabel(variant)}</Badge>
                        <Badge>{installSourceLabel(variant)}</Badge>
                        <Badge>{variant.install_phase}</Badge>
                        <Badge tone={variant.review_status === "approved" ? "ok" : "warn"}>{variant.review_status}</Badge>
                      </>
                    ) : (
                      <Badge tone="warn">当前系统不可用</Badge>
                    )}
                  </div>
                  {!variant?.assignable ? <p className="mt-3 text-xs leading-5 text-amber-700">{disabledReason}</p> : null}
                </div>
              );
            })}
            {!filtered.length ? <EmptyState title="没有匹配的软件">调整关键词或分类后再查看。</EmptyState> : null}
          </div>
        </section>
        <aside className="min-h-0 overflow-auto border-t border-zinc-200 bg-zinc-50 p-5 lg:border-l lg:border-t-0">
          <SectionTitle eyebrow="selected" title="已选软件">
            这些软件会随本次安装任务自动匹配对应系统版本，客户端安装系统后从官方来源下载并执行。
          </SectionTitle>
          <div className="grid gap-2">
            {selectedItems.map(({ item, variant }) => {
              return (
                <div key={variant.id} className="rounded-md border border-zinc-200 bg-white p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-medium text-zinc-950">{item.name}</p>
                      <p className="mt-1 text-xs text-zinc-500">{`${variantLabel(variant)} · ${installSourceLabel(variant)}`}</p>
                    </div>
                    <button className="text-zinc-400 hover:text-zinc-950" onClick={() => onChange(selectedPackageIds.filter((id) => id !== item.id))} type="button">
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              );
            })}
            {!selectedItems.length ? <EmptyState title="尚未选择软件">在左侧勾选软件后，这里会持续显示本次任务的软件清单。</EmptyState> : null}
          </div>
          <Button className="mt-4 w-full" variant="accent" onClick={onClose}>
            确认软件选择
          </Button>
        </aside>
      </div>
    </div>
  );
}

function SoftwareView({
  packages,
  profiles,
  adminToken,
  setAdminToken,
  onRefresh,
}: {
  packages: SoftwarePackage[];
  profiles: SoftwareProfile[];
  adminToken: string;
  setAdminToken: (token: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [osFilter, setOsFilter] = useState("");
  const [variantBusy, setVariantBusy] = useState("");
  const [variantMessage, setVariantMessage] = useState("");
  const [editingVariant, setEditingVariant] = useState<SoftwareVariant | null>(null);
  const [variantForm, setVariantForm] = useState<Record<string, string>>({});
  const [createPanel, setCreatePanel] = useState<"" | "package" | "variant" | "profile">("");
  const [packageForm, setPackageForm] = useState<Record<string, string>>({
    id: "",
    name: "",
    vendor: "",
    category: "",
    description: "",
    homepage_url: "",
    icon_key: "",
  });
  const [newVariantForm, setNewVariantForm] = useState<Record<string, string>>({
    package_id: "",
    id: "",
    os_family: "ubuntu",
    installer_type: "apt",
    official_source_url: "",
    download_url: "",
    source_policy: "official_package_repo",
    signature_policy: "repo_signed",
    install_action: "apt_package",
    package_name: "",
    silent_args: "",
    default_for_os: "",
    selection_priority: "0",
    risk_level: "medium",
    notes: "",
  });
  const [profileForm, setProfileForm] = useState<{ id: string; name: string; description: string; os_family: string; risk_level: string; variant_ids: string[] }>({
    id: "",
    name: "",
    description: "",
    os_family: "ubuntu",
    risk_level: "medium",
    variant_ids: [],
  });
  const filtered = packages.filter((item) => {
    const text = `${item.name} ${item.vendor || ""} ${item.category || ""} ${item.description || ""}`.toLowerCase();
    const matchesText = !query.trim() || text.includes(query.trim().toLowerCase());
    const matchesOs = !osFilter || item.variants?.some((variant) => variant.os_family === osFilter);
    return matchesText && matchesOs;
  });
  const variantCount = packages.reduce((count, item) => count + (item.variants?.length || 0), 0);
  const assignableCount = packages.reduce((count, item) => count + (item.variants || []).filter((variant) => variant.assignable).length, 0);
  const assignableVariants = packages.flatMap((item) => (item.variants || []).filter((variant) => variant.assignable).map((variant) => ({ ...variant, package_name_label: item.name })));
  const profileVariantOptions = assignableVariants.filter((variant) => variant.os_family === profileForm.os_family);

  async function softwareAdminToken() {
    let token = adminToken;
    if (!token) {
      token = window.prompt("请输入管理员 token")?.trim() || "";
    }
    if (!token) throw new Error("已取消：维护软件市场需要管理员 token。");
    const session = await validateAdminToken(token);
    if (!session.authenticated) {
      throw new Error(session.admin_configured ? "管理员 token 无效。" : "后端尚未配置 SYNABOOT_ADMIN_TOKEN。");
    }
    storeAdminToken(token, setAdminToken);
    return token;
  }

  async function updateVariantReview(variant: SoftwareVariant, payload: Record<string, unknown>) {
    setVariantMessage("");
    setVariantBusy(variant.id);
    try {
      const token = await softwareAdminToken();
      const updated = await postAdmin<SoftwareVariant>(`/api/software-variants/${encodeURIComponent(variant.id)}/review`, payload, token);
      const state = updated.assignable ? "可进入自动安装任务" : `仍不可选：${blockedReasonText(updated.blocked_reasons)}`;
      setVariantMessage(`${variantLabel(updated)} 已更新，${state}。`);
      await onRefresh();
    } catch (cause) {
      setVariantMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setVariantBusy("");
    }
  }

  async function updatePackageStatus(item: SoftwarePackage, action: "archive" | "restore") {
    setVariantMessage("");
    setVariantBusy(`package-${item.id}`);
    try {
      const token = await softwareAdminToken();
      const updated = await postAdmin<SoftwarePackage>(`/api/software-packages/${encodeURIComponent(item.id)}/${action}`, {}, token);
      setVariantMessage(`${updated.name} 已${action === "archive" ? "归档" : "恢复"}。归档应用不会出现在创建安装任务的软件选择中。`);
      await onRefresh();
    } catch (cause) {
      setVariantMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setVariantBusy("");
    }
  }

  async function updateProfileStatus(profile: SoftwareProfile, action: "archive" | "restore") {
    setVariantMessage("");
    setVariantBusy(`profile-${profile.id}`);
    try {
      const token = await softwareAdminToken();
      const updated = await postAdmin<SoftwareProfile>(`/api/software-profiles/${encodeURIComponent(profile.id)}/${action}`, {}, token);
      setVariantMessage(`${updated.name} 已${action === "archive" ? "归档" : "恢复"}。归档集合不会出现在创建安装任务的软件集合中。`);
      await onRefresh();
    } catch (cause) {
      setVariantMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setVariantBusy("");
    }
  }

  async function saveNewPackage() {
    setVariantMessage("");
    setVariantBusy("create-package");
    try {
      const token = await softwareAdminToken();
      const created = await postAdmin<SoftwarePackage>(
        "/api/software-packages",
        {
          id: (packageForm.id || "").trim(),
          name: (packageForm.name || "").trim(),
          vendor: (packageForm.vendor || "").trim(),
          category: (packageForm.category || "").trim(),
          description: (packageForm.description || "").trim(),
          homepage_url: (packageForm.homepage_url || "").trim(),
          icon_key: (packageForm.icon_key || packageForm.id || "").trim(),
        },
        token,
      );
      setVariantMessage(`${created.name} 已创建。请继续新增系统版本并完成来源审核。`);
      setPackageForm({ id: "", name: "", vendor: "", category: "", description: "", homepage_url: "", icon_key: "" });
      setNewVariantForm((current) => ({ ...current, package_id: created.id }));
      setCreatePanel("variant");
      await onRefresh();
    } catch (cause) {
      setVariantMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setVariantBusy("");
    }
  }

  async function saveNewVariant() {
    setVariantMessage("");
    setVariantBusy("create-variant");
    try {
      const token = await softwareAdminToken();
      const packageId = (newVariantForm.package_id || "").trim();
      const created = await postAdmin<SoftwareVariant>(
        `/api/software-packages/${encodeURIComponent(packageId)}/variants`,
        {
          id: (newVariantForm.id || "").trim(),
          os_family: newVariantForm.os_family || "ubuntu",
          installer_type: (newVariantForm.installer_type || "").trim(),
          official_source_url: (newVariantForm.official_source_url || "").trim(),
          download_url: (newVariantForm.download_url || "").trim(),
          source_policy: newVariantForm.source_policy || "official_vendor",
          signature_policy: newVariantForm.signature_policy || "vendor_signed",
          install_action: newVariantForm.install_action || "official_download",
          package_name: (newVariantForm.package_name || "").trim(),
          silent_args: (newVariantForm.silent_args || "").trim(),
          default_for_os: newVariantForm.default_for_os === "true",
          selection_priority: Number(newVariantForm.selection_priority || 0),
          risk_level: newVariantForm.risk_level || "medium",
          notes: (newVariantForm.notes || "").trim(),
        },
        token,
      );
      setVariantMessage(`${variantLabel(created)} 已创建，默认需要审核；审核通过且 runner 支持后才能进入安装任务。`);
      setNewVariantForm({
        package_id: packageId,
        id: "",
        os_family: "ubuntu",
        installer_type: "apt",
        official_source_url: "",
        download_url: "",
        source_policy: "official_package_repo",
        signature_policy: "repo_signed",
        install_action: "apt_package",
        package_name: "",
        silent_args: "",
        default_for_os: "",
        selection_priority: "0",
        risk_level: "medium",
        notes: "",
      });
      await onRefresh();
    } catch (cause) {
      setVariantMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setVariantBusy("");
    }
  }

  async function saveNewProfile() {
    setVariantMessage("");
    setVariantBusy("create-profile");
    try {
      const token = await softwareAdminToken();
      const created = await postAdmin<SoftwareProfile>(
        "/api/software-profiles",
        {
          id: profileForm.id.trim(),
          name: profileForm.name.trim(),
          description: profileForm.description.trim(),
          os_family: profileForm.os_family || "ubuntu",
          risk_level: profileForm.risk_level || "medium",
          variant_ids: profileForm.variant_ids,
        },
        token,
      );
      setVariantMessage(`${created.name} 已创建，可在客户端创建安装任务时作为默认软件集合选择。`);
      setProfileForm({ id: "", name: "", description: "", os_family: "ubuntu", risk_level: "medium", variant_ids: [] });
      await onRefresh();
    } catch (cause) {
      setVariantMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setVariantBusy("");
    }
  }

  function toggleProfileVariant(variantId: string) {
    setProfileForm((current) => ({
      ...current,
      variant_ids: current.variant_ids.includes(variantId) ? current.variant_ids.filter((id) => id !== variantId) : [...current.variant_ids, variantId],
    }));
  }

  function openVariantEditor(variant: SoftwareVariant) {
    setEditingVariant(variant);
    setVariantForm({
      official_source_url: variant.official_source_url || "",
      download_url: variant.download_url || "",
      source_policy: variant.source_policy || "official_vendor",
      signature_policy: variant.signature_policy || "vendor_signed",
      install_action: variant.install_action || "official_download",
      installer_type: variant.installer_type || "",
      silent_args: variant.silent_args || "",
      sha256: variant.sha256 || "",
      package_name: variant.package_name || "",
      default_for_os: variant.default_for_os ? "true" : "",
      selection_priority: String(variant.selection_priority || 0),
      risk_level: variant.risk_level || "medium",
      notes: variant.notes || "",
    });
  }

  async function saveVariantMetadata() {
    if (!editingVariant) return;
    setVariantMessage("");
    setVariantBusy(editingVariant.id);
    try {
      const token = await softwareAdminToken();
      const payload = {
        official_source_url: (variantForm.official_source_url || "").trim(),
        download_url: (variantForm.download_url || "").trim(),
        source_policy: variantForm.source_policy || "official_vendor",
        signature_policy: variantForm.signature_policy || "vendor_signed",
        install_action: variantForm.install_action || "official_download",
        installer_type: (variantForm.installer_type || "").trim(),
        silent_args: (variantForm.silent_args || "").trim(),
        sha256: (variantForm.sha256 || "").trim(),
        package_name: (variantForm.package_name || "").trim(),
        default_for_os: variantForm.default_for_os === "true",
        selection_priority: Number(variantForm.selection_priority || 0),
        risk_level: variantForm.risk_level || "medium",
        notes: (variantForm.notes || "").trim(),
      };
      const updated = await postAdmin<SoftwareVariant>(`/api/software-variants/${encodeURIComponent(editingVariant.id)}/review`, payload, token);
      const state = updated.assignable ? "可进入自动安装任务" : `仍不可选：${blockedReasonText(updated.blocked_reasons)}`;
      setVariantMessage(`${variantLabel(updated)} 来源信息已保存，${state}。`);
      setEditingVariant(null);
      await onRefresh();
    } catch (cause) {
      setVariantMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setVariantBusy("");
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <SectionTitle eyebrow="market" title="软件市场" />
          <strong className="text-3xl font-semibold text-zinc-950">{packages.length}</strong>
          <p className="mt-2 text-sm text-zinc-500">可选应用</p>
        </Card>
        <Card>
          <SectionTitle eyebrow="variants" title="系统版本" />
          <strong className="text-3xl font-semibold text-zinc-950">{variantCount}</strong>
          <p className="mt-2 text-sm text-zinc-500">Windows / Ubuntu</p>
        </Card>
        <Card>
          <SectionTitle eyebrow="approved" title="可自动安装" />
          <strong className="text-3xl font-semibold text-zinc-950">{assignableCount}</strong>
          <p className="mt-2 text-sm text-zinc-500">已通过来源审查</p>
        </Card>
        <Card>
          <SectionTitle eyebrow="profiles" title="软件集合" />
          <strong className="text-3xl font-semibold text-zinc-950">{profiles.length}</strong>
          <p className="mt-2 text-sm text-zinc-500">可用于批量任务</p>
        </Card>
      </div>
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <SectionTitle eyebrow="app catalog" title="应用目录">SynaBoot 不托管第三方安装包，只保存官网/官方源链接、脚本模板和校验规则。</SectionTitle>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => setCreatePanel(createPanel === "package" ? "" : "package")}>
              <PackagePlus className="h-4 w-4" />
              新增应用
            </Button>
            <Button size="sm" variant="outline" onClick={() => setCreatePanel(createPanel === "variant" ? "" : "variant")}>
              <Boxes className="h-4 w-4" />
              新增系统版本
            </Button>
            <Button size="sm" variant="outline" onClick={() => setCreatePanel(createPanel === "profile" ? "" : "profile")}>
              <Check className="h-4 w-4" />
              新增软件集合
            </Button>
          </div>
        </div>
        <p className="mb-3 text-xs leading-5 text-zinc-500">
          归档不是删除，不影响历史安装任务和审计记录；归档后的应用或软件集合只会退出新的创建安装任务选择范围。
        </p>
        {variantMessage ? <p className="mb-3 rounded-md bg-zinc-50 px-3 py-2 text-sm text-zinc-700">{variantMessage}</p> : null}
        {createPanel === "package" ? (
          <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50/60 p-4">
            <SectionTitle eyebrow="new app" title="新增应用">这里只创建应用目录 metadata，不上传第三方安装包。</SectionTitle>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">应用 ID</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={packageForm.id || ""} onChange={(event) => setPackageForm((current) => ({ ...current, id: event.target.value }))} placeholder="例如 feishu" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">应用名称</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={packageForm.name || ""} onChange={(event) => setPackageForm((current) => ({ ...current, name: event.target.value }))} placeholder="例如 飞书" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">厂商</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={packageForm.vendor || ""} onChange={(event) => setPackageForm((current) => ({ ...current, vendor: event.target.value }))} />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">分类</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={packageForm.category || ""} onChange={(event) => setPackageForm((current) => ({ ...current, category: event.target.value }))} placeholder="协作 / 浏览器 / 运维" />
              </label>
              <label className="grid gap-1 text-sm md:col-span-2">
                <span className="font-medium text-zinc-800">官网 URL</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={packageForm.homepage_url || ""} onChange={(event) => setPackageForm((current) => ({ ...current, homepage_url: event.target.value }))} placeholder="https://vendor.example/" />
              </label>
              <label className="grid gap-1 text-sm md:col-span-2">
                <span className="font-medium text-zinc-800">说明</span>
                <textarea className="min-h-20 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={packageForm.description || ""} onChange={(event) => setPackageForm((current) => ({ ...current, description: event.target.value }))} />
              </label>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button variant="accent" onClick={() => void saveNewPackage()} disabled={variantBusy === "create-package"}>创建应用</Button>
              <p className="text-xs text-zinc-500">创建后还需要新增对应 Windows / Ubuntu 系统版本。</p>
            </div>
          </div>
        ) : null}
        {createPanel === "variant" ? (
          <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50/60 p-4">
            <SectionTitle eyebrow="new variant" title="新增系统版本">保存官方来源、安装动作和校验策略；新增后默认需要审核。</SectionTitle>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">所属应用</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.package_id || ""} onChange={(event) => setNewVariantForm((current) => ({ ...current, package_id: event.target.value }))}>
                  <option value="">请选择应用</option>
                  {packages.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">版本 ID</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.id || ""} onChange={(event) => setNewVariantForm((current) => ({ ...current, id: event.target.value }))} placeholder="例如 feishu-ubuntu-amd64" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">系统</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.os_family || "ubuntu"} onChange={(event) => setNewVariantForm((current) => ({ ...current, os_family: event.target.value }))}>
                  <option value="ubuntu">Ubuntu</option>
                  <option value="windows">Windows</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">安装动作</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.install_action || "official_download"} onChange={(event) => {
                  const action = event.target.value;
                  setNewVariantForm((current) => ({ ...current, install_action: action, installer_type: installerTypeForAction(action) }));
                }}>
                  <option value="official_download">仅记录官方下载页</option>
                  <option value="apt_package">Ubuntu 官方 apt 包</option>
                  <option value="download_deb">下载官方 deb</option>
                  <option value="msi_install">Windows MSI</option>
                  <option value="exe_install">Windows EXE 静默安装</option>
                  <option value="office_odt_install">Office Deployment Tool</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">安装器类型</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.installer_type || ""} onChange={(event) => setNewVariantForm((current) => ({ ...current, installer_type: event.target.value }))} placeholder="apt / deb / msi / exe" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">包名</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 font-mono text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.package_name || ""} onChange={(event) => setNewVariantForm((current) => ({ ...current, package_name: event.target.value }))} placeholder="apt 包名或 Office 产品 ID" />
              </label>
              <label className="grid gap-1 text-sm md:col-span-2">
                <span className="font-medium text-zinc-800">静默安装参数</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 font-mono text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.silent_args || ""} onChange={(event) => setNewVariantForm((current) => ({ ...current, silent_args: event.target.value }))} placeholder="例如 /quiet /norestart；apt/deb 可留空" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">默认版本</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.default_for_os || ""} onChange={(event) => setNewVariantForm((current) => ({ ...current, default_for_os: event.target.value }))}>
                  <option value="">否</option>
                  <option value="true">作为该系统默认版本</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">选择优先级</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 font-mono text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.selection_priority || "0"} onChange={(event) => setNewVariantForm((current) => ({ ...current, selection_priority: event.target.value }))} placeholder="0-1000，数字越大越优先" />
              </label>
              <label className="grid gap-1 text-sm md:col-span-2">
                <span className="font-medium text-zinc-800">官方来源 URL</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.official_source_url || ""} onChange={(event) => setNewVariantForm((current) => ({ ...current, official_source_url: event.target.value }))} placeholder="https://vendor.example/download" />
              </label>
              <label className="grid gap-1 text-sm md:col-span-2">
                <span className="font-medium text-zinc-800">安装器下载 URL</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.download_url || ""} onChange={(event) => setNewVariantForm((current) => ({ ...current, download_url: event.target.value }))} placeholder="download_deb / msi_install / office_odt_install 必填；apt_package 可留空" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">来源策略</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.source_policy || "official_vendor"} onChange={(event) => setNewVariantForm((current) => ({ ...current, source_policy: event.target.value }))}>
                  <option value="official_vendor">官方厂商</option>
                  <option value="official_package_repo">官方软件源</option>
                  <option value="approved_enterprise_mirror">企业批准镜像源</option>
                  <option value="admin_reviewed_download">管理员审核直链</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">校验策略</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={newVariantForm.signature_policy || "vendor_signed"} onChange={(event) => setNewVariantForm((current) => ({ ...current, signature_policy: event.target.value }))}>
                  <option value="vendor_signed">厂商签名</option>
                  <option value="repo_signed">仓库签名</option>
                  <option value="sha256_required">要求 sha256</option>
                </select>
              </label>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button variant="accent" onClick={() => void saveNewVariant()} disabled={variantBusy === "create-variant"}>创建系统版本</Button>
              <p className="text-xs text-zinc-500">新增版本默认需要审核；Windows 可使用管理员审核的安装器直链，不需要正式软件源；不保存第三方安装包，不执行任意命令。</p>
            </div>
          </div>
        ) : null}
        {createPanel === "profile" ? (
          <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50/60 p-4">
            <SectionTitle eyebrow="new profile" title="新增软件集合">集合只引用已审核、可自动安装的软件版本，不新增下载源，也不保存第三方安装包。</SectionTitle>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">集合 ID</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={profileForm.id} onChange={(event) => setProfileForm((current) => ({ ...current, id: event.target.value }))} placeholder="例如 ubuntu-office-basic" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">集合名称</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={profileForm.name} onChange={(event) => setProfileForm((current) => ({ ...current, name: event.target.value }))} placeholder="例如 Ubuntu 办公基础包" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">适用系统</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={profileForm.os_family} onChange={(event) => setProfileForm((current) => ({ ...current, os_family: event.target.value, variant_ids: [] }))}>
                  <option value="ubuntu">Ubuntu</option>
                  <option value="windows">Windows</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">风险等级</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={profileForm.risk_level} onChange={(event) => setProfileForm((current) => ({ ...current, risk_level: event.target.value }))}>
                  <option value="low">低</option>
                  <option value="medium">中</option>
                  <option value="high">高</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm md:col-span-2">
                <span className="font-medium text-zinc-800">说明</span>
                <textarea className="min-h-20 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={profileForm.description} onChange={(event) => setProfileForm((current) => ({ ...current, description: event.target.value }))} />
              </label>
            </div>
            <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {profileVariantOptions.map((variant) => {
                const checked = profileForm.variant_ids.includes(variant.id);
                return (
                  <label key={variant.id} className={cn("flex cursor-pointer items-start gap-2 rounded-md border bg-white p-3 text-sm", checked ? "border-cyan-300 ring-2 ring-cyan-100" : "border-zinc-200")}>
                    <input className="mt-1 h-4 w-4 accent-cyan-600" type="checkbox" checked={checked} onChange={() => toggleProfileVariant(variant.id)} />
                    <span>
                      <span className="block font-medium text-zinc-900">{variant.package_name_label}</span>
                      <span className="mt-1 block text-xs text-zinc-500">{variantLabel(variant)} · {installSourceLabel(variant)}</span>
                      {variant.package_name ? <span className="mt-1 block font-mono text-[11px] text-zinc-500">包/产品: {variant.package_name}</span> : null}
                    </span>
                  </label>
                );
              })}
              {!profileVariantOptions.length ? <EmptyState title="暂无可加入集合的软件">先审核通过对应系统的软件版本后，再创建软件集合。</EmptyState> : null}
            </div>
            {profileForm.variant_ids.length ? (
              <p className="mt-3 text-sm text-cyan-800">已选 {profileForm.variant_ids.length} 个软件版本：{profileForm.variant_ids.join("、")}</p>
            ) : null}
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button variant="accent" onClick={() => void saveNewProfile()} disabled={variantBusy === "create-profile"}>创建软件集合</Button>
              <p className="text-xs text-zinc-500">创建后可在客户端任务面板中与系统镜像一起分配。</p>
            </div>
          </div>
        ) : null}
        {profiles.length ? (
          <div className="mb-4 rounded-lg border border-zinc-200 bg-zinc-50 p-4">
            <SectionTitle eyebrow="profiles" title="现有软件集合">用于快速给单台或批量客户端分配默认软件。</SectionTitle>
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {profiles.map((profile) => (
                <div key={profile.id} className="rounded-md border border-zinc-200 bg-white p-3 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold text-zinc-950">{profile.name}</p>
                      <p className="mt-1 text-xs text-zinc-500">{profile.os_family} · {(profile.variants || []).length} 个软件</p>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      <Badge tone={profile.assignable ? "ok" : "warn"}>{profile.status === "archived" ? "已归档" : profile.assignable ? "可分配" : "需检查"}</Badge>
                      {profile.status === "archived" ? (
                        <Button size="sm" variant="ghost" onClick={() => void updateProfileStatus(profile, "restore")} disabled={variantBusy === `profile-${profile.id}`}>
                          恢复
                        </Button>
                      ) : (
                        <Button size="sm" variant="ghost" onClick={() => void updateProfileStatus(profile, "archive")} disabled={variantBusy === `profile-${profile.id}`}>
                          归档
                        </Button>
                      )}
                    </div>
                  </div>
                  {profile.description ? <p className="mt-2 text-xs leading-5 text-zinc-600">{profile.description}</p> : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}
        {editingVariant ? (
          <div className="mb-4 rounded-lg border border-cyan-200 bg-cyan-50/60 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <SectionTitle eyebrow="variant source" title="维护软件来源">
                {variantLabel(editingVariant)}。这里只保存来源链接、安装器直链和安装元数据，不上传安装包。
              </SectionTitle>
              <Button size="sm" variant="ghost" onClick={() => setEditingVariant(null)}>
                <X className="h-4 w-4" />
                关闭
              </Button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">安装动作</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.install_action || "official_download"} onChange={(event) => {
                  const action = event.target.value;
                  setVariantForm((current) => ({ ...current, install_action: action, installer_type: installerTypeForAction(action) }));
                }}>
                  <option value="official_download">仅记录官方下载页</option>
                  <option value="apt_package">Ubuntu 官方 apt 包</option>
                  <option value="download_deb">下载官方 deb</option>
                  <option value="msi_install">Windows MSI</option>
                  <option value="exe_install">Windows EXE 静默安装</option>
                  <option value="office_odt_install">Office Deployment Tool</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">安装器类型</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 font-mono text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.installer_type || ""} onChange={(event) => setVariantForm((current) => ({ ...current, installer_type: event.target.value }))} placeholder="apt / deb / msi / exe / office_odt" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">官方来源 URL</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.official_source_url || ""} onChange={(event) => setVariantForm((current) => ({ ...current, official_source_url: event.target.value }))} placeholder="https://vendor.example/download" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">安装器下载 URL</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.download_url || ""} onChange={(event) => setVariantForm((current) => ({ ...current, download_url: event.target.value }))} placeholder="download_deb / msi_install / exe_install / office_odt_install 必填；apt_package 可留空" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">来源策略</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.source_policy || "official_vendor"} onChange={(event) => setVariantForm((current) => ({ ...current, source_policy: event.target.value }))}>
                  <option value="official_vendor">官方厂商</option>
                  <option value="official_package_repo">官方软件源</option>
                  <option value="approved_enterprise_mirror">企业批准镜像源</option>
                  <option value="admin_reviewed_download">管理员审核直链</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">校验策略</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.signature_policy || "vendor_signed"} onChange={(event) => setVariantForm((current) => ({ ...current, signature_policy: event.target.value }))}>
                  <option value="vendor_signed">厂商签名</option>
                  <option value="repo_signed">仓库签名</option>
                  <option value="sha256_required">要求 sha256</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">sha256</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 font-mono text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.sha256 || ""} onChange={(event) => setVariantForm((current) => ({ ...current, sha256: event.target.value }))} placeholder="可留空，sha256_required 时必须填写" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">Ubuntu apt 包名</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 font-mono text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.package_name || ""} onChange={(event) => setVariantForm((current) => ({ ...current, package_name: event.target.value }))} placeholder="例如 curl 或 ProPlus2024Volume" />
              </label>
              <label className="grid gap-1 text-sm md:col-span-2">
                <span className="font-medium text-zinc-800">静默安装参数</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 font-mono text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.silent_args || ""} onChange={(event) => setVariantForm((current) => ({ ...current, silent_args: event.target.value }))} placeholder="例如 /quiet /norestart；只允许安全字符，不支持任意命令" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">默认版本</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.default_for_os || ""} onChange={(event) => setVariantForm((current) => ({ ...current, default_for_os: event.target.value }))}>
                  <option value="">否</option>
                  <option value="true">作为该系统默认版本</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">选择优先级</span>
                <input className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 font-mono text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.selection_priority || "0"} onChange={(event) => setVariantForm((current) => ({ ...current, selection_priority: event.target.value }))} placeholder="0-1000，数字越大越优先" />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-zinc-800">风险等级</span>
                <select className="min-h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.risk_level || "medium"} onChange={(event) => setVariantForm((current) => ({ ...current, risk_level: event.target.value }))}>
                  <option value="low">低</option>
                  <option value="medium">中</option>
                  <option value="high">高</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm md:col-span-2">
                <span className="font-medium text-zinc-800">审核备注</span>
                <textarea className="min-h-24 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={variantForm.notes || ""} onChange={(event) => setVariantForm((current) => ({ ...current, notes: event.target.value }))} />
              </label>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button variant="accent" onClick={() => void saveVariantMetadata()} disabled={variantBusy === editingVariant.id}>
                保存来源信息
              </Button>
              <p className="text-xs text-zinc-500">保存后仍需满足审核状态、签名策略和 runner 支持，才会进入创建任务的软件选择。</p>
            </div>
          </div>
        ) : null}
        <div className="mb-4 grid gap-3 md:grid-cols-[1fr_180px]">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
            <input
              className="min-h-10 w-full rounded-md border border-zinc-200 pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索软件、厂商或分类"
            />
          </label>
          <select className="min-h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={osFilter} onChange={(event) => setOsFilter(event.target.value)}>
            <option value="">全部系统</option>
            <option value="windows">Windows</option>
            <option value="ubuntu">Ubuntu</option>
          </select>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {filtered.map((item) => (
            <div key={item.id} className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold text-zinc-950">{item.name}</p>
                  <p className="mt-0.5 text-xs text-zinc-500">{item.vendor} · {item.category}</p>
                </div>
                <Badge tone={item.status === "archived" ? "warn" : "ok"}>{item.status === "archived" ? "已归档" : "可用"}</Badge>
              </div>
              <p className="mt-3 min-h-10 text-sm leading-5 text-zinc-600">{item.description}</p>
              {item.homepage_url ? (
                <a className="mt-3 inline-flex text-xs font-medium text-cyan-700 hover:text-cyan-900" href={item.homepage_url} target="_blank" rel="noreferrer">
                  官方主页
                </a>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-1.5">
                {(item.variants || []).map((variant) => (
                  <Badge key={variant.id} tone={variant.assignable ? "ok" : "warn"}>{variantLabel(variant)}</Badge>
                ))}
              </div>
              <div className="mt-3 grid gap-2">
                {(item.variants || []).map((variant) => (
                  <div key={variant.id} className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-xs text-zinc-600">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium text-zinc-800">{variantLabel(variant)}</span>
                      <Badge tone={variant.assignable ? "ok" : "warn"}>{variant.review_status || "unknown"}</Badge>
                    </div>
                    <p className="mt-1">{installSourceLabel(variant)} · {variant.install_phase}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {variant.default_for_os ? <Badge tone="ok">默认版本</Badge> : null}
                      <Badge>优先级 {variant.selection_priority || 0}</Badge>
                    </div>
                    {variant.package_name ? <p className="mt-1 font-mono text-[11px] text-zinc-500">包/产品: {variant.package_name}</p> : null}
                    {!variant.assignable ? <p className="mt-1 text-amber-700">{blockedReasonText(variant.blocked_reasons)}</p> : null}
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Button size="sm" variant="outline" onClick={() => openVariantEditor(variant)} disabled={variantBusy === variant.id}>
                        维护来源
                      </Button>
                      {variant.review_status === "approved" ? (
                        <Button size="sm" variant="outline" onClick={() => void updateVariantReview(variant, { review_status: "needs_review" })} disabled={variantBusy === variant.id}>
                          退回审核
                        </Button>
                      ) : (
                        <Button size="sm" variant="outline" onClick={() => void updateVariantReview(variant, { review_status: "approved", enabled: true })} disabled={variantBusy === variant.id}>
                          批准自动安装
                        </Button>
                      )}
                      {variant.enabled === false ? (
                        <Button size="sm" variant="ghost" onClick={() => void updateVariantReview(variant, { enabled: true })} disabled={variantBusy === variant.id}>
                          启用
                        </Button>
                      ) : (
                        <Button size="sm" variant="ghost" onClick={() => void updateVariantReview(variant, { enabled: false })} disabled={variantBusy === variant.id}>
                          禁用
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-3 border-t border-zinc-100 pt-3">
                {item.status === "archived" ? (
                  <Button size="sm" variant="outline" onClick={() => void updatePackageStatus(item, "restore")} disabled={variantBusy === `package-${item.id}`}>
                    恢复应用
                  </Button>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => void updatePackageStatus(item, "archive")} disabled={variantBusy === `package-${item.id}`}>
                    归档应用
                  </Button>
                )}
              </div>
            </div>
          ))}
          {!filtered.length ? <EmptyState title="没有匹配的软件">调整搜索或系统筛选后再查看。</EmptyState> : null}
        </div>
        {!packages.length ? <EmptyState title="暂无软件声明">后续可添加官方来源链接、安装脚本模板和校验规则；这里不会上传第三方安装包。</EmptyState> : null}
      </Card>
    </div>
  );
}

function BootView({ data, onRefresh }: { data: AppData; onRefresh: () => Promise<void> }) {
  const items = data.menuText
    .split("\n")
    .filter((line) => line.startsWith("item ") && !line.includes("--gap"))
    .map((line) => line.replace(/^item\s+/, "").trim());

  async function generateMenu() {
    const token = window.prompt("请输入管理员 token");
    if (!token) return;
    try {
      await postAdmin<string>("/api/menu/generate", {}, token);
      await onRefresh();
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : String(cause));
    }
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
      <section className="space-y-4">
        <Card>
          <SectionTitle eyebrow="boot menu" title="菜单摘要">这里只展示管理员需要判断的入口，不展开所有 Phase 3 证据包。</SectionTitle>
          <div className="grid gap-3">
            <Step label="菜单项" value={`${items.length} 个`} tone={items.length ? "ok" : "warn"} />
            <Step label="HTTP 链接" value={data.safety.menu_url || "/boot/menu.ipxe"} tone="ok" />
            <Step label="ProxyNet/PXE" value={data.bootEntry.pxe_ipv4_readiness?.runtime_enabled ? "已启用" : "默认关闭"} tone="warn" />
          </div>
          <Button className="mt-4" variant="accent" onClick={generateMenu}>
            <Rocket className="h-4 w-4" />
            重新生成菜单
          </Button>
        </Card>
        <Card>
          <SectionTitle eyebrow="visible entries" title="当前启动项" />
          <div className="space-y-2">
            {items.map((item) => (
              <div key={item} className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 font-mono text-sm">{item}</div>
            ))}
            {!items.length ? <EmptyState title="当前菜单没有可启动项" /> : null}
          </div>
        </Card>
      </section>
      <Card>
        <SectionTitle eyebrow="ipxe" title="原始菜单预览">用于排错。默认折叠到一个可复制的技术视图。</SectionTitle>
        <pre className="max-h-[620px] overflow-auto rounded-lg bg-zinc-950 p-4 text-xs leading-5 text-zinc-100">{data.menuText || "menu.ipxe empty"}</pre>
      </Card>
    </div>
  );
}

function EditionsView({ capabilities }: { capabilities: Capabilities }) {
  const tiers = capabilities.edition_catalog?.tiers || [];
  return (
    <div className="space-y-5">
      <Card>
        <SectionTitle eyebrow="product boundary" title="免费版与付费版边界">基础装机闭环永久免费；收费只覆盖高级效率、规模化治理和企业支持。</SectionTitle>
        <div className="grid gap-3 md:grid-cols-3">
          <Step label="当前发布线" value={capabilities.release_channel || "free"} tone="ok" />
          <Step label="商业代码" value={capabilities.commercial_code_included ? "包含" : "不包含"} tone={capabilities.commercial_code_included ? "danger" : "ok"} />
          <Step label="在线激活" value={capabilities.online_activation_required ? "需要" : "不需要"} tone={capabilities.online_activation_required ? "danger" : "ok"} />
        </div>
      </Card>
      <div className="grid gap-4 lg:grid-cols-3">
        {tiers.map((tier) => (
          <Card key={tier.id || tier.name}>
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-lg font-semibold text-zinc-950">{tier.name || tier.id}</h3>
              <Badge>{tier.billing || "候选"}</Badge>
            </div>
            <p className="mt-2 text-sm leading-6 text-zinc-500">{tier.summary}</p>
            <ul className="mt-4 space-y-2 text-sm text-zinc-700">
              {(tier.included || tier.candidate_features || []).slice(0, 8).map((item) => (
                <li key={item} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-500" />{item}</li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <ListCard title="免费核心能力" items={capabilities.core_free_guarantees || []} />
        <ListCard title="禁止进入免费发布线" items={capabilities.blocked_from_public_release || []} tone="warn" />
      </div>
    </div>
  );
}

function SafetyView({ data }: { data: AppData }) {
  const proxy = data.bootEntry.phase3_3a_boot_metadata_proxy_feasibility;
  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <SectionTitle eyebrow="deployment" title="部署状态" />
          <Step label="状态" value={data.deployment.status || "unknown"} tone={statusTone(data.deployment.status)} />
          <Step label="管理员写操作" value={data.deployment.admin_configured ? "已配置" : "未配置"} tone={data.deployment.admin_configured ? "ok" : "warn"} />
        </Card>
        <Card>
          <SectionTitle eyebrow="network" title="网络边界" />
          <Step label="当前模式" value={data.safety.mode || "HTTP only"} tone="ok" />
          <Step label="允许端口" value={(data.safety.allowed_ports || ["18080/tcp"]).join("，")} tone="ok" />
        </Card>
        <Card>
          <SectionTitle eyebrow="proxynet" title="Boot Metadata Proxy" />
          <Step label="状态" value={proxy?.status || "not enabled"} tone="warn" />
          <Step label="生产 LAN" value={proxy?.production_lan_allowed ? "允许" : "禁止/需二次确认"} tone="warn" />
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <ListCard title="禁止动作" items={data.safety.forbidden_actions || []} tone="warn" />
        <ListCard title="下一步建议" items={data.deployment.next_actions || []} />
      </div>
      <Card>
        <SectionTitle eyebrow="paths" title="本地路径检查" />
        <div className="grid gap-3 md:grid-cols-2">
          {(data.deployment.required_paths || []).map((item) => (
            <Step key={item.path} label={item.label || item.path || "path"} value={item.exists ? "exists" : "missing"} detail={item.path} tone={item.exists ? "ok" : "warn"} />
          ))}
        </div>
      </Card>
    </div>
  );
}

function ListCard({ title, items, tone = "muted" }: { title: string; items: string[]; tone?: "muted" | "warn" }) {
  return (
    <Card>
      <SectionTitle title={title} />
      <ul className="space-y-2 text-sm text-zinc-700">
        {items.slice(0, 12).map((item) => (
          <li key={item} className="flex gap-2">
            <span className={cn("mt-2 h-1.5 w-1.5 shrink-0 rounded-full", tone === "warn" ? "bg-amber-500" : "bg-cyan-500")} />
            {item}
          </li>
        ))}
      </ul>
      {!items.length ? <EmptyState title="暂无条目" /> : null}
    </Card>
  );
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-white/10 bg-zinc-900/70 p-3">
      <p className="text-xs text-zinc-400">{label}</p>
      <p className="mt-1 break-words font-mono text-sm text-cyan-200">{value}</p>
    </div>
  );
}

function Step({ label, value, detail, tone = "muted" }: { label: string; value?: string | number; detail?: string; tone?: string }) {
  return (
    <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-zinc-500">{label}</p>
        <Badge tone={statusTone(tone)}>{tone}</Badge>
      </div>
      <p className="mt-2 break-words text-sm font-semibold text-zinc-950">{value || "-"}</p>
      {detail ? <p className="mt-1 break-words text-xs text-zinc-500">{detail}</p> : null}
    </div>
  );
}

function Notice({ title, detail, tone = "warn" }: { title: string; detail: string; tone?: "warn" | "danger" }) {
  return (
    <div className={cn("mt-4 flex gap-3 rounded-lg border p-4", tone === "danger" ? "border-red-200 bg-red-50 text-red-800" : "border-amber-200 bg-amber-50 text-amber-800")}>
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p className="font-medium">{title}</p>
        <p className="mt-1 text-sm leading-6">{detail}</p>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
