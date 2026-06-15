# 镜像制作工厂

Phase 2 的镜像工厂只做任务编排与模板生成，不执行破坏性磁盘操作。

## 支持任务

- `ubuntu-autoinstall-template`：生成 `user-data` 与 `meta-data` 模板
- `ubuntu-xorriso-iso`：生成 Ubuntu ISO 任务说明与安全输出目录
- `windows-adk-package`：生成 Windows ADK/DISM 外部构建包说明
- `hotpe-iso-prepare`：为 HotPE ISO 生成准备任务包，并调用受限 HotPE
  本地准备脚本
- `ubuntu-iso-extract-kernel-initrd`：为 Ubuntu/Linux ISO 生成 kernel/initrd
  提取任务包

任务输出目录：

```text
data/builds/<job-id>/
```

## Ubuntu Autoinstall

默认模板不会自动写入真实磁盘。若后续要加入自动分区配置，必须由管理员明确确认。

生成的密码字段必须替换为加密 hash，不应保存明文密码。

默认 `user-data` 不包含 `storage:` 自动分区段，避免触发自动格式化语义。

任务创建后默认状态为 `draft`。后续执行或推进状态必须由管理员显式确认。

## ISO 准备任务

ISO 准备任务只创建可审查的任务包，不会在创建时执行解包。

任务包包含：

- `manifest.json`：记录源 ISO、目标输出、安全边界和本机工具探测结果。
- `README.md`：给管理员审查和执行前确认。
- `prepare.sh`：幂等脚本，执行时再次检查路径、工具和目标文件。

Ubuntu/Linux 提取任务只允许从源 ISO 提取：

```text
casper/vmlinuz
casper/initrd
```

管理员已将 Linux ISO 放入 `data/images/linux/...` 后，也可以使用本地批量准备脚本：

```bash
bash scripts/image-factory/prepare-linux-boot-artifacts.sh
```

该脚本只处理 `data/images/linux/**/*.iso`。它会优先使用本机已有 `bsdtar`
或 `7z`；若没有外部工具，则使用项目内 `extract-iso9660-file.py` 只读提取器
提取 `casper/vmlinuz` 与 `casper/initrd`。输出仍写回对应 ISO 目录下的
`casper/`。如果目标文件已存在、路径越界或解包结果不是普通文件，脚本会
fail-fast，不会安装依赖、不会挂载 ISO、不会处理 Windows/HotPE。

HotPE 本地准备脚本可以尝试从 `data/images/pe/hotpe/*.iso` 的固定候选路径
提取 `bootmgr`、`BCD`、`boot.sdi`、`boot.wim`：

```bash
bash scripts/image-factory/prepare-hotpe-boot-artifacts.sh
```

它不会自动准备 `wimboot`。`wimboot` 通常来自 iPXE/wimboot 发布包或本地可信
构建产物，需要管理员记录来源、版本和 sha256 后手工导入。导入 provenance
写入非公开 `data/metadata/wimboot-provenance/`，不会放入公开 `/images/`
仓库。

```bash
python3 scripts/boot-assets/import-wimboot.py /path/to/wimboot \
  --reviewed-by local-admin \
  --source-label official-ipxe-wimboot \
  --source-version v2.9.0
```

如果 HotPE ISO 只暴露 `readme.txt`、使用隐藏 El Torito 启动镜像，或文件不在
固定候选路径内，脚本会 fail-fast 并要求人工确认布局，避免按二进制偏移猜测
提取错误文件。

安全边界：

- 原始 ISO 只读，不删除、不改写。
- 输出只写入 `data/images` 对应子目录或 `data/builds/<job-id>/`。
- 目标文件存在时拒绝覆盖。
- 解包得到的 `casper/vmlinuz` 和 `casper/initrd` 必须是普通文件，若为
  symlink、特殊文件或缺失文件则拒绝复制。
- HotPE 解包得到的 `bootmgr`、`BCD`、`boot.sdi` 和 `boot.wim` 也必须是
  普通文件，若为 symlink、特殊文件或缺失文件则拒绝复制。
- 只探测本机已有 `bsdtar` 或 `7z`，不会自动安装新依赖。
- 不执行分区、格式化、写真实块设备、挂载宿主敏感目录等操作。

## Windows ADK/DISM

Windows 镜像封装应在 Windows 构建机执行，并安装 Windows ADK。

SynaBoot 的 Ubuntu 服务器只负责生成任务包、保存模板和归档产物，不承诺在 Linux
上完整、安全、通用地封装 Windows ISO。
