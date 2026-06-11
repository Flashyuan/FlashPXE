请将已验证来源的 iPXE loader 放在此目录：

- ipxe.efi
- ipxe.iso

SynaBoot 不在仓库中伪造二进制 loader。
放入真实文件后，Nginx 会通过以下地址提供：

- http://192.168.1.168:8080/boot/loaders/ipxe.efi
- http://192.168.1.168:8080/boot/loaders/ipxe.iso
