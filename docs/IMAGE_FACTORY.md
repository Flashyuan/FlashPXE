# 镜像制作工厂

Phase 1 的镜像工厂只做任务编排与模板生成，不执行破坏性磁盘操作。

## 支持任务

- `ubuntu-autoinstall`：生成 `user-data` 与 `meta-data` 模板
- `windows-adk-package`：生成 Windows ADK/DISM 外部构建包说明

任务输出目录：

```text
data/builds/<job-id>/
```

## Ubuntu Autoinstall

默认模板不会自动写入真实磁盘。若后续要加入自动分区配置，必须由管理员明确确认。

生成的密码字段必须替换为加密 hash，不应保存明文密码。

默认 `user-data` 不包含 `storage:` 自动分区段，避免触发自动格式化语义。

## Windows ADK/DISM

Windows 镜像封装应在 Windows 构建机执行，并安装 Windows ADK。

SynaBoot 的 Ubuntu 服务器只负责生成任务包、保存模板和归档产物，不承诺在 Linux
上完整、安全、通用地封装 Windows ISO。
