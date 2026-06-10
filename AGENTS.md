# AGENTS.md — SynaBoot Codex Instructions

This repository builds SynaBoot, an internal LAN iPXE HTTP Boot and OS image deployment platform.

## Absolute Safety Priority

This project is deployed inside an existing production LAN.

The current LAN already has a DHCP server.

The project MUST NOT change, replace, intercept, or supplement existing LAN network services.

## Forbidden Actions

The following actions are strictly forbidden:

- Installing or enabling DHCP server
- Enabling ProxyDHCP
- Running dnsmasq in DHCP or ProxyDHCP mode
- Running TFTP server
- Opening UDP 67, 68, 69, or 4011
- Changing router, OpenWrt, TP-Link, switch, AP, VLAN, gateway, DNS, route, or firewall configuration
- Running iptables, nftables, ufw, firewalld, route, ip route, nmcli network changes
- Using Docker `network_mode: host`
- Using Docker `privileged: true`
- Mounting host `/`, `/etc`, or `/var/run/docker.sock`
- Using public SaaS or third-party upload for internal ISO/images

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

## Phase 1 Network Model

Phase 1 is zero-intrusion.

Do not implement DHCP, ProxyDHCP, or TFTP.

Users boot using:

- iPXE USB/ISO/EFI
- or manual UEFI HTTP Boot if supported

The iPXE menu loads from:

```text
http://<SERVER_IP>:8080/boot/menu.ipxe
```

## Required Subagents

Use project custom agents from `.codex/agents/`.

Required agents:

- network_safety_agent
- architecture_agent
- pxe_agent
- storage_agent
- image_factory_agent
- webui_agent
- security_audit_agent

Before making network-related changes, spawn network_safety_agent.

After implementation, spawn both network_safety_agent and security_audit_agent for final review.

## Coding Rules

- Prefer simple, maintainable code.
- Keep all services Docker Compose friendly.
- Do not require public internet at runtime.
- Do not depend on external CDN for UI assets.
- Keep image paths under `./data/images`.
- Keep generated boot files under `./data/boot`.
- All scripts must be idempotent.
- All destructive operations must require explicit user confirmation.
- Never auto-format or partition disks from this platform in Phase 1.

## Validation Commands

Prefer local safe commands:

```bash
bash scripts/preflight/check-network-safety.sh
docker compose config
docker compose up -d
curl http://localhost:8080/
curl http://localhost:8080/boot/menu.ipxe
curl http://localhost:8080/images/
```

Do not run commands that alter LAN network behavior.
