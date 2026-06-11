# SynaBoot

内网 iPXE HTTP Boot 与系统镜像部署平台。

## Phase 1 原则

零网络侵入。不启用 DHCP、ProxyDHCP、TFTP，不修改路由器、网关、DNS 或防火墙。

用户通过 iPXE USB/ISO/EFI 或手动 UEFI HTTP Boot 加载：

```text
http://192.168.1.168:8080/boot/menu.ipxe
```

## 快速启动

```bash
cp .env.example .env
bash init-directories.sh
bash scripts/preflight/check-network-safety.sh
docker compose config
docker compose up -d
```

如果当前宿主机 `8080/tcp` 已被占用，请先确认端口归属，不要直接停止未知服务。
本机临时验证可以使用：

```bash
SYNABOOT_HTTP_BIND=127.0.0.1:18180 SYNABOOT_HTTP_PORT=18180 docker compose up -d --build
```

如需启用扫描、生成菜单、创建任务等写操作，请在 `.env` 设置强随机
`SYNABOOT_ADMIN_TOKEN`。未设置时写接口默认禁用。

端口变量说明：

- `SYNABOOT_HTTP_BIND`：Docker 宿主机发布绑定，默认 `8080`
- `SYNABOOT_HTTP_PORT`：应用展示端口，必须是整数，默认 `8080`

访问：

- Web UI：`http://192.168.1.168:8080`
- 镜像仓库：`http://192.168.1.168:8080/images/`
- iPXE 菜单：`http://192.168.1.168:8080/boot/menu.ipxe`

iPXE 启动介质说明：

```bash
bash scripts/create-ipxe-usb.sh
```

## 镜像路径

所有镜像都应放在 `data/images` 下：

```text
data/images/pe/hotpe/
data/images/windows/win11/
data/images/linux/ubuntu-22.04.3/
data/images/tools/
data/images/custom/
```

详见 `PLAN.md`、`AGENTS.md` 和 `docs/`。
