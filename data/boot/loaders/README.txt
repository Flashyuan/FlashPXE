请通过导入脚本放入已验证来源的 iPXE loader：

  python3 scripts/boot-assets/import-loader.py <本地源文件> ipxe.efi
  python3 scripts/boot-assets/import-loader.py <本地源文件> snponly.efi

如果拿到的是官方 iPXE 本地归档，例如 ipxeboot.tar.gz，可使用：

  python3 scripts/boot-assets/import-ipxe-archive.py <本地归档> snponly.efi
  python3 scripts/boot-assets/import-ipxe-archive.py <本地归档> ipxe.efi

脚本只接受本地文件，不下载、不生成、不执行 loader，不启用 TFTP、ProxyDHCP
或 DHCP。导入后会在 data/boot/loader-metadata 记录 SHA256、大小、来源和
review 状态。

允许的固定白名单文件名：

- ipxe.efi
- snponly.efi
- undionly.kpxe
- ipxe.iso

SynaBoot 不在仓库中伪造二进制 loader。
SynaBoot 只读取固定白名单文件的元数据、来源记录和 SHA256，不会下载、生成
或启用 loader。
放入真实文件后，Nginx 会通过以下地址提供：

- http://192.168.1.168:18080/boot/loaders/ipxe.efi
- http://192.168.1.168:18080/boot/loaders/snponly.efi
- http://192.168.1.168:18080/boot/loaders/undionly.kpxe
- http://192.168.1.168:18080/boot/loaders/ipxe.iso
