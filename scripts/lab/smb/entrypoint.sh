#!/bin/sh
set -eu

SMB_PASSWORD="${SYNABOOT_SMB_PASSWORD:-synaboot-lab}"

if [ -z "$SMB_PASSWORD" ]; then
  echo "SYNABOOT_SMB_PASSWORD must not be empty" >&2
  exit 1
fi

mkdir -p /var/lib/samba/private /var/cache/samba /var/log/samba /run/samba
chmod 0700 /var/lib/samba/private

printf '%s\n%s\n' "$SMB_PASSWORD" "$SMB_PASSWORD" | smbpasswd -a -s synaboot >/dev/null
smbpasswd -e synaboot >/dev/null

exec smbd --foreground --no-process-group --configfile=/etc/samba/smb.conf
