#!/usr/bin/env bash
set -euo pipefail

SERVER_IP="${SERVER_IP:-192.168.1.168}"
SYNABOOT_PORT="${SYNABOOT_PORT:-8080}"
BOOT_DIR="${SYNABOOT_BOOT_DIR:-data/boot}"
IMAGES_DIR="${SYNABOOT_IMAGES_DIR:-data/images}"
MENU_FILE="${BOOT_DIR}/menu.ipxe"

mkdir -p "$BOOT_DIR"

hotpe_ready=false
if [[ -f "${IMAGES_DIR}/pe/hotpe/wimboot" && -f "${IMAGES_DIR}/pe/hotpe/bootmgr" && -f "${IMAGES_DIR}/pe/hotpe/BCD" && -f "${IMAGES_DIR}/pe/hotpe/boot.sdi" && -f "${IMAGES_DIR}/pe/hotpe/boot.wim" ]]; then
  hotpe_ready=true
fi

ubuntu_iso="$(find "${IMAGES_DIR}/linux/ubuntu-22.04.3" -maxdepth 1 -type f -name '*.iso' 2>/dev/null | sort | head -n 1 || true)"
ubuntu_ready=false
if [[ -n "$ubuntu_iso" && -f "${IMAGES_DIR}/linux/ubuntu-22.04.3/casper/vmlinuz" && -f "${IMAGES_DIR}/linux/ubuntu-22.04.3/casper/initrd" ]]; then
  ubuntu_ready=true
fi

cat > "$MENU_FILE" <<EOF
#!ipxe

set server-ip ${SERVER_IP}
set base-url http://\${server-ip}:${SYNABOOT_PORT}
set boot-url \${base-url}/boot
set image-url \${base-url}/images

:start
menu SynaBoot Phase 1 - HTTP Boot
item --gap --          === PE / Recovery ===
item hotpe            HotPE via wimboot
item --gap --          === Linux ===
item ubuntu22043      Ubuntu 22.04.3 Live Server
item --gap --          === Windows ===
item windows_hotpe    Windows installation via HotPE
item --gap --          === Tools ===
item shell            iPXE shell
item reboot           Reboot
choose --default hotpe --timeout 15000 target && goto \${target} || goto start

:hotpe
EOF

if [[ "$hotpe_ready" == true ]]; then
  cat >> "$MENU_FILE" <<'EOF'
echo Booting HotPE from ${base-url}
kernel ${image-url}/pe/hotpe/wimboot
initrd ${image-url}/pe/hotpe/bootmgr bootmgr
initrd ${image-url}/pe/hotpe/BCD BCD
initrd ${image-url}/pe/hotpe/boot.sdi boot.sdi
initrd ${image-url}/pe/hotpe/boot.wim boot.wim
boot || goto boot_failed
EOF
else
  cat >> "$MENU_FILE" <<'EOF'
echo HotPE files are not ready.
echo Put wimboot, bootmgr, BCD, boot.sdi and boot.wim under ${image-url}/pe/hotpe/.
goto start
EOF
fi

cat >> "$MENU_FILE" <<'EOF'

:ubuntu22043
EOF

if [[ "$ubuntu_ready" == true ]]; then
  ubuntu_name="$(basename "$ubuntu_iso")"
  cat >> "$MENU_FILE" <<EOF
echo Booting Ubuntu 22.04.3 installer over HTTP
set ubuntu-url \${image-url}/linux/ubuntu-22.04.3
kernel \${ubuntu-url}/casper/vmlinuz ip=dhcp url=\${ubuntu-url}/${ubuntu_name} ---
initrd \${ubuntu-url}/casper/initrd
boot || goto boot_failed
EOF
else
  cat >> "$MENU_FILE" <<'EOF'
echo Ubuntu 22.04.3 files are not ready.
echo Put ISO, casper/vmlinuz and casper/initrd under ${image-url}/linux/ubuntu-22.04.3/.
goto start
EOF
fi

cat >> "$MENU_FILE" <<'EOF'

:windows_hotpe
echo Windows ISO cannot be reliably installed directly by iPXE.
echo Boot HotPE, then open ${image-url}/windows/.
goto hotpe

:shell
shell
goto start

:reboot
reboot

:boot_failed
echo Boot failed. Press any key to return to menu.
prompt
goto start
EOF

printf 'Generated %s\n' "$MENU_FILE"
