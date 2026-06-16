export type ImageItem = {
  id: string;
  name?: string;
  display_name?: string;
  category?: string;
  kind?: string;
  size_bytes?: number;
  scan_status?: string;
  boot_readiness?: string;
  preparation_status?: string;
  readiness_detail?: string;
  next_action?: string;
  relative_path?: string;
  rel_path?: string;
  sha256?: string;
  menu_enabled?: boolean;
  boot_method?: string;
  missing_artifacts?: string[];
  source_role?: string;
};

export type JobItem = {
  id: string;
  title?: string;
  kind?: string;
  status?: string;
  note?: string;
  output_dir?: string;
};

export type Capabilities = {
  edition?: string;
  release_channel?: string;
  github_public_release?: boolean;
  commercial_code_included?: boolean;
  online_activation_required?: boolean;
  runtime_enforcement?: string;
  core_free_guarantees?: string[];
  paid_feature_placeholders?: string[];
  blocked_from_public_release?: string[];
  free_limits?: Record<string, boolean>;
  edition_catalog?: {
    tiers?: Array<{
      id?: string;
      name?: string;
      billing?: string;
      summary?: string;
      included?: string[];
      candidate_features?: string[];
    }>;
    guardrails?: string[];
  };
};

export type Safety = {
  web_url?: string;
  menu_url?: string;
  images_url?: string;
  phase?: string;
  mode?: string;
  allowed_ports?: string[];
  forbidden_actions?: string[];
};

export type Deployment = {
  status?: string;
  admin_configured?: boolean;
  required_paths?: Array<{ label?: string; path?: string; exists?: boolean; writable?: boolean }>;
  config_files?: Array<{ path?: string; exists?: boolean; readable?: boolean }>;
  runtime_checks?: Array<{ label?: string; status?: string; detail?: string }>;
  next_actions?: string[];
};

export type HotpeReadiness = {
  status?: string;
  hotpe_menu_ready?: boolean;
  hotpe_source_iso_present?: boolean;
  required_artifacts_present?: boolean;
  windows_iso_candidate_count?: number;
  missing_artifacts?: string[];
  required_artifacts?: Array<{ path?: string; present?: boolean }>;
  windows_iso_candidates?: ImageItem[];
  repository_urls?: { windows?: string };
  client_boot_test_status?: string;
  client_install_test_status?: string;
};

export type BootEntry = {
  phase?: string;
  display_phase?: string;
  display_status?: string;
  mode?: string;
  status?: string;
  enabled?: boolean;
  server?: { menu_url?: string; http_boot_loader_url?: string };
  pxe_ipv4_readiness?: {
    status?: string;
    runtime_enabled?: boolean;
    boot_tested?: boolean;
    preferred_loaders?: Array<{ filename?: string; usable?: boolean; status?: string }>;
  };
  phase3_3a_boot_metadata_proxy_feasibility?: {
    status?: string;
    runtime_enabled?: boolean;
    production_lan_allowed?: boolean;
    product_promise?: string[];
  };
};

export type AppData = {
  images: ImageItem[];
  jobs: JobItem[];
  capabilities: Capabilities;
  safety: Safety;
  deployment: Deployment;
  hotpe: HotpeReadiness;
  bootEntry: BootEntry;
  menuText: string;
};
