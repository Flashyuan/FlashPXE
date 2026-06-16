#!/usr/bin/env bash
set -euo pipefail

# SYNABOOT_LAB_ONLY_BIND=10.101.8.135
# SYNABOOT_LAB_ONLY_INTERFACE=ens19
# SYNABOOT_REQUIRES_MANUAL_SUDO_CONFIRMATION=1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

LAB_IFACE="${SYNABOOT_LAB_IFACE:-ens19}"
LAB_IP="${SYNABOOT_LAB_IP:-10.101.8.135}"
NFS_IP="${SYNABOOT_NFS_LAB_IP:-10.101.8.136}"
LAB_CIDR="${SYNABOOT_LAB_CIDR:-10.101.8.0}"
LAB_NETMASK="${SYNABOOT_LAB_NETMASK:-255.255.255.0}"
PROD_IFACE="${SYNABOOT_PROD_IFACE:-ens18}"
PROD_IP="${SYNABOOT_PROD_IP:-192.168.1.168}"
HTTP_PORT="${SYNABOOT_HTTP_PORT:-18080}"
STATE_DIR="$ROOT_DIR/data/builds/proxynet-lab"
TFTP_PARENT="${SYNABOOT_LAB_TFTP_PARENT:-/tmp/synaboot-proxynet-lab}"
TFTP_ROOT="$TFTP_PARENT/tftp"
CONF_FILE="$STATE_DIR/dnsmasq-proxynet-lab.conf"
PID_FILE="$STATE_DIR/dnsmasq.pid"
LOG_FILE="$STATE_DIR/dnsmasq.log"

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

info() {
  printf 'INFO: %s\n' "$1"
}

[[ "$LAB_IFACE" == "ens19" ]] || fail "实验接口必须是 ens19，当前: ${LAB_IFACE}"
[[ "$LAB_IP" == "10.101.8.135" ]] || fail "实验 IP 必须是 10.101.8.135，当前: ${LAB_IP}"
[[ "$NFS_IP" == "10.101.8.136" ]] || fail "NFS 实验 IP 必须是 10.101.8.136，当前: ${NFS_IP}"
[[ "$PROD_IFACE" == "ens18" ]] || fail "生产接口期望 ens18，当前: ${PROD_IFACE}"
[[ "$PROD_IP" == "192.168.1.168" ]] || fail "生产 IP 期望 192.168.1.168，当前: ${PROD_IP}"

ip -4 addr show dev "$LAB_IFACE" | grep -Fq "${LAB_IP}/24" \
  || fail "${LAB_IFACE} 未持有 ${LAB_IP}/24"
ip -4 addr show dev "$PROD_IFACE" | grep -Fq "${PROD_IP}/24" \
  || fail "${PROD_IFACE} 未持有 ${PROD_IP}/24"
ip route show default | grep -Fq "dev ${PROD_IFACE}" \
  || fail "默认路由必须仍在生产接口 ${PROD_IFACE}"

[[ -f data/boot/menu.ipxe ]] || fail "缺少 data/boot/menu.ipxe"
[[ -f data/boot/loaders/snponly.efi ]] || fail "缺少 data/boot/loaders/snponly.efi"
[[ -f data/boot/loaders/ipxe.efi ]] || fail "缺少 data/boot/loaders/ipxe.efi"

mkdir -p "$STATE_DIR" "$TFTP_ROOT"
case "$STATE_DIR" in
  "$ROOT_DIR/data/builds/proxynet-lab") ;;
  *) fail "STATE_DIR 越界: ${STATE_DIR}" ;;
esac
case "$TFTP_ROOT" in
  /tmp/synaboot-proxynet-lab/tftp) ;;
  *) fail "TFTP_ROOT 必须是隔离实验运行目录: ${TFTP_ROOT}" ;;
esac
chmod 0755 "$TFTP_PARENT" "$TFTP_ROOT"
find "$TFTP_ROOT" -mindepth 1 -maxdepth 1 -type f -delete
cp data/boot/loaders/snponly.efi "$TFTP_ROOT/snponly.efi"
cp data/boot/loaders/ipxe.efi "$TFTP_ROOT/ipxe.efi"
chmod 0644 "$TFTP_ROOT/snponly.efi" "$TFTP_ROOT/ipxe.efi"

