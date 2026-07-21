# PROGRAM-ROLLOUT Windows CI 构建批次（2026-07-22）

## 目标

把 Windows 构建从当前 macOS 工作站迁移到 Windows Runner：Mac 负责提交或手动触发，Windows Runner 负责生成 Python sidecar、Tauri NSIS 安装器和可校验 artifact，随后由人工在 Windows 安装测试。

## 已落地

- 新增 `.github/workflows/windows-desktop-build.yml`。
- Runner 固定为 `windows-latest`，目标固定为 `x86_64-pc-windows-msvc`。
- 使用仓库锁定依赖构建 `pixelle-api-x86_64-pc-windows-msvc.exe`。
- 使用 `npm ci`、Vitest 和 Tauri NSIS build。
- 产出 installer、sidecar 和 SHA-256 manifest artifact。
- workflow 支持 `workflow_dispatch`，Mac 可通过 GitHub Actions 页面/API 触发。
- 新增 `scripts/windows_desktop_artifact_check.py`，拒绝缺失、空文件、错误后缀和错误 sidecar target。

## Windows 人工安装测试清单

拿到 workflow artifact 后，在 Windows 实机执行：

1. 下载 NSIS `.exe` 和 `windows-artifact-manifest.json`，核对 installer/sidecar SHA-256。
2. 安装到默认目录，启动 Pixelle Video Desktop。
3. 验证首次启动、sidecar health、应用中心入口和已有项目读取。
4. 关闭并重新打开应用，验证 sidecar 重启、窗口路由和本地数据回读。
5. 在不点击最终发布的前提下，验证发布中心进入人工确认状态。
6. 记录 Windows 版本、安装器版本、artifact SHA、启动/重启结果和截图；若遇登录、扫码、第三方授权或最终发布按钮，按人工暂停点处理。

## 当前状态与边界

当前状态：`implementation_pass_with_boundary`。独立六维复审已通过，但本机只完成 workflow/manifest 合约测试，尚未在 Windows Runner 真实运行，因此不能把 PG-L-04 标为通过。

独立复审：[`PROGRAM-ROLLOUT-windows-ci-build-review-2026-07-22.md`](PROGRAM-ROLLOUT-windows-ci-build-review-2026-07-22.md)，P0/P1/实质性 P2 均为 0。

本批不自动安装、不自动发布、不改变默认 Publish V2 或抖音灰度；Windows 安装测试必须由人工在 Windows 环境完成。完成一次真实 CI build + Windows 安装/启动/重启证据后，才能更新 PG-L-04 和 PG-L 总审计。
