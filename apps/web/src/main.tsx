import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  Boxes,
  ChevronRight,
  Disc3,
  FileText,
  Gauge,
  HardDrive,
  Network,
  RefreshCw,
  Rocket,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
} from "lucide-react";
import "./index.css";
import { Badge, Button, Card, EmptyState, SectionTitle } from "./components/ui";
import { cn, fetchJson, formatSize, postAdmin, statusTone } from "./lib/utils";
import type { AppData, BootEntry, Capabilities, Deployment, HotpeReadiness, ImageItem, JobItem, Safety } from "./types";

const navItems = [
  { id: "overview", label: "总览", icon: Gauge },
  { id: "images", label: "镜像", icon: Disc3 },
  { id: "boot", label: "启动菜单", icon: TerminalSquare },
  { id: "editions", label: "版本边界", icon: Sparkles },
  { id: "safety", label: "实验 / 安全", icon: ShieldCheck },
] as const;

type ViewId = (typeof navItems)[number]["id"];

const emptyData: AppData = {
  images: [],
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

  async function refresh() {
    setError("");
    setLoading(true);
    try {
      const [images, jobs, capabilities, safety, deployment, hotpe, bootEntry, menuText] = await Promise.all([
        fetchJson<{ images: ImageItem[] }>("/api/images"),
        fetchJson<{ jobs: JobItem[] }>("/api/jobs"),
        fetchJson<Capabilities>("/api/capabilities"),
        fetchJson<Safety>("/api/network-safety"),
        fetchJson<Deployment>("/api/deployment-status"),
        fetchJson<HotpeReadiness>("/api/hotpe-readiness"),
        fetchJson<BootEntry>("/api/boot-entry"),
        fetch("/api/menu", { cache: "no-store" }).then((response) => response.text()),
      ]);
      const nextData = {
        images: images.images || [],
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
  }, []);

  const selectedImage = data.images.find((item) => item.id === selectedImageId);
  const filteredImages = useMemo(() => {
    const query = search.trim().toLowerCase();
    return data.images.filter((image) => {
      const text = `${image.display_name || image.name || ""} ${image.relative_path || image.rel_path || ""}`.toLowerCase();
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
            />
          ) : null}
          {activeView === "boot" ? <BootView data={data} onRefresh={refresh} /> : null}
          {activeView === "editions" ? <EditionsView capabilities={data.capabilities} /> : null}
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
    boot: "启动菜单",
    editions: "免费与付费边界",
    safety: "实验与安全边界",
  }[view];
}

function Overview({ data, loading, onNavigate }: { data: AppData; loading: boolean; onNavigate: (view: ViewId) => void }) {
  const readyImages = data.images.filter((image) => image.scan_status === "present" && image.boot_readiness === "ready");
  const windowsImages = data.images.filter((image) => image.category === "windows");
  const hotpeReady = Boolean(data.hotpe.hotpe_menu_ready);
  const phase3Enabled = Boolean(data.bootEntry.pxe_ipv4_readiness?.runtime_enabled);
  const metrics = [
    { label: "可启动镜像", value: readyImages.length, detail: `${data.images.length} 个已扫描` },
    { label: "HotPE", value: hotpeReady ? "Ready" : "待处理", detail: data.hotpe.status || "unknown" },
    { label: "Windows 源", value: windowsImages.length, detail: "WinNTSetup/原生安装候选" },
    { label: "PXE Runtime", value: phase3Enabled ? "已启用" : "默认关闭", detail: "Boot Metadata Proxy 边界" },
  ];

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-xl border border-zinc-200 bg-zinc-950 text-white shadow-sm">
        <div className="grid gap-6 p-6 md:grid-cols-[1.3fr_0.7fr] md:p-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">Modern PXE operations</p>
            <h2 className="mt-4 max-w-3xl text-3xl font-semibold leading-tight tracking-tight md:text-4xl xl:text-5xl">把装机链路压缩成可行动状态。</h2>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-zinc-300">
              页面只保留镜像、启动、版本边界和实验安全。Phase 3 仍遵守人工确认与可回滚原则，基础装机能力保持免费。
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              <Button variant="accent" onClick={() => onNavigate("images")}>管理镜像</Button>
              <Button className="border-white/15 bg-white/10 text-white hover:bg-white/15" variant="outline" onClick={() => onNavigate("boot")}>查看启动菜单</Button>
            </div>
          </div>
          <div className="grid content-start gap-3 rounded-lg border border-white/10 bg-white/5 p-4">
            <StatusLine label="Web UI" value={data.safety.web_url || "/"} />
            <StatusLine label="iPXE Menu" value={data.safety.menu_url || "/boot/menu.ipxe"} />
            <StatusLine label="Image Repo" value={data.safety.images_url || "/images/"} />
          </div>
        </div>
      </section>

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
          <SectionTitle eyebrow="install path" title="当前最短可用路径">优先完成 Windows 原生安装、HotPE 内挂载 SMB/ISO，以及 Ubuntu 的长期网络挂载方案。</SectionTitle>
          <div className="grid gap-3">
            <Step label="Windows 11" value={windowsImages.length ? "可进入安装界面" : "等待镜像"} tone={windowsImages.length ? "ok" : "warn"} />
            <Step label="HotPE" value={hotpeReady ? "可启动，需挂载外部工具/镜像" : data.hotpe.status || "未就绪"} tone={hotpeReady ? "ok" : "warn"} />
            <Step label="Ubuntu" value="HTTP RAM fallback 不适合作为长期路径" tone="warn" />
          </div>
        </Card>
        <Card>
          <SectionTitle eyebrow="recent jobs" title="构建任务" />
          <div className="space-y-3">
            {data.jobs.slice(0, 5).map((job) => (
              <div key={job.id} className="rounded-md border border-zinc-200 p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-medium text-zinc-900">{job.title || job.kind}</p>
                  <Badge tone={statusTone(job.status)}>{job.status || "unknown"}</Badge>
                </div>
                <p className="mt-1 text-xs text-zinc-500">{job.note || job.output_dir}</p>
              </div>
            ))}
            {!data.jobs.length ? <EmptyState title="暂无构建任务" /> : null}
          </div>
        </Card>
      </div>
    </div>
  );
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
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
      <section className="space-y-4">
        <Card>
          <SectionTitle eyebrow="repository" title="镜像仓库">管理员只需要看到能否启动、下一步做什么，以及镜像在哪。</SectionTitle>
          <div className="grid gap-3 md:grid-cols-[1fr_180px]">
            <input className="min-h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索镜像名称或路径" />
            <select className="min-h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-300" value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">全部分类</option>
              <option value="windows">Windows</option>
              <option value="pe">HotPE / PE</option>
              <option value="linux">Linux</option>
              <option value="tools">Tools</option>
              <option value="custom">Custom</option>
            </select>
          </div>
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
                <Badge tone={statusTone(image.boot_readiness)}>{image.boot_readiness || "unknown"}</Badge>
                <Badge tone={statusTone(image.preparation_status)}>{image.preparation_status || "unknown"}</Badge>
                <Badge>{formatSize(image.size_bytes)}</Badge>
              </div>
            </button>
          ))}
          {!filteredImages.length ? <EmptyState title="没有匹配的镜像" /> : null}
        </div>
      </section>

      <section className="space-y-4">
        <ImageDetail image={selectedImage} onRefresh={onRefresh} />
        <HotpeQuickCard hotpe={data.hotpe} />
      </section>
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
    const kind = image.category === "pe" ? "hotpe-iso-prepare" : image.category === "linux" ? "ubuntu-iso-extract-kernel-initrd" : "";
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
    ["类型", image.kind],
    ["启动方式", image.boot_method],
    ["状态", image.boot_readiness],
    ["准备", image.preparation_status],
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
      <div className="mt-4 rounded-md bg-zinc-950 p-3 font-mono text-xs text-zinc-100">
        <p>{image.relative_path || image.rel_path}</p>
        <p className="mt-1 text-zinc-400">{image.sha256 || "sha256 not calculated"}</p>
      </div>
      {image.missing_artifacts?.length ? (
        <Notice tone="warn" title="缺失启动组件" detail={image.missing_artifacts.join("，")} />
      ) : null}
      {image.preparation_status === "needs_extraction" ? (
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