[[ -f data/images/pe/hotpe/wimboot ]] || fail "缺少 data/images/pe/hotpe/wimboot"
[[ -f data/images/pe/hotpe/bootmgr ]] || fail "缺少 data/images/pe/hotpe/bootmgr"
[[ -f data/images/pe/hotpe/bootx64.efi ]] || fail "缺少 data/images/pe/hotpe/bootx64.efi"
[[ -f data/images/pe/hotpe/BCD.uefi ]] || fail "缺少 data/images/pe/hotpe/BCD.uefi"
[[ -f data/images/pe/hotpe/boot.sdi ]] || fail "缺少 data/images/pe/hotpe/boot.sdi"
[[ -f data/images/pe/hotpe/boot.wim ]] || fail "缺少 data/images/pe/hotpe/boot.wim"
[[ -f data/boot/flashpxe-logo.png ]] || fail "缺少 data/boot/flashpxe-logo.png"
[[ -f data/images/windows/win11/boot/BCD ]] || fail "缺少 data/images/windows/win11/boot/BCD"
[[ -f data/images/windows/win11/boot/boot.sdi ]] || fail "缺少 data/images/windows/win11/boot/boot.sdi"
[[ -f data/images/windows/win11/boot/boot.wim ]] || fail "缺少 data/images/windows/win11/boot/boot.wim"
[[ -f data/images/windows/win11/boot/bootx64.efi ]] || fail "缺少 data/images/windows/win11/boot/bootx64.efi"
[[ -f data/images/linux/ubuntu-22.04.3/casper/vmlinuz ]] || fail "缺少 Ubuntu 22.04.3 vmlinuz"
[[ -f data/images/linux/ubuntu-22.04.3/casper/initrd ]] || fail "缺少 Ubuntu 22.04.3 initrd"
[[ -f data/images/linux/ubuntu-22.04.3/casper/filesystem.squashfs ]] || fail "缺少 Ubuntu 22.04.3 livefs"
[[ -f data/images/linux/ubuntu-22.04.3/ubuntu-22.04.3-desktop-amd64.iso ]] || fail "缺少 Ubuntu 22.04.3 ISO fallback"
[[ -f data/images/linux/ubuntu-24.04/casper/vmlinuz ]] || fail "缺少 Ubuntu 24.04 vmlinuz"
[[ -f data/images/linux/ubuntu-24.04/casper/initrd ]] || fail "缺少 Ubuntu 24.04 initrd"
find data/images/linux/ubuntu-24.04/casper -maxdepth 1 -type f -name '*.squashfs' -print -quit | grep -q . \
  || fail "缺少 Ubuntu 24.04 livefs"
[[ -f data/images/linux/ubuntu-24.04/ubuntu-24.04.3-desktop-amd64.iso ]] || fail "缺少 Ubuntu 24.04 ISO fallback"

cat > data/boot/menu-lab.ipxe <<EOF
#!ipxe

set server-ip ${LAB_IP}
set base-url http://\${server-ip}:${HTTP_PORT}
set boot-url \${base-url}/boot
set image-url \${base-url}/images
isset \${platform} || set platform unknown

:start
console --x 1024 --y 768 || echo Console resize skipped
console --picture \${boot-url}/flashpxe-logo.png || echo FlashPXE picture skipped
colour --basic 0 --rgb 0x000000 0 || echo Colour command skipped
colour --basic 6 --rgb 0x00aaaa 6 || echo Colour command skipped
colour --basic 7 --rgb 0xffffff 7 || echo Colour command skipped
colour --basic 1 --rgb 0x00aaaa 1 || echo Colour command skipped
cpair --foreground 7 --background 0 0 || echo Colour pair skipped
cpair --foreground 6 --background 0 1 || echo Colour pair skipped
cpair --foreground 7 --background 1 2 || echo Colour pair skipped
cpair --foreground 6 --background 0 3 || echo Colour pair skipped
menu FlashPXE
item --gap --                                      FlashPXE
item --gap --                                A fast netboot console
item --gap --          ${LAB_IP}    \${platform}    \${base-url}
item --gap --          ----------------------------------------------------------------------------
item --gap --          ISO Boot Menu
item --gap --          SIZE      IMAGE
item --key w windows_setup  5162MB   Windows 11 24H2 Pro Chinese x64
item --key h hotpe          1058MB   HotPE V2.8
item --key 1 linux_linux_ubuntu_22_04_3  4700MB   Ubuntu 22.04.3 desktop amd64
item --key 2 linux_linux_ubuntu_24_04    5900MB   Ubuntu 24.04 desktop amd64
choose --default windows_setup --timeout 15000 target && goto \${target} || goto start

:windows_setup
echo Loading Windows 11 installer...
imgfree
kernel \${image-url}/pe/hotpe/wimboot
initrd -n BCD \${image-url}/windows/win11/boot/BCD BCD
initrd -n boot.sdi \${image-url}/windows/win11/boot/boot.sdi boot.sdi
initrd -n boot.wim \${image-url}/windows/win11/boot/boot.wim boot.wim
boot || goto boot_failed

:hotpe
echo Loading HotPE recovery environment...
imgfree
kernel \${image-url}/pe/hotpe/wimboot pause
initrd -n bootmgfw.efi \${image-url}/windows/win11/boot/bootx64.efi bootmgfw.efi
initrd -n BCD \${image-url}/windows/win11/boot/BCD BCD
initrd -n boot.sdi \${image-url}/windows/win11/boot/boot.sdi boot.sdi
initrd -n boot.wim \${image-url}/pe/hotpe/boot.wim boot.wim
boot || goto boot_failed

