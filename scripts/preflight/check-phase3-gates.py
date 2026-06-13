#!/usr/bin/env python3
"""校验 Phase 3 只读门禁字段，避免运行时能力被误读为已解锁。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


# 该预检应保持只读，不在 apps/ 或 scripts/ 下生成 __pycache__。
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
API_MAIN = ROOT / "apps" / "api" / "main.py"
PHASE3_SOURCE_SKELETON_FIXTURE = ROOT / "config" / "synaboot" / "phase3.13-isolated-lab-source-skeleton.disabled.json"

EXPECTED_STATUS = "router_option_path_not_recommended_but_blocked"
EXPECTED_NEXT_STEP = "controlled_proxy" + "d" + "hcp_feasibility_evaluation_only"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_api_module() -> Any:
    spec = importlib.util.spec_from_file_location("synaboot_api_main", API_MAIN)
    if spec is None or spec.loader is None:
        fail(f"cannot load API module from {API_MAIN}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(value: bool, message: str) -> None:
    if not value:
        fail(message)


def require_false(mapping: dict[str, Any], key: str, scope: str) -> None:
    require(mapping.get(key) is False, f"{scope}.{key} must be false")


def collect_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        keys = list(value.keys())
        for item in value.values():
            keys.extend(collect_keys(item))
        return keys
    if isinstance(value, list):
        keys: list[str] = []
        for item in value:
            keys.extend(collect_keys(item))
        return keys
    return []


def collect_string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(collect_string_values(item))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(collect_string_values(item))
        return values
    return []


def main() -> int:
    api = load_api_module()
    boot_entry = api.boot_entry_status()
    network_safety = api.network_safety_status()

    entry_gate = boot_entry.get("phase3_3_gate", {})
    safety_gate = network_safety.get("phase3_gate", {})
    feasibility = boot_entry.get("phase3_3_feasibility", {})
    isolated_plan = boot_entry.get("isolated_validation_plan", {})
    pxe_readiness = boot_entry.get("pxe_ipv4_readiness", {})
    pxe_lab_plan = boot_entry.get("pxe_lab_boot_metadata_plan", {})
    disabled_skeleton = boot_entry.get("isolated_lab_boot_services_disabled_skeleton", {})
    evidence_package = boot_entry.get("isolated_lab_evidence_package", {})
    config_intent = boot_entry.get("isolated_lab_config_intent_package", {})
    source_skeleton = boot_entry.get("isolated_lab_source_skeleton_package", {})
    manual_gate = boot_entry.get("isolated_lab_manual_declaration_gate", {})
    runtime_plan = boot_entry.get("isolated_lab_runtime_authorization_plan", {})
    runtime_draft = boot_entry.get("isolated_lab_runtime_authorization_draft", {})

    require(boot_entry.get("phase") == "3.1", "boot-entry phase must remain 3.1")
    require(boot_entry.get("display_phase") == "3.4", "boot-entry display_phase must remain 3.4")
    require(
        boot_entry.get("display_status") == "readonly_boot_entry_with_local_fact_gate",
        "boot-entry display_status must remain readonly_boot_entry_with_local_fact_gate",
    )
    require_false(boot_entry, "enabled", "boot-entry")
    require_false(boot_entry, "operation_allowed", "boot-entry")

    require(entry_gate.get("status") == EXPECTED_STATUS, "boot-entry phase3_3_gate status mismatch")
    require(entry_gate.get("allowed_next_step") == EXPECTED_NEXT_STEP, "boot-entry allowed_next_step mismatch")
    for key in ("confirmed_evidence", "missing_local_facts", "blocked_until", "do_not_infer"):
        require(isinstance(entry_gate.get(key), list) and bool(entry_gate[key]), f"phase3_3_gate.{key} must be a non-empty list")

    require(safety_gate.get("model_phase") == "3.1", "network-safety phase3_gate model_phase mismatch")
    require(safety_gate.get("display_phase") == "3.4", "network-safety phase3_gate display_phase mismatch")
    require(safety_gate.get("status") == EXPECTED_STATUS, "network-safety phase3_gate status mismatch")
    require(safety_gate.get("allowed_next_step") == EXPECTED_NEXT_STEP, "network-safety allowed_next_step mismatch")
    for key in ("implementation_allowed", "service_enablement_allowed", "production_lan_testing_allowed"):
        require_false(safety_gate, key, "network-safety.phase3_gate")
        require_false(feasibility, key, "boot-entry.phase3_3_feasibility")
        require_false(isolated_plan, key, "boot-entry.isolated_validation_plan")

    require(pxe_readiness.get("schema_version") == "pxe-ipv4-readiness.v1", "pxe_ipv4_readiness schema mismatch")
    require(pxe_readiness.get("mode") == "readonly_summary_only", "pxe_ipv4_readiness mode mismatch")
    require(pxe_readiness.get("status") == "blocked_by_phase3_gate", "pxe_ipv4_readiness must remain blocked by Phase 3 gate")
    for key in ("operation_allowed", "service_enablement_allowed", "production_lan_testing_allowed", "production_lan_allowed", "runtime_enabled", "boot_tested"):
        require_false(pxe_readiness, key, "boot-entry.pxe_ipv4_readiness")
    readiness_invariants = pxe_readiness.get("safety_invariants", {})
    for key in (
        "production_lan_enabled",
        "production_lan_allowed",
        "d" + "hcp_server_enabled",
        "d" + "hcp_lease_assignment_allowed",
        "proxy" + "d" + "hcp_enabled",
        "tf" + "tp_enabled",
        "udp_67_open",
        "udp_69_open",
        "udp_4011_open",
        "docker_host_network_allowed",
        "docker_privileged_allowed",
        "host_network_mutation_allowed",
        "openwrt_mutation_allowed",
        "tplink_" + "d" + "hcp_replacement_allowed",
        "default_gateway_change_allowed",
        "auto_enable_boot_services_allowed",
    ):
        require_false(readiness_invariants, key, "boot-entry.pxe_ipv4_readiness.safety_invariants")
    require(isinstance(pxe_readiness.get("blocking_items"), list) and pxe_readiness["blocking_items"], "pxe_ipv4_readiness.blocking_items required")
    require(isinstance(pxe_readiness.get("preferred_loaders"), list), "pxe_ipv4_readiness.preferred_loaders must be a list")
    require(isinstance(pxe_readiness.get("image_menu"), dict), "pxe_ipv4_readiness.image_menu must be an object")
    readiness_text = " ".join(pxe_readiness.get("blocking_items", []) + pxe_readiness.get("next_actions", []))
    for token in ("Proxy" + "D" + "HCP", "TF" + "TP", "production LAN"):
        require(token in readiness_text, f"pxe_ipv4_readiness must preserve blocked wording for {token}")

    require(pxe_lab_plan.get("schema_version") == "pxe-lab-boot-metadata-plan.v1", "pxe_lab_boot_metadata_plan schema mismatch")
    require(pxe_lab_plan.get("mode") == "readonly_plan_only", "pxe_lab_boot_metadata_plan mode mismatch")
    require(pxe_lab_plan.get("phase3_status") == "blocked_by_phase3_gate", "pxe_lab_boot_metadata_plan phase3_status mismatch")
    require(
        pxe_lab_plan.get("status") == "blocked_until_lab_service_authorized",
        "pxe_lab_boot_metadata_plan status mismatch",
    )
    for key in (
        "operation_allowed",
        "service_enablement_allowed",
        "runtime_enabled",
        "production_lan_allowed",
        "production_lan_testing_allowed",
        "boot_tested",
        "generates_config_files",
        "config_generation_allowed",
        "command_execution_allowed",
        "starts_services",
        "writes_router_config",
    ):
        require_false(pxe_lab_plan, key, "boot-entry.pxe_lab_boot_metadata_plan")
    lab_invariants = pxe_lab_plan.get("safety_invariants", {})
    for key in (
        "d" + "hcp_server_enabled",
        "d" + "hcp_lease_assignment_allowed",
        "proxy" + "d" + "hcp_enabled",
        "tf" + "tp_enabled",
        "udp_67_open",
        "udp_69_open",
        "udp_4011_open",
        "tplink_" + "d" + "hcp_replacement_allowed",
        "openwrt_mutation_allowed",
        "default_gateway_change_allowed",
    ):
        require_false(lab_invariants, key, "boot-entry.pxe_lab_boot_metadata_plan.safety_invariants")
    metadata = pxe_lab_plan.get("candidate_boot_metadata", {})
    require(metadata.get("bootfile") in {"", "snponly.efi", "ipxe.efi"}, "pxe_lab bootfile must stay in UEFI loader allowlist")
    require(metadata.get("tftp_root") == "data/boot/loaders", "pxe_lab tftp_root mismatch")
    require("menu.ipxe" in metadata.get("forbidden_tftp_files", []), "pxe_lab must forbid serving menu.ipxe by TFTP")
    require("ipxe.iso" in metadata.get("forbidden_tftp_files", []), "pxe_lab must forbid serving ipxe.iso by TFTP")
    require(isinstance(pxe_lab_plan.get("loader_evidence"), list), "pxe_lab loader_evidence must be a list")
    require(isinstance(pxe_lab_plan.get("required_packet_evidence"), list) and pxe_lab_plan["required_packet_evidence"], "pxe_lab packet evidence required")
    forbidden_fields = " ".join(pxe_lab_plan.get("forbidden_dhcp_fields", []))
    for token in ("router", "DNS", "subnet", "lease", "DHCP ACK", "classless static route", "address pool"):
        require(token in forbidden_fields, f"pxe_lab forbidden_dhcp_fields must mention {token}")
    lab_text = " ".join(
        pxe_lab_plan.get("proxy_dhcp_metadata_fields", [])
        + pxe_lab_plan.get("required_packet_evidence", [])
        + pxe_lab_plan.get("blocking_items", [])
        + pxe_lab_plan.get("next_gate", [])
    )
    for token in ("Proxy" + "D" + "HCP", "TF" + "TP", "UDP", "production LAN"):
        require(token in lab_text, f"pxe_lab_boot_metadata_plan must preserve blocked wording for {token}")

    require(
        disabled_skeleton.get("schema_version") == "isolated-lab-boot-services-disabled-skeleton.v1",
        "isolated_lab_boot_services_disabled_skeleton schema mismatch",
    )
    require(
        disabled_skeleton.get("mode") == "isolated_lab_boot_services_disabled_skeleton",
        "isolated_lab_boot_services_disabled_skeleton mode mismatch",
    )
    require(disabled_skeleton.get("phase") == "3.10", "isolated_lab_boot_services_disabled_skeleton phase mismatch")
    require(
        disabled_skeleton.get("environment_scope") == "isolated_lab_only",
        "isolated_lab_boot_services_disabled_skeleton scope mismatch",
    )
    require(
        disabled_skeleton.get("status") == "blocked_disabled_skeleton_only",
        "isolated_lab_boot_services_disabled_skeleton status mismatch",
    )
    require(disabled_skeleton.get("read_only") is True, "isolated_lab_boot_services_disabled_skeleton.read_only must be true")
    for key in (
        "enabled",
        "runtime_enabled",
        "service_authorization_allowed",
        "service_start_allowed",
        "config_generation_allowed",
        "command_execution_allowed",
        "compose_change_allowed",
        "production_lan_allowed",
        "production_lan_testing_allowed",
        "boot_tested",
    ):
        require_false(disabled_skeleton, key, "boot-entry.isolated_lab_boot_services_disabled_skeleton")
    skeleton_invariants = disabled_skeleton.get("safety_invariants", {})
    for key in (
        "d" + "hcp_server_enabled",
        "d" + "hcp_lease_assignment_allowed",
        "proxy" + "d" + "hcp_enabled",
        "tf" + "tp_enabled",
        "udp_67_open",
        "udp_69_open",
        "udp_4011_open",
        "router_config_generation_allowed",
        "compose_boot_service_generation_allowed",
        "host_network_allowed",
        "privileged_container_allowed",
        "tplink_mutation_allowed",
        "openwrt_mutation_allowed",
        "default_gateway_change_allowed",
    ):
        require_false(skeleton_invariants, key, "boot-entry.isolated_lab_boot_services_disabled_skeleton.safety_invariants")
    service_profiles = disabled_skeleton.get("service_profiles", [])
    require(isinstance(service_profiles, list) and service_profiles, "isolated_lab_boot_services_disabled_skeleton.service_profiles required")
    for service in service_profiles:
        require(
            service.get("id") in {"proxy_" + "d" + "hcp_metadata_only", "tf" + "tp_loader_only"},
            f"isolated_lab_boot_services_disabled_skeleton service profile must stay limited: {service.get('id')}",
        )
        require_false(service, "service_enabled", f"isolated_lab_boot_services_disabled_skeleton.service_profiles.{service.get('id')}")
        require_false(service, "runtime_available", f"isolated_lab_boot_services_disabled_skeleton.service_profiles.{service.get('id')}")
        require_false(service, "runtime_authorization_allowed", f"isolated_lab_boot_services_disabled_skeleton.service_profiles.{service.get('id')}")
    reference_targets = disabled_skeleton.get("reference_targets", [])
    require(isinstance(reference_targets, list) and reference_targets, "isolated_lab_boot_services_disabled_skeleton.reference_targets required")
    require(
        any(target.get("id") == "http_menu_target" and target.get("current_reference_only") is True for target in reference_targets),
        "isolated_lab_boot_services_disabled_skeleton must keep HTTP menu as reference target",
    )
    require(
        "menu.ipxe" in disabled_skeleton.get("forbidden_transfer_scope", []),
        "isolated_lab_boot_services_disabled_skeleton must forbid menu.ipxe transfer scope",
    )
    require(
        "ipxe.iso" in disabled_skeleton.get("forbidden_transfer_scope", []),
        "isolated_lab_boot_services_disabled_skeleton must forbid ipxe.iso transfer scope",
    )
    for key in (
        "target_chain_model",
        "bootfile_candidates",
        "tftp_loader_allowlist",
        "client_evidence_template",
        "failure_modes",
        "rollback_plan",
        "blocked_actions",
        "next_gate",
    ):
        require(
            isinstance(disabled_skeleton.get(key), list) and bool(disabled_skeleton[key]),
            f"isolated_lab_boot_services_disabled_skeleton.{key} must be a non-empty list",
        )
    skeleton_gates = disabled_skeleton.get("gates", {})
    for key in (
        "research_review",
        "network_safety_review",
        "security_audit_review",
        "project_decision",
        "isolated_lab_confirmation",
    ):
        require(
            skeleton_gates.get(key) == "required_before_runtime",
            f"isolated_lab_boot_services_disabled_skeleton.gates.{key} mismatch",
        )
    skeleton_text = " ".join(
        disabled_skeleton.get("target_chain_model", [])
        + disabled_skeleton.get("failure_modes", [])
        + disabled_skeleton.get("rollback_plan", [])
        + disabled_skeleton.get("blocked_actions", [])
        + disabled_skeleton.get("next_gate", [])
    )
    for token in ("Proxy" + "D" + "HCP", "TF" + "TP", "UDP", "production LAN"):
        require(token in skeleton_text, f"isolated_lab_boot_services_disabled_skeleton must preserve blocked wording for {token}")

    require(
        evidence_package.get("schema_version") == "phase3-isolated-lab-evidence-package.v1",
        "isolated_lab_evidence_package schema mismatch",
    )
    require(evidence_package.get("phase") == "3.11", "isolated_lab_evidence_package phase mismatch")
    require(evidence_package.get("mode") == "readonly_evidence_package", "isolated_lab_evidence_package mode mismatch")
    require(evidence_package.get("status") == "not_authorized", "isolated_lab_evidence_package status mismatch")
    require(evidence_package.get("read_only") is True, "isolated_lab_evidence_package.read_only must be true")
    for key in (
        "enabled",
        "secrets_included",
        "secret_fields_allowed",
        "sensitive_values_exposed",
        "raw_commands_included",
        "config_generation_allowed",
        "command_execution_allowed",
        "service_start_allowed",
        "compose_generation_allowed",
        "router_config_generation_allowed",
        "production_lan_allowed",
        "production_lan_testing_allowed",
        "packet_capture_started",
        "network_probe_started",
        "boot_tested",
    ):
        require_false(evidence_package, key, "boot-entry.isolated_lab_evidence_package")
    require(evidence_package.get("secret_redaction_applied") is True, "isolated_lab_evidence_package.secret_redaction_applied must be true")
    auth_request = evidence_package.get("authorization_request", {})
    require(auth_request.get("status") == "draft_not_authorized", "isolated_lab_evidence_package.authorization_request status mismatch")
    require(auth_request.get("request_is_authorization") is False, "authorization request must not be treated as authorization")
    approval_state = auth_request.get("approval_state", {})
    for key in (
        "research_review",
        "network_safety_review",
        "security_audit_review",
        "project_decision",
        "user_manual_confirmation",
    ):
        require(approval_state.get(key) == "required_before_runtime", f"isolated_lab_evidence_package.approval_state.{key} mismatch")
    evidence_service_state = evidence_package.get("network_service_state", {})
    for key in (
        "d" + "hcp_server_enabled",
        "d" + "hcp_lease_assignment_allowed",
        "proxy" + "d" + "hcp_enabled",
        "tf" + "tp_enabled",
        "udp_67_open",
        "udp_69_open",
        "udp_4011_open",
        "host_network_allowed",
        "privileged_container_allowed",
    ):
        require_false(evidence_service_state, key, "boot-entry.isolated_lab_evidence_package.network_service_state")
    for item in evidence_package.get("udp_port_evidence", []):
        require(item.get("port") in {67, 69, 4011}, "isolated_lab_evidence_package UDP evidence port allowlist mismatch")
        require(item.get("observed_in_api_namespace") is False, f"UDP {item.get('port')} must not be observed in API namespace")
    for key in (
        "evidence_checks",
        "udp_port_evidence",
        "manual_lab_declaration_required",
        "client_evidence_template",
        "expected_observations",
        "forbidden_outputs",
        "blocking_items",
        "next_gate",
    ):
        require(
            isinstance(evidence_package.get(key), list) and bool(evidence_package[key]),
            f"isolated_lab_evidence_package.{key} must be a non-empty list",
        )
    forbidden_exact_keys = {"command", "commands", "run", "exec", "shell", "apply_script"}
    allowed_exact_keys = {"command_execution_allowed", "raw_commands_included"}
    for key in collect_keys(evidence_package):
        require(
            key not in forbidden_exact_keys or key in allowed_exact_keys,
            f"isolated_lab_evidence_package contains forbidden raw command key: {key}",
        )
    evidence_text = " ".join(
        evidence_package.get("manual_lab_declaration_required", [])
        + evidence_package.get("expected_observations", [])
        + evidence_package.get("forbidden_outputs", [])
        + evidence_package.get("blocking_items", [])
        + evidence_package.get("next_gate", [])
    )
    for token in ("Proxy" + "D" + "HCP", "TF" + "TP", "UDP", "production LAN"):
        require(token in evidence_text, f"isolated_lab_evidence_package must preserve blocked wording for {token}")

    require(
        config_intent.get("schema_version") == "phase3-isolated-lab-config-intent-package.v1",
        "isolated_lab_config_intent_package schema mismatch",
    )
    require(config_intent.get("phase") == "3.12", "isolated_lab_config_intent_package phase mismatch")
    require(
        config_intent.get("mode") == "readonly_config_intent_package",
        "isolated_lab_config_intent_package mode mismatch",
    )
    require(config_intent.get("status") == "not_authorized", "isolated_lab_config_intent_package status mismatch")
    require(config_intent.get("read_only") is True, "isolated_lab_config_intent_package.read_only must be true")
    require(config_intent.get("request_is_authorization") is False, "isolated_lab_config_intent_package request_is_authorization must be false")
    for key in (
        "enabled",
        "authorized",
        "runtime_enabled",
        "secrets_included",
        "secret_fields_allowed",
        "sensitive_values_exposed",
        "env_contents_exposed",
        "raw_commands_included",
        "config_files_generated",
        "config_generation_allowed",
        "command_execution_allowed",
        "service_start_allowed",
        "write_api_available",
        "compose_change_allowed",
        "router_config_generation_allowed",
        "production_lan_allowed",
        "production_lan_testing_allowed",
        "packet_capture_started",
        "network_probe_started",
        "task_consumption_allowed",
        "boot_tested",
    ):
        require_false(config_intent, key, "boot-entry.isolated_lab_config_intent_package")
    require(
        config_intent.get("secret_redaction_applied") is True,
        "isolated_lab_config_intent_package.secret_redaction_applied must be true",
    )
    require(
        config_intent.get("environment_scope") == "single_machine_isolated_lab_only",
        "isolated_lab_config_intent_package environment scope mismatch",
    )
    config_service_state = config_intent.get("network_service_state", {})
    for key in (
        "d" + "hcp_server_enabled",
        "d" + "hcp_lease_assignment_allowed",
        "proxy" + "d" + "hcp_enabled",
        "tf" + "tp_enabled",
        "udp_67_open",
        "udp_69_open",
        "udp_4011_open",
        "host_network_allowed",
        "privileged_container_allowed",
    ):
        require_false(config_service_state, key, "boot-entry.isolated_lab_config_intent_package.network_service_state")
    intended_services = config_intent.get("intended_services", {})
    require(
        intended_services.get("proxy_" + "d" + "hcp_metadata_only") == "disabled_intent_only",
        "isolated_lab_config_intent_package ProxyDHCP intent must stay disabled",
    )
    require(
        intended_services.get("tf" + "tp_loader_only") == "disabled_intent_only",
        "isolated_lab_config_intent_package TFTP intent must stay disabled",
    )
    intended_ports = config_intent.get("intended_ports", [])
    require(isinstance(intended_ports, list) and len(intended_ports) == 3, "isolated_lab_config_intent_package intended ports required")
    for item in intended_ports:
        require(item.get("port") in {67, 69, 4011}, "isolated_lab_config_intent_package port allowlist mismatch")
        require(item.get("protocol") == "udp", "isolated_lab_config_intent_package intended ports must be UDP")
        require(item.get("observed_listening") is False, f"UDP {item.get('port')} must not be observed listening")
        require(item.get("desired_listening") is False, f"UDP {item.get('port')} desired_listening must be false")
    candidate = config_intent.get("candidate_bootfile", {})
    require(candidate.get("value") in {"", "snponly.efi", "ipxe.efi"}, "isolated_lab_config_intent_package candidate bootfile mismatch")
    require(candidate.get("status") == "intent_only", "isolated_lab_config_intent_package candidate bootfile must be intent only")
    require(candidate.get("tested") is False, "isolated_lab_config_intent_package candidate bootfile must remain untested")
    for loader in config_intent.get("loader_allowlist", []):
        require(loader.get("name") in {"snponly.efi", "ipxe.efi"}, "isolated_lab_config_intent_package loader allowlist mismatch")
        require(loader.get("reviewed") is True, "isolated_lab_config_intent_package loader allowlist must contain only reviewed loaders")
        require(loader.get("served_by_loader_transfer") is False, "isolated_lab_config_intent_package loader transfer must remain false")
    http_target = config_intent.get("http_chain_target", {})
    require("menu.ipxe" in http_target.get("menu_url", ""), "isolated_lab_config_intent_package HTTP menu target missing")
    require(http_target.get("current_reference_only") is True, "isolated_lab_config_intent_package HTTP target must be reference only")
    require(http_target.get("changes_http_topology") is False, "isolated_lab_config_intent_package HTTP topology must not change")
    require(http_target.get("reachable_from_pxe_path_tested") is False, "isolated_lab_config_intent_package PXE reachability must remain untested")
    for key in (
        "intent_chain",
        "client_validation_checklist",
        "manual_authorization_gates",
        "rollback_triggers",
        "blocked_actions",
        "next_gate",
    ):
        require(
            isinstance(config_intent.get(key), list) and bool(config_intent[key]),
            f"isolated_lab_config_intent_package.{key} must be a non-empty list",
        )
    for item in config_intent.get("client_validation_checklist", []):
        require(item.get("passed") is False, f"isolated_lab_config_intent_package checklist {item.get('id')} must remain unpassed")
        require(item.get("observed") == "", f"isolated_lab_config_intent_package checklist {item.get('id')} must not include observations")
    gates_text = " ".join(config_intent.get("manual_authorization_gates", []))
    for token in ("research_agent", "network_safety_agent", "security_audit_agent", "project_decision_agent", "user_manual"):
        require(token in gates_text, f"isolated_lab_config_intent_package missing gate token {token}")
    forbidden_config_keys = {
        "command",
        "commands",
        "cmd",
        "run",
        "exec",
        "shell",
        "script",
        "scripts",
        "apply",
        "apply_script",
        "deploy",
        "start",
        "stop",
        "restart",
        "enable",
        "disable",
        "open_port",
        "write_file",
        "config_file",
        "generated_config",
        "compose_yaml",
        "dnsmasq_conf",
        "tftpd_conf",
        "router_command",
    }
    allowed_config_keys = {
        "command_execution_allowed",
        "raw_commands_included",
        "config_generation_allowed",
        "service_start_allowed",
    }
    for key in collect_keys(config_intent):
        require(
            key not in forbidden_config_keys or key in allowed_config_keys,
            f"isolated_lab_config_intent_package contains forbidden config key: {key}",
        )
    forbidden_value_tokens = (
        "dnsmasq",
        "tftpd",
        "dhcp-range",
        "dhcp-boot",
        "pxe-service",
        "enable-tftp",
        "docker compose",
        "iptables",
        "nft ",
        "ufw",
        "ip route",
        "nmcli",
    )
    config_values_text = "\n".join(collect_string_values(config_intent)).lower()
    for token in forbidden_value_tokens:
        require(token not in config_values_text, f"isolated_lab_config_intent_package contains forbidden value token: {token}")
    config_text = " ".join(
        config_intent.get("intent_chain", [])
        + config_intent.get("rollback_triggers", [])
        + config_intent.get("blocked_actions", [])
        + config_intent.get("next_gate", [])
    )
    for token in ("Proxy" + "D" + "HCP", "TF" + "TP", "UDP", "production LAN"):
        require(token in config_text, f"isolated_lab_config_intent_package must preserve blocked wording for {token}")

    require(
        source_skeleton.get("schema_version") == "phase3-isolated-lab-source-skeleton.v1",
        "isolated_lab_source_skeleton_package schema mismatch",
    )
    require(source_skeleton.get("phase") == "3.13", "isolated_lab_source_skeleton_package phase mismatch")
    require(
        source_skeleton.get("package_kind") == "isolated_lab_boot_services_source_skeleton",
        "isolated_lab_source_skeleton_package kind mismatch",
    )
    require(source_skeleton.get("mode") == "readonly_source_skeleton", "isolated_lab_source_skeleton_package mode mismatch")
    require(source_skeleton.get("status") == "not_runnable", "isolated_lab_source_skeleton_package status mismatch")
    require(source_skeleton.get("read_only") is True, "isolated_lab_source_skeleton_package.read_only must be true")
    require(source_skeleton.get("fixture_only") is True, "isolated_lab_source_skeleton_package.fixture_only must be true")
    require(source_skeleton.get("offline_package_only") is True, "isolated_lab_source_skeleton_package.offline_package_only must be true")
    require(source_skeleton.get("source_kind") == "fixture_model_only", "isolated_lab_source_skeleton_package source_kind mismatch")
    require(source_skeleton.get("request_is_authorization") is False, "isolated_lab_source_skeleton_package request_is_authorization must be false")
    for key in (
        "enabled",
        "authorized",
        "runtime_enabled",
        "runtime_available",
        "service_start_allowed",
        "service_started",
        "command_execution_allowed",
        "raw_commands_included",
        "config_generation_allowed",
        "config_files_generated",
        "write_api_available",
        "compose_integration_allowed",
        "compose_change_allowed",
        "docker_compose_modified",
        "router_change_allowed",
        "router_config_generation_allowed",
        "gateway_change_allowed",
        "firewall_change_allowed",
        "production_lan_allowed",
        "production_lan_testing_allowed",
        "host_network_allowed",
        "privileged_container_allowed",
        "task_consumption_allowed",
        "packet_send_allowed",
        "packet_capture_allowed",
        "packet_capture_started",
        "active_probe_allowed",
        "network_probe_started",
        "boot_tested",
    ):
        require_false(source_skeleton, key, "boot-entry.isolated_lab_source_skeleton_package")
    for key in (
        "forbidden_runtime_import",
        "requires_future_design_review",
        "requires_network_safety_review",
        "requires_security_audit_review",
        "requires_project_decision",
    ):
        require(source_skeleton.get(key) is True, f"isolated_lab_source_skeleton_package.{key} must be true")
    source_service_state = source_skeleton.get("network_service_state", {})
    for key in (
        "d" + "hcp_server_enabled",
        "d" + "hcp_lease_assignment_allowed",
        "proxy" + "d" + "hcp_enabled",
        "tf" + "tp_enabled",
        "udp_67_open",
        "udp_69_open",
        "udp_4011_open",
        "udp_67_enabled",
        "udp_69_enabled",
        "udp_4011_enabled",
        "udp_67_listening",
        "udp_69_listening",
        "udp_4011_listening",
        "udp_67_mapped",
        "udp_69_mapped",
        "udp_4011_mapped",
        "host_network_allowed",
        "privileged_container_allowed",
    ):
        require_false(source_service_state, key, "boot-entry.isolated_lab_source_skeleton_package.network_service_state")
    for key in (
        "runtime_entrypoints",
        "compose_services",
        "generated_files",
        "opened_ports",
        "task_consumers",
        "network_listeners",
    ):
        require(source_skeleton.get(key) == [], f"isolated_lab_source_skeleton_package.{key} must be empty")
    source_services = source_skeleton.get("intended_services", {})
    for key in ("proxy_" + "d" + "hcp_metadata_model", "tf" + "tp_loader_model"):
        service = source_services.get(key, {})
        require(service.get("state") == "source_placeholder_only", f"isolated_lab_source_skeleton_package.{key} state mismatch")
        require(service.get("enabled") is False, f"isolated_lab_source_skeleton_package.{key}.enabled must be false")
        require(service.get("startable") is False, f"isolated_lab_source_skeleton_package.{key}.startable must be false")
    for item in source_skeleton.get("intended_ports", []):
        require(item.get("port") in {67, 69, 4011}, "isolated_lab_source_skeleton_package port allowlist mismatch")
        require(item.get("protocol") == "udp", "isolated_lab_source_skeleton_package intended ports must be UDP")
        require(item.get("observed_listening") is False, f"UDP {item.get('port')} must not be observed listening")
        require(item.get("desired_listening") is False, f"UDP {item.get('port')} desired_listening must be false")
        require(item.get("model_only") is True, f"UDP {item.get('port')} must remain model-only")
    offline_model = source_skeleton.get("offline_protocol_model", {})
    metadata_intent = offline_model.get("boot_metadata_intent", {})
    for key in ("assigns_lease", "includes_gateway", "includes_dns", "includes_subnet", "includes_route"):
        require_false(metadata_intent, key, "boot-entry.isolated_lab_source_skeleton_package.offline_protocol_model.boot_metadata_intent")
    require(
        metadata_intent.get("candidate_bootfile") in {"", "snponly.efi", "ipxe.efi"},
        "isolated_lab_source_skeleton_package candidate bootfile mismatch",
    )
    transfer_scope = offline_model.get("loader_transfer_scope", {})
    require(transfer_scope.get("service_enabled") is False, "isolated_lab_source_skeleton_package transfer service must be false")
    require(transfer_scope.get("port_exposed") is False, "isolated_lab_source_skeleton_package transfer port must be false")
    require(transfer_scope.get("root_path") == "", "isolated_lab_source_skeleton_package must not bind a transfer root path")
    for item in transfer_scope.get("allowlist", []):
        require(item.get("name") in {"snponly.efi", "ipxe.efi"}, "isolated_lab_source_skeleton_package allowlist mismatch")
        require(item.get("reviewed") is True, "isolated_lab_source_skeleton_package allowlist must be reviewed")
        require(item.get("served") is False, "isolated_lab_source_skeleton_package allowlist must not be served")
    http_model = offline_model.get("http_chain_target", {})
    require("menu.ipxe" in http_model.get("menu_url", ""), "isolated_lab_source_skeleton_package HTTP target missing")
    require(http_model.get("reachable_via_pxe_tested") is False, "isolated_lab_source_skeleton_package PXE reachability must be untested")
    require(http_model.get("production_lan_supported") is False, "isolated_lab_source_skeleton_package production LAN support must be false")
    fixture_ref = source_skeleton.get("offline_fixture_reference", {})
    require(
        fixture_ref.get("path") == "config/synaboot/phase3.13-isolated-lab-source-skeleton.disabled.json",
        "isolated_lab_source_skeleton_package fixture path mismatch",
    )
    require(fixture_ref.get("fixture_only") is True, "isolated_lab_source_skeleton_package fixture_only reference required")
    require(fixture_ref.get("loaded_at_runtime") is False, "isolated_lab_source_skeleton_package fixture must not be loaded at runtime")
    require(fixture_ref.get("contains_real_client_data") is False, "isolated_lab_source_skeleton_package fixture must not include real client data")
    for item in source_skeleton.get("client_evidence_fixture", []):
        require(item.get("passed") is False, f"isolated_lab_source_skeleton_package fixture {item.get('id')} must remain unpassed")
        require(item.get("observed") == "", f"isolated_lab_source_skeleton_package fixture {item.get('id')} must not include observations")
    source_gate_text = " ".join(source_skeleton.get("authorization_gates", []))
    for token in ("research_agent", "network_safety_agent", "security_audit_agent", "project_decision_agent", "manual_isolated_lab"):
        require(token in source_gate_text, f"isolated_lab_source_skeleton_package missing gate token {token}")
    forbidden_source_keys = {
        "command",
        "commands",
        "cmd",
        "run",
        "exec",
        "shell",
        "script",
        "scripts",
        "apply",
        "apply_script",
        "deploy",
        "start",
        "stop",
        "restart",
        "enable",
        "disable",
        "open_port",
        "write_file",
        "config_file",
        "generated_config",
        "compose_yaml",
        "dnsmasq_conf",
        "tftpd_conf",
        "router_command",
        "systemd_unit",
        "entrypoint",
        "daemon",
        "listener",
        "bind_address",
        "bind_port",
        "socket",
        "handler",
        "server",
    }
    allowed_source_keys = {
        "command_execution_allowed",
        "raw_commands_included",
        "config_generation_allowed",
        "service_start_allowed",
        "runtime_enabled",
        "write_api_available",
        "compose_integration_allowed",
        "runtime_entrypoints",
        "network_listeners",
    }
    for key in collect_keys(source_skeleton):
        require(
            key not in forbidden_source_keys or key in allowed_source_keys,
            f"isolated_lab_source_skeleton_package contains forbidden source key: {key}",
        )
    forbidden_source_value_tokens = (
        "dnsmasq",
        "tftpd",
        "dhcp-range",
        "dhcp-boot",
        "pxe-service",
        "enable-tftp",
        "docker compose",
        "network_mode: host",
        "privileged: true",
        "iptables",
        "nft ",
        "ufw",
        "firewall-cmd",
        "ip route",
        "nmcli",
        "systemctl",
        "service start",
        "listen",
        "bind(",
        "bind:",
        "0.0.0.0",
        "udp/67 open",
        "udp/69 open",
        "udp/4011 open",
        "67:67",
        "69:69",
        "4011:4011",
    )
    source_values_text = "\n".join(collect_string_values(source_skeleton)).lower()
    for token in forbidden_source_value_tokens:
        require(token not in source_values_text, f"isolated_lab_source_skeleton_package contains forbidden value token: {token}")
    source_text = " ".join(
        source_skeleton.get("blocked_actions", [])
        + source_skeleton.get("next_gate", [])
    )
    for token in ("Proxy" + "D" + "HCP", "TF" + "TP", "UDP", "production LAN"):
        require(token in source_text, f"isolated_lab_source_skeleton_package must preserve blocked wording for {token}")
    require(PHASE3_SOURCE_SKELETON_FIXTURE.is_file(), "Phase 3.13 source skeleton fixture is missing")
    require(not PHASE3_SOURCE_SKELETON_FIXTURE.is_symlink(), "Phase 3.13 source skeleton fixture must not be a symlink")
    require(not (PHASE3_SOURCE_SKELETON_FIXTURE.stat().st_mode & 0o111), "Phase 3.13 source skeleton fixture must not be executable")
    fixture_text = PHASE3_SOURCE_SKELETON_FIXTURE.read_text(encoding="utf-8")
    require(not fixture_text.startswith("#!"), "Phase 3.13 source skeleton fixture must not contain a shebang")
    fixture_data = json.loads(fixture_text)
    require(fixture_data.get("schema_version") == "phase3-isolated-lab-source-skeleton-fixture.v1", "Phase 3.13 fixture schema mismatch")
    require(fixture_data.get("status") == "not_runnable", "Phase 3.13 fixture must stay not_runnable")
    require(fixture_data.get("fixture_only") is True, "Phase 3.13 fixture must stay fixture_only")
    require(fixture_data.get("offline_package_only") is True, "Phase 3.13 fixture must stay offline_package_only")
    require(fixture_data.get("loaded_at_runtime") is False, "Phase 3.13 fixture must not load at runtime")

    require(
        manual_gate.get("schema_version") == "phase3-isolated-lab-manual-declaration-gate.v1",
        "isolated_lab_manual_declaration_gate schema mismatch",
    )
    require(manual_gate.get("phase") == "3.14", "isolated_lab_manual_declaration_gate phase mismatch")
    require(
        manual_gate.get("gate_kind") == "isolated_lab_manual_declaration_gate",
        "isolated_lab_manual_declaration_gate kind mismatch",
    )
    require(manual_gate.get("mode") == "readonly_manual_declaration_gate", "isolated_lab_manual_declaration_gate mode mismatch")
    require(
        manual_gate.get("template_mode") == "readonly_manual_declaration_template",
        "isolated_lab_manual_declaration_gate template mode mismatch",
    )
    require(manual_gate.get("status") == "missing_facts", "isolated_lab_manual_declaration_gate status mismatch")
    require(manual_gate.get("submission_status") == "not_submitted", "isolated_lab_manual_declaration_gate submission mismatch")
    require(manual_gate.get("authorization_status") == "not_authorized", "isolated_lab_manual_declaration_gate authorization mismatch")
    require(manual_gate.get("read_only") is True, "isolated_lab_manual_declaration_gate.read_only must be true")
    require(manual_gate.get("template_only") is True, "isolated_lab_manual_declaration_gate.template_only must be true")
    for key in (
        "request_is_authorization",
        "collects_user_input",
        "stores_user_input",
        "contains_real_client_data",
        "contains_real_mac",
        "contains_real_ip",
        "contains_customer_info",
        "secrets_included",
        "raw_commands_included",
        "config_snippets_included",
        "write_api_available",
        "write_api_allowed",
        "database_write_allowed",
        "task_consumption_allowed",
        "config_generation_allowed",
        "config_files_generated",
        "command_execution_allowed",
        "service_start_allowed",
        "service_started",
        "runtime_enabled",
        "runtime_unlock_allowed",
        "enabled",
        "authorized",
        "production_lan_allowed",
        "production_lan_testing_allowed",
        "gateway_change_allowed",
        "route_change_allowed",
        "firewall_change_allowed",
        "dns_change_allowed",
        "packet_capture_allowed",
        "packet_capture_started",
        "network_probe_allowed",
        "network_probe_started",
        "active_probe_allowed",
        "command_execution_started",
        "compose_change_allowed",
        "host_network_allowed",
        "privileged_container_allowed",
        "router_read_allowed",
        "router_write_allowed",
        "tplink_read_allowed",
        "tplink_write_allowed",
        "openwrt_read_allowed",
        "openwrt_write_allowed",
        "boot_tested",
    ):
        require_false(manual_gate, key, "boot-entry.isolated_lab_manual_declaration_gate")
    manual_service_state = manual_gate.get("network_service_state", {})
    for key in (
        "d" + "hcp_server_enabled",
        "d" + "hcp_enabled",
        "proxy" + "d" + "hcp_enabled",
        "tf" + "tp_enabled",
        "udp_67_open",
        "udp_69_open",
        "udp_4011_open",
        "udp_67_opened",
        "udp_69_opened",
        "udp_4011_opened",
        "udp_67_mapped",
        "udp_69_mapped",
        "udp_4011_mapped",
        "udp_67_listening",
        "udp_69_listening",
        "udp_4011_listening",
    ):
        require_false(manual_service_state, key, "boot-entry.isolated_lab_manual_declaration_gate.network_service_state")
    manual_facts = manual_gate.get("required_manual_facts", [])
    require(isinstance(manual_facts, list) and bool(manual_facts), "isolated_lab_manual_declaration_gate facts required")
    fact_keys = []
    for item in manual_facts:
        require(item.get("required") is True, f"isolated_lab_manual_declaration_gate fact {item.get('key')} must be required")
        require(item.get("status") == "missing", f"isolated_lab_manual_declaration_gate fact {item.get('key')} must remain missing")
        require(item.get("template_only") is True, f"isolated_lab_manual_declaration_gate fact {item.get('key')} must be template only")
        require(item.get("stores_value") is False, f"isolated_lab_manual_declaration_gate fact {item.get('key')} must not store values")
        fact_keys.append(item.get("key"))
    missing_facts = manual_gate.get("missing_facts", [])
    require(isinstance(missing_facts, list) and bool(missing_facts), "isolated_lab_manual_declaration_gate missing facts required")
    require(set(missing_facts) == set(fact_keys), "isolated_lab_manual_declaration_gate missing facts must match required facts")
    for item in manual_gate.get("boot_path_checklist", []):
        require(item.get("observed") == "", f"isolated_lab_manual_declaration_gate checklist {item.get('id')} must not include observations")
        require(item.get("passed") is False, f"isolated_lab_manual_declaration_gate checklist {item.get('id')} must remain unpassed")
    manual_gate_text = " ".join(manual_gate.get("authorization_gates", []))
    for token in ("research_agent", "network_safety_agent", "security_audit_agent", "project_decision_agent"):
        require(token in manual_gate_text, f"isolated_lab_manual_declaration_gate missing authorization gate {token}")
    allowed_manual_keys = {
        "contains_real_client_data",
        "contains_real_mac",
        "contains_real_ip",
        "contains_customer_info",
        "secrets_included",
        "raw_commands_included",
        "config_snippets_included",
        "write_api_available",
        "dhcp_server_enabled",
        "dhcp_enabled",
        "proxydhcp_enabled",
        "tftp_enabled",
        "service_start_allowed",
    }
    forbidden_manual_keys = {
        "mac",
        "mac_address",
        "client_mac",
        "ip",
        "ip_address",
        "client_ip",
        "customer",
        "customer_name",
        "hostname",
        "asset_tag",
        "serial_number",
        "real_client_data",
        "token",
        "password",
        "passwd",
        "secret",
        "private_key",
        "command",
        "commands",
        "cmd",
        "run",
        "exec",
        "shell",
        "script",
        "scripts",
        "apply",
        "apply_script",
        "deploy",
        "start",
        "stop",
        "restart",
        "enable",
        "disable",
        "open_port",
        "write_file",
        "config_file",
        "generated_config",
        "config_snippet",
        "compose_yaml",
        "dnsmasq_conf",
        "tftpd_conf",
        "router_command",
    }
    for key in collect_keys(manual_gate):
        require(
            key in allowed_manual_keys or key not in forbidden_manual_keys,
            f"isolated_lab_manual_declaration_gate contains forbidden key: {key}",
        )
    forbidden_manual_value_tokens = (
        "dnsmasq",
        "tftpd",
        "dhcp-range",
        "dhcp-boot",
        "pxe-service",
        "enable-tftp",
        "docker compose",
        "network_mode: host",
        "privileged: true",
        "iptables",
        "nft",
        "ufw",
        "firewall-cmd",
        "ip route",
        "nmcli",
        "systemctl",
        "service start",
        "curl",
        "wget",
        "ssh",
        "scp",
        "token=",
        "password=",
        "begin private key",
        "mac:",
        "ip:",
        "192.168.",
        "10.",
        "172.16.",
        "client serial",
        "customer name",
    )
    manual_values_text = "\n".join(collect_string_values(manual_gate)).lower()
    for token in forbidden_manual_value_tokens:
        require(token not in manual_values_text, f"isolated_lab_manual_declaration_gate contains forbidden value token: {token}")

    require(
        runtime_plan.get("schema_version") == "phase3-isolated-lab-runtime-authorization-plan.v1",
        "isolated_lab_runtime_authorization_plan schema mismatch",
    )
    require(runtime_plan.get("phase") == "3.15", "isolated_lab_runtime_authorization_plan phase mismatch")
    require(
        runtime_plan.get("plan_id") == "isolated_lab_runtime_authorization_plan",
        "isolated_lab_runtime_authorization_plan id mismatch",
    )
    require(
        runtime_plan.get("status") == "blocked_until_manual_facts_and_approvals",
        "isolated_lab_runtime_authorization_plan status mismatch",
    )
    require(runtime_plan.get("read_only") is True, "isolated_lab_runtime_authorization_plan.read_only must be true")
    require(runtime_plan.get("source") == "static_pre_review_plan", "isolated_lab_runtime_authorization_plan source mismatch")
    require(
        runtime_plan.get("depends_on_manual_gate_phase") == "3.14",
        "isolated_lab_runtime_authorization_plan manual gate dependency mismatch",
    )
    for key in (
        "request_is_authorization",
        "authorization_granted",
        "runtime_enabled",
        "runtime_start_allowed",
        "service_start_allowed",
        "service_started",
        "config_generation_allowed",
        "config_files_generated",
        "write_api_available",
        "write_api_allowed",
        "database_write_allowed",
        "task_consumption_allowed",
        "production_lan_allowed",
        "production_lan_testing_allowed",
        "boot_tested",
        "observations_recorded",
        "packet_capture_allowed",
        "packet_capture_started",
        "network_probe_allowed",
        "network_probe_started",
        "active_probe_allowed",
        "command_execution_allowed",
        "host_network_allowed",
        "privileged_container_allowed",
        "router_change_allowed",
        "gateway_change_allowed",
        "routing_change_allowed",
        "firewall_change_allowed",
        "dns_change_allowed",
        "normal_dhcp_leases_enabled",
        "manual_gate_ready",
    ):
        require_false(runtime_plan, key, "boot-entry.isolated_lab_runtime_authorization_plan")
    runtime_service_state = runtime_plan.get("network_service_state", {})
    for key in (
        "d" + "hcp_server_enabled",
        "proxy" + "d" + "hcp_enabled",
        "tf" + "tp_enabled",
        "udp_67_open",
        "udp_69_open",
        "udp_4011_open",
        "udp_67_listening",
        "udp_69_listening",
        "udp_4011_listening",
        "udp_67_mapped",
        "udp_69_mapped",
        "udp_4011_mapped",
    ):
        require_false(runtime_service_state, key, "boot-entry.isolated_lab_runtime_authorization_plan.network_service_state")
    require(
        set(runtime_plan.get("missing_manual_facts", [])) == set(manual_gate.get("missing_facts", [])),
        "isolated_lab_runtime_authorization_plan must inherit manual gate missing facts",
    )
    approvals = runtime_plan.get("required_approvals", [])
    require(isinstance(approvals, list) and len(approvals) >= 5, "isolated_lab_runtime_authorization_plan approvals required")
    approval_text = " ".join(item.get("role", "") + " " + item.get("status", "") for item in approvals)
    for token in ("research_agent", "network_safety_agent", "security_audit_agent", "project_decision_agent", "user_manual_confirmation"):
        require(token in approval_text, f"isolated_lab_runtime_authorization_plan missing approval {token}")
    for item in runtime_plan.get("runtime_scope_candidates", []):
        require(item.get("status") == "candidate_only", f"isolated_lab_runtime_authorization_plan scope {item.get('id')} status mismatch")
        require(item.get("allowed_to_execute") is False, f"isolated_lab_runtime_authorization_plan scope {item.get('id')} must not execute")
    for key in (
        "explicit_non_goals",
        "transition_requirements",
        "rollback_conditions",
        "boot_evidence_requirements",
        "future_research_items",
        "next_gate",
    ):
        require(
            isinstance(runtime_plan.get(key), list) and bool(runtime_plan[key]),
            f"isolated_lab_runtime_authorization_plan.{key} must be a non-empty list",
        )
    for item in runtime_plan.get("boot_evidence_requirements", []):
        require(item.get("observed") == "", f"isolated_lab_runtime_authorization_plan evidence {item.get('id')} must not include observations")
        require(item.get("passed") is False, f"isolated_lab_runtime_authorization_plan evidence {item.get('id')} must remain unpassed")
    runtime_text = " ".join(
        runtime_plan.get("explicit_non_goals", [])
        + runtime_plan.get("transition_requirements", [])
        + runtime_plan.get("rollback_conditions", [])
        + runtime_plan.get("next_gate", [])
    )
    for token in ("runtime authorization", "ordinary client leases", "production", "reviewer approvals"):
        require(token in runtime_text, f"isolated_lab_runtime_authorization_plan must preserve blocked wording for {token}")
    forbidden_runtime_value_tokens = (
        "dnsmasq",
        "tftpd",
        "dhcp-range",
        "dhcp-boot",
        "pxe-service",
        "enable-tftp",
        "docker compose",
        "network_mode: host",
        "privileged: true",
        "iptables",
        "nft",
        "ufw",
        "firewall-cmd",
        "ip route",
        "nmcli",
        "systemctl",
        "service start",
        "curl",
        "wget",
        "ssh",
        "scp",
        "token=",
        "password=",
        "begin private key",
        "mac:",
        "ip:",
        "192.168.",
        "10.",
        "172.16.",
        "client serial",
        "customer name",
    )
    runtime_values_text = "\n".join(collect_string_values(runtime_plan)).lower()
    for token in forbidden_runtime_value_tokens:
        require(token not in runtime_values_text, f"isolated_lab_runtime_authorization_plan contains forbidden value token: {token}")

    require(
        runtime_draft.get("schema_version") == "phase3-isolated-lab-runtime-authorization-draft.v1",
        "isolated_lab_runtime_authorization_draft schema mismatch",
    )
    require(runtime_draft.get("phase") == "3.16", "isolated_lab_runtime_authorization_draft phase mismatch")
    require(
        runtime_draft.get("draft_id") == "isolated_lab_runtime_authorization_draft",
        "isolated_lab_runtime_authorization_draft id mismatch",
    )
    require(
        runtime_draft.get("status") == "draft_blocked_until_evidence_and_approvals",
        "isolated_lab_runtime_authorization_draft status mismatch",
    )
    require(runtime_draft.get("read_only") is True, "isolated_lab_runtime_authorization_draft.read_only must be true")
    require(
        runtime_draft.get("source") == "static_read_only_authorization_draft",
        "isolated_lab_runtime_authorization_draft source mismatch",
    )
    require(runtime_draft.get("depends_on_manual_gate_phase") == "3.14", "isolated_lab_runtime_authorization_draft manual dependency mismatch")
    require(runtime_draft.get("depends_on_plan_phase") == "3.15", "isolated_lab_runtime_authorization_draft plan dependency mismatch")
    for key in (
        "is_authorization_result",
        "is_state_transition_event",
        "is_runtime_config_source",
        "request_is_authorization",
        "authorized",
        "authorization_granted",
        "manual_facts_cleared",
        "runtime_enabled",
        "runtime_start_allowed",
        "service_start_allowed",
        "service_started",
        "config_generation_allowed",
        "config_files_generated",
        "write_api_available",
        "write_api_allowed",
        "database_write_allowed",
        "task_consumption_allowed",
        "production_lan_allowed",
        "production_lan_boot_allowed",
        "production_lan_testing_allowed",
        "boot_tested",
        "observations_recorded",
        "packet_capture_allowed",
        "packet_capture_started",
        "network_probe_allowed",
        "network_probe_started",
        "command_execution_allowed",
        "host_network",
        "host_network_allowed",
        "privileged",
        "privileged_container_allowed",
        "tp_link_modified",
        "openwrt_modified",
        "routing_modified",
        "gateway_modified",
        "firewall_modified",
        "dns_modified",
        "normal_dhcp_leases_enabled",
    ):
        require_false(runtime_draft, key, "boot-entry.isolated_lab_runtime_authorization_draft")
    draft_service_state = runtime_draft.get("network_service_state", {})
    for key in (
        "d" + "hcp_server_enabled",
        "proxy" + "d" + "hcp_enabled",
        "tf" + "tp_enabled",
        "udp_67_open",
        "udp_69_open",
        "udp_4011_open",
        "udp_67_listening",
        "udp_69_listening",
        "udp_4011_listening",
        "udp_67_mapped",
        "udp_69_mapped",
        "udp_4011_mapped",
    ):
        require_false(draft_service_state, key, "boot-entry.isolated_lab_runtime_authorization_draft.network_service_state")
    for key in (
        "required_evidence",
        "required_approvals",
        "isolated_scope_requirements",
        "rollback_plan_requirements",
        "boot_evidence_collection_plan",
        "explicit_non_goals",
        "transition_requirements",
        "next_gate",
    ):
        require(
            isinstance(runtime_draft.get(key), list) and bool(runtime_draft[key]),
            f"isolated_lab_runtime_authorization_draft.{key} must be a non-empty list",
        )
    for item in runtime_draft.get("required_evidence", []):
        require(item.get("status") == "missing", f"isolated_lab_runtime_authorization_draft evidence {item.get('id')} must remain missing")
        require(item.get("stores_value") is False, f"isolated_lab_runtime_authorization_draft evidence {item.get('id')} must not store values")
    draft_approval_text = " ".join(item.get("role", "") + " " + item.get("status", "") for item in runtime_draft.get("required_approvals", []))
    for token in ("network_safety_agent", "security_audit_agent", "project_decision_agent", "user_manual_confirmation"):
        require(token in draft_approval_text, f"isolated_lab_runtime_authorization_draft missing approval {token}")
    for item in runtime_draft.get("boot_evidence_collection_plan", []):
        require(item.get("observed") == "", f"isolated_lab_runtime_authorization_draft boot evidence {item.get('id')} must not include observations")
        require(item.get("passed") is False, f"isolated_lab_runtime_authorization_draft boot evidence {item.get('id')} must remain unpassed")
    draft_text = " ".join(
        runtime_draft.get("explicit_non_goals", [])
        + runtime_draft.get("transition_requirements", [])
        + runtime_draft.get("next_gate", [])
    )
    for token in ("runtime authorization", "state transition", "runtime configuration source", "production LAN"):
        require(token in draft_text, f"isolated_lab_runtime_authorization_draft must preserve blocked wording for {token}")
    runtime_draft_values_text = "\n".join(collect_string_values(runtime_draft)).lower()
    for token in forbidden_runtime_value_tokens:
        require(
            token not in runtime_draft_values_text,
            f"isolated_lab_runtime_authorization_draft contains forbidden value token: {token}",
        )

    require(isolated_plan.get("phase") == "3.5", "isolated_validation_plan phase mismatch")
    require(isolated_plan.get("mode") == "readonly_plan_only", "isolated_validation_plan mode mismatch")
    require(
        isolated_plan.get("status") == "blocked_until_isolated_lab_approved",
        "isolated_validation_plan status mismatch",
    )
    require(isolated_plan.get("read_only") is True, "isolated_validation_plan.read_only must be true")
    require_false(isolated_plan, "runtime_enabled", "boot-entry.isolated_validation_plan")
    require_false(isolated_plan, "production_lan_allowed", "boot-entry.isolated_validation_plan")
    require(isolated_plan.get("requires_manual_authorization") is True, "isolated_validation_plan requires manual authorization")
    invariants = isolated_plan.get("safety_invariants", {})
    require(invariants.get("primary_dhcp_invariant") == "192.168.1.1", "isolated_validation_plan primary DHCP invariant mismatch")
    require(invariants.get("default_gateway_invariant") == "192.168.1.4", "isolated_validation_plan gateway invariant mismatch")
    require(invariants.get("udp_ports_allowed") == [], "isolated_validation_plan must not allow UDP boot ports")
    for key in (
        "d" + "hcp_server_enabled",
        "proxy" + "d" + "hcp_enabled",
        "tf" + "tp_enabled",
        "assigns_" + "d" + "hcp_leases",
        "changes_gateway",
    ):
        require_false(invariants, key, "boot-entry.isolated_validation_plan.safety_invariants")
    for key in (
        "target_chain",
        "environment_requirements",
        "allowed_preparation",
        "forbidden_actions",
        "required_evidence_before_lab",
        "success_criteria_for_future_lab",
        "exit_conditions",
    ):
        require(
            isinstance(isolated_plan.get(key), list) and bool(isolated_plan[key]),
            f"isolated_validation_plan.{key} must be a non-empty list",
        )

    forbidden_text = " ".join(isolated_plan.get("forbidden_actions", []))
    sensitive_tokens = (
        "D" + "HCP",
        "Proxy" + "D" + "HCP",
        "TF" + "TP",
        "UDP 67",
        "69",
        "4011",
        "production LAN",
    )
    for token in sensitive_tokens:
        require(token in forbidden_text, f"isolated_validation_plan.forbidden_actions must mention {token}")

    safety = boot_entry.get("safety", {})
    for key in (
        "d" + "hcp_server_enabled",
        "proxy" + "d" + "hcp_enabled",
        "tf" + "tp_enabled",
        "assigns_" + "d" + "hcp_leases",
        "changes_gateway",
    ):
        require_false(safety, key, "boot-entry.safety")

    services = boot_entry.get("services", {})
    for service_name in ("proxy_" + "d" + "hcp", "tf" + "tp"):
        service = services.get(service_name, {})
        require_false(service, "enabled", f"boot-entry.services.{service_name}")
        require_false(service, "available_in_phase", f"boot-entry.services.{service_name}")

    print("APPROVED: Phase 3 gates remain readonly and blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
