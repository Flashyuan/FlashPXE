#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

info() {
  printf 'INFO: %s\n' "$1"
}

renderer="scripts/image-factory/render-hotpe-automount-assets.py"
secret_dir="data/secrets/hotpe/automount"
public_dir="data/images/pe/hotpe/runtime/AutoMount"
boot_wim="data/images/pe/hotpe/boot.wim"

[[ -f "$renderer" ]] || fail "缺少 HotPE AutoMount 生成器"
python3 -m py_compile "$renderer"

if [[ -e "$secret_dir" ]] && [[ -L "$secret_dir" ]]; then
  fail "secret_dir 禁止为 symlink"
fi
if [[ -e "$public_dir" ]] && [[ -L "$public_dir" ]]; then
  fail "public_dir 禁止为 symlink"
fi

if SYNABOOT_HOTPE_SMB_PASSWORD= python3 "$renderer" >/tmp/synaboot-hotpe-empty.out 2>/tmp/synaboot-hotpe-empty.err; then
  fail "未设置 SMB 密码时生成器必须 fail-closed"
fi
grep -Fq "SYNABOOT_HOTPE_SMB_PASSWORD" /tmp/synaboot-hotpe-empty.err \
  || fail "未设置 SMB 密码时缺少明确错误"

for bad_password in 'bad%value' 'bad!value' 'bad"value' 'bad&value' 'bad|value' 'bad<value' 'bad>value'; do
  if SYNABOOT_HOTPE_SMB_HOST=10.101.8.135 \
    SYNABOOT_HOTPE_SMB_USER=synaboot \
    SYNABOOT_HOTPE_SMB_PASSWORD="$bad_password" \
    python3 "$renderer" >/tmp/synaboot-hotpe-bad-password.out 2>/tmp/synaboot-hotpe-bad-password.err; then
    fail "SMB 密码包含 CMD 敏感字符时必须 fail-closed"
  fi
done

before=""
if [[ -f "$boot_wim" ]]; then
  before="$(sha256sum "$boot_wim" | awk '{print $1}')"
fi

test_password="synaboot-preflight-secret"
render_output="$(
  SYNABOOT_HOTPE_SMB_HOST=10.101.8.135 \
  SYNABOOT_HOTPE_SMB_USER=synaboot \
  SYNABOOT_HOTPE_SMB_PASSWORD="$test_password" \
  python3 "$renderer"
)"
printf '%s\n' "$render_output" | grep -Fq "$test_password" && fail "生成器 stdout 泄漏 SMB 密码"

after=""
if [[ -f "$boot_wim" ]]; then
  after="$(sha256sum "$boot_wim" | awk '{print $1}')"
fi
[[ "$before" == "$after" ]] || fail "生成器修改了 boot.wim"

git check-ignore -q "$secret_dir/mount-synaboot-shares.cmd" \
  || fail "含密 HotPE 挂载脚本未被 .gitignore 覆盖"

[[ -f "$secret_dir/mount-synaboot-shares.cmd" ]] || fail "缺少生成的 SMB 挂载脚本"
[[ -f "$secret_dir/load-hotpe-modules.cmd" ]] || fail "缺少生成的 HPM 加载脚本"
[[ -f "$public_dir/manifest.json" ]] || fail "缺少公开 manifest"

grep -Fq "$test_password" "$secret_dir/mount-synaboot-shares.cmd" \
  || fail "含密脚本未写入测试密码，无法验证真实生成路径"
if grep -RIl --exclude='manifest.json' "$test_password" "$public_dir" 2>/dev/null | grep -q .; then
  fail "公开 AutoMount 目录泄漏 SMB 密码"
fi
if git diff -- . ':!docs/SUBAGENT_SESSION_POOL.md' | grep -Fq "$test_password"; then
  fail "Git diff 泄漏 SMB 密码"
fi

for forbidden in \
  "del /s" "format " "diskpart" "Clear-Disk" "Initialize-Disk" "bcdedit" \
  "route"" add" "ipconfig /release" "netsh advfirewall" "Set-DnsClient" "New-NetRoute"; do
  if grep -RFi "$forbidden" "$secret_dir" scripts/image-factory/templates/hotpe "$renderer" >/dev/null; then
    fail "HotPE AutoMount 资产包含禁止命令: $forbidden"
  fi
done

grep -Fq "call :MountShare Z:" "$secret_dir/mount-synaboot-shares.cmd" || fail "缺少 Z: 映射"
grep -Fq "call :MountShare M:" "$secret_dir/mount-synaboot-shares.cmd" || fail "缺少 M: 映射"
grep -Fq "call :MountShare W:" "$secret_dir/mount-synaboot-shares.cmd" || fail "缺少 W: 映射"
grep -Fq "net use %DRIVE%" "$secret_dir/mount-synaboot-shares.cmd" || fail "缺少受控 net use 映射函数"
grep -Fq "start \"\" \"M:\\" "$secret_dir/load-hotpe-modules.cmd" || fail "缺少模块目录兜底打开动作"

if docker compose config --services 2>/dev/null | grep -Eq 'smb|samba'; then
  fail "主 docker-compose.yml 不应包含 SMB 服务"
fi
docker compose -p synaboot-smb-lab -f docker-compose.smb-lab.yml config >/tmp/synaboot-smb-lab-config.yml
grep -Fq "read_only: true" /tmp/synaboot-smb-lab-config.yml || fail "SMB lab 容器必须 read_only"
grep -Fq "target: /srv/synaboot/images" /tmp/synaboot-smb-lab-config.yml \
  || fail "SMB lab 必须挂载到 /srv/synaboot/images"
grep -Fq "read_only: true" /tmp/synaboot-smb-lab-config.yml \
  || fail "SMB lab 的 data/images 挂载必须只读"

if grep -REi 'casper|nfsroot|squashfs' \
  "$renderer" scripts/image-factory/templates/hotpe "$secret_dir" 2>/dev/null; then
  fail "HotPE AutoMount 生成器或产物不应包含 Ubuntu livefs/NFS 语义"
fi
info "hotpe_automount_secret_dir=${secret_dir}"
info "hotpe_automount_public_dir=${public_dir}"
info "APPROVED: HotPE AutoMount 生成器和实验资产通过安全预检"
