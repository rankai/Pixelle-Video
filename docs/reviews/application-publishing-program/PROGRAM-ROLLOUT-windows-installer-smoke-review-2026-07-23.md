# PROGRAM-ROLLOUT / PG-L Windows installer smoke 独立六维复审

日期：2026-07-23  
审查线程：`/root/pg_l_windows_smoke_reviewer`  
审查结论：`implementation_pass_with_boundary`  
问题等级：P0=0，P1=0，实质性 P2=0

## 审查范围

本次复审覆盖 Windows CI 构建、PyInstaller sidecar、NSIS 安装器、Tauri 应用启动/关闭/重开循环、sidecar 健康检查、端口释放、失败诊断和证据上传。审查线程只读检查，没有修改代码或证据。

## 六维验证结果

1. **需求完整性**：工作流包含 Windows runner、NSIS 安装、直接 sidecar smoke、两轮 Tauri 启动/健康/关闭/端口释放、失败时证据上传、安装包清单与 SHA-256；最终发布点击和外部动作保持为 0。
2. **逻辑正确性**：Run `30028402812` / Job `89278574897` 真实通过；安装退出码为 0，两轮 health 通过，监听进程 owner 为 `pixelle-api.exe`，优雅关闭且端口释放。此前 sidecar 启动失败已由 Windows cp1252 不兼容的 Unicode banner 修复；`docs/contracts` 已随 sidecar 打包。
3. **边界情况**：安装目录隔离并校验，启动/健康/安装/端口查询/进程树/清理均有超时或 fail-closed 处理；诊断输出脱敏，不泄露 PID、路径、授权或平台数据。
4. **代码质量**：PowerShell smoke、sidecar 诊断、工作流路径触发和错误摘要职责清晰；没有引入最终发布或第三方授权副作用。
5. **测试覆盖**：定向测试 13 passed；Ruff、workflow YAML 解析和 `git diff --check` 通过；Windows Runner artifact 与 PR 必需检查均成功。
6. **实际运行结果**：安装器 artifact 与 sidecar artifact 均已下载、解析并记录 SHA-256；两轮 Tauri smoke 真实完成启动、health、sidecar owner、优雅关闭和端口释放。

## 证据

- Windows workflow：Run `30028402812`，Job `89278574897`
- 安装器 smoke artifact：`8572608418`，安装器 SHA-256：`11665ccfffadddf6166526a42bd61d40224565d208b5e889c97a1f7873061264`
- sidecar smoke artifact：`8572367050`
- installer artifact：`8572611983`
- PR 必需检查：`Windows NSIS installer and sidecar` = success

## 保留边界

这次结论不关闭 PG-L：真实 Windows 用户设备人工安装/启动/重启/sidecar health、产品负责人签字（PG-L-10）、真实平台 rollback/WebView SLA（PG-L-11）仍是外部边界。默认 Publish V2、最终发布点击、第三方授权和平台灰度继续关闭。