:linux_linux_ubuntu_22_04_3
echo Loading Ubuntu 22.04.3 NFS livefs...
echo NFS source: ${NFS_IP}:/ubuntu-22.04.3
echo This mode mounts casper/filesystem.squashfs from the read-only NFS export.
kernel \${base-url}/images/linux/ubuntu-22.04.3/casper/vmlinuz ip=dhcp boot=casper netboot=nfs nfsroot=${NFS_IP}:/ubuntu-22.04.3 ---
initrd \${base-url}/images/linux/ubuntu-22.04.3/casper/initrd
boot || goto boot_failed

:linux_linux_ubuntu_24_04
echo Loading Ubuntu 24.04 NFS livefs...
echo NFS source: ${NFS_IP}:/ubuntu-24.04
echo This mode mounts casper/*.squashfs from the read-only NFS export.
kernel \${base-url}/images/linux/ubuntu-24.04/casper/vmlinuz ip=dhcp boot=casper netboot=nfs nfsroot=${NFS_IP}:/ubuntu-24.04 ---
initrd \${base-url}/images/linux/ubuntu-24.04/casper/initrd
boot || goto boot_failed

:boot_failed
echo Boot failed. Press any key to return to FlashPXE.
prompt
goto start
EOF
chmod 0644 data/boot/menu-lab.ipxe

cat > data/boot/lab-chain.ipxe <<EOF
#!ipxe

echo SynaBoot Phase 3.3-B ProxyNet lab chain
dhcp || goto failed
chain http://${LAB_IP}:${HTTP_PORT}/boot/menu-lab.ipxe || goto failed

:failed
echo Failed to reach SynaBoot lab HTTP menu.
shell
EOF
chmod 0644 data/boot/lab-chain.ipxe

if grep -Fq "$PROD_IP" data/boot/menu-lab.ipxe data/boot/lab-chain.ipxe; then
  fail "lab iPXE 文件不得包含生产 IP ${PROD_IP}"
fi

cat > "$CONF_FILE" <<EOF
# SynaBoot Phase 3.3-B ProxyNet lab config.
# Generated file; do not use outside the isolated ${LAB_CIDR}/24 lab.
port=0
interface=${LAB_IFACE}
listen-address=${LAB_IP}
bind-interfaces
no-dhcp-interface=${PROD_IFACE}
no-hosts
no-resolv
log-dhcp
log-facility=${LOG_FILE}
pid-file=${PID_FILE}
leasefile-ro
dhcp-leasefile=${STATE_DIR}/dnsmasq.leases

dhcp-range=${LAB_CIDR},proxy,${LAB_NETMASK}
dhcp-vendorclass=set:pxeclient,PXEClient
dhcp-vendorclass=set:httpclient,HTTPClient
dhcp-match=set:ipxe,175
dhcp-match=set:efi64,option:client-arch,7
dhcp-match=set:efi64,option:client-arch,9
tag-if=set:bootclient,tag:pxeclient
tag-if=set:bootclient,tag:httpclient
tag-if=set:uefi_pxe,tag:pxeclient,tag:efi64
dhcp-ignore=tag:!bootclient
dhcp-ignore=tag:pxeclient,tag:!efi64

dhcp-boot=tag:ipxe,http://${LAB_IP}:${HTTP_PORT}/boot/menu-lab.ipxe
dhcp-boot=tag:httpclient,http://${LAB_IP}:${HTTP_PORT}/boot/loaders/ipxe.efi
dhcp-boot=tag:uefi_pxe,tag:!ipxe,snponly.efi,,${LAB_IP}
pxe-prompt=tag:uefi_pxe,tag:!ipxe,"SynaBoot ProxyNet lab",0
pxe-service=tag:uefi_pxe,tag:!ipxe,x86-64_EFI,"SynaBoot iPXE",snponly.efi,${LAB_IP}

enable-tftp=${LAB_IFACE}
tftp-root=${TFTP_ROOT},${LAB_IFACE}
tftp-no-fail
EOF

dnsmasq --test --conf-file="$CONF_FILE" >/dev/null

info "lab_menu=http://${LAB_IP}:${HTTP_PORT}/boot/menu-lab.ipxe"
info "lab_chain=http://${LAB_IP}:${HTTP_PORT}/boot/lab-chain.ipxe"
info "ubuntu_nfs=${NFS_IP}:/ubuntu-22.04.3 ${NFS_IP}:/ubuntu-24.04"
info "http_loader=http://${LAB_IP}:${HTTP_PORT}/boot/loaders/ipxe.efi"
info "pxe_loader=snponly.efi"
info "dnsmasq_conf=${CONF_FILE}"
info "tftp_root=${TFTP_ROOT}"
