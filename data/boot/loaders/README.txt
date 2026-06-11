请将已验证来源的 iPXE loader 放在此目录：

- ipxe.efi
- snponly.efi
- undionly.kpxe
- ipxe.iso

SynaBoot 不在仓库中伪造二进制 loader。
SynaBoot 只读取固定白名单文件的元数据和 SHA256，不会下载、生成或启用 loader。
放入真实文件后，Nginx 会通过以下地址提供：

- http://192.168.1.168:18080/boot/loaders/ipxe.efi
- http://192.168.1.168:18080/boot/loaders/snponly.efi
- http://192.168.1.168:18080/boot/loaders/undionly.kpxe
- http://192.168.1.168:18080/boot/loaders/ipxe.iso
