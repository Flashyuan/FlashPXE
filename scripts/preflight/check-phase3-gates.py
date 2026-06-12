#!/usr/bin/env python3
"""校验 Phase 3 只读门禁字段，避免运行时能力被误读为已解锁。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
API_MAIN = ROOT / "apps" / "api" / "main.py"

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


def main() -> int:
    api = load_api_module()
    boot_entry = api.boot_entry_status()
    network_safety = api.network_safety_status()

    entry_gate = boot_entry.get("phase3_3_gate", {})
    safety_gate = network_safety.get("phase3_gate", {})
    feasibility = boot_entry.get("phase3_3_feasibility", {})

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
