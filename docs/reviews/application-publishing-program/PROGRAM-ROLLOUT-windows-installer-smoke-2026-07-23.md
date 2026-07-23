# PROGRAM-ROLLOUT Windows 安装器与 sidecar smoke 收口（2026-07-23）

## 结论

Run 30028402812 / job 89278574897 在 windows-latest 上通过了 Windows sidecar 直接健康诊断和 NSIS 安装器生命周期 smoke。结论为 implementation_pass_with_boundary：Windows Runner 自动化安装、启动、sidecar health、关闭、重开和端口释放已通过；这不等价于产品负责人在真实 Windows 设备上的人工验收，也不关闭 PG-L、PG-L-10 或 PG-L-11。

## 根因与修复

前置 Run 30027262943 的 sidecar stderr 证明 Windows 进程以 sidecar_exit_1 退出，原因是 api/app.py 启动 banner 使用 Unicode 方框字符，Windows cp1252 stdout 在 uvicorn 启动前触发 UnicodeEncodeError。本批完成：

- api/app.py 将冻结 sidecar 启动 banner 改为 ASCII-only；
- desktop/scripts/build_sidecar.py 用 PyInstaller --add-data 打包 docs/contracts，覆盖应用中心和发布数据库 schema；
- workflow 纳入 docs/contracts/** 触发路径；
- 增加直接 sidecar smoke、安装器生命周期 smoke、退出码/脱敏 stderr 证据与契约测试；
- 默认发布安全边界不变：external_actions=0、final_publish_clicks=0。

## 真实 Runner 证据

- Workflow：https://github.com/rankai/Pixelle-Video/actions/runs/30028402812
- Installer smoke artifact：8572608418，SHA-256 digest sha256:3d483c3a202d30f9d141fe87c5c84dd6bf96ca8d6377099dc1bc0cd4fce7fb6a
- Sidecar smoke artifact：8572367050，SHA-256 digest sha256:4707b8cabffb90d3566f83d9a9d4517aaff495562e9be4d1fc1952e61fa542d2
- Installer：Pixelle Video_0.1.0_x64-setup.exe，134,242,602 bytes，SHA-256 11665ccfffadddf6166526a42bd61d40224565d208b5e889c97a1f7873061264
- Sidecar：pixelle-api-x86_64-pc-windows-msvc.exe

Installer smoke JSON：

- status=passed_with_boundary、install.status=passed、NSIS exit code 0；
- cycle 1/2 均 process_started=true、health=passed、listener owner=pixelle-api.exe、close=graceful、port_released=true；
- cleanup_port_released=true，external_actions=0，final_publish_clicks=0。

Sidecar direct smoke 同样 status=passed_with_boundary、health passed、port released。其诊断工作目录不含 Tauri resource templates，因此 stderr 仍记录默认模板 warning；这不影响安装后的 Tauri smoke，且没有把该 warning 误报为完整业务渲染验收。

## 本地验证

- uv run pytest -q tests/desktop_sidecar_test.py tests/windows_desktop_ci_contract_test.py tests/windows_installer_smoke_contract_test.py tests/windows_sidecar_smoke_contract_test.py：13 passed；
- Ruff、workflow YAML parse、git diff --check：通过。

## 未关闭边界

本批不执行真实 Windows 用户设备安装、不做产品签字、不做真实平台双向 rollback 或原生 WebView SLA 验收；不改变默认 Publish V2、抖音灰度或最终发布按钮。台账仍保持 PROGRAM-ROLLOUT/PG-L_waiting_user，等待人工 Windows 安装回传与 PG-L-10/PG-L-11 外部证据。
