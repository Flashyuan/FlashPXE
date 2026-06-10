# SynaBoot

Internal LAN iPXE HTTP Boot and OS image deployment platform.

## Phase 1 Principle

Zero network intrusion. No DHCP, no ProxyDHCP, no TFTP, no router changes.

Users boot with iPXE USB/ISO/EFI or manual UEFI HTTP Boot and load:

```text
http://<SERVER_IP>:8080/boot/menu.ipxe
```

See `PLAN.md` and `AGENTS.md`.
