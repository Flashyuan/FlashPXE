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
  inventory_role?: string;
  object_type?: string;
  visibility?: string;
  is_primary_inventory?: boolean;
  os_family?: string;
  os_distribution?: string;
  detected_distro?: string;
  detected_version?: string;
  detected_arch?: string;
  detection_confidence?: string;
  detection_status?: string;
  detection_strategy?: string;
  detection_evidence?: string[];
  strategy_key?: string;
  strategy_display_name?: string;
  strategy_status?: string;
  source_group?: string;
  parent_relative_path?: string;
  artifact_role?: string;
  artifact_count?: number;
  artifacts?: ImageArtifact[];
};

export type ImageArtifact = {
  id?: string;
  object_type?: string;
  name?: string;
  parent_relative_path?: string;
  relative_path?: string;
  kind?: string;
  artifact_role?: string;
  size_bytes?: number;
  boot_readiness?: string;
  preparation_status?: string;
  source_role?: string;
};

export type ImagesResponse = {
  schema_version?: string;
  inventory_mode?: string;
  images?: ImageItem[];
  source_images?: ImageItem[];
  artifacts?: ImageArtifact[];
  derived_artifacts?: ImageArtifact[];
  summary?: {
    total_files?: number;
    source_image_count?: number;
    artifact_count?: number;
    ready_source_count?: number;
    research_required_count?: number;
    unsupported_source_count?: number;
  };
};

export type ClientSession = {
  session_id: string;
  mac?: string;
  ip?: string;
  uuid?: string;
  serial?: string;
  asset?: string;
  manufacturer?: string;
  product?: string;
  platform?: string;
  buildarch?: string;
  state?: string;
  selected_target?: string;
  selected_label?: string;
  first_seen_at?: number;
  last_seen_at?: number;
  expires_at?: number;
  online?: boolean;
  latest_assignment?: {
    id?: string;
    boot_target?: string;
    boot_label?: string;
    status?: string;
    software_count?: number;
    software_labels?: string[];
    event_summary?: {
      last_status?: string;
      last_stage?: string;
      last_message?: string;
      last_event_at?: number;
      completed?: number;
      failed?: number;
      blocked?: number;
    };
    session_event_summary?: {
      last_status?: string;
      last_stage?: string;
      last_message?: string;
      last_event_at?: number;
      completed?: number;
      failed?: number;
      blocked?: number;
    };
  } | null;
};

export type AssignableTarget = {
  target: string;
  label: string;
  kind?: string;
  software_assignment_enabled?: boolean;
  postinstall_status?: string;
  postinstall_detail?: string;
};

export type SoftwareVariant = {
  id: string;
  package_id?: string;
  os_family: "windows" | "ubuntu" | "linux" | string;
  os_version_constraint?: string;
  arch?: string;
  version?: string;
  installer_type?: string;
  official_source_url?: string;
  download_url?: string;
  source_policy?: string;
  sha256?: string;
  signature_policy?: string;
  install_phase?: string;
  install_action?: string;
  package_name?: string;
  default_for_os?: boolean;
  selection_priority?: number;
  silent_args?: string;
  requires_network?: boolean;
  risk_level?: string;
  review_status?: string;
  enabled?: boolean;
  notes?: string;
  assignable?: boolean;
  blocked_reasons?: string[];
  install_context?: string;
  detection_rules?: Array<Record<string, unknown>>;
  requirements?: Record<string, unknown>;
  dependencies?: Array<Record<string, unknown>>;
  return_codes?: Record<string, number[]>;
  restart_behavior?: string;
  install_location_policy?: string;
};

export type SoftwarePackage = {
  id: string;
  name: string;
  vendor?: string;
  category?: string;
  description?: string;
  homepage_url?: string;
  icon_key?: string;
  status?: string;
  review_status?: string;
  variants?: SoftwareVariant[];
};

export type SoftwareProfile = {
  id: string;
  name: string;
  description?: string;
  os_family?: string;
  variant_ids?: string[];
  variants?: SoftwareVariant[];
  status?: string;
  review_status?: string;
  risk_level?: string;
  assignable?: boolean;
};

export type SoftwarePackagesResponse = {
  schema_version?: string;
  policy?: {
    artifact_hosting_allowed?: boolean;
    third_party_binary_stored?: boolean;
    client_downloads_from_official_source?: boolean;
  };
  packages?: SoftwarePackage[];
};

