# PROGRAM-ROLLOUT Windows hotfix 构建与安装器证据

- 日期：2026-07-28
- 分支：`codex/publish-v2-sidecar-gate`
- 提交：`8de798d260459bb0e62d44b0bb7ab670f4b8b92f`
- Workflow：`Windows Desktop Build`
- Run：[`30320633215`](https://github.com/rankai/Pixelle-Video/actions/runs/30320633215)
- 结果：`success`

## 构建结果

Hosted Windows Runner 已完成：

- Windows sidecar 构建；
- Tauri NSIS 安装器构建；
- 静默安装；
- 桌面应用两轮启动、关闭和重开；
- sidecar health、监听进程归属和端口释放；
- artifact manifest 和 smoke evidence 上传。

`windows-installer-smoke.json` 记录：

- 安装状态：`passed`
- cycle 1 health：`passed`
- cycle 2 health：`passed`
- 两轮关闭：`graceful`
- 两轮端口释放：`true`
- external actions：`0`
- final publish clicks：`0`

## 下载后摘要复核

本地目录：

`/Users/nickfury/Downloads/Pixelle-Video-Windows-20260728`

| 文件 | SHA-256 |
| --- | --- |
| `Pixelle Video_0.1.0_x64-setup.exe` | `b9e6fbafdf545728fcc9869061fccbc52bb67b4d1395cd0f6e8e71f17484051c` |
| `pixelle-api-x86_64-pc-windows-msvc.exe` | `07fb8368ebbdfb382f75cb6d1fdc85867b320d7632b8055b8b52ff63898d893d` |
| `windows-artifact-manifest.json` | `2a564c2ad05e92d926c360e318e06e541d00ade232200054c3f35e54b3c2078b` |
| `windows-installer-smoke.json` | `86274ecf1e0511e1179626cce727f61ffb6825b703f1de7cf52d687d4772c6d8` |

安装器与 sidecar 摘要和 Windows Runner 生成的 manifest 一致。

## 边界

- 用户明确表示不对本次安装包进行真实设备测试；
- Hosted Runner smoke 不能替代真实用户 Windows 设备验收；
- `PROGRAM-ROLLOUT/PG-L` 的产品负责人签字、真实平台 rollback 和原生 WebView SLA 仍保持 open；
- 默认 Publish V2、最终发布自动点击和任何真实平台动作均未开启。
