# AGENTS.md — SynaBoot Codex Instructions

This repository builds SynaBoot, an internal LAN iPXE HTTP Boot and OS image deployment platform.

## Absolute Safety Priority

This project is deployed inside an existing production LAN.

The current LAN already has a DHCP server: TP-Link TL-ER6120T at `192.168.1.1`.

The production gateway is OpenWrt at `192.168.1.4`.

Phase 1/2 remain zero-intrusion. Phase 3 may introduce controlled boot integration,
but it MUST NOT interrupt LAN connectivity, replace the main DHCP server, or change
the default gateway.

## Forbidden Actions

The following actions are strictly forbidden:

- Installing or enabling DHCP server
- Replacing or disabling the TP-Link DHCP server at `192.168.1.1`
- Assigning normal DHCP leases from SynaBoot
- Changing the default gateway away from `192.168.1.4`
- Changing OpenWrt gateway, route, NAT, firewall, DNS forwarding, VLAN, switch, or AP configuration
- Running iptables, nftables, ufw, firewalld, route, ip route, nmcli network changes
- Using Docker `network_mode: host` by default
- Using Docker `privileged: true`
- Mounting host `/`, `/etc`, or `/var/run/docker.sock`
- Using public SaaS or third-party upload for internal ISO/images

Phase 3 controlled boot integration may allow these actions only after explicit
network_safety_agent and security_audit_agent approval plus project_decision_agent authorization:

- Adding DHCP boot options on the TP-Link router without changing leases, DNS, or gateway
- Running ProxyDHCP that does not assign IP addresses
- Running TFTP only for boot loaders under `./data/boot/loaders`
- Opening UDP 67, 69, or 4011 for boot integration

If any action may affect LAN communication, STOP and ask the network_safety_agent to review it.

## Project Scope

Build a Docker Compose deployable platform on Ubuntu 22.04:

- Web UI
- HTTP image repository
- iPXE HTTP Boot menu
- HotPE integration
- Windows/Linux image listing
- Optional Samba image sharing after preflight
- Image factory task framework
- Ubuntu autoinstall templates
- Windows external ADK/DISM task package templates

## Phase 1/2 Network Model

Phase 1 and Phase 2 are both zero-intrusion.

Do not implement DHCP, ProxyDHCP, or TFTP.

Users boot using:

- iPXE USB/ISO/EFI
- or manual UEFI HTTP Boot if supported

The iPXE menu loads from:

```text
http://<SERVER_IP>:18080/boot/menu.ipxe
```

## Phase 3 Network Boot Integration

Phase 3 targets automatic entry from firmware boot options:

- `UEFI: HTTP IPv4`
- `UEFI: PXE IPv4`
- `UEFI: HTTP IPv6`
- `UEFI: PXE IPv6`

Preferred implementation:

- Keep TP-Link `192.168.1.1` as the only DHCP lease server.
- Keep gateway option pointing to OpenWrt `192.168.1.4`.
- Use DHCP boot options, ProxyDHCP, TFTP chain loaders, and HTTP iPXE only for boot metadata.
- Verify whether TL-ER6120T can distinguish `HTTPClient` and `PXEClient` before relying on DHCP boot options.
- Keep ProxyDHCP/TFTP disabled by default and require project_decision_agent authorization after safety review before enabling.
- Treat IPv6 boot as experimental unless the LAN already has stable RA/DHCPv6.

## Required Subagents

Use project custom agents from `.codex/agents/`.

Required agents:

- research_agent
- project_decision_agent
- network_safety_agent
- architecture_agent
- boot_entry_agent
- storage_agent
- image_factory_agent
- webui_agent
- tutorial_docs_agent
- security_audit_agent
- git_audit_agent

Before Phase 3 design or implementation, invoke `research_agent` first to investigate
router firmware capabilities, DHCP/PXE/HTTP Boot protocol behavior, and any
uncertain external facts. Other agents should request research_agent input when
they need knowledge base or internet research.

When a decision affects project direction, milestone priority, implementation
strategy, or approved tradeoffs, trigger project_decision_agent. It may decide on
the user's behalf when network_safety_agent and security_audit_agent have not
blocked the option and the decision preserves normal LAN connectivity and
internet access.

Before making network-related changes, invoke `network_safety_agent`.

After implementation, invoke `network_safety_agent` and `security_audit_agent`
for final review when the change touches their risk areas.

In this document, "invoke" means: first read `docs/SUBAGENT_SESSION_POOL.md`,
reuse the registered role session with `resume_agent`/`send_input` when it is
available, and only create a replacement session after the registered session is
confirmed stale, unreachable, off-role, or explicitly replaced by the user. Do
not create a new same-role subagent merely because a previous review completed
or because a BLOCKED finding was fixed; send the fix back to the same reviewer.

After each completed feature or milestone, run git_audit_agent before considering
the work complete. The git audit must inspect the diff, secrets, network-impacting
changes, generated files, and test/validation results. If approved, it may create
a local commit on the current branch. GitHub push is treated as a version-control
operation, not a LAN-risk operation. After git_audit_agent approves the diff and
project_decision_agent approves the release direction, git_audit_agent may push
to the current GitHub branch without additional user confirmation.

## Coding Rules

- Prefer simple, maintainable code.
- Keep all services Docker Compose friendly.
- Do not require public internet at runtime.
- Do not depend on external CDN for UI assets.
- Keep image paths under `./data/images`.
- Keep generated boot files under `./data/boot`.
- All scripts must be idempotent.
- All destructive operations must require explicit user confirmation.
- Never auto-format or partition disks from this platform in Phase 1 or Phase 2.

## Validation Commands

Prefer local safe commands:

```bash
bash scripts/preflight/check-network-safety.sh
docker compose config
docker compose up -d
curl http://localhost:18080/
curl http://localhost:18080/boot/menu.ipxe
curl http://localhost:18080/images/
```

Do not run commands that alter LAN network behavior.