export type SoftwareProfilesResponse = {
  schema_version?: string;
  policy?: {
    artifact_hosting_allowed?: boolean;
    third_party_binary_stored?: boolean;
    profile_groups_assignable_variants_only?: boolean;
  };
  profiles?: SoftwareProfile[];
};

export type InstallPreset = {
  id: string;
  name: string;
  description?: string;
  os_family?: string;
  boot_target?: string;
  software_package_ids?: string[];
  software_profile_ids?: string[];
  settings?: Record<string, unknown>;
  status?: string;
  review_status?: string;
  assignable?: boolean;
  blocked_reasons?: string[];
  notes?: string;
};

export type InstallPresetsResponse = {
  schema_version?: string;
  policy?: Record<string, unknown>;
  presets?: InstallPreset[];
};

export type ClientSessionsResponse = {
  schema_version?: string;
  access?: string;
  sessions?: ClientSession[];
  assignable_targets?: AssignableTarget[];
  summary?: {
    total?: number;
    online?: number;
    waiting?: number;
    assigned?: number;
  };
};

export type AdminSession = {
  schema_version?: string;
  admin_configured?: boolean;
  authenticated?: boolean;
  image_drop_folder?: string;
  auto_refresh_seconds?: number;
  error?: string;
};

export type AssignmentOptions = {
  schema_version?: string;
  session?: ClientSession;
  sessions?: ClientSession[];
  boot_targets?: AssignableTarget[];
  compatible_software_packages?: SoftwarePackage[];
  compatible_software_by_target?: Record<string, SoftwarePackage[]>;
  compatible_software_profiles_by_target?: Record<string, SoftwareProfile[]>;
  install_presets_by_target?: Record<string, InstallPreset[]>;
  install_presets?: InstallPreset[];
  compatible_software_variants?: SoftwareVariant[];
  software_profiles?: SoftwareProfile[];
  software_market_status?: string;
  software_market_policy?: Record<string, unknown>;
  conflicts?: string[];
  notes?: string[];
};

export type JobItem = {
  id: string;
  title?: string;
  kind?: string;
  status?: string;
  note?: string;
  output_dir?: string;
};

export type ClientEvent = {
  id: string;
  session_id?: string;
  assignment_id?: string;
  event_type?: string;
  stage?: string;
  status?: string;
  message?: string;
  payload?: Record<string, unknown>;
  created_at?: number;
};

export type DeploymentAssignment = {
  id: string;
  session_id?: string;
  session_ids?: string[];
  boot_target?: string;
  boot_label?: string;
  software_package_ids?: string[];
  software_profile_ids?: string[];
  software_variant_ids?: string[];
  install_preset_id?: string;
  task_sequence_plan?: {
    schema_version?: string;
    mode?: string;
    os_family?: string;
    boot_target?: string;
    install_preset_id?: string;
    software_variant_count?: number;
    steps?: Array<{ id?: string; status?: string; execution?: string }>;
  };
  resolved_software_plan?: {
    package_ids?: string[];
    packages?: Array<{
      id?: string;
      name?: string;
      vendor?: string;
      category?: string;
      selected_variant_id?: string;
    }>;
    profiles?: SoftwareProfile[];
    variants?: SoftwareVariant[];
    os_family?: string;
    third_party_binary_stored?: boolean;
    client_downloads_from_official_source?: boolean;
  };
  status?: string;
  created_at?: number;
  updated_at?: number;
  expires_at?: number;
  recent_events?: ClientEvent[];
  event_summary?: {
    total?: number;
    last_status?: string;
    last_stage?: string;
    last_message?: string;
    last_event_at?: number;
    completed?: number;
    failed?: number;
    blocked?: number;
  };
};

export type DeploymentAssignmentsResponse = {
  schema_version?: string;
  assignments?: DeploymentAssignment[];
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
  software: SoftwarePackage[];
  softwareProfiles: SoftwareProfile[];
  installPresets: InstallPreset[];
  clients: ClientSessionsResponse;
  assignments: DeploymentAssignment[];
  jobs: JobItem[];
  capabilities: Capabilities;
  safety: Safety;
  deployment: Deployment;
  hotpe: HotpeReadiness;
  bootEntry: BootEntry;
  menuText: string;
};
